"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge, Button, Card, Field, Input, Skeleton, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Brand, Budget, BudgetLine, Provider } from "@/lib/types";

export function money(n: number) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function useBudget(brandId: string) {
  return useQuery({ queryKey: ["brand", brandId, "budget"], queryFn: () => api.get<Budget>(`/brands/${brandId}/budget`) });
}

/** This month's spend for a brand: Claude (the studio's bill, admins set the budget) and the client's capped tools. */
export function SpendingCard({ brand }: { brand: Brand }) {
  const qc = useQueryClient();
  const toast = useToast();
  const me = useMe();
  const isAdmin = me.data?.org_role === "admin";
  const budget = useBudget(brand.id);
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => api.get<Provider[]>("/providers"), staleTime: 3600_000 });
  const [limit, setLimit] = useState("");
  useEffect(() => {
    if (budget.data) setLimit(budget.data.claude_brand_usd != null ? String(budget.data.claude_brand_usd) : "");
  }, [budget.data]);
  const save = useMutation({
    mutationFn: (value: number | null) => api.put<Budget>(`/brands/${brand.id}/budget`, { limit_usd: value }),
    onSuccess: (b) => { toast("Budget saved", "success"); qc.setQueryData(["brand", brand.id, "budget"], b); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  if (!budget.data) return <Card className="max-w-xl p-6"><Skeleton className="h-24" /></Card>;
  const b = budget.data;
  const name = (id: string) => providers.data?.find((p) => p.id === id)?.name ?? id;
  const parsed = limit.trim() === "" ? null : Number(limit);
  const bad = parsed != null && (!Number.isFinite(parsed) || parsed < 0);
  return (
    <Card className="max-w-xl space-y-5 p-6">
      <div>
        <h3 className="text-sm font-semibold">Spending in {b.month}</h3>
        <p className="mt-0.5 text-[13px] text-text-2">Checked before anything is spent: a message is refused once Claude&apos;s budget is used up,
          and a paid step is declined once its account&apos;s cap is reached.</p>
      </div>
      <Meter label="Claude" hint="the studio's Anthropic bill for this brand" line={b.claude}
        none={b.claude_default_usd == null ? "No monthly limit" : undefined} />
      {isAdmin ? (
        <Field label="Monthly Claude budget (USD)"
          hint={b.claude_default_usd != null ? `Empty uses the studio default, ${money(b.claude_default_usd)}. 0 switches Claude off for this brand.`
            : "Empty means no limit. 0 switches Claude off for this brand."}>
          <div className="flex gap-2">
            <Input inputMode="decimal" placeholder={b.claude_default_usd != null ? `default ${b.claude_default_usd}` : "no limit"}
              aria-invalid={bad || undefined} value={limit} onChange={(e) => setLimit(e.target.value)} />
            <Button variant="primary" disabled={bad} loading={save.isPending} onClick={() => save.mutate(parsed)}>Save</Button>
          </div>
        </Field>
      ) : (
        <p className="text-xs text-text-3">An admin sets the Claude budget.</p>
      )}
      {b.tools.length > 0 && (
        <div className="space-y-3 border-t border-border pt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-3">Client accounts (caps set on Connections)</p>
          {b.tools.map((t) => <Meter key={t.provider} label={name(t.provider)} line={t} none="No cap: approved estimates are still recorded" />)}
        </div>
      )}
    </Card>
  );
}

function Meter({ label, hint, line, none }: { label: string; hint?: string; line: BudgetLine; none?: string }) {
  const capped = line.limit_usd != null;
  const pct = capped && line.limit_usd! > 0 ? Math.min(100, (line.spent_usd / line.limit_usd!) * 100) : capped ? 100 : 0;
  const tone = !capped ? "neutral" : pct >= 100 ? "danger" : pct >= 80 ? "warning" : "success";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span><b>{label}</b>{hint && <span className="text-text-3"> · {hint}</span>}</span>
        <span className="tabular-nums">{money(line.spent_usd)}{capped ? <> of {money(line.limit_usd!)}</> : null}</span>
      </div>
      {capped ? (
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2" role="meter" aria-label={`${label} spend`}
          aria-valuemin={0} aria-valuemax={line.limit_usd!} aria-valuenow={line.spent_usd}>
          <div className={tone === "danger" ? "h-full bg-danger" : tone === "warning" ? "h-full bg-warning" : "h-full bg-success"} style={{ width: `${pct}%` }} />
        </div>
      ) : (
        <p className="mt-0.5 text-xs text-text-3">{none}</p>
      )}
      {capped && pct >= 100 && <Badge tone="danger" className="mt-1.5">{line.limit_usd === 0 ? "Off" : "Used up this month"}</Badge>}
    </div>
  );
}

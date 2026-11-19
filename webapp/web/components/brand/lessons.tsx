"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GraduationCap, Plus, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, Dialog, Empty, Field, Input, Select, Skeleton, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import type { CheckDef, Lesson } from "@/lib/types";

const CATS = ["music", "sound", "audio", "captions", "text", "pacing", "cuts", "color", "framing", "assets", "brand", "delivery", "other"];

function checkSummary(check: Record<string, unknown>): string {
  return Object.entries(check).map(([k, v]) => `${k.replace(/_/g, " ")} ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ");
}

export function LessonsTab({ brandId, brandName, canEdit }: { brandId: string; brandName: string; canEdit: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const lessons = useQuery({ queryKey: ["brand", brandId, "lessons"], queryFn: () => api.get<Lesson[]>(`/brands/${brandId}/lessons`) });
  const [open, setOpen] = useState(false);
  const [retire, setRetire] = useState<Lesson | null>(null);
  const [why, setWhy] = useState("");
  const doRetire = useMutation({
    mutationFn: () => api.patch(`/lessons/${retire!.id}`, { status: "retired", retired_why: why }),
    onSuccess: () => { toast("Lesson retired", "success"); setRetire(null); setWhy(""); qc.invalidateQueries({ queryKey: ["brand", brandId] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  if (!lessons.data) return <Skeleton className="h-80" />;
  const brandL = lessons.data.filter((l) => l.brand_id), house = lessons.data.filter((l) => !l.brand_id);
  const row = (l: Lesson) => (
    <div key={l.id} className="flex flex-wrap items-start gap-3 px-4 py-3.5">
      <span className="mt-0.5 rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-xs font-semibold text-text-2">{l.brand_id ? "" : "H·"}L{l.number}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{l.rule}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <Badge>{l.category}</Badge>
          {l.must && <Badge tone="danger"><ShieldAlert className="size-3" />Must</Badge>}
          {Object.keys(l.check).length > 0 && <Badge tone="accent" className="max-w-full truncate">checked: {checkSummary(l.check)}</Badge>}
          {l.when.length > 0 && <Badge>only {l.when.join(", ")}</Badge>}
          {l.repeats > 0 && <Badge tone="warning">came back {l.repeats}×</Badge>}
          {l.caught > 0 && <Badge tone="success">caught before delivery {l.caught}×</Badge>}
          <span className="text-xs text-text-3">{l.source === "told" ? "client said so" : "learned from feedback"} · {ago(l.created_at)}</span>
        </div>
      </div>
      {canEdit && l.brand_id && <Button size="sm" variant="ghost" onClick={() => setRetire(l)}>Retire</Button>}
    </div>
  );
  return (
    <div className="space-y-6">
      <Card className="flex flex-wrap items-center gap-4 p-4">
        <span className="flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent"><GraduationCap className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">What {brandName}&apos;s feedback has taught us</p>
          <p className="text-[13px] text-text-2">Every cut follows these. Rules with a check run in QA on every render: a broken MUST fails it before the client sees it.</p>
        </div>
        {canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>Add lesson</Button>}
      </Card>
      {brandL.length ? <Card className="divide-y divide-border">{brandL.map(row)}</Card>
        : <Empty icon={<GraduationCap className="size-5" />} title="No lessons yet" body="Add the client's rules now (logo, banned clips, music level, captions), and turn review notes into lessons as they come in." />}
      {house.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">House rules (every brand)</h3>
          <Card className="divide-y divide-border">{house.map(row)}</Card>
        </section>
      )}
      <LessonDialog brandId={brandId} open={open} onClose={() => setOpen(false)} />
      <Dialog open={!!retire} onClose={() => setRetire(null)} title={`Retire L${retire?.number}`} description="Retired lessons stop applying; the history stays."
        footer={<><Button variant="ghost" onClick={() => setRetire(null)}>Cancel</Button><Button variant="danger" disabled={!why.trim()} loading={doRetire.isPending} onClick={() => doRetire.mutate()}>Retire</Button></>}>
        <p className="text-sm">{retire?.rule}</p>
        <Field label="Why"><Input autoFocus value={why} onChange={(e) => setWhy(e.target.value)} placeholder="e.g. new brand guidelines from March" /></Field>
      </Dialog>
    </div>
  );
}

export function LessonDialog({ brandId, open, onClose, fromNote }: {
  brandId: string; open: boolean; onClose: () => void; fromNote?: { id: string; body: string };
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const checks = useQuery({ queryKey: ["lesson-checks"], queryFn: () => api.get<CheckDef[]>("/lessons/checks"), staleTime: 3600_000 });
  const [rule, setRule] = useState("");
  const [category, setCategory] = useState("");
  const [must, setMust] = useState(false);
  const [told, setTold] = useState(false);
  const [checkKey, setCheckKey] = useState("");
  const [checkVal, setCheckVal] = useState("");
  const [when, setWhen] = useState("");
  useEffect(() => {
    if (open) { setRule(fromNote ? "" : ""); setCategory(""); setMust(false); setTold(false); setCheckKey(""); setCheckVal(""); setWhen(""); }
  }, [open, fromNote]);
  const def = checks.data?.find((c) => c.key === checkKey);
  const add = useMutation({
    mutationFn: () => api.post<Lesson>(`/brands/${brandId}/lessons`, {
      rule, category: category || null, must, source: told ? "told" : "inferred",
      check: checkKey && checkVal ? { [checkKey]: checkVal } : {}, when: when.split(",").map((w) => w.trim()).filter(Boolean),
      from_note_id: fromNote?.id ?? null,
    }),
    onSuccess: (l) => { toast(`L${l.number} saved: every future cut follows it`, "success"); qc.invalidateQueries({ queryKey: ["brand", brandId] }); qc.invalidateQueries({ queryKey: ["project"] }); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Dialog open={open} onClose={onClose} title={fromNote ? "Turn this note into a lesson" : "Add a lesson"} width={560}
      description={fromNote ? <>From the note: “{fromNote.body}”. Write the general rule, with the number you fixed it to, not the note&apos;s words.</> : "One concrete rule for every future video of this client."}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={add.isPending} disabled={rule.trim().length < 4} onClick={() => add.mutate()}>Save lesson</Button></>}>
      <Field label="Rule"><Textarea autoFocus value={rule} onChange={(e) => setRule(e.target.value)} placeholder="e.g. Keep the music bed at -22 dB or lower under speech" className="min-h-16" /></Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Topic"><Select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Detect from the rule</option>{CATS.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select></Field>
        <Field label="Only for" hint="Optional: reels, youtube, ad…"><Input value={when} onChange={(e) => setWhen(e.target.value)} placeholder="All formats" /></Field>
      </div>
      <Field group label="Automatic check" hint={def ? def.description : "Optional. Measurable rules are checked in QA on every render."}>
        <div className="grid grid-cols-[1fr_140px] gap-2">
          <Select value={checkKey} onChange={(e) => setCheckKey(e.target.value)}>
            <option value="">No automatic check</option>
            {checks.data?.map((c) => <option key={c.key} value={c.key}>{c.key.replace(/_/g, " ")}</option>)}
          </Select>
          <Input disabled={!checkKey} value={checkVal} onChange={(e) => setCheckVal(e.target.value)} placeholder={def?.list ? "a, b, c" : "value"} />
        </div>
      </Field>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" className="accent-[var(--accent)]" checked={must} onChange={(e) => setMust(e.target.checked)} />
          Must: breaking it fails QA</label>
        <label className="flex items-center gap-2"><input type="checkbox" className="accent-[var(--accent)]" checked={told} onChange={(e) => setTold(e.target.checked)} />
          The client said “always/never”</label>
      </div>
    </Dialog>
  );
}

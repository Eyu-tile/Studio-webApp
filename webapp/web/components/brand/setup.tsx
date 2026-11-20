"use client";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check } from "lucide-react";
import clsx from "clsx";
import { Button, Card, Progress, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { Setup } from "@/lib/types";

const GO: Record<string, string> = {
  profile: "settings", team: "members", products: "products", library: "library", review: "library", connections: "connections",
  lessons: "lessons", project: "projects",
};
const CTA: Record<string, string> = {
  profile: "Add description", team: "Add people", products: "Add products", library: "Add footage", review: "Review clips",
  connections: "Connect tools", lessons: "Add rules", project: "New project",
};

export function SetupTab({ brandId, onGo }: { brandId: string; onGo: (tab: string) => void }) {
  const q = useQuery({ queryKey: ["brand", brandId, "setup"], queryFn: () => api.get<Setup>(`/brands/${brandId}/setup`) });
  if (!q.data) return <Skeleton className="h-96" />;
  const s = q.data;
  const next = s.steps.find((x) => !x.done);
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px]">
      <Card className="divide-y divide-border">
        {s.steps.map((step, i) => (
          <div key={step.key} className={clsx("flex items-center gap-4 px-5 py-4", step === next && "bg-accent-soft/40")}>
            <span className={clsx("flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
              step.done ? "bg-success text-white" : step === next ? "bg-accent text-accent-text" : "bg-surface-2 text-text-3")}>
              {step.done ? <Check className="size-4" /> : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className={clsx("text-sm font-medium", step.done && "text-text-2")}>{step.title}</p>
              <p className="truncate text-[13px] text-text-3">{step.detail}</p>
            </div>
            {!step.done && <Button size="sm" variant={step === next ? "primary" : "secondary"} onClick={() => onGo(GO[step.key])}
              icon={step === next ? <ArrowRight className="size-3.5" /> : undefined}>{CTA[step.key]}</Button>}
          </div>
        ))}
      </Card>
      <Card className="h-fit p-5">
        <p className="text-sm font-semibold">Client setup</p>
        <p className="mt-1 text-[13px] text-text-2">Everything Studio needs to edit for this client the way they like it.</p>
        <p className="mt-5 text-3xl font-semibold tracking-tight tabular">{s.done}<span className="text-lg text-text-3"> / {s.total}</span></p>
        <Progress value={s.done / s.total} tone={s.done === s.total ? "success" : "accent"} className="mt-3" />
        <p className="mt-3 text-[13px] text-text-2">{next ? <>Next: <span className="font-medium text-text">{next.title}</span></> : "All set. New feedback keeps teaching the lessons."}</p>
      </Card>
    </div>
  );
}

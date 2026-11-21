"use client";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, BadgeCheck, Bot, CheckCircle2, CircleSlash, Film, MessageSquare, PencilLine, Sparkles, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { Empty, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { HistoryEvent } from "@/lib/types";

const LOOK: Record<HistoryEvent["kind"], { icon: ReactNode; tone: string; group: Filter }> = {
  created: { icon: <Sparkles className="size-3.5" />, tone: "bg-accent-soft text-accent", group: "all" },
  changed: { icon: <PencilLine className="size-3.5" />, tone: "bg-surface-2 text-text-2", group: "all" },
  version: { icon: <Film className="size-3.5" />, tone: "bg-success-soft text-success", group: "versions" },
  asked: { icon: <Bot className="size-3.5" />, tone: "bg-accent-soft text-accent", group: "claude" },
  made: { icon: <Sparkles className="size-3.5" />, tone: "bg-accent-soft text-accent", group: "claude" },
  failed: { icon: <AlertTriangle className="size-3.5" />, tone: "bg-danger-soft text-danger", group: "claude" },
  approved: { icon: <BadgeCheck className="size-3.5" />, tone: "bg-warning-soft text-warning", group: "claude" },
  declined: { icon: <CircleSlash className="size-3.5" />, tone: "bg-surface-2 text-text-2", group: "claude" },
  note: { icon: <MessageSquare className="size-3.5" />, tone: "bg-warning-soft text-warning", group: "notes" },
  resolved: { icon: <CheckCircle2 className="size-3.5" />, tone: "bg-success-soft text-success", group: "notes" },
  job: { icon: <Wrench className="size-3.5" />, tone: "bg-surface-2 text-text-2", group: "all" },
  job_failed: { icon: <AlertTriangle className="size-3.5" />, tone: "bg-danger-soft text-danger", group: "all" },
};
type Filter = "all" | "versions" | "claude" | "notes";
const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Everything" }, { value: "versions", label: "Versions" }, { value: "claude", label: "Claude" }, { value: "notes", label: "Review notes" },
];

/** Everything that happened to this ad, newest first: what an editor (and Claude) needs to pick it up again later. */
export function History({ projectId, onOpenVersion, onOpenThread }: {
  projectId: string; onOpenVersion: () => void; onOpenThread: (id: string) => void;
}) {
  const q = useQuery({ queryKey: ["project", projectId, "history"], queryFn: () => api.get<HistoryEvent[]>(`/projects/${projectId}/history`) });
  const [filter, setFilter] = useState<Filter>("all");
  const days = useMemo(() => {
    const list = (q.data ?? []).filter((e) => filter === "all" || LOOK[e.kind].group === filter);
    const out: [string, HistoryEvent[]][] = [];
    for (const e of list) {
      const d = new Date(e.at).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
      if (!out.length || out[out.length - 1][0] !== d) out.push([d, []]);
      out[out.length - 1][1].push(e);
    }
    return out;
  }, [q.data, filter]);
  if (!q.data) return <Skeleton className="h-96" />;
  const versions = q.data.filter((e) => e.kind === "version").length;
  const asks = q.data.filter((e) => e.kind === "asked").length;
  return (
    <div className="max-w-3xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-text-2">{versions} version{versions === 1 ? "" : "s"} · {asks} request{asks === 1 ? "" : "s"} to Claude ·
          every new message to Claude starts from this history.</p>
        <div className="flex gap-1 rounded-lg bg-surface-2 p-0.5">
          {FILTERS.map((f) => (
            <button key={f.value} onClick={() => setFilter(f.value)} aria-pressed={filter === f.value}
              className={clsx("rounded-md px-2.5 py-1 text-[13px] font-medium", filter === f.value ? "bg-surface text-text shadow-card" : "text-text-2 hover:text-text")}>{f.label}</button>
          ))}
        </div>
      </div>
      {days.length === 0 ? <Empty icon={<Film className="size-5" />} title="Nothing here yet" body="Versions, Claude requests, approvals and review notes will build up here." /> : (
        <div className="space-y-7">
          {days.map(([day, list]) => (
            <section key={day}>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">{day}</p>
              <ol className="relative space-y-3 border-l border-border pl-6">
                {list.map((e, i) => {
                  const look = LOOK[e.kind];
                  const open = e.ref.thread ? () => onOpenThread(e.ref.thread!) : e.ref.version ? onOpenVersion : undefined;
                  return (
                    <li key={`${e.at}-${i}`} className="relative">
                      <span className={clsx("absolute -left-[35px] top-0.5 flex size-[22px] items-center justify-center rounded-full ring-4 ring-bg", look.tone)}>{look.icon}</span>
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        {open ? <button onClick={open} className="text-left text-sm font-medium hover:underline">{e.title}</button> : <span className="text-sm font-medium">{e.title}</span>}
                        <span className="text-xs text-text-3">{new Date(e.at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}{e.who && ` · ${e.who}`}</span>
                      </div>
                      {e.detail && <p className="mt-0.5 whitespace-pre-wrap text-[13px] text-text-2 line-clamp-4">{e.detail}</p>}
                    </li>
                  );
                })}
              </ol>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

"use client";
import { CheckCircle2, CircleDashed, Clock3, Film, Loader2, MessageSquare, XCircle } from "lucide-react";
import Link from "next/link";
import { ago, JOB_LABEL, KIND_LABEL } from "@/lib/format";
import type { Job, JobStatus, Project } from "@/lib/types";
import { Badge, Progress } from "./ui";

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const map: Record<JobStatus, [React.ComponentProps<typeof Badge>["tone"], string]> = {
    queued: ["neutral", "Queued"], running: ["accent", "Running"], succeeded: ["success", "Done"],
    failed: ["danger", "Failed"], canceled: ["neutral", "Canceled"],
  };
  const [tone, label] = map[status];
  return <Badge tone={tone} dot>{label}</Badge>;
}

export function JobIcon({ status }: { status: JobStatus }) {
  if (status === "running") return <Loader2 className="size-4 animate-spin text-accent" />;
  if (status === "succeeded") return <CheckCircle2 className="size-4 text-success" />;
  if (status === "failed") return <XCircle className="size-4 text-danger" />;
  if (status === "queued") return <Clock3 className="size-4 text-text-3" />;
  return <CircleDashed className="size-4 text-text-3" />;
}

export function JobLine({ job, project }: { job: Job; project?: string }) {
  return (
    <div className="flex items-center gap-3 py-3">
      <JobIcon status={job.status} />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 whitespace-nowrap text-sm font-medium">{JOB_LABEL[job.kind] ?? job.kind}</span>
          {project && <span className="truncate text-sm text-text-3">· {project}</span>}
        </div>
        <p className="truncate text-[13px] text-text-2">{job.message}</p>
        {job.status === "running" && <Progress value={job.progress} className="mt-2" />}
      </div>
      <span className="shrink-0 text-xs text-text-3">{ago(job.created_at)}</span>
    </div>
  );
}

const STATUS_TONE: Record<string, React.ComponentProps<typeof Badge>["tone"]> = {
  active: "accent", in_review: "warning", delivered: "success", archived: "neutral",
};
export const STATUS_LABEL: Record<string, string> = { active: "In progress", in_review: "In review", delivered: "Delivered", archived: "Archived" };

export function ProjectCard({ p, brandName, brandColor }: { p: Project; brandName?: string; brandColor?: string }) {
  return (
    <Link href={`/projects/${p.id}`} className="group block overflow-hidden rounded-xl border border-border bg-surface shadow-card transition-all hover:border-border-strong hover:shadow-pop">
      <div className="relative aspect-video bg-surface-2">
        {p.poster_url
          ? <img src={p.poster_url} alt="" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]" />
          : <div className="flex h-full items-center justify-center text-text-3"><Film className="size-7" /></div>}
        <div className="absolute left-2.5 top-2.5"><Badge tone={STATUS_TONE[p.status] ?? "neutral"} className="backdrop-blur">{STATUS_LABEL[p.status] ?? p.status}</Badge></div>
      </div>
      <div className="p-3.5">
        <p className="truncate font-medium">{p.name}</p>
        <div className="mt-1 flex items-center gap-2 text-[13px] text-text-2">
          {brandName && <><span className="size-2 rounded-[3px]" style={{ background: brandColor }} /><span className="truncate">{brandName}</span><span className="text-text-3">·</span></>}
          <span>{KIND_LABEL[p.kind] ?? p.kind}</span>
        </div>
        <div className="mt-3 flex items-center gap-3 text-xs text-text-3">
          <span className="tabular">{p.version_count} version{p.version_count === 1 ? "" : "s"}</span>
          {p.open_notes > 0 && <span className="flex items-center gap-1 text-warning"><MessageSquare className="size-3" />{p.open_notes} open</span>}
          <span className="ml-auto">{ago(p.updated_at)}</span>
        </div>
      </div>
    </Link>
  );
}

export function Stat({ label, value, icon }: { label: string; value: number | string; icon: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between text-[13px] text-text-2">{label}<span className="text-text-3">{icon}</span></div>
      <p className="mt-2 text-2xl font-semibold tracking-tight tabular">{value}</p>
    </div>
  );
}

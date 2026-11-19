"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Ban, CheckCircle2, CircleDashed, FileVideo, Image as ImageIcon, Link2, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, Dialog, Empty, Field, Input, Progress, Skeleton, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { bytes, duration, PROVIDER_LABEL } from "@/lib/format";
import { useBrandEvents } from "@/lib/hooks";
import type { Clip, LibrarySource, LibrarySummary, Review } from "@/lib/types";

const REVIEW: Record<Review, { label: string; tone: "neutral" | "success" | "warning" | "danger"; icon: React.ReactNode }> = {
  unreviewed: { label: "To review", tone: "neutral", icon: <CircleDashed className="size-3" /> },
  ok: { label: "Usable", tone: "success", icon: <CheckCircle2 className="size-3" /> },
  caution: { label: "Caution", tone: "warning", icon: <AlertTriangle className="size-3" /> },
  banned: { label: "Banned", tone: "danger", icon: <Ban className="size-3" /> },
};

export function LibraryTab({ brandId, canEdit, isLead }: { brandId: string; canEdit: boolean; isLead: boolean }) {
  useBrandEvents(brandId);
  const qc = useQueryClient();
  const toast = useToast();
  const [filter, setFilter] = useState<Review | "">("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [open, setOpen] = useState<Clip | null>(null);
  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t); }, [q]);

  const summary = useQuery({
    queryKey: ["brand", brandId, "library", "summary"], queryFn: () => api.get<LibrarySummary>(`/brands/${brandId}/library/summary`),
    refetchInterval: (x) => (x.state.data?.last_job && ["queued", "running"].includes(x.state.data.last_job.status) ? 3000 : false),
  });
  const running = !!summary.data?.last_job && ["queued", "running"].includes(summary.data.last_job.status);
  const sources = useQuery({ queryKey: ["brand", brandId, "library", "sources"], queryFn: () => api.get<LibrarySource[]>(`/brands/${brandId}/library/sources`),
    refetchInterval: running ? 4000 : false });
  const clips = useQuery({
    queryKey: ["brand", brandId, "library", "clips", filter, query],
    queryFn: () => api.get<{ total: number; clips: Clip[] }>(`/brands/${brandId}/library/clips?limit=120&review=${filter}&q=${encodeURIComponent(query)}`),
    refetchInterval: running ? 5000 : false,
  });
  const scan = useMutation({
    mutationFn: () => api.post(`/brands/${brandId}/library/scan`, { limit: 300 }),
    onSuccess: () => { toast("Learning the library: frames are read over the network, nothing is downloaded in full", "success"); qc.invalidateQueries({ queryKey: ["brand", brandId, "library"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const removeSource = useMutation({
    mutationFn: (id: string) => api.del(`/brands/${brandId}/library/sources/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brand", brandId, "library"] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });

  const s = summary.data;
  const job = s?.last_job;
  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <p className="text-sm font-semibold">Where the client keeps footage</p>
            <p className="text-[13px] text-text-2">Google Drive, Frame.io, Dropbox, OneDrive share links, or any page with videos.</p>
          </div>
          <div className="flex gap-2">
            {canEdit && <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => setAddOpen(true)}>Add link</Button>}
            {canEdit && <Button size="sm" variant="primary" icon={<RefreshCw className={clsx("size-3.5", running && "animate-spin")} />} loading={scan.isPending}
              disabled={running || !sources.data?.length} onClick={() => scan.mutate()}>{running ? "Learning…" : "Learn library"}</Button>}
          </div>
        </div>
        {job && running && (
          <div className="border-b border-border px-4 py-3">
            <div className="mb-2 flex justify-between text-[13px]"><span className="text-text-2">{job.message}</span><span className="tabular text-text-3">{Math.round(job.progress * 100)}%</span></div>
            <Progress value={job.progress} />
          </div>
        )}
        {job && job.status === "failed" && <p className="border-b border-border bg-danger-soft px-4 py-2.5 text-[13px] text-danger">Last learning run failed: {job.message}</p>}
        {sources.data?.length ? (
          <div className="divide-y divide-border">
            {sources.data.map((src) => (
              <div key={src.id} className="flex items-center gap-3 px-4 py-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-text-2"><Link2 className="size-4" /></span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{src.name} <span className="font-normal text-text-3">· {PROVIDER_LABEL[src.provider] ?? src.provider}</span></p>
                  <p className="truncate text-[13px] text-text-3">{src.url}</p>
                </div>
                <Badge tone={src.status === "ready" ? "success" : src.status === "error" ? "danger" : src.status === "scanning" ? "accent" : "neutral"}>
                  {src.status === "ready" ? `${src.file_count} files` : src.status === "error" ? "Error" : src.status === "scanning" ? "Learning" : "Not learned yet"}
                </Badge>
                {src.status === "error" && <span className="hidden max-w-60 truncate text-xs text-danger md:inline" title={src.message}>{src.message}</span>}
                {isLead && <button className="rounded-md p-1.5 text-text-3 hover:bg-danger-soft hover:text-danger" aria-label="Remove link"
                  onClick={() => confirm(`Remove ${src.name}? Clips already learned stay in the library.`) && removeSource.mutate(src.id)}><Trash2 className="size-4" /></button>}
              </div>
            ))}
          </div>
        ) : <p className="px-4 py-6 text-center text-sm text-text-3">No links yet. Add the folder or page the client shared.</p>}
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        {(["", "unreviewed", "ok", "caution", "banned"] as const).map((r) => (
          <button key={r || "all"} onClick={() => setFilter(r)}
            className={clsx("rounded-lg border px-2.5 py-1 text-[13px] font-medium transition-colors",
              filter === r ? "border-accent bg-accent-soft text-accent" : "border-border bg-surface text-text-2 hover:text-text")}>
            {r ? REVIEW[r].label : "All"} <span className="tabular text-text-3">{r ? s?.by_review[r] ?? 0 : s?.total ?? 0}</span>
          </button>
        ))}
        <div className="relative ml-auto w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-3" />
          <Input className="w-full pl-9" placeholder="Search names, folders, notes…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      {!clips.data ? <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">{Array.from({ length: 12 }, (_, i) => <Skeleton key={i} className="aspect-video" />)}</div>
        : clips.data.clips.length === 0 ? <Empty icon={<FileVideo className="size-5" />} title={s?.total ? "Nothing matches" : "The library is empty"}
            body={s?.total ? "Try another filter or search." : "Add the client's links, then press Learn library: every clip gets a thumbnail and a frame strip to review."} />
        : <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            {clips.data.clips.map((c) => (
              <button key={c.id} onClick={() => setOpen(c)} className="group overflow-hidden rounded-xl border border-border bg-surface text-left shadow-card transition hover:border-border-strong">
                <div className="relative aspect-video bg-surface-2">
                  {c.thumb_url ? <img src={c.thumb_url} alt="" loading="lazy" className="h-full w-full object-cover" />
                    : <div className="flex h-full items-center justify-center text-text-3">{c.kind === "image" ? <ImageIcon className="size-5" /> : <FileVideo className="size-5" />}</div>}
                  {c.duration ? <span className="absolute bottom-1.5 right-1.5 rounded bg-black/70 px-1 text-[11px] font-medium text-white tabular">{duration(c.duration)}</span> : null}
                  <span className="absolute left-1.5 top-1.5"><Badge tone={REVIEW[c.review].tone} className="backdrop-blur">{REVIEW[c.review].icon}{REVIEW[c.review].label}</Badge></span>
                </div>
                <div className="p-2.5">
                  <p className="truncate text-[13px] font-medium" title={c.name}>{c.name}</p>
                  <p className="truncate text-xs text-text-3">{c.folder || "—"}{c.sample_error ? " · unreadable" : ""}</p>
                </div>
              </button>
            ))}
          </div>}
      {clips.data && clips.data.total > clips.data.clips.length && <p className="text-center text-[13px] text-text-3">Showing {clips.data.clips.length} of {clips.data.total}: search or filter to narrow down.</p>}

      <AddSource brandId={brandId} open={addOpen} onClose={() => setAddOpen(false)} />
      <ClipDialog clip={open} onClose={() => setOpen(null)} canEdit={canEdit} brandId={brandId} />
    </div>
  );
}

function AddSource({ brandId, open, onClose }: { brandId: string; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  useEffect(() => { if (open) { setUrl(""); setName(""); } }, [open]);
  const add = useMutation({
    mutationFn: () => api.post(`/brands/${brandId}/library/sources`, { url, name }),
    onSuccess: () => { toast("Link added: press Learn library to read it", "success"); qc.invalidateQueries({ queryKey: ["brand", brandId] }); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Dialog open={open} onClose={onClose} title="Add the client's footage" description="A share link to a folder or page. Public links work as they are; connecting Google Drive or Dropbox makes big folders faster."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={add.isPending} disabled={!url.startsWith("http")} onClick={() => add.mutate()}>Add link</Button></>}>
      <Field label="Link"><Input autoFocus value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://drive.google.com/drive/folders/…" /></Field>
      <Field label="Name" hint="Optional, e.g. “2025 UGC shoots”"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
    </Dialog>
  );
}

function ClipDialog({ clip, onClose, canEdit, brandId }: { clip: Clip | null; onClose: () => void; canEdit: boolean; brandId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [info, setInfo] = useState<Record<string, string>>({});
  const [review, setReview] = useState<Review>("unreviewed");
  useEffect(() => { if (clip) { setInfo(clip.info ?? {}); setReview(clip.review); } }, [clip]);
  const save = useMutation({
    mutationFn: () => api.patch(`/library/clips/${clip!.id}`, { review, info }),
    onSuccess: () => { toast("Saved", "success"); qc.invalidateQueries({ queryKey: ["brand", brandId] }); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  if (!clip) return <Dialog open={false} onClose={onClose} title="">{null}</Dialog>;
  return (
    <Dialog open={!!clip} onClose={onClose} title={clip.name} width={760}
      description={[clip.folder, clip.width && `${clip.width}×${clip.height}`, clip.duration && duration(clip.duration), clip.size && bytes(clip.size)].filter(Boolean).join(" · ")}
      footer={canEdit ? <><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save</Button></> : undefined}>
      {clip.strip_url ? <img src={clip.strip_url} alt="Frames across the clip" className="w-full rounded-lg border border-border bg-black" />
        : clip.thumb_url ? <img src={clip.thumb_url} alt="" className="w-full rounded-lg border border-border" />
        : <p className="text-sm text-text-3">{clip.sample_error || "No frames yet: learn the library to read them."}</p>}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(REVIEW) as Review[]).map((r) => (
          <button key={r} disabled={!canEdit} onClick={() => setReview(r)}
            className={clsx("flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[13px] font-medium transition-colors",
              review === r ? (r === "banned" ? "border-danger bg-danger-soft text-danger" : r === "caution" ? "border-warning bg-warning-soft text-warning"
                : r === "ok" ? "border-success bg-success-soft text-success" : "border-border-strong bg-surface-2 text-text")
                : "border-border text-text-2 hover:text-text")}>{REVIEW[r].icon}{REVIEW[r].label}</button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Who's in it"><Input disabled={!canEdit} value={info.people ?? ""} onChange={(e) => setInfo({ ...info, people: e.target.value })} placeholder="e.g. woman, 30s, kitchen" /></Field>
        <Field label="Product"><Input disabled={!canEdit} value={info.product ?? ""} onChange={(e) => setInfo({ ...info, product: e.target.value })} /></Field>
        <Field label="Best part"><Input disabled={!canEdit} value={info.best ?? ""} onChange={(e) => setInfo({ ...info, best: e.target.value })} placeholder="e.g. 2–6 s, the pour" /></Field>
        <Field label="Tags"><Input disabled={!canEdit} value={info.tags ?? ""} onChange={(e) => setInfo({ ...info, tags: e.target.value })} placeholder="ugc, hook, b-roll" /></Field>
      </div>
      <Field label="Notes" hint={review === "banned" ? "Say why it's banned: editors see this before using anything similar." : undefined}>
        <Textarea disabled={!canEdit} value={info.notes ?? ""} onChange={(e) => setInfo({ ...info, notes: e.target.value })} />
      </Field>
      {clip.used_in?.length > 0 && <p className="text-[13px] text-text-2">Used in: {clip.used_in.join(", ")}</p>}
      <p className="text-xs text-text-3">Learned {clip.sampled ? "with frames" : "from the listing only"}{clip.duplicate_of ? " · duplicate of another file" : ""}</p>
    </Dialog>
  );
}

"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Check, ChevronRight, Clapperboard, Download, FileAudio, FileVideo, Film, GraduationCap, ImageIcon, Languages,
  MessageSquarePlus, RotateCcw, Scissors, Trash2, UploadCloud, X } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { JobIcon, JobStatusBadge, STATUS_LABEL } from "@/components/bits";
import { LessonDialog } from "@/components/brand/lessons";
import { ClaudeTab } from "@/components/claude/panel";
import { useWorkspace } from "@/components/workspace/context";
import { Avatar, Badge, Button, Card, Dialog, Empty, Field, PageHeader, Progress, Select, Skeleton, Spinner, Tabs, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, bytes, duration, JOB_LABEL, KIND_LABEL, timecode } from "@/lib/format";
import { useMe, useProjectEvents } from "@/lib/hooks";
import { uploadFile } from "@/lib/upload";
import type { Asset, Brand, Job, Note, Project, Version } from "@/lib/types";

type Tab = "claude" | "media" | "review" | "activity";

function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "claude");
  useEffect(() => { const t = params.get("tab") as Tab | null; if (t) setTab(t); }, [params]);     // sidebar and tasks links
  const [cutOpen, setCutOpen] = useState(false);
  useProjectEvents(projectId);
  const me = useMe().data!;
  const project = useQuery({ queryKey: ["project", projectId, "summary"], queryFn: () => api.get<Project>(`/projects/${projectId}`) });
  // Live updates come over SSE; while anything is still working, also re-check every few seconds as a safety net
  // (a proxy that buffers the stream must never leave the page stuck on "Processing").
  const jobs = useQuery({ queryKey: ["project", projectId, "jobs"], queryFn: () => api.get<Job[]>(`/projects/${projectId}/jobs`),
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === "queued" || j.status === "running") ? 3000 : false) });
  const busy = jobs.data?.some((j) => j.status === "queued" || j.status === "running") ?? false;
  const assets = useQuery({ queryKey: ["project", projectId, "assets"], queryFn: () => api.get<Asset[]>(`/projects/${projectId}/assets`),
    refetchInterval: (q) => (busy || q.state.data?.some((a) => a.status === "processing") ? 3000 : false) });
  const versions = useQuery({ queryKey: ["project", projectId, "versions"], queryFn: () => api.get<Version[]>(`/projects/${projectId}/versions`),
    refetchInterval: busy ? 5000 : false });

  // the project's brand is the one in focus (sidebar chats, gallery, spend)
  const { brandId: focus, setBrandId } = useWorkspace();
  const pb = project.data?.brand_id;
  useEffect(() => { if (pb && pb !== focus) setBrandId(pb); }, [pb, focus, setBrandId]);
  if (project.error) return <Empty icon={<Film className="size-5" />} title="Project not found" body="It may have been removed, or you don't have access." />;
  if (!project.data) return <Skeleton className="h-40" />;
  const p = project.data;
  const brand: Brand | undefined = me.brands.find((b) => b.id === p.brand_id);
  const canEdit = brand?.role === "lead" || brand?.role === "editor";
  const running = jobs.data?.filter((j) => j.status === "running" || j.status === "queued").length ?? 0;

  return (
    <>
      <PageHeader
        breadcrumb={brand && <>
          <Link href={`/brands/${brand.id}`} className="flex items-center gap-1.5 hover:text-text"><span className="size-2 rounded-[3px]" style={{ background: brand.color }} />{brand.name}</Link>
          <ChevronRight className="size-3.5" /><span>{KIND_LABEL[p.kind] ?? p.kind}</span></>}
        title={p.name}
        subtitle={<span className="flex items-center gap-2"><Badge tone="accent">{STATUS_LABEL[p.status] ?? p.status}</Badge>{p.brief || "No brief yet"}</span>}
        actions={canEdit && <Button variant="primary" icon={<Scissors className="size-4" />} onClick={() => setCutOpen(true)}
          disabled={!assets.data?.some((a) => a.status === "ready")}>Make a cut</Button>} />
      <Tabs value={tab} onChange={setTab} items={[
        { value: "claude", label: "Claude" },
        { value: "media", label: "Media", count: assets.data?.length },
        { value: "review", label: "Review", count: versions.data?.length },
        { value: "activity", label: running ? `Activity · ${running} running` : "Activity" },
      ]} />
      {tab === "claude" && <ClaudeTab projectId={projectId} canEdit={canEdit} isLead={brand?.role === "lead"}
        openNotes={p.open_notes} onOpenReview={() => setTab("review")} thread={params.get("thread")} />}
      {tab === "media" && <Media projectId={projectId} assets={assets.data} canEdit={canEdit} onCut={() => setCutOpen(true)} />}
      {tab === "review" && <Review projectId={projectId} brandId={p.brand_id} versions={versions.data} canEdit={canEdit} />}
      {tab === "activity" && <ActivityList jobs={jobs.data} canEdit={canEdit} />}
      <CutDialog open={cutOpen} onClose={() => setCutOpen(false)} projectId={projectId} assets={assets.data ?? []} kind={p.kind}
        onStarted={() => { setCutOpen(false); setTab("activity"); }} />
    </>
  );
}

/* ---------------- media ---------------- */

interface Uploading { id: string; name: string; size: number; progress: number; error?: string; ctrl: AbortController }

function Media({ projectId, assets, canEdit, onCut }: { projectId: string; assets?: Asset[]; canEdit: boolean; onCut: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [ups, setUps] = useState<Uploading[]>([]);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const start = useCallback((files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      const u: Uploading = { id: crypto.randomUUID(), name: f.name, size: f.size, progress: 0, ctrl: new AbortController() };
      setUps((x) => [...x, u]);
      uploadFile(projectId, f, (pr) => setUps((x) => x.map((y) => (y.id === u.id ? { ...y, progress: pr } : y))), u.ctrl.signal)
        .then(() => {
          setUps((x) => x.filter((y) => y.id !== u.id));
          qc.invalidateQueries({ queryKey: ["project", projectId] });
          toast(`${f.name} uploaded · processing`, "success");
        })
        .catch((e: Error) => {
          if (e.name === "AbortError") setUps((x) => x.filter((y) => y.id !== u.id));
          else setUps((x) => x.map((y) => (y.id === u.id ? { ...y, error: e.message } : y)));
        });
    }
  }, [projectId, qc, toast]);

  return (
    <div className="space-y-6">
      {canEdit && (
        <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); start(e.dataTransfer.files); }}
          onClick={() => input.current?.click()} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
          className={clsx("flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-6 py-9 text-center transition-colors",
            drag ? "border-accent bg-accent-soft" : "border-border-strong bg-surface hover:border-accent/60 hover:bg-surface-2")}>
          <div className="mb-3 flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent"><UploadCloud className="size-5" /></div>
          <p className="font-medium">Drop footage here, or click to choose</p>
          <p className="mt-1 text-[13px] text-text-2">Video, audio and images of any size. Files go straight to secure storage.</p>
          <input ref={input} type="file" multiple accept="video/*,audio/*,image/*" className="hidden" onChange={(e) => { if (e.target.files) start(e.target.files); e.target.value = ""; }} />
        </div>
      )}
      {ups.length > 0 && (
        <Card className="divide-y divide-border">
          {ups.map((u) => (
            <div key={u.id} className="flex items-center gap-3 px-4 py-3">
              <FileVideo className="size-4 shrink-0 text-text-3" />
              <div className="min-w-0 flex-1">
                <div className="flex justify-between gap-3 text-sm"><span className="truncate font-medium">{u.name}</span>
                  <span className="shrink-0 text-text-2 tabular">{u.error ? "" : `${Math.round(u.progress * 100)}% of ${bytes(u.size)}`}</span></div>
                {u.error ? <p className="mt-1 text-[13px] text-danger">{u.error}</p> : <Progress value={u.progress} className="mt-2" />}
              </div>
              <button onClick={() => (u.error ? setUps((x) => x.filter((y) => y.id !== u.id)) : u.ctrl.abort())} className="rounded-md p-1 text-text-3 hover:bg-surface-2 hover:text-text" aria-label="Cancel upload"><X className="size-4" /></button>
            </div>
          ))}
        </Card>
      )}
      {!assets ? <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-56" />)}</div>
        : assets.length === 0 ? (!canEdit && <Empty icon={<Film className="size-5" />} title="No footage yet" body="Editors upload source files here." />)
        : <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{assets.map((a) => <AssetCard key={a.id} a={a} canEdit={canEdit} onCut={onCut} projectId={projectId} />)}</div>}
    </div>
  );
}

function AssetCard({ a, canEdit, onCut, projectId }: { a: Asset; canEdit: boolean; onCut: () => void; projectId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [preview, setPreview] = useState(false);
  const transcribe = useMutation({
    mutationFn: () => api.post<Job>(`/projects/${projectId}/jobs`, { kind: "transcribe", payload: { asset_id: a.id } }),
    onSuccess: () => { toast("Transcription started", "success"); qc.invalidateQueries({ queryKey: ["project", projectId, "jobs"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const del = useMutation({
    mutationFn: () => api.del(`/assets/${a.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", projectId] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const Icon = a.mime.startsWith("audio") ? FileAudio : a.mime.startsWith("image") ? ImageIcon : FileVideo;
  const pr = a.probe;
  return (
    <Card className="overflow-hidden">
      <button className="relative block aspect-video w-full bg-surface-2" onClick={() => a.proxy_url && setPreview(true)} disabled={!a.proxy_url}>
        {a.poster_url ? <img src={a.poster_url} alt="" className="h-full w-full object-cover" />
          : <div className="flex h-full flex-col items-center justify-center gap-2 text-text-3">{a.status === "processing" ? <><Spinner className="size-5" /><span className="text-xs">Processing…</span></> : <Icon className="size-7" />}</div>}
        {pr.duration ? <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-xs font-medium text-white tabular">{duration(pr.duration)}</span> : null}
        {a.status === "failed" && <span className="absolute left-2 top-2"><Badge tone="danger">Unreadable</Badge></span>}
      </button>
      <div className="p-3.5">
        <p className="truncate text-sm font-medium" title={a.filename}>{a.filename}</p>
        <p className="mt-0.5 truncate text-[13px] text-text-2 tabular">
          {[pr.width && `${pr.width}×${pr.height}`, pr.fps && `${pr.fps} fps`, bytes(a.size)].filter(Boolean).join(" · ")}
        </p>
        <div className="mt-3 flex items-center gap-1.5">
          {a.has_transcript ? <Badge tone="success"><Check className="size-3" />Transcript</Badge>
            : canEdit && a.status === "ready" && pr.has_audio && <Button size="sm" icon={<Languages className="size-3.5" />} loading={transcribe.isPending} onClick={() => transcribe.mutate()}>Transcribe</Button>}
          {canEdit && a.status === "ready" && pr.has_audio && <Button size="sm" variant="ghost" icon={<Scissors className="size-3.5" />} onClick={onCut}>Cut</Button>}
          {canEdit && <button className="ml-auto rounded-md p-1.5 text-text-3 hover:bg-danger-soft hover:text-danger" aria-label="Delete file"
            onClick={() => confirm(`Delete ${a.filename}? This removes the file and its previews.`) && del.mutate()}><Trash2 className="size-4" /></button>}
        </div>
      </div>
      <Dialog open={preview} onClose={() => setPreview(false)} title={a.filename} width={880}>
        {a.proxy_url && (a.mime.startsWith("audio") ? <audio src={a.proxy_url} controls className="w-full" /> :
          <video src={a.proxy_url} controls autoPlay className="max-h-[70vh] w-full rounded-lg bg-black" />)}
        {a.filmstrip_url && <img src={a.filmstrip_url} alt="Filmstrip" className="w-full rounded-lg border border-border" />}
      </Dialog>
    </Card>
  );
}

/* ---------------- cut dialog ---------------- */

const PRESET_FOR: Record<string, string> = { reel: "reels", tiktok: "tiktok", short: "shorts", youtube: "youtube", ad: "reels" };

function CutDialog({ open, onClose, projectId, assets, kind, onStarted }: {
  open: boolean; onClose: () => void; projectId: string; assets: Asset[]; kind: string; onStarted: () => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const ready = assets.filter((a) => a.status === "ready" && a.probe.has_audio);
  const [assetId, setAssetId] = useState("");
  const [preset, setPreset] = useState(PRESET_FOR[kind] ?? "youtube");
  const [captions, setCaptions] = useState("bold-pop");
  const [pace, setPace] = useState("0.45");
  useEffect(() => { if (open && !assetId && ready[0]) setAssetId(ready[0].id); }, [open, ready, assetId]);
  const go = useMutation({
    mutationFn: () => api.post<Job>(`/projects/${projectId}/jobs`, { kind: "render", payload: {
      asset_id: assetId, preset, captions: captions || null, max_pause: Number(pace) } }),
    onSuccess: () => { toast("Cut started: you'll see it under Review when it's ready", "success"); qc.invalidateQueries({ queryKey: ["project", projectId, "jobs"] }); onStarted(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Dialog open={open} onClose={onClose} title="Make a cut" description="Transcribes the speech, cuts the pauses and fillers, adds captions, renders for the platform and runs the quality check."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" icon={<Clapperboard className="size-4" />} loading={go.isPending} disabled={!assetId} onClick={() => go.mutate()}>Start cut</Button></>}>
      {ready.length === 0 ? <p className="text-sm text-text-2">Upload a file with speech first; it appears here once it&apos;s processed.</p> : (<>
        <Field label="Source"><Select value={assetId} onChange={(e) => setAssetId(e.target.value)}>
          {ready.map((a) => <option key={a.id} value={a.id}>{a.filename} ({duration(a.probe.duration)})</option>)}
        </Select></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Platform"><Select value={preset} onChange={(e) => setPreset(e.target.value)}>
            <option value="reels">Instagram Reels · 9:16</option><option value="tiktok">TikTok · 9:16</option>
            <option value="shorts">YouTube Shorts · 9:16</option><option value="youtube">YouTube · 16:9</option>
            <option value="square">Square · 1:1</option><option value="linkedin">LinkedIn</option><option value="x">X</option>
          </Select></Field>
          <Field label="Captions"><Select value={captions} onChange={(e) => setCaptions(e.target.value)}>
            <option value="bold-pop">Bold pop</option><option value="clean">Clean</option><option value="karaoke">Karaoke</option>
            <option value="minimal">Minimal</option><option value="">None</option>
          </Select></Field>
        </div>
        <Field label="Pacing" hint="Pauses longer than this are cut."><Select value={pace} onChange={(e) => setPace(e.target.value)}>
          <option value="0.3">Punchy · 0.3 s</option><option value="0.45">Tight · 0.45 s</option><option value="0.6">Natural · 0.6 s</option><option value="0.8">Relaxed · 0.8 s</option>
        </Select></Field>
      </>)}
    </Dialog>
  );
}

/* ---------------- review ---------------- */

function Review({ projectId, brandId, versions, canEdit }: { projectId: string; brandId: string; versions?: Version[]; canEdit: boolean }) {
  const [vid, setVid] = useState<string | null>(null);
  const v = versions?.find((x) => x.id === vid) ?? versions?.[0];
  const video = useRef<HTMLVideoElement>(null);
  const [t, setT] = useState(0);
  if (!versions) return <Skeleton className="h-96" />;
  if (!v) return <Empty icon={<Clapperboard className="size-5" />} title="No versions yet" body="Use “Make a cut” and each render shows up here for review." />;
  const qa = v.qa.results ?? [];
  const fails = qa.filter((r) => r.level === "FAIL"), warns = qa.filter((r) => r.level === "WARN");
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_380px]">
      <div className="min-w-0 space-y-4">
        <Card className="overflow-hidden">
          <div className="flex items-center justify-center bg-black" style={{ maxHeight: "70vh" }}>
            <video ref={video} key={v.id} src={v.url ?? undefined} controls playsInline onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
              className="max-h-[70vh] w-full object-contain" />
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-border px-4 py-3">
            <Select className="!h-8 w-auto max-w-[260px] text-[13px]" value={v.id} onChange={(e) => setVid(e.target.value)}>
              {versions.map((x) => <option key={x.id} value={x.id}>Version {x.number}{x.note ? ` · ${x.note}` : ""}</option>)}
            </Select>
            <span className="text-[13px] text-text-2 tabular">{v.asset.probe.width}×{v.asset.probe.height} · {duration(v.asset.probe.duration)} · {bytes(v.asset.size)}</span>
            <span className="text-[13px] text-text-3">{ago(v.created_at)}</span>
            {v.download_url && <a href={v.download_url} className="ml-auto"><Button size="sm" icon={<Download className="size-3.5" />}>Download</Button></a>}
          </div>
        </Card>
        <Card className="p-4">
          <div className="mb-3 flex items-center gap-2">
            <h3 className="text-sm font-semibold">Quality check</h3>
            {fails.length ? <Badge tone="danger">{fails.length} failing</Badge> : warns.length ? <Badge tone="warning">{warns.length} to look at</Badge> : <Badge tone="success">All passed</Badge>}
          </div>
          <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
            {qa.filter((r) => r.level !== "INFO").map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-[13px]">
                {r.level === "PASS" ? <Check className="mt-0.5 size-3.5 shrink-0 text-success" /> : <AlertTriangle className={clsx("mt-0.5 size-3.5 shrink-0", r.level === "FAIL" ? "text-danger" : "text-warning")} />}
                <span><span className="font-medium capitalize">{r.check.replace(/-/g, " ")}</span> <span className="text-text-2">{r.msg}</span></span>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <Notes projectId={projectId} brandId={brandId} version={v} time={t} seek={(s) => { if (video.current) { video.current.currentTime = s; video.current.play(); } }} canEdit={canEdit} />
    </div>
  );
}

function Notes({ projectId, brandId, version, time, seek, canEdit }: { projectId: string; brandId: string; version: Version; time: number; seek: (s: number) => void; canEdit: boolean }) {
  const [teach, setTeach] = useState<Note | null>(null);
  const qcNotes = useQueryClient();
  const oneOff = useMutation({
    mutationFn: (id: string) => api.patch(`/notes/${id}`, { lesson_link: "none" }),
    onSuccess: () => qcNotes.invalidateQueries({ queryKey: ["project", projectId, "notes"] }),
  });
  const qc = useQueryClient();
  const toast = useToast();
  const [body, setBody] = useState("");
  const [at, setAt] = useState<number | null>(null);
  const notes = useQuery({ queryKey: ["project", projectId, "notes", version.id], queryFn: () => api.get<Note[]>(`/projects/${projectId}/notes?version_id=${version.id}`) });
  const add = useMutation({
    mutationFn: () => api.post<Note>(`/projects/${projectId}/notes`, { body, version_id: version.id, start_s: at }),
    onSuccess: () => { setBody(""); setAt(null); qc.invalidateQueries({ queryKey: ["project", projectId, "notes"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: Note["status"] }) => api.patch(`/notes/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", projectId, "notes"] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const list = notes.data ?? [];
  const open = list.filter((n) => n.status === "open").length;
  return (
    <Card className="flex max-h-[calc(100vh-180px)] flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold">Notes</h3>
        <span className="text-[13px] text-text-2">{open} open · {list.length - open} resolved</span>
      </div>
      <div className="flex-1 divide-y divide-border overflow-y-auto">
        {list.length === 0 && <p className="px-4 py-10 text-center text-sm text-text-3">Pause on a moment and leave a note. Each note keeps its timecode.</p>}
        {list.map((n) => (
          <div key={n.id} className={clsx("px-4 py-3", n.status !== "open" && "opacity-60")}>
            <div className="flex items-center gap-2">
              <Avatar name={n.author?.name ?? ""} email={n.author?.email} size={22} />
              <span className="text-[13px] font-medium">{n.author?.name || n.author?.email}</span>
              {n.start_s != null && <button onClick={() => seek(n.start_s!)} className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs font-medium text-accent tabular hover:underline">{timecode(n.start_s)}</button>}
              <span className="ml-auto text-xs text-text-3">{ago(n.created_at)}</span>
            </div>
            <p className={clsx("mt-1.5 whitespace-pre-wrap text-sm", n.status !== "open" && "line-through")}>{n.body}</p>
            {n.lesson_link === "repeat" && <p className="mt-2 flex items-start gap-1.5 rounded-lg bg-warning-soft px-2.5 py-1.5 text-[13px] text-warning">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /><span><b>Repeat of L{n.lesson_number}</b>: we already learned this ({n.lesson_rule}). Fix it, then tighten that lesson.</span></p>}
            {n.lesson_link === "taught" && <p className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-success-soft px-2 py-0.5 text-xs font-medium text-success"><GraduationCap className="size-3.5" />Became lesson L{n.lesson_number}</p>}
            {canEdit && (
              <div className="mt-2 flex flex-wrap gap-1">
                {!n.lesson_link && <Button size="sm" variant="ghost" icon={<GraduationCap className="size-3.5" />} onClick={() => setTeach(n)}>Make lesson</Button>}
                {!n.lesson_link && <Button size="sm" variant="ghost" onClick={() => oneOff.mutate(n.id)}>One-off</Button>}
                {n.status === "open"
                  ? <Button size="sm" variant="ghost" icon={<Check className="size-3.5" />} onClick={() => update.mutate({ id: n.id, status: "done" })}>Resolve</Button>
                  : <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => update.mutate({ id: n.id, status: "open" })}>Reopen</Button>}
              </div>
            )}
          </div>
        ))}
      </div>
      <LessonDialog brandId={brandId} open={!!teach} onClose={() => setTeach(null)} fromNote={teach ? { id: teach.id, body: teach.body } : undefined} />
      <div className="space-y-2 border-t border-border p-3">
        <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Leave a note…" className="min-h-16"
          onFocus={() => at == null && setAt(Math.round(time * 10) / 10)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && body.trim()) add.mutate(); }} />
        <div className="flex items-center gap-2">
          <button onClick={() => setAt(at == null ? Math.round(time * 10) / 10 : null)}
            className={clsx("rounded-md px-2 py-1 text-xs font-medium tabular", at != null ? "bg-accent-soft text-accent" : "bg-surface-2 text-text-2")}>
            {at != null ? `At ${timecode(at)}` : "General note"}
          </button>
          <Button size="sm" variant="primary" className="ml-auto" icon={<MessageSquarePlus className="size-3.5" />} disabled={!body.trim()} loading={add.isPending} onClick={() => add.mutate()}>Add note</Button>
        </div>
      </div>
    </Card>
  );
}

/* ---------------- activity ---------------- */

function ActivityList({ jobs, canEdit }: { jobs?: Job[]; canEdit: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [openLog, setOpenLog] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: ({ id, op }: { id: string; op: "cancel" | "retry" }) => api.post<Job>(`/jobs/${id}/${op}`),
    onSuccess: (j) => qc.invalidateQueries({ queryKey: ["project", j.project_id, "jobs"] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const sorted = useMemo(() => jobs ?? [], [jobs]);
  if (!jobs) return <Skeleton className="h-64" />;
  if (!sorted.length) return <Empty icon={<Clapperboard className="size-5" />} title="Nothing has run yet" body="Uploads, transcriptions, cuts and quality checks appear here with live progress." />;
  return (
    <Card className="divide-y divide-border">
      {sorted.map((j) => (
        <div key={j.id} className="px-4 py-3.5">
          <div className="flex items-center gap-3">
            <JobIcon status={j.status} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{JOB_LABEL[j.kind] ?? j.kind}</span>
                <JobStatusBadge status={j.status} />
                {j.created_by && <span className="text-[13px] text-text-3">by {j.created_by.name || j.created_by.email}</span>}
              </div>
              <p className="mt-0.5 truncate text-[13px] text-text-2">{j.message}</p>
            </div>
            <span className="hidden text-xs text-text-3 sm:block">{ago(j.created_at)}{j.finished_at && j.started_at ? ` · ${Math.max(1, Math.round((+new Date(j.finished_at) - +new Date(j.started_at)) / 1000))} s` : ""}</span>
            {j.log_tail && <Button size="sm" variant="ghost" onClick={() => setOpenLog(openLog === j.id ? null : j.id)}>{openLog === j.id ? "Hide log" : "Log"}</Button>}
            {canEdit && (j.status === "running" || j.status === "queued") && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: j.id, op: "cancel" })}>Cancel</Button>}
            {canEdit && (j.status === "failed" || j.status === "canceled") && <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={() => act.mutate({ id: j.id, op: "retry" })}>Retry</Button>}
          </div>
          {j.status === "running" && <div className="mt-2.5 pl-7"><Progress value={j.progress} /></div>}
          {openLog === j.id && <pre className="ml-7 mt-3 max-h-72 overflow-auto rounded-lg bg-surface-2 p-3 font-mono text-xs leading-relaxed text-text-2">{j.log_tail}</pre>}
        </div>
      ))}
    </Card>
  );
}

export default function Page() { return <Suspense><ProjectPage /></Suspense>; }

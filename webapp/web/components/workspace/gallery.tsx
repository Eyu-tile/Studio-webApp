"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Ban, Check, Download, FileText, Film, Filter, Image as ImageIcon, MessageSquarePlus, Music, Search, TriangleAlert,
  Upload, X } from "lucide-react";
import Link from "next/link";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, Dialog, Field, Progress, Select, Skeleton, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, bytes, duration } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { uploadFile } from "@/lib/upload";
import type { Clip, ClipPage, MediaItem, Project } from "@/lib/types";
import { brandQuery, useWorkspace } from "./context";

type Tab = "renders" | "footage" | "library" | "outputs";
type Shape = "all" | "vertical" | "horizontal" | "square";
const TABS: { value: Tab; label: string }[] = [
  { value: "renders", label: "Renders" }, { value: "footage", label: "Footage" },
  { value: "library", label: "Library" }, { value: "outputs", label: "Claude files" },
];

/** Something from the gallery handed to the prompt ("use this in a chat"). */
export interface Pick { name: string; project_id?: string; project_name?: string; brand_id?: string; kind: string }

export function Gallery({ onUse }: { onUse: (p: Pick) => void }) {
  const { brandId } = useWorkspace();
  const [tab, setTab] = useState<Tab>("renders");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => { const t = setTimeout(() => setQuery(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  const [shape, setShape] = useState<Shape>("all");
  const [project, setProject] = useState("");
  const [filters, setFilters] = useState(false);
  const [upload, setUpload] = useState(false);
  const [open, setOpen] = useState<MediaItem | null>(null);
  const [clip, setClip] = useState<Clip | null>(null);

  const media = useQuery({
    queryKey: ["workspace", "media", brandId, tab, query],
    queryFn: () => api.get<MediaItem[]>(`/workspace/media?kind=${tab}&limit=120${query ? `&q=${encodeURIComponent(query)}` : ""}${brandQuery(brandId, false)}`),
    enabled: tab !== "library",
    refetchInterval: (s) => (s.state.data?.some((m) => m.status === "processing") ? 4000 : false),
  });
  const library = useQuery({
    queryKey: ["brand", brandId, "library", "gallery", query],
    queryFn: () => api.get<ClipPage>(`/brands/${brandId}/library/clips?limit=120${query ? `&q=${encodeURIComponent(query)}` : ""}`),
    enabled: tab === "library" && !!brandId,
  });
  const projects = useMemo(() => {
    const m = new Map<string, string>();
    media.data?.forEach((x) => m.set(x.project_id, x.project_name));
    return [...m.entries()];
  }, [media.data]);
  useEffect(() => setProject(""), [brandId, tab]);
  const fit = (w?: number | null, h?: number | null) => {
    if (shape === "all" || !w || !h) return shape === "all";
    const r = w / h;
    return shape === "vertical" ? r < 0.9 : shape === "horizontal" ? r > 1.1 : r >= 0.9 && r <= 1.1;
  };
  const items = (media.data ?? []).filter((m) => (!project || m.project_id === project) && fit(m.width, m.height));
  const clips = (library.data?.clips ?? []).filter((c) => fit(c.width, c.height));
  const active = (shape !== "all" ? 1 : 0) + (project ? 1 : 0);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-3 p-4 pb-3">
        <div className="grid grid-cols-4 gap-1 rounded-xl bg-surface-2 p-1" role="tablist" aria-label="Gallery">
          {TABS.map((t) => (
            <button key={t.value} role="tab" aria-selected={tab === t.value} onClick={() => setTab(t.value)}
              className={clsx("h-8 rounded-lg text-[13px] font-medium transition-colors",
                tab === t.value ? "bg-surface text-text shadow-card" : "text-text-2 hover:text-text")}>{t.label}</button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <label className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-surface px-3 focus-within:border-accent focus-within:ring-3 focus-within:ring-[var(--ring)]">
            <Search className="size-4 shrink-0 text-text-3" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tab === "library" ? "Search clips, folders, notes" : "Search files, projects or ID"}
              className="min-w-0 flex-1 bg-transparent text-sm placeholder:text-text-3 focus:outline-none" aria-label="Search the gallery" />
            {q && <button onClick={() => setQ("")} aria-label="Clear search" className="text-text-3 hover:text-text"><X className="size-3.5" /></button>}
          </label>
          <div className="relative">
            <Button icon={<Filter className="size-4" />} onClick={() => setFilters(!filters)} aria-expanded={filters}>
              Filters{active > 0 && <span className="rounded-md bg-accent-soft px-1 text-xs text-accent">{active}</span>}
            </Button>
            {filters && (
              <div className="absolute right-0 top-full z-20 mt-1 w-64 space-y-3 rounded-xl border border-border bg-surface p-3 shadow-pop">
                <Field label="Shape">
                  <Select value={shape} onChange={(e) => setShape(e.target.value as Shape)}>
                    <option value="all">Any</option><option value="vertical">Vertical (9:16, 4:5)</option>
                    <option value="horizontal">Horizontal (16:9)</option><option value="square">Square</option>
                  </Select>
                </Field>
                {tab !== "library" && projects.length > 1 && (
                  <Field label="Project">
                    <Select value={project} onChange={(e) => setProject(e.target.value)}>
                      <option value="">All projects</option>
                      {projects.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                    </Select>
                  </Field>
                )}
                <div className="flex justify-between">
                  <Button size="sm" variant="ghost" onClick={() => { setShape("all"); setProject(""); }}>Reset</Button>
                  <Button size="sm" onClick={() => setFilters(false)}>Done</Button>
                </div>
              </div>
            )}
          </div>
          <Button variant="primary" icon={<Upload className="size-4" />} onClick={() => setUpload(true)}>Upload</Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
        {tab === "library" ? (
          !brandId ? <Hint title="Pick a brand" body="Each client has its own footage library. Choose a brand in the sidebar to browse it." />
            : !library.data ? <Tiles />
            : clips.length === 0 ? <Hint title={query ? "No clips match" : "No library yet"} body={query ? "Try other words." : "Add the client's Drive, Dropbox or Frame.io links on the brand's Library page."} />
            : <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">{clips.map((c) => <ClipTile key={c.id} c={c} onOpen={() => setClip(c)} />)}</div>
        ) : !media.data ? <Tiles />
          : items.length === 0 ? <Hint title={query || active ? "Nothing matches" : EMPTY[tab].title} body={query || active ? "Try other words or reset the filters." : EMPTY[tab].body} />
          : <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">{items.map((m) => <MediaTile key={m.id} m={m} onOpen={() => setOpen(m)} />)}</div>}
      </div>

      <Preview item={open} onClose={() => setOpen(null)} onUse={(p) => { setOpen(null); onUse(p); }} />
      <ClipPreview clip={clip} onClose={() => setClip(null)} onUse={(p) => { setClip(null); onUse(p); }} />
      <UploadDialog open={upload} onClose={() => setUpload(false)} />
    </div>
  );
}

const EMPTY: Record<Exclude<Tab, "library">, { title: string; body: string }> = {
  renders: { title: "No renders yet", body: "Every cut, from Claude or from Make a cut, lands here as a version." },
  footage: { title: "No footage yet", body: "Upload interviews, b-roll and voice notes to a project." },
  outputs: { title: "No files from Claude yet", body: "Subtitles, XML for editors, review pages and exports show up here." },
};

function Hint({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex h-full min-h-48 flex-col items-center justify-center rounded-xl border border-dashed border-border-strong px-6 text-center">
      <p className="text-sm font-medium">{title}</p><p className="mt-1 max-w-xs text-[13px] text-text-2">{body}</p>
    </div>
  );
}

function Tiles() {
  return <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">{Array.from({ length: 9 }, (_, i) => <Skeleton key={i} className="aspect-[3/4]" />)}</div>;
}

function TileFrame({ children, onClick, label }: { children: React.ReactNode; onClick: () => void; label: string }) {
  return (
    <button onClick={onClick} aria-label={label}
      className="group relative block aspect-[3/4] w-full overflow-hidden rounded-xl border border-border bg-surface-2 text-left transition-shadow hover:shadow-pop focus-visible:outline-offset-2">
      {children}
    </button>
  );
}

function Corner({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={clsx("absolute rounded-md bg-black/65 px-1.5 py-0.5 text-[11px] font-medium text-white tabular backdrop-blur-sm", className)}>{children}</span>;
}

function Caption({ title, sub }: { title: string; sub: string }) {
  return (
    <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 via-black/30 to-transparent px-2.5 pb-2 pt-8 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
      <span className="block truncate text-[13px] font-medium text-white">{title}</span>
      <span className="block truncate text-[11px] text-white/75">{sub}</span>
    </span>
  );
}

function MediaTile({ m, onOpen }: { m: MediaItem; onOpen: () => void }) {
  const video = m.mime.startsWith("video");
  const Icon = m.mime.startsWith("audio") ? Music : m.mime.startsWith("image") ? ImageIcon : video ? Film : FileText;
  return (
    <TileFrame onClick={onOpen} label={`${m.name}, ${m.project_name}`}>
      {m.poster_url ? <img src={m.poster_url} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
        : m.url && video ? <video src={`${m.url}#t=0.5`} muted preload="metadata" playsInline className="pointer-events-none h-full w-full object-cover" />
        : m.url && m.mime.startsWith("image") ? <img src={m.url} alt="" loading="lazy" className="h-full w-full object-cover" />
        : <span className="flex h-full flex-col items-center justify-center gap-2 px-3 text-center text-text-3">
            <Icon className="size-6" /><span className="line-clamp-2 break-all text-xs text-text-2">{m.name}</span></span>}
      {m.status === "processing" && <Corner className="left-2 top-2">Processing…</Corner>}
      {m.version != null && <Corner className="left-2 top-2">v{m.version}</Corner>}
      {m.duration ? <Corner className="bottom-2 right-2">{duration(m.duration)}</Corner> : null}
      <Caption title={m.name} sub={`${m.project_name} · ${ago(m.created_at)}`} />
    </TileFrame>
  );
}

const REVIEW: Record<string, { label: string; icon: React.ReactNode } | undefined> = {
  ok: { label: "Usable", icon: <Check className="size-3" /> },
  caution: { label: "Caution", icon: <TriangleAlert className="size-3" /> },
  banned: { label: "Banned", icon: <Ban className="size-3" /> },
};

function ClipTile({ c, onOpen }: { c: Clip; onOpen: () => void }) {
  const r = REVIEW[c.review];
  return (
    <TileFrame onClick={onOpen} label={c.name}>
      {c.thumb_url ? <img src={c.thumb_url} alt="" loading="lazy" className={clsx("h-full w-full object-cover", c.review === "banned" && "opacity-40 grayscale")} />
        : <span className="flex h-full items-center justify-center text-text-3"><Film className="size-6" /></span>}
      {r && <Corner className="left-2 top-2"><span className="flex items-center gap-1">{r.icon}{r.label}</span></Corner>}
      {c.duration ? <Corner className="bottom-2 right-2">{duration(c.duration)}</Corner> : null}
      <Caption title={c.name} sub={c.folder || "Library"} />
    </TileFrame>
  );
}

function Preview({ item, onClose, onUse }: { item: MediaItem | null; onClose: () => void; onUse: (p: Pick) => void }) {
  const toast = useToast();
  const m = item;
  const download = async () => {
    if (!m) return;
    try { window.open((await api.get<{ url: string }>(`/assets/${m.id}/url?download=true`)).url, "_blank", "noopener"); }
    catch (e) { toast((e as Error).message, "danger"); }
  };
  return (
    <Dialog open={!!m} onClose={onClose} title={m?.name ?? ""} width={760}
      description={m && <>{m.project_name}{m.version != null && ` · version ${m.version}`} · {ago(m.created_at)}</>}
      footer={m && <>
        <Link href={`/projects/${m.project_id}?tab=${m.kind === "render" ? "review" : m.kind === "footage" ? "media" : "claude"}`}><Button variant="ghost">Open project</Button></Link>
        <Button icon={<Download className="size-4" />} onClick={download}>Download</Button>
        <Button variant="primary" icon={<MessageSquarePlus className="size-4" />}
          onClick={() => onUse({ name: m.name, project_id: m.project_id, project_name: m.project_name, brand_id: m.brand_id, kind: m.kind })}>Use in chat</Button>
      </>}>
      {m && (m.url && m.mime.startsWith("video") ? <video src={m.url} controls autoPlay playsInline className="max-h-[60vh] w-full rounded-lg bg-black" />
        : m.url && m.mime.startsWith("audio") ? <audio src={m.url} controls className="w-full" />
        : m.url && m.mime.startsWith("image") ? <img src={m.url} alt="" className="max-h-[60vh] w-full rounded-lg object-contain" />
        : <p className="text-sm text-text-2">No preview for this file. Download it to open it.</p>)}
      {m && <p className="text-[13px] text-text-2 tabular">{[m.width && `${m.width}×${m.height}`, m.duration && duration(m.duration), m.mime].filter(Boolean).join(" · ")}</p>}
    </Dialog>
  );
}

function ClipPreview({ clip, onClose, onUse }: { clip: Clip | null; onClose: () => void; onUse: (p: Pick) => void }) {
  const c = clip;
  const r = c ? REVIEW[c.review] : undefined;
  return (
    <Dialog open={!!c} onClose={onClose} title={c?.name ?? ""} width={760} description={c && [c.folder, c.duration && duration(c.duration), c.size && bytes(c.size)].filter(Boolean).join(" · ")}
      footer={c && <Button variant="primary" icon={<MessageSquarePlus className="size-4" />} disabled={c.review === "banned"}
        onClick={() => onUse({ name: c.name, kind: "library clip" })}>Use in chat</Button>}>
      {c?.strip_url ? <img src={c.strip_url} alt="Frames from the clip" className="w-full rounded-lg border border-border" />
        : c?.thumb_url ? <img src={c.thumb_url} alt="" className="max-h-[50vh] w-full rounded-lg object-contain" /> : null}
      {r && <Badge tone={c!.review === "ok" ? "success" : c!.review === "caution" ? "warning" : "danger"}>{r.label}</Badge>}
      {c && Object.keys(c.info ?? {}).length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
          {Object.entries(c.info).map(([k, v]) => <Fragment key={k}><dt className="text-text-3">{k}</dt><dd>{v}</dd></Fragment>)}
        </dl>
      )}
    </Dialog>
  );
}

interface Up { name: string; progress: number; error?: string }

function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { brandId } = useWorkspace();
  const me = useMe().data!;
  const qc = useQueryClient();
  const toast = useToast();
  const writable = new Set(me.brands.filter((b) => b.role === "lead" || b.role === "editor").map((b) => b.id));
  const recent = useQuery({ queryKey: ["recent", "upload"], queryFn: () => api.get<Project[]>("/projects/recent?limit=50"), enabled: open });
  const options = (recent.data ?? []).filter((p) => writable.has(p.brand_id) && (!brandId || p.brand_id === brandId));
  const [project, setProject] = useState("");
  const [ups, setUps] = useState<Up[]>([]);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open && !project && options[0]) setProject(options[0].id); }, [open, options, project]);
  useEffect(() => { if (!open) setUps([]); }, [open]);
  const start = (files: FileList) => {
    for (const f of Array.from(files)) {
      setUps((x) => [...x, { name: f.name, progress: 0 }]);
      uploadFile(project, f, (p) => setUps((x) => x.map((u) => (u.name === f.name ? { ...u, progress: p } : u))), new AbortController().signal)
        .then(() => {
          setUps((x) => x.map((u) => (u.name === f.name ? { ...u, progress: 1 } : u)));
          qc.invalidateQueries({ queryKey: ["workspace", "media"] });
          qc.invalidateQueries({ queryKey: ["project", project] });
          toast(`${f.name} uploaded · processing`, "success");
        })
        .catch((e: Error) => setUps((x) => x.map((u) => (u.name === f.name ? { ...u, error: e.message } : u))));
    }
  };
  return (
    <Dialog open={open} onClose={onClose} title="Upload footage" description="Files go straight to secure storage, then get a preview, poster and frame strip."
      footer={<Button onClick={onClose}>Done</Button>}>
      {options.length === 0 ? (
        <p className="text-sm text-text-2">{recent.isLoading ? "Loading projects…" : "There's no project you can upload to here yet. Start a chat, or create a project on the brand's page."}</p>
      ) : (<>
        <Field label="Project">
          <Select value={project} onChange={(e) => setProject(e.target.value)}>
            {options.map((p) => <option key={p.id} value={p.id}>{p.name}{!brandId ? ` · ${me.brands.find((b) => b.id === p.brand_id)?.name ?? ""}` : ""}</option>)}
          </Select>
        </Field>
        <Button variant="primary" icon={<Upload className="size-4" />} onClick={() => input.current?.click()} disabled={!project}>Choose files</Button>
        <input ref={input} type="file" multiple accept="video/*,audio/*,image/*" className="hidden" onChange={(e) => { if (e.target.files) start(e.target.files); e.target.value = ""; }} />
        {ups.map((u) => (
          <div key={u.name} className="space-y-1">
            <div className="flex justify-between gap-3 text-[13px]"><span className="truncate">{u.name}</span>
              <span className={clsx("shrink-0 tabular", u.error ? "text-danger" : "text-text-2")}>{u.error ? "failed" : u.progress >= 1 ? "done" : `${Math.round(u.progress * 100)}%`}</span></div>
            {u.error ? <p className="text-xs text-danger">{u.error}</p> : <Progress value={u.progress} tone={u.progress >= 1 ? "success" : "accent"} />}
          </div>
        ))}
      </>)}
    </Dialog>
  );
}

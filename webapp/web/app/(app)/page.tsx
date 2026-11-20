"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowUp, Captions, ChevronDown, Clapperboard, Clock3, Cpu, Images, Megaphone, Package, MoreHorizontal, Music, PanelRightClose,
  PanelRightOpen, Paperclip, Plus, RectangleVertical, Scissors, ShieldCheck, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { BrandSwitcher } from "@/components/shell";
import { Badge, Button, Dialog, Input, Progress, useToast } from "@/components/ui";
import { brandQuery, useWorkspace } from "@/components/workspace/context";
import { Gallery, type Pick } from "@/components/workspace/gallery";
import { api } from "@/lib/api";
import { KIND_LABEL, modelName } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { uploadFile } from "@/lib/upload";
import type { Capabilities, Product, Project, QuickAction, ThreadDetail, WorkspaceThread } from "@/lib/types";

const PLATFORMS = [
  { value: "auto", label: "Any format", hint: "", kind: "other" },
  { value: "reels", label: "Reels · 9:16", hint: "Deliver it as a vertical 9:16 Instagram Reel.", kind: "reel" },
  { value: "tiktok", label: "TikTok · 9:16", hint: "Deliver it as a vertical 9:16 TikTok.", kind: "tiktok" },
  { value: "shorts", label: "Shorts · 9:16", hint: "Deliver it as a vertical 9:16 YouTube Short.", kind: "short" },
  { value: "youtube", label: "YouTube · 16:9", hint: "Deliver it as a 16:9 YouTube video.", kind: "youtube" },
  { value: "square", label: "Square · 1:1", hint: "Deliver it as a 1:1 square video.", kind: "ad" },
];
const LENGTHS = [
  { value: "auto", label: "Any length", hint: "" }, { value: "15", label: "15 s", hint: "Aim for about 15 seconds." },
  { value: "30", label: "30 s", hint: "Aim for about 30 seconds." }, { value: "60", label: "60 s", hint: "Aim for about 60 seconds." },
  { value: "90", label: "90 s", hint: "Aim for about 90 seconds." },
];
// the tools on the front page, in this order, when the plugin has them; the rest are under "More"
const FEATURED: { skill: string; icon: ReactNode }[] = [
  { skill: "video-edit", icon: <Scissors className="size-4" /> },
  { skill: "video-repurpose", icon: <Clapperboard className="size-4" /> },
  { skill: "ugc-ads", icon: <Megaphone className="size-4" /> },
  { skill: "video-captions", icon: <Captions className="size-4" /> },
  { skill: "video-music", icon: <Music className="size-4" /> },
  { skill: "ai-presenter", icon: <UserRound className="size-4" /> },
];

function Workspace() {
  const me = useMe().data!;
  const { brandId, setBrandId, gallery, setGallery } = useWorkspace();
  const params = useSearchParams();
  const brand = me.brands.find((b) => b.id === brandId) ?? (me.brands.length === 1 ? me.brands[0] : undefined);
  const [text, setText] = useState("");
  const [picks, setPicks] = useState<Pick[]>([]);
  const [projectId, setProjectId] = useState<string>("new");
  const [sheet, setSheet] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (params.get("new")) { setText(""); setPicks([]); setProjectId("new"); area.current?.focus(); } }, [params]);
  const use = (p: Pick) => {
    setPicks((x) => (x.some((y) => y.name === p.name) ? x : [...x, p]));
    if (p.brand_id && p.brand_id !== brandId) setBrandId(p.brand_id);      // work happens in that file's brand
    if (p.project_id && projectId === "new") setProjectId(p.project_id);
    area.current?.focus();
  };
  return (
    <div className="flex h-full min-h-0">
      <div className="relative flex min-w-0 flex-1 flex-col overflow-y-auto">
        <div className="sticky top-0 z-10 flex h-12 shrink-0 items-center justify-end px-3">
          <button onClick={() => setSheet(true)} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-text-2 hover:bg-surface-2 hover:text-text xl:hidden">
            <Images className="size-4" />Gallery
          </button>
          <button onClick={() => setGallery(!gallery)} className="hidden rounded-lg p-1.5 text-text-2 hover:bg-surface-2 hover:text-text xl:block"
            aria-label={gallery ? "Hide gallery" : "Show gallery"} title={gallery ? "Hide gallery" : "Show gallery"}>
            {gallery ? <PanelRightClose className="size-5" /> : <PanelRightOpen className="size-5" />}
          </button>
        </div>
        <div className="mx-auto flex w-full max-w-[760px] flex-1 flex-col px-4 pb-10 pt-[max(2rem,9vh)] sm:px-8">
          <h1 className="text-center font-[family-name:var(--font-display)] text-[56px] leading-none tracking-tight sm:text-[68px]">Studio</h1>
          <div className="mt-5 flex justify-center">
            {me.brands.length === 0 ? (
              me.org_role === "admin"
                ? <Link href="/brands/new" className="flex h-8 items-center gap-1.5 rounded-full border border-dashed border-border-strong px-3.5 text-sm text-text-2 hover:text-text"><Plus className="size-4" />Add brand</Link>
                : <span className="text-sm text-text-3">Ask an admin to add you to a brand.</span>
            ) : <div className="w-56"><BrandSwitcher brands={me.brands} isAdmin={me.org_role === "admin"} compact /></div>}
          </div>
          <p className="mt-4 text-center text-[15px] text-text-2">Start with a prompt, or choose a tool below. Claude runs the full video-studio plugin with this client&apos;s lessons.</p>
          <Composer text={text} setText={setText} area={area} picks={picks} setPicks={setPicks} brandId={brand?.id ?? null}
            projectId={projectId} setProjectId={setProjectId} />
          <Tools onPick={(a) => { setText(a.prompt); area.current?.focus(); }} />
          <WaitingOnYou />
        </div>
      </div>
      {gallery && (
        <aside className="hidden w-[min(44vw,620px)] shrink-0 border-l border-border bg-surface xl:block">
          <Gallery onUse={use} />
        </aside>
      )}
      {sheet && (
        <div className="fixed inset-0 z-40 flex flex-col bg-surface xl:hidden" role="dialog" aria-label="Gallery">
          <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
            <span className="text-sm font-semibold">Gallery</span>
            <button onClick={() => setSheet(false)} className="rounded-md p-1.5 text-text-2 hover:bg-surface-2" aria-label="Close gallery"><X className="size-4" /></button>
          </div>
          <div className="min-h-0 flex-1"><Gallery onUse={(p) => { setSheet(false); use(p); }} /></div>
        </div>
      )}
    </div>
  );
}

/* ---------------- the prompt ---------------- */

function Chip({ icon, children, onClick, active, title }: { icon: ReactNode; children: ReactNode; onClick?: () => void; active?: boolean; title?: string }) {
  return (
    <button type="button" onClick={onClick} title={title}
      className={clsx("flex h-8 items-center gap-1.5 rounded-lg px-2 text-[13px] transition-colors",
        active ? "bg-accent-soft text-accent" : "text-text-2 hover:bg-surface-2 hover:text-text")}>
      {icon}<span className="max-w-44 truncate">{children}</span>
    </button>
  );
}

function Menu<T extends string>({ value, options, onChange, icon, title }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; icon: ReactNode; title: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", down);
    return () => document.removeEventListener("mousedown", down);
  }, [open]);
  const current = options.find((o) => o.value === value);
  return (
    <div className="relative" ref={ref}>
      <Chip icon={icon} onClick={() => setOpen(!open)} active={value !== options[0].value} title={title}>
        <span className="flex items-center gap-1">{current?.label}<ChevronDown className="size-3.5" /></span>
      </Chip>
      {open && (
        <div role="listbox" aria-label={title} className="absolute bottom-full left-0 z-20 mb-1 max-h-72 min-w-48 overflow-y-auto rounded-xl border border-border bg-surface p-1 shadow-pop">
          {options.map((o) => (
            <button key={o.value} role="option" aria-selected={o.value === value} onClick={() => { onChange(o.value); setOpen(false); }}
              className={clsx("block w-full truncate rounded-lg px-2.5 py-1.5 text-left text-[13px] hover:bg-surface-2", o.value === value && "font-medium text-accent")}>{o.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function titleFrom(text: string) {
  const words = text.replace(/\s+/g, " ").trim().split(" ").slice(0, 7).join(" ");
  return (words.length > 60 ? words.slice(0, 60) : words).replace(/[.,;:!?]+$/, "") || "New project";
}

function Composer({ text, setText, area, picks, setPicks, brandId, projectId, setProjectId }: {
  text: string; setText: (v: string) => void; area: React.RefObject<HTMLTextAreaElement | null>; picks: Pick[];
  setPicks: (f: (p: Pick[]) => Pick[]) => void; brandId: string | null; projectId: string; setProjectId: (v: string) => void;
}) {
  const me = useMe().data!;
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const caps = useQuery({ queryKey: ["claude-capabilities"], queryFn: () => api.get<Capabilities>("/claude/capabilities"), staleTime: 300_000 });
  const projects = useQuery({ queryKey: ["brand", brandId, "projects"], queryFn: () => api.get<Project[]>(`/brands/${brandId}/projects`), enabled: !!brandId });
  const products = useQuery({ queryKey: ["brand", brandId, "products"], queryFn: () => api.get<Product[]>(`/brands/${brandId}/products`), enabled: !!brandId });
  const [productId, setProductId] = useState("none");
  // an existing project brings its product; a new one takes what's picked
  const chosen = projects.data?.find((p) => p.id === projectId);
  useEffect(() => { if (chosen) setProductId(chosen.product_id ?? "none"); }, [chosen?.id, chosen?.product_id]);
  useEffect(() => { if (productId !== "none" && products.data && !products.data.some((p) => p.id === productId)) setProductId("none"); },
    [products.data, productId]);
  const [platform, setPlatform] = useState("auto");
  const [length, setLength] = useState("auto");
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const brand = me.brands.find((b) => b.id === brandId);
  const canEdit = brand?.role === "lead" || brand?.role === "editor";
  const configured = caps.data?.configured ?? true;
  useEffect(() => { if (projectId !== "new" && projects.data && !projects.data.some((p) => p.id === projectId)) setProjectId("new"); },
    [projects.data, projectId, setProjectId]);

  const send = useMutation({
    mutationFn: async () => {
      let pid = projectId;
      const plat = PLATFORMS.find((p) => p.value === platform)!;
      const product = productId === "none" ? null : productId;
      if (pid === "new") {
        const p = await api.post<Project>(`/brands/${brandId}/projects`, { name: titleFrom(text), kind: plat.kind, brief: text.slice(0, 2000), product_id: product });
        pid = p.id;
      } else if ((chosen?.product_id ?? null) !== product) {
        await api.patch(`/projects/${pid}`, product ? { product_id: product } : { clear_product: true });
      }
      for (let i = 0; i < files.length; i++) {
        setProgress(i / files.length);
        await uploadFile(pid, files[i], (f) => setProgress((i + f) / files.length), new AbortController().signal);
      }
      setProgress(null);
      const extra = [plat.hint, LENGTHS.find((l) => l.value === length)!.hint,
        files.length ? `I just uploaded: ${files.map((f) => f.name).join(", ")} (they appear in raw/ once processed).` : "",
        picks.length ? `Use these: ${picks.map((p) => `${p.name}${p.kind === "library clip" ? " (from the client's library)" : p.project_name ? ` (${p.kind} in “${p.project_name}”)` : ""}`).join("; ")}.` : ""]
        .filter(Boolean).join(" ");
      const t = await api.post<ThreadDetail>(`/projects/${pid}/claude/threads`, { text: extra ? `${text.trim()}\n\n${extra}` : text.trim() });
      return { pid, t };
    },
    onSuccess: ({ pid, t }) => {
      qc.invalidateQueries({ queryKey: ["workspace"] });
      setText(""); setFiles([]); setPicks(() => []);
      router.push(`/projects/${pid}?tab=claude&thread=${t.id}`);
    },
    onError: (e: Error) => { setProgress(null); toast(e.message, "danger"); },
  });
  const blocked = !brandId ? "Pick a brand first" : !canEdit ? "Viewers can't start chats on this brand" : !configured ? "Claude isn't set up on this server yet" : "";
  const go = () => { if (!blocked && text.trim() && !send.isPending) send.mutate(); };
  const key = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); go(); }
  };
  const projectOptions = [{ value: "new", label: "New project" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: `${p.name} · ${KIND_LABEL[p.kind] ?? p.kind}` }))];
  return (
    <div className="mt-8">
      <div className="rounded-2xl border border-border bg-surface shadow-card transition-shadow focus-within:border-border-strong focus-within:shadow-pop">
        {(picks.length > 0 || files.length > 0) && (
          <div className="flex flex-wrap gap-1.5 px-4 pt-3">
            {picks.map((p) => (
              <span key={p.name} className="flex max-w-full items-center gap-1 rounded-lg bg-surface-2 py-1 pl-2 pr-1 text-xs text-text-2">
                <span className="truncate">{p.name}</span>
                <button onClick={() => setPicks((x) => x.filter((y) => y.name !== p.name))} aria-label={`Remove ${p.name}`} className="rounded p-0.5 hover:bg-border"><X className="size-3" /></button>
              </span>
            ))}
            {files.map((f) => (
              <span key={f.name} className="flex max-w-full items-center gap-1 rounded-lg bg-accent-soft py-1 pl-2 pr-1 text-xs text-accent">
                <Paperclip className="size-3" /><span className="truncate">{f.name}</span>
                <button onClick={() => setFiles((x) => x.filter((y) => y !== f))} aria-label={`Remove ${f.name}`} className="rounded p-0.5 hover:bg-accent/10"><X className="size-3" /></button>
              </span>
            ))}
          </div>
        )}
        <textarea ref={area} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={key} rows={3}
          placeholder="What do you want to make today?" aria-label="What do you want to make today?"
          className="block max-h-72 min-h-24 w-full resize-none bg-transparent px-4 py-3.5 text-[15px] placeholder:text-text-3 focus:outline-none focus-visible:outline-none" />
        {progress != null && <div className="px-4 pb-2"><Progress value={progress} /><p className="mt-1 text-xs text-text-3">Uploading footage…</p></div>}
        <div className="flex flex-wrap items-center gap-0.5 px-2 pb-2">
          <button onClick={() => fileInput.current?.click()} className="flex size-8 items-center justify-center rounded-lg text-text-2 hover:bg-surface-2 hover:text-text"
            aria-label="Attach footage" title="Attach footage (uploaded to the project before Claude starts)"><Plus className="size-4" /></button>
          <input ref={fileInput} type="file" multiple accept="video/*,audio/*,image/*" className="hidden"
            onChange={(e) => { const fl = e.target.files; if (fl) setFiles((x) => [...x, ...Array.from(fl)]); e.target.value = ""; }} />
          {brandId && <Menu value={projectId} options={projectOptions} onChange={setProjectId} title="Where Claude works" icon={<Clapperboard className="size-4" />} />}
          {brandId && !!products.data?.length && <Menu value={productId} title="The product this is for"
            options={[{ value: "none", label: "No product" }, ...products.data.map((p) => ({ value: p.id, label: p.name }))]}
            onChange={setProductId} icon={<Package className="size-4" />} />}
          <Menu value={platform} options={PLATFORMS} onChange={setPlatform} title="Format" icon={<RectangleVertical className="size-4" />} />
          <Menu value={length} options={LENGTHS} onChange={setLength} title="Length" icon={<Clock3 className="size-4" />} />
          <span className="ml-1 hidden items-center gap-1.5 px-1 text-[13px] text-text-3 sm:flex" title={caps.data ? `Every turn runs ${caps.data.model} with the video-studio plugin v${caps.data.plugin_version} (set on the server)` : undefined}>
            <Cpu className="size-4" />{caps.data ? modelName(caps.data.model) : "Claude"}
          </span>
          <Button variant="primary" className="ml-auto size-9 rounded-full !p-0" aria-label="Send" title={blocked || "Send (Enter)"}
            disabled={!!blocked || !text.trim()} loading={send.isPending} onClick={go} icon={!send.isPending ? <ArrowUp className="size-4" /> : undefined} />
        </div>
      </div>
      <p className="mt-2 h-4 text-center text-xs text-text-3">
        {blocked ? blocked : projectId === "new" ? `A new ${PLATFORMS.find((p) => p.value === platform)!.kind === "other" ? "" : PLATFORMS.find((p) => p.value === platform)!.label.split(" ")[0] + " "}project in ${brand?.name} is created for this chat. Paid steps wait for a lead.`
          : "Claude works in this project's files. Paid steps wait for a lead."}
      </p>
    </div>
  );
}

/* ---------------- tools ---------------- */

function Tools({ onPick }: { onPick: (a: QuickAction) => void }) {
  const caps = useQuery({ queryKey: ["claude-capabilities"], queryFn: () => api.get<Capabilities>("/claude/capabilities"), staleTime: 300_000 });
  const [all, setAll] = useState(false);
  const [q, setQ] = useState("");
  const actions = caps.data?.quick_actions ?? [];
  const featured = FEATURED.map((f) => ({ ...f, a: actions.find((a) => a.skill === f.skill) })).filter((f) => f.a);
  const groups = useMemo(() => {
    const g: Record<string, QuickAction[]> = {};
    actions.filter((a) => !q || `${a.label} ${a.prompt}`.toLowerCase().includes(q.toLowerCase())).forEach((a) => { (g[a.group] ??= []).push(a); });
    return g;
  }, [actions, q]);
  if (!caps.data) return null;
  return (
    <section className="mt-10">
      <h2 className="mb-3 text-sm font-medium text-text-2">Tools</h2>
      <div className="flex flex-wrap gap-2">
        {featured.map(({ a, icon }) => (
          <button key={a!.skill} onClick={() => onPick(a!)} title={a!.prompt}
            className="flex h-10 items-center gap-2 rounded-full border border-border bg-surface px-4 text-sm text-text shadow-card transition-colors hover:border-border-strong hover:bg-surface-2">
            <span className="text-text-2">{icon}</span>{a!.label}
          </button>
        ))}
        <button onClick={() => setAll(true)} className="flex h-10 items-center gap-2 rounded-full border border-border bg-surface px-4 text-sm text-text shadow-card hover:border-border-strong hover:bg-surface-2">
          <MoreHorizontal className="size-4 text-text-2" />More
        </button>
      </div>
      <Dialog open={all} onClose={() => setAll(false)} title="Everything Claude can do here" width={640}
        description={`${caps.data.skills.length} skills and ${caps.data.agents.length} specialists from the video-studio plugin. Pick one to start from its request, or just describe what you want.`}>
        <Input autoFocus placeholder="Search tools…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="max-h-[55vh] space-y-4 overflow-y-auto pr-1">
          {Object.entries(groups).map(([group, items]) => (
            <div key={group}>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-3">{group}</p>
              <div className="space-y-0.5">
                {items.map((a) => (
                  <button key={a.skill} onClick={() => { setAll(false); onPick(a); }} className="block w-full rounded-lg px-2.5 py-2 text-left hover:bg-surface-2">
                    <span className="block text-sm font-medium">{a.label}</span>
                    <span className="line-clamp-1 block text-xs text-text-2">{a.prompt}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Dialog>
    </section>
  );
}

/* ---------------- what's waiting ---------------- */

function WaitingOnYou() {
  const { brandId } = useWorkspace();
  const threads = useQuery({ queryKey: ["workspace", "threads", brandId], queryFn: () => api.get<WorkspaceThread[]>(`/workspace/threads${brandQuery(brandId)}`) });
  const waiting = (threads.data ?? []).filter((t) => t.pending_approvals > 0 || t.status === "failed").slice(0, 4);
  if (!waiting.length) return null;
  return (
    <section className="mt-10">
      <h2 className="mb-3 text-sm font-medium text-text-2">Waiting on you</h2>
      <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
        {waiting.map((t) => (
          <Link key={t.id} href={`/projects/${t.project_id}?tab=claude&thread=${t.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2">
            <ShieldCheck className={clsx("size-4 shrink-0", t.pending_approvals ? "text-warning" : "text-danger")} />
            <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{t.title}</span>
              <span className="block truncate text-xs text-text-3">{t.project_name}</span></span>
            {t.pending_approvals ? <Badge tone="warning">{t.pending_approvals} to approve</Badge> : <Badge tone="danger">Failed</Badge>}
          </Link>
        ))}
      </div>
    </section>
  );
}

export default function Page() { return <Suspense><Workspace /></Suspense>; }

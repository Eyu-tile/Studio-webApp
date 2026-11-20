"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { BookOpenCheck, Check, ChevronDown, ChevronUp, FolderKanban, GraduationCap, Layers, Library, LoaderCircle,
  LogOut, Menu, Package, PanelLeftClose, PanelLeftOpen, Plug, Plus, Shield, SquarePen, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { JOB_LABEL, KIND_LABEL } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Brand, Me, Spend, Task, WorkspaceThread } from "@/lib/types";
import { money } from "./brand/spending";
import { Logo } from "./logo";
import { Avatar, Progress, Spinner } from "./ui";
import { brandQuery, useWorkspace, WorkspaceProvider } from "./workspace/context";

export function Shell({ children }: { children: ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => { if (me.error?.status === 401) router.replace(`/login?next=${encodeURIComponent(path)}`); }, [me.error, router, path]);
  if (me.isLoading || me.error) return <div className="flex h-screen items-center justify-center"><Spinner className="size-5" /></div>;
  return (
    <WorkspaceProvider brands={me.data!.brands}>
      <Suspense><Frame me={me.data!}>{children}</Frame></Suspense>
    </WorkspaceProvider>
  );
}

function Frame({ me, children }: { me: Me; children: ReactNode }) {
  const path = usePathname();
  const { sidebar, setSidebar } = useWorkspace();
  const [drawer, setDrawer] = useState(false);
  useEffect(() => setDrawer(false), [path]);
  const fullBleed = path === "/";                  // the workspace lays out its own columns
  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <div className="flex min-h-0 flex-1">
        <div className={clsx("hidden shrink-0 lg:block", !sidebar && "lg:hidden")}><Sidebar me={me} /></div>
        {drawer && (
          <div className="fixed inset-0 z-40 flex lg:hidden">
            <div className="shadow-pop"><Sidebar me={me} onClose={() => setDrawer(false)} /></div>
            <div className="flex-1 bg-black/40" onClick={() => setDrawer(false)} />
          </div>
        )}
        <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-surface px-3 lg:hidden">
            <button onClick={() => setDrawer(true)} className="rounded-md p-1.5 text-text-2" aria-label="Open menu"><Menu className="size-5" /></button>
            <Logo size={22} /><span className="font-semibold">Studio</span>
          </div>
          {!sidebar && (
            <button onClick={() => setSidebar(true)} aria-label="Show sidebar" title="Show sidebar"
              className="absolute left-3 top-3 z-10 hidden rounded-lg border border-border bg-surface p-1.5 text-text-2 shadow-card hover:text-text lg:block">
              <PanelLeftOpen className="size-4" />
            </button>
          )}
          {fullBleed ? <div className="min-h-0 flex-1">{children}</div> : (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-8 sm:py-8">{children}</div>
            </div>
          )}
        </main>
      </div>
      <TasksBar />
    </div>
  );
}

/* ---------------- sidebar ---------------- */

function Sidebar({ me, onClose }: { me: Me; onClose?: () => void }) {
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  const { brandId, setSidebar } = useWorkspace();
  const brand = me.brands.find((b) => b.id === brandId) ?? null;
  const signOut = async () => { await api.post("/auth/logout"); qc.clear(); router.replace("/login"); };
  const nav = (href: string, active: boolean, icon: ReactNode, label: string) => (
    <Link href={href} className={clsx("flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
      active ? "bg-surface-2 font-medium text-text" : "text-text-2 hover:bg-surface-2 hover:text-text")}>{icon}{label}</Link>
  );
  const params = useSearchParams();
  const onBrand = brand && path === `/brands/${brand.id}`;
  const tab = params.get("tab");
  return (
    <aside className="flex h-full w-[272px] flex-col border-r border-border bg-surface">
      <div className="flex h-14 shrink-0 items-center gap-2.5 px-4">
        <Link href="/" className="flex items-center gap-2.5"><Logo /><span className="text-[17px] font-semibold tracking-tight">Studio</span></Link>
        {onClose ? <button className="ml-auto rounded-md p-1 text-text-3" onClick={onClose} aria-label="Close menu"><X className="size-4" /></button>
          : <button className="ml-auto rounded-md p-1 text-text-3 hover:bg-surface-2 hover:text-text" onClick={() => setSidebar(false)}
              aria-label="Hide sidebar" title="Hide sidebar"><PanelLeftClose className="size-4" /></button>}
      </div>
      <div className="space-y-2 px-3">
        <p className="px-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-3">Brand · client</p>
        <BrandSwitcher brands={me.brands} isAdmin={me.org_role === "admin"} />
        <Link href="/?new=1" className="flex h-9 items-center gap-2 rounded-lg border border-border px-3 text-sm font-medium text-text shadow-card transition-colors hover:border-border-strong hover:bg-surface-2">
          <SquarePen className="size-4 text-text-2" />New chat
        </Link>
      </div>
      <Chats brandId={brandId} brands={me.brands} />
      <nav className="shrink-0 space-y-0.5 border-t border-border px-3 py-2.5">
        {brand ? (<>
          {nav(`/brands/${brand.id}?tab=projects`, !!onBrand && (tab === "projects" || !tab), <FolderKanban className="size-4" />, "Projects")}
          {nav(`/brands/${brand.id}?tab=products`, !!onBrand && tab === "products", <Package className="size-4" />, "Products")}
          {nav(`/brands/${brand.id}?tab=library`, !!onBrand && tab === "library", <Library className="size-4" />, "Library")}
          {nav(`/brands/${brand.id}?tab=lessons`, !!onBrand && tab === "lessons", <GraduationCap className="size-4" />, "Lessons")}
          {nav(`/brands/${brand.id}?tab=connections`, !!onBrand && tab === "connections", <Plug className="size-4" />, "Connections")}
        </>) : (
          <p className="px-2.5 py-1 text-[13px] text-text-3">Pick a brand for its projects, library, lessons and connections.</p>
        )}
        {me.org_role === "admin" && nav("/admin", path.startsWith("/admin"), <Shield className="size-4" />, "Admin")}
      </nav>
      <Footer me={me} onSignOut={signOut} />
    </aside>
  );
}

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); };
  }, [open]);
  return { open, setOpen, ref };
}

export function BrandSwitcher({ brands, isAdmin, compact }: { brands: Brand[]; isAdmin: boolean; compact?: boolean }) {
  const { brandId, setBrandId } = useWorkspace();
  const router = useRouter();
  const { open, setOpen, ref } = usePopover();
  const current = brands.find((b) => b.id === brandId);
  const pick = (id: string | null) => { setBrandId(id); setOpen(false); };
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open}
        className={clsx("flex w-full items-center gap-2.5 rounded-lg border border-border bg-surface text-left text-sm shadow-card transition-colors hover:border-border-strong",
          compact ? "h-8 px-2.5" : "h-10 px-3")}>
        {current ? <span className="size-2.5 shrink-0 rounded-[4px]" style={{ background: current.color }} /> : <Layers className="size-4 shrink-0 text-text-2" />}
        <span className="min-w-0 flex-1 truncate font-medium">{current?.name ?? "All brands"}</span>
        <ChevronDown className="size-4 shrink-0 text-text-3" />
      </button>
      {open && (
        <div role="listbox" className="absolute left-0 right-0 top-full z-30 mt-1 max-h-80 min-w-56 overflow-y-auto rounded-xl border border-border bg-surface p-1 shadow-pop">
          {[{ id: null as string | null, name: "All brands", color: "" }, ...brands].map((b) => (
            <button key={b.id ?? "all"} role="option" aria-selected={brandId === b.id} onClick={() => pick(b.id)}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-surface-2">
              {b.id ? <span className="size-2.5 shrink-0 rounded-[4px]" style={{ background: b.color }} /> : <Layers className="size-4 text-text-2" />}
              <span className="min-w-0 flex-1 truncate">{b.name}</span>
              {brandId === b.id && <Check className="size-4 text-accent" />}
            </button>
          ))}
          {isAdmin && (
            <button onClick={() => { setOpen(false); router.push("/brands/new"); }}
              className="mt-1 flex w-full items-center gap-2.5 rounded-lg border-t border-border px-2.5 py-2 text-left text-sm text-text-2 hover:bg-surface-2 hover:text-text">
              <Plus className="size-4" />Add brand
            </button>
          )}
        </div>
      )}
    </div>
  );
}

const TAG: Record<string, { label: string; className: string }> = {
  waiting: { label: "Approval", className: "bg-warning-soft text-warning" },
  running: { label: "Working", className: "bg-accent-soft text-accent" },
  queued: { label: "Queued", className: "bg-accent-soft text-accent" },
  failed: { label: "Failed", className: "bg-danger-soft text-danger" },
};

function Chats({ brandId, brands }: { brandId: string | null; brands: Brand[] }) {
  const path = usePathname();
  const params = useSearchParams();
  const threads = useQuery({
    queryKey: ["workspace", "threads", brandId],
    queryFn: () => api.get<WorkspaceThread[]>(`/workspace/threads${brandQuery(brandId)}`),
    refetchInterval: (q) => (q.state.data?.some((t) => t.status !== "idle" && t.status !== "failed") ? 5000 : 30_000),
  });
  const color = Object.fromEntries(brands.map((b) => [b.id, b.color]));
  const activeThread = params.get("thread");
  return (
    <div className="mt-4 flex min-h-0 flex-1 flex-col">
      <p className="px-4 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-3">Chats</p>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {!threads.data ? <div className="space-y-2 px-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-8 rounded-lg" />)}</div>
          : threads.data.length === 0 ? <p className="px-2.5 py-1 text-[13px] text-text-3">No conversations yet. Start one with New chat.</p>
          : threads.data.map((t) => {
            const tag = t.pending_approvals > 0 ? TAG.waiting : TAG[t.status];
            const href = `/projects/${t.project_id}?tab=claude&thread=${t.id}`;
            const active = path === `/projects/${t.project_id}` && activeThread === t.id;
            return (
              <Link key={t.id} href={href} title={`${t.title} · ${t.project_name}`}
                className={clsx("group flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors",
                  active ? "bg-surface-2 text-text" : "text-text-2 hover:bg-surface-2 hover:text-text")}>
                {!brandId && <span className="size-1.5 shrink-0 rounded-full" style={{ background: color[t.brand_id] }} />}
                <span className="min-w-0 flex-1 truncate">{t.title}</span>
                {tag ? <span className={clsx("shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-medium", tag.className)}>{tag.label}</span>
                  : <span className="shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 text-[11px] text-text-3 group-hover:bg-surface">{KIND_LABEL[t.project_kind] ?? t.project_kind}</span>}
              </Link>
            );
          })}
      </div>
    </div>
  );
}

function Footer({ me, onSignOut }: { me: Me; onSignOut: () => void }) {
  const { brandId } = useWorkspace();
  const spend = useQuery({ queryKey: ["workspace", "spend", brandId], queryFn: () => api.get<Spend>(`/workspace/spend${brandQuery(brandId)}`),
    refetchInterval: 60_000 });
  return (
    <div className="shrink-0 border-t border-border px-3 py-3">
      <div className="flex items-center gap-2.5 px-1">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={me.email}>{me.name || me.email}</p>
          <p className="truncate text-xs text-text-3 tabular" title="What Claude has cost this month, for the brands in view">
            {spend.data ? <>{money(spend.data.spent_usd)}{spend.data.limit_usd != null && ` of ${money(spend.data.limit_usd)}`} Claude · {spend.data.month.split(" ")[0]}</> : " "}
          </p>
        </div>
        <Avatar name={me.name} email={me.email} url={me.avatar_url} size={30} />
        <button onClick={onSignOut} className="rounded-md p-1.5 text-text-3 hover:bg-surface-2 hover:text-text" title="Sign out" aria-label="Sign out">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  );
}

/* ---------------- tasks bar ---------------- */

function TasksBar() {
  const { brandId } = useWorkspace();
  const { open, setOpen, ref } = usePopover();
  const tasks = useQuery({ queryKey: ["workspace", "tasks", brandId], queryFn: () => api.get<Task[]>(`/workspace/tasks${brandQuery(brandId)}`),
    refetchInterval: (q) => (q.state.data?.length ? 3000 : 10_000) });
  const list = tasks.data ?? [];
  const running = list.filter((t) => t.status === "running").length;
  return (
    <div ref={ref} className="relative shrink-0 border-t border-border bg-surface">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex h-9 w-full items-center gap-3 px-4 text-[13px] text-text-2 hover:text-text">
        <span className="flex items-center gap-1 font-medium text-text">Tasks{open ? <ChevronDown className="size-3.5" /> : <ChevronUp className="size-3.5" />}</span>
        {list.length === 0 ? <span className="flex items-center gap-1.5 text-text-3"><BookOpenCheck className="size-3.5" />No active tasks</span>
          : <span className="flex min-w-0 items-center gap-1.5"><LoaderCircle className="size-3.5 shrink-0 animate-spin text-accent" />
              <span className="truncate">{running} running{list.length > running && ` · ${list.length - running} queued`} · {JOB_LABEL[list[0].kind] ?? list[0].kind} in {list[0].project_name}</span></span>}
      </button>
      {open && (
        <div className="absolute bottom-full left-2 z-30 mb-1 w-[min(420px,calc(100vw-16px))] rounded-xl border border-border bg-surface p-1.5 shadow-pop">
          {list.length === 0 ? <p className="px-3 py-4 text-center text-[13px] text-text-3">Uploads, cuts, checks and Claude turns show up here while they run.</p>
            : list.map((t) => (
              <Link key={t.id} href={`/projects/${t.project_id}?tab=activity`} onClick={() => setOpen(false)} className="block rounded-lg px-3 py-2 hover:bg-surface-2">
                <div className="flex items-center gap-2 text-[13px]">
                  <span className="font-medium">{JOB_LABEL[t.kind] ?? t.kind}</span>
                  <span className="min-w-0 flex-1 truncate text-text-3">{t.project_name}</span>
                  <span className={clsx("text-xs", t.status === "running" ? "text-accent" : "text-text-3")}>{t.status === "running" ? `${Math.round(t.progress * 100)}%` : "queued"}</span>
                </div>
                <p className="truncate text-xs text-text-2">{t.message}</p>
                {t.status === "running" && <Progress value={t.progress} className="mt-1.5" />}
              </Link>
            ))}
        </div>
      )}
    </div>
  );
}

"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, ArrowUp, Bot, Check, ChevronDown, ChevronRight, CircleDollarSign, Cpu, Download, FileText,
  Film, Loader2, MessageSquarePlus, Plus, ShieldCheck, Sparkles, Square, Terminal, X } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { Avatar, Badge, Button, Card, Dialog, Input, Skeleton, Spinner, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, bytes } from "@/lib/format";
import type { AgentMsg, Approval, Asset, Capabilities, Thread, ThreadDetail } from "@/lib/types";

const BUSY = new Set(["queued", "running", "waiting"]);

export function ClaudeTab({ projectId, canEdit, isLead, openNotes, onOpenReview }: {
  projectId: string; canEdit: boolean; isLead: boolean; openNotes: number; onOpenReview: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const caps = useQuery({ queryKey: ["claude-capabilities"], queryFn: () => api.get<Capabilities>("/claude/capabilities"), staleTime: 300_000 });
  const threads = useQuery({ queryKey: ["project", projectId, "threads"], queryFn: () => api.get<Thread[]>(`/projects/${projectId}/claude/threads`),
    refetchInterval: (q) => (q.state.data?.some((t) => BUSY.has(t.status)) ? 4000 : false) });
  const outputs = useQuery({ queryKey: ["project", projectId, "outputs"], queryFn: () => api.get<Asset[]>(`/projects/${projectId}/outputs`) });
  const [sel, setSel] = useState<string | null>(null);
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    if (!sel && !fresh && threads.data?.length) setSel(threads.data[0].id);
  }, [threads.data, sel, fresh]);
  const start = useMutation({
    mutationFn: (text: string) => api.post<ThreadDetail>(`/projects/${projectId}/claude/threads`, { text }),
    onSuccess: (t) => { qc.setQueryData(["claude", t.id], t); qc.invalidateQueries({ queryKey: ["project", projectId, "threads"] }); setFresh(false); setSel(t.id); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const configured = caps.data?.configured ?? true;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[250px_minmax(0,1fr)]">
      <aside className="order-2 space-y-4 lg:order-none">
        {canEdit && <Button className="w-full" icon={<Plus className="size-4" />} onClick={() => { setSel(null); setFresh(true); }}>New conversation</Button>}
        <Card className="overflow-hidden">
          <p className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-text-3">Conversations</p>
          {!threads.data ? <div className="p-3"><Skeleton className="h-16" /></div>
            : threads.data.length === 0 ? <p className="px-3 py-4 text-[13px] text-text-3">None yet.</p>
            : <ul className="max-h-80 overflow-y-auto py-1">{threads.data.map((t) => (
              <li key={t.id}>
                <button onClick={() => { setSel(t.id); setFresh(false); }}
                  className={clsx("flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-surface-2", sel === t.id && "bg-surface-2")}>
                  <span className="flex items-center gap-2 text-[13px] font-medium"><StatusDot status={t.status} /><span className="truncate">{t.title}</span></span>
                  <span className="pl-4 text-xs text-text-3">{ago(t.updated_at)}{t.cost_usd > 0 && ` · $${t.cost_usd.toFixed(2)}`}</span>
                </button>
              </li>))}</ul>}
        </Card>
        <Card className="overflow-hidden">
          <p className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-text-3">Files Claude made</p>
          {!outputs.data?.length ? <p className="px-3 py-4 text-[13px] text-text-3">Subtitles, exports and pages land here. Videos go to Review.</p>
            : <ul className="max-h-72 overflow-y-auto py-1">{outputs.data.map((a) => <OutputRow key={a.id} a={a} />)}</ul>}
        </Card>
        {caps.data && <SkillsCard caps={caps.data} />}
      </aside>
      <section className="min-w-0">
        {!configured && (
          <Card className="mb-4 flex items-start gap-3 border-warning/40 p-4">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
            <div className="text-sm"><p className="font-medium">Claude isn&apos;t set up on this server yet</p>
              <p className="text-text-2">An admin adds <code className="font-mono text-xs">ANTHROPIC_API_KEY</code> (or Bedrock / Vertex credentials) to the API and worker environment. Everything else on this page works without it.</p></div>
          </Card>
        )}
        {sel && !fresh ? <ThreadView key={sel} threadId={sel} canEdit={canEdit && configured} isLead={isLead} onOpenReview={onOpenReview} />
          : <Start caps={caps.data} canEdit={canEdit && configured} openNotes={openNotes} pending={start.isPending} onSend={(t) => start.mutate(t)} />}
      </section>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  return <span className={clsx("size-2 shrink-0 rounded-full", status === "running" || status === "queued" ? "animate-pulse bg-accent"
    : status === "waiting" ? "bg-warning" : status === "failed" ? "bg-danger" : "bg-border-strong")} title={status} />;
}

function OutputRow({ a }: { a: Asset }) {
  const toast = useToast();
  const get = async () => {
    try { window.open((await api.get<{ url: string }>(`/assets/${a.id}/url?download=true`)).url, "_blank", "noopener"); }
    catch (e) { toast((e as Error).message, "danger"); }
  };
  return (
    <li><button onClick={get} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] hover:bg-surface-2">
      <FileText className="size-3.5 shrink-0 text-text-3" /><span className="min-w-0 flex-1 truncate">{a.filename}</span>
      <span className="text-xs text-text-3">{bytes(a.size)}</span><Download className="size-3.5 text-text-3" />
    </button></li>
  );
}

function SkillsCard({ caps }: { caps: Capabilities }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const all = [...caps.skills, ...caps.agents, ...caps.commands];
  const list = all.filter((c) => !q || `${c.name} ${c.description}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <button onClick={() => setOpen(true)} className="flex w-full items-center gap-2.5 rounded-xl border border-border bg-surface px-3 py-2.5 text-left shadow-card hover:border-border-strong">
        <Cpu className="size-4 text-accent" />
        <span className="min-w-0 flex-1"><span className="block text-[13px] font-medium">What Claude can do here</span>
          <span className="block text-xs text-text-3">{caps.skills.length} skills · {caps.agents.length} specialists · plugin v{caps.plugin_version}</span></span>
        <ChevronRight className="size-4 text-text-3" />
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title="The video-studio plugin" width={640}
        description={`Claude runs the same plugin as in the terminal (${caps.model}). Ask for any of these in plain words.`}>
        <Input autoFocus placeholder="Search skills…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="max-h-[55vh] space-y-1 overflow-y-auto pr-1">
          {list.map((c) => (
            <div key={`${c.kind}-${c.name}`} className="rounded-lg px-2 py-2 hover:bg-surface-2">
              <p className="flex items-center gap-2 text-sm font-medium">{c.name}<Badge tone={c.kind === "skill" ? "neutral" : "accent"}>{c.kind === "agent" ? "specialist" : c.kind}</Badge></p>
              <p className="mt-0.5 line-clamp-2 text-xs text-text-2">{c.description}</p>
            </div>
          ))}
        </div>
      </Dialog>
    </>
  );
}

/* ---------------- starting a conversation ---------------- */

function Start({ caps, canEdit, openNotes, pending, onSend }: {
  caps?: Capabilities; canEdit: boolean; openNotes: number; pending: boolean; onSend: (t: string) => void;
}) {
  const groups = useMemo(() => {
    const g: Record<string, Capabilities["quick_actions"]> = {};
    caps?.quick_actions.forEach((a) => { (g[a.group] ??= []).push(a); });
    return g;
  }, [caps]);
  const [text, setText] = useState("");
  return (
    <Card className="p-5 sm:p-6">
      <div className="mb-5 flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent"><Sparkles className="size-5" /></span>
        <div>
          <h2 className="text-base font-semibold">What should Claude do on this project?</h2>
          <p className="text-sm text-text-2">It works in the project&apos;s files with the full video-studio plugin and this client&apos;s lessons. Videos it makes become new versions; paid steps wait for a lead.</p>
        </div>
      </div>
      <Composer value={text} onChange={setText} disabled={!canEdit} busy={pending} autoFocus
        placeholder={canEdit ? "e.g. Cut a 30 s vertical hook from the interview, captions in the brand style" : "Only editors can ask Claude"}
        onSend={() => { if (text.trim()) onSend(text.trim()); }} />
      {canEdit && openNotes > 0 && (
        <button onClick={() => onSend("Fix every open review note with `vs fix` (exact places only), re-render and run QA. Record any general preference as a lesson.")}
          className="mt-3 flex w-full items-center gap-2 rounded-lg border border-accent/30 bg-accent-soft px-3 py-2 text-left text-sm text-accent hover:border-accent/60">
          <MessageSquarePlus className="size-4" />Fix the {openNotes} open review note{openNotes > 1 && "s"}<ChevronRight className="ml-auto size-4" />
        </button>
      )}
      {canEdit && Object.keys(groups).length > 0 && (
        <div className="mt-6 space-y-3">
          {Object.entries(groups).map(([group, items]) => (
            <div key={group} className="flex flex-wrap items-center gap-1.5">
              <span className="w-20 shrink-0 text-xs font-medium text-text-3">{group}</span>
              {items.map((a) => (
                <button key={a.skill} title={a.prompt} onClick={() => setText(a.prompt)}
                  className="rounded-full border border-border bg-surface px-2.5 py-1 text-[13px] text-text-2 transition-colors hover:border-border-strong hover:text-text">{a.label}</button>
              ))}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Composer({ value, onChange, onSend, onStop, busy, disabled, placeholder, autoFocus }: {
  value: string; onChange: (v: string) => void; onSend: () => void; onStop?: () => void; busy?: boolean; disabled?: boolean;
  placeholder?: string; autoFocus?: boolean;
}) {
  const key = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!busy && !disabled) onSend(); }
  };
  return (
    <div className="rounded-xl border border-border bg-surface shadow-card focus-within:border-accent focus-within:ring-3 focus-within:ring-[var(--ring)]">
      <textarea value={value} onChange={(e) => onChange(e.target.value)} onKeyDown={key} disabled={disabled} autoFocus={autoFocus} rows={2}
        placeholder={placeholder} className="block max-h-60 min-h-14 w-full resize-y rounded-t-xl bg-transparent px-3.5 py-3 text-sm placeholder:text-text-3 focus:outline-none disabled:opacity-60" />
      <div className="flex items-center justify-between px-2.5 pb-2">
        <span className="text-xs text-text-3">Enter to send · Shift+Enter for a new line</span>
        {busy && onStop ? <Button size="sm" variant="secondary" icon={<Square className="size-3 fill-current" />} onClick={onStop}>Stop</Button>
          : <Button size="sm" variant="primary" disabled={disabled || busy || !value.trim()} loading={busy && !onStop}
              icon={<ArrowUp className="size-3.5" />} onClick={onSend}>Send</Button>}
      </div>
    </div>
  );
}

/* ---------------- a conversation ---------------- */

function ThreadView({ threadId, canEdit, isLead, onOpenReview }: { threadId: string; canEdit: boolean; isLead: boolean; onOpenReview: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const t = useQuery({ queryKey: ["claude", threadId], queryFn: () => api.get<ThreadDetail>(`/claude/threads/${threadId}`),
    refetchInterval: (q) => (q.state.data && BUSY.has(q.state.data.status) ? 2500 : false) });
  const delta = useQuery<string>({ queryKey: ["claude", threadId, "delta"], queryFn: () => "", staleTime: Infinity, initialData: "" });
  const [text, setText] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const send = useMutation({
    mutationFn: (body: string) => api.post<ThreadDetail>(`/claude/threads/${threadId}/messages`, { text: body }),
    onSuccess: (d) => { setText(""); qc.setQueryData(["claude", threadId], d); qc.invalidateQueries({ queryKey: ["project", d.project_id, "threads"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const stop = useMutation({
    mutationFn: () => api.post(`/claude/threads/${threadId}/stop`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["claude", threadId] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const n = t.data?.messages.length ?? 0;
  // keep the newest message in view, scrolling only the conversation (never the page)
  useEffect(() => { const el = scroller.current; if (el) el.scrollTop = el.scrollHeight; }, [n, delta.data, t.data?.status]);
  if (!t.data) return <Skeleton className="h-96" />;
  const d = t.data;
  const busy = BUSY.has(d.status);
  const results = new Map(d.messages.filter((m) => m.role === "tool_result").map((m) => [m.body.id as string, m]));
  const approvals = new Map(d.approvals.map((a) => [a.id, a]));
  return (
    <Card className="flex h-[calc(100dvh-230px)] min-h-[480px] flex-col">
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Bot className="size-4 text-accent" />
        <p className="min-w-0 flex-1 truncate text-sm font-semibold">{d.title}</p>
        <span className="flex items-center gap-1 text-xs text-text-3"><CircleDollarSign className="size-3.5" />${d.cost_usd.toFixed(2)} · {d.turns} message{d.turns === 1 ? "" : "s"}</span>
      </div>
      <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {d.messages.map((m) => m.role === "tool_result" ? null : (
          <Fragment key={m.id}><Message m={m} result={m.role === "tool" ? results.get(m.body.id) : undefined}
            approval={m.role === "approval" ? approvals.get(m.body.approval_id) : undefined} isLead={isLead} threadId={threadId}
            onOpenReview={onOpenReview} live={busy} /></Fragment>
        ))}
        {busy && delta.data && <div className="max-w-[46rem] text-sm leading-relaxed text-text"><Markdown text={delta.data} /></div>}
        {busy && (
          <div className="flex items-center gap-2 text-[13px] text-text-3">
            <Loader2 className="size-3.5 animate-spin" />
            {d.status === "queued" ? "Waiting for a worker…" : d.status === "waiting" ? "Waiting for approval…" : "Claude is working…"}
          </div>
        )}
        {d.status === "failed" && d.last_error && (
          <div className="flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{d.last_error}</div>
        )}
      </div>
      <div className="border-t border-border p-3">
        <Composer value={text} onChange={setText} disabled={!canEdit} busy={busy || send.isPending} onStop={busy ? () => stop.mutate() : undefined}
          placeholder={canEdit ? "Ask for changes, a new version, exports…" : "Only editors can ask Claude"}
          onSend={() => { if (text.trim()) send.mutate(text.trim()); }} />
      </div>
    </Card>
  );
}

function Message({ m, result, approval, isLead, threadId, onOpenReview, live }: {
  m: AgentMsg; result?: AgentMsg; approval?: Approval; isLead: boolean; threadId: string; onOpenReview: () => void; live: boolean;
}) {
  const b = m.body;
  switch (m.role) {
    case "user":
      return (
        <div className="flex justify-end gap-2.5">
          <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-tr-md bg-accent px-3.5 py-2 text-sm text-accent-text">{b.text}</div>
          {m.author && <Avatar name={m.author.name} email={m.author.email} size={26} />}
        </div>
      );
    case "assistant":
      return <div className="max-w-[46rem] text-sm leading-relaxed text-text"><Markdown text={b.text} /></div>;
    case "tool":
      return <ToolRow m={m} result={result} live={live} />;
    case "approval":
      return <ApprovalCard a={approval} fallback={b} isLead={isLead} threadId={threadId} />;
    case "notice":
      return (
        <p className={clsx("flex items-center gap-1.5 text-[13px]", b.tone === "danger" ? "text-danger" : b.tone === "warning" ? "text-warning" : "text-text-3")}>
          {b.tone === "danger" ? <X className="size-3.5" /> : <AlertTriangle className="size-3.5" />}{b.text}
        </p>
      );
    case "output":
      return (
        <div className="rounded-xl border border-success/30 bg-success-soft/50 p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-success">Made in this message</p>
          <ul className="space-y-1.5">{(b.items as Record<string, any>[]).map((it, i) => (
            <li key={i} className="flex items-center gap-2 text-sm">
              {it.kind === "version" ? <Film className="size-4 text-success" /> : <FileText className="size-4 text-success" />}
              <span className="min-w-0 flex-1 truncate">{it.kind === "version" ? <><b>v{it.number}</b> · {it.name} <span className="text-text-3">{it.info}</span></> : it.name}</span>
              {it.kind === "version" && <Button size="sm" variant="ghost" onClick={onOpenReview}>Review</Button>}
            </li>))}</ul>
        </div>
      );
    case "result":
      return (
        <p className="border-t border-dashed border-border pt-2 text-xs text-text-3">
          {b.turns ?? 0} steps · {b.duration_ms ? `${Math.round(b.duration_ms / 1000)} s` : "–"}{b.cost != null && ` · $${Number(b.cost).toFixed(2)}`}
          {b.subtype && b.subtype !== "success" && <span className="text-warning"> · ended: {String(b.subtype).replace(/_/g, " ")}</span>}
        </p>
      );
    case "engine":
      return (
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-text-3"><Cpu className="size-3.5" />
          {(b.plugins as string[] | undefined)?.includes("video-studio") ? "video-studio plugin" : "plugin"} · {b.skills} skills · {b.agents} specialists · {b.model}
          {Object.entries((b.mcp ?? {}) as Record<string, string>).map(([k, v]) => <Badge key={k} tone={v === "connected" ? "success" : "warning"}>{k} {v}</Badge>)}
        </p>
      );
    case "error":
      return <div className="flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{b.text}</div>;
    default:
      return null;
  }
}

function ToolRow({ m, result, live }: { m: AgentMsg; result?: AgentMsg; live: boolean }) {
  const [open, setOpen] = useState(false);
  const b = m.body;
  const err = result?.body.error;
  return (
    <div className={clsx("max-w-[46rem] rounded-lg border text-[13px]", b.sub ? "ml-5 border-transparent" : "border-border bg-surface-2/40")}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left">
        {!result ? (live ? <Spinner className="size-3.5" /> : <Terminal className="size-3.5 text-text-3" />)
          : err ? <X className="size-3.5 text-danger" /> : <Check className="size-3.5 text-success" />}
        <span className={clsx("min-w-0 flex-1 truncate", b.name === "Bash" && "font-mono text-xs")}>{b.title || b.name}</span>
        {open ? <ChevronDown className="size-3.5 text-text-3" /> : <ChevronRight className="size-3.5 text-text-3" />}
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-2.5 py-2">
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-text-2">{JSON.stringify(b.input, null, 1)}</pre>
          {result && <pre className={clsx("max-h-72 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px]", err ? "text-danger" : "text-text-2")}>{result.body.text || "(no output)"}</pre>}
        </div>
      )}
    </div>
  );
}

function ApprovalCard({ a, fallback, isLead, threadId }: { a?: Approval; fallback: Record<string, any>; isLead: boolean; threadId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [note, setNote] = useState("");
  const decide = useMutation({
    mutationFn: (approve: boolean) => api.post<Approval>(`/claude/approvals/${a!.id}`, { approve, note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["claude", threadId] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const status = a?.status ?? "pending";
  const v = a ?? (fallback as unknown as Approval);
  return (
    <div className={clsx("max-w-[46rem] rounded-xl border p-3.5", status === "pending" ? "border-warning/50 bg-warning-soft/60" : "border-border bg-surface")}>
      <div className="flex items-start gap-2.5">
        <ShieldCheck className={clsx("mt-0.5 size-4 shrink-0", status === "pending" ? "text-warning" : "text-text-3")} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">{v.title || v.tool}
            {v.paid && <Badge tone="warning">Spends credits</Badge>}
            {status !== "pending" && <Badge tone={status === "approved" ? "success" : "neutral"}>{status}{a?.decided_by && ` by ${a.decided_by.name || a.decided_by.email}`}</Badge>}
          </p>
          <p className="mt-0.5 text-[13px] text-text-2">{v.reason}</p>
          {v.account && <p className="mt-1.5 text-[13px]"><span className="text-text-3">Account: </span><b>{v.account}</b></p>}
          {v.input && Object.keys(v.input).length > 0 && (
            <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-md bg-surface/70 px-2 py-1.5 font-mono text-[11px] text-text-2">{JSON.stringify(v.input, null, 1)}</pre>
          )}
          {a?.note && status !== "pending" && <p className="mt-1.5 text-[13px] text-text-2">“{a.note}”</p>}
          {status === "pending" && a && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Input className="h-8 min-w-0 flex-1 text-[13px]" placeholder="Note to Claude (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
              <Button size="sm" variant="ghost" loading={decide.isPending && decide.variables === false} onClick={() => decide.mutate(false)}>Decline</Button>
              <Button size="sm" variant="primary" disabled={!isLead} title={isLead ? "" : "A brand lead approves paid steps"}
                loading={decide.isPending && decide.variables === true} onClick={() => decide.mutate(true)}>Approve</Button>
            </div>
          )}
          {status === "pending" && !isLead && <p className="mt-1.5 text-xs text-text-3">A brand lead approves this. You can decline it.</p>}
        </div>
      </div>
    </div>
  );
}

/* ---------------- minimal, safe markdown (no HTML) ---------------- */

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const rx = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0, i = 0;
  for (const m of text.matchAll(rx)) {
    if (m.index! > last) out.push(text.slice(last, m.index));
    const t = m[0];
    out.push(t.startsWith("`") ? <code key={i++} className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[12px]">{t.slice(1, -1)}</code>
      : <strong key={i++}>{t.slice(2, -2)}</strong>);
    last = m.index! + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0, k = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) body.push(lines[i++]);
      i++;
      blocks.push(<pre key={k++} className="my-2 overflow-x-auto rounded-lg bg-surface-2 p-3 font-mono text-[12px]">{body.join("\n")}</pre>);
    } else if (/^\s*([-*]|\d+\.)\s/.test(line)) {
      const items: string[] = [];
      const ordered = /^\s*\d+\./.test(line);
      while (i < lines.length && /^\s*([-*]|\d+\.)\s/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s/, ""));
      const L = ordered ? "ol" : "ul";
      blocks.push(<L key={k++} className={clsx("my-1.5 space-y-0.5 pl-5", ordered ? "list-decimal" : "list-disc")}>{items.map((t, j) => <li key={j}>{inline(t)}</li>)}</L>);
    } else if (/^#{1,4}\s/.test(line)) {
      blocks.push(<p key={k++} className="mt-3 mb-1 font-semibold">{inline(line.replace(/^#+\s/, ""))}</p>);
      i++;
    } else if (!line.trim()) {
      i++;
    } else {
      const para: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|\s*([-*]|\d+\.)\s)/.test(lines[i])) para.push(lines[i++]);
      blocks.push(<p key={k++} className="my-1.5">{inline(para.join(" "))}</p>);
    }
  }
  return <>{blocks}</>;
}


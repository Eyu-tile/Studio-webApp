"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, Copy, KeyRound, Link2, Lock, LogIn, RefreshCw, Send, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, Dialog, Field, Input, Select, Skeleton, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, CATEGORY_LABEL } from "@/lib/format";
import type { Brand, ConnectLink, Connection, Provider } from "@/lib/types";

const ORDER = ["generation", "voice", "avatar", "ai", "footage", "stock"];

export function ConnectionsTab({ brand }: { brand: Brand }) {
  const isLead = brand.role === "lead";
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => api.get<Provider[]>("/providers"), staleTime: 3600_000 });
  const conns = useQuery({ queryKey: ["brand", brand.id, "connections"], queryFn: () => api.get<Connection[]>(`/brands/${brand.id}/connections`) });
  const [connect, setConnect] = useState<Provider | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const toast = useToast();
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const ok = q.get("connected"), err = q.get("oauth_error");
    if (ok) toast(`${ok[0].toUpperCase()}${ok.slice(1)} connected for ${brand.name}`, "success");
    if (err) toast(err, "danger");
    if (ok || err) { q.delete("connected"); q.delete("oauth_error"); window.history.replaceState(null, "", `${window.location.pathname}?${q}`); }
  }, [brand.name, toast]);
  if (!providers.data || !conns.data) return <Skeleton className="h-96" />;
  const byId = Object.fromEntries(conns.data.map((c) => [c.provider, c]));
  const groups = ORDER.map((cat) => [cat, providers.data.filter((p) => p.category === cat)] as const).filter(([, ps]) => ps.length);
  const connected = conns.data.filter((c) => c.status === "connected").length;
  return (
    <div className="space-y-6">
      <Card className="flex flex-wrap items-center gap-4 p-4">
        <span className="flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent"><ShieldCheck className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{connected} tool{connected === 1 ? "" : "s"} connected for {brand.name}</p>
          <p className="text-[13px] text-text-2">Keys are encrypted and only used for {brand.name}&apos;s jobs. Nobody can read a key back, not even admins.</p>
        </div>
        {isLead && <Button variant="primary" icon={<Send className="size-4" />} onClick={() => setLinkOpen(true)}>Send connect link</Button>}
      </Card>

      {groups.map(([cat, ps]) => (
        <section key={cat}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">{CATEGORY_LABEL[cat] ?? cat}</h3>
          <Card className="divide-y divide-border">
            {ps.map((p) => {
              const c = byId[p.id];
              const live = c?.status === "connected";
              return (
                <div key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <span className={clsx("flex size-9 shrink-0 items-center justify-center rounded-lg text-sm font-semibold",
                    live ? "bg-success-soft text-success" : "bg-surface-2 text-text-2")}>{p.name[0]}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{p.name} {p.paid && <span className="ml-1 text-xs font-normal text-text-3">paid</span>}</p>
                    <p className="truncate text-[13px] text-text-3">
                      {live ? <>{c.account_label || "Connected"}{c.last4 && ` · ••••${c.last4}`} · {c.connected_by} · checked {c.last_checked_at ? ago(c.last_checked_at) : "never"}</>
                        : c?.status === "error" ? <span className="text-danger">{c.last_error}</span>
                        : p.used_for}
                    </p>
                  </div>
                  {!p.available ? <Badge><Lock className="size-3" />Not available yet</Badge>
                    : live ? <Badge tone={c.verified ? "success" : "neutral"} dot>{c.verified ? "Verified" : "Saved"}</Badge>
                    : c?.status === "error" ? <Badge tone="danger" dot>Needs attention</Badge>
                    : c?.status === "revoked" ? <Badge>Removed</Badge> : null}
                  {c?.spend_cap_monthly != null && live && <Badge tone="accent">cap ${c.spend_cap_monthly}/mo</Badge>}
                  <ConnActions brandId={brand.id} provider={p} conn={c} isLead={isLead} canCheck={brand.role !== "viewer"} onConnect={() => setConnect(p)} />
                </div>
              );
            })}
          </Card>
        </section>
      ))}

      {isLead && <Links brand={brand} providers={providers.data} />}
      <ConnectDialog brandId={brand.id} provider={connect} existing={connect ? byId[connect.id] : undefined} onClose={() => setConnect(null)} />
      <LinkDialog brand={brand} providers={providers.data} open={linkOpen} onClose={() => setLinkOpen(false)} />
    </div>
  );
}

function ConnActions({ brandId, provider, conn, isLead, canCheck, onConnect }: {
  brandId: string; provider: Provider; conn?: Connection; isLead: boolean; canCheck: boolean; onConnect: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const refresh = () => qc.invalidateQueries({ queryKey: ["brand", brandId] });
  const check = useMutation({
    mutationFn: () => api.post<Connection>(`/brands/${brandId}/connections/${provider.id}/check`),
    onSuccess: (c) => { toast(c.status === "connected" ? `${provider.name}: working` : `${provider.name}: ${c.last_error}`, c.status === "connected" ? "success" : "danger"); refresh(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/brands/${brandId}/connections/${provider.id}`),
    onSuccess: () => { toast(`${provider.name} removed and its key deleted`, "success"); refresh(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const signIn = useMutation({
    mutationFn: () => api.post<{ url: string }>(`/brands/${brandId}/connections/${provider.id}/oauth`),
    onSuccess: (r) => { window.location.href = r.url; },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  if (!provider.available) return null;
  const live = conn && conn.status !== "revoked";
  if (provider.auth === "oauth") return (
    <div className="flex items-center gap-1">
      {live && canCheck && <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} loading={check.isPending} onClick={() => check.mutate()}>Check</Button>}
      {isLead && <Button size="sm" variant={live ? "secondary" : "primary"} icon={<LogIn className="size-3.5" />} loading={signIn.isPending}
        onClick={() => signIn.mutate()}>{live ? "Switch account" : `Sign in with ${provider.name}`}</Button>}
      {isLead && live && <button className="rounded-md p-1.5 text-text-3 hover:bg-danger-soft hover:text-danger" aria-label={`Remove ${provider.name}`}
        onClick={() => confirm(`Disconnect ${provider.name}? Claude can't use this account anymore.`) && remove.mutate()}><Trash2 className="size-4" /></button>}
    </div>
  );
  return (
    <div className="flex items-center gap-1">
      {live && canCheck && <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} loading={check.isPending} onClick={() => check.mutate()}>Check</Button>}
      {isLead && <Button size="sm" variant={live ? "secondary" : "primary"} icon={<KeyRound className="size-3.5" />} onClick={onConnect}>{live ? "Replace" : "Connect"}</Button>}
      {isLead && live && <button className="rounded-md p-1.5 text-text-3 hover:bg-danger-soft hover:text-danger" aria-label={`Remove ${provider.name}`}
        onClick={() => confirm(`Remove ${provider.name}? The key is deleted; jobs can't use it anymore.`) && remove.mutate()}><Trash2 className="size-4" /></button>}
    </div>
  );
}

function ConnectDialog({ brandId, provider, existing, onClose }: { brandId: string; provider: Provider | null; existing?: Connection; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [secret, setSecret] = useState("");
  const [cap, setCap] = useState("");
  useEffect(() => { setSecret(""); setCap(existing?.spend_cap_monthly != null ? String(existing.spend_cap_monthly) : ""); }, [provider, existing]);
  const save = useMutation({
    mutationFn: () => api.put<Connection>(`/brands/${brandId}/connections/${provider!.id}`,
      { secret, spend_cap_monthly: cap ? Number(cap) : null }),
    onSuccess: (c) => { toast(`${provider!.name} connected${c.verified ? `: ${c.account_label}` : ""}`, "success"); qc.invalidateQueries({ queryKey: ["brand", brandId] }); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Dialog open={!!provider} onClose={onClose} title={provider ? `Connect ${provider.name}` : ""}
      description={provider ? `${provider.used_for}. We check the key with a read-only call before saving it; a refused key is never stored.` : undefined}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={save.isPending} disabled={secret.trim().length < 8} onClick={() => save.mutate()}>Check and save</Button></>}>
      {provider && <>
        <Field label="API key" hint={<>Where to find it: {provider.how_to_get}</>}>
          <Input type="password" autoComplete="off" spellCheck={false} autoFocus value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="Paste the key" />
        </Field>
        {provider.paid && <Field label="Monthly spending cap (USD)" hint="Optional. Paid actions above it will need a lead's approval.">
          <Input type="number" min={0} value={cap} onChange={(e) => setCap(e.target.value)} placeholder="No cap" className="w-40" />
        </Field>}
      </>}
    </Dialog>
  );
}

function LinkDialog({ brand, providers, open, onClose }: { brand: Brand; providers: Provider[]; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const choosable = providers.filter((p) => p.available);
  const [picked, setPicked] = useState<string[]>([]);
  const [recipient, setRecipient] = useState("");
  const [message, setMessage] = useState("");
  const [days, setDays] = useState("7");
  const [made, setMade] = useState<ConnectLink | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => { if (open) { setPicked([]); setRecipient(""); setMessage(""); setDays("7"); setMade(null); setCopied(false); } }, [open]);
  const create = useMutation({
    mutationFn: () => api.post<ConnectLink>(`/brands/${brand.id}/connect-links`, { providers: picked, recipient, message, expires_days: Number(days) }),
    onSuccess: (l) => { setMade(l); qc.invalidateQueries({ queryKey: ["brand", brand.id, "links"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Dialog open={open} onClose={onClose} title={made ? "Connect link ready" : "Send a connect link"} width={520}
      description={made ? "Copy it now: for safety it is shown only once. Anyone with the link can add keys for these tools until it expires." :
        `The client opens it, sees ${brand.name}'s request, and pastes their own keys. No account needed; keys go straight into encrypted storage.`}
      footer={made ? <Button variant="primary" onClick={onClose}>Done</Button> :
        <><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" icon={<Link2 className="size-4" />} loading={create.isPending} disabled={!picked.length} onClick={() => create.mutate()}>Create link</Button></>}>
      {made ? (
        <div className="flex gap-2">
          <Input readOnly value={made.url ?? ""} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
          <Button icon={copied ? <Check className="size-4" /> : <Copy className="size-4" />} onClick={() => { navigator.clipboard?.writeText(made.url ?? ""); setCopied(true); }}>{copied ? "Copied" : "Copy"}</Button>
        </div>
      ) : (<>
        <Field label="Tools to ask for" group>
          <div className="grid grid-cols-2 gap-1.5">
            {choosable.map((p) => (
              <label key={p.id} className={clsx("flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-1.5 text-[13px]",
                picked.includes(p.id) ? "border-accent bg-accent-soft text-accent" : "border-border hover:bg-surface-2")}>
                <input type="checkbox" className="accent-[var(--accent)]" checked={picked.includes(p.id)}
                  onChange={(e) => setPicked(e.target.checked ? [...picked, p.id] : picked.filter((x) => x !== p.id))} />{p.name}
              </label>
            ))}
          </div>
        </Field>
        <div className="grid grid-cols-[1fr_120px] gap-3">
          <Field label="For"><Input value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="e.g. Maya at CaptureCards" /></Field>
          <Field label="Expires"><Select value={days} onChange={(e) => setDays(e.target.value)}>
            <option value="1">1 day</option><option value="3">3 days</option><option value="7">7 days</option><option value="14">14 days</option>
          </Select></Field>
        </div>
        <Field label="Message" hint="Shown to the client on the page."><Textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Hi Maya, could you connect your ElevenLabs account for the voiceovers?" /></Field>
      </>)}
    </Dialog>
  );
}

function Links({ brand, providers }: { brand: Brand; providers: Provider[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const names = Object.fromEntries(providers.map((p) => [p.id, p.name]));
  const links = useQuery({ queryKey: ["brand", brand.id, "links"], queryFn: () => api.get<ConnectLink[]>(`/brands/${brand.id}/connect-links`) });
  const revoke = useMutation({
    mutationFn: (id: string) => api.del(`/brands/${brand.id}/connect-links/${id}`),
    onSuccess: () => { toast("Link withdrawn", "success"); qc.invalidateQueries({ queryKey: ["brand", brand.id, "links"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const now = Date.now();
  const rows = (links.data ?? []).filter((l) => !l.revoked && +new Date(l.expires_at) > now);
  if (!rows.length) return null;
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">Open connect links</h3>
      <Card className="divide-y divide-border">
        {rows.map((l) => (
          <div key={l.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <Link2 className="size-4 text-text-3" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{l.recipient || "Connect link"} <span className="font-normal text-text-3">· {l.providers.map((p) => names[p] ?? p).join(", ")}</span></p>
              <p className="text-[13px] text-text-3">expires {new Date(l.expires_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })} · used {l.uses}×{l.last_used_at ? `, last ${ago(l.last_used_at)}` : ""}</p>
            </div>
            <Button size="sm" variant="ghost" onClick={() => revoke.mutate(l.id)}>Withdraw</Button>
          </div>
        ))}
      </Card>
    </section>
  );
}

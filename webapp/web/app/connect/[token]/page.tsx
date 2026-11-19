"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Lock, LogIn, ShieldCheck } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { Button, Card, Field, Input, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { PublicLink } from "@/lib/types";

export default function ConnectPage() {
  const { token } = useParams<{ token: string }>();
  const q = useQuery<PublicLink, ApiError>({ queryKey: ["connect", token], queryFn: () => api.get<PublicLink>(`/public/connect/${token}`), retry: false });
  return (
    <div className="min-h-screen px-4 py-10 sm:py-16" style={{ background: "radial-gradient(60rem 30rem at 50% -10%, var(--accent-soft), transparent 70%), var(--bg)" }}>
      <div className="mx-auto w-full max-w-[560px]">
        <div className="mb-8 flex items-center justify-center gap-2.5"><Logo /><span className="font-semibold tracking-tight">Studio</span></div>
        {q.isLoading ? <Skeleton className="h-80" /> : q.error ? (
          <Card className="p-8 text-center">
            <Lock className="mx-auto size-8 text-text-3" />
            <p className="mt-4 font-semibold">This link isn&apos;t active</p>
            <p className="mt-1.5 text-sm text-text-2">{q.error.message}</p>
          </Card>
        ) : <Body token={token} link={q.data!} />}
        <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-text-3"><ShieldCheck className="size-3.5" />Keys are encrypted at rest and only used for your projects. Nobody can view them after saving.</p>
      </div>
    </div>
  );
}

function Body({ token, link }: { token: string; link: PublicLink }) {
  const done = link.providers.filter((p) => p.connected).length;
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const ok = q.get("connected"), err = q.get("oauth_error");
    if (ok) setNotice({ ok: true, text: `${link.providers.find((p) => p.id === ok)?.name ?? ok} is connected. Thank you!` });
    if (err) setNotice({ ok: false, text: err });
    if (ok || err) window.history.replaceState(null, "", window.location.pathname);
  }, [link.providers]);
  return (
    <>
      <div className="mb-6 text-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-[13px] font-medium shadow-card">
          <span className="size-2.5 rounded-[3px]" style={{ background: link.brand_color }} />{link.brand_name}
        </span>
        <h1 className="mt-4 text-xl font-semibold tracking-tight">Connect your accounts</h1>
        <p className="mt-1.5 text-sm text-text-2">Your production team asked for {link.providers.length === 1 ? "one tool" : `${link.providers.length} tools`} so they can create with your own accounts. {done}/{link.providers.length} done.</p>
        {link.message && <p className="mx-auto mt-4 max-w-md rounded-xl bg-surface-2 px-4 py-3 text-left text-sm italic text-text-2">“{link.message}”</p>}
      </div>
      {notice && <p className={`mb-3 rounded-lg px-3 py-2 text-[13px] ${notice.ok ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>{notice.text}</p>}
      <div className="space-y-3">{link.providers.map((p) => <ProviderCard key={p.id} token={token} p={p} />)}</div>
      <p className="mt-4 text-center text-xs text-text-3">This link expires {new Date(link.expires_at).toLocaleDateString(undefined, { day: "numeric", month: "long" })}.</p>
    </>
  );
}

function ProviderCard({ token, p }: { token: string; p: PublicLink["providers"][number] }) {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [err, setErr] = useState("");
  const [editing, setEditing] = useState(!p.connected);
  const signIn = useMutation({
    mutationFn: () => api.post<{ url: string }>(`/public/connect/${token}/${p.id}/oauth`),
    onSuccess: (r) => { window.location.href = r.url; },
    onError: (e: Error) => setErr(e.message),
  });
  const save = useMutation({
    mutationFn: () => api.put<PublicLink>(`/public/connect/${token}/${p.id}`, { secret: key }),
    onSuccess: (d) => { qc.setQueryData(["connect", token], d); setKey(""); setErr(""); setEditing(false); },
    onError: (e: Error) => setErr(e.message),
  });
  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className={p.connected ? "flex size-9 shrink-0 items-center justify-center rounded-lg bg-success-soft text-success" : "flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-text-2"}>
          {p.connected ? <CheckCircle2 className="size-5" /> : <KeyRound className="size-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{p.name}</p>
          <p className="text-[13px] text-text-2">{p.connected ? `Connected${p.account_label ? `: ${p.account_label}` : ""}` : p.used_for}</p>
        </div>
        {p.connected && !editing && <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Replace</Button>}
      </div>
      {editing && p.auth === "oauth" && (
        <div className="mt-4 space-y-3">
          <p className="text-[13px] text-text-2">You&apos;ll sign in on {p.name}&apos;s own page and choose the account and workspace to use. We never see your password.</p>
          {err && <p className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">{err}</p>}
          <Button variant="primary" className="w-full" icon={<LogIn className="size-4" />} loading={signIn.isPending} onClick={() => signIn.mutate()}>Sign in with {p.name}</Button>
        </div>
      )}
      {editing && p.auth !== "oauth" && (
        <form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <Field label="API key" hint={<>Where to find it: {p.how_to_get}</>}>
            <Input type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKey(e.target.value)} placeholder="Paste your key" />
          </Field>
          {err && <p className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">{err}</p>}
          <Button type="submit" variant="primary" className="w-full" loading={save.isPending} disabled={key.trim().length < 8}>Check and connect</Button>
        </form>
      )}
    </Card>
  );
}

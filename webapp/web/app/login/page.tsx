"use client";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Logo } from "@/components/logo";
import { Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import type { AuthConfig } from "@/lib/types";

const ERRORS: Record<string, string> = {
  not_invited: "This email hasn't been invited yet. Ask an admin to add you.",
  invalid_token: "Sign-in could not be verified. Please try again.",
  sign_in_failed: "Sign-in was cancelled or expired. Please try again.",
  token_exchange_failed: "The sign-in provider did not respond. Please try again.",
  email_not_verified: "Your email address isn't verified with the sign-in provider.",
};

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: () => api.get<AuthConfig>("/auth/config") });
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(ERRORS[params.get("error") ?? ""] ?? "");
  const next = params.get("next") || "/";

  async function devLogin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await api.post("/auth/dev-login", { email, name });
      router.replace(next.startsWith("/") ? next : "/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-[380px]">
      <div className="mb-8 flex flex-col items-center text-center">
        <Logo size={40} />
        <h1 className="mt-5 text-xl font-semibold tracking-tight">Sign in to Studio</h1>
        <p className="mt-1.5 text-sm text-text-2">Editing, review and delivery for every brand.</p>
      </div>
      <div className="rounded-2xl border border-border bg-surface p-6 shadow-card">
        {error && <div className="mb-4 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger">{error}</div>}
        {cfg.data?.mode === "oidc" ? (
          <a href="/api/auth/oidc/login" className="block">
            <Button variant="primary" className="w-full" icon={<ArrowRight className="size-4" />}>
              Continue with {cfg.data.provider ?? "SSO"}
            </Button>
          </a>
        ) : (
          <form onSubmit={devLogin} className="space-y-4">
            <Field label="Work email"><Input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" /></Field>
            <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional" /></Field>
            <Button type="submit" variant="primary" className="w-full" loading={busy}>Sign in</Button>
            <p className="text-center text-xs text-text-3">Development sign-in. Production uses your company account (SSO).</p>
          </form>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4"
      style={{ background: "radial-gradient(60rem 30rem at 50% -10%, var(--accent-soft), transparent 70%), var(--bg)" }}>
      <Suspense><LoginForm /></Suspense>
    </div>
  );
}

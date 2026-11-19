"use client";
import clsx from "clsx";
import { Home, LogOut, Menu, Shield, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { Logo } from "./logo";
import { Avatar, Spinner } from "./ui";

export function Shell({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => { if (me.error?.status === 401) router.replace(`/login?next=${encodeURIComponent(path)}`); }, [me.error, router, path]);

  if (me.isLoading || me.error) {
    return <div className="flex h-screen items-center justify-center"><Spinner className="size-5" /></div>;
  }
  const user = me.data!;
  const signOut = async () => { await api.post("/auth/logout"); qc.clear(); router.replace("/login"); };
  const nav = (href: string, active: boolean, icon: React.ReactNode, label: string) => (
    <Link href={href} className={clsx("flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
      active ? "bg-surface-2 font-medium text-text" : "text-text-2 hover:bg-surface-2 hover:text-text")}>{icon}{label}</Link>
  );

  const sidebar = (
    <aside className="flex h-full w-64 flex-col border-r border-border bg-surface">
      <div className="flex h-14 items-center gap-2.5 px-4">
        <Logo />
        <span className="font-semibold tracking-tight">Studio</span>
        <button className="ml-auto rounded-md p-1 text-text-3 lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu"><X className="size-4" /></button>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-2">
        <div className="space-y-0.5">
          {nav("/", path === "/", <Home className="size-4" />, "Home")}
          {user.org_role === "admin" && nav("/admin", path.startsWith("/admin"), <Shield className="size-4" />, "Admin")}
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between px-2.5 text-xs font-medium text-text-3">
            <span>Brands</span>
            {user.org_role === "admin" && <Link href="/brands/new" className="hover:text-text" aria-label="New brand">+ New</Link>}
          </div>
          <div className="space-y-0.5">
            {user.brands.length === 0 && <p className="px-2.5 py-1 text-[13px] text-text-3">No brands yet</p>}
            {user.brands.map((b) => (
              <Link key={b.id} href={`/brands/${b.id}`}
                className={clsx("flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                  path.startsWith(`/brands/${b.id}`) ? "bg-surface-2 font-medium text-text" : "text-text-2 hover:bg-surface-2 hover:text-text")}>
                <span className="size-2.5 shrink-0 rounded-[4px]" style={{ background: b.color }} />
                <span className="truncate">{b.name}</span>
              </Link>
            ))}
          </div>
        </div>
      </nav>
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-2.5 rounded-lg px-1.5 py-1">
          <Avatar name={user.name} email={user.email} url={user.avatar_url} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{user.name || user.email}</p>
            <p className="truncate text-xs text-text-3">{user.org_role === "admin" ? "Admin" : "Member"}</p>
          </div>
          <button onClick={signOut} className="rounded-md p-1.5 text-text-3 hover:bg-surface-2 hover:text-text" title="Sign out" aria-label="Sign out">
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden lg:block">{sidebar}</div>
      {open && <div className="fixed inset-0 z-40 flex lg:hidden"><div className="shadow-pop">{sidebar}</div><div className="flex-1 bg-black/40" onClick={() => setOpen(false)} /></div>}
      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4 lg:hidden">
          <button onClick={() => setOpen(true)} className="rounded-md p-1.5 text-text-2" aria-label="Open menu"><Menu className="size-5" /></button>
          <Logo size={22} /><span className="font-semibold">Studio</span>
        </div>
        <div className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-8 sm:py-8">{children}</div>
      </main>
    </div>
  );
}

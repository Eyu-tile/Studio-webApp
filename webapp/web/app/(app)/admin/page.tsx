"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, UserPlus } from "lucide-react";
import { useState } from "react";
import { Avatar, Badge, Button, Card, Dialog, Empty, Field, Input, PageHeader, Select, Skeleton, Tabs, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { AuditEvent, OrgRole, User } from "@/lib/types";

type Tab = "users" | "audit";

export default function Admin() {
  const me = useMe().data!;
  const [tab, setTab] = useState<Tab>("users");
  if (me.org_role !== "admin") return <Empty icon={<ShieldAlert className="size-5" />} title="Admins only" body="Ask an admin if you need access." />;
  return (
    <>
      <PageHeader title="Admin" subtitle="People with access to Studio, and a record of everything that changed." />
      <Tabs value={tab} onChange={setTab} items={[{ value: "users", label: "People" }, { value: "audit", label: "Audit log" }]} />
      {tab === "users" ? <Users meId={me.id} /> : <Audit />}
    </>
  );
}

function Users({ meId }: { meId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: () => api.get<User[]>("/admin/users") });
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<OrgRole>("member");
  const invite = useMutation({
    mutationFn: () => api.post("/admin/users", { email, name, org_role: role }),
    onSuccess: () => { toast(`${email} invited`, "success"); setOpen(false); setEmail(""); setName(""); qc.invalidateQueries({ queryKey: ["admin"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<User> }) => api.patch(`/admin/users/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin"] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  if (!users.data) return <Skeleton className="h-64" />;
  return (
    <>
      <Card>
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="text-sm text-text-2">{users.data.length} people · admins manage brands, people and connections.</p>
          <Button size="sm" icon={<UserPlus className="size-3.5" />} onClick={() => setOpen(true)}>Invite</Button>
        </div>
        <div className="divide-y divide-border">
          {users.data.map((u) => (
            <div key={u.id} className="flex items-center gap-3 px-4 py-3">
              <Avatar name={u.name} email={u.email} url={u.avatar_url} size={32} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{u.name || u.email}{u.id === meId && <span className="ml-1.5 text-text-3">(you)</span>}</p>
                <p className="truncate text-[13px] text-text-3">{u.email} · {u.last_seen_at ? `seen ${ago(u.last_seen_at)}` : "never signed in"}</p>
              </div>
              {!u.active && <Badge tone="danger">Disabled</Badge>}
              <Select className="!h-8 w-28 text-[13px]" value={u.org_role} onChange={(e) => update.mutate({ id: u.id, body: { org_role: e.target.value as OrgRole } })}>
                <option value="member">Member</option><option value="admin">Admin</option>
              </Select>
              <Button size="sm" variant="ghost" disabled={u.id === meId} onClick={() => update.mutate({ id: u.id, body: { active: !u.active } })}>{u.active ? "Disable" : "Enable"}</Button>
            </div>
          ))}
        </div>
      </Card>
      <Dialog open={open} onClose={() => setOpen(false)} title="Invite someone" description="They sign in with their company account. Add them to brands afterwards."
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={invite.isPending} disabled={!email} onClick={() => invite.mutate()}>Send invite</Button></>}>
        <Field label="Email"><Input type="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Access"><Select value={role} onChange={(e) => setRole(e.target.value as OrgRole)}><option value="member">Member</option><option value="admin">Admin</option></Select></Field>
      </Dialog>
    </>
  );
}

const ACTION: Record<string, string> = {
  "auth.sign_in": "signed in", "auth.sign_out": "signed out", "brand.create": "created brand", "brand.update": "updated brand",
  "brand.member_add": "added member", "brand.member_role": "changed role of", "brand.member_remove": "removed member",
  "project.create": "created project", "project.update": "updated project", "asset.upload_start": "started uploading",
  "asset.upload_complete": "uploaded", "asset.delete": "deleted file", "job.render": "started a cut of", "job.transcribe": "transcribed in",
  "job.qa": "checked", "job.cancel": "canceled", "job.retry": "retried", "note.add": "left a note on", "note.update": "updated a note on",
  "user.invite": "invited", "user.update": "updated user",
};

function Audit() {
  const log = useQuery({ queryKey: ["admin", "audit"], queryFn: () => api.get<AuditEvent[]>("/admin/audit?limit=200"), refetchInterval: 15_000 });
  if (!log.data) return <Skeleton className="h-64" />;
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="border-b border-border text-left text-xs font-medium text-text-3">
          <th className="px-4 py-2.5 font-medium">When</th><th className="px-4 py-2.5 font-medium">Who</th><th className="px-4 py-2.5 font-medium">What</th><th className="px-4 py-2.5 font-medium">IP</th>
        </tr></thead>
        <tbody className="divide-y divide-border">
          {log.data.map((e) => (
            <tr key={e.id}>
              <td className="whitespace-nowrap px-4 py-2.5 text-[13px] text-text-2" title={new Date(e.at).toLocaleString()}>{ago(e.at)}</td>
              <td className="whitespace-nowrap px-4 py-2.5">{e.actor?.name || e.actor?.email || "system"}</td>
              <td className="px-4 py-2.5"><span className="text-text-2">{ACTION[e.action] ?? e.action}</span> <span className="font-medium">{e.target}</span></td>
              <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-text-3">{e.ip}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

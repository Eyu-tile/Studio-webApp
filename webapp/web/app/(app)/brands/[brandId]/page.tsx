"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, Plus, Trash2, UserPlus } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { ConnectionsTab } from "@/components/brand/connections";
import { LessonsTab } from "@/components/brand/lessons";
import { LibraryTab } from "@/components/brand/library";
import { ProductsTab } from "@/components/brand/products";
import { SetupTab } from "@/components/brand/setup";
import { SpendingCard } from "@/components/brand/spending";
import { ProjectCard } from "@/components/bits";
import { Avatar, Badge, Button, Card, Dialog, Empty, Field, Input, PageHeader, Select, Skeleton, Tabs, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, KIND_LABEL } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Brand, BrandRole, Member, Product, Project, Setup } from "@/lib/types";

type Tab = "setup" | "projects" | "products" | "library" | "connections" | "lessons" | "members" | "settings";
const ROLE_LABEL: Record<BrandRole, string> = { lead: "Lead", editor: "Editor", viewer: "Viewer" };

function BrandPage() {
  const { brandId } = useParams<{ brandId: string }>();
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "projects");
  const picked = useRef(!!params.get("tab"));
  useEffect(() => { const t = params.get("tab") as Tab | null; if (t) { picked.current = true; setTab(t); } }, [params]);   // sidebar links
  const setup = useQuery({ queryKey: ["brand", brandId, "setup"], queryFn: () => api.get<Setup>(`/brands/${brandId}/setup`) });
  useEffect(() => {     // a client still being set up opens on its checklist
    if (!picked.current && setup.data) { picked.current = true; if (setup.data.done < setup.data.total - 1) setTab("setup"); }
  }, [setup.data]);
  const [newOpen, setNewOpen] = useState(params.get("new") === "1");
  const brand = useQuery({ queryKey: ["brand", brandId], queryFn: () => api.get<Brand>(`/brands/${brandId}`) });
  const projects = useQuery({ queryKey: ["brand", brandId, "projects"], queryFn: () => api.get<Project[]>(`/brands/${brandId}/projects`) });
  const members = useQuery({ queryKey: ["brand", brandId, "members"], queryFn: () => api.get<Member[]>(`/brands/${brandId}/members`) });
  const products = useQuery({ queryKey: ["brand", brandId, "products"], queryFn: () => api.get<Product[]>(`/brands/${brandId}/products`) });

  if (brand.error) return <Empty icon={<FolderKanban className="size-5" />} title="Brand not found" body="It may have been removed, or you don't have access." />;
  if (!brand.data) return <Skeleton className="h-40" />;
  const b = brand.data;
  const canEdit = b.role === "lead" || b.role === "editor";

  return (
    <>
      <PageHeader
        breadcrumb={<><span className="size-2.5 rounded-[3px]" style={{ background: b.color }} /> Brand</>}
        title={b.name} subtitle={b.description || `${b.project_count} active projects · ${b.member_count} members`}
        actions={canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setNewOpen(true)}>New project</Button>} />
      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <Tabs value={tab} onChange={(t) => { picked.current = true; setTab(t); }} items={[
          { value: "setup", label: setup.data && setup.data.done < setup.data.total ? `Setup ${setup.data.done}/${setup.data.total}` : "Setup" },
          { value: "projects", label: "Projects", count: projects.data?.length },
          { value: "products", label: "Products", count: products.data?.length },
          { value: "library", label: "Library" },
          { value: "connections", label: "Connections" },
          { value: "lessons", label: "Lessons" },
          { value: "members", label: "Members", count: members.data?.length },
          ...(b.role === "lead" ? [{ value: "settings" as Tab, label: "Settings" }] : []),
        ]} />
      </div>
      {tab === "setup" && <SetupTab brandId={b.id} onGo={(t) => { if (t === "projects") { setTab("projects"); setNewOpen(true); } else setTab(t as Tab); }} />}
      {tab === "products" && <ProductsTab brandId={b.id} canEdit={canEdit} />}
      {tab === "library" && <LibraryTab brandId={b.id} canEdit={canEdit} isLead={b.role === "lead"} />}
      {tab === "connections" && <ConnectionsTab brand={b} />}
      {tab === "lessons" && <LessonsTab brandId={b.id} brandName={b.name} canEdit={canEdit} />}
      {tab === "projects" && (
        projects.isLoading ? <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-60" />)}</div>
        : projects.data?.length ? <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{projects.data.map((p) => <ProjectCard key={p.id} p={p} />)}</div>
        : <Empty icon={<FolderKanban className="size-5" />} title="No projects yet" body="Projects hold the footage, edits, versions and review notes for one video."
            action={canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setNewOpen(true)}>New project</Button>} />
      )}
      {tab === "members" && <Members brand={b} members={members.data ?? []} />}
      {tab === "settings" && <Settings brand={b} />}
      <NewProject brandId={b.id} open={newOpen} onClose={() => setNewOpen(false)} />
    </>
  );
}

function NewProject({ brandId, open, onClose }: { brandId: string; open: boolean; onClose: () => void }) {
  const router = useRouter();
  const toast = useToast();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("reel");
  const [brief, setBrief] = useState("");
  const [product, setProduct] = useState("");
  const products = useQuery({ queryKey: ["brand", brandId, "products"], queryFn: () => api.get<Product[]>(`/brands/${brandId}/products`), enabled: open });
  const create = useMutation({
    mutationFn: () => api.post<Project>(`/brands/${brandId}/projects`, { name, kind, brief, product_id: product || null }),
    onSuccess: (p) => { toast(`${p.name} created`, "success"); router.push(`/projects/${p.id}`); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  useEffect(() => { if (open) { setName(""); setBrief(""); setProduct(""); } }, [open]);
  return (
    <Dialog open={open} onClose={onClose} title="New project" description="One video: its footage, edits, versions and notes."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate()}>Create project</Button></>}>
      <Field label="Name"><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Scale & awareness, hook test" onKeyDown={(e) => e.key === "Enter" && name.trim() && create.mutate()} /></Field>
      <Field label="Format">
        <Select value={kind} onChange={(e) => setKind(e.target.value)}>
          {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </Field>
      {!!products.data?.length && (
        <Field label="Product" hint="Claude gets its card and packshots in every message of this project.">
          <Select value={product} onChange={(e) => setProduct(e.target.value)}>
            <option value="">None</option>
            {products.data.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </Field>
      )}
      <Field label="Brief" hint="Optional: goal, audience, length, references."><Textarea value={brief} onChange={(e) => setBrief(e.target.value)} /></Field>
    </Dialog>
  );
}

function Members({ brand, members }: { brand: Brand; members: Member[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const me = useMe().data!;
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<BrandRole>("editor");
  const lead = brand.role === "lead";
  const refresh = () => { qc.invalidateQueries({ queryKey: ["brand", brand.id] }); };
  const add = useMutation({
    mutationFn: () => api.post(`/brands/${brand.id}/members`, { email, role }),
    onSuccess: () => { toast(`${email} added`, "success"); setOpen(false); setEmail(""); refresh(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const change = useMutation({
    mutationFn: ({ id, role }: { id: string; role: BrandRole }) => api.patch(`/brands/${brand.id}/members/${id}`, { role }),
    onSuccess: refresh, onError: (e: Error) => toast(e.message, "danger"),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.del(`/brands/${brand.id}/members/${id}`),
    onSuccess: refresh, onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <>
      <Card>
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="text-sm text-text-2">Leads approve paid work and deliveries; editors edit and render; viewers watch and comment.</p>
          {lead && <Button size="sm" icon={<UserPlus className="size-3.5" />} onClick={() => setOpen(true)}>Add member</Button>}
        </div>
        <div className="divide-y divide-border">
          {members.map((m) => (
            <div key={m.id} className="flex items-center gap-3 px-4 py-3">
              <Avatar name={m.user.name} email={m.user.email} size={32} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{m.user.name || m.user.email}{m.user.id === me.id && <span className="ml-1.5 text-text-3">(you)</span>}</p>
                <p className="truncate text-[13px] text-text-3">{m.user.email} · added {ago(m.created_at)}</p>
              </div>
              {lead ? (
                <Select className="!h-8 w-28 text-[13px]" value={m.role} onChange={(e) => change.mutate({ id: m.id, role: e.target.value as BrandRole })}>
                  {Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              ) : <Badge>{ROLE_LABEL[m.role]}</Badge>}
              {lead && <button className="rounded-md p-1.5 text-text-3 hover:bg-danger-soft hover:text-danger" onClick={() => remove.mutate(m.id)} aria-label="Remove member"><Trash2 className="size-4" /></button>}
            </div>
          ))}
        </div>
      </Card>
      <Dialog open={open} onClose={() => setOpen(false)} title={`Add to ${brand.name}`} description="They can sign in once added. Leads can change roles anytime."
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={add.isPending} disabled={!email} onClick={() => add.mutate()}>Add member</Button></>}>
        <Field label="Email"><Input type="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" /></Field>
        <Field label="Role">
          <Select value={role} onChange={(e) => setRole(e.target.value as BrandRole)}>
            {Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
      </Dialog>
    </>
  );
}

function Settings({ brand }: { brand: Brand }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(brand.name);
  const [description, setDescription] = useState(brand.description);
  const save = useMutation({
    mutationFn: () => api.patch<Brand>(`/brands/${brand.id}`, { name, description }),
    onSuccess: () => { toast("Saved", "success"); qc.invalidateQueries({ queryKey: ["brand", brand.id] }); qc.invalidateQueries({ queryKey: ["me"] }); },  // includes setup
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <div className="space-y-6">
      <Card className="max-w-xl space-y-5 p-6">
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Description"><Textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <div className="flex justify-end"><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save changes</Button></div>
      </Card>
      <SpendingCard brand={brand} />
    </div>
  );
}

export default function Page() { return <Suspense><BrandPage /></Suspense>; }

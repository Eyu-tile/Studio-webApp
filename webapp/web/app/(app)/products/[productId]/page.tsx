"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Check, ChevronRight, Clapperboard, Package, Plus } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ProjectCard } from "@/components/bits";
import { ProductForm, Resources } from "@/components/brand/products";
import { Button, Dialog, Empty, Field, Input, PageHeader, Select, Skeleton, Tabs, Textarea, useToast } from "@/components/ui";
import { useWorkspace } from "@/components/workspace/context";
import { api } from "@/lib/api";
import { KIND_LABEL } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Product, ProductDetail, Project } from "@/lib/types";

type Tab = "ads" | "resources" | "details";

function ProductPage() {
  const { productId } = useParams<{ productId: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const me = useMe().data!;
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "ads");
  useEffect(() => { const t = params.get("tab") as Tab | null; if (t) setTab(t); }, [params]);
  const [newAd, setNewAd] = useState(false);
  const product = useQuery({ queryKey: ["product", productId], queryFn: () => api.get<ProductDetail>(`/products/${productId}`) });
  const ads = useQuery({ queryKey: ["product", productId, "ads"], queryFn: () => api.get<Project[]>(`/products/${productId}/ads`) });
  const { brandId, setBrandId } = useWorkspace();
  const bid = product.data?.brand_id;
  useEffect(() => { if (bid && bid !== brandId) setBrandId(bid); }, [bid, brandId, setBrandId]);
  const archive = useMutation({
    mutationFn: () => api.patch<Product>(`/products/${productId}`, { archived: true }),
    onSuccess: (p) => { qc.invalidateQueries({ queryKey: ["brand", p.brand_id] }); toast(`${p.name} archived: its ads keep their history`, "success"); router.push(`/brands/${p.brand_id}?tab=products`); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  if (product.error) return <Empty icon={<Package className="size-5" />} title="Product not found" body="It may have been archived, or you don't have access." />;
  if (!product.data) return <Skeleton className="h-60" />;
  const p = product.data;
  const brand = me.brands.find((b) => b.id === p.brand_id);
  const canEdit = brand?.role === "lead" || brand?.role === "editor";
  const steps = [
    { done: !!(p.pitch && (p.benefits.length || p.claims_ok.length || p.claims_no.length)), title: "Fill in the card", body: "What it is, benefits, approved and banned claims", tab: "details" as Tab },
    { done: p.files.length > 0, title: "Add its resources", body: "Packshots, briefs, research, reference ads", tab: "resources" as Tab },
    { done: (ads.data?.length ?? 0) > 0, title: "Make the first ad", body: "Each ad keeps its whole history", tab: "ads" as Tab },
  ];
  const left = steps.filter((s) => !s.done).length;
  return (
    <>
      <PageHeader
        breadcrumb={brand && <>
          <Link href={`/brands/${brand.id}?tab=products`} className="flex items-center gap-1.5 hover:text-text"><span className="size-2 rounded-[3px]" style={{ background: brand.color }} />{brand.name}</Link>
          <ChevronRight className="size-3.5" /><Link href={`/brands/${brand.id}?tab=products`} className="hover:text-text">Products</Link></>}
        title={<span className="flex items-center gap-3">
          {p.image_url ? <img src={p.image_url} alt="" className="size-10 rounded-lg border border-border bg-surface object-contain p-0.5" />
            : <span className="flex size-10 items-center justify-center rounded-lg bg-surface-2 text-text-3"><Package className="size-5" /></span>}
          {p.name}</span>}
        subtitle={p.pitch || "No description yet"}
        actions={<>
          {brand?.role === "lead" && <Button variant="ghost" icon={<Archive className="size-4" />} loading={archive.isPending}
            onClick={() => confirm(`Archive ${p.name}? It leaves the product list and new chats; its ads keep their history.`) && archive.mutate()}>Archive</Button>}
          {canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setNewAd(true)}>New ad</Button>}
        </>} />
      {left > 0 && canEdit && (
        <div className="mb-6 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {steps.map((s, i) => (
            <button key={s.title} onClick={() => (s.tab === "ads" && !s.done ? setNewAd(true) : setTab(s.tab))}
              className="flex items-start gap-3 rounded-xl border border-border bg-surface p-3.5 text-left shadow-card hover:border-border-strong">
              <span className={s.done ? "flex size-6 shrink-0 items-center justify-center rounded-full bg-success text-white" : "flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent"}>
                {s.done ? <Check className="size-3.5" /> : i + 1}</span>
              <span><span className="block text-sm font-medium">{s.title}</span><span className="block text-xs text-text-2">{s.body}</span></span>
            </button>
          ))}
        </div>
      )}
      <Tabs value={tab} onChange={setTab} items={[
        { value: "ads", label: "Ads", count: ads.data?.length },
        { value: "resources", label: "Resources", count: p.files.length },
        { value: "details", label: "Details" },
      ]} />
      {tab === "ads" && (
        !ads.data ? <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-60" />)}</div>
          : ads.data.length === 0 ? <Empty icon={<Clapperboard className="size-5" />} title={`No ads for ${p.name} yet`}
              body="Each ad is its own page: footage, Claude chats, versions, review notes, and a History tab with everything that happened to it."
              action={canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setNewAd(true)}>Make the first ad</Button>} />
          : <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{ads.data.map((x) => <ProjectCard key={x.id} p={x} />)}</div>
      )}
      {tab === "resources" && <Resources product={p} canEdit={canEdit} />}
      {tab === "details" && <ProductForm product={p} canEdit={canEdit} />}
      <NewAd product={p} open={newAd} onClose={() => setNewAd(false)} />
    </>
  );
}

function NewAd({ product, open, onClose }: { product: ProductDetail; open: boolean; onClose: () => void }) {
  const router = useRouter();
  const toast = useToast();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("ad");
  const [brief, setBrief] = useState("");
  useEffect(() => { if (open) { setName(""); setBrief(""); setKind("ad"); } }, [open]);
  const create = useMutation({
    mutationFn: () => api.post<Project>(`/brands/${product.brand_id}/projects`, { name: name.trim(), kind, brief, product_id: product.id }),
    onSuccess: (p) => router.push(`/projects/${p.id}`),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Dialog open={open} onClose={onClose} title={`New ad for ${product.name}`} description="Its footage, chats, versions and notes stay together, with the full history for later updates."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate()}>Create ad</Button></>}>
      <Field label="Name"><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. 3 a.m. feed hook, UGC" onKeyDown={(e) => e.key === "Enter" && name.trim() && create.mutate()} /></Field>
      <Field label="Format"><Select value={kind} onChange={(e) => setKind(e.target.value)}>
        {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </Select></Field>
      <Field label="Brief" hint="Goal, audience, angle, length, offer. Claude also reads the product's card and resources."><Textarea value={brief} onChange={(e) => setBrief(e.target.value)} /></Field>
    </Dialog>
  );
}

export default function Page() { return <Suspense><ProductPage /></Suspense>; }

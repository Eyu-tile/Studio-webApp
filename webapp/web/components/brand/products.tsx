"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Archive, Ban, CheckCircle2, Film, ImagePlus, Package, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Badge, Button, Card, Dialog, Empty, Field, Input, Select, Skeleton, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { bytes, duration, KIND_LABEL } from "@/lib/format";
import type { Product, ProductDetail, ProductFile } from "@/lib/types";

/** A brand's products: the cards Claude reads in every turn of a project that sells one. */
export function ProductsTab({ brandId, canEdit, isLead }: { brandId: string; canEdit: boolean; isLead: boolean }) {
  const list = useQuery({ queryKey: ["brand", brandId, "products"], queryFn: () => api.get<Product[]>(`/brands/${brandId}/products`) });
  const [open, setOpen] = useState<string | "new" | null>(null);
  if (!list.data) return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-64" />)}</div>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-[13px] text-text-2">What each product is, what may and may never be claimed, and its packshots. A project that sells a
          product gives Claude its card and packshots in every message; library clips whose Product field names it are listed on the card.</p>
        {canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setOpen("new")}>New product</Button>}
      </div>
      {list.data.length === 0 ? (
        <Empty icon={<Package className="size-5" />} title="No products yet"
          body="Add the client's products so Claude writes scripts, captions and generation prompts from the real facts and claims, with the real packaging."
          action={canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setOpen("new")}>Add the first product</Button>} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {list.data.map((p) => (
            <button key={p.id} onClick={() => setOpen(p.id)} className="group overflow-hidden rounded-xl border border-border bg-surface text-left shadow-card transition-all hover:border-border-strong hover:shadow-pop">
              <div className="aspect-[4/3] bg-surface-2">
                {p.image_url ? <img src={p.image_url} alt="" className="h-full w-full object-contain p-3 transition-transform duration-300 group-hover:scale-[1.03]" />
                  : <div className="flex h-full flex-col items-center justify-center gap-1.5 text-text-3"><Package className="size-7" /><span className="text-xs">No packshot yet</span></div>}
              </div>
              <div className="p-3.5">
                <p className="truncate font-medium">{p.name}</p>
                <p className="mt-0.5 line-clamp-2 min-h-[2.5em] text-[13px] text-text-2">{p.pitch || "No description yet"}</p>
                <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-3">
                  {p.price && <span className="text-text-2">{p.price}</span>}
                  <span>{p.file_count} file{p.file_count === 1 ? "" : "s"}</span>
                  <span>{p.clip_count} clip{p.clip_count === 1 ? "" : "s"}</span>
                  <span>{p.project_count} project{p.project_count === 1 ? "" : "s"}</span>
                  {p.claims_no.length > 0 && <span className="flex items-center gap-1 text-danger"><Ban className="size-3" />{p.claims_no.length} banned claim{p.claims_no.length === 1 ? "" : "s"}</span>}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
      <ProductDialog brandId={brandId} id={open} canEdit={canEdit} isLead={isLead} onClose={() => setOpen(null)} onCreated={(id) => setOpen(id)} />
    </div>
  );
}

const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);

function ProductDialog({ brandId, id, canEdit, isLead, onClose, onCreated }: {
  brandId: string; id: string | "new" | null; canEdit: boolean; isLead: boolean; onClose: () => void; onCreated: (id: string) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const isNew = id === "new";
  const detail = useQuery({ queryKey: ["product", id], queryFn: () => api.get<ProductDetail>(`/products/${id}`), enabled: !!id && !isNew });
  const [f, setF] = useState({ name: "", pitch: "", price: "", benefits: "", claims_ok: "", claims_no: "", links: "", notes: "" });
  useEffect(() => {
    if (isNew) setF({ name: "", pitch: "", price: "", benefits: "", claims_ok: "", claims_no: "", links: "", notes: "" });
    else if (detail.data) {
      const d = detail.data;
      setF({ name: d.name, pitch: d.pitch, price: d.price, benefits: d.benefits.join("\n"), claims_ok: d.claims_ok.join("\n"),
        claims_no: d.claims_no.join("\n"), links: d.links.join("\n"), notes: d.notes });
    }
  }, [isNew, detail.data, id]);
  const body = () => ({ name: f.name.trim(), pitch: f.pitch.trim(), price: f.price.trim(), benefits: lines(f.benefits),
    claims_ok: lines(f.claims_ok), claims_no: lines(f.claims_no), links: lines(f.links), notes: f.notes });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["brand", brandId] }); qc.invalidateQueries({ queryKey: ["product", id] }); };
  const save = useMutation({
    mutationFn: () => isNew ? api.post<Product>(`/brands/${brandId}/products`, body()) : api.patch<Product>(`/products/${id}`, body()),
    onSuccess: (p) => { refresh(); toast(isNew ? `${p.name} added: now add its packshots` : "Saved", "success"); if (isNew) onCreated(p.id); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const archive = useMutation({
    mutationFn: () => api.patch<Product>(`/products/${id}`, { archived: true }),
    onSuccess: () => { refresh(); toast("Archived: projects keep their history", "success"); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const d = detail.data;
  const ro = !canEdit;
  return (
    <Dialog open={!!id} onClose={onClose} width={880} title={isNew ? "New product" : d?.name ?? "Product"}
      description={isNew ? "Facts first: Claude only uses what's on this card." : "Claude reads this card, with the packshots below, in every message of a project that sells it."}
      footer={<>
        {!isNew && isLead && <Button variant="ghost" className="mr-auto" icon={<Archive className="size-4" />} loading={archive.isPending}
          onClick={() => confirm(`Archive ${d?.name}? It leaves the list and new chats; projects that sold it keep their history.`) && archive.mutate()}>Archive</Button>}
        <Button variant="ghost" onClick={onClose}>{ro ? "Close" : "Cancel"}</Button>
        {!ro && <Button variant="primary" loading={save.isPending} disabled={!f.name.trim()} onClick={() => save.mutate()}>{isNew ? "Add product" : "Save"}</Button>}
      </>}>
      {!isNew && !d ? <Skeleton className="h-80" /> : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px]">
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_160px]">
              <Field label="Name"><Input value={f.name} disabled={ro} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Night Serum" autoFocus={isNew} /></Field>
              <Field label="Price"><Input value={f.price} disabled={ro} onChange={(e) => setF({ ...f, price: e.target.value })} placeholder="$48 / 30 ml" /></Field>
            </div>
            <Field label="What it is" hint="One line: what it is and who it's for."><Input value={f.pitch} disabled={ro} onChange={(e) => setF({ ...f, pitch: e.target.value })} placeholder="Overnight repair serum for dry, sensitive skin" /></Field>
            <Field label="Key benefits" hint="One per line, in the client's words."><Textarea value={f.benefits} disabled={ro} onChange={(e) => setF({ ...f, benefits: e.target.value })} className="min-h-20" /></Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Claims we may make" hint="Approved by the client. One per line.">
                <Textarea value={f.claims_ok} disabled={ro} onChange={(e) => setF({ ...f, claims_ok: e.target.value })} className="min-h-24 border-success/30" placeholder="Dermatologist tested" /></Field>
              <Field label="Never claim or imply" hint="Legal, medical, competitor… One per line.">
                <Textarea value={f.claims_no} disabled={ro} onChange={(e) => setF({ ...f, claims_no: e.target.value })} className="min-h-24 border-danger/30" placeholder="Cures acne" /></Field>
            </div>
            <Field label="Links" hint="Product page, store, reviews. One per line."><Textarea value={f.links} disabled={ro} onChange={(e) => setF({ ...f, links: e.target.value })} className="min-h-14" /></Field>
            <Field label="Notes" hint="Audience, offers, how it's always shown, anything else Claude should know."><Textarea value={f.notes} disabled={ro} onChange={(e) => setF({ ...f, notes: e.target.value })} className="min-h-20" /></Field>
          </div>
          <div className="space-y-5">
            {isNew ? <p className="rounded-xl border border-dashed border-border-strong p-4 text-[13px] text-text-2">Packshots and logos can be added once the product is saved.</p>
              : d && <>
                <Files productId={d.id} files={d.files} canEdit={canEdit} onChange={refresh} />
                <section>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">In the library · {d.clips.length}</p>
                  {d.clips.length === 0 ? <p className="text-[13px] text-text-3">Clips whose Product field names “{d.name}” show up here.</p> : (
                    <div className="grid grid-cols-3 gap-1.5">
                      {d.clips.slice(0, 12).map((c) => (
                        <div key={c.id} title={c.name} className="relative aspect-square overflow-hidden rounded-lg bg-surface-2">
                          {c.thumb_url ? <img src={c.thumb_url} alt={c.name} className={clsx("h-full w-full object-cover", c.review === "banned" && "opacity-40 grayscale")} />
                            : <Film className="m-auto mt-[35%] size-5 text-text-3" />}
                          {c.duration ? <span className="absolute bottom-1 right-1 rounded bg-black/65 px-1 text-[10px] text-white tabular">{duration(c.duration)}</span> : null}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
                <section>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">Projects · {d.projects.length}</p>
                  {d.projects.length === 0 ? <p className="text-[13px] text-text-3">Pick this product when you start a chat or a project.</p>
                    : <ul className="space-y-1">{d.projects.map((x) => (
                      <li key={x.id}><Link href={`/projects/${x.id}`} className="flex items-center gap-2 rounded-lg px-2 py-1 text-[13px] hover:bg-surface-2">
                        <span className="min-w-0 flex-1 truncate">{x.name}</span><span className="text-xs text-text-3">{KIND_LABEL[x.kind] ?? x.kind}</span></Link></li>))}</ul>}
                </section>
              </>}
          </div>
        </div>
      )}
    </Dialog>
  );
}

function Files({ productId, files, canEdit, onChange }: { productId: string; files: ProductFile[]; canEdit: boolean; onChange: () => void }) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<ProductFile["kind"]>("packshot");
  const [busy, setBusy] = useState(0);
  const upload = async (list: FileList) => {
    for (const file of Array.from(list)) {
      setBusy((n) => n + 1);
      try {
        const mime = file.type || "application/octet-stream";
        const s = await api.post<{ file: ProductFile; upload_url: string }>(`/products/${productId}/files`, { filename: file.name, size: file.size, mime, kind });
        const put = await fetch(s.upload_url, { method: "PUT", body: file, headers: { "Content-Type": mime } });
        if (!put.ok) throw new Error(`storage refused the file (${put.status})`);
        await api.post(`/product-files/${s.file.id}/complete`);
        onChange();
      } catch (e) { toast(`${file.name}: ${(e as Error).message}`, "danger"); }
      finally { setBusy((n) => n - 1); }
    }
  };
  const del = useMutation({ mutationFn: (fid: string) => api.del(`/product-files/${fid}`), onSuccess: onChange, onError: (e: Error) => toast(e.message, "danger") });
  return (
    <section>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">Packshots and logos · {files.length}</p>
      <div className="grid grid-cols-3 gap-1.5">
        {files.map((x) => (
          <div key={x.id} className="group relative aspect-square overflow-hidden rounded-lg border border-border bg-surface-2" title={`${x.filename} · ${bytes(x.size)}`}>
            {x.url && x.mime.startsWith("image") ? <img src={x.url} alt={x.filename} className="h-full w-full object-contain p-1" />
              : <span className="flex h-full items-center justify-center px-1 text-center text-[10px] text-text-2 break-all">{x.filename}</span>}
            <span className="absolute left-1 top-1"><Badge tone={x.kind === "logo" ? "accent" : "neutral"} className="!px-1 !py-0 text-[10px]">{x.kind}</Badge></span>
            {canEdit && <button onClick={() => confirm(`Delete ${x.filename}?`) && del.mutate(x.id)} aria-label={`Delete ${x.filename}`}
              className="absolute right-1 top-1 rounded-md bg-surface/90 p-1 text-text-2 opacity-0 transition-opacity hover:text-danger group-hover:opacity-100 focus:opacity-100"><Trash2 className="size-3.5" /></button>}
          </div>
        ))}
        {canEdit && (
          <button onClick={() => input.current?.click()} disabled={busy > 0}
            className="flex aspect-square flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-border-strong text-text-2 hover:border-accent hover:text-accent disabled:opacity-60">
            <ImagePlus className="size-5" /><span className="text-[11px]">{busy ? "Uploading…" : "Add"}</span>
          </button>
        )}
      </div>
      {canEdit && (
        <div className="mt-2 flex items-center gap-2 text-[13px] text-text-2">
          <span>New files are</span>
          <Select className="!h-7 w-auto text-[13px]" value={kind} onChange={(e) => setKind(e.target.value as ProductFile["kind"])}>
            <option value="packshot">packshots</option><option value="logo">logos</option><option value="other">other</option>
          </Select>
        </div>
      )}
      <input ref={input} type="file" multiple accept="image/*,video/*,application/pdf" className="hidden" onChange={(e) => { if (e.target.files) upload(e.target.files); e.target.value = ""; }} />
      <p className="mt-2 flex items-start gap-1.5 text-xs text-text-3"><CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" />Claude uses these real images for product shots and end cards, and as references when it generates.</p>
    </section>
  );
}


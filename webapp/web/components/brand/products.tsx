"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Ban, Clapperboard, FileText, Film, Image as ImageIcon, Music, Package, Pencil, Plus, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button, Dialog, Empty, Field, Input, Skeleton, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { bytes } from "@/lib/format";
import type { Product, ProductDetail, ProductFile } from "@/lib/types";

/* ---------------- the brand's products ---------------- */

/** A brand's products. Each opens its own page: its ads, the resources Claude learns it from, its card. */
export function ProductsTab({ brandId, canEdit }: { brandId: string; canEdit: boolean }) {
  const list = useQuery({ queryKey: ["brand", brandId, "products"], queryFn: () => api.get<Product[]>(`/brands/${brandId}/products`) });
  const [adding, setAdding] = useState(false);
  if (!list.data) return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-64" />)}</div>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-[13px] text-text-2">Each product has its own page: the ads made for it, every one with its full history, and the
          resources Claude learns the product from (packshots, briefs, research, reference ads).</p>
        {canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>New product</Button>}
      </div>
      {list.data.length === 0 ? (
        <Empty icon={<Package className="size-5" />} title="No products yet"
          body="Add the client's first product, give Claude its resources, then make its ads."
          action={canEdit && <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add the first product</Button>} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {list.data.map((p) => (
            <Link key={p.id} href={`/products/${p.id}`} className="group flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-card transition-all hover:border-border-strong hover:shadow-pop">
              <div className="aspect-[4/3] bg-surface-2">
                {p.image_url ? <img src={p.image_url} alt="" className="h-full w-full object-contain p-3 transition-transform duration-300 group-hover:scale-[1.03]" />
                  : <div className="flex h-full flex-col items-center justify-center gap-1.5 text-text-3"><Package className="size-7" /><span className="text-xs">No packshot yet</span></div>}
              </div>
              <div className="flex flex-1 flex-col p-3.5">
                <p className="truncate font-medium">{p.name}</p>
                <p className="mt-0.5 line-clamp-2 text-[13px] text-text-2">{p.pitch || "No description yet"}</p>
                <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-3 text-xs text-text-3">
                  <span className="font-medium text-text-2">{p.project_count} ad{p.project_count === 1 ? "" : "s"}</span>
                  <span>{p.file_count} resource{p.file_count === 1 ? "" : "s"}</span>
                  {p.price && <span>{p.price}</span>}
                  {p.claims_no.length > 0 && <span className="flex items-center gap-1 text-danger"><Ban className="size-3" />{p.claims_no.length} banned claim{p.claims_no.length === 1 ? "" : "s"}</span>}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
      <NewProduct brandId={brandId} open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}

function NewProduct({ brandId, open, onClose }: { brandId: string; open: boolean; onClose: () => void }) {
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [pitch, setPitch] = useState("");
  useEffect(() => { if (open) { setName(""); setPitch(""); } }, [open]);
  const create = useMutation({
    mutationFn: () => api.post<Product>(`/brands/${brandId}/products`, { name: name.trim(), pitch: pitch.trim() }),
    onSuccess: (p) => { qc.invalidateQueries({ queryKey: ["brand", brandId] }); router.push(`/products/${p.id}?tab=resources`); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Dialog open={open} onClose={onClose} title="New product" description="Name it now; its resources, card and ads come next on its page."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate()}>Create product</Button></>}>
      <Field label="Name"><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Night Serum"
        onKeyDown={(e) => e.key === "Enter" && name.trim() && create.mutate()} /></Field>
      <Field label="What it is" hint="One line: what it is and who it's for. Optional."><Input value={pitch} onChange={(e) => setPitch(e.target.value)} placeholder="Overnight repair serum for dry, sensitive skin" /></Field>
    </Dialog>
  );
}

/* ---------------- the card ---------------- */

const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);

/** What Claude reads first: facts, approved and banned claims. */
export function ProductForm({ product, canEdit }: { product: ProductDetail; canEdit: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const from = (d: ProductDetail) => ({ name: d.name, pitch: d.pitch, price: d.price, benefits: d.benefits.join("\n"),
    claims_ok: d.claims_ok.join("\n"), claims_no: d.claims_no.join("\n"), links: d.links.join("\n"), notes: d.notes });
  const [f, setF] = useState(from(product));
  useEffect(() => setF(from(product)), [product]);
  const dirty = JSON.stringify(f) !== JSON.stringify(from(product));
  const save = useMutation({
    mutationFn: () => api.patch<Product>(`/products/${product.id}`, { name: f.name.trim(), pitch: f.pitch.trim(), price: f.price.trim(),
      benefits: lines(f.benefits), claims_ok: lines(f.claims_ok), claims_no: lines(f.claims_no), links: lines(f.links), notes: f.notes }),
    onSuccess: () => { toast("Saved: Claude reads the new card from the next message", "success"); qc.invalidateQueries({ queryKey: ["product", product.id] }); qc.invalidateQueries({ queryKey: ["brand", product.brand_id] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const ro = !canEdit;
  return (
    <div className="max-w-3xl space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_180px]">
        <Field label="Name"><Input value={f.name} disabled={ro} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Price"><Input value={f.price} disabled={ro} onChange={(e) => setF({ ...f, price: e.target.value })} placeholder="$48 / 30 ml" /></Field>
      </div>
      <Field label="What it is" hint="One line: what it is and who it's for."><Input value={f.pitch} disabled={ro} onChange={(e) => setF({ ...f, pitch: e.target.value })} /></Field>
      <Field label="Key benefits" hint="One per line, in the client's words."><Textarea value={f.benefits} disabled={ro} onChange={(e) => setF({ ...f, benefits: e.target.value })} className="min-h-20" /></Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Claims we may make" hint="Approved by the client. One per line.">
          <Textarea value={f.claims_ok} disabled={ro} onChange={(e) => setF({ ...f, claims_ok: e.target.value })} className="min-h-24 border-success/30" placeholder="Dermatologist tested" /></Field>
        <Field label="Never claim or imply" hint="Legal, medical, competitor… One per line.">
          <Textarea value={f.claims_no} disabled={ro} onChange={(e) => setF({ ...f, claims_no: e.target.value })} className="min-h-24 border-danger/30" placeholder="Cures acne" /></Field>
      </div>
      <Field label="Links" hint="Product page, store, reviews. One per line."><Textarea value={f.links} disabled={ro} onChange={(e) => setF({ ...f, links: e.target.value })} className="min-h-14" /></Field>
      <Field label="Notes" hint="Audience, offers, how it's always shown, anything else Claude should know."><Textarea value={f.notes} disabled={ro} onChange={(e) => setF({ ...f, notes: e.target.value })} className="min-h-24" /></Field>
      {canEdit && <div className="flex justify-end gap-2">
        {dirty && <Button variant="ghost" onClick={() => setF(from(product))}>Discard</Button>}
        <Button variant="primary" disabled={!dirty || !f.name.trim()} loading={save.isPending} onClick={() => save.mutate()}>Save card</Button>
      </div>}
    </div>
  );
}

/* ---------------- resources ---------------- */

type Kind = ProductFile["kind"];
const KINDS: { kind: Kind; title: string; hint: string; accept: string }[] = [
  { kind: "packshot", title: "Packshots", hint: "The real product: Claude uses these for product shots, end cards and as generation references.", accept: "image/*,video/*" },
  { kind: "logo", title: "Logos", hint: "Brand and product marks, ideally transparent PNG or SVG.", accept: "image/*" },
  { kind: "document", title: "Documents", hint: "Briefs, research, brand guidelines, claim sheets, reviews, past scripts. Claude reads them before planning.", accept: ".pdf,.txt,.md,.csv,.json,.docx,.pptx,.xlsx" },
  { kind: "reference", title: "Reference ads", hint: "Ads to learn structure and pacing from (theirs or competitors'). Studied, never copied.", accept: "video/*,image/*,audio/*" },
  { kind: "other", title: "Other", hint: "Music the client owns, voice samples, anything else.", accept: "*" },
];
const EXT_MIME: Record<string, string> = {
  md: "text/markdown", txt: "text/plain", csv: "text/csv", json: "application/json", pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
};
const mimeOf = (f: File) => f.type || EXT_MIME[f.name.split(".").pop()?.toLowerCase() ?? ""] || "application/octet-stream";

export function Resources({ product, canEdit }: { product: ProductDetail; canEdit: boolean }) {
  const qc = useQueryClient();
  const refresh = () => { qc.invalidateQueries({ queryKey: ["product", product.id] }); qc.invalidateQueries({ queryKey: ["brand", product.brand_id] }); };
  return (
    <div className="space-y-8">
      <p className="max-w-3xl text-[13px] text-text-2">Everything here goes into the workspace of every Claude message on this product&apos;s ads, with your note on what it is.
        Add a note to say how to use a file (“final claims, approved by legal”, “match this hook’s pacing”).</p>
      {KINDS.map((k) => <Section key={k.kind} {...k} product={product} files={product.files.filter((f) => f.kind === k.kind)} canEdit={canEdit} onChange={refresh} />)}
      <section>
        <h3 className="text-sm font-semibold">In the client&apos;s library · {product.clips.length}</h3>
        <p className="mb-3 text-[13px] text-text-2">Clips whose Product field names “{product.name}”. Set it on the Library tab.</p>
        {product.clips.length === 0 ? <p className="text-[13px] text-text-3">None yet.</p> : (
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6 lg:grid-cols-8">
            {product.clips.map((c) => (
              <div key={c.id} title={c.name} className="relative aspect-square overflow-hidden rounded-lg bg-surface-2">
                {c.thumb_url ? <img src={c.thumb_url} alt={c.name} className={clsx("h-full w-full object-cover", c.review === "banned" && "opacity-40 grayscale")} />
                  : <Film className="m-auto mt-[35%] size-5 text-text-3" />}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Section({ kind, title, hint, accept, product, files, canEdit, onChange }: {
  kind: Kind; title: string; hint: string; accept: string; product: ProductDetail; files: ProductFile[]; canEdit: boolean; onChange: () => void;
}) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(0);
  const upload = async (list: FileList) => {
    for (const file of Array.from(list)) {
      setBusy((n) => n + 1);
      try {
        const mime = mimeOf(file);
        const s = await api.post<{ file: ProductFile; upload_url: string }>(`/products/${product.id}/files`, { filename: file.name, size: file.size, mime, kind });
        const put = await fetch(s.upload_url, { method: "PUT", body: file, headers: { "Content-Type": mime } });
        if (!put.ok) throw new Error(`storage refused the file (${put.status})`);
        await api.post(`/product-files/${s.file.id}/complete`);
        onChange();
      } catch (e) { toast(`${file.name}: ${(e as Error).message}`, "danger"); }
      finally { setBusy((n) => n - 1); }
    }
  };
  const visual = kind === "packshot" || kind === "logo";
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div><h3 className="text-sm font-semibold">{title} · {files.length}</h3><p className="text-[13px] text-text-2">{hint}</p></div>
        {canEdit && <Button size="sm" icon={<Upload className="size-3.5" />} loading={busy > 0} onClick={() => input.current?.click()}>Add {title.toLowerCase()}</Button>}
        <input ref={input} type="file" multiple accept={accept} className="hidden" onChange={(e) => { if (e.target.files) upload(e.target.files); e.target.value = ""; }} />
      </div>
      {files.length === 0 ? (
        canEdit ? <button onClick={() => input.current?.click()} className="w-full rounded-xl border border-dashed border-border-strong px-4 py-6 text-[13px] text-text-3 hover:border-accent hover:text-accent">
          Nothing yet. Click to add {title.toLowerCase()}.</button>
          : <p className="text-[13px] text-text-3">None yet.</p>
      ) : visual ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">{files.map((f) => <Tile key={f.id} f={f} canEdit={canEdit} onChange={onChange} />)}</div>
      ) : (
        <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">{files.map((f) => <Row key={f.id} f={f} canEdit={canEdit} onChange={onChange} />)}</div>
      )}
    </section>
  );
}

function useFileActions(f: ProductFile, onChange: () => void) {
  const toast = useToast();
  const del = useMutation({ mutationFn: () => api.del(`/product-files/${f.id}`), onSuccess: onChange, onError: (e: Error) => toast(e.message, "danger") });
  const note = useMutation({ mutationFn: (n: string) => api.patch(`/product-files/${f.id}`, { note: n }), onSuccess: onChange, onError: (e: Error) => toast(e.message, "danger") });
  const editNote = () => { const n = prompt(`What is ${f.filename}, and how should Claude use it?`, f.note); if (n != null) note.mutate(n); };
  return { remove: () => confirm(`Delete ${f.filename}?`) && del.mutate(), editNote };
}

function Tile({ f, canEdit, onChange }: { f: ProductFile; canEdit: boolean; onChange: () => void }) {
  const a = useFileActions(f, onChange);
  return (
    <div className="group">
      <div className="relative aspect-square overflow-hidden rounded-xl border border-border bg-surface-2">
        {f.url && f.mime.startsWith("image") ? <img src={f.url} alt={f.filename} className="h-full w-full object-contain p-2" />
          : f.url && f.mime.startsWith("video") ? <video src={`${f.url}#t=0.5`} muted preload="metadata" className="h-full w-full object-cover" />
          : <FileText className="m-auto mt-[38%] size-6 text-text-3" />}
        {canEdit && <div className="absolute right-1.5 top-1.5 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <button onClick={a.editNote} aria-label={`Note on ${f.filename}`} className="rounded-md bg-surface/90 p-1 text-text-2 hover:text-text"><Pencil className="size-3.5" /></button>
          <button onClick={a.remove} aria-label={`Delete ${f.filename}`} className="rounded-md bg-surface/90 p-1 text-text-2 hover:text-danger"><Trash2 className="size-3.5" /></button>
        </div>}
      </div>
      <p className="mt-1.5 truncate text-xs font-medium" title={f.filename}>{f.filename}</p>
      <p className="truncate text-xs text-text-3" title={f.note}>{f.note || bytes(f.size)}</p>
    </div>
  );
}

function Row({ f, canEdit, onChange }: { f: ProductFile; canEdit: boolean; onChange: () => void }) {
  const a = useFileActions(f, onChange);
  const Icon = f.mime.startsWith("video") ? Clapperboard : f.mime.startsWith("audio") ? Music : f.mime.startsWith("image") ? ImageIcon : FileText;
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <Icon className="size-4 shrink-0 text-text-3" />
      <div className="min-w-0 flex-1">
        <a href={f.url ?? undefined} target="_blank" rel="noopener" className="block truncate text-sm font-medium hover:underline">{f.filename}</a>
        <p className="truncate text-xs text-text-3">{f.note ? <span className="text-text-2">{f.note}</span> : "No note yet"} · {bytes(f.size)}</p>
      </div>
      {canEdit && <>
        <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" />} onClick={a.editNote}>{f.note ? "Edit note" : "Add note"}</Button>
        <button onClick={a.remove} aria-label={`Delete ${f.filename}`} className="rounded-md p-1.5 text-text-3 hover:bg-danger-soft hover:text-danger"><Trash2 className="size-4" /></button>
      </>}
    </div>
  );
}


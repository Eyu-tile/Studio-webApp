"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Card, Field, Input, PageHeader, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import type { Brand } from "@/lib/types";

const COLORS = ["#4f46e5", "#2563eb", "#0891b2", "#059669", "#65a30d", "#d97706", "#dc2626", "#db2777", "#7c3aed", "#52525b"];

export default function NewBrand() {
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState(COLORS[0]);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const b = await api.post<Brand>("/brands", { name, description, color });
      await qc.invalidateQueries({ queryKey: ["me"] });
      toast(`${b.name} created`, "success");
      router.push(`/brands/${b.id}`);
    } catch (err) {
      toast((err as Error).message, "danger");
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl">
      <PageHeader title="New brand" subtitle="A brand is one client library: its projects, footage, lessons and connections." />
      <Card className="p-6">
        <form onSubmit={submit} className="space-y-5">
          <Field label="Name"><Input required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. CaptureCards" /></Field>
          <Field label="Description" hint="Optional: what this client is, tone, anything editors should know.">
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <Field label="Colour" group>
            <div className="flex flex-wrap gap-2">
              {COLORS.map((c) => (
                <button type="button" key={c} onClick={() => setColor(c)} aria-label={c}
                  className="size-7 rounded-lg ring-offset-2 ring-offset-surface transition" style={{ background: c, boxShadow: color === c ? `0 0 0 2px var(--surface), 0 0 0 4px ${c}` : undefined }} />
              ))}
            </div>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => router.back()}>Cancel</Button>
            <Button type="submit" variant="primary" loading={busy}>Create brand</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

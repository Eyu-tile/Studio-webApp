"use client";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Brand } from "@/lib/types";

/** What the shell remembers per person: the brand in focus (null = all brands) and which panels are open. Stored in
 *  the browser only: a convenience, never a permission (the API checks every brand). */
interface Workspace {
  brandId: string | null; setBrandId: (id: string | null) => void;
  sidebar: boolean; setSidebar: (open: boolean) => void;
  gallery: boolean; setGallery: (open: boolean) => void;
}
const Ctx = createContext<Workspace | null>(null);

function stored<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v == null ? fallback : (JSON.parse(v) as T); } catch { return fallback; }
}
function save(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: keep it for this visit only */ }
}

export function WorkspaceProvider({ brands, children }: { brands: Brand[]; children: ReactNode }) {
  const [brandId, setBrand] = useState<string | null>(null);
  const [sidebar, setSide] = useState(true);
  const [gallery, setGal] = useState(true);
  useEffect(() => {
    setBrand(stored<string | null>("studio.brand", null));
    setSide(stored("studio.sidebar", true));
    setGal(stored("studio.gallery", true));
  }, []);
  // a brand you no longer belong to is forgotten
  useEffect(() => { if (brandId && !brands.some((b) => b.id === brandId)) setBrand(null); }, [brands, brandId]);
  // opening a brand's page puts that brand in focus
  const path = usePathname();
  useEffect(() => {
    const m = path.match(/^\/brands\/([0-9a-f-]{36})/);
    if (m && brands.some((b) => b.id === m[1])) { setBrand(m[1]); save("studio.brand", m[1]); }
  }, [path, brands]);
  const setBrandId = useCallback((id: string | null) => { setBrand(id); save("studio.brand", id); }, []);
  const setSidebar = useCallback((v: boolean) => { setSide(v); save("studio.sidebar", v); }, []);
  const setGallery = useCallback((v: boolean) => { setGal(v); save("studio.gallery", v); }, []);
  return <Ctx.Provider value={{ brandId, setBrandId, sidebar, setSidebar, gallery, setGallery }}>{children}</Ctx.Provider>;
}

export function useWorkspace(): Workspace {
  const w = useContext(Ctx);
  if (!w) throw new Error("useWorkspace outside WorkspaceProvider");
  return w;
}

/** `?brand_id=` for the workspace endpoints, or "" for every brand. */
export const brandQuery = (id: string | null, first = true) => (id ? `${first ? "?" : "&"}brand_id=${id}` : "");

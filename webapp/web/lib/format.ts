export function duration(s?: number | null): string {
  if (s == null || !isFinite(s)) return "–";
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
                 : `${m}:${String(sec).padStart(2, "0")}`;
}

export function timecode(s: number): string {
  const m = Math.floor(s / 60), sec = s - m * 60;
  return `${m}:${sec.toFixed(1).padStart(4, "0")}`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const u = ["KB", "MB", "GB", "TB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return `${n.toFixed(n < 10 ? 1 : 0)} ${u[i]}`;
}

export function ago(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 45) return "just now";
  if (d < 3600) return `${Math.round(d / 60)} min ago`;
  if (d < 86400) return `${Math.round(d / 3600)} h ago`;
  if (d < 86400 * 7) return `${Math.round(d / 86400)} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function initials(name: string, email = ""): string {
  const src = name || email;
  const p = src.split(/[\s@._-]+/).filter(Boolean);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase() || "?";
}

export const KIND_LABEL: Record<string, string> = {
  reel: "Reel", short: "Short", tiktok: "TikTok", youtube: "YouTube", ad: "Ad", podcast: "Podcast",
  "talking-head": "Talking head", montage: "Montage", other: "Other",
};

export const JOB_LABEL: Record<string, string> = {
  ingest: "Process upload", transcribe: "Transcribe", render: "Render", qa: "Quality check", library_scan: "Learn library",
  agent_turn: "Claude",
};

export const PROVIDER_LABEL: Record<string, string> = {
  gdrive: "Google Drive", frameio: "Frame.io", dropbox: "Dropbox", onedrive: "OneDrive", web: "Web page", direct: "Direct link",
};

export const CATEGORY_LABEL: Record<string, string> = {
  generation: "AI generation", voice: "Voice", avatar: "Avatars", ai: "AI services", footage: "Footage sources", stock: "Stock libraries",
};

/** "claude-opus-5-5" -> "Opus 5.5" (a dated id's date is dropped). */
export function modelName(id: string): string {
  const parts = id.replace(/^claude-/, "").replace(/\[.*\]$/, "").split("-").filter((p) => !/^\d{8}$/.test(p));
  const words = parts.filter((p) => !/^\d+$/.test(p)).map((w) => w[0].toUpperCase() + w.slice(1));
  const version = parts.filter((p) => /^\d+$/.test(p)).join(".");
  return [words.join(" "), version].filter(Boolean).join(" ") || id;
}

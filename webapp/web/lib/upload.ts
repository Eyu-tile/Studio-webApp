// Direct-to-storage uploads: the API signs S3 multipart parts, the browser PUTs them (4 at a time) and reports
// progress; any size, and a failed part is retried without restarting the file.
import { api } from "./api";
import type { Asset } from "./types";

interface Started { asset_id: string; part_size: number; parts: Record<string, string> }

function putPart(url: string, blob: Blob, onBytes: (n: number) => void, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    let last = 0;
    xhr.upload.onprogress = (e) => { onBytes(e.loaded - last); last = e.loaded; };
    xhr.onload = () => {
      const etag = xhr.getResponseHeader("ETag");
      if (xhr.status >= 200 && xhr.status < 300 && etag) resolve(etag);
      else reject(new Error(etag ? `part upload failed (${xhr.status})` : "storage did not return an ETag (check bucket CORS)"));
    };
    xhr.onerror = () => reject(new Error("network error during upload"));
    signal.addEventListener("abort", () => { xhr.abort(); reject(new DOMException("aborted", "AbortError")); });
    xhr.send(blob);
  });
}

export async function uploadFile(projectId: string, file: File, onProgress: (fraction: number) => void,
                                 signal: AbortSignal): Promise<Asset> {
  const start = await api.post<Started>(`/projects/${projectId}/uploads`, {
    filename: file.name, size: file.size, mime: file.type || "application/octet-stream",
  });
  const count = Math.max(1, Math.ceil(file.size / start.part_size));
  const urls: Record<number, string> = Object.fromEntries(Object.entries(start.parts).map(([k, v]) => [Number(k), v]));
  const etags: { part_number: number; etag: string }[] = [];
  let sent = 0;
  const queue = Array.from({ length: count }, (_, i) => i + 1);
  async function urlFor(n: number) {
    if (!urls[n]) {
      const batch = Array.from({ length: Math.min(20, count - n + 1) }, (_, i) => n + i);
      Object.assign(urls, Object.fromEntries(Object.entries(await api.post<Record<string, string>>(`/assets/${start.asset_id}/parts`, { parts: batch })).map(([k, v]) => [Number(k), v])));
    }
    return urls[n];
  }
  async function workerLoop() {
    while (queue.length) {
      const n = queue.shift()!;
      const blob = file.slice((n - 1) * start.part_size, Math.min(n * start.part_size, file.size));
      for (let attempt = 1; ; attempt++) {
        let partSent = 0;
        try {
          const etag = await putPart(await urlFor(n), blob, (b) => { partSent += b; sent += b; onProgress(sent / file.size); }, signal);
          etags.push({ part_number: n, etag });
          break;
        } catch (e) {
          sent -= partSent;
          if ((e as Error).name === "AbortError" || attempt >= 3) throw e;
          delete urls[n];
        }
      }
    }
  }
  try {
    await Promise.all(Array.from({ length: Math.min(4, count) }, workerLoop));
  } catch (e) {
    await api.post(`/assets/${start.asset_id}/abort`).catch(() => undefined);
    throw e;
  }
  return api.post<Asset>(`/assets/${start.asset_id}/complete`, { parts: etags });
}

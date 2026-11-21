"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, ApiError } from "./api";
import type { Me, ThreadDetail } from "./types";

export function useMe() {
  return useQuery<Me, ApiError>({ queryKey: ["me"], queryFn: () => api.get<Me>("/auth/me"), retry: false, staleTime: 60_000 });
}

/** Live project events (jobs, assets, versions, notes) over SSE; each event refreshes the matching queries. */
export function useProjectEvents(projectId: string) {
  const qc = useQueryClient();
  useEffect(() => {
    const es = new EventSource(`/api/projects/${projectId}/events`);
    const refresh = (keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: ["project", projectId, k] }));
    es.addEventListener("job", (e) => {
      const j = JSON.parse((e as MessageEvent).data);
      qc.setQueryData(["project", projectId, "jobs"], (old: unknown) =>
        Array.isArray(old) ? old.map((x) => (x.id === j.id ? { ...x, ...j } : x)) : old);
      if (j.status !== "running") refresh(["jobs", "assets", "versions", "summary", "history"]);
    });
    es.addEventListener("asset", () => refresh(["assets", "summary", "outputs"]));
    es.addEventListener("version", () => refresh(["versions", "summary", "jobs", "history"]));
    es.addEventListener("note", () => refresh(["notes", "summary", "history"]));
    // Claude conversations: messages append live, text streams in as it is written, status changes refresh the list
    const data = (e: Event) => JSON.parse((e as MessageEvent).data);
    es.addEventListener("agent_message", (e) => {
      const m = data(e);
      qc.setQueryData(["claude", m.thread_id], (old: ThreadDetail | undefined) =>
        old && !old.messages.some((x) => x.id === m.id)
          ? { ...old, messages: [...old.messages, { id: m.id, seq: m.seq, role: m.role, body: m.body, created_at: new Date().toISOString(), author: null }] }
          : old);
      if (m.role === "assistant") qc.setQueryData(["claude", m.thread_id, "delta"], "");
      if (m.role === "approval") qc.invalidateQueries({ queryKey: ["claude", m.thread_id] });
    });
    es.addEventListener("agent_delta", (e) => {
      const d = data(e);
      qc.setQueryData(["claude", d.thread_id, "delta"], (old: string | undefined) => (old ?? "") + d.text);
    });
    es.addEventListener("agent_thread", (e) => {
      const d = data(e);
      qc.setQueryData(["claude", d.thread_id], (old: ThreadDetail | undefined) => (old ? { ...old, status: d.status } : old));
      if (d.status === "idle" || d.status === "failed") {
        qc.setQueryData(["claude", d.thread_id, "delta"], "");
        qc.invalidateQueries({ queryKey: ["claude", d.thread_id] });
      }
      refresh(["threads", "history"]);
    });
    es.addEventListener("agent_approval", (e) => qc.invalidateQueries({ queryKey: ["claude", data(e).thread_id] }));
    return () => es.close();
  }, [projectId, qc]);
}

/** Live brand events (library learning): refresh the library queries when anything changes. */
export function useBrandEvents(brandId: string) {
  const qc = useQueryClient();
  useEffect(() => {
    const es = new EventSource(`/api/brands/${brandId}/events`);
    const refresh = () => qc.invalidateQueries({ queryKey: ["brand", brandId, "library"] });
    es.addEventListener("job", refresh);
    es.addEventListener("library", () => { refresh(); qc.invalidateQueries({ queryKey: ["brand", brandId, "setup"] }); });
    return () => es.close();
  }, [brandId, qc]);
}

"use client";
import { useQuery } from "@tanstack/react-query";
import { Activity, Clapperboard, FolderKanban, MessageSquare, Plus } from "lucide-react";
import Link from "next/link";
import { JobLine, ProjectCard, Stat } from "@/components/bits";
import { Button, Card, Empty, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Job, Project } from "@/lib/types";

interface Dash { active_projects: number; renders_7d: number; open_notes: number; running_jobs: number; recent_jobs: (Job & { project_name: string })[] }

export default function Home() {
  const me = useMe().data!;
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dash>("/dashboard"), refetchInterval: 10_000 });
  const recent = useQuery({ queryKey: ["recent"], queryFn: () => api.get<Project[]>("/projects/recent?limit=6") });
  const brands = Object.fromEntries(me.brands.map((b) => [b.id, b]));
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <>
      <PageHeader title={`${greet}, ${(me.name || me.email).split(" ")[0]}`} subtitle="Here's what's happening across your brands."
        actions={me.brands.length > 0 && <Link href={`/brands/${me.brands[0].id}?new=1`}><Button variant="primary" icon={<Plus className="size-4" />}>New project</Button></Link>} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {dash.data ? (<>
          <Stat label="Active projects" value={dash.data.active_projects} icon={<FolderKanban className="size-4" />} />
          <Stat label="Renders this week" value={dash.data.renders_7d} icon={<Clapperboard className="size-4" />} />
          <Stat label="Open review notes" value={dash.data.open_notes} icon={<MessageSquare className="size-4" />} />
          <Stat label="Jobs running" value={dash.data.running_jobs} icon={<Activity className="size-4" />} />
        </>) : [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[92px]" />)}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-[1fr_360px]">
        <section>
          <h2 className="mb-3 text-sm font-semibold">Recent projects</h2>
          {recent.isLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-60" />)}</div>
          ) : recent.data?.length ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {recent.data.map((p) => <ProjectCard key={p.id} p={p} brandName={brands[p.brand_id]?.name} brandColor={brands[p.brand_id]?.color} />)}
            </div>
          ) : (
            <Empty icon={<FolderKanban className="size-5" />} title="No projects yet"
              body={me.brands.length ? "Start a project inside one of your brands." : me.org_role === "admin" ? "Create your first brand to get started." : "Ask an admin to add you to a brand."}
              action={me.org_role === "admin" && !me.brands.length ? <Link href="/brands/new"><Button variant="primary">Create a brand</Button></Link> : undefined} />
          )}
        </section>
        <section>
          <h2 className="mb-3 text-sm font-semibold">Activity</h2>
          <Card className="px-4">
            {dash.data?.recent_jobs.length ? (
              <div className="divide-y divide-border">
                {dash.data.recent_jobs.map((j) => <Link key={j.id} href={`/projects/${j.project_id}?tab=activity`} className="block"><JobLine job={j} project={j.project_name} /></Link>)}
              </div>
            ) : <p className="py-8 text-center text-sm text-text-3">Uploads, renders and checks show up here.</p>}
          </Card>
        </section>
      </div>
    </>
  );
}

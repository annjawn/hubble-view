import { useState } from 'react'
import { ArrowLeft, ChevronRight, Folder, GitBranch } from 'lucide-react'
import { useOverview, useProjectArtifacts } from '../hooks/useMetrics'
import { compactNumber, relativeTime } from '../lib/format'
import { LoadingState } from '../components/common/LoadingState'
import { ContributionGrid } from '../components/projects/ContributionGrid'
import { ArtifactBrowser, artifactTabs } from './ProvidersView'
import type { ArtifactCategory, ProjectUsage } from '../types/api'

const projectName = (path: string) => path.split(/[\\/]/).filter(Boolean).pop() || path

function ProjectDetail({ project, onBack }: { project: ProjectUsage; onBack: () => void }) {
  const artifactQuery = useProjectArtifacts(project.project_path)
  const [tab, setTab] = useState<'overview' | ArtifactCategory>('overview')
  const artifacts = artifactQuery.data?.artifacts ?? []
  return <>
    <button className="mb-5 flex items-center gap-2 text-sm text-zinc-400 transition hover:text-white" onClick={onBack}><ArrowLeft size={15}/> All projects</button>
    <div className="mb-6 flex items-start gap-3"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-indigo-400/10 text-indigo-300"><Folder size={19}/></span><div className="min-w-0"><h1 className="truncate text-2xl font-semibold">{projectName(project.project_path)}</h1><p className="mt-1 truncate font-mono text-xs text-zinc-600">{project.project_path}</p></div></div>
    <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-white/[0.07]">{[{ id: 'overview', label: 'Overview' }, ...artifactTabs].map(item => { const count = item.id === 'overview' ? undefined : artifacts.filter(artifact => artifact.category === item.id).length; return <button key={item.id} onClick={() => setTab(item.id as 'overview' | ArtifactCategory)} className={`relative shrink-0 px-3 py-3 text-xs font-medium transition ${tab === item.id ? 'text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>{item.label}{count !== undefined && count > 0 && <span className="ml-1.5 text-[9px] text-zinc-600">{count}</span>}{tab === item.id && <span className="absolute inset-x-2 bottom-0 h-px bg-indigo-400"/>}</button> })}</nav>
    {tab === 'overview' ? <div className="space-y-4"><div className="panel grid grid-cols-3 divide-x divide-white/[0.06]"><div className="p-5"><div className="label">Tokens</div><div className="mt-2 text-xl font-semibold">{compactNumber(project.tokens)}</div></div><div className="p-5"><div className="label">Sessions</div><div className="mt-2 text-xl font-semibold">{project.sessions}</div></div><div className="p-5"><div className="label">Active days</div><div className="mt-2 text-xl font-semibold">{project.activity.length}</div></div></div><div className="panel p-5"><div className="mb-4 flex items-end justify-between"><div><h2 className="text-sm font-semibold">Project activity</h2><p className="mt-1 text-xs text-zinc-500">Token usage during the past 30 days.</p></div><span className="text-xs text-zinc-600">Active {relativeTime(project.last_active)}</span></div><ContributionGrid activity={project.activity} weeks={12}/></div></div> : (!artifactQuery.data ? <LoadingState error={artifactQuery.error as Error}/> : <ArtifactBrowser artifacts={artifacts} category={tab}/>)}
  </>
}

export function ProjectsView() {
  const projects = useOverview(30); const annual = useOverview(365)
  const [selected, setSelected] = useState<ProjectUsage | null>(null)
  if (!projects.data || !annual.data) return <LoadingState error={(projects.error || annual.error) as Error}/>
  if (selected) return <ProjectDetail project={selected} onBack={() => setSelected(null)}/>
  const aggregate = Array.from(annual.data.timeline.reduce((days, point) => { days.set(point.day, (days.get(point.day) ?? 0) + point.tokens); return days }, new Map<string, number>()), ([day, tokens]) => ({ day, tokens }))
  return <><div className="mb-7"><h1 className="text-2xl font-semibold">Projects</h1><p className="mt-1 text-sm text-zinc-500">Usage and project-scoped harness configuration.</p></div><div className="panel mb-4 p-5"><div className="mb-4 flex items-end justify-between"><div><h2 className="text-sm font-semibold">Contribution activity</h2><p className="mt-1 text-xs text-zinc-500">Aggregate local usage across all projects and harnesses.</p></div><span className="text-[10px] text-zinc-600">Past year</span></div><ContributionGrid activity={aggregate} weeks={52}/></div><div className="grid grid-cols-2 gap-4">{projects.data.projects.map(project=><button onClick={() => setSelected(project)} className="panel p-5 text-left transition hover:bg-white/[0.055]" key={project.project_path}><div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-400/10 text-indigo-300"><Folder size={18}/></span><div className="min-w-0 flex-1"><h3 className="truncate text-sm font-medium">{projectName(project.project_path)}</h3><p className="mt-1 truncate text-xs text-zinc-600">{project.project_path}</p></div><ChevronRight size={16} className="mt-3 text-zinc-600"/></div><div className="mt-6 grid grid-cols-3 gap-4"><div><div className="label">Tokens</div><div className="mt-2 font-semibold">{compactNumber(project.tokens)}</div></div><div><div className="label">Sessions</div><div className="mt-2 font-semibold">{project.sessions}</div></div><div><div className="label">Active days</div><div className="mt-2 font-semibold">{project.activity.length}</div></div></div><div className="mt-5 flex items-center gap-2 border-t border-white/[0.05] pt-3 text-xs text-zinc-600"><GitBranch size={13}/>Active {relativeTime(project.last_active)}</div></button>)}</div></>
}

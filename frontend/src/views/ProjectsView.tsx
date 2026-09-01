import { Folder, GitBranch } from 'lucide-react'
import { useOverview } from '../hooks/useMetrics'
import { compactNumber, relativeTime } from '../lib/format'
import { LoadingState } from '../components/common/LoadingState'
import { ContributionGrid } from '../components/projects/ContributionGrid'

export function ProjectsView() {
  const projects = useOverview(30)
  const annual = useOverview(365)
  if (!projects.data || !annual.data) return <LoadingState error={(projects.error || annual.error) as Error}/>
  const aggregate = Array.from(annual.data.timeline.reduce((days, point) => {
    days.set(point.day, (days.get(point.day) ?? 0) + point.tokens)
    return days
  }, new Map<string, number>()), ([day, tokens]) => ({ day, tokens }))

  return <><div className="mb-7"><h1 className="text-2xl font-semibold">Projects</h1><p className="mt-1 text-sm text-zinc-500">Usage grouped by detected repository or working directory.</p></div><div className="panel mb-4 p-5"><div className="mb-4 flex items-end justify-between"><div><h2 className="text-sm font-semibold">Contribution activity</h2><p className="mt-1 text-xs text-zinc-500">Aggregate local usage across all projects and harnesses.</p></div><span className="text-[10px] text-zinc-600">Past year</span></div><ContributionGrid activity={aggregate} weeks={52}/></div><div className="grid grid-cols-2 gap-4">{projects.data.projects.map(project=><div className="panel p-5" key={project.project_path}><div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-400/10 text-indigo-300"><Folder size={18}/></span><div className="min-w-0"><h3 className="truncate text-sm font-medium">{project.project_path.split(/[\\/]/).pop()}</h3><p className="mt-1 truncate text-xs text-zinc-600">{project.project_path}</p></div></div><div className="mt-6 grid grid-cols-3 gap-4"><div><div className="label">Tokens</div><div className="mt-2 font-semibold">{compactNumber(project.tokens)}</div></div><div><div className="label">Sessions</div><div className="mt-2 font-semibold">{project.sessions}</div></div><div><div className="label">Active days</div><div className="mt-2 font-semibold">{project.activity.length}</div></div></div><div className="mt-5 flex items-center gap-2 border-t border-white/[0.05] pt-3 text-xs text-zinc-600"><GitBranch size={13}/>Active {relativeTime(project.last_active)}</div></div>)}</div></>
}

import { Folder, GitBranch } from 'lucide-react'
import { useOverview } from '../hooks/useMetrics'
import { compactNumber, currency, relativeTime } from '../lib/format'
import { LoadingState } from '../components/common/LoadingState'

export function ProjectsView() {
  const { data, error } = useOverview(30)
  if (!data) return <LoadingState error={error}/>
  return <><div className="mb-7"><h1 className="text-2xl font-semibold">Projects</h1><p className="mt-1 text-sm text-zinc-500">Usage grouped by detected repository or working directory.</p></div><div className="grid grid-cols-2 gap-4">{data.projects.map(project=><div className="panel p-5" key={project.project_path}><div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-400/10 text-indigo-300"><Folder size={18}/></span><div className="min-w-0"><h3 className="truncate text-sm font-medium">{project.project_path.split(/[\\/]/).pop()}</h3><p className="mt-1 truncate text-xs text-zinc-600">{project.project_path}</p></div></div><div className="mt-6 grid grid-cols-3 gap-4"><div><div className="label">Tokens</div><div className="mt-2 font-semibold">{compactNumber(project.tokens)}</div></div><div><div className="label">Sessions</div><div className="mt-2 font-semibold">{project.sessions}</div></div><div><div className="label">Cost</div><div className="mt-2 font-semibold">{currency(project.cost_usd)}</div></div></div><div className="mt-5 flex items-center gap-2 border-t border-white/[0.05] pt-3 text-xs text-zinc-600"><GitBranch size={13}/>Active {relativeTime(project.last_active)}</div></div>)}</div></>
}


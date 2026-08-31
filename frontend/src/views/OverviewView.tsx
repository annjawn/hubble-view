import { Clock3, Coins, MousePointerClick, RefreshCw, Shapes } from 'lucide-react'
import { useOverview, useScan } from '../hooks/useMetrics'
import { compactNumber, currency, relativeTime } from '../lib/format'
import { LoadingState } from '../components/common/LoadingState'
import { MetricCard } from '../components/dashboard/MetricCard'
import { UsageChart } from '../components/dashboard/UsageChart'
import { ProviderMark } from '../components/common/ProviderMark'

export function OverviewView() {
  const { data, error } = useOverview(7)
  const scan = useScan()
  if (!data) return <LoadingState error={error} />
  return <>
    <div className="mb-7 flex items-end justify-between"><div><h1 className="text-2xl font-semibold tracking-tight">Usage overview</h1><p className="mt-1 text-sm text-zinc-500">A private view of your coding harness activity.</p></div><button className="button" disabled={scan.isPending} onClick={() => scan.mutate()}><RefreshCw size={14} className={scan.isPending ? 'animate-spin' : ''}/>Scan now</button></div>
    <div className="grid grid-cols-4 gap-4"><MetricCard label="Total tokens" value={compactNumber(data.totals.total_tokens)} detail={`${compactNumber(data.totals.input_tokens)} in · ${compactNumber(data.totals.output_tokens)} out`} icon={Shapes}/><MetricCard label="Sessions" value={compactNumber(data.totals.sessions)} detail="Across the last 7 days" icon={Clock3}/><MetricCard label="Tool calls" value={compactNumber(data.totals.tool_calls)} detail="Detected local invocations" icon={MousePointerClick}/><MetricCard label="Est. API cost" value={currency(data.totals.cost_usd)} detail="When reported by providers" icon={Coins}/></div>
    <div className="mt-4 grid grid-cols-3 gap-4"><UsageChart points={data.timeline}/><div className="panel p-5"><h3 className="text-sm font-semibold">Harnesses</h3><p className="mt-1 text-xs text-zinc-500">Latest detected activity</p><div className="mt-5 space-y-5">{['claude','codex'].map(id => { const item=data.providers.find(p=>p.provider===id); return <div key={id} className="flex items-center gap-3"><ProviderMark provider={id}/><div className="min-w-0 flex-1"><div className="flex items-center justify-between"><span className="text-sm font-medium">{id==='claude'?'Claude Code':'Codex'}</span><span className="text-xs text-zinc-400">{compactNumber(item?.tokens ?? 0)}</span></div><div className="mt-1 flex justify-between text-[11px] text-zinc-600"><span className="truncate">{item?.model ?? 'No model detected'}</span><span>{relativeTime(item?.last_active ?? null)}</span></div></div></div>})}</div></div></div>
    <div className="panel mt-4 overflow-hidden"><div className="border-b border-white/[0.06] px-5 py-4"><h3 className="text-sm font-semibold">Top projects</h3></div>{data.projects.length ? data.projects.map((project,index)=><div key={project.project_path} className="grid grid-cols-[32px_1fr_100px_100px] items-center gap-3 border-b border-white/[0.04] px-5 py-3 text-sm last:border-0"><span className="text-xs text-zinc-600">{String(index+1).padStart(2,'0')}</span><span className="truncate text-zinc-300">{project.project_path}</span><span className="text-right text-zinc-500">{project.sessions} sessions</span><span className="text-right font-medium">{compactNumber(project.tokens)}</span></div>) : <div className="px-5 py-10 text-center text-sm text-zinc-600">No projects detected yet.</div>}</div>
  </>
}


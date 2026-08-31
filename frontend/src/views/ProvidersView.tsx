import { CheckCircle2, CircleOff, FolderSearch } from 'lucide-react'
import { useOverview, useProviders } from '../hooks/useMetrics'
import { compactNumber } from '../lib/format'
import { ProviderMark } from '../components/common/ProviderMark'
import { LoadingState } from '../components/common/LoadingState'

export function ProvidersView() {
  const providers = useProviders(); const overview = useOverview(30)
  if (!providers.data || !overview.data) return <LoadingState error={(providers.error || overview.error) as Error}/>
  return <><div className="mb-7"><h1 className="text-2xl font-semibold">Providers</h1><p className="mt-1 text-sm text-zinc-500">Modular collectors make additional harnesses easy to add later.</p></div><div className="grid grid-cols-2 gap-4">{providers.data.map(provider=>{const usage=overview.data.providers.find(p=>p.provider===provider.id);return <div className="panel p-6" key={provider.id}><div className="flex items-center justify-between"><div className="flex items-center gap-3"><ProviderMark provider={provider.id}/><div><h3 className="font-medium">{provider.name}</h3><p className="mt-1 text-xs text-zinc-500">{usage?.model ?? 'Waiting for model data'}</p></div></div><span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] ${provider.available?'bg-emerald-400/10 text-emerald-300':'bg-zinc-500/10 text-zinc-500'}`}>{provider.available?<CheckCircle2 size={12}/>:<CircleOff size={12}/>} {provider.available?'Detected':'Not detected'}</span></div><div className="mt-7 grid grid-cols-2"><div><div className="label">30-day tokens</div><div className="mt-2 text-xl font-semibold">{compactNumber(usage?.tokens ?? 0)}</div></div><div><div className="label">Sessions</div><div className="mt-2 text-xl font-semibold">{usage?.sessions ?? 0}</div></div></div><div className="mt-6 border-t border-white/[0.06] pt-4"><div className="mb-2 flex items-center gap-2 text-xs text-zinc-500"><FolderSearch size={13}/>Log locations</div>{provider.paths.map(path=><div key={path} className="truncate font-mono text-[11px] text-zinc-600">{path}</div>)}</div></div>})}</div></>
}


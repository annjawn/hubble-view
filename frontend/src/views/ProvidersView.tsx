import { useEffect, useState } from 'react'
import { ArrowDownToLine, ArrowLeft, ArrowUpFromLine, Bot, Brain, CheckCircle2, ChevronRight, CircleOff, Clock3, FileCode2, FileText, FolderSearch, Hammer, Radio, Terminal, UserRound, Wrench } from 'lucide-react'
import { useOverview, useProviderArtifacts, useProviders, useProviderSessions, useSessionEvents } from '../hooks/useMetrics'
import { compactNumber, relativeTime } from '../lib/format'
import { ProviderMark } from '../components/common/ProviderMark'
import { LoadingState } from '../components/common/LoadingState'
import type { ArtifactCategory, ProviderArtifact, ProviderStatus, TraceEvent } from '../types/api'

const projectName = (path: string | null) => path?.split('/').filter(Boolean).pop() || 'Unknown project'

const eventPresentation = (event: TraceEvent) => {
  if (event.kind === 'usage') return { label: 'Usage', detail: 'Token snapshot', Icon: Radio, accent: 'text-cyan-300', dot: 'bg-cyan-300' }
  if (event.kind === 'tool_call') return { label: event.name || 'Tool call', detail: 'Tool call', Icon: Wrench, accent: 'text-amber-300', dot: 'bg-amber-300' }
  if (event.kind === 'tool_result') return { label: event.metadata.is_error ? 'Tool error' : 'Tool result', detail: event.name || 'Result', Icon: Hammer, accent: event.metadata.is_error ? 'text-red-300' : 'text-sky-300', dot: event.metadata.is_error ? 'bg-red-400' : 'bg-sky-300' }
  if (event.kind === 'thinking') return { label: 'Thinking', detail: 'Reasoning', Icon: Brain, accent: 'text-violet-300', dot: 'bg-violet-300' }
  if (event.role === 'user') return { label: 'User', detail: 'Message', Icon: UserRound, accent: 'text-emerald-300', dot: 'bg-emerald-300' }
  if (event.role === 'developer' || event.role === 'system') return { label: 'System', detail: 'Instructions', Icon: Terminal, accent: 'text-zinc-400', dot: 'bg-zinc-500' }
  return { label: 'Assistant', detail: 'Response', Icon: Bot, accent: 'text-indigo-300', dot: 'bg-indigo-300' }
}

const readableContent = (event: TraceEvent) => {
  if (!event.content) return ''
  if (!event.kind.startsWith('tool')) return event.content
  try { return JSON.stringify(JSON.parse(event.content), null, 2) } catch { return event.content }
}

function SessionDetail({ provider, sessionId, onBack }: { provider: ProviderStatus; sessionId: string; onBack: () => void }) {
  const sessions = useProviderSessions(provider.id)
  const events = useSessionEvents(provider.id, sessionId)
  const session = sessions.data?.find(item => item.session_id === sessionId)
  return <>
    <button className="mb-5 flex items-center gap-2 text-sm text-zinc-400 transition hover:text-white" onClick={onBack}><ArrowLeft size={15}/> All sessions</button>
    <div className="mb-6 flex items-start justify-between gap-5"><div className="flex min-w-0 gap-3"><ProviderMark provider={provider.id}/><div className="min-w-0"><div className="mb-1 flex items-center gap-2"><h1 className="truncate text-xl font-semibold">{projectName(session?.project_path ?? null)}</h1>{session?.status === 'live' && <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-emerald-400/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300"><Radio size={11}/> Live</span>}</div><p className="truncate font-mono text-xs text-zinc-500">{session?.project_path || session?.session_id}</p></div></div><div className="hidden items-center gap-2 text-xs text-zinc-500 sm:flex"><Clock3 size={13}/> Updated {relativeTime(session?.last_active ?? null)}</div></div>
    {session && <div className="panel mb-8 overflow-hidden"><div className="grid grid-cols-2 divide-x divide-white/[0.06] sm:grid-cols-5">{[
      ['Model', session.model || 'Unknown'], ['Input', compactNumber(session.input_tokens)], ['Output', compactNumber(session.output_tokens)], ['Cached', compactNumber(session.cache_read_tokens + session.cache_write_tokens)], ['Tools', session.tool_calls]
    ].map(([label,value])=><div className="min-w-0 px-5 py-4" key={label}><div className="label">{label}</div><div className="mt-2 truncate text-sm font-medium">{value}</div></div>)}</div></div>}
    <div className="mb-4 flex items-end justify-between"><div><h2 className="text-sm font-semibold">Session trace</h2><p className="mt-1 text-xs text-zinc-500">Prompts, responses, and tool activity in chronological order.</p></div><span className="text-xs tabular-nums text-zinc-600">{events.data?.length ?? 0} events</span></div>
    {!events.data ? <LoadingState error={events.error as Error}/> : events.data.length === 0 ? <div className="panel py-16 text-center"><Terminal className="mx-auto mb-3 text-zinc-700" size={24}/><p className="text-sm text-zinc-400">Waiting for session activity</p><p className="mt-1 text-xs text-zinc-600">New events will appear here automatically.</p></div> : <div>{events.data.map((event, index) => {
      const presentation = eventPresentation(event); const Icon = presentation.Icon
      const tokens = event.input_tokens + event.output_tokens + event.cache_read_tokens + event.cache_write_tokens
      return <div key={event.id} className="grid grid-cols-[34px_minmax(0,1fr)] sm:grid-cols-[180px_minmax(0,1fr)]">
        <div className="relative pb-5 sm:pr-8"><div className={`absolute left-[13px] top-4 z-10 h-2 w-2 rounded-full ring-4 ring-[#090b0f] sm:left-auto sm:right-[13px] ${presentation.dot}`}/>{index < events.data.length - 1 && <div className="absolute bottom-0 left-[16px] top-5 border-l border-dashed border-white/[0.13] sm:left-auto sm:right-[16px]"/>}<div className="hidden items-start justify-end gap-2 pt-1 sm:flex"><div className="min-w-0 text-right"><div className={`truncate text-xs font-semibold ${presentation.accent}`}>{presentation.label}</div><div className="mt-1 text-[10px] text-zinc-600">{relativeTime(event.occurred_at)}</div></div><Icon className={`mt-0.5 shrink-0 ${presentation.accent}`} size={14}/></div></div>
        <article className={`panel mb-5 min-w-0 overflow-hidden ${event.metadata.is_error ? 'border-red-400/20' : ''}`}><header className="flex items-center justify-between gap-4 border-b border-white/[0.055] bg-white/[0.018] px-4 py-3"><div className="flex min-w-0 items-center gap-2 sm:hidden"><Icon className={`shrink-0 ${presentation.accent}`} size={14}/><span className={`truncate text-xs font-semibold ${presentation.accent}`}>{presentation.label}</span></div><span className="hidden text-[11px] font-medium uppercase tracking-[0.12em] text-zinc-600 sm:block">{presentation.detail}</span><div className="flex items-center gap-2">{event.model && <span className="hidden max-w-44 truncate rounded-md bg-white/[0.04] px-2 py-1 font-mono text-[10px] text-zinc-500 md:block">{event.model}</span>}<span className="text-[10px] text-zinc-600 sm:hidden">{relativeTime(event.occurred_at)}</span></div></header>
          <div className="p-4">{event.content ? <pre className={`max-h-[32rem] overflow-auto whitespace-pre-wrap break-words text-[13px] leading-6 text-zinc-300 ${event.kind.startsWith('tool') ? 'font-mono' : 'font-sans'}`}>{readableContent(event)}</pre> : <p className="text-xs italic text-zinc-600">No text content</p>}{tokens > 0 && <footer className="mt-4 flex flex-wrap gap-2 border-t border-white/[0.05] pt-3">{event.input_tokens > 0 && <span className="flex items-center gap-1.5 rounded-md bg-white/[0.035] px-2 py-1 text-[10px] text-zinc-500"><ArrowDownToLine size={11}/>{compactNumber(event.input_tokens)} input</span>}{event.output_tokens > 0 && <span className="flex items-center gap-1.5 rounded-md bg-white/[0.035] px-2 py-1 text-[10px] text-zinc-500"><ArrowUpFromLine size={11}/>{compactNumber(event.output_tokens)} output</span>}{event.cache_read_tokens + event.cache_write_tokens > 0 && <span className="rounded-md bg-white/[0.035] px-2 py-1 text-[10px] text-zinc-500">{compactNumber(event.cache_read_tokens + event.cache_write_tokens)} cached</span>}</footer>}</div>
        </article>
      </div>
    })}</div>}
  </>
}

export const artifactTabs: { id: ArtifactCategory; label: string }[] = [
  { id: 'instructions', label: 'Instructions' }, { id: 'memory', label: 'Memory' },
  { id: 'rules', label: 'Rules' }, { id: 'hooks', label: 'Hooks' },
  { id: 'skills', label: 'Skills' }, { id: 'settings', label: 'Settings' },
]

export function ArtifactBrowser({ artifacts, category }: { artifacts: ProviderArtifact[]; category: ArtifactCategory }) {
  const visible = artifacts.filter(item => item.category === category)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  useEffect(() => {
    if (!visible.some(item => item.id === selectedId)) setSelectedId(visible[0]?.id ?? null)
  }, [category, artifacts, selectedId])
  const selected = visible.find(item => item.id === selectedId) ?? visible[0]
  if (!selected) return <div className="panel py-16 text-center"><FileText className="mx-auto mb-3 text-zinc-700" size={25}/><p className="text-sm text-zinc-400">No {category} discovered</p><p className="mx-auto mt-1 max-w-md text-xs leading-5 text-zinc-600">Hubble checked this provider’s documented global locations and the projects represented in your sessions.</p></div>
  return <div className="panel grid min-h-[520px] overflow-hidden lg:grid-cols-[270px_minmax(0,1fr)]">
    <aside className="border-b border-white/[0.06] bg-black/10 lg:border-b-0 lg:border-r"><div className="border-b border-white/[0.06] px-4 py-3"><span className="label">Discovered files</span><span className="ml-2 text-[10px] text-zinc-600">{visible.length}</span></div><div className="max-h-52 overflow-y-auto p-2 lg:max-h-[475px]">{visible.map(item => <button key={item.id} onClick={() => setSelectedId(item.id)} className={`mb-1 flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition ${selected.id === item.id ? 'bg-white/[0.07] text-zinc-100' : 'text-zinc-500 hover:bg-white/[0.035] hover:text-zinc-300'}`}><FileCode2 size={14} className="mt-0.5 shrink-0"/><div className="min-w-0"><div className="truncate text-xs font-medium">{item.name}</div><div className="mt-1 flex items-center gap-1.5"><span className={`rounded px-1.5 py-0.5 text-[9px] uppercase tracking-wide ${item.scope === 'global' ? 'bg-indigo-400/10 text-indigo-300' : 'bg-emerald-400/10 text-emerald-300'}`}>{item.scope}</span>{item.project_path && <span className="truncate text-[9px] text-zinc-600">{projectName(item.project_path)}</span>}</div></div></button>)}</div></aside>
    <section className="min-w-0"><header className="border-b border-white/[0.06] px-5 py-3"><div className="flex items-center justify-between gap-4"><div className="min-w-0"><h3 className="truncate text-sm font-medium">{selected.name}</h3><p className="mt-1 truncate font-mono text-[10px] text-zinc-600" title={selected.path}>{selected.path}</p></div><span className="shrink-0 text-[10px] text-zinc-600">{compactNumber(selected.size)}B</span></div></header><pre className="max-h-[475px] min-h-[420px] overflow-auto whitespace-pre-wrap break-words p-5 font-mono text-xs leading-6 text-zinc-300">{selected.content}</pre></section>
  </div>
}

function ProviderDetail({ provider, onBack }: { provider: ProviderStatus; onBack: () => void }) {
  const sessions = useProviderSessions(provider.id); const artifactQuery = useProviderArtifacts(provider.id)
  const [selected, setSelected] = useState<string | null>(null); const [tab, setTab] = useState<'sessions' | ArtifactCategory>('sessions')
  useEffect(() => { if (selected && !sessions.data?.some(item => item.session_id === selected)) setSelected(null) }, [sessions.data, selected])
  if (selected) return <SessionDetail provider={provider} sessionId={selected} onBack={() => setSelected(null)}/>
  const artifacts = artifactQuery.data?.artifacts ?? []
  return <><button className="mb-5 flex items-center gap-2 text-sm text-zinc-400 hover:text-white" onClick={onBack}><ArrowLeft size={15}/> Providers</button><div className="mb-6 flex items-center gap-3"><ProviderMark provider={provider.id}/><div><h1 className="text-2xl font-semibold">{provider.name}</h1><p className="mt-1 text-sm text-zinc-500">Sessions and configuration from global and project scopes.</p></div></div>
    <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-white/[0.07]">{[{ id: 'sessions', label: 'Sessions' }, ...artifactTabs].map(item => { const count = item.id === 'sessions' ? sessions.data?.length : artifacts.filter(artifact => artifact.category === item.id).length; return <button key={item.id} onClick={() => setTab(item.id as 'sessions' | ArtifactCategory)} className={`relative shrink-0 px-3 py-3 text-xs font-medium transition ${tab === item.id ? 'text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>{item.label}{count !== undefined && count > 0 && <span className="ml-1.5 text-[9px] text-zinc-600">{count}</span>}{tab === item.id && <span className="absolute inset-x-2 bottom-0 h-px bg-indigo-400"/>}</button> })}</nav>
    {tab === 'sessions' ? (!sessions.data ? <LoadingState error={sessions.error as Error}/> : sessions.data.length === 0 ? <div className="panel p-10 text-center text-sm text-zinc-500">No trace-capable sessions found yet.</div> : <div className="space-y-3">{sessions.data.map(session=><button key={session.session_id} onClick={()=>setSelected(session.session_id)} className="panel flex w-full items-center gap-4 p-5 text-left transition hover:bg-white/[0.055]"><span className={`h-2.5 w-2.5 rounded-full ${session.status === 'live' ? 'bg-emerald-400 shadow-[0_0_10px_#34d399]' : 'bg-zinc-700'}`}/><div className="min-w-0 flex-1"><div className="truncate font-medium">{projectName(session.project_path)}</div><div className="mt-1 truncate text-xs text-zinc-500">{session.model || 'Unknown model'} · {relativeTime(session.last_active)}</div></div><div className="text-right"><div className="text-sm font-medium">{compactNumber(session.total_tokens)} tokens</div><div className="mt-1 text-xs text-zinc-500">{session.tool_calls} tools · {session.event_count} events</div></div><ChevronRight size={16} className="text-zinc-600"/></button>)}</div>) : (!artifactQuery.data ? <LoadingState error={artifactQuery.error as Error}/> : <ArtifactBrowser artifacts={artifacts} category={tab}/>)}</>
}

export function ProvidersView() {
  const providers = useProviders(); const overview = useOverview(30); const [selected, setSelected] = useState<ProviderStatus | null>(null)
  if (!providers.data || !overview.data) return <LoadingState error={(providers.error || overview.error) as Error}/>
  if (selected) return <ProviderDetail provider={selected} onBack={()=>setSelected(null)}/>
  return <><div className="mb-7"><h1 className="text-2xl font-semibold">Providers</h1><p className="mt-1 text-sm text-zinc-500">Open a provider to inspect its sessions and live trace.</p></div><div className="grid grid-cols-2 gap-4">{providers.data.map(provider=>{const usage=overview.data.providers.find(p=>p.provider===provider.id);return <button onClick={()=>setSelected(provider)} className="panel p-6 text-left transition hover:bg-white/[0.055]" key={provider.id}><div className="flex items-center justify-between"><div className="flex items-center gap-3"><ProviderMark provider={provider.id}/><div><h3 className="font-medium">{provider.name}</h3><p className="mt-1 text-xs text-zinc-500">{usage?.last_active ? `Last activity ${relativeTime(usage.last_active)}` : provider.available ? 'Ready for local collection' : 'Collector not detected'}</p></div></div><span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] ${provider.available?'bg-emerald-400/10 text-emerald-300':'bg-zinc-500/10 text-zinc-500'}`}>{provider.available?<CheckCircle2 size={12}/>:<CircleOff size={12}/>} {provider.available?'Detected':'Not detected'}</span></div><div className="mt-7 grid grid-cols-2"><div><div className="label">30-day tokens</div><div className="mt-2 text-xl font-semibold">{compactNumber(usage?.tokens ?? 0)}</div></div><div><div className="label">Sessions</div><div className="mt-2 text-xl font-semibold">{usage?.sessions ?? 0}</div></div></div><div className="mt-6 border-t border-white/[0.06] pt-4"><div className="mb-2 flex items-center gap-2 text-xs text-zinc-500"><FolderSearch size={13}/>Log locations</div>{provider.paths.map(path=><div key={path} className="truncate font-mono text-[11px] text-zinc-600">{path}</div>)}</div></button>})}</div></>
}

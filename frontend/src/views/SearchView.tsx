import { useEffect, useState } from 'react'
import { ChevronRight, Search } from 'lucide-react'
import { useSearch } from '../hooks/useMetrics'
import { relativeTime } from '../lib/format'
import { ProviderMark } from '../components/common/ProviderMark'

const kindLabels: Record<string, string> = {
  message: 'Message', thinking: 'Thinking', tool_call: 'Tool call', tool_result: 'Tool result', usage: 'Usage',
}
const projectName = (path: string | null) => path?.split('/').filter(Boolean).pop() || 'Unknown project'

export function SearchView({ onOpen }: { onOpen: (provider: string, sessionId: string) => void }) {
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  // Wait for a pause in typing before querying.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(text.trim()), 250)
    return () => clearTimeout(timer)
  }, [text])
  const search = useSearch(query)
  const results = search.data?.results ?? []
  return <>
    <div className="mb-7"><h1 className="text-2xl font-semibold">Search</h1><p className="mt-1 text-sm text-zinc-500">Find prompts, responses, and tool activity across every stored session. Search runs on this device.</p></div>
    <label className="panel flex items-center gap-3 px-4 py-3"><Search size={16} className="shrink-0 text-zinc-500"/><input autoFocus value={text} onChange={event => setText(event.target.value)} placeholder="Search session transcripts" aria-label="Search session transcripts" className="w-full bg-transparent text-sm text-zinc-200 outline-none placeholder:text-zinc-600"/></label>
    <div className="mt-4">
      {query.length < 2 ? <p className="px-1 text-xs text-zinc-600">Type at least two characters. Every word must appear; partial words match from their start.</p>
        : search.isError ? <p className="px-1 text-sm text-red-300">Search failed: {(search.error as Error).message}</p>
        : !search.data ? <p className="px-1 text-sm text-zinc-500">Searching…</p>
        : results.length === 0 ? <div className="panel py-14 text-center text-sm text-zinc-500">No stored events match “{query}”.</div>
        : <><p className="mb-3 px-1 text-xs text-zinc-600">{results.length === 50 ? 'Showing the 50 most recent matches' : `${results.length} ${results.length === 1 ? 'match' : 'matches'}`}, newest first</p><div className="space-y-2">{results.map(item => <button key={item.id} onClick={() => onOpen(item.provider, item.session_id)} className="panel flex w-full items-start gap-4 p-4 text-left transition hover:bg-white/[0.055]"><ProviderMark provider={item.provider} size="sm"/><div className="min-w-0 flex-1"><div className="flex items-center gap-2 text-xs"><span className="truncate font-medium text-zinc-200">{projectName(item.project_path)}</span><span className="shrink-0 rounded bg-white/[0.05] px-1.5 py-0.5 text-[10px] text-zinc-500">{item.kind === 'message' && item.role ? item.role : kindLabels[item.kind] ?? item.kind}{item.name && item.kind === 'tool_call' ? ` · ${item.name}` : ''}</span><span className="shrink-0 text-[10px] text-zinc-600">{relativeTime(item.occurred_at)}</span></div><p className="mt-2 line-clamp-3 break-words text-[13px] leading-5 text-zinc-400">{item.snippet}</p></div><ChevronRight size={16} className="mt-1 shrink-0 text-zinc-600"/></button>)}</div></>}
    </div>
  </>
}

import type { ModelUsage } from '../../types/api'
import { compactNumber, relativeTime } from '../../lib/format'
import { ProviderMark } from '../common/ProviderMark'

const providerNames: Record<string, string> = {
  claude: 'Claude Code', codex: 'Codex', cursor: 'Cursor', kiro: 'Kiro',
}

export function ModelUsageRail({ models }: { models: ModelUsage[] }) {
  return <section className="panel mt-4 overflow-hidden">
    <div className="border-b border-white/[0.06] px-5 py-4">
      <div><h3 className="text-sm font-semibold">Usage by model</h3><p className="mt-1 text-xs text-zinc-500">Processed tokens across every harness</p></div>
    </div>
    {models.length ? <div className="overflow-x-auto p-4">
      <div className="flex w-max gap-3">
        {models.map(item => <article key={`${item.provider}:${item.model}`} className="w-[270px] shrink-0 rounded-xl border border-white/[0.07] bg-gradient-to-br from-white/[0.045] to-transparent p-4">
          <div className="flex items-center gap-3"><ProviderMark provider={item.provider} size="sm"/><div className="min-w-0"><div className="truncate text-sm font-medium text-zinc-200" title={item.model}>{item.model}</div><div className="mt-0.5 text-[10px] uppercase tracking-wider text-zinc-600">{providerNames[item.provider] ?? item.provider}</div></div></div>
          <div className="mt-5 text-2xl font-semibold tracking-tight">{compactNumber(item.tokens)}</div>
          <div className="mt-1 text-[11px] text-zinc-500">{item.estimated ? 'estimated processed tokens' : 'processed tokens'}</div>
          <div className="mt-4 grid grid-cols-3 gap-2 border-t border-white/[0.06] pt-3 text-[10px]">
            <div><div className="text-zinc-600">Fresh</div><div className="mt-1 text-zinc-400">{compactNumber(item.input_tokens + item.cache_write_tokens)}</div></div>
            <div><div className="text-zinc-600">Cached</div><div className="mt-1 text-zinc-400">{compactNumber(item.cache_read_tokens)}</div></div>
            <div><div className="text-zinc-600">Output</div><div className="mt-1 text-zinc-400">{compactNumber(item.output_tokens)}</div></div>
          </div>
          <div className="mt-3 flex justify-between text-[10px] text-zinc-600"><span>{item.sessions} {item.sessions === 1 ? 'session' : 'sessions'}</span><span>{relativeTime(item.last_active)}</span></div>
        </article>)}
      </div>
    </div> : <div className="px-5 py-10 text-center text-sm text-zinc-600">Model usage will appear after a model-bearing session is detected.</div>}
  </section>
}

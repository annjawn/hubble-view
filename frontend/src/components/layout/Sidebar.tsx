import { FolderKanban, Gauge, Settings, Waypoints } from 'lucide-react'

export type View = 'overview' | 'projects' | 'providers' | 'settings'
const items = [
  { id: 'overview' as const, label: 'Overview', icon: Gauge },
  { id: 'projects' as const, label: 'Projects', icon: FolderKanban },
  { id: 'providers' as const, label: 'Providers', icon: Waypoints },
  { id: 'settings' as const, label: 'Settings', icon: Settings },
]

export function Sidebar({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return <aside className="flex w-60 shrink-0 flex-col border-r border-white/[0.06] bg-black/20 px-3 pb-4 pt-12">
    <div className="mb-7 flex items-center gap-3 px-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-black text-white ring-1 ring-white/10"><span className="flex flex-col items-center gap-1"><span className="h-2 w-2 rounded-full bg-white"/><span className="h-0.5 w-4 rounded-full bg-white"/></span></span><div><div className="text-sm font-semibold">Hubble</div><div className="text-[11px] text-zinc-500">Local usage monitor</div></div></div>
    <nav className="space-y-1">{items.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => onChange(id)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${view === id ? 'bg-white/[0.08] text-white' : 'text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300'}`}><Icon size={17} />{label}</button>)}</nav>
    <div className="mt-auto rounded-xl border border-white/[0.06] bg-white/[0.025] p-3"><div className="mb-1 flex items-center gap-2 text-xs text-zinc-400"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Local only</div><p className="text-[11px] leading-4 text-zinc-600">Usage stays on this device.</p></div>
  </aside>
}

import type { LucideIcon } from 'lucide-react'

export function MetricCard({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: LucideIcon }) {
  return <div className="panel p-5"><div className="mb-5 flex items-center justify-between"><span className="label">{label}</span><span className="grid h-8 w-8 place-items-center rounded-lg bg-white/[0.05] text-zinc-400"><Icon size={16} /></span></div><div className="text-2xl font-semibold tracking-tight">{value}</div><div className="mt-1 text-xs text-zinc-500">{detail}</div></div>
}


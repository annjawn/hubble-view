import type { LucideIcon } from 'lucide-react'

export function MetricCard({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: LucideIcon }) {
  return <div className="panel relative overflow-hidden p-5">
    <div className="pointer-events-none absolute -right-16 -top-20 h-44 w-44 rounded-full bg-amber-400/[0.10] blur-3xl"/>
    <div className="relative mb-5 flex items-center justify-between"><span className="label">{label}</span><span className="grid h-8 w-8 place-items-center rounded-lg border border-amber-300/[0.08] bg-amber-300/[0.06] text-amber-100/60"><Icon size={16} /></span></div>
    <div className="relative text-3xl font-semibold tracking-tight">{value}</div><div className="relative mt-1 text-xs text-zinc-500">{detail}</div>
  </div>
}

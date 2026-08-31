import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TimelinePoint } from '../../types/api'
import { compactNumber } from '../../lib/format'

export function UsageChart({ points }: { points: TimelinePoint[] }) {
  const data = Object.values(points.reduce<Record<string, Record<string, number | string>>>((acc, point) => {
    const row = acc[point.day] ?? { day: point.day, claude: 0, codex: 0 }
    row[point.provider] = point.tokens; acc[point.day] = row; return acc
  }, {}))
  return <div className="panel col-span-2 p-5"><div className="mb-5"><h3 className="text-sm font-semibold">Token activity</h3><p className="mt-1 text-xs text-zinc-500">Input and output tokens by day</p></div><div className="h-64">
    {data.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={data}><defs><linearGradient id="claude" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fb923c" stopOpacity={.35}/><stop offset="1" stopColor="#fb923c" stopOpacity={0}/></linearGradient><linearGradient id="codex" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#34d399" stopOpacity={.3}/><stop offset="1" stopColor="#34d399" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#ffffff0b" vertical={false}/><XAxis dataKey="day" tick={{fill:'#71717a',fontSize:11}} tickLine={false} axisLine={false}/><YAxis tickFormatter={compactNumber} tick={{fill:'#71717a',fontSize:11}} tickLine={false} axisLine={false}/><Tooltip contentStyle={{background:'#15181e',border:'1px solid #ffffff12',borderRadius:10}}/><Area type="monotone" dataKey="claude" stroke="#fb923c" fill="url(#claude)" strokeWidth={2}/><Area type="monotone" dataKey="codex" stroke="#34d399" fill="url(#codex)" strokeWidth={2}/></AreaChart></ResponsiveContainer> : <div className="grid h-full place-items-center text-sm text-zinc-600">Usage will appear after your first detected session.</div>}
  </div></div>
}

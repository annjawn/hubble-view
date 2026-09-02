import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TimelinePoint } from '../../types/api'
import { compactNumber } from '../../lib/format'
import { providerColors } from '../../lib/providerColors'

const formatTooltipDate = (value: string) => new Date(`${value}T00:00:00Z`).toLocaleDateString('en-US', {
  month: 'short', day: '2-digit', year: '2-digit', timeZone: 'UTC',
})

const formatAxisDate = (value: string) => {
  const date = new Date(`${value}T00:00:00Z`)
  return `${String(date.getUTCDate()).padStart(2, '0')}/${String(date.getUTCFullYear()).slice(-2)}`
}

export function UsageChart({ points }: { points: TimelinePoint[] }) {
  const data = Object.values(points.reduce<Record<string, Record<string, number | string>>>((acc, point) => {
    const row = acc[point.day] ?? { day: point.day, claude: 0, codex: 0, cursor: 0, kiro: 0, opencode: 0, antigravity: 0 }
    row[point.provider] = point.tokens; acc[point.day] = row; return acc
  }, {}))
  return <div className="panel col-span-2 flex min-h-[400px] flex-col p-5"><div className="mb-5"><h3 className="text-sm font-semibold">Token activity</h3><p className="mt-1 text-xs text-zinc-500">Processed tokens by day</p></div><div className="min-h-0 flex-1">
    {data.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{bottom:18}}><defs>{Object.entries(providerColors).map(([id,color])=><linearGradient id={id} key={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity={.3}/><stop offset="1" stopColor={color} stopOpacity={0}/></linearGradient>)}</defs><CartesianGrid stroke="#ffffff0b" vertical={false}/><XAxis dataKey="day" tickFormatter={formatAxisDate} tick={{fill:'#71717a',fontSize:10}} angle={-35} textAnchor="end" height={52} tickMargin={8} interval="preserveStartEnd" tickLine={false} axisLine={false}/><YAxis tickFormatter={compactNumber} tick={{fill:'#71717a',fontSize:11}} tickLine={false} axisLine={false}/><Tooltip labelFormatter={value => formatTooltipDate(String(value))} contentStyle={{background:'#15181e',border:'1px solid #ffffff12',borderRadius:10}}/>{Object.entries(providerColors).map(([id,color])=><Area key={id} type="monotone" dataKey={id} stroke={color} fill={`url(#${id})`} strokeWidth={2}/>)}</AreaChart></ResponsiveContainer> : <div className="grid h-full place-items-center text-sm text-zinc-600">Usage will appear after your first detected session.</div>}
  </div></div>
}

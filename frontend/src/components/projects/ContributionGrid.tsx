import type { ProjectActivity } from '../../types/api'
import { compactNumber } from '../../lib/format'

const levels = ['bg-white/[0.035]', 'bg-slate-700', 'bg-slate-600', 'bg-blue-500/70', 'bg-blue-400']

function dayKey(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function ContributionGrid({ activity, weeks = 5 }: { activity: ProjectActivity[]; weeks?: number }) {
  const totals = new Map(activity.map(item => [item.day, item.tokens]))
  const max = Math.max(0, ...activity.map(item => item.tokens))
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const start = new Date(today)
  start.setDate(today.getDate() - today.getDay() - ((weeks - 1) * 7))
  const days = Array.from({ length: weeks * 7 }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)
    const key = dayKey(date)
    const tokens = totals.get(key) ?? 0
    const level = tokens === 0 || max === 0 ? 0 : Math.min(4, Math.max(1, Math.ceil((tokens / max) * 4)))
    return { date, key, tokens, level, future: date > today }
  })

  const columns = Array.from({ length: weeks }, (_, week) => days.slice(week * 7, (week + 1) * 7))

  return <div>
    <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${weeks}, minmax(0, 1fr))` }} aria-label={`${weeks}-week contribution activity`}>
      {columns.map((column, week) => <div key={week} className="grid grid-rows-7 gap-1">{column.map(({ key, tokens, level, future }) => <span key={key} title={`${key}: ${compactNumber(tokens)} tokens`} className={`aspect-square w-full rounded-[2px] border border-white/[0.035] ${future ? 'opacity-20' : levels[level]}`}/>)}</div>)}
    </div>
    <div className="mt-3 flex items-center gap-1 text-[9px] text-zinc-600"><span className="mr-1">Less</span>{levels.map((level, index)=><span key={index} className={`h-2 w-2 rounded-[2px] ${level}`}/>)}<span className="ml-1">More</span></div>
  </div>
}

export function compactNumber(value: number) {
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

export function currency(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value)
}

export function relativeTime(value: string | null) {
  if (!value) return 'No activity yet'
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  if (Math.abs(seconds) < 3600) return formatter.format(Math.round(seconds / 60), 'minute')
  if (Math.abs(seconds) < 86400) return formatter.format(Math.round(seconds / 3600), 'hour')
  return formatter.format(Math.round(seconds / 86400), 'day')
}

/** API list-price estimate, e.g. "≈ $12.40". Sub-cent values show as "< $0.01". */
export function estimate(value: number | null | undefined) {
  if (value === null || value === undefined) return 'no list price'
  if (value > 0 && value < 0.01) return '≈ < $0.01'
  return `≈ ${currency(value)}`
}

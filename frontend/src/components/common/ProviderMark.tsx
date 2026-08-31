import { Braces, Sparkles } from 'lucide-react'

export function ProviderMark({ provider, size = 'md' }: { provider: string; size?: 'sm' | 'md' }) {
  const cls = `${size === 'sm' ? 'h-7 w-7' : 'h-9 w-9'} grid place-items-center rounded-lg border`
  return provider === 'claude'
    ? <span className={`${cls} border-orange-400/20 bg-orange-400/10 text-orange-300`}><Sparkles size={size === 'sm' ? 14 : 17} /></span>
    : <span className={`${cls} border-emerald-400/20 bg-emerald-400/10 text-emerald-300`}><Braces size={size === 'sm' ? 14 : 17} /></span>
}


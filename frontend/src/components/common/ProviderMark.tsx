import { Boxes } from 'lucide-react'
import claudeCodeLogo from '../../assets/harnesses/claude-code.webp'
import codexLogo from '../../assets/harnesses/codex.png'
import cursorLogo from '../../assets/harnesses/cursor.png'
import kiroLogo from '../../assets/harnesses/kiro.png'
import openCodeLogo from '../../assets/harnesses/open-code.png'

const logos: Record<string, string> = {
  claude: claudeCodeLogo,
  'claude-code': claudeCodeLogo,
  codex: codexLogo,
  cursor: cursorLogo,
  kiro: kiroLogo,
  'open-code': openCodeLogo,
  opencode: openCodeLogo,
}

export function ProviderMark({ provider, size = 'md' }: { provider: string; size?: 'sm' | 'md' }) {
  const dimension = size === 'sm' ? 'h-7 w-7 rounded-md' : 'h-9 w-9 rounded-lg'
  const logo = logos[provider.toLowerCase()]
  return logo
    ? <img src={logo} alt="" className={`${dimension} shrink-0 object-cover shadow-sm shadow-black/30`} />
    : <span className={`${dimension} grid shrink-0 place-items-center border border-slate-400/15 bg-slate-400/10 text-slate-400`}><Boxes size={size === 'sm' ? 14 : 17}/></span>
}

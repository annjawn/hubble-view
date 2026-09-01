import { ThinkingOrb, type OrbState } from 'thinking-orbs'
import { FolderOpen, RotateCw } from 'lucide-react'
import { useState } from 'react'
import { useStartupStatus } from '../hooks/useStartupStatus'

const orbStates: Record<StartupStatus['phase'], OrbState> = {
  starting: 'connecting',
  scanning: 'searching',
  ready: 'working',
  error: 'breathing',
}

export function SplashView() {
  const startup = useStartupStatus()
  const [retrying, setRetrying] = useState(false)
  const failed = startup.phase === 'error'
  const title = failed ? 'Hubble couldn’t start' : startup.phase === 'scanning' ? 'Finding your local usage data' : 'Starting Hubble'
  const detail = failed ? 'Try again, or open diagnostics if the problem continues.' : startup.phase === 'scanning' ? 'The first scan may take a moment.' : 'Preparing your private usage dashboard.'

  const retry = async () => {
    setRetrying(true)
    await window.desktop?.retryStartup()
    setRetrying(false)
  }

  return <main className="flex h-screen select-none flex-col items-center justify-center overflow-hidden bg-[#090b0f] text-center">
    <div className="mb-7"><ThinkingOrb state={orbStates[startup.phase]} size={64} theme="dark" aria-label="Hubble is loading"/></div>
    <p className="loading-shimmer text-base font-medium" data-text={title}>{title}</p>
    <p className="mt-2 max-w-[300px] text-xs leading-5 text-zinc-500">{detail}</p>
    {failed && <div className="mt-5 flex gap-2">
      <button className="button" disabled={retrying} onClick={retry}><RotateCw size={14} className={retrying ? 'animate-spin' : ''}/>Try again</button>
      <button className="button" onClick={() => window.desktop?.openDiagnostics()}><FolderOpen size={14}/>Diagnostics</button>
    </div>}
  </main>
}

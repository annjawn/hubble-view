import { Activity, FolderOpen, RotateCw } from 'lucide-react'
import { useState } from 'react'
import { useStartupStatus } from '../../hooks/useStartupStatus'

export function LoadingState({ error }: { error?: Error | null }) {
  const startup = useStartupStatus()
  const [retrying, setRetrying] = useState(false)
  const failed = startup.phase === 'error'
  const title = failed ? 'Hubble couldn’t start' : startup.phase === 'scanning' ? 'Finding your local usage data' : error ? 'Hubble is taking longer than expected' : 'Starting Hubble'
  const detail = failed ? 'Try again, or open diagnostics if the problem continues.' : startup.phase === 'scanning' ? 'The first scan may take a moment.' : error ? 'We’re still getting things ready.' : 'Preparing your private usage dashboard.'

  const retry = async () => {
    setRetrying(true)
    await window.desktop?.retryStartup()
    window.location.reload()
  }

  return <div className="grid min-h-[420px] place-items-center text-center">
    <div><Activity className="mx-auto mb-3 animate-pulse text-indigo-400" />
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-sm text-zinc-500">{detail}</p>
      {failed && <div className="mt-5 flex justify-center gap-2">
        <button className="button" disabled={retrying} onClick={retry}><RotateCw size={14} className={retrying ? 'animate-spin' : ''}/>Try again</button>
        <button className="button" onClick={() => window.desktop?.openDiagnostics()}><FolderOpen size={14}/>Open diagnostics</button>
      </div>}
    </div>
  </div>
}

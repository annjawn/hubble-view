import { useEffect, useState } from 'react'

const ready: StartupStatus = { phase: 'ready' }

export function useStartupStatus() {
  const [status, setStatus] = useState<StartupStatus>(window.desktop ? { phase: 'starting' } : ready)

  useEffect(() => {
    if (!window.desktop) return
    void window.desktop.getStartupStatus().then(setStatus)
    return window.desktop.onStartupStatus(setStatus)
  }, [])

  return status
}

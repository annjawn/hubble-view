export {}

declare global {
  type StartupStatus = { phase: 'starting' | 'scanning' | 'ready' | 'error'; detail?: string }

  interface Window {
    desktop?: {
      platform: string
      getApiBaseUrl: () => Promise<string>
      getStartupStatus: () => Promise<StartupStatus>
      retryStartup: () => Promise<StartupStatus>
      openDiagnostics: () => Promise<string>
      onStartupStatus: (listener: (status: StartupStatus) => void) => () => void
      showMainWindow: () => Promise<void>
      openPath: (path: string) => Promise<string>
      setLoginItem: (enabled: boolean) => Promise<void>
    }
  }
}

export {}

declare global {
  interface Window {
    desktop?: {
      apiBaseUrl: string
      platform: string
      showMainWindow: () => Promise<void>
      openPath: (path: string) => Promise<string>
      setLoginItem: (enabled: boolean) => Promise<void>
    }
  }
}


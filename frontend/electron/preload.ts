import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('desktop', {
  platform: process.platform,
  getApiBaseUrl: () => ipcRenderer.invoke('startup:apiBaseUrl'),
  getStartupStatus: () => ipcRenderer.invoke('startup:status'),
  retryStartup: () => ipcRenderer.invoke('startup:retry'),
  openDiagnostics: () => ipcRenderer.invoke('startup:openDiagnostics'),
  onStartupStatus: (listener: (status: { phase: string; detail?: string }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, status: { phase: string; detail?: string }) => listener(status)
    ipcRenderer.on('startup:status', handler)
    return () => ipcRenderer.removeListener('startup:status', handler)
  },
  showMainWindow: () => ipcRenderer.invoke('app:show'),
  openPath: (path: string) => ipcRenderer.invoke('app:openPath', path),
  setLoginItem: (enabled: boolean) => ipcRenderer.invoke('app:setLoginItem', enabled),
})

import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('desktop', {
  apiBaseUrl: 'http://127.0.0.1:8765/api',
  platform: process.platform,
  showMainWindow: () => ipcRenderer.invoke('app:show'),
  openPath: (path: string) => ipcRenderer.invoke('app:openPath', path),
  setLoginItem: (enabled: boolean) => ipcRenderer.invoke('app:setLoginItem', enabled),
})


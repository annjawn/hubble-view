import { app, BrowserWindow, ipcMain, Menu, nativeImage, shell, Tray } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import path from 'node:path'

const API_PORT = 8765
let mainWindow: BrowserWindow | null = null
let trayWindow: BrowserWindow | null = null
let tray: Tray | null = null
let backend: ChildProcess | null = null
let quitting = false

app.setName('Hubble')

function appIcon() {
  return nativeImage.createFromPath(path.join(__dirname, '../../build/icons/hubble-1024.png'))
}

function startBackend() {
  const dataDir = app.getPath('userData')
  const backendDir = path.resolve(process.cwd(), '../backend')
  backend = spawn('uv', [
    'run', '--project', backendDir,
    'uvicorn', 'harness_metrics.main:app', '--host', '127.0.0.1', '--port', String(API_PORT),
  ], {
    cwd: backendDir,
    env: { ...process.env, HARNESS_METRICS_DATA_DIR: dataDir },
    stdio: 'inherit',
  })
  backend.on('error', (error) => console.error('Unable to start backend:', error))
}

function rendererUrl(route = '/') {
  const devUrl = process.env.VITE_DEV_SERVER_URL
  return devUrl ? `${devUrl}${route}` : `file://${path.join(__dirname, '../../dist/index.html')}#${route}`
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280, height: 820, minWidth: 980, minHeight: 650,
    title: 'Hubble', icon: appIcon(),
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    backgroundColor: '#090b0f',
    webPreferences: { preload: path.join(__dirname, '../preload/preload.cjs'), contextIsolation: true, nodeIntegration: false },
  })
  void mainWindow.loadURL(rendererUrl('/'))
  mainWindow.on('close', (event) => {
    if (!quitting) { event.preventDefault(); mainWindow?.hide() }
  })
}

function trayIcon() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" fill="white"/><rect x="7" y="15" width="10" height="2" rx="1" fill="white"/></svg>`
  const icon = nativeImage.createFromDataURL(`data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`)
  if (process.platform === 'darwin') icon.setTemplateImage(true)
  return icon
}

function createTray() {
  trayWindow = new BrowserWindow({
    width: 380, height: 520, show: false, frame: false, resizable: false,
    skipTaskbar: true, alwaysOnTop: true, backgroundColor: '#0d1015',
    webPreferences: { preload: path.join(__dirname, '../preload/preload.cjs'), contextIsolation: true, nodeIntegration: false },
  })
  void trayWindow.loadURL(rendererUrl('/tray'))
  trayWindow.on('blur', () => trayWindow?.hide())
  tray = new Tray(trayIcon())
  tray.setToolTip('Hubble')
  tray.on('click', () => {
    if (!trayWindow || !tray) return
    if (trayWindow.isVisible()) return trayWindow.hide()
    const trayBounds = tray.getBounds()
    const windowBounds = trayWindow.getBounds()
    const x = Math.round(trayBounds.x + trayBounds.width / 2 - windowBounds.width / 2)
    const y = process.platform === 'darwin' ? trayBounds.y + trayBounds.height + 5 : trayBounds.y - windowBounds.height - 5
    trayWindow.setPosition(x, y, false)
    trayWindow.show(); trayWindow.focus()
  })
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open Hubble', click: () => { mainWindow?.show(); mainWindow?.focus() } },
    { type: 'separator' },
    { label: 'Quit', click: () => { quitting = true; app.quit() } },
  ]))
}

app.whenReady().then(() => {
  if (process.platform === 'darwin') app.dock?.setIcon(appIcon())
  startBackend(); createMainWindow(); createTray()
  ipcMain.handle('app:show', () => { mainWindow?.show(); mainWindow?.focus(); trayWindow?.hide() })
  ipcMain.handle('app:openPath', (_event, target: string) => shell.openPath(target))
  ipcMain.handle('app:setLoginItem', (_event, enabled: boolean) => app.setLoginItemSettings({ openAtLogin: enabled }))
  app.on('activate', () => { mainWindow?.show() })
})

app.on('before-quit', () => { quitting = true; backend?.kill() })
app.on('window-all-closed', () => { if (process.platform !== 'darwin' && quitting) app.quit() })

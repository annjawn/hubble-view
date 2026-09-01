import { app, BrowserWindow, ipcMain, Menu, nativeImage, shell, Tray } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { createWriteStream, mkdirSync } from 'node:fs'
import { createServer } from 'node:net'
import path from 'node:path'

type StartupPhase = 'starting' | 'scanning' | 'ready' | 'error'
type StartupStatus = { phase: StartupPhase; detail?: string }

let mainWindow: BrowserWindow | null = null
let splashWindow: BrowserWindow | null = null
let trayWindow: BrowserWindow | null = null
let tray: Tray | null = null
let backend: ChildProcess | null = null
let apiBaseUrl = ''
let startupStatus: StartupStatus = { phase: 'starting' }
let splashShownAt = 0
let quitting = false

app.setName('Hubble')

function appIcon() {
  return nativeImage.createFromPath(path.join(__dirname, '../../icons/macos/icon_1024.png'))
}

function setStartupStatus(status: StartupStatus) {
  startupStatus = status
  for (const window of BrowserWindow.getAllWindows()) window.webContents.send('startup:status', status)
}

async function getApiBaseUrl() {
  while (!apiBaseUrl && startupStatus.phase !== 'error') {
    await new Promise(resolve => setTimeout(resolve, 50))
  }
  if (!apiBaseUrl) throw new Error('Hubble could not initialize its local service')
  return apiBaseUrl
}

function availablePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 8765
      server.close(error => error ? reject(error) : resolve(port))
    })
  })
}

async function waitUntilReady(url: string) {
  const deadline = Date.now() + 30_000
  while (Date.now() < deadline) {
    if (backend?.exitCode !== null) throw new Error(`Local service exited with code ${backend?.exitCode}`)
    try {
      const response = await fetch(`${url}/health`)
      if (response.ok) return
    } catch { /* Service is still starting. */ }
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error('Local service did not become ready in time')
}

async function startBackend() {
  setStartupStatus({ phase: 'starting' })
  const port = await availablePort()
  apiBaseUrl = `http://127.0.0.1:${port}/api`
  const dataDir = app.getPath('userData')
  const backendDir = app.isPackaged ? path.join(process.resourcesPath, 'backend') : path.resolve(process.cwd(), '../backend')
  const executable = app.isPackaged
    ? path.join(backendDir, process.platform === 'win32' ? 'hubble-service.exe' : 'hubble-service')
    : (process.env.HUBBLE_UV_PATH ?? 'uv')
  const args = app.isPackaged
    ? ['--host', '127.0.0.1', '--port', String(port)]
    : ['run', '--project', backendDir, 'uvicorn', 'harness_metrics.main:app', '--host', '127.0.0.1', '--port', String(port)]
  const logsDir = path.join(dataDir, 'logs')
  mkdirSync(logsDir, { recursive: true })
  const log = createWriteStream(path.join(logsDir, 'service.log'), { flags: 'a' })
  backend = spawn(executable, args, {
    cwd: app.isPackaged ? backendDir : undefined,
    env: {
      ...process.env,
      HARNESS_METRICS_DATA_DIR: dataDir,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  backend.stdout?.pipe(log, { end: false })
  backend.stderr?.pipe(log, { end: false })
  const child = backend
  backend.once('error', error => {
    log.write(`\nUnable to start local service: ${error.message}\n`)
    setStartupStatus({ phase: 'error', detail: error.message })
  })
  backend.once('exit', code => {
    log.end(`\nLocal service exited with code ${code ?? 'unknown'}\n`)
    if (!quitting && backend === child) setStartupStatus({ phase: 'error', detail: 'The local service stopped unexpectedly' })
  })
  setStartupStatus({ phase: 'scanning' })
  try {
    await waitUntilReady(apiBaseUrl)
    setStartupStatus({ phase: 'ready' })
    await revealMainWindow()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    log.write(`\nStartup failed: ${detail}\n`)
    setStartupStatus({ phase: 'error', detail })
  }
}

function rendererUrl(route = '/') {
  const devUrl = process.env.VITE_DEV_SERVER_URL
  return devUrl ? `${devUrl}${route}` : `file://${path.join(__dirname, '../../dist/index.html')}#${route}`
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    show: false,
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

function createSplashWindow() {
  splashShownAt = Date.now()
  splashWindow = new BrowserWindow({
    width: 420, height: 320, show: false, frame: false, resizable: false,
    maximizable: false, minimizable: false, fullscreenable: false,
    backgroundColor: '#090b0f', roundedCorners: true,
    webPreferences: { preload: path.join(__dirname, '../preload/preload.cjs'), contextIsolation: true, nodeIntegration: false },
  })
  splashWindow.setMenuBarVisibility(false)
  void splashWindow.loadURL(rendererUrl('/splash'))
  splashWindow.once('ready-to-show', () => splashWindow?.show())
  splashWindow.on('closed', () => { splashWindow = null })
}

async function revealMainWindow() {
  const remaining = Math.max(0, 1_400 - (Date.now() - splashShownAt))
  if (remaining) await new Promise(resolve => setTimeout(resolve, remaining))
  mainWindow?.show()
  mainWindow?.focus()
  splashWindow?.close()
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
  // Dev only: the packaged .app already carries icon.icns, and a runtime-set dock image
  // bypasses macOS's icon masking (Tahoe squircle), making the Dock icon look wrong.
  if (process.platform === 'darwin' && !app.isPackaged) app.dock?.setIcon(appIcon())
  ipcMain.handle('startup:status', () => startupStatus)
  ipcMain.handle('startup:apiBaseUrl', getApiBaseUrl)
  ipcMain.handle('startup:retry', async () => {
    backend?.kill()
    backend = null
    await startBackend()
    return startupStatus
  })
  ipcMain.handle('startup:openDiagnostics', () => shell.openPath(path.join(app.getPath('userData'), 'logs')))
  createSplashWindow(); createMainWindow(); createTray(); void startBackend()
  ipcMain.handle('app:show', () => {
    if (startupStatus.phase === 'ready') { mainWindow?.show(); mainWindow?.focus() }
    else { splashWindow?.show(); splashWindow?.focus() }
    trayWindow?.hide()
  })
  ipcMain.handle('app:openPath', (_event, target: string) => shell.openPath(target))
  ipcMain.handle('app:setLoginItem', (_event, enabled: boolean) => app.setLoginItemSettings({ openAtLogin: enabled }))
  app.on('activate', () => {
    if (startupStatus.phase === 'ready') mainWindow?.show()
    else { splashWindow?.show(); splashWindow?.focus() }
  })
})

app.on('before-quit', () => { quitting = true; backend?.kill() })
app.on('window-all-closed', () => { if (process.platform !== 'darwin' && quitting) app.quit() })

import { useState } from 'react'
import { Sidebar, type View } from './components/layout/Sidebar'
import { OverviewView } from './views/OverviewView'
import { ProjectsView } from './views/ProjectsView'
import { ProvidersView } from './views/ProvidersView'
import { SettingsView } from './views/SettingsView'
import { TrayView } from './views/TrayView'

export function App() {
  const [view, setView] = useState<View>('overview')
  const route = window.location.hash.slice(1) || window.location.pathname
  if (route === '/tray') return <TrayView />
  const views = { overview: <OverviewView/>, projects: <ProjectsView/>, providers: <ProvidersView/>, settings: <SettingsView/> }
  return <div className="flex h-screen overflow-hidden"><Sidebar view={view} onChange={setView}/><main className="min-w-0 flex-1 overflow-y-auto"><div className="drag-region h-10"/><div className="mx-auto max-w-[1180px] px-8 pb-10">{views[view]}</div></main></div>
}


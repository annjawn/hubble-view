import type { AppSettings, Overview, ProjectArtifacts, ProviderArtifacts, ProviderSession, ProviderStatus, SearchResponse, TraceEvent } from '../types/api'

async function send(path: string, init?: RequestInit): Promise<Response> {
  const baseUrl = window.desktop ? await window.desktop.getApiBaseUrl() : 'http://127.0.0.1:8765/api'
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  // The desktop shell issues a per-launch token; the manual dev service has none.
  if (window.desktop) headers['X-Hubble-Token'] = await window.desktop.getApiToken()
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers })
  if (!response.ok) throw new Error(await response.text())
  return response
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>
}

/** Fetch an export and hand it to the browser as a file download. */
async function download(path: string, filename: string): Promise<void> {
  const blob = await (await send(path)).blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

const safeName = (value: string) => value.replace(/[^A-Za-z0-9._-]+/g, '-').slice(0, 80)

export const api = {
  overview: (days = 7) => request<Overview>(`/overview?days=${days}`),
  providers: () => request<ProviderStatus[]>('/providers'),
  providerSessions: (provider: string) => request<ProviderSession[]>(`/providers/${encodeURIComponent(provider)}/sessions`),
  providerArtifacts: (provider: string) => request<ProviderArtifacts>(`/providers/${encodeURIComponent(provider)}/artifacts`),
  projectArtifacts: (projectPath: string) => request<ProjectArtifacts>(`/projects/artifacts?project_path=${encodeURIComponent(projectPath)}`),
  sessionEvents: (provider: string, sessionId: string) => request<TraceEvent[]>(`/providers/${encodeURIComponent(provider)}/sessions/${encodeURIComponent(sessionId)}/events`),
  search: (query: string, provider?: string) => request<SearchResponse>(`/search?q=${encodeURIComponent(query)}${provider ? `&provider=${encodeURIComponent(provider)}` : ''}`),
  exportSession: (provider: string, sessionId: string, format: 'markdown' | 'json') => download(
    `/providers/${encodeURIComponent(provider)}/sessions/${encodeURIComponent(sessionId)}/export?format=${format}`,
    `${safeName(provider)}-${safeName(sessionId)}.${format === 'json' ? 'json' : 'md'}`,
  ),
  exportUsage: (days = 30) => download(`/export/usage.csv?days=${days}`, `hubble-usage-${days}d.csv`),
  scan: () => request<{ imported: Record<string, number> }>('/scan', { method: 'POST' }),
  settings: () => request<AppSettings>('/settings'),
  updateSettings: (settings: Partial<AppSettings>) => request<AppSettings>('/settings', { method: 'PATCH', body: JSON.stringify(settings) }),
}

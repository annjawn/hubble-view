import type { AppSettings, Overview, ProjectArtifacts, ProviderArtifacts, ProviderSession, ProviderStatus, TraceEvent } from '../types/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = window.desktop ? await window.desktop.getApiBaseUrl() : 'http://127.0.0.1:8765/api'
  const response = await fetch(`${baseUrl}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!response.ok) throw new Error(await response.text())
  return response.json() as Promise<T>
}

export const api = {
  overview: (days = 7) => request<Overview>(`/overview?days=${days}`),
  providers: () => request<ProviderStatus[]>('/providers'),
  providerSessions: (provider: string) => request<ProviderSession[]>(`/providers/${encodeURIComponent(provider)}/sessions`),
  providerArtifacts: (provider: string) => request<ProviderArtifacts>(`/providers/${encodeURIComponent(provider)}/artifacts`),
  projectArtifacts: (projectPath: string) => request<ProjectArtifacts>(`/projects/artifacts?project_path=${encodeURIComponent(projectPath)}`),
  sessionEvents: (provider: string, sessionId: string) => request<TraceEvent[]>(`/providers/${encodeURIComponent(provider)}/sessions/${encodeURIComponent(sessionId)}/events`),
  scan: () => request<{ imported: Record<string, number> }>('/scan', { method: 'POST' }),
  settings: () => request<AppSettings>('/settings'),
  updateSettings: (settings: Partial<AppSettings>) => request<AppSettings>('/settings', { method: 'PATCH', body: JSON.stringify(settings) }),
}

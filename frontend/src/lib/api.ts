import type { AppSettings, Overview, ProviderStatus } from '../types/api'

const baseUrl = window.desktop?.apiBaseUrl ?? 'http://127.0.0.1:8765/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!response.ok) throw new Error(await response.text())
  return response.json() as Promise<T>
}

export const api = {
  overview: (days = 7) => request<Overview>(`/overview?days=${days}`),
  providers: () => request<ProviderStatus[]>('/providers'),
  scan: () => request<{ imported: Record<string, number> }>('/scan', { method: 'POST' }),
  settings: () => request<AppSettings>('/settings'),
  updateSettings: (settings: Partial<AppSettings>) => request<AppSettings>('/settings', { method: 'PATCH', body: JSON.stringify(settings) }),
}


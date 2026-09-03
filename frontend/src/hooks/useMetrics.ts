import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

export const useOverview = (days = 7) => useQuery({
  queryKey: ['overview', days],
  queryFn: () => api.overview(days),
  refetchInterval: 15_000,
  refetchIntervalInBackground: true,
})
export const useProviders = () => useQuery({ queryKey: ['providers'], queryFn: api.providers })
export const useProviderSessions = (provider: string | null) => useQuery({
  queryKey: ['provider-sessions', provider], queryFn: () => api.providerSessions(provider!),
  enabled: !!provider, refetchInterval: 2_000, refetchIntervalInBackground: true,
})
export const useProviderArtifacts = (provider: string | null) => useQuery({
  queryKey: ['provider-artifacts', provider], queryFn: () => api.providerArtifacts(provider!),
  enabled: !!provider, refetchInterval: 5_000, refetchIntervalInBackground: true,
})
export const useProjectArtifacts = (projectPath: string | null) => useQuery({
  queryKey: ['project-artifacts', projectPath], queryFn: () => api.projectArtifacts(projectPath!),
  enabled: !!projectPath, refetchInterval: 5_000, refetchIntervalInBackground: true,
})
export const useSessionEvents = (provider: string | null, sessionId: string | null) => useQuery({
  queryKey: ['session-events', provider, sessionId], queryFn: () => api.sessionEvents(provider!, sessionId!),
  enabled: !!provider && !!sessionId, refetchInterval: 1_000, refetchIntervalInBackground: true,
})
export const useSettings = () => useQuery({ queryKey: ['settings'], queryFn: api.settings })

export function useScan() {
  const client = useQueryClient()
  return useMutation({ mutationFn: api.scan, onSuccess: () => client.invalidateQueries({ queryKey: ['overview'] }) })
}

export function useUpdateSettings() {
  const client = useQueryClient()
  return useMutation({ mutationFn: api.updateSettings, onSuccess: (data) => client.setQueryData(['settings'], data) })
}

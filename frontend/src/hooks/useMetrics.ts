import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

export const useOverview = (days = 7) => useQuery({ queryKey: ['overview', days], queryFn: () => api.overview(days) })
export const useProviders = () => useQuery({ queryKey: ['providers'], queryFn: api.providers })
export const useSettings = () => useQuery({ queryKey: ['settings'], queryFn: api.settings })

export function useScan() {
  const client = useQueryClient()
  return useMutation({ mutationFn: api.scan, onSuccess: () => client.invalidateQueries({ queryKey: ['overview'] }) })
}

export function useUpdateSettings() {
  const client = useQueryClient()
  return useMutation({ mutationFn: api.updateSettings, onSuccess: (data) => client.setQueryData(['settings'], data) })
}


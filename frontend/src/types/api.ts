export interface Totals {
  sessions: number; input_tokens: number; output_tokens: number; total_tokens: number
  cache_read_tokens: number; cache_write_tokens: number; cost_usd: number
  active_projects: number; active_models: number; active_harnesses: number
  tool_calls: number; duration_ms: number
  /** API list-price estimate from the backend price table; never an amount billed. */
  estimated_cost_usd: number
}
export interface ProviderUsage { provider: string; sessions: number; tokens: number; cost_usd: number; last_active: string | null; model: string | null; estimated_cost_usd: number }
export interface ModelUsage { provider: string; model: string; sessions: number; input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number; tokens: number; last_active: string | null; estimated: number; estimated_cost_usd: number | null }
export interface TimelinePoint { day: string; provider: string; tokens: number; sessions: number }
export interface ProjectActivity { day: string; tokens: number }
export interface ProjectUsage { project_path: string; sessions: number; tokens: number; cost_usd: number; estimated_cost_usd: number; last_active: string; activity: ProjectActivity[] }
export interface UsageWindow { label: string; provider: string | null; active: boolean; tokens: number; sessions: number; started_at: string | null; resets_at: string | null; duration_seconds: number; source: string }
export interface Pricing { version: string; sources: string[]; unpriced_models: string[] }
export interface Overview { range_days: number; totals: Totals; providers: ProviderUsage[]; models: ModelUsage[]; timeline: TimelinePoint[]; projects: ProjectUsage[]; windows: UsageWindow[]; pricing: Pricing }
export interface ProviderStatus { id: string; name: string; available: boolean; paths: string[] }
export interface ProviderSession {
  session_id: string; project_path: string | null; model: string | null
  started_at: string; last_active: string; status: 'live' | 'ended'
  input_tokens: number; output_tokens: number; cache_read_tokens: number
  cache_write_tokens: number; total_tokens: number; tool_calls: number; event_count: number
  estimated_cost_usd: number | null
}
export interface TraceEvent {
  id: string; occurred_at: string; kind: 'message' | 'thinking' | 'tool_call' | 'tool_result' | 'usage'
  role: string | null; name: string | null; content: string | null; model: string | null
  input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number
  metadata: { tool_use_id?: string; is_error?: boolean }
}
export type ArtifactCategory = 'instructions' | 'memory' | 'rules' | 'hooks' | 'skills' | 'settings'
export interface ProviderArtifact {
  id: string; category: ArtifactCategory; scope: 'global' | 'project'; name: string
  path: string; project_path: string | null; providers: string[]; content: string; size: number; modified_at: number
}
export interface ProviderArtifacts { provider: string; projects: string[]; artifacts: ProviderArtifact[] }
export interface ProjectArtifacts { project_path: string; artifacts: ProviderArtifact[] }
export interface AppSettings { scan_interval_seconds: number; launch_at_login: boolean; minimize_to_tray: boolean; trace_retention_days: number; data_dir: string }
export interface SearchResult {
  id: string; provider: string; session_id: string; project_path: string | null; model: string | null
  occurred_at: string; kind: TraceEvent['kind']; role: string | null; name: string | null; snippet: string
}
export interface SearchResponse { query: string; mode: 'fts' | 'scan' | 'none'; results: SearchResult[] }

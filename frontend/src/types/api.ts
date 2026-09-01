export interface Totals {
  sessions: number; input_tokens: number; output_tokens: number; total_tokens: number
  cache_read_tokens: number; cache_write_tokens: number; cost_usd: number
  active_projects: number; active_models: number; active_harnesses: number
  tool_calls: number; duration_ms: number
}
export interface ProviderUsage { provider: string; sessions: number; tokens: number; cost_usd: number; last_active: string | null; model: string | null }
export interface ModelUsage { provider: string; model: string; sessions: number; input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number; tokens: number; last_active: string | null; estimated: number }
export interface TimelinePoint { day: string; provider: string; tokens: number; sessions: number }
export interface ProjectActivity { day: string; tokens: number }
export interface ProjectUsage { project_path: string; sessions: number; tokens: number; cost_usd: number; last_active: string; activity: ProjectActivity[] }
export interface UsageWindow { label: string; tokens: number; sessions: number; resets_at: string; duration_seconds: number; source: string }
export interface Overview { range_days: number; totals: Totals; providers: ProviderUsage[]; models: ModelUsage[]; timeline: TimelinePoint[]; projects: ProjectUsage[]; windows: UsageWindow[] }
export interface ProviderStatus { id: string; name: string; available: boolean; paths: string[] }
export interface AppSettings { scan_interval_seconds: number; launch_at_login: boolean; minimize_to_tray: boolean; data_dir: string }

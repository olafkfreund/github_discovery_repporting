export interface GlobalSettings {
  id: string
  global_kill_switch_enabled: boolean
  default_data_residency_region: string
  audit_log_retention_days: number
  streaming_log_retention_hours: number
  default_llm_connection_id: string | null
  created_at: string
  updated_at: string
}

export interface GlobalSettingsUpdate {
  global_kill_switch_enabled?: boolean
  default_data_residency_region?: string
  audit_log_retention_days?: number
  streaming_log_retention_hours?: number
  default_llm_connection_id?: string | null
}

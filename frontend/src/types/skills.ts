// Skill types for the Skills settings page (issue #40).
// Backend contract: backend/schemas/skill.py

export type SkillCategory = string // 16 scanner-domain keys + "general"

export type SkillSource = 'builtin' | 'custom'

export interface Skill {
  id?: string // undefined for built-ins
  name: string // slug
  description: string
  category: SkillCategory
  applies_to_check_ids: string[]
  triggers: ('remediation' | 'scan_enrichment')[]
  source: SkillSource
  enabled: boolean // effective enabled for this customer
  version: number
  updated_at?: string // null for built-ins with no toggle
}

export interface SkillContent {
  name: string
  content: string // markdown body
  source: SkillSource
}

export interface SkillCreatePayload {
  name: string
  description: string
  category: SkillCategory
  applies_to_check_ids: string[]
  triggers: string[]
  body: string
  enabled: boolean
}

export interface SkillUpdatePayload {
  description?: string
  category?: SkillCategory
  applies_to_check_ids?: string[]
  triggers?: string[]
  body?: string
  enabled?: boolean
}

export interface SkillsListResponse {
  skills: Skill[]
}

export type SkillFilterType = 'all' | 'builtin' | 'custom'

export interface SkillFilters {
  type: SkillFilterType
  enabledOnly: boolean
  search: string
}

/**
 * Per-connection skill overrides.
 *
 * Sparse dict: skill names ABSENT from the map inherit the customer-level
 * toggle. Present-and-true forces enabled for this connection; present-and-false
 * forces disabled.
 *
 * Empty dict clears all overrides on the connection.
 */
export interface ConnectionSkillsOverridePayload {
  overrides: Record<string, boolean>
}

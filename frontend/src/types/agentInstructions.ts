// Types for Agent Instructions — per-customer AGENTS.md-equivalent
// Injected into remediation agent context when the target repo has no
// AGENTS.md, CLAUDE.md, .cursorrules, or .github/copilot-instructions.md.
// The repo's own instructions always win.

export interface AgentInstructions {
  id: string
  customer_id: string
  content: string
  enabled: boolean
  profile_slug: string | null   // NEW — which profile was used as the starting point
  created_at: string
  updated_at: string
}

export interface AgentInstructionsUpsertPayload {
  content: string
  enabled: boolean
  profile_slug?: string | null  // NEW — passes through on PUT
}

export interface AgentProfile {
  slug: string
  display_name: string
  short_description: string
}

export interface AgentProfileContent {
  slug: string
  body: string
}

export interface AgentProfilesResponse {
  profiles: AgentProfile[]
}

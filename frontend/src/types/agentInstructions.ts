// Types for Agent Instructions — per-customer AGENTS.md-equivalent
// Injected into remediation agent context when the target repo has no
// AGENTS.md, CLAUDE.md, .cursorrules, or .github/copilot-instructions.md.
// The repo's own instructions always win.

export interface AgentInstructions {
  id: string
  customer_id: string
  content: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface AgentInstructionsUpsertPayload {
  content: string
  enabled: boolean
}

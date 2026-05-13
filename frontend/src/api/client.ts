import type {
  Customer,
  CustomerCreatePayload,
  Connection,
  ConnectionCreatePayload,
  ConnectionUpdatePayload,
  Scan,
  ScanScore,
  Finding,
  Report,
  DashboardStats,
  ScanProfile,
  ScanProfileConfig,
  CategoryRegistryInfo,
} from '../types'
import type {
  Skill,
  SkillContent,
  SkillCreatePayload,
  SkillUpdatePayload,
  SkillsListResponse,
  ConnectionSkillsOverridePayload,
} from '../types/skills'
import type {
  AgentInstructions,
  AgentInstructionsUpsertPayload,
  AgentProfile,
  AgentProfileContent,
  AgentProfilesResponse,
} from '../types/agentInstructions'
import type {
  LLMConnection,
  LLMConnectionCreatePayload,
  LLMConnectionUpdatePayload,
  LLMConnectionValidatePayload,
  LLMConnectionValidateResult,
} from '../types/llm'
import type {
  AgentRun,
  AgentRunDetailed,
  AgentRunCostEstimate,
  AgentRunTriggerPayload,
  RemediationPolicy,
  RemediationPolicyUpsertPayload,
} from '../types/agents'
import type { GlobalSettings, GlobalSettingsUpdate } from '../types/settings'

const BASE_URL = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = (body as { detail?: string | Array<{ msg: string; loc?: string[] }> }).detail
    let message: string
    if (Array.isArray(detail)) {
      message = detail.map((e) => e.msg).join('; ')
    } else {
      message = detail ?? res.statusText
    }
    throw new Error(message)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  // Customers
  listCustomers: () =>
    request<Customer[]>('/customers'),

  getCustomer: (id: string) =>
    request<Customer>(`/customers/${id}`),

  createCustomer: (data: CustomerCreatePayload) =>
    request<Customer>('/customers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateCustomer: (id: string, data: Partial<CustomerCreatePayload>) =>
    request<Customer>(`/customers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteCustomer: (id: string) =>
    request<void>(`/customers/${id}`, { method: 'DELETE' }),

  // Connections
  listConnections: (customerId: string) =>
    request<Connection[]>(`/customers/${customerId}/connections`),

  addConnection: (customerId: string, data: ConnectionCreatePayload) =>
    request<Connection>(`/customers/${customerId}/connections`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateConnection: (id: string, data: ConnectionUpdatePayload) =>
    request<Connection>(`/connections/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteConnection: (id: string) =>
    request<void>(`/connections/${id}`, { method: 'DELETE' }),

  validateConnection: (id: string) =>
    request<{ valid: boolean; message: string }>(`/connections/${id}/validate`, {
      method: 'POST',
    }),

  // Scan Profiles
  getScannerRegistry: () =>
    request<CategoryRegistryInfo[]>('/scanners/registry'),

  listScanProfiles: (customerId: string) =>
    request<ScanProfile[]>(`/customers/${customerId}/scan-profiles`),

  createScanProfile: (customerId: string, data: { name: string; description?: string; is_default?: boolean; config: ScanProfileConfig }) =>
    request<ScanProfile>(`/customers/${customerId}/scan-profiles`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getScanProfile: (id: string) =>
    request<ScanProfile>(`/scan-profiles/${id}`),

  updateScanProfile: (id: string, data: { name?: string; description?: string; is_default?: boolean; config?: ScanProfileConfig }) =>
    request<ScanProfile>(`/scan-profiles/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteScanProfile: (id: string) =>
    request<void>(`/scan-profiles/${id}`, { method: 'DELETE' }),

  // Scans
  triggerScan: (customerId: string, connectionId: string, profileId?: string) =>
    request<Scan>(`/customers/${customerId}/scans`, {
      method: 'POST',
      body: JSON.stringify({
        connection_id: connectionId,
        ...(profileId ? { profile_id: profileId } : {}),
      }),
    }),

  listScans: (customerId: string) =>
    request<Scan[]>(`/customers/${customerId}/scans`),

  getScan: (id: string) =>
    request<Scan>(`/scans/${id}`),

  getScanScores: (id: string) =>
    request<ScanScore[]>(`/scans/${id}/scores`),

  getScanFindings: (id: string) =>
    request<Finding[]>(`/scans/${id}/findings`),

  // Reports
  generateReport: (scanId: string) =>
    request<Report>(`/scans/${scanId}/reports`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  getReport: (id: string) =>
    request<Report>(`/reports/${id}`),

  listReports: (customerId: string) =>
    request<Report[]>(`/customers/${customerId}/reports`),

  downloadReport: (id: string) =>
    `${BASE_URL}/reports/${id}/download`,

  downloadReportExcel: (id: string) =>
    `${BASE_URL}/reports/${id}/download/excel`,

  downloadReportZip: (id: string) =>
    `${BASE_URL}/reports/${id}/download/zip`,

  // Dashboard
  getStats: () =>
    request<DashboardStats>('/dashboard/stats'),

  getRecentScans: () =>
    request<Scan[]>('/dashboard/recent-scans'),

  // LLM Connections
  listLLMConnections: (customerId: string) =>
    request<LLMConnection[]>(`/llm-connections/?customer_id=${customerId}`),

  getLLMConnection: (id: string) =>
    request<LLMConnection>(`/llm-connections/${id}`),

  createLLMConnection: (payload: LLMConnectionCreatePayload) =>
    request<LLMConnection>('/llm-connections/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateLLMConnection: (id: string, payload: LLMConnectionUpdatePayload) =>
    request<LLMConnection>(`/llm-connections/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteLLMConnection: (id: string) =>
    request<void>(`/llm-connections/${id}`, { method: 'DELETE' }),

  validateLLMConnection: (payload: LLMConnectionValidatePayload) =>
    request<LLMConnectionValidateResult>('/llm-connections/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  testLLMConnection: (id: string) =>
    request<LLMConnectionValidateResult>(`/llm-connections/${id}/test`, {
      method: 'POST',
    }),

  // Agent Instructions
  getAgentInstructions: async (customerId: string): Promise<AgentInstructions | null> => {
    const res = await fetch(`${BASE_URL}/customers/${customerId}/agent-instructions`, {
      headers: { 'Content-Type': 'application/json' },
    })
    if (res.status === 404) return null
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }))
      const detail = (body as { detail?: string }).detail
      throw new Error(detail ?? res.statusText)
    }
    return res.json() as Promise<AgentInstructions>
  },

  upsertAgentInstructions: (customerId: string, payload: AgentInstructionsUpsertPayload) =>
    request<AgentInstructions>(`/customers/${customerId}/agent-instructions`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteAgentInstructions: (customerId: string) =>
    request<void>(`/customers/${customerId}/agent-instructions`, { method: 'DELETE' }),

  // Agent Profiles
  listAgentProfiles: async (): Promise<AgentProfile[]> => {
    const response = await request<AgentProfilesResponse>('/agent-profiles/')
    return response.profiles
  },

  getAgentProfileContent: (slug: string): Promise<AgentProfileContent> =>
    request<AgentProfileContent>(`/agent-profiles/${slug}/content`),

  // Skills
  listSkills: async (customerId: string): Promise<Skill[]> => {
    const response = await request<SkillsListResponse>(`/customers/${customerId}/skills`)
    return response.skills
  },

  createSkill: (customerId: string, payload: SkillCreatePayload): Promise<Skill> =>
    request<Skill>(`/customers/${customerId}/skills`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateSkill: (customerId: string, name: string, payload: SkillUpdatePayload): Promise<Skill> =>
    request<Skill>(`/customers/${customerId}/skills/${name}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteSkill: (customerId: string, name: string): Promise<void> =>
    request<void>(`/customers/${customerId}/skills/${name}`, { method: 'DELETE' }),

  getSkillContent: (customerId: string, name: string): Promise<SkillContent> =>
    request<SkillContent>(`/skills/${name}/content?customer_id=${customerId}`),

  updateConnectionSkillsOverride: (
    connectionId: string,
    payload: ConnectionSkillsOverridePayload,
  ): Promise<Connection> =>
    request<Connection>(`/connections/${connectionId}/skills-override`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  // Agent Runs
  getRemediationPolicy: async (customerId: string): Promise<RemediationPolicy | null> => {
    try {
      return await request<RemediationPolicy>(`/customers/${customerId}/remediation-policy`)
    } catch (err) {
      // 404 means no policy configured yet — return null gracefully
      if (err instanceof Error && err.message.includes('404')) return null
      throw err
    }
  },

  upsertRemediationPolicy: (
    customerId: string,
    payload: RemediationPolicyUpsertPayload,
  ): Promise<RemediationPolicy> =>
    request<RemediationPolicy>(`/customers/${customerId}/remediation-policy`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteRemediationPolicy: (customerId: string): Promise<void> =>
    request<void>(`/customers/${customerId}/remediation-policy`, { method: 'DELETE' }),

  estimateAgentRunCost: (scanId: string): Promise<AgentRunCostEstimate> =>
    request<AgentRunCostEstimate>(`/scans/${scanId}/agent-run-estimate`),

  triggerAgentRun: (scanId: string, payload: AgentRunTriggerPayload): Promise<AgentRun> =>
    request<AgentRun>(`/scans/${scanId}/agent-runs`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listAgentRuns: async (filters?: {
    scan_id?: string
    customer_id?: string
    status?: string
    since?: string
    limit?: number
    offset?: number
  }): Promise<AgentRun[]> => {
    const params = new URLSearchParams()
    if (filters?.scan_id) params.set('scan_id', filters.scan_id)
    if (filters?.customer_id) params.set('customer_id', filters.customer_id)
    if (filters?.status) params.set('status', filters.status)
    if (filters?.since) params.set('since', filters.since)
    if (filters?.limit) params.set('limit', String(filters.limit))
    if (filters?.offset) params.set('offset', String(filters.offset))
    const qs = params.toString()
    return request<AgentRun[]>(`/agent-runs${qs ? `?${qs}` : ''}`)
  },

  getAgentRun: (id: string): Promise<AgentRunDetailed> =>
    request<AgentRunDetailed>(`/agent-runs/${id}`),

  cancelAgentRun: (id: string): Promise<AgentRun> =>
    request<AgentRun>(`/agent-runs/${id}/cancel`, { method: 'POST' }),

  // Global Settings
  getGlobalSettings: (): Promise<GlobalSettings> =>
    request<GlobalSettings>('/settings'),

  updateGlobalSettings: (payload: GlobalSettingsUpdate): Promise<GlobalSettings> =>
    request<GlobalSettings>('/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
}

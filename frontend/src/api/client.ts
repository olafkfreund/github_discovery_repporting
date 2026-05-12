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
import type { AgentInstructions, AgentInstructionsUpsertPayload } from '../types/agentInstructions'
import type {
  LLMConnection,
  LLMConnectionCreatePayload,
  LLMConnectionUpdatePayload,
  LLMConnectionValidatePayload,
  LLMConnectionValidateResult,
} from '../types/llm'

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
}

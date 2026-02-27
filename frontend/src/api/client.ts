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
} from '../types'

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

  // Scans
  triggerScan: (customerId: string, connectionId: string) =>
    request<Scan>(`/customers/${customerId}/scans`, {
      method: 'POST',
      body: JSON.stringify({ connection_id: connectionId }),
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

  // Dashboard
  getStats: () =>
    request<DashboardStats>('/dashboard/stats'),

  getRecentScans: () =>
    request<Scan[]>('/dashboard/recent-scans'),
}

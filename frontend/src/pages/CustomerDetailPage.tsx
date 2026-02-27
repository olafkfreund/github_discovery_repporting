import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import type {
  Customer,
  Connection,
  Scan,
  Report,
  ConnectionCreatePayload,
  ConnectionUpdatePayload,
} from '../types'

// ── Status badge ──────────────────────────────────────────────────────────────

const SCAN_STATUS_CLASSES: Record<string, string> = {
  completed: 'bg-green-100 text-green-800',
  scanning: 'bg-blue-100 text-blue-800',
  analyzing: 'bg-blue-100 text-blue-800',
  generating_report: 'bg-purple-100 text-purple-800',
  pending: 'bg-gray-100 text-gray-700',
  failed: 'bg-red-100 text-red-800',
}

function ScanBadge({ status }: { status: Scan['status'] }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${SCAN_STATUS_CLASSES[status] ?? 'bg-gray-100 text-gray-700'}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

const REPORT_STATUS_CLASSES: Record<string, string> = {
  completed: 'bg-green-100 text-green-800',
  generating: 'bg-blue-100 text-blue-800',
  pending: 'bg-gray-100 text-gray-700',
  failed: 'bg-red-100 text-red-800',
}

function ReportBadge({ status }: { status: Report['status'] }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${REPORT_STATUS_CLASSES[status] ?? 'bg-gray-100 text-gray-700'}`}>
      {status}
    </span>
  )
}

// ── Platform labels ───────────────────────────────────────────────────────────

const PLATFORM_LABELS: Record<string, string> = {
  github: 'GitHub',
  gitlab: 'GitLab',
  azure_devops: 'Azure DevOps',
}

// ── Add connection form ───────────────────────────────────────────────────────

interface AddConnectionFormProps {
  customerId: string
  onCreated: (conn: Connection) => void
  onCancel: () => void
}

function AddConnectionForm({ customerId, onCreated, onCancel }: AddConnectionFormProps) {
  const [form, setForm] = useState({
    platform: 'github' as ConnectionCreatePayload['platform'],
    display_name: '',
    org_or_group: '',
    auth_type: 'token' as ConnectionCreatePayload['auth_type'],
    token: '',
    base_url: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.display_name.trim() || !form.org_or_group.trim() || !form.token.trim()) {
      setError('Display name, organization, and token are all required')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const payload: ConnectionCreatePayload = {
        platform: form.platform,
        display_name: form.display_name.trim(),
        org_or_group: form.org_or_group.trim(),
        auth_type: form.auth_type,
        credentials: form.token.trim(),
      }
      if (form.base_url?.trim()) payload.base_url = form.base_url.trim()
      const created = await api.addConnection(customerId, payload)
      onCreated(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add connection')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-5 mt-4">
      <h4 className="text-sm font-semibold text-gray-800 mb-4">Add Platform Connection</h4>
      {error && (
        <div className="mb-3 bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">{error}</div>
      )}
      <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Platform</label>
            <select
              value={form.platform}
              onChange={(e) => setForm((f) => ({ ...f, platform: e.target.value as ConnectionCreatePayload['platform'] }))}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                         focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="github">GitHub</option>
              <option value="gitlab">GitLab</option>
              <option value="azure_devops">Azure DevOps</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Display Name</label>
            <input
              type="text"
              value={form.display_name}
              onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
              placeholder="My GitHub Org"
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                         focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              required
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Organization / Group</label>
          <input
            type="text"
            value={form.org_or_group}
            onChange={(e) => setForm((f) => ({ ...f, org_or_group: e.target.value }))}
            placeholder="my-org-name"
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                       focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            required
          />
        </div>
        {form.platform !== 'github' && (
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Base URL</label>
            <input
              type="url"
              value={form.base_url ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
              placeholder="https://gitlab.mycompany.com"
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                         focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        )}
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Access Token</label>
          <input
            type="password"
            value={form.token}
            onChange={(e) => setForm((f) => ({ ...f, token: e.target.value }))}
            placeholder="ghp_…"
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                       focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            required
          />
        </div>
        <div className="flex gap-3 pt-1">
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md
                       hover:bg-indigo-700 disabled:opacity-50
                       focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            {submitting ? 'Adding…' : 'Add Connection'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md
                       border border-gray-300 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

// ── Edit connection form ─────────────────────────────────────────────────────

interface EditConnectionFormProps {
  connection: Connection
  onUpdated: (conn: Connection) => void
  onCancel: () => void
}

function EditConnectionForm({ connection, onUpdated, onCancel }: EditConnectionFormProps) {
  const [form, setForm] = useState({
    display_name: connection.display_name,
    org_or_group: connection.org_or_group,
    auth_type: connection.auth_type as ConnectionUpdatePayload['auth_type'],
    token: '',
    base_url: connection.base_url ?? '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.display_name.trim() || !form.org_or_group.trim()) {
      setError('Display name and organization are required')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const payload: ConnectionUpdatePayload = {}
      if (form.display_name.trim() !== connection.display_name) {
        payload.display_name = form.display_name.trim()
      }
      if (form.org_or_group.trim() !== connection.org_or_group) {
        payload.org_or_group = form.org_or_group.trim()
      }
      if (form.auth_type !== connection.auth_type) {
        payload.auth_type = form.auth_type
      }
      if (form.token.trim()) {
        payload.credentials = form.token.trim()
      }
      const newBaseUrl = form.base_url?.trim() || null
      if (newBaseUrl !== (connection.base_url ?? null)) {
        payload.base_url = newBaseUrl
      }
      if (Object.keys(payload).length === 0) {
        setError('No changes detected')
        setSubmitting(false)
        return
      }
      const updated = await api.updateConnection(connection.id, payload)
      onUpdated(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update connection')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-5 mt-2">
      <h4 className="text-sm font-semibold text-gray-800 mb-4">
        Edit Connection: {connection.display_name}
      </h4>
      {error && (
        <div className="mb-3 bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">{error}</div>
      )}
      <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Platform</label>
            <input
              type="text"
              value={PLATFORM_LABELS[connection.platform] ?? connection.platform}
              disabled
              className="block w-full rounded-md border border-gray-200 bg-gray-100 px-3 py-2 text-sm text-gray-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Display Name</label>
            <input
              type="text"
              value={form.display_name}
              onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                         focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              required
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Organization / Group</label>
          <input
            type="text"
            value={form.org_or_group}
            onChange={(e) => setForm((f) => ({ ...f, org_or_group: e.target.value }))}
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                       focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            required
          />
        </div>
        {connection.platform !== 'github' && (
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Base URL</label>
            <input
              type="url"
              value={form.base_url}
              onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
              placeholder="https://gitlab.mycompany.com"
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                         focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        )}
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            New Access Token <span className="text-gray-400 font-normal">(leave blank to keep current)</span>
          </label>
          <input
            type="password"
            value={form.token}
            onChange={(e) => setForm((f) => ({ ...f, token: e.target.value }))}
            placeholder="Enter new token to update..."
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                       focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div className="flex gap-3 pt-1">
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 bg-amber-600 text-white text-sm font-medium rounded-md
                       hover:bg-amber-700 disabled:opacity-50
                       focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2"
          >
            {submitting ? 'Saving...' : 'Save Changes'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md
                       border border-gray-300 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [connections, setConnections] = useState<Connection[]>([])
  const [scans, setScans] = useState<Scan[]>([])
  const [reports, setReports] = useState<Report[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [showAddConnection, setShowAddConnection] = useState(false)
  const [editingConnId, setEditingConnId] = useState<string | null>(null)
  const [validatingId, setValidatingId] = useState<string | null>(null)
  const [deletingConnId, setDeletingConnId] = useState<string | null>(null)

  const [showScanForm, setShowScanForm] = useState(false)
  const [selectedConnectionId, setSelectedConnectionId] = useState('')
  const [triggeringScan, setTriggeringScan] = useState(false)

  const [generatingReportScanId, setGeneratingReportScanId] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [cust, conns, scanList, reportList] = await Promise.all([
        api.getCustomer(id),
        api.listConnections(id),
        api.listScans(id),
        api.listReports(id),
      ])
      setCustomer(cust)
      setConnections(conns)
      setScans(scanList)
      setReports(reportList)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load customer')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  // Validate a connection
  const handleValidate = async (connId: string) => {
    setValidatingId(connId)
    try {
      const result = await api.validateConnection(connId)
      alert(result.valid ? `Valid: ${result.message}` : `Invalid: ${result.message}`)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Validation failed')
    } finally {
      setValidatingId(null)
    }
  }

  // Delete a connection
  const handleDeleteConnection = async (connId: string) => {
    if (!window.confirm('Delete this connection?')) return
    setDeletingConnId(connId)
    try {
      await api.deleteConnection(connId)
      setConnections((prev) => prev.filter((c) => c.id !== connId))
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete connection')
    } finally {
      setDeletingConnId(null)
    }
  }

  // Trigger a scan
  const handleTriggerScan = async () => {
    if (!id || !selectedConnectionId) return
    setTriggeringScan(true)
    try {
      const scan = await api.triggerScan(id, selectedConnectionId)
      setScans((prev) => [scan, ...prev])
      setShowScanForm(false)
      setSelectedConnectionId('')
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to trigger scan')
    } finally {
      setTriggeringScan(false)
    }
  }

  // Generate a report for a scan
  const handleGenerateReport = async (scanId: string) => {
    setGeneratingReportScanId(scanId)
    try {
      const report = await api.generateReport(scanId)
      setReports((prev) => [report, ...prev])
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to generate report')
    } finally {
      setGeneratingReportScanId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    )
  }

  if (error || !customer) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-700 font-medium">Error loading customer</p>
        <p className="text-red-600 text-sm mt-1">{error ?? 'Customer not found'}</p>
        <Link to="/customers" className="mt-3 inline-block text-red-700 underline text-sm">
          Back to Customers
        </Link>
      </div>
    )
  }

  const activeConnections = connections.filter((c) => c.is_active)

  return (
    <div className="space-y-8">
      {/* Breadcrumb */}
      <nav className="text-sm">
        <Link to="/customers" className="text-indigo-600 hover:text-indigo-700">
          Customers
        </Link>
        <span className="mx-2 text-gray-400">/</span>
        <span className="text-gray-700 font-medium">{customer.name}</span>
      </nav>

      {/* Customer info */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">{customer.name}</h2>
            <p className="text-sm font-mono text-gray-400 mt-1">{customer.slug}</p>
          </div>
        </div>
        <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider font-medium">Contact Email</dt>
            <dd className="mt-1 text-sm text-gray-800">{customer.contact_email ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider font-medium">Created</dt>
            <dd className="mt-1 text-sm text-gray-800">{new Date(customer.created_at).toLocaleDateString()}</dd>
          </div>
          {customer.notes && (
            <div className="sm:col-span-2">
              <dt className="text-xs text-gray-500 uppercase tracking-wider font-medium">Notes</dt>
              <dd className="mt-1 text-sm text-gray-800 whitespace-pre-wrap">{customer.notes}</dd>
            </div>
          )}
        </dl>
      </div>

      {/* Connections */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-800">Platform Connections</h3>
          <button
            onClick={() => setShowAddConnection((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-sm
                       font-medium rounded-md hover:bg-indigo-700"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            Add Connection
          </button>
        </div>
        <div className="p-6">
          {showAddConnection && (
            <AddConnectionForm
              customerId={customer.id}
              onCreated={(conn) => {
                setConnections((prev) => [...prev, conn])
                setShowAddConnection(false)
              }}
              onCancel={() => setShowAddConnection(false)}
            />
          )}
          {connections.length === 0 && !showAddConnection ? (
            <p className="text-sm text-gray-500 text-center py-4">
              No connections yet. Add a platform connection to enable scanning.
            </p>
          ) : (
            <div className="space-y-3 mt-4">
              {connections.map((conn) => (
                <div key={conn.id}>
                  <div className="flex items-center justify-between p-4 rounded-lg border border-gray-200 bg-gray-50">
                    <div className="flex items-center gap-3">
                      <div className={`w-2 h-2 rounded-full ${conn.is_active ? 'bg-green-500' : 'bg-gray-300'}`} />
                      <div>
                        <p className="text-sm font-medium text-gray-900">{conn.display_name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {PLATFORM_LABELS[conn.platform] ?? conn.platform} · {conn.org_or_group}
                          {conn.base_url && ` · ${conn.base_url}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setEditingConnId(editingConnId === conn.id ? null : conn.id)}
                        className="px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50
                                   border border-amber-200 rounded-md hover:bg-amber-100"
                      >
                        {editingConnId === conn.id ? 'Cancel Edit' : 'Edit'}
                      </button>
                      <button
                        onClick={() => { void handleValidate(conn.id) }}
                        disabled={validatingId === conn.id}
                        className="px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50
                                   border border-indigo-200 rounded-md hover:bg-indigo-100
                                   disabled:opacity-50"
                      >
                        {validatingId === conn.id ? 'Validating...' : 'Validate'}
                      </button>
                      <button
                        onClick={() => { void handleDeleteConnection(conn.id) }}
                        disabled={deletingConnId === conn.id}
                        className="px-3 py-1.5 text-xs font-medium text-red-700 bg-red-50
                                   border border-red-200 rounded-md hover:bg-red-100
                                   disabled:opacity-50"
                      >
                        {deletingConnId === conn.id ? 'Deleting...' : 'Delete'}
                      </button>
                    </div>
                  </div>
                  {editingConnId === conn.id && (
                    <EditConnectionForm
                      connection={conn}
                      onUpdated={(updated) => {
                        setConnections((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
                        setEditingConnId(null)
                      }}
                      onCancel={() => setEditingConnId(null)}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Scans */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-800">Scan History</h3>
          <button
            onClick={() => setShowScanForm((v) => !v)}
            disabled={activeConnections.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-sm
                       font-medium rounded-md hover:bg-indigo-700
                       disabled:opacity-50 disabled:cursor-not-allowed"
            title={activeConnections.length === 0 ? 'Add a connection first' : undefined}
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            New Scan
          </button>
        </div>
        <div className="p-6">
          {/* Scan trigger form */}
          {showScanForm && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-end gap-4">
              <div className="flex-1">
                <label className="block text-xs font-medium text-gray-700 mb-1">Select Connection</label>
                <select
                  value={selectedConnectionId}
                  onChange={(e) => setSelectedConnectionId(e.target.value)}
                  className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                             focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="">— choose connection —</option>
                  {activeConnections.map((c) => (
                    <option key={c.id} value={c.id}>{c.display_name}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={() => { void handleTriggerScan() }}
                disabled={!selectedConnectionId || triggeringScan}
                className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md
                           hover:bg-indigo-700 disabled:opacity-50"
              >
                {triggeringScan ? 'Starting…' : 'Start Scan'}
              </button>
              <button
                onClick={() => { setShowScanForm(false); setSelectedConnectionId('') }}
                className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md
                           border border-gray-300 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          )}

          {scans.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">No scans yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Repos</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Completed</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {scans.map((scan) => (
                    <tr key={scan.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <ScanBadge status={scan.status} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">{scan.total_repos}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {scan.started_at ? new Date(scan.started_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {scan.completed_at ? new Date(scan.completed_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-3">
                          {scan.status === 'completed' && (
                            <button
                              onClick={() => { void handleGenerateReport(scan.id) }}
                              disabled={generatingReportScanId === scan.id}
                              className="text-xs font-medium text-green-700 hover:text-green-800
                                         disabled:opacity-50"
                            >
                              {generatingReportScanId === scan.id ? 'Generating…' : 'Generate Report'}
                            </button>
                          )}
                          <Link
                            to={`/scans/${scan.id}`}
                            className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
                          >
                            View
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Reports */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800">Reports</h3>
        </div>
        <div className="p-6">
          {reports.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">
              No reports yet. Complete a scan and generate a report.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Title</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">DORA Level</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Generated</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {reports.map((report) => (
                    <tr key={report.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-medium text-gray-900">{report.title}</td>
                      <td className="px-4 py-3">
                        <ReportBadge status={report.status} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {report.overall_score != null ? `${Math.round(report.overall_score)}%` : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">{report.dora_level ?? '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {new Date(report.generated_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {report.status === 'completed' && report.pdf_path && (
                          <a
                            href={api.downloadReport(report.id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
                          >
                            Download PDF
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

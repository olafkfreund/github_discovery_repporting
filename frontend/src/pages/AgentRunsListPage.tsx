// AgentRunsListPage — real table view for /agents (issue #29)
//
// Features:
//   - Filters: customer dropdown, status dropdown, time-window dropdown, search
//   - 5s polling while any row has a non-terminal status (pending/running/opening_pr)
//   - Polling pauses when tab is hidden
//   - Row click navigates to /agents/:id
//   - Empty states for filtered-no-results vs truly-no-runs
//
// NOTE: AgentRun does not carry customer_id directly in v1. The Customer column
// is omitted for now. A follow-up issue should join customer via scan_id.

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { AgentRun, AgentRunStatus } from '../types/agents'
import type { Customer } from '../types'
import { AgentRunStatusBadge } from '../components/ui/AgentStatusBadge'
import { Spinner } from '../components/ui/Spinner'
import { ErrorPanel } from '../components/ui/ErrorPanel'
import { formatRelative, formatDuration } from '../utils/format'

// Statuses that indicate an agent run is still active and needs polling
const ACTIVE_STATUSES = new Set<AgentRunStatus>(['pending', 'running', 'opening_pr'])

type WindowOption = '24h' | '7d' | '30d' | 'all'

const WINDOW_LABELS: Record<WindowOption, string> = {
  '24h': 'Last 24 hours',
  '7d': 'Last 7 days',
  '30d': 'Last 30 days',
  'all': 'All time',
}

const ALL_STATUSES: Array<{ value: AgentRunStatus | ''; label: string }> = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'opening_pr', label: 'Opening PR' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

function sinceFromWindow(window: WindowOption): string | undefined {
  if (window === 'all') return undefined
  const now = Date.now()
  const offsets: Record<WindowOption, number> = {
    '24h': 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
    'all': 0,
  }
  return new Date(now - offsets[window]).toISOString()
}

export default function AgentRunsListPage() {
  const navigate = useNavigate()

  // Filter state
  const [customerId, setCustomerId] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<AgentRunStatus | ''>('')
  const [window, setWindow] = useState<WindowOption>('7d')
  const [search, setSearch] = useState<string>('')

  // Data
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Load customers once for the dropdown
  useEffect(() => {
    api.listCustomers()
      .then(setCustomers)
      .catch(() => { /* non-fatal: filter just won't show customer names */ })
  }, [])

  // Load runs based on server-side filters
  const loadRuns = useCallback(async () => {
    setError(null)
    try {
      const since = sinceFromWindow(window)
      const data = await api.listAgentRuns({
        ...(customerId ? { customer_id: customerId } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(since ? { since } : {}),
        limit: 200,
      })
      setRuns(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent runs')
    } finally {
      setLoading(false)
    }
  }, [customerId, statusFilter, window])

  // Initial load + reload on filter changes
  useEffect(() => {
    setLoading(true)
    void loadRuns()
  }, [loadRuns])

  // 5s polling while any active run exists; pauses when tab hidden
  const hasActiveRun = runs.some((r) => ACTIVE_STATUSES.has(r.status))
  useEffect(() => {
    if (!hasActiveRun) return

    let interval: ReturnType<typeof setInterval> | null = null

    const start = () => {
      interval = setInterval(() => { void loadRuns() }, 5000)
    }
    const stop = () => {
      if (interval) { clearInterval(interval); interval = null }
    }
    const onVisibility = () => {
      if (document.hidden) stop(); else if (!interval) start()
    }

    start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => { stop(); document.removeEventListener('visibilitychange', onVisibility) }
  }, [hasActiveRun, loadRuns])

  // Client-side search on id and scan_id prefix
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return runs
    return runs.filter(
      (r) =>
        r.id.toLowerCase().includes(q) ||
        r.scan_id.toLowerCase().startsWith(q)
    )
  }, [runs, search])

  const handleRowKeyDown = (e: React.KeyboardEvent, id: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      navigate(`/agents/${id}`)
    }
  }

  return (
    <div>
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-brand-800">Agents Running</h1>
        <p className="mt-1 text-sm text-gray-500">
          Live and historical agent runs across all customers.
        </p>
      </div>

      {/* Filter bar */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-4">
        <div className="flex flex-col gap-3
                        sm:flex-row sm:flex-wrap sm:items-end sm:gap-4">
          {/* Customer filter */}
          <div>
            <label
              htmlFor="filter-customer"
              className="block text-xs font-medium text-gray-600 mb-1"
            >
              Customer
            </label>
            <select
              id="filter-customer"
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              className="block rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm
                         focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">All customers</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>

          {/* Status filter */}
          <div>
            <label
              htmlFor="filter-status"
              className="block text-xs font-medium text-gray-600 mb-1"
            >
              Status
            </label>
            <select
              id="filter-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as AgentRunStatus | '')}
              className="block rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm
                         focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              {ALL_STATUSES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          {/* Time window filter */}
          <div>
            <label
              htmlFor="filter-window"
              className="block text-xs font-medium text-gray-600 mb-1"
            >
              Window
            </label>
            <select
              id="filter-window"
              value={window}
              onChange={(e) => setWindow(e.target.value as WindowOption)}
              className="block rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm
                         focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              {(Object.keys(WINDOW_LABELS) as WindowOption[]).map((w) => (
                <option key={w} value={w}>{WINDOW_LABELS[w]}</option>
              ))}
            </select>
          </div>

          {/* Search */}
          <div className="flex-1 min-w-48">
            <label
              htmlFor="filter-search"
              className="block text-xs font-medium text-gray-600 mb-1"
            >
              Search
            </label>
            <input
              id="filter-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Run ID or scan ID prefix…"
              className="block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm
                         focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {/* Reload button */}
          <div>
            <button
              onClick={() => { setLoading(true); void loadRuns() }}
              className="px-3 py-1.5 text-sm font-medium rounded-md border border-gray-300
                         bg-white text-gray-700 hover:bg-gray-50
                         focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1"
              aria-label="Reload agent runs"
            >
              Reload
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <Spinner className="h-48" />
      ) : error ? (
        <ErrorPanel message={error} onRetry={() => { setLoading(true); void loadRuns() }} />
      ) : filtered.length === 0 ? (
        runs.length === 0 ? (
          /* No runs anywhere */
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <svg
              className="mx-auto h-12 w-12 text-gray-300"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <p className="mt-4 text-gray-500 font-medium">No agent runs yet</p>
            <p className="text-gray-400 text-sm mt-1">
              Trigger remediation from a completed scan.
            </p>
            <Link
              to="/customers"
              className="mt-4 inline-block px-4 py-2 bg-brand-600 text-white text-sm font-medium
                         rounded-md hover:bg-brand-700"
            >
              Go to Customers
            </Link>
          </div>
        ) : (
          /* Filters match nothing */
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500 font-medium">
              No agent runs match the current filters.
            </p>
            <p className="text-gray-400 text-sm mt-1">
              Try changing the status, time window, or search query.
            </p>
            <Link
              to="/customers"
              className="mt-4 inline-block text-sm text-brand-700 underline hover:no-underline"
            >
              Browse customers
            </Link>
          </div>
        )
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  Status
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  Scan
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  Model
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  Started
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  Dur
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  PRs
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  Cost
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filtered.map((run) => (
                <tr
                  key={run.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/agents/${run.id}`)}
                  onKeyDown={(e) => handleRowKeyDown(e, run.id)}
                  className="hover:bg-gray-50 cursor-pointer focus:outline-none focus:bg-brand-50"
                >
                  <td className="px-4 py-3 whitespace-nowrap">
                    <AgentRunStatusBadge status={run.status} />
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <Link
                      to={`/scans/${run.scan_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-mono text-xs text-brand-700 hover:underline"
                      title={run.scan_id}
                    >
                      {run.scan_id.slice(0, 7)}&hellip;
                    </Link>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <code className="text-xs text-gray-700 bg-gray-100 px-1.5 py-0.5 rounded">
                      {run.model}
                    </code>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                    {formatRelative(run.started_at)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 font-mono">
                    {formatDuration(run.started_at, run.finished_at)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 text-right">
                    {/* pr_count not yet in AgentRun v1 schema — defaulting to 0; see issue #30 */}
                    0
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 text-right">
                    ${run.total_cost_usd.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {hasActiveRun && (
            <p className="px-4 py-2 bg-blue-50 text-xs text-blue-700 border-t border-blue-100">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse mr-1.5 align-middle" aria-hidden="true" />
              Live — refreshing every 5 seconds
            </p>
          )}
        </div>
      )}
    </div>
  )
}

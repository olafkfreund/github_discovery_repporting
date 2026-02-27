import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Scan, ScanScore, Finding } from '../types'

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_CLASSES: Record<string, string> = {
  completed: 'bg-green-100 text-green-800',
  scanning: 'bg-blue-100 text-blue-800',
  analyzing: 'bg-blue-100 text-blue-800',
  generating_report: 'bg-purple-100 text-purple-800',
  pending: 'bg-gray-100 text-gray-700',
  failed: 'bg-red-100 text-red-800',
}

function ScanBadge({ status }: { status: Scan['status'] }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${STATUS_CLASSES[status] ?? 'bg-gray-100 text-gray-700'}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

// ── Severity badge ────────────────────────────────────────────────────────────

const SEVERITY_CLASSES: Record<string, string> = {
  critical: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-blue-100 text-blue-800',
  info: 'bg-gray-100 text-gray-700',
}

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${SEVERITY_CLASSES[severity.toLowerCase()] ?? 'bg-gray-100 text-gray-700'}`}>
      {severity}
    </span>
  )
}

// ── Finding status badge ──────────────────────────────────────────────────────

const FINDING_STATUS_CLASSES: Record<string, string> = {
  pass: 'bg-green-100 text-green-800',
  fail: 'bg-red-100 text-red-800',
  warning: 'bg-yellow-100 text-yellow-800',
  na: 'bg-gray-100 text-gray-500',
}

function FindingStatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${FINDING_STATUS_CLASSES[status.toLowerCase()] ?? 'bg-gray-100 text-gray-700'}`}>
      {status}
    </span>
  )
}

// ── Score progress bar ────────────────────────────────────────────────────────

function ScoreBar({ score }: ScanScore) {
  const pct = score > 0 ? Math.round((score / 100) * 100) : 0
  const barColor =
    pct >= 80 ? 'bg-green-500' : pct >= 60 ? 'bg-yellow-500' : 'bg-red-500'

  return (
    <div className="flex items-center gap-4">
      <div className="flex-1 bg-gray-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm font-semibold text-gray-700 w-12 text-right">{score.toFixed(0)}</span>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

const ALL_OPTION = '__all__'

export default function ScanDetailPage() {
  const { id } = useParams<{ id: string }>()

  const [scan, setScan] = useState<Scan | null>(null)
  const [scores, setScores] = useState<ScanScore[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [generatingReport, setGeneratingReport] = useState(false)
  const [reportMessage, setReportMessage] = useState<string | null>(null)

  // Filters
  const [filterCategory, setFilterCategory] = useState(ALL_OPTION)
  const [filterSeverity, setFilterSeverity] = useState(ALL_OPTION)
  const [filterStatus, setFilterStatus] = useState(ALL_OPTION)

  const loadAll = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [scanData, scoresData, findingsData] = await Promise.all([
        api.getScan(id),
        api.getScanScores(id),
        api.getScanFindings(id),
      ])
      setScan(scanData)
      setScores(scoresData)
      setFindings(findingsData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scan')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const handleGenerateReport = async () => {
    if (!id) return
    setGeneratingReport(true)
    setReportMessage(null)
    try {
      const report = await api.generateReport(id)
      setReportMessage(`Report "${report.title}" queued successfully (ID: ${report.id.slice(0, 8)}…)`)
    } catch (err) {
      setReportMessage(err instanceof Error ? err.message : 'Failed to generate report')
    } finally {
      setGeneratingReport(false)
    }
  }

  // Derive unique filter options
  const categories = [ALL_OPTION, ...new Set(findings.map((f) => f.category))]
  const severities = [ALL_OPTION, ...new Set(findings.map((f) => f.severity))]
  const statuses = [ALL_OPTION, ...new Set(findings.map((f) => f.status))]

  const filteredFindings = findings.filter((f) => {
    if (filterCategory !== ALL_OPTION && f.category !== filterCategory) return false
    if (filterSeverity !== ALL_OPTION && f.severity !== filterSeverity) return false
    if (filterStatus !== ALL_OPTION && f.status !== filterStatus) return false
    return true
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    )
  }

  if (error || !scan) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-700 font-medium">Error loading scan</p>
        <p className="text-red-600 text-sm mt-1">{error ?? 'Scan not found'}</p>
        <Link to="/customers" className="mt-3 inline-block text-red-700 underline text-sm">
          Back to Customers
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Breadcrumb */}
      <nav className="text-sm">
        <Link to="/customers" className="text-indigo-600 hover:text-indigo-700">Customers</Link>
        <span className="mx-2 text-gray-400">/</span>
        <Link to={`/customers/${scan.customer_id}`} className="text-indigo-600 hover:text-indigo-700">
          Customer
        </Link>
        <span className="mx-2 text-gray-400">/</span>
        <span className="text-gray-700 font-medium">Scan {scan.id.slice(0, 8)}…</span>
      </nav>

      {/* Scan summary */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-gray-900">Scan Details</h2>
              <ScanBadge status={scan.status} />
            </div>
            <p className="text-sm font-mono text-gray-400 mt-1">{scan.id}</p>
          </div>
          {scan.status === 'completed' && (
            <div>
              {reportMessage && (
                <p className="text-xs text-gray-600 mb-2 max-w-xs text-right">{reportMessage}</p>
              )}
              <button
                onClick={() => { void handleGenerateReport() }}
                disabled={generatingReport}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm
                           font-medium rounded-md hover:bg-green-700 disabled:opacity-50"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                {generatingReport ? 'Generating…' : 'Generate Report'}
              </button>
            </div>
          )}
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider font-medium">Total Repos</dt>
            <dd className="mt-1 text-2xl font-bold text-gray-800">{scan.total_repos}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider font-medium">Started</dt>
            <dd className="mt-1 text-sm text-gray-700">
              {scan.started_at ? new Date(scan.started_at).toLocaleString() : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider font-medium">Completed</dt>
            <dd className="mt-1 text-sm text-gray-700">
              {scan.completed_at ? new Date(scan.completed_at).toLocaleString() : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider font-medium">Findings</dt>
            <dd className="mt-1 text-2xl font-bold text-gray-800">{findings.length}</dd>
          </div>
        </dl>

        {scan.error_message && (
          <div className="mt-4 bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
            <span className="font-medium">Error: </span>{scan.error_message}
          </div>
        )}
      </div>

      {/* Category scores */}
      {scores.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-5">Category Scores</h3>
          <div className="space-y-4">
            {scores.map((s) => (
              <div key={s.id}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-gray-700 capitalize">
                      {s.category.replace(/_/g, ' ')}
                    </span>
                    <span className="text-xs text-gray-400">weight: {(s.weight * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    <span className="text-green-600 font-medium">{s.pass_count} pass</span>
                    <span className="text-red-600 font-medium">{s.fail_count} fail</span>
                    <span>{s.finding_count} total</span>
                  </div>
                </div>
                <ScoreBar {...s} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Findings */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-lg font-semibold text-gray-800">
              Findings
              <span className="ml-2 text-sm font-normal text-gray-400">
                ({filteredFindings.length} of {findings.length})
              </span>
            </h3>
            {/* Filters */}
            <div className="flex flex-wrap gap-2">
              <select
                value={filterCategory}
                onChange={(e) => setFilterCategory(e.target.value)}
                className="text-xs rounded-md border border-gray-300 px-2 py-1.5
                           focus:border-indigo-500 focus:outline-none"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>{c === ALL_OPTION ? 'All categories' : c.replace(/_/g, ' ')}</option>
                ))}
              </select>
              <select
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value)}
                className="text-xs rounded-md border border-gray-300 px-2 py-1.5
                           focus:border-indigo-500 focus:outline-none"
              >
                {severities.map((s) => (
                  <option key={s} value={s}>{s === ALL_OPTION ? 'All severities' : s}</option>
                ))}
              </select>
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="text-xs rounded-md border border-gray-300 px-2 py-1.5
                           focus:border-indigo-500 focus:outline-none"
              >
                {statuses.map((s) => (
                  <option key={s} value={s}>{s === ALL_OPTION ? 'All statuses' : s}</option>
                ))}
              </select>
              {(filterCategory !== ALL_OPTION || filterSeverity !== ALL_OPTION || filterStatus !== ALL_OPTION) && (
                <button
                  onClick={() => {
                    setFilterCategory(ALL_OPTION)
                    setFilterSeverity(ALL_OPTION)
                    setFilterStatus(ALL_OPTION)
                  }}
                  className="text-xs text-indigo-600 hover:text-indigo-700 font-medium px-2 py-1.5"
                >
                  Clear filters
                </button>
              )}
            </div>
          </div>
        </div>

        {filteredFindings.length === 0 ? (
          <div className="px-6 py-10 text-center text-sm text-gray-500">
            {findings.length === 0 ? 'No findings for this scan.' : 'No findings match the current filters.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Check</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Severity</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Detail</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredFindings.map((finding) => (
                  <tr key={finding.id} className="hover:bg-gray-50 align-top">
                    <td className="px-4 py-3">
                      <p className="text-sm font-medium text-gray-900">{finding.check_name}</p>
                      <p className="text-xs text-gray-400 font-mono mt-0.5">{finding.check_id}</p>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {finding.category.replace(/_/g, ' ')}
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={finding.severity} />
                    </td>
                    <td className="px-4 py-3">
                      <FindingStatusBadge status={finding.status} />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700 font-mono">
                      {finding.score.toFixed(1)} / {finding.weight.toFixed(1)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 max-w-xs">
                      {finding.detail ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, useCallback, useRef } from 'react'
import { useSettingsCustomerId } from '../../hooks/useSettingsCustomerId'
import { api } from '../../api/client'
import type { LLMConnection } from '../../types/llm'
import type { CostStatus } from '../../types/agents'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorPanel } from '../../components/ui/ErrorPanel'
import { ConfirmDialog } from '../../components/ui/ConfirmDialog'
import { SpendProgressBar } from '../../components/ui/SpendProgressBar'
import LLMConnectionTable from '../../components/settings/LLMConnectionTable'
import LLMConnectionForm from '../../components/settings/LLMConnectionForm'
import { formatDate, nextMonthStart } from '../../utils/format'

export default function LLMProvidersPage() {
  const customerId = useSettingsCustomerId()

  const [connections, setConnections] = useState<LLMConnection[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [costStatus, setCostStatus] = useState<CostStatus | null>(null)

  const [isDrawerOpen, setIsDrawerOpen] = useState(false)
  const [editingConnection, setEditingConnection] = useState<LLMConnection | null>(null)

  const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string } | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Ref to the Add provider button — used to return focus after drawer closes
  const addButtonRef = useRef<HTMLButtonElement>(null)

  const loadConnections = useCallback(async (id: string) => {
    setLoading(true)
    setError(null)
    try {
      const [data, status] = await Promise.all([
        api.listLLMConnections(id),
        api.getCostStatus(id).catch(() => null),
      ])
      setConnections(data)
      setCostStatus(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load LLM providers')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!customerId) {
      setConnections([])
      setCostStatus(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      api.listLLMConnections(customerId),
      api.getCostStatus(customerId).catch(() => null),
    ])
      .then(([data, status]) => {
        if (!cancelled) {
          setConnections(data)
          setCostStatus(status)
        }
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load LLM providers')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [customerId])

  const openAdd = () => {
    setEditingConnection(null)
    setIsDrawerOpen(true)
  }

  const openEdit = (conn: LLMConnection) => {
    setEditingConnection(conn)
    setIsDrawerOpen(true)
  }

  const handleSaved = (saved: LLMConnection) => {
    setConnections((prev) => {
      const existing = prev.findIndex((c) => c.id === saved.id)
      if (existing >= 0) {
        const next = [...prev]
        next[existing] = saved
        // If this connection is now default, clear others
        if (saved.is_default) {
          return next.map((c) => (c.id !== saved.id ? { ...c, is_default: false } : c))
        }
        return next
      }
      // New connection — prepend
      if (saved.is_default) {
        return [saved, ...prev.map((c) => ({ ...c, is_default: false }))]
      }
      return [saved, ...prev]
    })
    setIsDrawerOpen(false)
    setEditingConnection(null)
    // Refresh spend after save to reflect any policy changes
    if (customerId) {
      api.getCostStatus(customerId).then(setCostStatus).catch(() => null)
    }
    // Return focus to add button
    setTimeout(() => addButtonRef.current?.focus(), 100)
  }

  const handleCloseDrawer = () => {
    setIsDrawerOpen(false)
    setEditingConnection(null)
    setTimeout(() => addButtonRef.current?.focus(), 100)
  }

  const requestDelete = (id: string, name: string) => {
    setConfirmDelete({ id, name })
  }

  const performDelete = async () => {
    if (!confirmDelete) return
    setDeleting(true)
    const { id } = confirmDelete
    setConfirmDelete(null)
    try {
      await api.deleteLLMConnection(id)
      setConnections((prev) => prev.filter((c) => c.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete provider')
    } finally {
      setDeleting(false)
    }
  }

  const handleDefaultChange = () => {
    if (customerId) void loadConnections(customerId)
  }

  if (!customerId) {
    return (
      <div className="p-6">
        <ErrorPanel message="Select a customer to view LLM providers." />
      </div>
    )
  }

  const capPct =
    costStatus && costStatus.cap_usd > 0
      ? Math.round(Math.min(1, costStatus.spent_usd / costStatus.cap_usd) * 100)
      : 0

  const resetDateLabel =
    costStatus
      ? formatDate(nextMonthStart(costStatus.month_start), 'date')
      : '—'

  return (
    <div className="p-6">
      {/* Page header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">LLM Providers</h1>
          <p className="mt-1 text-sm text-gray-500">
            Configure how AI analysis and remediation reason about findings.
          </p>
        </div>
        <button
          ref={addButtonRef}
          onClick={openAdd}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-700
                     text-white text-sm font-medium rounded-md
                     focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add provider
        </button>
      </div>

      {/* Monthly spend section */}
      {costStatus === null ? null : (
        <div className="mb-6 p-4 bg-white border border-gray-200 rounded-lg">
          {costStatus.cap_usd === 0 ? (
            <p className="text-sm text-gray-500 italic">No cap configured.</p>
          ) : (
            <>
              <p className="text-sm mb-1.5">
                Monthly spend:{' '}
                <span className="font-medium text-gray-900">
                  ${costStatus.spent_usd.toFixed(2)}
                </span>
                {' '}of{' '}
                <span className="font-medium text-gray-900">
                  ${costStatus.cap_usd.toFixed(2)}
                </span>
                {' '}
                <span className="text-gray-500">({capPct}%)</span>
              </p>
              <SpendProgressBar
                spent={costStatus.spent_usd}
                cap={costStatus.cap_usd}
              />
              <p className="text-xs text-gray-500 mt-1">
                ${costStatus.remaining_usd.toFixed(2)} remaining
                {' · '}
                resets on {resetDateLabel}
              </p>
            </>
          )}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <Spinner className="h-48" />
      ) : error ? (
        <ErrorPanel message={error} onRetry={() => void loadConnections(customerId)} />
      ) : connections.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <svg
            className="mx-auto h-12 w-12 text-gray-300"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
            />
          </svg>
          <p className="mt-4 text-gray-500 font-medium">No LLM providers configured</p>
          <p className="text-gray-400 text-sm mt-1">
            Add a provider to enable AI-powered analysis for this customer.
          </p>
          <button
            onClick={openAdd}
            className="mt-4 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm
                       font-medium rounded-md
                       focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            Add provider
          </button>
        </div>
      ) : (
        <>
          <LLMConnectionTable
            connections={connections}
            onEdit={openEdit}
            onDelete={requestDelete}
            onDefaultChange={handleDefaultChange}
          />
          <p className="mt-3 text-xs text-gray-500">
            {connections.length} {connections.length === 1 ? 'connection' : 'connections'} configured
            {deleting && ' — deleting...'}
          </p>
        </>
      )}

      {/* Drawer */}
      <LLMConnectionForm
        open={isDrawerOpen}
        customerId={customerId}
        initial={editingConnection ?? undefined}
        onClose={handleCloseDrawer}
        onSaved={handleSaved}
      />

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!confirmDelete}
        title="Delete LLM Provider"
        message={`Delete "${confirmDelete?.name ?? ''}"? This action cannot be undone.`}
        onConfirm={() => { void performDelete() }}
        onCancel={() => setConfirmDelete(null)}
        confirmLabel="Delete"
        variant="danger"
      />
    </div>
  )
}

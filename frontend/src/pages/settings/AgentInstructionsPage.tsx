import { useState, useEffect, useId } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { AgentInstructions } from '../../types/agentInstructions'
import type { Connection, ConnectionUpdatePayload } from '../../types'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorPanel } from '../../components/ui/ErrorPanel'
import { ConfirmDialog } from '../../components/ui/ConfirmDialog'
import ConnectionOverrideRow from '../../components/settings/ConnectionOverrideRow'
import { formatDate } from '../../utils/format'

// ── Helpers ──────────────────────────────────────────────────────────────────

const DEFAULT_TEMPLATE = `# Agent Instructions

## Build

## Testing

## Style conventions

## Areas to avoid
`

function relativeSaved(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  if (isNaN(then)) return formatDate(dateStr)
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60_000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin} min ago`
  return formatDate(dateStr)
}

interface Draft {
  content: string
  enabled: boolean
}

function draftsEqual(a: Draft, b: Draft): boolean {
  return a.content === b.content && a.enabled === b.enabled
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AgentInstructionsPage() {
  const [searchParams] = useSearchParams()
  const customerId = searchParams.get('customer_id') ?? ''

  const [instructions, setInstructions] = useState<AgentInstructions | null>(null)
  const [draft, setDraft] = useState<Draft>({ content: DEFAULT_TEMPLATE, enabled: true })
  const [originalDraft, setOriginalDraft] = useState<Draft>({ content: DEFAULT_TEMPLATE, enabled: true })
  const [connections, setConnections] = useState<Connection[]>([])

  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)

  const textareaId = useId()
  const enabledId = useId()
  const saveStatusId = useId()

  // ── Load data ──────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!customerId) {
      setInstructions(null)
      setConnections([])
      return
    }

    let cancelled = false
    setLoading(true)
    setSaveError(null)

    Promise.all([
      api.getAgentInstructions(customerId),
      api.listConnections(customerId),
    ])
      .then(([instrData, connData]) => {
        if (cancelled) return
        const initial = instrData
          ? { content: instrData.content, enabled: instrData.enabled }
          : { content: DEFAULT_TEMPLATE, enabled: true }
        setInstructions(instrData)
        setDraft(initial)
        setOriginalDraft(initial)
        setConnections(connData)
      })
      .catch((err) => {
        if (!cancelled)
          setSaveError(err instanceof Error ? err.message : 'Failed to load data')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [customerId])

  // ── Handlers ───────────────────────────────────────────────────────────────

  async function handleSave() {
    if (!customerId || saving) return
    setSaving(true)
    setSaveError(null)
    setSaveSuccess(false)
    try {
      const saved = await api.upsertAgentInstructions(customerId, {
        content: draft.content,
        enabled: draft.enabled,
      })
      setInstructions(saved)
      setOriginalDraft({ content: saved.content, enabled: saved.enabled })
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2000)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save instructions')
    } finally {
      setSaving(false)
    }
  }

  function handleDiscard() {
    setDraft({ ...originalDraft })
    setSaveError(null)
    setSaveSuccess(false)
  }

  async function handleDelete() {
    if (!customerId) return
    setConfirmDeleteOpen(false)
    try {
      await api.deleteAgentInstructions(customerId)
      setInstructions(null)
      const reset = { content: DEFAULT_TEMPLATE, enabled: true }
      setDraft(reset)
      setOriginalDraft(reset)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to delete instructions')
    }
  }

  async function handleOverrideChange(id: string, override: string | null): Promise<void> {
    const payload: ConnectionUpdatePayload = { agent_instructions_override: override }
    const updated = await api.updateConnection(id, payload)
    setConnections((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
  }

  // ── Derived state ──────────────────────────────────────────────────────────

  const charCount = draft.content.length
  const tokenEstimate = Math.ceil(charCount / 4)
  const canSave =
    !draftsEqual(draft, originalDraft) && draft.content.trim().length > 0 && !saving

  // ── Render ─────────────────────────────────────────────────────────────────

  if (!customerId) {
    return (
      <div className="p-6">
        <ErrorPanel message="Select a customer to configure agent instructions." />
      </div>
    )
  }

  if (loading) {
    return <Spinner className="h-48" />
  }

  return (
    <div className="p-6 max-w-4xl">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Agent Instructions</h1>
        <p className="mt-1 text-sm text-gray-500">
          Injected into the remediation agent&apos;s context when the target repo has no{' '}
          <code className="text-xs font-mono bg-gray-100 px-1 rounded">AGENTS.md</code>,{' '}
          <code className="text-xs font-mono bg-gray-100 px-1 rounded">CLAUDE.md</code>,{' '}
          <code className="text-xs font-mono bg-gray-100 px-1 rounded">.cursorrules</code>, or{' '}
          <code className="text-xs font-mono bg-gray-100 px-1 rounded">.github/copilot-instructions.md</code>{' '}
          of its own. The repo&apos;s own instructions always win.
        </p>
      </div>

      {/* ── Customer default section ── */}
      <section aria-labelledby="customer-default-heading">
        <h2 id="customer-default-heading" className="text-lg font-semibold text-brand-800 mb-4">
          Customer default
        </h2>

        {/* Enabled toggle */}
        <div className="flex items-center gap-2 mb-4">
          <input
            id={enabledId}
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) => setDraft((d) => ({ ...d, enabled: e.target.checked }))}
            className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
          />
          <label htmlFor={enabledId} className="text-sm text-gray-700">
            Enable customer-level instructions
          </label>
        </div>

        {/* Error panel */}
        {saveError && (
          <div className="mb-4">
            <ErrorPanel message={saveError} />
          </div>
        )}

        {/* Textarea */}
        <div>
          <label htmlFor={textareaId} className="sr-only">
            Agent instructions content
          </label>
          <textarea
            id={textareaId}
            value={draft.content}
            onChange={(e) => setDraft((d) => ({ ...d, content: e.target.value }))}
            rows={20}
            spellCheck={false}
            className="font-mono text-sm border border-gray-300 rounded-md p-3 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full resize-y"
            aria-label="Agent instructions content"
          />
        </div>

        {/* Meta row: char count + last saved */}
        <div className="mt-1 flex items-center justify-between text-xs text-gray-500">
          <span>
            {charCount.toLocaleString()} / 100,000 chars &middot; ~{tokenEstimate.toLocaleString()} tokens
          </span>
          {instructions && (
            <span>Last saved {relativeSaved(instructions.updated_at)}</span>
          )}
        </div>

        {/* Action row */}
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={handleDiscard}
            disabled={draftsEqual(draft, originalDraft)}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md
                       hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed
                       focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            Discard changes
          </button>

          {instructions && (
            <button
              type="button"
              onClick={() => setConfirmDeleteOpen(true)}
              className="px-4 py-2 text-sm font-medium text-red-600 bg-white border border-red-300 rounded-md
                         hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
            >
              Delete instructions
            </button>
          )}

          <div className="ml-auto flex items-center gap-2">
            <span
              id={saveStatusId}
              aria-live="polite"
              className="text-xs"
            >
              {saving && <span className="text-gray-500">Saving…</span>}
              {saveSuccess && <span className="text-emerald-700">Saved</span>}
            </span>
            <button
              type="button"
              onClick={() => { void handleSave() }}
              disabled={!canSave}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-md
                         disabled:opacity-40 disabled:cursor-not-allowed
                         focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
              aria-describedby={saveStatusId}
            >
              Save
            </button>
          </div>
        </div>
      </section>

      {/* Divider */}
      <hr className="my-8 border-gray-200" />

      {/* ── Per-connection overrides section ── */}
      <section aria-labelledby="overrides-heading">
        <h2 id="overrides-heading" className="text-lg font-semibold text-brand-800 mb-1">
          Per-connection overrides
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          An override for a specific connection supersedes the customer-level instructions above.
        </p>

        {connections.length === 0 ? (
          <p className="text-sm text-gray-400 italic">
            No connections configured for this customer.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {connections.map((conn) => (
              <ConnectionOverrideRow
                key={conn.id}
                connection={conn}
                onChange={handleOverrideChange}
              />
            ))}
          </div>
        )}
      </section>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={confirmDeleteOpen}
        title="Delete Agent Instructions"
        message="This will remove the customer-level instructions. Per-connection overrides remain unchanged."
        confirmLabel="Delete"
        variant="danger"
        onConfirm={() => { void handleDelete() }}
        onCancel={() => setConfirmDeleteOpen(false)}
      />
    </div>
  )
}

// AgentRunDetailPage — SSE-driven agent run detail page (issue #30)
//
// Route: /agents/:id

import { useState, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAgentRunStream } from '../hooks/useAgentRunStream'
import type { AgentRunStatus } from '../types/agents'
import { AgentRunStatusBadge } from '../components/ui/AgentStatusBadge'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { Spinner } from '../components/ui/Spinner'
import { ErrorPanel } from '../components/ui/ErrorPanel'
import { AgentStepTimeline } from '../components/agents/AgentStepTimeline'
import { RemediationActionList } from '../components/agents/RemediationActionList'
import { RawLogPanel } from '../components/agents/RawLogPanel'
import { JumpToLivePill } from '../components/agents/JumpToLivePill'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TERMINAL_STATUSES = new Set<AgentRunStatus>(['completed', 'failed', 'cancelled'])

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return '—'
  const diff = Date.now() - new Date(dateStr).getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m ago`
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return '—'
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  const seconds = Math.floor((end - new Date(startedAt).getTime()) / 1000)
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

// ---------------------------------------------------------------------------
// LiveIndicator
// ---------------------------------------------------------------------------

interface LiveIndicatorProps {
  connectionState: 'connecting' | 'open' | 'closed' | 'error'
  onReconnect: () => void
}

function LiveIndicator({ connectionState, onReconnect }: LiveIndicatorProps) {
  if (connectionState === 'open') {
    return (
      <span
        role="status"
        aria-live="polite"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-green-700"
      >
        <span
          className="w-2 h-2 rounded-full bg-green-500 animate-pulse"
          aria-hidden="true"
        />
        Live
      </span>
    )
  }

  if (connectionState === 'connecting') {
    return (
      <span
        role="status"
        aria-live="polite"
        className="text-xs font-medium text-gray-500"
      >
        Connecting…
      </span>
    )
  }

  if (connectionState === 'error') {
    return (
      <span
        role="status"
        aria-live="polite"
        className="inline-flex items-center gap-2 text-xs font-medium text-red-600"
      >
        Disconnected — retrying…
        <button
          type="button"
          onClick={onReconnect}
          className="underline hover:no-underline focus:outline-none focus:ring-1 focus:ring-red-500 rounded"
        >
          Reconnect now
        </button>
      </span>
    )
  }

  // closed
  return (
    <span
      role="status"
      aria-live="polite"
      className="text-xs font-medium text-gray-400"
    >
      Closed
    </span>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AgentRunDetailPage() {
  const { id: runId } = useParams<{ id: string }>()
  const { run, steps, actions, connectionState, reconnect } = useAgentRunStream(runId!)

  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [followTail, setFollowTail] = useState(true)
  const [cancelError, setCancelError] = useState<string | null>(null)

  const isTerminal = run ? TERMINAL_STATUSES.has(run.status) : false
  const canCancel = run !== null && !isTerminal && !cancelling

  const handleConfirmCancel = useCallback(async () => {
    if (!runId) return
    setConfirmCancelOpen(false)
    setCancelling(true)
    setCancelError(null)
    try {
      await api.cancelAgentRun(runId)
      // SSE will receive status_change event and close itself
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : 'Cancel failed')
      setCancelling(false)
    }
  }, [runId])

  const handleJumpToLive = useCallback(() => {
    setFollowTail(true)
  }, [])

  // Initial loading state
  if (run === null && connectionState === 'connecting') {
    return (
      <div className="p-6">
        <Spinner />
      </div>
    )
  }

  // 404 / error on initial load
  if (run === null && connectionState === 'error') {
    return (
      <div className="p-6 max-w-lg">
        <ErrorPanel message="Agent run not found or could not be loaded.">
          <Link
            to="/agents"
            className="mt-3 inline-block text-red-700 underline text-sm"
          >
            ← Back to agents
          </Link>
        </ErrorPanel>
      </div>
    )
  }

  const totalTokens = run
    ? run.total_input_tokens + run.total_output_tokens
    : 0

  return (
    <div className="p-6 space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/* Back link                                                            */}
      {/* ------------------------------------------------------------------ */}
      <Link
        to="/agents"
        className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-800"
      >
        ← Back to agents
      </Link>

      {/* ------------------------------------------------------------------ */}
      {/* Header                                                               */}
      {/* ------------------------------------------------------------------ */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm space-y-3">
        {/* Title row */}
        <div
          role="status"
          aria-live="polite"
          className="flex items-center flex-wrap gap-3"
        >
          {run && <AgentRunStatusBadge status={run.status} />}
          <span className="text-sm font-mono text-gray-700">
            run #{run?.id.slice(0, 8) ?? '…'}
          </span>
          {run && (
            <span className="text-sm text-gray-500">
              {run.provider}/{run.model}
            </span>
          )}
          <LiveIndicator
            connectionState={connectionState}
            onReconnect={reconnect}
          />
        </div>

        {/* Subtitle row */}
        {run && (
          <div className="flex items-center flex-wrap gap-4 text-sm text-gray-500">
            <span>Started {formatRelative(run.started_at)}</span>
            <span>{formatDuration(run.started_at, run.finished_at)} elapsed</span>
            <span>${run.total_cost_usd.toFixed(4)}</span>
            <span>{totalTokens.toLocaleString()} tokens</span>

            {canCancel && (
              <button
                type="button"
                aria-label="Cancel agent run"
                onClick={() => setConfirmCancelOpen(true)}
                className="ml-auto px-3 py-1 text-xs font-medium text-red-700 border border-red-300
                           rounded-md hover:bg-red-50
                           focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-1
                           disabled:opacity-50"
                disabled={cancelling}
              >
                {cancelling ? 'Cancelling…' : 'Cancel run'}
              </button>
            )}
          </div>
        )}

        {cancelError && (
          <p className="text-xs text-red-600" role="alert">{cancelError}</p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Two-column body                                                      */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] xl:grid-cols-[1fr_24rem] gap-6 items-start">

        {/* Step timeline column */}
        <section aria-label="Step timeline">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Step timeline
            <span className="ml-2 text-xs font-normal text-gray-400">
              ({steps.length} step{steps.length !== 1 ? 's' : ''})
            </span>
          </h2>

          <div className="relative">
            <AgentStepTimeline
              steps={steps}
              followTail={followTail}
              onScrollChange={setFollowTail}
            />
            <JumpToLivePill
              visible={!followTail}
              onJump={handleJumpToLive}
            />
          </div>
        </section>

        {/* PRs panel column */}
        <section aria-label="Pull requests opened">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">PRs opened</h2>
          <RemediationActionList actions={actions} />
        </section>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Raw log panel                                                        */}
      {/* ------------------------------------------------------------------ */}
      <RawLogPanel steps={steps} />

      {/* ------------------------------------------------------------------ */}
      {/* Cancel confirmation dialog                                           */}
      {/* ------------------------------------------------------------------ */}
      <ConfirmDialog
        open={confirmCancelOpen}
        title="Cancel agent run"
        message="Stop the running agent. Steps so far will be preserved. PRs already opened will NOT be closed."
        onConfirm={() => void handleConfirmCancel()}
        onCancel={() => setConfirmCancelOpen(false)}
        confirmLabel="Cancel run"
        variant="danger"
      />
    </div>
  )
}

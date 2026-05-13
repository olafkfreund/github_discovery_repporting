// Usage:
//   import { TriggerAgentRunDialog } from '../components/agents/TriggerAgentRunDialog'
//
//   <TriggerAgentRunDialog
//     open={dialogOpen}
//     scanId={scan.id}
//     customerId={customer.id}
//     onConfirm={async (payload) => {
//       const run = await api.triggerAgentRun(scan.id, payload)
//       navigate(`/agent-runs/${run.id}`)
//     }}
//     onCancel={() => setDialogOpen(false)}
//   />

import { useState, useEffect } from 'react'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { Spinner } from '../ui/Spinner'
import { ErrorPanel } from '../ui/ErrorPanel'
import { SpendProgressBar } from '../ui/SpendProgressBar'
import { api } from '../../api/client'
import type { LLMConnection } from '../../types/llm'
import type {
  RemediationPolicy,
  AgentRunCostEstimate,
  AgentRunTriggerPayload,
  CostStatus,
} from '../../types/agents'

interface Props {
  open: boolean
  scanId: string
  customerId: string
  onConfirm: (payload: AgentRunTriggerPayload) => Promise<void>
  onCancel: () => void
}

interface LoadedData {
  connections: LLMConnection[]
  policy: RemediationPolicy | null
  estimate: AgentRunCostEstimate
  costStatus: CostStatus | null
}

type LoadState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'error'; connectionsError: string | null; estimateError: string | null }
  | { phase: 'ready'; data: LoadedData }

export function TriggerAgentRunDialog({
  open,
  scanId,
  customerId,
  onConfirm,
  onCancel,
}: Props) {
  const [loadState, setLoadState] = useState<LoadState>({ phase: 'idle' })
  const [selectedConnectionId, setSelectedConnectionId] = useState<string>('')
  const [runtimeMode] = useState<'backend' | 'ci'>('backend')
  const [isTriggering, setIsTriggering] = useState(false)

  useEffect(() => {
    if (!open) {
      setLoadState({ phase: 'idle' })
      setSelectedConnectionId('')
      setIsTriggering(false)
      return
    }

    setLoadState({ phase: 'loading' })

    const connectionsPromise = api.listLLMConnections(customerId)
    const policyPromise = api.getRemediationPolicy(customerId)
    const estimatePromise = api.estimateAgentRunCost(scanId)
    const costStatusPromise = api.getCostStatus(customerId)

    let connectionsError: string | null = null
    let estimateError: string | null = null
    let connections: LLMConnection[] = []
    let policy: RemediationPolicy | null = null
    let estimate: AgentRunCostEstimate | null = null
    let costStatus: CostStatus | null = null

    Promise.allSettled([
      connectionsPromise,
      policyPromise,
      estimatePromise,
      costStatusPromise,
    ]).then(
      ([connectionsResult, policyResult, estimateResult, costStatusResult]) => {
        if (connectionsResult.status === 'fulfilled') {
          connections = connectionsResult.value
        } else {
          connectionsError = connectionsResult.reason instanceof Error
            ? connectionsResult.reason.message
            : 'Failed to load LLM connections'
        }

        if (policyResult.status === 'fulfilled') {
          policy = policyResult.value
        }
        // policyResult rejection is non-fatal — treated as null (handled in getRemediationPolicy)

        if (estimateResult.status === 'fulfilled') {
          estimate = estimateResult.value
        } else {
          estimateError = estimateResult.reason instanceof Error
            ? estimateResult.reason.message
            : 'Failed to load cost estimate'
        }

        // costStatus rejection is non-fatal — treated as null (cap section will be hidden)
        if (costStatusResult.status === 'fulfilled') {
          costStatus = costStatusResult.value
        }

        if (connectionsError || estimateError) {
          setLoadState({ phase: 'error', connectionsError, estimateError })
          if (connections.length > 0) {
            // Partial success: connections loaded, estimate failed — still allow use
            const defaultConn =
              connections.find((c) => c.is_default) ?? connections[0]
            setSelectedConnectionId(defaultConn?.id ?? '')
            setLoadState({
              phase: 'ready',
              data: {
                connections,
                policy,
                costStatus,
                estimate: estimate ?? { min_usd: 0, max_usd: 0, expected_tokens: 0 },
              },
            })
            return
          }
        } else {
          const defaultConn =
            connections.find((c) => c.is_default) ?? connections[0]
          setSelectedConnectionId(defaultConn?.id ?? '')
          setLoadState({
            phase: 'ready',
            data: {
              connections,
              policy,
              costStatus,
              estimate: estimate!,
            },
          })
        }
      }
    )
  }, [open, customerId, scanId])

  const handleConfirm = async () => {
    if (!selectedConnectionId) return
    setIsTriggering(true)
    try {
      await onConfirm({ llm_connection_id: selectedConnectionId, runtime_mode: runtimeMode })
    } finally {
      setIsTriggering(false)
    }
  }

  const capExceeded =
    loadState.phase === 'ready' &&
    loadState.data.costStatus?.exceeded === true

  const isConfirmDisabled =
    loadState.phase === 'loading' ||
    isTriggering ||
    !selectedConnectionId ||
    capExceeded ||
    (loadState.phase === 'ready' && loadState.data.connections.length === 0) ||
    (loadState.phase === 'error' && loadState.connectionsError !== null)

  const body = (
    <DialogBody
      loadState={loadState}
      selectedConnectionId={selectedConnectionId}
      onConnectionChange={setSelectedConnectionId}
      isTriggering={isTriggering}
    />
  )

  return (
    <ConfirmDialog
      open={open}
      title="Run remediation agent"
      message="Launch an AI agent to automatically remediate findings from this scan."
      body={body}
      onConfirm={() => { void handleConfirm() }}
      onCancel={onCancel}
      confirmLabel={isTriggering ? 'Triggering...' : 'Run remediation'}
      confirmDisabled={isConfirmDisabled}
      variant="default"
    />
  )
}

interface DialogBodyProps {
  loadState: LoadState
  selectedConnectionId: string
  onConnectionChange: (id: string) => void
  isTriggering: boolean
}

function DialogBody({
  loadState,
  selectedConnectionId,
  onConnectionChange,
  isTriggering,
}: DialogBodyProps) {
  if (loadState.phase === 'loading') {
    return <Spinner className="h-16" />
  }

  if (loadState.phase === 'error') {
    return (
      <div className="space-y-3">
        {loadState.connectionsError && (
          <ErrorPanel message={loadState.connectionsError} />
        )}
        {loadState.estimateError && (
          <ErrorPanel message={loadState.estimateError} />
        )}
      </div>
    )
  }

  if (loadState.phase !== 'ready') {
    return null
  }

  const { connections, policy, estimate, costStatus } = loadState.data

  const capPct =
    costStatus && costStatus.cap_usd > 0
      ? Math.round(Math.min(1, costStatus.spent_usd / costStatus.cap_usd) * 100)
      : 0

  const showCapWarning =
    costStatus &&
    !costStatus.exceeded &&
    costStatus.cap_usd > 0 &&
    costStatus.remaining_usd < estimate.max_usd

  return (
    <div className="space-y-4 text-sm">
      {/* LLM connection selector */}
      <div>
        <label
          htmlFor="llm-connection-select"
          className="block text-xs font-medium text-gray-700 mb-1"
        >
          LLM connection
        </label>
        {connections.length === 0 ? (
          <div className="bg-red-50 border border-red-200 rounded-md p-3">
            <p className="text-red-700 text-xs font-medium">
              No LLM provider configured. Open Settings to add one.
            </p>
          </div>
        ) : (
          <select
            id="llm-connection-select"
            value={selectedConnectionId}
            onChange={(e) => onConnectionChange(e.target.value)}
            disabled={isTriggering}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm
                       text-gray-900 shadow-sm focus:border-brand-500 focus:outline-none
                       focus:ring-1 focus:ring-brand-500 disabled:bg-gray-50 disabled:text-gray-500"
          >
            {connections.map((conn) => (
              <option key={conn.id} value={conn.id}>
                {conn.name} ({conn.provider}/{conn.model})
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Policy snapshot */}
      <div>
        <p className="text-xs font-medium text-gray-700 mb-1">Policy snapshot</p>
        {policy === null ? (
          <p className="text-xs text-gray-500 italic">Default policy will be used.</p>
        ) : (
          <ul className="text-xs text-gray-600 space-y-0.5 pl-3 list-disc">
            <li>
              {policy.allowed_check_ids.length} checks enabled
            </li>
            <li>
              Max {policy.max_prs_per_scan} PRs per scan
            </li>
            <li>
              Allowed paths:{' '}
              {policy.allowed_path_globs.length > 0
                ? policy.allowed_path_globs.join(', ')
                : '(any)'}
            </li>
            <li>
              Denied paths:{' '}
              {policy.denied_path_globs.length > 0
                ? policy.denied_path_globs.join(', ')
                : '(none)'}
            </li>
          </ul>
        )}
      </div>

      {/* Cost estimate */}
      <div>
        <p className="text-xs font-medium text-gray-700 mb-0.5">Estimated cost</p>
        <p className="text-xs text-gray-600">
          ${estimate.min_usd.toFixed(4)}–${estimate.max_usd.toFixed(4)}{' '}
          <span className="text-gray-400">
            (~{estimate.expected_tokens.toLocaleString()} tokens)
          </span>
        </p>
      </div>

      {/* Cost cap section */}
      {costStatus && (
        <div className="mt-4 text-sm">
          {costStatus.exceeded ? (
            <div
              role="alert"
              className="bg-red-50 border border-red-200 rounded-md p-3 text-sm"
            >
              <p className="text-red-700 font-medium">
                Monthly cost cap exceeded
              </p>
              <p className="text-red-600 text-xs mt-0.5">
                ${costStatus.spent_usd.toFixed(2)} of ${costStatus.cap_usd.toFixed(2)} spent.
                Cannot trigger new agent runs this month.
              </p>
            </div>
          ) : costStatus.cap_usd === 0 ? (
            <p className="text-xs text-gray-500 italic">No cost cap configured.</p>
          ) : (
            <>
              <p className="text-xs font-medium text-gray-700 mb-1">
                Monthly cost cap
              </p>
              <p className="text-xs text-gray-600 mb-1.5">
                <span className="font-medium text-gray-900">
                  ${costStatus.spent_usd.toFixed(2)}
                </span>
                {' '}spent of{' '}
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
              </p>
              {showCapWarning && (
                <p
                  role="status"
                  className="text-amber-700 text-xs mt-1.5"
                >
                  Warning: estimated max cost (${estimate.max_usd.toFixed(4)}) exceeds
                  remaining cap (${costStatus.remaining_usd.toFixed(2)}).
                  This run may be rejected if it overshoots.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {/* Runtime mode */}
      <fieldset>
        <legend className="text-xs font-medium text-gray-700 mb-1">Runtime mode</legend>
        <div className="space-y-1">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="runtime-mode"
              value="backend"
              checked={true}
              readOnly
              disabled={isTriggering}
              className="h-3.5 w-3.5 text-brand-600 border-gray-300 focus:ring-brand-500"
            />
            <span className="text-xs text-gray-700">Backend (default)</span>
          </label>
          <label
            className="flex items-center gap-2 cursor-not-allowed"
            title="Phase 4 — coming soon"
          >
            <input
              type="radio"
              name="runtime-mode"
              value="ci"
              checked={false}
              readOnly
              disabled
              aria-disabled="true"
              title="Phase 4 — coming soon"
              className="h-3.5 w-3.5 text-brand-600 border-gray-300 opacity-40 cursor-not-allowed"
            />
            <span className="text-xs text-gray-400">
              CI runner{' '}
              <span className="italic">(Phase 4 — coming soon)</span>
            </span>
          </label>
        </div>
      </fieldset>
    </div>
  )
}

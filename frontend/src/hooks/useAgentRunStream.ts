// useAgentRunStream — SSE-driven hook for AgentRunDetailPage (issue #30)
//
// Usage:
//   const { run, steps, actions, connectionState, reconnect } = useAgentRunStream(runId)

import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../api/client'
import type { AgentRunDetailed, AgentStep, RemediationAction } from '../types/agents'

export type ConnectionState = 'connecting' | 'open' | 'closed' | 'error'

export interface UseAgentRunStreamResult {
  run: AgentRunDetailed | null
  steps: AgentStep[]
  actions: RemediationAction[]
  connectionState: ConnectionState
  reconnect: () => void
}

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])
const BACKOFF_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000]

function getBackoffDelay(attempt: number): number {
  return BACKOFF_DELAYS[Math.min(attempt, BACKOFF_DELAYS.length - 1)]
}

export function useAgentRunStream(runId: string): UseAgentRunStreamResult {
  const [run, setRun] = useState<AgentRunDetailed | null>(null)
  const [steps, setSteps] = useState<AgentStep[]>([])
  const [actions, setActions] = useState<RemediationAction[]>([])
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting')

  const esRef = useRef<EventSource | null>(null)
  const backoffTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const backoffAttemptRef = useRef(0)
  const pollingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const unmountedRef = useRef(false)

  // Dedup helper: merge a new step by step_index
  const mergeStep = useCallback((incoming: AgentStep) => {
    setSteps((prev) => {
      const idx = prev.findIndex((s) => s.step_index === incoming.step_index)
      if (idx === -1) return [...prev, incoming]
      const next = [...prev]
      next[idx] = incoming
      return next
    })
  }, [])

  const closeConnection = useCallback(() => {
    if (esRef.current) {
      esRef.current.close()
      esRef.current = null
    }
    if (backoffTimerRef.current !== null) {
      clearTimeout(backoffTimerRef.current)
      backoffTimerRef.current = null
    }
    if (pollingTimerRef.current !== null) {
      clearInterval(pollingTimerRef.current)
      pollingTimerRef.current = null
    }
  }, [])

  const startPolling = useCallback(() => {
    if (pollingTimerRef.current !== null) return
    pollingTimerRef.current = setInterval(() => {
      void api.getAgentRun(runId).then((data) => {
        if (unmountedRef.current) return
        setRun(data)
        setSteps(data.steps)
        setActions(data.actions)
        if (TERMINAL_STATUSES.has(data.status)) {
          if (pollingTimerRef.current !== null) {
            clearInterval(pollingTimerRef.current)
            pollingTimerRef.current = null
          }
          setConnectionState('closed')
        }
      }).catch(() => {
        // silent — keep polling
      })
    }, 5000)
  }, [runId])

  const openStream = useCallback(() => {
    if (unmountedRef.current) return

    // Fallback: if EventSource is not available (jsdom, etc.)
    if (typeof EventSource === 'undefined') {
      setConnectionState('open')
      startPolling()
      return
    }

    let es: EventSource
    try {
      es = new EventSource(`/api/agent-runs/${runId}/stream`)
    } catch {
      setConnectionState('error')
      startPolling()
      return
    }

    esRef.current = es
    setConnectionState('connecting')

    es.onopen = () => {
      if (unmountedRef.current) return
      backoffAttemptRef.current = 0
      setConnectionState('open')
    }

    const STEP_EVENT_TYPES = ['llm_call', 'tool_call', 'tool_result', 'observation', 'final'] as const
    for (const type of STEP_EVENT_TYPES) {
      es.addEventListener(type, (evt: MessageEvent) => {
        if (unmountedRef.current) return
        try {
          const step = JSON.parse(evt.data as string) as AgentStep
          mergeStep(step)
        } catch {
          // ignore malformed events
        }
      })
    }

    es.addEventListener('status_change', (evt: MessageEvent) => {
      if (unmountedRef.current) return
      try {
        const payload = JSON.parse(evt.data as string) as {
          status: AgentRunDetailed['status']
          finished_at: string | null
        }
        setRun((prev) =>
          prev
            ? { ...prev, status: payload.status, finished_at: payload.finished_at }
            : prev
        )
        // Server will close on terminal status — we follow suit
        if (TERMINAL_STATUSES.has(payload.status)) {
          // Give the server a moment to flush remaining events, then mark closed
          setTimeout(() => {
            if (!unmountedRef.current) setConnectionState('closed')
          }, 500)
        }
      } catch {
        // ignore
      }
    })

    es.onerror = () => {
      if (unmountedRef.current) return
      es.close()
      esRef.current = null
      setConnectionState('error')

      const delay = getBackoffDelay(backoffAttemptRef.current)
      backoffAttemptRef.current += 1
      backoffTimerRef.current = setTimeout(() => {
        if (!unmountedRef.current) openStream()
      }, delay)
    }
  }, [runId, mergeStep, startPolling])

  const reconnect = useCallback(() => {
    closeConnection()
    backoffAttemptRef.current = 0
    openStream()
  }, [closeConnection, openStream])

  useEffect(() => {
    unmountedRef.current = false

    // Initial REST fetch
    void api.getAgentRun(runId).then((data) => {
      if (unmountedRef.current) return
      setRun(data)
      setSteps(data.steps)
      setActions(data.actions)

      // Don't open SSE for already-terminal runs
      if (TERMINAL_STATUSES.has(data.status)) {
        setConnectionState('closed')
        return
      }
      openStream()
    }).catch(() => {
      if (!unmountedRef.current) {
        setConnectionState('error')
      }
    })

    return () => {
      unmountedRef.current = true
      closeConnection()
    }
    // openStream and closeConnection are stable refs — intentional single-run
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  return { run, steps, actions, connectionState, reconnect }
}

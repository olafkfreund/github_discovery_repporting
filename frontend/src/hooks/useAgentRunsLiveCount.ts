// Usage:
//   import { useAgentRunsLiveCount } from '../hooks/useAgentRunsLiveCount'
//   const { count, loading } = useAgentRunsLiveCount()
//
// Polls /api/agent-runs for pending, running, and opening_pr runs every 5s.
// Pauses polling when the browser tab is hidden and resumes on visibility.
// Sidebar badge is rendered by Sidebar.tsx when count > 0.

import { useState, useEffect } from 'react'
import { api } from '../api/client'

export function useAgentRunsLiveCount(): { count: number; loading: boolean } {
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    let interval: ReturnType<typeof setInterval> | null = null

    const fetchCount = async () => {
      try {
        const [pending, running, opening] = await Promise.all([
          api.listAgentRuns({ status: 'pending', limit: 200 }),
          api.listAgentRuns({ status: 'running', limit: 200 }),
          api.listAgentRuns({ status: 'opening_pr', limit: 200 }),
        ])
        if (cancelled) return
        setCount(pending.length + running.length + opening.length)
      } catch {
        /* keep previous count on transient errors */
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    const start = () => {
      void fetchCount()
      interval = setInterval(() => { void fetchCount() }, 5000)
    }

    const stop = () => {
      if (interval) {
        clearInterval(interval)
        interval = null
      }
    }

    const onVisibility = () => {
      if (document.hidden) {
        stop()
      } else if (!interval) {
        start()
      }
    }

    start()
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      cancelled = true
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  return { count, loading }
}

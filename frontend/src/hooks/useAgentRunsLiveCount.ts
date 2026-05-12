/**
 * Placeholder hook — returns a static count of 0.
 *
 * TODO: Wire to GET /api/agent-runs?status=running once the backend
 * agent_runs endpoint ships (Phase 3, issue #4 epic). The hook should
 * poll on a 5s interval (matching the pattern in CustomerDetailPage)
 * and expose { count, loading, error }.
 */
export function useAgentRunsLiveCount(): { count: number; loading: boolean } {
  return { count: 0, loading: false }
}

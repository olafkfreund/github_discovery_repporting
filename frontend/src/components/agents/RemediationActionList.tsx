// RemediationActionList — PRs panel for AgentRunDetailPage (issue #30)
//
// Usage:
//   <RemediationActionList actions={actions} />

import type { RemediationAction, RemediationActionStatus } from '../../types/agents'

interface Props {
  actions: RemediationAction[]
}

const STATUS_CLASSES: Record<RemediationActionStatus, string> = {
  planned:     'bg-gray-100 text-gray-600',
  in_progress: 'bg-blue-100 text-blue-700',
  opened:      'bg-green-100 text-green-700',
  merged:      'bg-purple-100 text-purple-700',
  closed:      'bg-yellow-100 text-yellow-700',
  failed:      'bg-red-100 text-red-700',
}

const STATUS_LABELS: Record<RemediationActionStatus, string> = {
  planned:     'planned',
  in_progress: 'in progress',
  opened:      'opened',
  merged:      'merged',
  closed:      'closed',
  failed:      'failed',
}

function repoFromUrl(url: string | null): string {
  if (!url) return ''
  try {
    const parts = new URL(url).pathname.split('/')
    // GitHub PR URLs: /owner/repo/pull/N
    const pullIdx = parts.findIndex((p) => p === 'pull')
    if (pullIdx >= 2) return `${parts[pullIdx - 2]}/${parts[pullIdx - 1]}`
    return parts.slice(1, 3).join('/')
  } catch {
    return url
  }
}

function prNumber(url: string | null): string | null {
  if (!url) return null
  try {
    const parts = new URL(url).pathname.split('/')
    const pullIdx = parts.findIndex((p) => p === 'pull')
    return pullIdx !== -1 ? `#${parts[pullIdx + 1]}` : null
  } catch {
    return null
  }
}

export function RemediationActionList({ actions }: Props) {
  if (actions.length === 0) {
    return (
      <p className="text-sm text-gray-400 italic">
        No PRs opened yet for this run.
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {actions.map((action) => {
        const num = prNumber(action.pr_url)
        const repo = repoFromUrl(action.pr_url)
        return (
          <li
            key={action.id}
            className="rounded-md border border-gray-200 bg-white p-3 shadow-sm"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_CLASSES[action.status]}`}
                >
                  {STATUS_LABELS[action.status]}
                </span>
                <span className="text-xs font-mono text-gray-700 truncate">
                  {action.check_id}
                </span>
              </div>
              {action.pr_url && (
                <a
                  href={action.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-brand-600 hover:text-brand-800"
                  aria-label={`Open PR ${num ?? ''} for ${action.check_id} in new tab`}
                >
                  {/* External link arrow */}
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                    />
                  </svg>
                </a>
              )}
            </div>

            <div className="mt-1 text-xs text-gray-500">
              {action.pr_url ? (
                <span>
                  {num && <span className="font-medium text-gray-700">{num} → </span>}
                  <span className="truncate">{repo || action.pr_url}</span>
                </span>
              ) : (
                <span className="italic">(no PR yet)</span>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

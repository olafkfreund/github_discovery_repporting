// Usage:
//   import { AllowedChecksEditor } from '../components/settings/AllowedChecksEditor'
//
//   <AllowedChecksEditor
//     registry={registry}
//     allowedCheckIds={draft.allowed_check_ids ?? []}
//     blockedCheckIds={draft.blocked_check_ids ?? []}
//     onChangeAllowed={(ids) => setDraft((d) => ({ ...d, allowed_check_ids: ids }))}
//     onChangeBlocked={(ids) => setDraft((d) => ({ ...d, blocked_check_ids: ids }))}
//   />

import { useState } from 'react'
import type { CategoryRegistryInfo } from '../../types'
import { CategoryBadge } from './CategoryBadge'

interface Props {
  registry: CategoryRegistryInfo[]
  allowedCheckIds: string[]
  blockedCheckIds: string[]
  onChangeAllowed: (ids: string[]) => void
  onChangeBlocked: (ids: string[]) => void
}

type CheckState = 'allow' | 'block' | 'none'

function getState(checkId: string, allowed: string[], blocked: string[]): CheckState {
  if (allowed.includes(checkId)) return 'allow'
  if (blocked.includes(checkId)) return 'block'
  return 'none'
}

export function AllowedChecksEditor({
  registry,
  allowedCheckIds,
  blockedCheckIds,
  onChangeAllowed,
  onChangeBlocked,
}: Props) {
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set())

  const toggleExpanded = (cat: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  const handleAllow = (checkId: string, checked: boolean) => {
    if (checked) {
      // Allow selected: remove from blocked, add to allowed
      onChangeBlocked(blockedCheckIds.filter((id) => id !== checkId))
      if (!allowedCheckIds.includes(checkId)) {
        onChangeAllowed([...allowedCheckIds, checkId])
      }
    } else {
      onChangeAllowed(allowedCheckIds.filter((id) => id !== checkId))
    }
  }

  const handleBlock = (checkId: string, checked: boolean) => {
    if (checked) {
      // Block selected: remove from allowed, add to blocked
      onChangeAllowed(allowedCheckIds.filter((id) => id !== checkId))
      if (!blockedCheckIds.includes(checkId)) {
        onChangeBlocked([...blockedCheckIds, checkId])
      }
    } else {
      onChangeBlocked(blockedCheckIds.filter((id) => id !== checkId))
    }
  }

  const totalChecks = registry.reduce((sum, cat) => sum + cat.checks.length, 0)
  const allowedCount = allowedCheckIds.length
  const blockedCount = blockedCheckIds.length

  return (
    <div>
      {/* Summary bar */}
      <div className="mb-3 px-3 py-2 bg-gray-50 rounded-md text-sm text-gray-600">
        {allowedCount === 0 ? (
          <span>
            All <strong>{totalChecks}</strong> checks allowed &mdash; no restrictions
          </span>
        ) : (
          <span>
            <strong>{allowedCount}</strong> check{allowedCount !== 1 ? 's' : ''} allow-listed
            {blockedCount > 0 && (
              <>
                {' · '}
                <strong>{blockedCount}</strong> check{blockedCount !== 1 ? 's' : ''} blocked
              </>
            )}
          </span>
        )}
      </div>

      {/* Category sections */}
      <div className="space-y-2">
        {registry.map((cat) => {
          const expanded = expandedCats.has(cat.category)

          return (
            <div key={cat.category} className="border border-gray-200 rounded-lg">
              {/* Category header */}
              <button
                type="button"
                onClick={() => toggleExpanded(cat.category)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 rounded-lg"
                aria-expanded={expanded}
              >
                <div className="flex items-center gap-3">
                  <svg
                    className={`h-4 w-4 text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                  <CategoryBadge category={cat.category} />
                  <span className="text-sm font-medium text-gray-800">{cat.display_name}</span>
                  <span className="text-xs text-gray-400">
                    {cat.checks.length} check{cat.checks.length !== 1 ? 's' : ''}
                  </span>
                </div>
                {/* Per-category summary */}
                {(() => {
                  const catAllowed = cat.checks.filter((c) => allowedCheckIds.includes(c.check_id)).length
                  const catBlocked = cat.checks.filter((c) => blockedCheckIds.includes(c.check_id)).length
                  if (catAllowed === 0 && catBlocked === 0) return null
                  return (
                    <span className="text-xs text-gray-500 mr-1">
                      {catAllowed > 0 && <span className="text-emerald-700">{catAllowed} allowed</span>}
                      {catAllowed > 0 && catBlocked > 0 && <span className="mx-1 text-gray-400">·</span>}
                      {catBlocked > 0 && <span className="text-red-700">{catBlocked} blocked</span>}
                    </span>
                  )
                })()}
              </button>

              {/* Checks table */}
              {expanded && (
                <div className="border-t border-gray-100 px-4 py-3">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs font-medium text-gray-500 uppercase">
                        <th className="pb-2 pr-3 w-16">Allow</th>
                        <th className="pb-2 pr-3 w-16">Block</th>
                        <th className="pb-2 pr-3">Check</th>
                        <th className="pb-2">Severity</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {cat.checks.map((check) => {
                        const state = getState(check.check_id, allowedCheckIds, blockedCheckIds)
                        const allowId = `allow-${check.check_id}`
                        const blockId = `block-${check.check_id}`

                        return (
                          <tr
                            key={check.check_id}
                            className={state === 'block' ? 'opacity-60' : ''}
                          >
                            <td className="py-2 pr-3">
                              <input
                                id={allowId}
                                type="checkbox"
                                checked={state === 'allow'}
                                onChange={(e) => handleAllow(check.check_id, e.target.checked)}
                                className="rounded border-gray-300 text-emerald-600
                                           focus:ring-emerald-500"
                                aria-label={`Allow ${check.check_id}`}
                              />
                            </td>
                            <td className="py-2 pr-3">
                              <input
                                id={blockId}
                                type="checkbox"
                                checked={state === 'block'}
                                onChange={(e) => handleBlock(check.check_id, e.target.checked)}
                                className="rounded border-gray-300 text-red-600
                                           focus:ring-red-500"
                                aria-label={`Block ${check.check_id}`}
                              />
                            </td>
                            <td className="py-2 pr-3">
                              <div className="font-medium text-gray-800">{check.check_id}</div>
                              <div className="text-xs text-gray-500">{check.check_name}</div>
                            </td>
                            <td className="py-2">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                                  check.severity === 'critical'
                                    ? 'bg-red-100 text-red-800'
                                    : check.severity === 'high'
                                      ? 'bg-orange-100 text-orange-800'
                                      : check.severity === 'medium'
                                        ? 'bg-yellow-100 text-yellow-800'
                                        : 'bg-gray-100 text-gray-700'
                                }`}
                              >
                                {check.severity}
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

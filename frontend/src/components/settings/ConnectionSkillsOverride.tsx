// Usage:
//   import { ConnectionSkillsOverride } from './ConnectionSkillsOverride'
//   <ConnectionSkillsOverride connection={conn} skills={skills} onSave={handleSave} />
//
// onSave receives the connection id and the override payload; returns the updated Connection.
// The component manages its own tri-state pill UX and debounced 1s PUT.

import { useState, useRef, useEffect, useId } from 'react'
import type { Connection } from '../../types'
import type { Skill, ConnectionSkillsOverridePayload } from '../../types/skills'
import { CategoryBadge } from './CategoryBadge'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PLATFORM_BADGE: Record<Connection['platform'], string> = {
  github: 'bg-gray-100 text-gray-800',
  gitlab: 'bg-orange-100 text-orange-800',
  azure_devops: 'bg-blue-100 text-blue-800',
}

const PLATFORM_LABEL: Record<Connection['platform'], string> = {
  github: 'GitHub',
  gitlab: 'GitLab',
  azure_devops: 'Azure DevOps',
}

type TriState = 'default' | 'enabled' | 'disabled'
type SaveStatus = 'idle' | 'saving' | 'saved' | 'failed'

// ---------------------------------------------------------------------------
// Tri-state pill
// ---------------------------------------------------------------------------

interface TriStatePillProps {
  state: TriState
  onClick: () => void
}

function TriStatePill({ state, onClick }: TriStatePillProps) {
  const labels: Record<TriState, string> = {
    default: '— Default',
    enabled: '✓ Enabled here',
    disabled: '✗ Disabled here',
  }
  const classes: Record<TriState, string> = {
    default: 'bg-gray-100 text-gray-700 border border-gray-200',
    enabled: 'bg-emerald-100 text-emerald-900 border border-emerald-200',
    disabled: 'bg-red-100 text-red-900 border border-red-200',
  }
  const nextAction: Record<TriState, string> = {
    default: 'Click to force enable for this connection.',
    enabled: 'Click to force disable for this connection.',
    disabled: 'Click to reset to customer default.',
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Currently ${state}. ${nextAction[state]}`}
      className={[
        'inline-flex items-center px-2.5 py-1 rounded text-xs font-medium flex-shrink-0',
        'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1',
        'transition-colors cursor-pointer',
        classes[state],
      ].join(' ')}
    >
      {labels[state]}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  connection: Connection
  skills: Skill[]
  onSave: (
    connectionId: string,
    payload: ConnectionSkillsOverridePayload,
  ) => Promise<Connection>
}

export function ConnectionSkillsOverride({ connection, skills, onSave }: Props) {
  const bodyId = useId()
  const [expanded, setExpanded] = useState(false)
  const [draftOverrides, setDraftOverrides] = useState<Record<string, boolean>>(
    connection.skills_override ?? {},
  )
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const clearStatusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Keep a ref to always send the latest draft in the debounced callback.
  const latestOverridesRef = useRef(draftOverrides)
  latestOverridesRef.current = draftOverrides

  // Sync when parent passes a refreshed connection (e.g. after a save).
  useEffect(() => {
    setDraftOverrides(connection.skills_override ?? {})
  }, [connection.skills_override])

  // Cleanup timers on unmount.
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
      if (clearStatusTimerRef.current) clearTimeout(clearStatusTimerRef.current)
    }
  }, [])

  const overrideCount = Object.keys(draftOverrides).length

  function scheduleSave() {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      void (async () => {
        setSaveStatus('saving')
        setSaveError(null)
        try {
          await onSave(connection.id, { overrides: latestOverridesRef.current })
          setSaveStatus('saved')
          if (clearStatusTimerRef.current) clearTimeout(clearStatusTimerRef.current)
          clearStatusTimerRef.current = setTimeout(() => setSaveStatus('idle'), 2000)
        } catch (err) {
          setSaveStatus('failed')
          setSaveError(err instanceof Error ? err.message : 'Failed to save')
        }
      })()
    }, 1000)
  }

  function cycleSkill(skillName: string) {
    setDraftOverrides((prev) => {
      const next = { ...prev }
      const current = prev[skillName]
      if (current === undefined) {
        next[skillName] = true       // default → enabled
      } else if (current === true) {
        next[skillName] = false      // enabled → disabled
      } else {
        delete next[skillName]       // disabled → default
      }
      return next
    })
    scheduleSave()
  }

  function skillToState(skillName: string): TriState {
    const v = draftOverrides[skillName]
    if (v === true) return 'enabled'
    if (v === false) return 'disabled'
    return 'default'
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Collapsed header */}
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left bg-white hover:bg-gray-50
                   focus:outline-none focus:ring-2 focus:ring-inset focus:ring-brand-500 cursor-pointer"
      >
        {/* Chevron */}
        <svg
          className={`h-4 w-4 text-gray-400 flex-shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>

        {/* Platform badge */}
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium flex-shrink-0 ${PLATFORM_BADGE[connection.platform]}`}
        >
          {PLATFORM_LABEL[connection.platform]}
        </span>

        {/* Connection name */}
        <span className="text-sm font-medium text-gray-900">{connection.display_name}</span>

        {/* Org/group */}
        <span className="text-xs text-gray-500 truncate">
          (org/group: {connection.org_or_group})
        </span>

        {/* Override status pill */}
        <span className="ml-auto flex-shrink-0">
          {overrideCount === 0 ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
              Uses customer defaults
            </span>
          ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-brand-100 text-brand-900">
              Override active — {overrideCount} skill{overrideCount !== 1 ? 's' : ''} overridden
            </span>
          )}
        </span>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div
          id={bodyId}
          role="region"
          aria-label={`Skill overrides for ${connection.display_name}`}
          className="border-t border-gray-200 bg-gray-50 p-4 space-y-2"
        >
          {skills.length === 0 ? (
            <p className="text-sm text-gray-500">No skills available for this customer.</p>
          ) : (
            <div className="space-y-1">
              {skills.map((skill) => (
                <div
                  key={skill.name}
                  className="flex items-center gap-3 px-2 py-1 hover:bg-white rounded"
                >
                  {/* Skill name */}
                  <span className="flex-1 text-sm font-medium text-gray-900 truncate">
                    {skill.name}
                  </span>

                  {/* Category badge */}
                  <CategoryBadge category={skill.category} />

                  {/* Tri-state pill */}
                  <TriStatePill
                    state={skillToState(skill.name)}
                    onClick={() => cycleSkill(skill.name)}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Save status indicator */}
          <div role="status" aria-live="polite" className="mt-3 text-xs">
            {saveStatus === 'saving' && (
              <span className="text-gray-500">Saving…</span>
            )}
            {saveStatus === 'saved' && (
              <span className="text-emerald-700">Saved</span>
            )}
            {saveStatus === 'failed' && (
              <span className="text-red-700">Failed: {saveError}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

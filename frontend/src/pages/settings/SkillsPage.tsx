// Usage:
//   Rendered at /settings/skills?customer_id=<uuid>
//   Reads customer_id from URL search params (supplied by CustomerPicker in SettingsLayout)

import { useState, useEffect, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { Skill, SkillFilters, SkillFilterType } from '../../types/skills'
import type { CategoryRegistryInfo, Connection } from '../../types'
import { useSkills } from '../../hooks/useSkills'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorPanel } from '../../components/ui/ErrorPanel'
import { SkillsTable } from '../../components/settings/SkillsTable'
import { SkillDrawer } from '../../components/settings/SkillDrawer'
import { ConnectionSkillsOverride } from '../../components/settings/ConnectionSkillsOverride'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function filterSkills(skills: Skill[], filters: SkillFilters): Skill[] {
  return skills.filter((s) => {
    if (filters.type === 'builtin' && s.source !== 'builtin') return false
    if (filters.type === 'custom' && s.source !== 'custom') return false
    if (filters.enabledOnly && !s.enabled) return false
    if (filters.search) {
      const q = filters.search.toLowerCase()
      const inName = s.name.toLowerCase().includes(q)
      const inDesc = s.description.toLowerCase().includes(q)
      const inIds = s.applies_to_check_ids.some((id) => id.toLowerCase().includes(q))
      if (!inName && !inDesc && !inIds) return false
    }
    return true
  })
}

// ---------------------------------------------------------------------------
// Filter row sub-component
// ---------------------------------------------------------------------------

interface FilterRowProps {
  filters: SkillFilters
  onChange: (f: SkillFilters) => void
  onNewClick: () => void
  newButtonRef: React.RefObject<HTMLButtonElement | null>
}

const FILTER_PILLS: { value: SkillFilterType; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'builtin', label: 'Built-in' },
  { value: 'custom', label: 'Custom' },
]

function FilterRow({ filters, onChange, onNewClick, newButtonRef }: FilterRowProps) {
  const pillRefs = useRef<(HTMLButtonElement | null)[]>([])

  const handlePillKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const idx = pillRefs.current.findIndex((el) => el === document.activeElement)
    if (idx === -1) return
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      pillRefs.current[(idx + 1) % FILTER_PILLS.length]?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      pillRefs.current[(idx - 1 + FILTER_PILLS.length) % FILTER_PILLS.length]?.focus()
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Type filter pills */}
      <div
        role="radiogroup"
        aria-label="Skill filters"
        className="flex gap-1"
        onKeyDown={handlePillKeyDown}
      >
        {FILTER_PILLS.map(({ value, label }, idx) => (
          <button
            key={value}
            ref={(el) => { pillRefs.current[idx] = el }}
            role="radio"
            aria-checked={filters.type === value}
            tabIndex={filters.type === value ? 0 : -1}
            onClick={() => onChange({ ...filters, type: value })}
            className={[
              'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-brand-500',
              filters.type === value
                ? 'bg-brand-600 text-white'
                : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-50',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Enabled-only toggle */}
      <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
        <input
          type="checkbox"
          role="switch"
          checked={filters.enabledOnly}
          onChange={(e) => onChange({ ...filters, enabledOnly: e.target.checked })}
          className="h-4 w-4 text-brand-600 border-gray-300 rounded focus:ring-brand-500"
        />
        Enabled only
      </label>

      {/* Search */}
      <div className="flex-1 min-w-48">
        <input
          type="search"
          value={filters.search}
          onChange={(e) => onChange({ ...filters, search: e.target.value })}
          placeholder="Search skills…"
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
          aria-label="Search skills"
        />
      </div>

      {/* New skill button */}
      <button
        ref={newButtonRef}
        onClick={onNewClick}
        className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 ml-auto"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        New skill
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SkillsPage() {
  const [searchParams] = useSearchParams()
  const customerId = searchParams.get('customer_id')

  const { skills, loading, error, reload, toggleEnabled } = useSkills(customerId)

  const [filters, setFilters] = useState<SkillFilters>({
    type: 'all',
    enabledOnly: false,
    search: '',
  })
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null)
  const [allCheckIds, setAllCheckIds] = useState<string[]>([])
  const [connections, setConnections] = useState<Connection[]>([])

  const newButtonRef = useRef<HTMLButtonElement | null>(null)

  // Load scanner registry for check-id typeahead
  useEffect(() => {
    api
      .getScannerRegistry()
      .then((categories: CategoryRegistryInfo[]) => {
        const ids = categories.flatMap((c) => c.checks.map((ch) => ch.check_id))
        setAllCheckIds(ids)
      })
      .catch(() => {
        // non-fatal — typeahead simply won't have suggestions
      })
  }, [])

  // Load connections for per-connection override section
  useEffect(() => {
    if (!customerId) return
    api
      .listConnections(customerId)
      .then(setConnections)
      .catch(() => {
        // non-fatal — section will show empty state
      })
  }, [customerId])

  const filtered = useMemo(
    () => filterSkills(skills, filters),
    [skills, filters],
  )

  const openCreate = () => {
    setEditingSkill(null)
    setDrawerOpen(true)
  }

  const openEdit = (skill: Skill) => {
    setEditingSkill(skill)
    setDrawerOpen(true)
  }

  const handleClose = () => {
    setDrawerOpen(false)
    setTimeout(() => newButtonRef.current?.focus(), 100)
  }

  const handleSaved = (_saved: Skill) => {
    void reload()
    setDrawerOpen(false)
    setTimeout(() => newButtonRef.current?.focus(), 100)
  }

  const handleDeleted = (_name: string) => {
    void reload()
    setDrawerOpen(false)
    setTimeout(() => newButtonRef.current?.focus(), 100)
  }

  if (!customerId) {
    return (
      <div className="p-6">
        <ErrorPanel message="Select a customer to manage skills." />
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Page header */}
      <header>
        <h1 className="text-xl font-semibold text-gray-900">Skills</h1>
        <p className="mt-1 text-sm text-gray-500">
          Predefined and customer-authored knowledge the agent uses to reason about findings and remediations.
        </p>
      </header>

      {/* Filter row */}
      <FilterRow
        filters={filters}
        onChange={setFilters}
        onNewClick={openCreate}
        newButtonRef={newButtonRef}
      />

      {/* Content */}
      {loading ? (
        <Spinner className="h-48" />
      ) : error ? (
        <ErrorPanel message={error} onRetry={() => { void reload() }} />
      ) : (
        <SkillsTable
          skills={filtered}
          onRowClick={openEdit}
          onToggle={(skill, enabled) => toggleEnabled(skill.name, enabled)}
        />
      )}

      {/* Per-connection skill overrides (issue #41) */}
      <section className="mt-8">
        <h3 className="text-lg font-semibold text-brand-800 mb-4">Per-connection overrides</h3>
        <p className="text-sm text-gray-600 mb-4">
          Connections inherit the customer-level skill enable/disable by default.
          Add an override here to force a skill on or off for a specific connection.
        </p>
        {connections.length === 0 ? (
          <p className="text-sm text-gray-500">This customer has no platform connections yet.</p>
        ) : (
          <div className="space-y-3">
            {connections.map((conn) => (
              <ConnectionSkillsOverride
                key={conn.id}
                connection={conn}
                skills={skills}
                onSave={async (id, payload) => {
                  const updated = await api.updateConnectionSkillsOverride(id, payload)
                  setConnections((prev) => prev.map((c) => (c.id === id ? updated : c)))
                  return updated
                }}
              />
            ))}
          </div>
        )}
      </section>

      {/* Drawer */}
      {customerId && (
        <SkillDrawer
          open={drawerOpen}
          customerId={customerId}
          skill={editingSkill}
          allCheckIds={allCheckIds}
          onClose={handleClose}
          onSaved={handleSaved}
          onDeleted={handleDeleted}
        />
      )}
    </div>
  )
}

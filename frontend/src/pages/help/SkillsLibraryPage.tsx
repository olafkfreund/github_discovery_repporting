// SkillsLibraryPage — read-only browser for the built-in skills catalogue.
// Powered by GET /api/skills-registry; click a row to load the markdown body
// via GET /api/skills-registry/{name}/content into a slide-in drawer.

import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import { MarkdownRenderer } from '../../components/help/MarkdownRenderer'
import type { SkillRegistryEntry } from '../../types/skills'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ALL_CATEGORIES = '__all__'

function distinctCategories(entries: SkillRegistryEntry[]): string[] {
  const set = new Set<string>()
  for (const e of entries) set.add(e.category)
  return [...set].sort()
}

function formatCategoryLabel(category: string): string {
  // Title-case for display (turn "code_quality" / "code-quality" into "Code quality").
  return category
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

// ---------------------------------------------------------------------------
// SkillDetailDrawer — slim, read-only drawer for the body markdown.
// ---------------------------------------------------------------------------

interface SkillDetailDrawerProps {
  skillName: string | null
  onClose: () => void
}

function SkillDetailDrawer({ skillName, onClose }: SkillDetailDrawerProps) {
  const [body, setBody] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!skillName) return
    setLoading(true)
    setError(null)
    setBody(null)
    api
      .getSkillRegistryContent(skillName)
      .then((res) => setBody(res.body))
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : 'Failed to load skill'
        setError(message)
      })
      .finally(() => setLoading(false))
  }, [skillName])

  useEffect(() => {
    if (!skillName) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    // Focus the close button on open for keyboard users.
    setTimeout(() => closeButtonRef.current?.focus(), 0)
    return () => window.removeEventListener('keydown', handler)
  }, [skillName, onClose])

  if (!skillName) return null

  return (
    <div
      className="fixed inset-0 z-40 flex"
      role="dialog"
      aria-modal="true"
      aria-labelledby="skill-drawer-title"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close skill details"
        onClick={onClose}
        className="absolute inset-0 bg-black/30"
      />
      {/* Drawer panel */}
      <div className="ml-auto relative h-full w-full max-w-2xl bg-white shadow-xl flex flex-col">
        <header className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 id="skill-drawer-title" className="text-lg font-semibold text-gray-900">
            {skillName}
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 px-3 py-1 rounded focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            Close
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {loading && <p className="text-sm text-gray-500">Loading…</p>}
          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
          {body !== null && !loading && !error && <MarkdownRenderer source={body} />}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SkillsLibraryPage
// ---------------------------------------------------------------------------

export default function SkillsLibraryPage() {
  const [entries, setEntries] = useState<SkillRegistryEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<string>(ALL_CATEGORIES)
  const [openSkillName, setOpenSkillName] = useState<string | null>(null)

  // Remember which row opened the drawer so we can restore focus on close.
  const lastRowRef = useRef<HTMLTableRowElement | null>(null)

  useEffect(() => {
    api
      .listSkillsRegistry()
      .then(setEntries)
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : 'Failed to load skills'
        setError(message)
      })
  }, [])

  const categories = useMemo(
    () => (entries ? distinctCategories(entries) : []),
    [entries],
  )

  const filtered = useMemo(() => {
    if (!entries) return []
    if (filter === ALL_CATEGORIES) return entries
    return entries.filter((e) => e.category === filter)
  }, [entries, filter])

  const handleClose = () => {
    setOpenSkillName(null)
    setTimeout(() => lastRowRef.current?.focus(), 0)
  }

  if (error) {
    return (
      <div className="py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Skills Library</h1>
        <p className="text-red-600">{error}</p>
      </div>
    )
  }

  if (entries === null) {
    return (
      <div className="py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Skills Library</h1>
        <p className="text-gray-500">Loading skills…</p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Skills Library</h1>
      <p className="text-gray-600 mb-6">
        BPS ships {entries.length} built-in skills. Skills shape how the agent thinks about a
        check or category. Toggle them on or off per customer under Settings → Skills.
      </p>

      {/* Filter pills */}
      <div
        role="radiogroup"
        aria-label="Filter skills by category"
        className="flex flex-wrap gap-2 mb-4"
      >
        <button
          type="button"
          role="radio"
          aria-checked={filter === ALL_CATEGORIES}
          onClick={() => setFilter(ALL_CATEGORIES)}
          className={[
            'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-brand-500',
            filter === ALL_CATEGORIES
              ? 'bg-brand-600 text-white'
              : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-50',
          ].join(' ')}
        >
          All ({entries.length})
        </button>
        {categories.map((cat) => {
          const count = entries.filter((e) => e.category === cat).length
          const active = filter === cat
          return (
            <button
              key={cat}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setFilter(cat)}
              className={[
                'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-brand-500',
                active
                  ? 'bg-brand-600 text-white'
                  : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-50',
              ].join(' ')}
            >
              {formatCategoryLabel(cat)} ({count})
            </button>
          )
        })}
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">No skills match that filter.</p>
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left font-semibold text-gray-700 border-b">Name</th>
                <th className="px-3 py-2 text-left font-semibold text-gray-700 border-b">Category</th>
                <th className="px-3 py-2 text-left font-semibold text-gray-700 border-b">Applies to</th>
                <th className="px-3 py-2 text-left font-semibold text-gray-700 border-b">Triggers</th>
                <th className="px-3 py-2 text-left font-semibold text-gray-700 border-b">Version</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => (
                <tr
                  key={entry.name}
                  tabIndex={0}
                  className="hover:bg-gray-50 cursor-pointer focus:outline-none focus:bg-brand-50"
                  onClick={(e) => {
                    lastRowRef.current = e.currentTarget
                    setOpenSkillName(entry.name)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      lastRowRef.current = e.currentTarget
                      setOpenSkillName(entry.name)
                    }
                  }}
                >
                  <td className="px-3 py-2 border-b border-gray-100 font-mono text-xs text-gray-800">
                    {entry.name}
                  </td>
                  <td className="px-3 py-2 border-b border-gray-100">
                    <span className="inline-block px-2 py-0.5 rounded bg-brand-50 text-brand-800 text-xs font-medium">
                      {formatCategoryLabel(entry.category)}
                    </span>
                  </td>
                  <td className="px-3 py-2 border-b border-gray-100">
                    {entry.applies_to.length === 0 ? (
                      <span className="text-xs italic text-gray-500">Always-on</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {entry.applies_to.map((id) => (
                          <span
                            key={id}
                            className="inline-block px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 text-xs font-mono"
                          >
                            {id}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 border-b border-gray-100 text-xs text-gray-700">
                    {entry.triggers.join(', ')}
                  </td>
                  <td className="px-3 py-2 border-b border-gray-100 text-xs text-gray-700">
                    v{entry.version}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SkillDetailDrawer skillName={openSkillName} onClose={handleClose} />
    </div>
  )
}

// Usage:
//   import { SkillDrawer } from '../components/settings/SkillDrawer'
//   <SkillDrawer open={open} customerId={id} skill={editingSkill} ... />

import { useState, useEffect, useRef } from 'react'
import { api } from '../../api/client'
import type { Skill, SkillCreatePayload, SkillUpdatePayload } from '../../types/skills'
import { Spinner } from '../ui/Spinner'
import { ErrorPanel } from '../ui/ErrorPanel'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { CategoryBadge } from './CategoryBadge'
import { ApplyToCheckIdsPicker } from './ApplyToCheckIdsPicker'
import { SkillBodyEditor } from './SkillBodyEditor'

const NAME_REGEX = /^[a-z0-9-]+$/

const CATEGORIES = [
  'repo_governance', 'identity_access', 'cicd', 'secrets_mgmt', 'dependencies',
  'sast', 'dast', 'container_security', 'code_quality', 'sdlc_process',
  'compliance', 'collaboration', 'disaster_recovery', 'monitoring', 'migration',
  'platform_arch', 'general',
]

const CATEGORY_DISPLAY: Record<string, string> = {
  repo_governance:    'Repo Governance',
  identity_access:    'Identity & Access',
  cicd:               'CI/CD',
  secrets_mgmt:       'Secrets Mgmt',
  dependencies:       'Dependencies',
  sast:               'SAST',
  dast:               'DAST',
  container_security: 'Container Security',
  code_quality:       'Code Quality',
  sdlc_process:       'SDLC Process',
  compliance:         'Compliance',
  collaboration:      'Collaboration',
  disaster_recovery:  'Disaster Recovery',
  monitoring:         'Monitoring',
  migration:          'Migration',
  platform_arch:      'Platform Architecture',
  general:            'General',
}

interface Props {
  open: boolean
  customerId: string
  skill: Skill | null  // null = create mode
  onClose: () => void
  onSaved: (skill: Skill) => void
  onDeleted: (name: string) => void
  allCheckIds: string[]
}

interface FormState {
  name: string
  description: string
  category: string
  applies_to_check_ids: string[]
  triggers: string[]
  body: string
  enabled: boolean
}

function buildInitialForm(skill: Skill | null): FormState {
  if (!skill) {
    return {
      name: '',
      description: '',
      category: 'general',
      applies_to_check_ids: [],
      triggers: ['remediation', 'scan_enrichment'],
      body: '',
      enabled: true,
    }
  }
  return {
    name: skill.name,
    description: skill.description,
    category: skill.category,
    applies_to_check_ids: skill.applies_to_check_ids,
    triggers: skill.triggers,
    body: '', // fetched lazily for builtin; pre-filled for custom on open
    enabled: skill.enabled,
  }
}

// Built-in read-only view
function BuiltinView({
  skill,
  body,
  bodyLoading,
  onToggle,
  toggling,
}: {
  skill: Skill
  body: string | null
  bodyLoading: boolean
  onToggle: () => void
  toggling: boolean
}) {
  return (
    <div className="space-y-5">
      <dl className="space-y-3">
        <div>
          <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Name</dt>
          <dd className="mt-1 text-sm font-mono text-gray-900">{skill.name}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Description</dt>
          <dd className="mt-1 text-sm text-gray-900">{skill.description}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Category</dt>
          <dd className="mt-1">
            <CategoryBadge category={skill.category} />
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Applies to</dt>
          <dd className="mt-1 flex flex-wrap gap-1">
            {skill.applies_to_check_ids.length === 0 ? (
              <span className="text-sm text-gray-400 italic">any check</span>
            ) : (
              skill.applies_to_check_ids.map((id) => (
                <span key={id} className="px-1.5 py-0.5 bg-gray-100 text-gray-800 rounded text-xs font-mono">
                  {id}
                </span>
              ))
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Triggers</dt>
          <dd className="mt-1 flex flex-wrap gap-1">
            {skill.triggers.map((t) => (
              <span key={t} className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs">
                {t}
              </span>
            ))}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Authored by</dt>
          <dd className="mt-1 text-sm text-gray-900">BPS built-in</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Version</dt>
          <dd className="mt-1 text-sm text-gray-900">{skill.version}</dd>
        </div>
      </dl>

      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Body</p>
        {bodyLoading ? (
          <Spinner className="h-32" />
        ) : body !== null ? (
          <pre className="bg-gray-50 border border-gray-200 rounded-md p-4 text-xs font-mono overflow-x-auto whitespace-pre-wrap">
            {body}
          </pre>
        ) : null}
      </div>

      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Status</p>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
            skill.enabled ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {skill.enabled ? 'Enabled' : 'Disabled'}
        </span>
      </div>

      <div className="border-t border-gray-200 pt-4">
        <button
          type="button"
          onClick={onToggle}
          disabled={toggling}
          className={`px-4 py-2 rounded-md text-sm font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed ${
            skill.enabled
              ? 'bg-gray-100 text-gray-800 hover:bg-gray-200 focus:ring-gray-500'
              : 'bg-brand-600 text-white hover:bg-brand-700 focus:ring-brand-500'
          }`}
        >
          {toggling ? 'Saving...' : skill.enabled ? 'Disable' : 'Enable'}
        </button>
      </div>
    </div>
  )
}

export function SkillDrawer({
  open,
  customerId,
  skill,
  onClose,
  onSaved,
  onDeleted,
  allCheckIds,
}: Props) {
  const firstInputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)

  const mode = skill === null ? 'create' : skill.source === 'builtin' ? 'builtin' : 'custom'

  const [form, setForm] = useState<FormState>(() => buildInitialForm(skill))
  const [nameError, setNameError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [toggling, setToggling] = useState(false)

  // Built-in body loading
  const [builtinBody, setBuiltinBody] = useState<string | null>(null)
  const [builtinBodyLoading, setBuiltinBodyLoading] = useState(false)

  // Custom body loading (for edit mode)
  const [customBodyLoaded, setCustomBodyLoaded] = useState(false)

  // Delete confirm
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Status live region
  const [saveStatus, setSaveStatus] = useState<string>('')

  // Reset form when drawer opens
  useEffect(() => {
    if (open) {
      setForm(buildInitialForm(skill))
      setNameError(null)
      setSaveError(null)
      setSaveStatus('')
      setBuiltinBody(null)
      setCustomBodyLoaded(false)

      setTimeout(() => {
        const el = firstInputRef.current
        if (el) el.focus()
      }, 50)
    }
  }, [open, skill])

  // Load builtin body on open
  useEffect(() => {
    if (open && mode === 'builtin' && skill) {
      setBuiltinBodyLoading(true)
      api
        .getSkillContent(customerId, skill.name)
        .then((r) => setBuiltinBody(r.content))
        .catch(() => setBuiltinBody('Failed to load body.'))
        .finally(() => setBuiltinBodyLoading(false))
    }
  }, [open, mode, skill, customerId])

  // Load custom body on open
  useEffect(() => {
    if (open && mode === 'custom' && skill && !customBodyLoaded) {
      api
        .getSkillContent(customerId, skill.name)
        .then((r) => {
          setForm((prev) => ({ ...prev, body: r.content }))
          setCustomBodyLoaded(true)
        })
        .catch(() => {
          setCustomBodyLoaded(true) // don't keep retrying
        })
    }
  }, [open, mode, skill, customerId, customBodyLoaded])

  // ESC to close
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Return focus on close
  useEffect(() => {
    if (!open && triggerRef.current) {
      triggerRef.current.focus()
    }
  }, [open])

  const updateForm = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const validateName = (name: string): string | null => {
    if (name.length < 3 || name.length > 64) return 'Name must be 3–64 characters'
    if (!NAME_REGEX.test(name)) return 'Name may only contain lowercase letters, digits, and hyphens'
    return null
  }

  const handleSaveCreate = async () => {
    const nameErr = validateName(form.name)
    if (nameErr) { setNameError(nameErr); return }
    setNameError(null)
    setSaveError(null)
    setSaving(true)
    try {
      const payload: SkillCreatePayload = {
        name: form.name,
        description: form.description,
        category: form.category,
        applies_to_check_ids: form.applies_to_check_ids,
        triggers: form.triggers,
        body: form.body,
        enabled: form.enabled,
      }
      const created = await api.createSkill(customerId, payload)
      setSaveStatus('Skill created')
      onSaved(created)
      onClose()
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveEdit = async () => {
    if (!skill) return
    setSaveError(null)
    setSaving(true)
    try {
      const payload: SkillUpdatePayload = {
        description: form.description,
        category: form.category,
        applies_to_check_ids: form.applies_to_check_ids,
        triggers: form.triggers,
        body: form.body || undefined,
        enabled: form.enabled,
      }
      const updated = await api.updateSkill(customerId, skill.name, payload)
      setSaveStatus('Skill saved')
      onSaved(updated)
      onClose()
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!skill) return
    setDeleting(true)
    setConfirmDelete(false)
    try {
      await api.deleteSkill(customerId, skill.name)
      onDeleted(skill.name)
      onClose()
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  const handleBuiltinToggle = async () => {
    if (!skill) return
    setToggling(true)
    try {
      const updated = await api.updateSkill(customerId, skill.name, { enabled: !skill.enabled })
      onSaved(updated)
      onClose()
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Update failed')
    } finally {
      setToggling(false)
    }
  }

  const toggleTrigger = (t: string) => {
    setForm((prev) => ({
      ...prev,
      triggers: prev.triggers.includes(t)
        ? prev.triggers.filter((x) => x !== t)
        : [...prev.triggers, t],
    }))
  }

  if (!open) return null

  const title =
    mode === 'create'
      ? 'New skill'
      : mode === 'builtin'
      ? `Built-in: ${skill!.name}`
      : `Edit: ${skill!.name}`

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-drawer-title"
        className="fixed inset-y-0 right-0 z-50 flex flex-col bg-white shadow-xl w-full max-w-2xl"
        style={{ maxWidth: '720px' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 id="skill-drawer-title" className="text-lg font-semibold text-gray-900">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500 rounded"
            aria-label="Close drawer"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {saveError && (
            <div className="mb-4">
              <ErrorPanel message={saveError} />
            </div>
          )}

          {/* Built-in read-only */}
          {mode === 'builtin' && skill && (
            <BuiltinView
              skill={skill}
              body={builtinBody}
              bodyLoading={builtinBodyLoading}
              onToggle={() => { void handleBuiltinToggle() }}
              toggling={toggling}
            />
          )}

          {/* Create / Custom edit form */}
          {(mode === 'create' || mode === 'custom') && (
            <form
              id="skill-form"
              onSubmit={(e) => {
                e.preventDefault()
                void (mode === 'create' ? handleSaveCreate() : handleSaveEdit())
              }}
              noValidate
            >
              <div className="space-y-5">
                {/* Name */}
                <div>
                  <label htmlFor="skill-name" className="block text-sm font-medium text-gray-700 mb-1">
                    Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="skill-name"
                    ref={(el) => { firstInputRef.current = el }}
                    type="text"
                    value={form.name}
                    onChange={(e) => {
                      updateForm('name', e.target.value)
                      if (nameError) setNameError(null)
                    }}
                    disabled={mode === 'custom'}
                    placeholder="my-skill-name"
                    aria-describedby={nameError ? 'skill-name-error' : undefined}
                    className={[
                      'border border-gray-300 rounded-md px-3 py-2 text-sm font-mono',
                      'focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full',
                      mode === 'custom' ? 'bg-gray-50 cursor-not-allowed' : 'bg-white',
                    ].join(' ')}
                  />
                  {mode === 'create' && (
                    <p className="mt-1 text-xs text-gray-500">
                      Lowercase letters, digits, hyphens only. 3–64 characters.
                    </p>
                  )}
                  {nameError && (
                    <p id="skill-name-error" className="mt-1 text-xs text-red-600">
                      {nameError}
                    </p>
                  )}
                </div>

                {/* Description */}
                <div>
                  <label htmlFor="skill-description" className="block text-sm font-medium text-gray-700 mb-1">
                    Description <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="skill-description"
                    type="text"
                    value={form.description}
                    onChange={(e) => updateForm('description', e.target.value)}
                    placeholder="One-sentence summary of what this skill teaches"
                    maxLength={512}
                    className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
                  />
                </div>

                {/* Category */}
                <div>
                  <label htmlFor="skill-category" className="block text-sm font-medium text-gray-700 mb-1">
                    Category
                  </label>
                  <select
                    id="skill-category"
                    value={form.category}
                    onChange={(e) => updateForm('category', e.target.value)}
                    className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full bg-white"
                  >
                    {CATEGORIES.map((cat) => (
                      <option key={cat} value={cat}>
                        {CATEGORY_DISPLAY[cat] ?? cat}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Applies to check IDs */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Applies to check IDs
                  </label>
                  <ApplyToCheckIdsPicker
                    value={form.applies_to_check_ids}
                    onChange={(next) => updateForm('applies_to_check_ids', next)}
                    allCheckIds={allCheckIds}
                  />
                </div>

                {/* Triggers */}
                <fieldset>
                  <legend className="block text-sm font-medium text-gray-700 mb-1">Triggers</legend>
                  <div className="flex gap-4">
                    {(['remediation', 'scan_enrichment'] as const).map((t) => (
                      <label key={t} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.triggers.includes(t)}
                          onChange={() => toggleTrigger(t)}
                          className="h-4 w-4 text-brand-600 border-gray-300 rounded focus:ring-brand-500"
                        />
                        {t === 'remediation' ? 'Remediation' : 'Scan enrichment'}
                      </label>
                    ))}
                  </div>
                </fieldset>

                {/* Body */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Body (Markdown) <span className="text-red-500">*</span>
                  </label>
                  {mode === 'custom' && !customBodyLoaded ? (
                    <Spinner className="h-32" />
                  ) : (
                    <SkillBodyEditor
                      value={form.body}
                      onChange={(next) => updateForm('body', next)}
                    />
                  )}
                </div>

                {/* Enabled */}
                <div className="flex items-center gap-2">
                  <input
                    id="skill-enabled"
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(e) => updateForm('enabled', e.target.checked)}
                    className="h-4 w-4 text-brand-600 border-gray-300 rounded focus:ring-brand-500"
                  />
                  <label htmlFor="skill-enabled" className="text-sm text-gray-700">
                    Enabled for this customer
                  </label>
                </div>
              </div>
            </form>
          )}
        </div>

        {/* Footer */}
        {mode !== 'builtin' && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50">
            <div>
              {mode === 'custom' && (
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  disabled={deleting}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {deleting ? 'Deleting...' : 'Delete'}
                </button>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span role="status" aria-live="polite" className="text-sm text-emerald-700">
                {saveStatus}
              </span>
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-md text-sm font-medium hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
              >
                Cancel
              </button>
              <button
                type="submit"
                form="skill-form"
                disabled={saving}
                className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={confirmDelete}
        title="Delete custom skill"
        message={`Delete skill "${skill?.name ?? ''}"? This action cannot be undone.`}
        onConfirm={() => { void handleDelete() }}
        onCancel={() => setConfirmDelete(false)}
        confirmLabel="Delete"
        variant="danger"
      />
    </>
  )
}

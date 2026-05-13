import { useState, useEffect, useId } from 'react'
import { api } from '../../api/client'
import type { GlobalSettings, GlobalSettingsUpdate } from '../../types/settings'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorPanel } from '../../components/ui/ErrorPanel'
import { formatDate } from '../../utils/format'

// ── Region options ─────────────────────────────────────────────────────────────

const REGION_OPTIONS = [
  { value: 'eu-west', label: 'EU West (Ireland, Frankfurt)' },
  { value: 'eu-central', label: 'EU Central (Frankfurt)' },
  { value: 'uk', label: 'UK (London)' },
  { value: 'us-east', label: 'US East (Virginia)' },
  { value: 'us-west', label: 'US West (Oregon)' },
  { value: 'apac', label: 'APAC (Singapore, Sydney)' },
]

// ── UUID validation ────────────────────────────────────────────────────────────

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// ── Diff computation ───────────────────────────────────────────────────────────

function computeDiff(original: GlobalSettings, current: GlobalSettings): GlobalSettingsUpdate {
  const diff: GlobalSettingsUpdate = {}
  if (original.global_kill_switch_enabled !== current.global_kill_switch_enabled)
    diff.global_kill_switch_enabled = current.global_kill_switch_enabled
  if (original.default_data_residency_region !== current.default_data_residency_region)
    diff.default_data_residency_region = current.default_data_residency_region
  if (original.audit_log_retention_days !== current.audit_log_retention_days)
    diff.audit_log_retention_days = current.audit_log_retention_days
  if (original.streaming_log_retention_hours !== current.streaming_log_retention_hours)
    diff.streaming_log_retention_hours = current.streaming_log_retention_hours
  if (original.default_llm_connection_id !== current.default_llm_connection_id)
    diff.default_llm_connection_id = current.default_llm_connection_id
  return diff
}

// ── Section heading ────────────────────────────────────────────────────────────

function SectionHeading({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <h2
      id={id}
      className="text-lg font-semibold text-brand-800 mt-8 mb-3 border-b border-gray-200 pb-2"
    >
      {children}
    </h2>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function GlobalSettingsPage() {
  const [settings, setSettings] = useState<GlobalSettings | null>(null)
  const [draft, setDraft] = useState<GlobalSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [uuidError, setUuidError] = useState<string | null>(null)

  // Stable IDs for accessibility
  const killSwitchHeadingId = useId()
  const killSwitchCheckId = useId()
  const residencyId = useId()
  const auditLogId = useId()
  const streamingLogId = useId()
  const llmConnectionId = useId()
  const saveStatusId = useId()

  // ── Load ────────────────────────────────────────────────────────────────────

  function load() {
    let cancelled = false
    setLoading(true)
    setError(null)

    api
      .getGlobalSettings()
      .then((s) => {
        if (cancelled) return
        setSettings(s)
        setDraft({ ...s })
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load global settings')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }

  useEffect(() => {
    return load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Saved indicator auto-clear ──────────────────────────────────────────────

  useEffect(() => {
    if (savedAt === null) return
    const timer = setTimeout(() => setSavedAt(null), 2000)
    return () => clearTimeout(timer)
  }, [savedAt])

  // ── Handlers ────────────────────────────────────────────────────────────────

  async function handleSave() {
    if (!settings || !draft || saving || uuidError !== null) return
    const diff = computeDiff(settings, draft)
    if (Object.keys(diff).length === 0) return

    setSaving(true)
    setSaveError(null)

    try {
      const updated = await api.updateGlobalSettings(diff)
      setSettings(updated)
      setDraft({ ...updated })
      setSavedAt(Date.now())
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  function handleDiscard() {
    if (!settings) return
    setDraft({ ...settings })
    setSaveError(null)
    setUuidError(null)
  }

  function onChangeUuid(v: string) {
    if (!draft) return
    setDraft({ ...draft, default_llm_connection_id: v === '' ? null : v })
    if (v === '' || UUID_REGEX.test(v)) {
      setUuidError(null)
    } else {
      setUuidError('Must be a valid UUID or empty.')
    }
  }

  // ── Loading / error states ──────────────────────────────────────────────────

  if (loading) {
    return <Spinner className="h-48" />
  }

  if (error || !settings || !draft) {
    return (
      <div className="p-6">
        <ErrorPanel
          message={error ?? 'Failed to load global settings'}
          onRetry={() => { load() }}
        />
      </div>
    )
  }

  // ── Derived state ───────────────────────────────────────────────────────────

  const diff = computeDiff(settings, draft)
  const isDirty = Object.keys(diff).length > 0
  const canSave = isDirty && !saving && uuidError === null

  // Build region options — add a custom entry if backend has a value not in list
  const knownValues = REGION_OPTIONS.map((o) => o.value)
  const allRegionOptions =
    draft.default_data_residency_region &&
    !knownValues.includes(draft.default_data_residency_region)
      ? [
          { value: draft.default_data_residency_region, label: draft.default_data_residency_region },
          ...REGION_OPTIONS,
        ]
      : REGION_OPTIONS

  // ── Main render ─────────────────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-4xl">
      {/* Page header */}
      <div className="mb-2">
        <h1 className="text-xl font-semibold text-gray-900">Global Settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          App-wide controls. Changes apply to every customer until overridden by per-customer policy.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void handleSave()
        }}
      >
        {/* ── Kill switch ──────────────────────────────────────────────────── */}
        <section aria-labelledby={killSwitchHeadingId} className="mt-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <h2 id={killSwitchHeadingId} className="text-base font-semibold text-red-800 mb-2">
              Global kill switch
            </h2>
            <div className="flex items-start gap-3">
              <input
                id={killSwitchCheckId}
                type="checkbox"
                role="switch"
                checked={draft.global_kill_switch_enabled}
                onChange={(e) =>
                  setDraft((d) => d ? { ...d, global_kill_switch_enabled: e.target.checked } : d)
                }
                className="mt-0.5 h-4 w-4 rounded border-red-400 text-red-600 focus:ring-red-500"
              />
              <label htmlFor={killSwitchCheckId} className="text-sm text-red-700">
                <span className="font-medium">Block ALL agent runs across every customer.</span>{' '}
                When ON, no agent runs are accepted regardless of any per-customer policy. Use for
                incident response.
              </label>
            </div>
          </div>
        </section>

        {/* ── Data residency ──────────────────────────────────────────────── */}
        <SectionHeading>Data residency</SectionHeading>

        <div>
          <label htmlFor={residencyId} className="block text-sm font-medium text-gray-700 mb-1">
            Default region for new LLM connections
          </label>
          <select
            id={residencyId}
            value={draft.default_data_residency_region}
            onChange={(e) =>
              setDraft((d) => d ? { ...d, default_data_residency_region: e.target.value } : d)
            }
            className="border-gray-300 rounded-md px-3 py-1.5 text-sm
                       focus:ring-2 focus:ring-brand-500 focus:border-brand-500 max-w-[280px] block"
          >
            {allRegionOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-1">
            Customer / connection overrides apply per LLMConnection.
          </p>
        </div>

        {/* ── Retention ───────────────────────────────────────────────────── */}
        <SectionHeading>Retention</SectionHeading>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div>
            <label htmlFor={auditLogId} className="block text-sm font-medium text-gray-700 mb-1">
              Audit log retention (days)
            </label>
            <input
              id={auditLogId}
              type="number"
              min={30}
              max={3650}
              step={1}
              inputMode="numeric"
              required
              value={draft.audit_log_retention_days}
              onChange={(e) =>
                setDraft((d) =>
                  d
                    ? {
                        ...d,
                        audit_log_retention_days:
                          parseInt(e.target.value, 10) || 30,
                      }
                    : d,
                )
              }
              className="border-gray-300 rounded-md px-3 py-1.5 text-sm
                         focus:ring-2 focus:ring-brand-500 focus:border-brand-500 max-w-[120px] block"
            />
            <p className="text-xs text-gray-500 mt-1">
              Minimum 30 days for SOC 2 compliance.
            </p>
          </div>

          <div>
            <label
              htmlFor={streamingLogId}
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Streaming log retention (hours)
            </label>
            <input
              id={streamingLogId}
              type="number"
              min={1}
              max={720}
              step={1}
              inputMode="numeric"
              required
              value={draft.streaming_log_retention_hours}
              onChange={(e) =>
                setDraft((d) =>
                  d
                    ? {
                        ...d,
                        streaming_log_retention_hours:
                          parseInt(e.target.value, 10) || 1,
                      }
                    : d,
                )
              }
              className="border-gray-300 rounded-md px-3 py-1.5 text-sm
                         focus:ring-2 focus:ring-brand-500 focus:border-brand-500 max-w-[120px] block"
            />
            <p className="text-xs text-gray-500 mt-1">Older streaming logs are purged.</p>
          </div>
        </div>

        {/* ── Default LLM connection ───────────────────────────────────────── */}
        <SectionHeading>Default LLM connection</SectionHeading>

        <div>
          <p className="text-sm text-gray-500 mb-3">
            Optional global default used when a customer has no explicit default LLM. Leave empty
            to require per-customer configuration.
          </p>
          <label
            htmlFor={llmConnectionId}
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Connection UUID
          </label>
          <input
            id={llmConnectionId}
            type="text"
            placeholder="00000000-0000-0000-0000-000000000000"
            value={draft.default_llm_connection_id ?? ''}
            onChange={(e) => onChangeUuid(e.target.value)}
            aria-describedby={`${llmConnectionId}-help`}
            className={`border-gray-300 rounded-md px-3 py-1.5 text-sm
                       focus:ring-2 focus:ring-brand-500 focus:border-brand-500 max-w-[280px] block
                       ${uuidError ? 'border-red-400 focus:ring-red-500' : ''}`}
          />
          {uuidError && (
            <p className="text-xs text-red-600 mt-1" role="alert">
              {uuidError}
            </p>
          )}
          <p id={`${llmConnectionId}-help`} className="text-xs text-gray-500 mt-1">
            Leave empty to require per-customer configuration. UUID format:{' '}
            00000000-0000-0000-0000-000000000000.
          </p>
        </div>

        {/* ── Save error ──────────────────────────────────────────────────── */}
        {saveError && (
          <div className="mt-6">
            <ErrorPanel message={saveError} />
          </div>
        )}

        {/* ── Footer actions ───────────────────────────────────────────────── */}
        <div className="mt-8 flex flex-col items-end gap-2 pt-4 border-t border-gray-200">
          <div className="flex items-center gap-3">
            <span
              id={saveStatusId}
              role="status"
              aria-live="polite"
              className="text-xs"
            >
              {saving && <span className="text-gray-500">Saving&hellip;</span>}
              {savedAt !== null && !saving && (
                <span className="text-emerald-700 ml-3">Saved</span>
              )}
            </span>

            <button
              type="button"
              onClick={handleDiscard}
              disabled={!isDirty}
              className="bg-white text-gray-700 border border-gray-300 px-4 py-2 rounded-md text-sm font-medium
                         hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed
                         focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
            >
              Discard changes
            </button>

            <button
              type="submit"
              disabled={!canSave}
              aria-describedby={saveStatusId}
              className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-md text-sm font-medium
                         disabled:opacity-50 disabled:cursor-not-allowed
                         focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
            >
              Save
            </button>
          </div>

          <p className="text-xs text-gray-500">
            Last updated {formatDate(settings.updated_at)}
          </p>
        </div>
      </form>
    </div>
  )
}

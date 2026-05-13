import { useState, useEffect, useId } from 'react'
import { useSettingsCustomerId } from '../../hooks/useSettingsCustomerId'
import { api } from '../../api/client'
import type { RemediationPolicy, RemediationPolicyUpsertPayload } from '../../types/agents'
import type { CategoryRegistryInfo } from '../../types'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorPanel } from '../../components/ui/ErrorPanel'
import { ConfirmDialog } from '../../components/ui/ConfirmDialog'
import { AllowedChecksEditor } from '../../components/settings/AllowedChecksEditor'
import { PathGlobsEditor } from '../../components/settings/PathGlobsEditor'

// ── Defaults ─────────────────────────────────────────────────────────────────

const DEFAULTS: RemediationPolicyUpsertPayload = {
  enabled: false,
  auto_dispatch: false,
  kill_switch_enabled: false,
  allowed_check_ids: [],
  blocked_check_ids: [],
  max_prs_per_scan: 10,
  max_cost_usd_per_month: 100.0,
  allowed_path_globs: [],
  denied_path_globs: [],
  runtime_mode: 'backend',
  oversight_mode: 'strict',
  llm_input_scope: 'hunk',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function policyToPayload(p: RemediationPolicy): RemediationPolicyUpsertPayload {
  return {
    enabled: p.enabled,
    auto_dispatch: p.auto_dispatch,
    kill_switch_enabled: p.kill_switch_enabled,
    allowed_check_ids: p.allowed_check_ids,
    blocked_check_ids: p.blocked_check_ids,
    max_prs_per_scan: p.max_prs_per_scan,
    max_cost_usd_per_month: p.max_cost_usd_per_month,
    allowed_path_globs: p.allowed_path_globs,
    denied_path_globs: p.denied_path_globs,
    runtime_mode: p.runtime_mode,
    oversight_mode: p.oversight_mode,
    llm_input_scope: p.llm_input_scope,
  }
}

function payloadsEqual(
  a: RemediationPolicyUpsertPayload,
  b: RemediationPolicyUpsertPayload,
): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
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

export default function RemediationPolicyPage() {
  const customerId = useSettingsCustomerId()

  const [policy, setPolicy] = useState<RemediationPolicy | null>(null)
  const [draft, setDraft] = useState<RemediationPolicyUpsertPayload>(DEFAULTS)
  const [original, setOriginal] = useState<RemediationPolicyUpsertPayload>(DEFAULTS)
  const [registry, setRegistry] = useState<CategoryRegistryInfo[]>([])

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [deleteNotice, setDeleteNotice] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)

  // Stable IDs for accessibility
  const killSwitchHeadingId = useId()
  const killSwitchCheckId = useId()
  const masterEnableId = useId()
  const autoDispatchId = useId()
  const maxPrsId = useId()
  const maxCostId = useId()
  const saveStatusId = useId()

  // ── Load ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!customerId) {
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([api.getRemediationPolicy(customerId), api.getScannerRegistry()])
      .then(([policyData, registryData]) => {
        if (cancelled) return
        setRegistry(registryData)

        if (policyData === null) {
          setPolicy(null)
          setDraft(DEFAULTS)
          setOriginal(DEFAULTS)
        } else {
          const payload = policyToPayload(policyData)
          setPolicy(policyData)
          setDraft(payload)
          setOriginal(payload)
        }
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load remediation policy')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [customerId])

  // ── Validation ────────────────────────────────────────────────────────────

  function isValid(): boolean {
    const prs = draft.max_prs_per_scan ?? 10
    const cost = draft.max_cost_usd_per_month ?? 100
    return prs >= 1 && prs <= 100 && cost >= 0
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  async function handleSave() {
    if (!customerId || saving || !isValid()) return
    setSaving(true)
    setError(null)
    setSaveSuccess(false)
    setDeleteNotice(false)

    try {
      const saved = await api.upsertRemediationPolicy(customerId, draft)
      const payload = policyToPayload(saved)
      setPolicy(saved)
      setOriginal(payload)
      setDraft(payload)
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save policy')
    } finally {
      setSaving(false)
    }
  }

  function handleDiscard() {
    setDraft({ ...original })
    setError(null)
    setSaveSuccess(false)
  }

  async function handleDelete() {
    if (!customerId) return
    setConfirmDeleteOpen(false)
    try {
      await api.deleteRemediationPolicy(customerId)
      setPolicy(null)
      setDraft(DEFAULTS)
      setOriginal(DEFAULTS)
      setDeleteNotice(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete policy')
    }
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const isDirty = !payloadsEqual(draft, original)
  const canSave = isDirty && !saving && isValid()

  // ── Early-exit renders ────────────────────────────────────────────────────

  if (!customerId) {
    return (
      <div className="p-6">
        <ErrorPanel message="Select a customer to configure the remediation policy." />
      </div>
    )
  }

  if (loading) {
    return <Spinner className="h-48" />
  }

  // ── Main render ───────────────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-4xl">
      {/* Page header */}
      <div className="mb-2">
        <h1 className="text-xl font-semibold text-gray-900">Remediation Policy</h1>
        <p className="mt-1 text-sm text-gray-500">
          Controls how the BPS remediation agent behaves for this customer&apos;s repos. Defaults
          are opt-in only.
        </p>
      </div>

      {/* Delete notice */}
      {deleteNotice && (
        <div className="mt-4 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          Policy deleted &mdash; default behaviour applies.
        </div>
      )}

      {/* ── Kill switch ──────────────────────────────────────────────────── */}
      <section aria-labelledby={killSwitchHeadingId} className="mt-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h2 id={killSwitchHeadingId} className="text-base font-semibold text-red-800 mb-2">
            Kill switch
          </h2>
          <div className="flex items-start gap-3">
            <input
              id={killSwitchCheckId}
              type="checkbox"
              role="switch"
              checked={draft.kill_switch_enabled ?? false}
              onChange={(e) => setDraft((d) => ({ ...d, kill_switch_enabled: e.target.checked }))}
              className="mt-0.5 h-4 w-4 rounded border-red-400 text-red-600 focus:ring-red-500"
            />
            <label htmlFor={killSwitchCheckId} className="text-sm text-red-700">
              <span className="font-medium">Block ALL agent runs for this customer.</span>{' '}
              When ON, no agent runs are accepted regardless of other policy settings.
            </label>
          </div>
        </div>
      </section>

      {/* ── Master enable + auto-dispatch ────────────────────────────────── */}
      <SectionHeading>Master enable &amp; auto-dispatch</SectionHeading>

      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <input
            id={masterEnableId}
            type="checkbox"
            role="switch"
            checked={draft.enabled ?? false}
            onChange={(e) => setDraft((d) => ({ ...d, enabled: e.target.checked }))}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
          />
          <label htmlFor={masterEnableId} className="text-sm text-gray-700">
            <span className="font-medium">Remediation enabled</span> for this customer
          </label>
        </div>

        <div className={`flex items-start gap-3 ${!(draft.enabled ?? false) ? 'opacity-50' : ''}`}>
          <input
            id={autoDispatchId}
            type="checkbox"
            role="switch"
            checked={draft.auto_dispatch ?? false}
            disabled={!(draft.enabled ?? false)}
            onChange={(e) => setDraft((d) => ({ ...d, auto_dispatch: e.target.checked }))}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500
                       disabled:cursor-not-allowed"
          />
          <label htmlFor={autoDispatchId} className="text-sm text-gray-700">
            <span className="font-medium">Auto-dispatch</span> &mdash; automatically trigger an
            agent run after every completed scan (uses the customer&apos;s default LLM connection)
            {!(draft.enabled ?? false) && (
              <span className="ml-1 text-xs text-gray-400">(requires master enable)</span>
            )}
          </label>
        </div>
      </div>

      {/* ── Limits ───────────────────────────────────────────────────────── */}
      <SectionHeading>Limits</SectionHeading>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div>
          <label htmlFor={maxPrsId} className="block text-sm font-medium text-gray-700 mb-1">
            Max PRs per scan
          </label>
          <input
            id={maxPrsId}
            type="number"
            min={1}
            max={100}
            step={1}
            required
            value={draft.max_prs_per_scan ?? 10}
            onChange={(e) =>
              setDraft((d) => ({ ...d, max_prs_per_scan: parseInt(e.target.value, 10) || 1 }))
            }
            className="border-gray-300 rounded-md px-3 py-1.5 text-sm
                       focus:ring-2 focus:ring-brand-500 focus:border-brand-500 max-w-[120px] block"
          />
          <p className="mt-1 text-xs text-gray-400">Range: 1–100</p>
        </div>

        <div>
          <label htmlFor={maxCostId} className="block text-sm font-medium text-gray-700 mb-1">
            Max cost USD per month
          </label>
          <input
            id={maxCostId}
            type="number"
            min={0}
            step={0.01}
            required
            value={draft.max_cost_usd_per_month ?? 100}
            onChange={(e) =>
              setDraft((d) => ({
                ...d,
                max_cost_usd_per_month: parseFloat(e.target.value) || 0,
              }))
            }
            className="border-gray-300 rounded-md px-3 py-1.5 text-sm
                       focus:ring-2 focus:ring-brand-500 focus:border-brand-500 max-w-[120px] block"
          />
          <p className="mt-1 text-xs text-gray-400">$0 or more</p>
        </div>
      </div>

      {/* ── Modes ────────────────────────────────────────────────────────── */}
      <SectionHeading>Modes</SectionHeading>

      <div className="space-y-6">
        {/* Runtime mode */}
        <fieldset>
          <legend className="text-sm font-medium text-gray-700 mb-2">Runtime mode</legend>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="radio"
                name="runtime_mode"
                value="backend"
                checked={(draft.runtime_mode ?? 'backend') === 'backend'}
                onChange={() => setDraft((d) => ({ ...d, runtime_mode: 'backend' }))}
                className="border-gray-300 text-brand-600 focus:ring-brand-500"
              />
              Backend (agent runs in the BPS backend service)
            </label>
            <label
              className="flex items-center gap-2 text-sm text-gray-400 cursor-not-allowed"
              title="CI runner mode is coming in Phase 4"
            >
              <input
                type="radio"
                name="runtime_mode"
                value="ci"
                disabled
                aria-disabled="true"
                className="border-gray-300 text-gray-400 cursor-not-allowed"
              />
              CI runner
              <span className="ml-1 text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                Phase 4 — coming
              </span>
            </label>
          </div>
        </fieldset>

        {/* Oversight mode */}
        <fieldset>
          <legend className="text-sm font-medium text-gray-700 mb-2">Oversight mode</legend>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="radio"
                name="oversight_mode"
                value="strict"
                checked={(draft.oversight_mode ?? 'strict') === 'strict'}
                onChange={() => setDraft((d) => ({ ...d, oversight_mode: 'strict' }))}
                className="border-gray-300 text-brand-600 focus:ring-brand-500"
              />
              <span>
                <span className="font-medium">Strict</span> — PRs opened as draft, mandatory
                human review before merge
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="radio"
                name="oversight_mode"
                value="standard"
                checked={(draft.oversight_mode ?? 'strict') === 'standard'}
                onChange={() => setDraft((d) => ({ ...d, oversight_mode: 'standard' }))}
                className="border-gray-300 text-brand-600 focus:ring-brand-500"
              />
              <span>
                <span className="font-medium">Standard</span> — review required, PRs not forced
                draft
              </span>
            </label>
          </div>
        </fieldset>

        {/* LLM input scope */}
        <fieldset>
          <legend className="text-sm font-medium text-gray-700 mb-2">LLM input scope</legend>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="radio"
                name="llm_input_scope"
                value="hunk"
                checked={(draft.llm_input_scope ?? 'hunk') === 'hunk'}
                onChange={() => setDraft((d) => ({ ...d, llm_input_scope: 'hunk' }))}
                className="border-gray-300 text-brand-600 focus:ring-brand-500"
              />
              <span>
                <span className="font-medium">Hunk-only</span> — only the affected diff hunk is
                sent to the LLM (REQ-031, lowest cost)
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="radio"
                name="llm_input_scope"
                value="file"
                checked={(draft.llm_input_scope ?? 'hunk') === 'file'}
                onChange={() => setDraft((d) => ({ ...d, llm_input_scope: 'file' }))}
                className="border-gray-300 text-brand-600 focus:ring-brand-500"
              />
              <span>
                <span className="font-medium">Full file</span> — entire file is sent for better
                context
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="radio"
                name="llm_input_scope"
                value="repo-context"
                checked={(draft.llm_input_scope ?? 'hunk') === 'repo-context'}
                onChange={() => setDraft((d) => ({ ...d, llm_input_scope: 'repo-context' }))}
                className="border-gray-300 text-brand-600 focus:ring-brand-500"
              />
              <span>
                <span className="font-medium">Repo context</span> — includes broader repo
                structure and related files (highest cost)
              </span>
            </label>
          </div>
        </fieldset>
      </div>

      {/* ── Allowed checks ───────────────────────────────────────────────── */}
      <SectionHeading>Allowed checks</SectionHeading>

      <p className="text-sm text-gray-500 mb-3">
        Restrict the agent to a specific subset of checks. An empty allow-list means all checks are
        allowed. Use blocked checks to deny-list specific check IDs regardless of the allow-list.
      </p>

      {registry.length > 0 ? (
        <AllowedChecksEditor
          registry={registry}
          allowedCheckIds={draft.allowed_check_ids ?? []}
          blockedCheckIds={draft.blocked_check_ids ?? []}
          onChangeAllowed={(ids) => setDraft((d) => ({ ...d, allowed_check_ids: ids }))}
          onChangeBlocked={(ids) => setDraft((d) => ({ ...d, blocked_check_ids: ids }))}
        />
      ) : (
        <p className="text-sm text-gray-400 italic">Registry unavailable.</p>
      )}

      {/* ── Path globs ───────────────────────────────────────────────────── */}
      <SectionHeading>Path globs</SectionHeading>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <PathGlobsEditor
          label="Allowed path globs"
          helpText="Agent may only modify files matching these globs. Empty = no path restriction."
          globs={draft.allowed_path_globs ?? []}
          onChange={(next) => setDraft((d) => ({ ...d, allowed_path_globs: next }))}
          placeholder={'src/**\ntests/**'}
        />
        <PathGlobsEditor
          label="Denied path globs (overrides allow)"
          helpText="Agent will never touch files matching these globs, even if also allowed above."
          globs={draft.denied_path_globs ?? []}
          onChange={(next) => setDraft((d) => ({ ...d, denied_path_globs: next }))}
          placeholder={'infra/**\n.github/**'}
        />
      </div>

      {/* ── Error panel ──────────────────────────────────────────────────── */}
      {error && (
        <div className="mt-6">
          <ErrorPanel message={error} />
        </div>
      )}

      {/* ── Footer actions ───────────────────────────────────────────────── */}
      <div className="mt-8 flex items-center justify-between gap-4 pt-4 border-t border-gray-200">
        {/* Delete link — left side, only when policy exists */}
        <div>
          {policy !== null && (
            <button
              type="button"
              onClick={() => setConfirmDeleteOpen(true)}
              className="text-sm text-red-600 underline hover:no-underline
                         focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 rounded"
            >
              Delete policy
            </button>
          )}
        </div>

        {/* Save + Discard — right side */}
        <div className="flex items-center gap-3">
          <span
            id={saveStatusId}
            role="status"
            aria-live="polite"
            className="text-xs"
          >
            {saving && <span className="text-gray-500">Saving&hellip;</span>}
            {saveSuccess && <span className="text-emerald-700">Saved</span>}
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
            type="button"
            onClick={() => { void handleSave() }}
            disabled={!canSave}
            aria-describedby={saveStatusId}
            className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-md text-sm font-medium
                       disabled:opacity-50 disabled:cursor-not-allowed
                       focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            Save
          </button>
        </div>
      </div>

      {/* ── Delete confirmation dialog ───────────────────────────────────── */}
      <ConfirmDialog
        open={confirmDeleteOpen}
        title="Delete remediation policy"
        message="Delete this customer's remediation policy? The agent will revert to opt-in-safe defaults (no auto-dispatch, no kill switch, no check restrictions). This cannot be undone."
        confirmLabel="Delete policy"
        variant="danger"
        onConfirm={() => { void handleDelete() }}
        onCancel={() => setConfirmDeleteOpen(false)}
      />
    </div>
  )
}

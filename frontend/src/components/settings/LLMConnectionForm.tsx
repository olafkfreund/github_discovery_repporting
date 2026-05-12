// Usage:
//   import LLMConnectionForm from '../components/settings/LLMConnectionForm'
//   <LLMConnectionForm
//     open={isDrawerOpen}
//     customerId={customerId}
//     initial={editingConnection ?? undefined}
//     onClose={() => setDrawerOpen(false)}
//     onSaved={(conn) => { reload(); setDrawerOpen(false) }}
//   />

import { useState, useEffect, useRef, useCallback } from 'react'
import type { LLMConnection, LLMProviderId, ExtraConfig, LLMConnectionValidatePayload } from '../../types/llm'
import { api } from '../../api/client'
import { ErrorPanel } from '../ui/ErrorPanel'
import AnthropicFields from './ProviderFields/AnthropicFields'
import OpenAIFields from './ProviderFields/OpenAIFields'
import BedrockFields from './ProviderFields/BedrockFields'
import AzureOpenAIFields from './ProviderFields/AzureOpenAIFields'
import VertexFields from './ProviderFields/VertexFields'
import OpenAICompatFields from './ProviderFields/OpenAICompatFields'

interface Props {
  open: boolean
  customerId: string
  initial?: LLMConnection
  onClose: () => void
  onSaved: (connection: LLMConnection) => void
}

const PROVIDERS: { id: LLMProviderId; label: string }[] = [
  { id: 'anthropic', label: 'Anthropic' },
  { id: 'openai', label: 'OpenAI' },
  { id: 'bedrock', label: 'AWS Bedrock' },
  { id: 'azure_openai', label: 'Azure OpenAI' },
  { id: 'vertex', label: 'Vertex AI' },
  { id: 'openai_compatible', label: 'OpenAI-compatible' },
]

// Providers where endpoint_url is always visible (required)
const ENDPOINT_REQUIRED: LLMProviderId[] = ['openai_compatible']
// Providers where endpoint_url is optionally visible
const ENDPOINT_OPTIONAL: LLMProviderId[] = ['anthropic', 'openai']
// Providers where endpoint_url is hidden (region/project/deployment-driven)
// bedrock, azure_openai, vertex

function showEndpointUrl(provider: LLMProviderId): 'required' | 'optional' | 'hidden' {
  if (ENDPOINT_REQUIRED.includes(provider)) return 'required'
  if (ENDPOINT_OPTIONAL.includes(provider)) return 'optional'
  return 'hidden'
}

function defaultExtraConfig(provider: LLMProviderId): ExtraConfig {
  switch (provider) {
    case 'anthropic':
      return { provider: 'anthropic' }
    case 'openai':
      return { provider: 'openai', organization_id: null }
    case 'bedrock':
      return { provider: 'bedrock', aws_region: 'us-east-1' }
    case 'azure_openai':
      return { provider: 'azure_openai', azure_deployment: '', api_version: '2024-10-01' }
    case 'vertex':
      return { provider: 'vertex', gcp_project: '', gcp_region: 'us-central1', service_account_json: '' }
    case 'openai_compatible':
      return { provider: 'openai_compatible' }
  }
}

interface FormState {
  name: string
  provider: LLMProviderId
  model: string
  endpoint_url: string
  api_key: string
  is_default: boolean
  extra_config: ExtraConfig
}

interface FormErrors {
  name?: string
  provider?: string
  model?: string
  endpoint_url?: string
  // provider-specific
  azure_deployment?: string
  api_version?: string
  aws_region?: string
  aws_access_key_id?: string
  aws_secret_access_key?: string
  iam_role_arn?: string
  gcp_project?: string
  gcp_region?: string
  service_account_json?: string
}

type TestStatus =
  | { kind: 'idle' }
  | { kind: 'testing' }
  | { kind: 'ok'; latency_ms?: number | null }
  | { kind: 'error'; error: string }

function buildInitialState(initial?: LLMConnection): FormState {
  if (!initial) {
    return {
      name: '',
      provider: 'anthropic',
      model: '',
      endpoint_url: '',
      api_key: '',
      is_default: false,
      extra_config: defaultExtraConfig('anthropic'),
    }
  }
  return {
    name: initial.name,
    provider: initial.provider,
    model: initial.model,
    endpoint_url: initial.endpoint_url ?? '',
    api_key: '', // never pre-filled
    is_default: initial.is_default,
    extra_config: (initial.extra_config as ExtraConfig | null) ?? defaultExtraConfig(initial.provider),
  }
}

export default function LLMConnectionForm({ open, customerId, initial, onClose, onSaved }: Props) {
  const nameInputRef = useRef<HTMLInputElement>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)

  const [form, setForm] = useState<FormState>(() => buildInitialState(initial))
  const [errors, setErrors] = useState<FormErrors>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [testStatus, setTestStatus] = useState<TestStatus>({ kind: 'idle' })
  const [hasEdits, setHasEdits] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [showUpdateKey, setShowUpdateKey] = useState(false)

  // Reset state when drawer opens/closes or initial changes
  useEffect(() => {
    if (open) {
      setForm(buildInitialState(initial))
      setErrors({})
      setSaveError(null)
      setTestStatus({ kind: 'idle' })
      setHasEdits(false)
      setShowApiKey(false)
      setShowUpdateKey(false)
      // Focus name input on next tick
      setTimeout(() => nameInputRef.current?.focus(), 50)
    }
  }, [open, initial])

  // ESC to close
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Return focus to trigger on close
  useEffect(() => {
    if (!open && triggerRef.current) {
      triggerRef.current.focus()
    }
  }, [open])

  const markEdited = () => setHasEdits(true)

  const updateForm = useCallback(<K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    markEdited()
  }, [])

  const handleProviderChange = (provider: LLMProviderId) => {
    setForm((prev) => ({
      ...prev,
      provider,
      extra_config: defaultExtraConfig(provider),
      // Clear endpoint_url when switching to a provider where it's hidden
      endpoint_url: showEndpointUrl(provider) === 'hidden' ? '' : prev.endpoint_url,
    }))
    markEdited()
  }

  const validate = (): FormErrors => {
    const errs: FormErrors = {}

    if (!form.name.trim() || form.name.trim().length < 1) {
      errs.name = 'Name is required'
    } else if (form.name.trim().length > 255) {
      errs.name = 'Name must be 255 characters or fewer'
    }

    if (!form.model.trim()) {
      errs.model = 'Model is required'
    }

    const endpointVisibility = showEndpointUrl(form.provider)
    if (endpointVisibility === 'required' && !form.endpoint_url.trim()) {
      errs.endpoint_url = 'Endpoint URL is required'
    }

    const ec = form.extra_config
    if (ec.provider === 'bedrock') {
      if (!ec.aws_region.trim()) errs.aws_region = 'AWS region is required'
      if (ec.iam_role_arn) {
        // IAM role mode: iam_role_arn must be non-empty
        if (!ec.iam_role_arn.trim()) errs.iam_role_arn = 'IAM role ARN is required'
      } else {
        // Keys mode
        if (!ec.aws_access_key_id?.trim()) errs.aws_access_key_id = 'AWS Access Key ID is required'
        if (!ec.aws_secret_access_key?.trim())
          errs.aws_secret_access_key = 'AWS Secret Access Key is required'
      }
    }

    if (ec.provider === 'azure_openai') {
      if (!ec.azure_deployment.trim()) errs.azure_deployment = 'Azure deployment name is required'
      if (!ec.api_version.trim()) errs.api_version = 'API version is required'
    }

    if (ec.provider === 'vertex') {
      if (!ec.gcp_project.trim()) errs.gcp_project = 'GCP project is required'
      if (!ec.gcp_region.trim()) errs.gcp_region = 'GCP region is required'
      if (!ec.service_account_json.trim()) {
        errs.service_account_json = 'Service account JSON is required'
      } else {
        try {
          JSON.parse(ec.service_account_json)
        } catch {
          errs.service_account_json = 'Must be valid JSON'
        }
      }
    }

    return errs
  }

  const buildPayload = (): LLMConnectionValidatePayload => {
    const endpointVisibility = showEndpointUrl(form.provider)
    return {
      name: form.name.trim(),
      provider: form.provider,
      model: form.model.trim(),
      endpoint_url: endpointVisibility !== 'hidden' && form.endpoint_url.trim() ? form.endpoint_url.trim() : null,
      api_key: form.api_key || null,
      extra_config: form.extra_config,
      is_default: form.is_default,
    }
  }

  const handleTest = async () => {
    setTestStatus({ kind: 'testing' })
    try {
      let result
      if (!initial || hasEdits) {
        // Create or dirty edit: use validate endpoint
        result = await api.validateLLMConnection(buildPayload())
      } else {
        // Clean edit: ping existing connection
        result = await api.testLLMConnection(initial.id)
      }
      if (result.ok) {
        setTestStatus({ kind: 'ok', latency_ms: result.latency_ms })
      } else {
        setTestStatus({ kind: 'error', error: result.error ?? 'Connection failed' })
      }
    } catch (err) {
      setTestStatus({ kind: 'error', error: err instanceof Error ? err.message : 'Test failed' })
    }
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      return
    }
    setErrors({})
    setSaveError(null)
    setSaving(true)

    try {
      const endpointVisibility = showEndpointUrl(form.provider)
      const endpointUrl =
        endpointVisibility !== 'hidden' && form.endpoint_url.trim()
          ? form.endpoint_url.trim()
          : null

      let saved: LLMConnection
      if (!initial) {
        saved = await api.createLLMConnection({
          customer_id: customerId,
          name: form.name.trim(),
          provider: form.provider,
          model: form.model.trim(),
          endpoint_url: endpointUrl,
          api_key: form.api_key || null,
          extra_config: form.extra_config,
          is_default: form.is_default,
        })
      } else {
        const updatePayload: Parameters<typeof api.updateLLMConnection>[1] = {
          name: form.name.trim(),
          model: form.model.trim(),
          endpoint_url: endpointUrl,
          extra_config: form.extra_config,
          is_default: form.is_default,
        }
        // Only send api_key if user explicitly typed something
        if (form.api_key) {
          updatePayload.api_key = form.api_key
        }
        saved = await api.updateLLMConnection(initial.id, updatePayload)
      }
      onSaved(saved)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const testReadyForBuild = (): boolean => {
    if (!form.name.trim() || !form.model.trim()) return false
    if (showEndpointUrl(form.provider) === 'required' && !form.endpoint_url.trim()) return false
    return true
  }

  const renderTestStatus = () => {
    if (testStatus.kind === 'idle') return null
    if (testStatus.kind === 'testing') {
      return <span className="text-sm text-gray-500">Testing...</span>
    }
    if (testStatus.kind === 'ok') {
      const ms = testStatus.latency_ms != null ? ` (${testStatus.latency_ms}ms)` : ''
      return (
        <span className="text-sm text-emerald-700" aria-live="polite">
          OK{ms}
        </span>
      )
    }
    return (
      <span className="text-sm text-red-700" aria-live="polite">
        Failed: {testStatus.error}
      </span>
    )
  }

  const endpointVisibility = showEndpointUrl(form.provider)
  const isEditMode = !!initial

  // Bedrock errors passthrough
  const bedrockErrors = {
    aws_region: errors.aws_region,
    aws_access_key_id: errors.aws_access_key_id,
    aws_secret_access_key: errors.aws_secret_access_key,
    iam_role_arn: errors.iam_role_arn,
  }
  const azureErrors = {
    azure_deployment: errors.azure_deployment,
    api_version: errors.api_version,
  }
  const vertexErrors = {
    gcp_project: errors.gcp_project,
    gcp_region: errors.gcp_region,
    service_account_json: errors.service_account_json,
  }

  if (!open) return null

  return (
    <>
      {/* Overlay — click to close */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="llm-drawer-title"
        className="fixed inset-y-0 right-0 z-50 flex flex-col bg-white shadow-xl w-full max-w-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 id="llm-drawer-title" className="text-lg font-semibold text-gray-900">
            {isEditMode ? 'Edit LLM Provider' : 'Add LLM Provider'}
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

        {/* Scrollable form body */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <form id="llm-conn-form" onSubmit={(e) => { void handleSave(e) }} noValidate>
            <div className="space-y-5">
              {/* Save error */}
              {saveError && (
                <ErrorPanel message={saveError} />
              )}

              {/* Name */}
              <div>
                <label htmlFor="llm-name" className="block text-sm font-medium text-gray-700 mb-1">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="llm-name"
                  ref={nameInputRef}
                  type="text"
                  value={form.name}
                  onChange={(e) => updateForm('name', e.target.value)}
                  placeholder="My Anthropic connection"
                  aria-describedby={errors.name ? 'llm-name-error' : undefined}
                  className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
                />
                {errors.name && (
                  <p id="llm-name-error" className="mt-1 text-xs text-red-600">
                    {errors.name}
                  </p>
                )}
              </div>

              {/* Provider */}
              <div>
                <label htmlFor="llm-provider" className="block text-sm font-medium text-gray-700 mb-1">
                  Provider <span className="text-red-500">*</span>
                </label>
                <select
                  id="llm-provider"
                  value={form.provider}
                  onChange={(e) => handleProviderChange(e.target.value as LLMProviderId)}
                  className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full bg-white"
                >
                  {PROVIDERS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Provider-specific extra fields */}
              {form.extra_config.provider === 'anthropic' && <AnthropicFields />}
              {form.extra_config.provider === 'openai' && (
                <OpenAIFields
                  value={form.extra_config}
                  onChange={(next) => { updateForm('extra_config', { ...next, provider: 'openai' }) }}
                />
              )}
              {form.extra_config.provider === 'bedrock' && (
                <BedrockFields
                  value={form.extra_config}
                  onChange={(next) => { updateForm('extra_config', { ...next, provider: 'bedrock' }) }}
                  errors={bedrockErrors}
                />
              )}
              {form.extra_config.provider === 'azure_openai' && (
                <AzureOpenAIFields
                  value={form.extra_config}
                  onChange={(next) => { updateForm('extra_config', { ...next, provider: 'azure_openai' }) }}
                  errors={azureErrors}
                />
              )}
              {form.extra_config.provider === 'vertex' && (
                <VertexFields
                  value={form.extra_config}
                  onChange={(next) => { updateForm('extra_config', { ...next, provider: 'vertex' }) }}
                  errors={vertexErrors}
                />
              )}
              {form.extra_config.provider === 'openai_compatible' && <OpenAICompatFields />}

              {/* Endpoint URL — conditional by provider */}
              {endpointVisibility !== 'hidden' && (
                <div>
                  <label htmlFor="llm-endpoint-url" className="block text-sm font-medium text-gray-700 mb-1">
                    {endpointVisibility === 'required' ? (
                      <>Endpoint URL <span className="text-red-500">*</span></>
                    ) : (
                      'Base URL (optional)'
                    )}
                  </label>
                  <input
                    id="llm-endpoint-url"
                    type="url"
                    value={form.endpoint_url}
                    onChange={(e) => updateForm('endpoint_url', e.target.value)}
                    placeholder={
                      endpointVisibility === 'required'
                        ? 'https://vllm.example.com/v1'
                        : 'https://api.anthropic.com (leave blank for default)'
                    }
                    aria-describedby={errors.endpoint_url ? 'llm-endpoint-error' : undefined}
                    className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
                  />
                  {endpointVisibility === 'optional' && (
                    <p className="mt-1 text-xs text-gray-500">
                      Override only when using a proxy or custom routing.
                    </p>
                  )}
                  {errors.endpoint_url && (
                    <p id="llm-endpoint-error" className="mt-1 text-xs text-red-600">
                      {errors.endpoint_url}
                    </p>
                  )}
                </div>
              )}

              {/* Model */}
              <div>
                <label htmlFor="llm-model" className="block text-sm font-medium text-gray-700 mb-1">
                  Model <span className="text-red-500">*</span>
                </label>
                <input
                  id="llm-model"
                  type="text"
                  value={form.model}
                  onChange={(e) => updateForm('model', e.target.value)}
                  placeholder="claude-opus-4-5"
                  aria-describedby={errors.model ? 'llm-model-error' : undefined}
                  className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
                />
                {errors.model && (
                  <p id="llm-model-error" className="mt-1 text-xs text-red-600">
                    {errors.model}
                  </p>
                )}
              </div>

              {/* API Key */}
              <div>
                <label htmlFor="llm-api-key" className="block text-sm font-medium text-gray-700 mb-1">
                  API Key
                </label>
                {isEditMode && !showUpdateKey ? (
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-gray-500">
                      {initial.has_api_key ? 'Stored.' : 'Not set.'}
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowUpdateKey(true)}
                      className="text-sm text-brand-700 underline hover:no-underline"
                    >
                      Update key
                    </button>
                  </div>
                ) : (
                  <div className="relative">
                    <input
                      id="llm-api-key"
                      type={showApiKey ? 'text' : 'password'}
                      value={form.api_key}
                      onChange={(e) => updateForm('api_key', e.target.value)}
                      placeholder={isEditMode ? 'Enter new key to replace stored key' : 'sk-ant-...'}
                      className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full pr-16"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey((s) => !s)}
                      className="absolute inset-y-0 right-3 text-xs text-gray-500 hover:text-gray-700"
                    >
                      {showApiKey ? 'Hide' : 'Show'}
                    </button>
                  </div>
                )}
                {isEditMode && (
                  <p className="mt-1 text-xs text-gray-500">
                    Leave blank to keep the existing stored key.
                  </p>
                )}
              </div>

              {/* Set as default */}
              <div className="flex items-center gap-2">
                <input
                  id="llm-is-default"
                  type="checkbox"
                  checked={form.is_default}
                  onChange={(e) => updateForm('is_default', e.target.checked)}
                  className="h-4 w-4 text-brand-600 border-gray-300 rounded focus:ring-brand-500"
                />
                <label htmlFor="llm-is-default" className="text-sm text-gray-700">
                  Set as default
                </label>
              </div>

              {/* Divider */}
              <div className="border-t border-gray-200" />

              {/* Test connection */}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => { void handleTest() }}
                  disabled={!testReadyForBuild() || testStatus.kind === 'testing'}
                  className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-md text-sm font-medium hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
                >
                  {testStatus.kind === 'testing' ? 'Testing...' : 'Test connection'}
                </button>
                {renderTestStatus()}
              </div>
              {testStatus.kind !== 'idle' && testStatus.kind !== 'testing' && (
                <p className="text-xs text-gray-400">
                  Test result is advisory — a failing test does not block saving.
                </p>
              )}
            </div>
          </form>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-md text-sm font-medium hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="llm-conn-form"
            disabled={saving}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </>
  )
}

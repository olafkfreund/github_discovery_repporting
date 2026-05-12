// Usage:
//   import LLMConnectionTable from '../components/settings/LLMConnectionTable'
//   <LLMConnectionTable
//     connections={connections}
//     onEdit={(conn) => { setEditing(conn); setDrawerOpen(true) }}
//     onDelete={(id, name) => setConfirmDelete({ id, name })}
//     onDefaultChange={() => void reload()}
//   />

import { useState } from 'react'
import type { LLMConnection, LLMProviderId } from '../../types/llm'
import { api } from '../../api/client'
import { formatDate } from '../../utils/format'

const PROVIDER_LABELS: Record<LLMProviderId, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  bedrock: 'AWS Bedrock',
  azure_openai: 'Azure OpenAI',
  vertex: 'Vertex AI',
  openai_compatible: 'OpenAI-compatible',
}

const PROVIDER_BADGE_CLASSES: Record<LLMProviderId, string> = {
  anthropic: 'bg-orange-100 text-orange-800',
  openai: 'bg-emerald-100 text-emerald-800',
  bedrock: 'bg-yellow-100 text-yellow-800',
  azure_openai: 'bg-blue-100 text-blue-800',
  vertex: 'bg-purple-100 text-purple-800',
  openai_compatible: 'bg-gray-100 text-gray-800',
}

type TestStatus =
  | { kind: 'idle' }
  | { kind: 'testing' }
  | { kind: 'ok'; latency_ms: number | null | undefined }
  | { kind: 'error'; error: string }

interface Props {
  connections: LLMConnection[]
  onEdit: (connection: LLMConnection) => void
  onDelete: (id: string, name: string) => void
  onDefaultChange: () => void
}

export default function LLMConnectionTable({
  connections,
  onEdit,
  onDelete,
  onDefaultChange,
}: Props) {
  const [testStatuses, setTestStatuses] = useState<Record<string, TestStatus>>({})
  const [settingDefault, setSettingDefault] = useState<string | null>(null)

  const handleTest = async (id: string) => {
    setTestStatuses((prev) => ({ ...prev, [id]: { kind: 'testing' } }))
    try {
      const result = await api.testLLMConnection(id)
      if (result.ok) {
        setTestStatuses((prev) => ({ ...prev, [id]: { kind: 'ok', latency_ms: result.latency_ms } }))
      } else {
        setTestStatuses((prev) => ({
          ...prev,
          [id]: { kind: 'error', error: result.error ?? 'Unknown error' },
        }))
      }
    } catch (err) {
      setTestStatuses((prev) => ({
        ...prev,
        [id]: { kind: 'error', error: err instanceof Error ? err.message : 'Test failed' },
      }))
    }
  }

  const handleSetDefault = async (id: string) => {
    setSettingDefault(id)
    try {
      await api.updateLLMConnection(id, { is_default: true })
      onDefaultChange()
    } catch (err) {
      console.error('Failed to set default:', err instanceof Error ? err.message : err)
    } finally {
      setSettingDefault(null)
    }
  }

  const renderTestStatus = (id: string) => {
    const status = testStatuses[id]
    if (!status || status.kind === 'idle') return null
    if (status.kind === 'testing') {
      return <span className="text-xs text-gray-500 ml-1">Testing...</span>
    }
    if (status.kind === 'ok') {
      const ms = status.latency_ms != null ? ` (${status.latency_ms}ms)` : ''
      return (
        <span className="text-xs text-emerald-700 ml-1" aria-live="polite">
          OK{ms}
        </span>
      )
    }
    return (
      <span className="text-xs text-red-700 ml-1" aria-live="polite">
        Failed: {status.error}
      </span>
    )
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Name
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Provider
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Model
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Default
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              API Key
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Updated
            </th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {connections.map((conn) => (
            <tr key={conn.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 text-sm font-medium text-gray-900">{conn.name}</td>
              <td className="px-4 py-3">
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${PROVIDER_BADGE_CLASSES[conn.provider]}`}
                >
                  {PROVIDER_LABELS[conn.provider]}
                </span>
              </td>
              <td className="px-4 py-3">
                <code className="font-mono text-xs text-gray-700">{conn.model}</code>
              </td>
              <td className="px-4 py-3">
                <input
                  type="radio"
                  name="default-llm-connection"
                  checked={conn.is_default}
                  disabled={settingDefault !== null}
                  onChange={() => { void handleSetDefault(conn.id) }}
                  aria-label={`Set ${conn.name} as default`}
                  className="h-4 w-4 text-brand-600 border-gray-300 focus:ring-brand-500"
                />
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">
                    {conn.has_api_key ? 'Set' : '—'}
                  </span>
                  <button
                    onClick={() => { void handleTest(conn.id) }}
                    disabled={testStatuses[conn.id]?.kind === 'testing'}
                    className="text-xs text-brand-700 underline hover:no-underline disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label={`Test connection for ${conn.name}`}
                  >
                    Test
                  </button>
                  {renderTestStatus(conn.id)}
                </div>
              </td>
              <td className="px-4 py-3 text-xs text-gray-500">
                {formatDate(conn.updated_at, 'date')}
              </td>
              <td className="px-4 py-3 text-right">
                <div className="flex items-center justify-end gap-3">
                  <button
                    onClick={() => onEdit(conn)}
                    className="text-sm text-brand-700 font-medium hover:text-brand-800"
                    aria-label={`Edit ${conn.name}`}
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => onDelete(conn.id, conn.name)}
                    className="text-sm text-red-600 font-medium hover:text-red-700"
                    aria-label={`Delete ${conn.name}`}
                  >
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

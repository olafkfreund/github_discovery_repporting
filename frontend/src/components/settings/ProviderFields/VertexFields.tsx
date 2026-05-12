import { useState } from 'react'

interface VertexExtra {
  gcp_project: string
  gcp_region: string
  service_account_json: string
}

interface Props {
  value: VertexExtra
  onChange: (next: VertexExtra) => void
  errors?: {
    gcp_project?: string
    gcp_region?: string
    service_account_json?: string
  }
}

export default function VertexFields({ value, onChange, errors }: Props) {
  const [jsonError, setJsonError] = useState<string | null>(null)

  const handleJsonBlur = () => {
    if (!value.service_account_json) {
      setJsonError(null)
      return
    }
    try {
      JSON.parse(value.service_account_json)
      setJsonError(null)
    } catch {
      setJsonError('Must be valid JSON')
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <label
          htmlFor="vertex-project"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          GCP Project <span className="text-red-500">*</span>
        </label>
        <input
          id="vertex-project"
          type="text"
          value={value.gcp_project}
          onChange={(e) => onChange({ ...value, gcp_project: e.target.value })}
          placeholder="my-gcp-project-123"
          aria-describedby={errors?.gcp_project ? 'vertex-project-error' : undefined}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
        />
        {errors?.gcp_project && (
          <p id="vertex-project-error" className="mt-1 text-xs text-red-600">
            {errors.gcp_project}
          </p>
        )}
      </div>
      <div>
        <label
          htmlFor="vertex-region"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          GCP Region <span className="text-red-500">*</span>
        </label>
        <input
          id="vertex-region"
          type="text"
          value={value.gcp_region}
          onChange={(e) => onChange({ ...value, gcp_region: e.target.value })}
          placeholder="us-central1"
          aria-describedby={errors?.gcp_region ? 'vertex-region-error' : undefined}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
        />
        {errors?.gcp_region && (
          <p id="vertex-region-error" className="mt-1 text-xs text-red-600">
            {errors.gcp_region}
          </p>
        )}
      </div>
      <div>
        <label
          htmlFor="vertex-sa-json"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Service Account JSON <span className="text-red-500">*</span>
        </label>
        <textarea
          id="vertex-sa-json"
          value={value.service_account_json}
          onChange={(e) => {
            setJsonError(null)
            onChange({ ...value, service_account_json: e.target.value })
          }}
          onBlur={handleJsonBlur}
          rows={8}
          placeholder={'{\n  "type": "service_account",\n  ...\n}'}
          aria-describedby={
            errors?.service_account_json || jsonError ? 'vertex-sa-json-error' : undefined
          }
          className="border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
        />
        <p className="mt-1 text-xs text-gray-500">
          Paste the contents of your service-account JSON file.
        </p>
        {(errors?.service_account_json || jsonError) && (
          <p id="vertex-sa-json-error" className="mt-1 text-xs text-red-600">
            {errors?.service_account_json ?? jsonError}
          </p>
        )}
      </div>
    </div>
  )
}

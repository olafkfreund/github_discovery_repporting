interface AzureOpenAIExtra {
  azure_deployment: string
  api_version: string
}

interface Props {
  value: AzureOpenAIExtra
  onChange: (next: AzureOpenAIExtra) => void
  errors?: {
    azure_deployment?: string
    api_version?: string
  }
}

export default function AzureOpenAIFields({ value, onChange, errors }: Props) {
  return (
    <div className="space-y-4">
      <div>
        <label
          htmlFor="azure-deployment"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Azure Deployment Name <span className="text-red-500">*</span>
        </label>
        <input
          id="azure-deployment"
          type="text"
          value={value.azure_deployment}
          onChange={(e) => onChange({ ...value, azure_deployment: e.target.value })}
          placeholder="my-gpt4-deployment"
          aria-describedby={errors?.azure_deployment ? 'azure-deployment-error' : undefined}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
        />
        <p className="mt-1 text-xs text-gray-500">
          Your Azure OpenAI deployment name, NOT the model ID.
        </p>
        {errors?.azure_deployment && (
          <p id="azure-deployment-error" className="mt-1 text-xs text-red-600">
            {errors.azure_deployment}
          </p>
        )}
      </div>
      <div>
        <label
          htmlFor="azure-api-version"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          API Version <span className="text-red-500">*</span>
        </label>
        <input
          id="azure-api-version"
          type="text"
          value={value.api_version}
          onChange={(e) => onChange({ ...value, api_version: e.target.value })}
          placeholder="2024-10-01"
          aria-describedby={errors?.api_version ? 'azure-api-version-error' : undefined}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
        />
        {errors?.api_version && (
          <p id="azure-api-version-error" className="mt-1 text-xs text-red-600">
            {errors.api_version}
          </p>
        )}
      </div>
    </div>
  )
}

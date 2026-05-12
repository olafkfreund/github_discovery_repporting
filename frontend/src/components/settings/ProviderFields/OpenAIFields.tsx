interface OpenAIExtra {
  organization_id?: string | null
}

interface Props {
  value: OpenAIExtra
  onChange: (next: OpenAIExtra) => void
}

export default function OpenAIFields({ value, onChange }: Props) {
  return (
    <div>
      <label htmlFor="openai-org-id" className="block text-sm font-medium text-gray-700 mb-1">
        Organization ID
      </label>
      <input
        id="openai-org-id"
        type="text"
        value={value.organization_id ?? ''}
        onChange={(e) => onChange({ ...value, organization_id: e.target.value || null })}
        placeholder="org-..."
        className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
      />
      <p className="mt-1 text-xs text-gray-500">
        Optional — only set if your API key is scoped to a specific OpenAI organization.
      </p>
    </div>
  )
}

import { useState } from 'react'

interface BedrockExtra {
  aws_region: string
  aws_access_key_id?: string | null
  aws_secret_access_key?: string | null
  iam_role_arn?: string | null
}

type AuthMode = 'keys' | 'role'

interface Props {
  value: BedrockExtra
  onChange: (next: BedrockExtra) => void
  errors?: {
    aws_region?: string
    aws_access_key_id?: string
    aws_secret_access_key?: string
    iam_role_arn?: string
  }
}

export default function BedrockFields({ value, onChange, errors }: Props) {
  const [showSecret, setShowSecret] = useState(false)

  // Determine auth mode from value: if iam_role_arn is set, use role; otherwise keys
  const authMode: AuthMode = value.iam_role_arn ? 'role' : 'keys'

  const setAuthMode = (mode: AuthMode) => {
    if (mode === 'role') {
      onChange({
        ...value,
        aws_access_key_id: null,
        aws_secret_access_key: null,
        iam_role_arn: value.iam_role_arn ?? '',
      })
    } else {
      onChange({
        ...value,
        iam_role_arn: null,
        aws_access_key_id: value.aws_access_key_id ?? '',
        aws_secret_access_key: value.aws_secret_access_key ?? '',
      })
    }
  }

  return (
    <div className="space-y-4">
      {/* Auth mode selector */}
      <fieldset>
        <legend className="block text-sm font-medium text-gray-700 mb-2">
          Authentication method
        </legend>
        <div className="flex gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="radio"
              name="bedrock-auth-mode"
              value="keys"
              checked={authMode === 'keys'}
              onChange={() => setAuthMode('keys')}
              className="h-4 w-4 text-brand-600 border-gray-300 focus:ring-brand-500"
            />
            AWS access keys
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="radio"
              name="bedrock-auth-mode"
              value="role"
              checked={authMode === 'role'}
              onChange={() => setAuthMode('role')}
              className="h-4 w-4 text-brand-600 border-gray-300 focus:ring-brand-500"
            />
            IAM role
          </label>
        </div>
      </fieldset>

      {/* Keys mode */}
      {authMode === 'keys' && (
        <div className="space-y-4">
          <div>
            <label
              htmlFor="bedrock-access-key-id"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              AWS Access Key ID <span className="text-red-500">*</span>
            </label>
            <input
              id="bedrock-access-key-id"
              type="text"
              value={value.aws_access_key_id ?? ''}
              onChange={(e) => onChange({ ...value, aws_access_key_id: e.target.value || null })}
              placeholder="AKIAIOSFODNN7EXAMPLE"
              aria-describedby={errors?.aws_access_key_id ? 'bedrock-access-key-error' : undefined}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
            />
            {errors?.aws_access_key_id && (
              <p id="bedrock-access-key-error" className="mt-1 text-xs text-red-600">
                {errors.aws_access_key_id}
              </p>
            )}
          </div>
          <div>
            <label
              htmlFor="bedrock-secret-key"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              AWS Secret Access Key <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <input
                id="bedrock-secret-key"
                type={showSecret ? 'text' : 'password'}
                value={value.aws_secret_access_key ?? ''}
                onChange={(e) =>
                  onChange({ ...value, aws_secret_access_key: e.target.value || null })
                }
                placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
                aria-describedby={
                  errors?.aws_secret_access_key ? 'bedrock-secret-key-error' : undefined
                }
                className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full pr-16"
              />
              <button
                type="button"
                onClick={() => setShowSecret((s) => !s)}
                className="absolute inset-y-0 right-3 text-xs text-gray-500 hover:text-gray-700"
              >
                {showSecret ? 'Hide' : 'Show'}
              </button>
            </div>
            {errors?.aws_secret_access_key && (
              <p id="bedrock-secret-key-error" className="mt-1 text-xs text-red-600">
                {errors.aws_secret_access_key}
              </p>
            )}
          </div>
        </div>
      )}

      {/* IAM role mode */}
      {authMode === 'role' && (
        <div>
          <label
            htmlFor="bedrock-iam-role"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            IAM Role ARN <span className="text-red-500">*</span>
          </label>
          <input
            id="bedrock-iam-role"
            type="text"
            value={value.iam_role_arn ?? ''}
            onChange={(e) => onChange({ ...value, iam_role_arn: e.target.value || null })}
            placeholder="arn:aws:iam::123456789012:role/MyBedrockRole"
            aria-describedby={errors?.iam_role_arn ? 'bedrock-iam-role-error' : undefined}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
          />
          {errors?.iam_role_arn && (
            <p id="bedrock-iam-role-error" className="mt-1 text-xs text-red-600">
              {errors.iam_role_arn}
            </p>
          )}
        </div>
      )}

      {/* Region (always shown) */}
      <div>
        <label
          htmlFor="bedrock-region"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          AWS Region <span className="text-red-500">*</span>
        </label>
        <input
          id="bedrock-region"
          type="text"
          value={value.aws_region}
          onChange={(e) => onChange({ ...value, aws_region: e.target.value })}
          placeholder="us-east-1"
          aria-describedby={errors?.aws_region ? 'bedrock-region-error' : undefined}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
        />
        {errors?.aws_region && (
          <p id="bedrock-region-error" className="mt-1 text-xs text-red-600">
            {errors.aws_region}
          </p>
        )}
      </div>
    </div>
  )
}

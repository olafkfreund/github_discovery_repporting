export type LLMProviderId =
  | 'anthropic'
  | 'openai'
  | 'bedrock'
  | 'azure_openai'
  | 'vertex'
  | 'openai_compatible'

// Discriminated union for extra_config — matches backend schemas
export type ExtraConfig =
  | { provider: 'anthropic' }
  | { provider: 'openai'; organization_id?: string | null }
  | {
      provider: 'bedrock'
      aws_region: string
      aws_access_key_id?: string | null
      aws_secret_access_key?: string | null
      iam_role_arn?: string | null
    }
  | { provider: 'azure_openai'; azure_deployment: string; api_version: string }
  | { provider: 'vertex'; gcp_project: string; gcp_region: string; service_account_json: string }
  | { provider: 'openai_compatible' }

export interface LLMConnection {
  id: string
  customer_id: string
  name: string
  provider: LLMProviderId
  model: string
  endpoint_url: string | null
  extra_config: ExtraConfig | null
  is_default: boolean
  has_api_key: boolean
  created_at: string
  updated_at: string
}

export interface LLMConnectionCreatePayload {
  customer_id: string
  name: string
  provider: LLMProviderId
  model: string
  endpoint_url?: string | null
  api_key?: string | null
  extra_config?: ExtraConfig | null
  is_default?: boolean
}

export interface LLMConnectionUpdatePayload {
  name?: string
  model?: string
  endpoint_url?: string | null
  api_key?: string | null
  extra_config?: ExtraConfig | null
  is_default?: boolean
}

export type LLMConnectionValidatePayload = Omit<LLMConnectionCreatePayload, 'customer_id'>

export interface LLMConnectionValidateResult {
  ok: boolean
  latency_ms?: number | null
  error?: string | null
}

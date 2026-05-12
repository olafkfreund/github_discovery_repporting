from __future__ import annotations

"""Pydantic schemas for LLM connection CRUD and validation endpoints."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.enums import LLMProviderEnum

# ---------------------------------------------------------------------------
# Per-provider extra_config models (discriminated by provider literal)
# ---------------------------------------------------------------------------


class AnthropicExtra(BaseModel):
    """Extra configuration for the Anthropic provider.

    No provider-specific extras are required; the discriminator field is
    included solely for union dispatch.
    """

    provider: Literal[LLMProviderEnum.anthropic] = LLMProviderEnum.anthropic


class OpenAIExtra(BaseModel):
    """Extra configuration for the OpenAI provider.

    Attributes:
        organization_id: Optional OpenAI organisation identifier; used when the
            API key belongs to a member of multiple organisations.
    """

    provider: Literal[LLMProviderEnum.openai] = LLMProviderEnum.openai
    organization_id: str | None = None


class BedrockExtra(BaseModel):
    """Extra configuration for the AWS Bedrock provider.

    Attributes:
        aws_region: AWS region where the Bedrock endpoint is located.
        aws_access_key_id: Access key for static credential authentication;
            ``None`` when using an IAM role.
        aws_secret_access_key: Corresponding secret key; ``None`` when using
            an IAM role.
        iam_role_arn: ARN of an IAM role to assume; mutually exclusive with
            static credentials.
    """

    provider: Literal[LLMProviderEnum.bedrock] = LLMProviderEnum.bedrock
    aws_region: str
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    iam_role_arn: str | None = None


class AzureOpenAIExtra(BaseModel):
    """Extra configuration for the Azure OpenAI provider.

    Attributes:
        azure_deployment: Azure deployment name (resource-specific).
        api_version: Azure OpenAI REST API version string.
    """

    provider: Literal[LLMProviderEnum.azure_openai] = LLMProviderEnum.azure_openai
    azure_deployment: str
    api_version: str = "2024-10-01"


class VertexExtra(BaseModel):
    """Extra configuration for the Google Vertex AI provider.

    Attributes:
        gcp_project: Google Cloud project identifier.
        gcp_region: Google Cloud region for the Vertex endpoint.
        service_account_json: JSON-encoded service account credentials.
    """

    provider: Literal[LLMProviderEnum.vertex] = LLMProviderEnum.vertex
    gcp_project: str
    gcp_region: str
    service_account_json: str  # JSON-encoded service account


class OpenAICompatExtra(BaseModel):
    """Extra configuration for an OpenAI-compatible provider.

    No additional fields are required beyond the base ``endpoint_url``; this
    model exists for union discriminator completeness.
    """

    provider: Literal[LLMProviderEnum.openai_compatible] = LLMProviderEnum.openai_compatible


# ---------------------------------------------------------------------------
# Discriminated union — validated in create/update payloads
# ---------------------------------------------------------------------------

ExtraConfig = Annotated[
    AnthropicExtra
    | OpenAIExtra
    | BedrockExtra
    | AzureOpenAIExtra
    | VertexExtra
    | OpenAICompatExtra,
    Field(discriminator="provider"),
]

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class LLMConnectionBase(BaseModel):
    """Shared fields for LLM connection create and validate payloads."""

    name: str = Field(..., min_length=1, max_length=255)
    provider: LLMProviderEnum
    model: str = Field(..., min_length=1, max_length=255)
    endpoint_url: str | None = Field(None, max_length=512)
    extra_config: ExtraConfig | None = None
    is_default: bool = False


class LLMConnectionCreate(LLMConnectionBase):
    """Payload for creating a new LLM connection.

    Attributes:
        customer_id: UUID of the owning customer.
        api_key: Plaintext API key; encrypted before persistence.  Pass
            ``None`` when credentials come from environment variables or IAM
            roles.
    """

    customer_id: UUID
    api_key: str | None = None  # plaintext; encrypted before persistence


class LLMConnectionUpdate(BaseModel):
    """Partial update payload for an existing LLM connection.

    All fields are optional; only supplied (non-``None``) values are applied.
    Omitting ``api_key`` does NOT clear the stored encrypted key.

    Attributes:
        api_key: New plaintext key to re-encrypt and store, or ``None`` to
            leave the existing encrypted key unchanged.
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    model: str | None = Field(None, min_length=1, max_length=255)
    endpoint_url: str | None = Field(None, max_length=512)
    api_key: str | None = None  # optional; only re-encrypts if provided
    extra_config: ExtraConfig | None = None
    is_default: bool | None = None


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class LLMConnectionRead(LLMConnectionBase):
    """LLM connection record returned by the API.

    ``api_key_encrypted`` is NEVER serialised.  The boolean ``has_api_key``
    indicates whether an encrypted key is present without revealing the value.
    ``extra_config`` is returned as a plain ``dict`` (the discriminated-union
    validation is for input only).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime
    has_api_key: bool = False
    extra_config: dict[str, Any] | None = None  # type: ignore[assignment]

    @model_validator(mode="before")
    @classmethod
    def _populate_has_api_key(cls, data: Any) -> Any:
        """Derive ``has_api_key`` from the ORM attribute ``api_key_encrypted``.

        Works for both ORM instances (attribute access) and plain dicts (key
        access) so the schema can be used in tests without a database session.
        """
        if hasattr(data, "api_key_encrypted"):
            # ORM instance path
            data.__dict__.setdefault("has_api_key", bool(data.api_key_encrypted))
        elif isinstance(data, dict) and "has_api_key" not in data:
            data["has_api_key"] = bool(data.get("api_key_encrypted"))
        return data


# ---------------------------------------------------------------------------
# Validate / test schemas
# ---------------------------------------------------------------------------


class LLMConnectionValidatePayload(LLMConnectionBase):
    """Payload for ``POST /validate`` — same shape as Create but no customer required.

    Attributes:
        api_key: Plaintext API key to test; not persisted.
    """

    api_key: str | None = None


class LLMConnectionValidateResult(BaseModel):
    """Result returned by the validate and test endpoints.

    Attributes:
        ok: ``True`` when the provider responded successfully.
        latency_ms: Round-trip latency in milliseconds; ``None`` on failure.
        error: Human-readable error message; ``None`` on success.
    """

    ok: bool
    latency_ms: int | None = None
    error: str | None = None

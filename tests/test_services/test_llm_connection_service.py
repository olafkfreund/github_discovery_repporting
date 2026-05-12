from __future__ import annotations

"""Unit tests for llm_connection_service helpers (no HTTP layer)."""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.llm.base import LLMProviderError, LLMResponse
from backend.models.customer import Customer
from backend.models.enums import LLMProviderEnum
from backend.models.llm import LLMConnection
from backend.schemas.llm import (
    LLMConnectionCreate,
    LLMConnectionUpdate,
)
from backend.services import llm_connection_service as svc
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer(db: AsyncSession, name: str = "Svc Corp") -> Customer:
    slug = name.lower().replace(" ", "-")
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


def _fake_connection(
    *,
    provider: LLMProviderEnum = LLMProviderEnum.anthropic,
    model: str = "claude-3-5-sonnet-20241022",
    api_key: str | None = None,
    extra_config: dict[str, Any] | None = None,
    endpoint_url: str | None = None,
) -> LLMConnection:
    """Build an in-memory LLMConnection without a DB session."""
    conn = LLMConnection(
        customer_id=uuid.uuid4(),
        name="test",
        provider=provider,
        model=model,
        endpoint_url=endpoint_url,
        api_key_encrypted=secrets_service.encrypt(api_key) if api_key else None,
        extra_config=extra_config,
    )
    conn.id = uuid.uuid4()
    return conn


# ---------------------------------------------------------------------------
# to_provider_config round-trip tests
# ---------------------------------------------------------------------------


class TestToProviderConfig:
    def test_anthropic_no_key(self) -> None:
        """to_provider_config returns correct dict for Anthropic without api_key."""
        conn = _fake_connection(provider=LLMProviderEnum.anthropic)
        cfg = svc.to_provider_config(conn)

        assert cfg["provider"] == "anthropic"
        assert cfg["model"] == "claude-3-5-sonnet-20241022"
        assert cfg["api_key"] is None
        assert cfg["endpoint_url"] is None
        assert cfg["extra_config"] is None

    def test_anthropic_with_key(self) -> None:
        """to_provider_config decrypts api_key correctly."""
        conn = _fake_connection(provider=LLMProviderEnum.anthropic, api_key="sk-secret")
        cfg = svc.to_provider_config(conn)

        assert cfg["api_key"] == "sk-secret"

    def test_openai(self) -> None:
        """to_provider_config returns openai provider string."""
        conn = _fake_connection(provider=LLMProviderEnum.openai, model="gpt-4o")
        cfg = svc.to_provider_config(conn)
        assert cfg["provider"] == "openai"
        assert cfg["model"] == "gpt-4o"

    def test_bedrock_with_extra(self) -> None:
        """to_provider_config passes through extra_config dict."""
        extra = {"aws_region": "eu-west-1", "provider": "bedrock"}
        conn = _fake_connection(
            provider=LLMProviderEnum.bedrock,
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            extra_config=extra,
        )
        cfg = svc.to_provider_config(conn)

        assert cfg["provider"] == "bedrock"
        assert cfg["extra_config"]["aws_region"] == "eu-west-1"

    def test_azure_openai_with_endpoint(self) -> None:
        """to_provider_config includes endpoint_url for Azure OpenAI."""
        conn = _fake_connection(
            provider=LLMProviderEnum.azure_openai,
            model="gpt-4o",
            endpoint_url="https://myresource.openai.azure.com",
            extra_config={
                "azure_deployment": "my-deployment",
                "api_version": "2024-10-01",
                "provider": "azure_openai",
            },
        )
        cfg = svc.to_provider_config(conn)

        assert cfg["provider"] == "azure_openai"
        assert cfg["endpoint_url"] == "https://myresource.openai.azure.com"
        assert cfg["extra_config"]["azure_deployment"] == "my-deployment"

    def test_vertex(self) -> None:
        """to_provider_config returns vertex config."""
        conn = _fake_connection(
            provider=LLMProviderEnum.vertex,
            model="gemini-1.5-pro",
            extra_config={
                "gcp_project": "my-project",
                "gcp_region": "us-central1",
                "service_account_json": "{}",
                "provider": "vertex",
            },
        )
        cfg = svc.to_provider_config(conn)
        assert cfg["provider"] == "vertex"
        assert cfg["extra_config"]["gcp_project"] == "my-project"

    def test_openai_compatible(self) -> None:
        """to_provider_config returns openai_compatible config."""
        conn = _fake_connection(
            provider=LLMProviderEnum.openai_compatible,
            model="llama-3",
            endpoint_url="http://localhost:11434/v1",
        )
        cfg = svc.to_provider_config(conn)
        assert cfg["provider"] == "openai_compatible"
        assert cfg["endpoint_url"] == "http://localhost:11434/v1"


# ---------------------------------------------------------------------------
# CRUD service tests (with DB session)
# ---------------------------------------------------------------------------


class TestCreateConnection:
    @pytest.mark.asyncio
    async def test_create_persists(self, db_session: AsyncSession) -> None:
        """create_connection stores a connection in the database."""
        customer = await _create_customer(db_session)
        payload = LLMConnectionCreate(
            customer_id=customer.id,
            name="My LLM",
            provider=LLMProviderEnum.anthropic,
            model="claude-3-5-sonnet-20241022",
            api_key="sk-secret",
        )
        conn = await svc.create_connection(db_session, payload)

        assert conn.id is not None
        assert conn.name == "My LLM"
        assert conn.api_key_encrypted is not None
        # Stored bytes must NOT be the plaintext.
        assert conn.api_key_encrypted != b"sk-secret"
        # Must be decryptable.
        assert secrets_service.decrypt(conn.api_key_encrypted) == "sk-secret"

    @pytest.mark.asyncio
    async def test_create_sets_default_clears_others(self, db_session: AsyncSession) -> None:
        """When is_default=True, existing defaults are cleared."""
        customer = await _create_customer(db_session)
        payload_a = LLMConnectionCreate(
            customer_id=customer.id,
            name="First",
            provider=LLMProviderEnum.anthropic,
            model="claude-3-5-sonnet-20241022",
            is_default=True,
        )
        conn_a = await svc.create_connection(db_session, payload_a)
        assert conn_a.is_default is True

        payload_b = LLMConnectionCreate(
            customer_id=customer.id,
            name="Second",
            provider=LLMProviderEnum.openai,
            model="gpt-4o",
            is_default=True,
        )
        await svc.create_connection(db_session, payload_b)

        # Re-load conn_a from DB.
        await db_session.refresh(conn_a)
        assert conn_a.is_default is False


class TestUpdateConnection:
    @pytest.mark.asyncio
    async def test_update_api_key_omitted_preserves_key(self, db_session: AsyncSession) -> None:
        """Omitting api_key in update does not clear stored encrypted key."""
        customer = await _create_customer(db_session)
        payload = LLMConnectionCreate(
            customer_id=customer.id,
            name="Conn",
            provider=LLMProviderEnum.anthropic,
            model="model-a",
            api_key="original",
        )
        conn = await svc.create_connection(db_session, payload)
        original_encrypted = conn.api_key_encrypted

        update_payload = LLMConnectionUpdate(model="model-b")
        updated = await svc.update_connection(db_session, conn.id, update_payload)

        assert updated.api_key_encrypted == original_encrypted

    @pytest.mark.asyncio
    async def test_update_api_key_provided_re_encrypts(self, db_session: AsyncSession) -> None:
        """Providing api_key in update replaces the stored encrypted key."""
        customer = await _create_customer(db_session)
        payload = LLMConnectionCreate(
            customer_id=customer.id,
            name="Conn",
            provider=LLMProviderEnum.anthropic,
            model="model-a",
            api_key="original",
        )
        conn = await svc.create_connection(db_session, payload)

        update_payload = LLMConnectionUpdate(api_key="updated-key")
        updated = await svc.update_connection(db_session, conn.id, update_payload)

        assert secrets_service.decrypt(updated.api_key_encrypted) == "updated-key"


class TestGetConnectionNotFound:
    @pytest.mark.asyncio
    async def test_raises_404(self, db_session: AsyncSession) -> None:
        """get_connection raises HTTPException 404 for unknown UUID."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await svc.get_connection(db_session, uuid.uuid4())

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# ping_connection tests
# ---------------------------------------------------------------------------


class TestPingConnection:
    @pytest.mark.asyncio
    async def test_ping_success(self) -> None:
        """ping_connection returns ok=True and latency_ms when chat succeeds."""
        conn = _fake_connection()
        mock_response = LLMResponse(text="pong")
        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=mock_response)

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await svc.ping_connection(conn)

        assert result.ok is True
        assert result.latency_ms is not None
        assert result.error is None

    @pytest.mark.asyncio
    async def test_ping_provider_error(self) -> None:
        """ping_connection returns ok=False and error message when LLMProviderError raised."""
        conn = _fake_connection()
        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(side_effect=LLMProviderError("rate limit"))

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await svc.ping_connection(conn)

        assert result.ok is False
        assert "rate limit" in result.error
        assert result.latency_ms is None

    @pytest.mark.asyncio
    async def test_ping_unexpected_error(self) -> None:
        """ping_connection returns ok=False when an unexpected exception is raised."""
        conn = _fake_connection()
        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(side_effect=RuntimeError("timeout"))

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await svc.ping_connection(conn)

        assert result.ok is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# ping_payload tests
# ---------------------------------------------------------------------------


class TestPingPayload:
    @pytest.mark.asyncio
    async def test_ping_payload_success(self) -> None:
        """ping_payload returns ok=True for valid config."""
        mock_response = LLMResponse(text="pong")
        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=mock_response)

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await svc.ping_payload(
                {
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "api_key": "sk-test",
                    "endpoint_url": None,
                    "extra_config": None,
                }
            )

        assert result.ok is True

    @pytest.mark.asyncio
    async def test_ping_payload_error(self) -> None:
        """ping_payload returns ok=False on LLMProviderError."""
        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(side_effect=LLMProviderError("bad creds"))

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await svc.ping_payload(
                {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "bad",
                    "endpoint_url": None,
                    "extra_config": None,
                }
            )

        assert result.ok is False
        assert "bad creds" in result.error

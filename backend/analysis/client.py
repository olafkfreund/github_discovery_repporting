from __future__ import annotations

"""Provider-agnostic async wrapper for LLM-based analysis calls.

:class:`AnalysisClient` accepts any :class:`~backend.llm.base.LLMProvider`
instance and exposes a single coroutine — :meth:`AnalysisClient.analyze` —
that sends a prompt to the model and returns the raw text response.

The module-level singleton has been **removed**.  Call
:func:`get_analysis_client` to obtain a cached client backed by either a
caller-supplied provider or the default Anthropic provider (constructed from
:data:`~backend.config.settings`).

Example::

    from backend.analysis.client import get_analysis_client

    client = get_analysis_client()
    text = await client.analyze(prompt="...", system="...")
"""

import logging

from backend.config import settings
from backend.llm.base import LLMMessage, LLMProvider, LLMProviderError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class AnalysisClientError(RuntimeError):
    """Raised when the LLM provider call fails or is misconfigured.

    Callers that previously caught :class:`AnalysisClientError` continue to
    work unchanged — the exception class is still exported from this module.
    """


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AnalysisClient:
    """Provider-agnostic async wrapper for analysis calls.

    Args:
        provider:   Any object satisfying the
                    :class:`~backend.llm.base.LLMProvider` structural protocol.
        max_tokens: Maximum completion tokens forwarded to
                    :meth:`~backend.llm.base.LLMProvider.chat`.
                    Defaults to ``8192``.

    Example::

        from backend.llm.factory import get_llm_provider
        from backend.analysis.client import AnalysisClient

        provider = get_llm_provider({
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "api_key": "sk-ant-...",
            "endpoint_url": None,
            "extra_config": None,
        })
        client = AnalysisClient(provider=provider)
        text = await client.analyze(prompt="...", system="...")
    """

    def __init__(self, provider: LLMProvider, max_tokens: int = 8192) -> None:
        self._provider: LLMProvider = provider
        self._max_tokens: int = max_tokens
        logger.debug(
            "AnalysisClient: initialised with provider=%r max_tokens=%d.",
            getattr(type(provider), "provider_id", repr(provider)),
            max_tokens,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        prompt: str,
        system: str,
        json_schema: dict[str, object] | None = None,
    ) -> str:
        """Send *prompt* to the underlying LLM provider and return the text.

        Args:
            prompt:      The user-turn message containing the scan data and
                         output instructions.
            system:      The system-turn message that establishes the assistant
                         persona and behavioural guidelines.
            json_schema: Optional JSON Schema dict passed to
                         :meth:`~backend.llm.base.LLMProvider.chat` when the
                         provider supports native structured output.  Callers
                         should only supply this when
                         ``provider.supports_structured_output`` is ``True``.

        Returns:
            The raw text string returned by the provider.

        Raises:
            AnalysisClientError: If the provider raises
                :class:`~backend.llm.base.LLMProviderError` or any other
                exception, or if the response contains no text.
        """
        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=prompt),
        ]

        provider_id = getattr(type(self._provider), "provider_id", "unknown")
        logger.info(
            "AnalysisClient.analyze: calling provider=%s max_tokens=%d json_schema=%s.",
            provider_id,
            self._max_tokens,
            "yes" if json_schema else "no",
        )

        try:
            response = await self._provider.chat(
                messages,
                max_tokens=self._max_tokens,
                json_schema=json_schema,
            )
        except LLMProviderError as exc:
            logger.error("AnalysisClient.analyze: provider error — %s", exc)
            raise AnalysisClientError(f"LLM provider error: {exc}") from exc
        except Exception as exc:
            logger.error("AnalysisClient.analyze: unexpected error — %s", exc)
            raise AnalysisClientError(f"Unexpected error from LLM provider: {exc}") from exc

        if not response.text:
            raise AnalysisClientError("LLM provider returned an empty response.")

        logger.debug(
            "AnalysisClient.analyze: received %d characters.",
            len(response.text),
        )
        return response.text


# ---------------------------------------------------------------------------
# Factory / cache
# ---------------------------------------------------------------------------

# Module-level cache keyed by the id() of the provider instance so that
# repeated calls with the same provider object share one AnalysisClient.
_client_cache: dict[int, AnalysisClient] = {}


def get_analysis_client(provider: LLMProvider | None = None) -> AnalysisClient:
    """Return a cached :class:`AnalysisClient` for *provider*.

    When *provider* is ``None`` a default :class:`~backend.llm.base.LLMProvider`
    backed by the Anthropic API is constructed from
    :data:`~backend.config.settings`.  This preserves single-tenant local-dev
    behaviour until a Settings UI ships.

    The client is cached by the ``id()`` of the provider instance so repeated
    calls with the same object return the same :class:`AnalysisClient` without
    reconstruction overhead.

    Args:
        provider: An optional :class:`~backend.llm.base.LLMProvider` instance.
                  Pass ``None`` (default) to use the built-in Anthropic provider.

    Returns:
        A ready-to-use :class:`AnalysisClient`.

    Example::

        # Default Anthropic-backed client.
        client = get_analysis_client()

        # Custom provider (e.g. OpenAI).
        from backend.llm.factory import get_llm_provider
        openai_provider = get_llm_provider({"provider": "openai", ...})
        client = get_analysis_client(openai_provider)
    """
    if provider is None:
        # Build (lazily) the default Anthropic provider.
        from backend.llm.factory import get_llm_provider

        provider = get_llm_provider(
            {
                "provider": "anthropic",
                "model": "claude-opus-4-6",
                "api_key": settings.ANTHROPIC_API_KEY,
                "endpoint_url": None,
                "extra_config": None,
            }
        )

    cache_key = id(provider)
    if cache_key not in _client_cache:
        _client_cache[cache_key] = AnalysisClient(provider=provider)

    return _client_cache[cache_key]

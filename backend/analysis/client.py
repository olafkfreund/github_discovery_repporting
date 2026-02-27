from __future__ import annotations

"""Thin async wrapper around the Anthropic Messages API.

:class:`AnalysisClient` owns a single :class:`anthropic.AsyncAnthropic`
instance and exposes a single coroutine — :meth:`AnalysisClient.analyze` —
that sends a prompt to the model and returns the raw text response.

A module-level singleton :data:`analysis_client` is created at import time
using :data:`~backend.config.settings`.  When ``ANTHROPIC_API_KEY`` is not
configured the singleton is still constructed but any call to
:meth:`~AnalysisClient.analyze` will raise :class:`AnalysisClientError` with
a descriptive message rather than an obscure Anthropic SDK error.
"""

import logging

import anthropic

from backend.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model constant
# ---------------------------------------------------------------------------

_MODEL: str = "claude-opus-4-6"
_MAX_TOKENS: int = 8192

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class AnalysisClientError(RuntimeError):
    """Raised when the Anthropic API call fails or is misconfigured."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AnalysisClient:
    """Async wrapper around :class:`anthropic.AsyncAnthropic`.

    Args:
        api_key: Anthropic API key.  An empty string is accepted at
                 construction time (so the singleton can always be created)
                 but will cause :meth:`analyze` to raise
                 :class:`AnalysisClientError` immediately rather than
                 forwarding the request to the API.

    Example::

        client = AnalysisClient(api_key="sk-ant-...")
        text = await client.analyze(prompt="...", system="...")
    """

    def __init__(self, api_key: str) -> None:
        self._api_key: str = api_key
        if api_key:
            self._client: anthropic.AsyncAnthropic | None = anthropic.AsyncAnthropic(
                api_key=api_key
            )
            logger.debug("AnalysisClient: Anthropic async client initialised.")
        else:
            self._client = None
            logger.warning(
                "AnalysisClient: ANTHROPIC_API_KEY is not configured — "
                "AI analysis will be unavailable until the key is set."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, prompt: str, system: str) -> str:
        """Send *prompt* to Claude and return the plain-text response.

        Args:
            prompt: The user-turn message containing the scan data and
                    output instructions.
            system: The system-turn message that establishes the assistant
                    persona and behavioural guidelines.

        Returns:
            The raw text content of the first ``TextBlock`` in the response.

        Raises:
            AnalysisClientError: If the API key is absent, if the Anthropic
                API returns an error, or if the response contains no usable
                text content.
        """
        if self._client is None:
            raise AnalysisClientError(
                "Anthropic API key is not configured.  Set ANTHROPIC_API_KEY "
                "in the environment or .env file."
            )

        logger.info(
            "AnalysisClient.analyze: calling %s (max_tokens=%d).",
            _MODEL,
            _MAX_TOKENS,
        )

        try:
            message = await self._client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIStatusError as exc:
            logger.error(
                "AnalysisClient.analyze: API status error %s — %s",
                exc.status_code,
                exc.message,
            )
            raise AnalysisClientError(
                f"Anthropic API returned HTTP {exc.status_code}: {exc.message}"
            ) from exc
        except anthropic.APIConnectionError as exc:
            logger.error("AnalysisClient.analyze: connection error — %s", exc)
            raise AnalysisClientError(
                f"Failed to connect to Anthropic API: {exc}"
            ) from exc
        except anthropic.APIError as exc:
            logger.error("AnalysisClient.analyze: unexpected API error — %s", exc)
            raise AnalysisClientError(
                f"Anthropic API error: {exc}"
            ) from exc

        # Extract text from the first TextBlock in the response.
        for block in message.content:
            if hasattr(block, "text"):
                logger.debug(
                    "AnalysisClient.analyze: received %d characters.",
                    len(block.text),
                )
                return block.text

        raise AnalysisClientError(
            "Anthropic API response contained no text content blocks."
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

analysis_client: AnalysisClient = AnalysisClient(api_key=settings.ANTHROPIC_API_KEY)

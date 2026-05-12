from __future__ import annotations

"""Unit tests for :class:`~backend.analysis.analyzer.DevOpsAnalyzer`.

Tests verify:

- :meth:`DevOpsAnalyzer.analyze_scan` delegates to the injected
  :class:`~backend.analysis.client.AnalysisClient`.
- DI parameter ``analysis_client`` on :meth:`analyze_scan` overrides the
  instance-level client.
- The fallback result is returned when the client raises
  :class:`~backend.analysis.client.AnalysisClientError`.
- When :attr:`~backend.llm.base.LLMProvider.supports_structured_output` is
  ``True`` the analyzer passes ``json_schema=`` to
  :meth:`AnalysisClient.analyze` rather than embedding the schema in the prompt.
- When :attr:`~backend.llm.base.LLMProvider.supports_structured_output` is
  ``False`` the prompt contains the JSON schema text.
- The module-level :data:`~backend.analysis.analyzer.analyzer` singleton is a
  :class:`DevOpsAnalyzer` with no pre-bound client.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.analysis.analyzer import DevOpsAnalyzer, analyzer
from backend.analysis.client import AnalysisClient, AnalysisClientError
from backend.analysis.schemas import AnalysisResult
from backend.llm.base import LLMMessage, LLMResponse
from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.scanners.orchestrator import CategoryScore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_check(
    check_id: str = "REPO-001",
    check_name: str = "Branch Protection",
    category: Category = Category.repo_governance,
    severity: Severity = Severity.high,
    weight: float = 1.0,
) -> ScanCheck:
    return ScanCheck(
        check_id=check_id,
        check_name=check_name,
        category=category,
        severity=severity,
        weight=weight,
    )


def _make_result(
    check: ScanCheck | None = None,
    status: CheckStatus = CheckStatus.passed,
    detail: str = "",
) -> CheckResult:
    return CheckResult(
        check=check or _make_check(),
        status=status,
        detail=detail,
        evidence={},
    )


def _make_category_scores() -> dict[Category, CategoryScore]:
    return {
        Category.repo_governance: CategoryScore(
            category=Category.repo_governance,
            score=8.0,
            max_score=10.0,
            weight=0.1,
            finding_count=2,
            pass_count=1,
            fail_count=1,
        )
    }


def _minimal_analysis_result_json() -> str:
    """Return a JSON string that passes AnalysisResult Pydantic validation."""
    return json.dumps(
        {
            "executive_summary": "Good posture overall.",
            "category_narratives": [
                {
                    "category": "repo_governance",
                    "score_percentage": 80.0,
                    "summary": "Strong governance.",
                    "strengths": ["Branch protection enabled."],
                    "weaknesses": [],
                    "key_findings": ["8/10 checks passed."],
                }
            ],
            "recommendations": [
                {
                    "priority": 1,
                    "title": "Enable 2FA",
                    "description": "Enforce 2FA for all members.",
                    "category": "identity_access",
                    "effort": "low",
                    "impact": "high",
                    "check_ids": ["IAM-001"],
                }
            ],
            "benchmark_comparisons": [],
            "overall_maturity_assessment": "Medium maturity.",
            "risk_highlights": ["Some checks failed."],
        }
    )


# ---------------------------------------------------------------------------
# Fake providers for structured-output detection tests
# ---------------------------------------------------------------------------


class FakeProviderWithStructuredOutput:
    """Provider that advertises native structured output support."""

    provider_id = "openai"
    supports_structured_output = True
    supports_tool_use = True

    def __init__(self) -> None:
        self.last_json_schema: dict[str, Any] | None = None

    async def chat(
        self,
        messages: list[LLMMessage],
        tools=None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.last_json_schema = json_schema
        return LLMResponse(text=_minimal_analysis_result_json(), finish_reason="stop")

    async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
        return
        yield  # pragma: no cover


class FakeProviderWithoutStructuredOutput:
    """Provider that does NOT support native structured output."""

    provider_id = "bedrock"
    supports_structured_output = False
    supports_tool_use = True

    def __init__(self) -> None:
        self.last_messages: list[LLMMessage] = []
        self.last_json_schema: dict[str, Any] | None = None

    async def chat(
        self,
        messages: list[LLMMessage],
        tools=None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.last_messages = messages
        self.last_json_schema = json_schema
        return LLMResponse(text=_minimal_analysis_result_json(), finish_reason="stop")

    async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
        return
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# Fake AnalysisClient helpers
# ---------------------------------------------------------------------------


class _FakeProviderNoStructured:
    """Stub provider with supports_structured_output=False for mock clients."""

    provider_id = "stub"
    supports_structured_output = False
    supports_tool_use = False


def _make_mock_client(
    response_text: str = "",
    raise_error: str | None = None,
    capture_kwargs: dict | None = None,
) -> AnalysisClient:
    """Return a stub AnalysisClient whose analyze() records calls or raises.

    The returned object is a real :class:`AnalysisClient` instance so that
    ``effective_client._provider`` attribute access inside :meth:`analyze_scan`
    does not fail.  The underlying provider has
    ``supports_structured_output=False`` so the prompt-injection code path is
    exercised (which is the simpler path).
    """
    # Build a real AnalysisClient over the stub provider.
    stub_provider = _FakeProviderNoStructured()
    client = AnalysisClient.__new__(AnalysisClient)
    client._provider = stub_provider  # type: ignore[attr-defined]
    client._max_tokens = 8192

    if raise_error is not None:
        client.analyze = AsyncMock(side_effect=AnalysisClientError(raise_error))  # type: ignore[method-assign]
    else:
        recorded = capture_kwargs if capture_kwargs is not None else {}

        async def _analyze(prompt: str, system: str, json_schema=None) -> str:
            recorded["prompt"] = prompt
            recorded["system"] = system
            recorded["json_schema"] = json_schema
            return response_text or _minimal_analysis_result_json()

        client.analyze = _analyze  # type: ignore[method-assign]
    return client


# ---------------------------------------------------------------------------
# Tests: DevOpsAnalyzer singleton
# ---------------------------------------------------------------------------


class TestAnalyzerSingleton:
    """Tests for the module-level :data:`analyzer` singleton."""

    def test_singleton_is_devops_analyzer(self) -> None:
        assert isinstance(analyzer, DevOpsAnalyzer)

    def test_singleton_has_no_pre_bound_client(self) -> None:
        """The singleton must have no pre-bound client (lazy construction)."""
        assert analyzer._client is None


# ---------------------------------------------------------------------------
# Tests: DevOpsAnalyzer with injected client via __init__
# ---------------------------------------------------------------------------


class TestDevOpsAnalyzerInit:
    """Tests for :class:`DevOpsAnalyzer` initialisation."""

    def test_init_with_client(self) -> None:
        mock_client = MagicMock(spec=AnalysisClient)
        az = DevOpsAnalyzer(client=mock_client)
        assert az._client is mock_client

    def test_init_without_client(self) -> None:
        az = DevOpsAnalyzer()
        assert az._client is None


# ---------------------------------------------------------------------------
# Tests: analyze_scan — DI parameter overrides
# ---------------------------------------------------------------------------


class TestAnalyzeScanDI:
    """Tests that the analysis_client DI parameter is honoured."""

    @pytest.mark.asyncio
    async def test_di_client_is_used_over_instance_client(self) -> None:
        """The analysis_client kwarg overrides self._client."""
        instance_client = _make_mock_client(raise_error="should not be called")
        di_client_calls: dict = {}
        di_client = _make_mock_client(capture_kwargs=di_client_calls)

        az = DevOpsAnalyzer(client=instance_client)
        await az.analyze_scan(
            org_name="AcmeCorp",
            scan_results=[_make_result()],
            category_scores=_make_category_scores(),
            overall_score=75.0,
            analysis_client=di_client,
        )
        # The DI client's analyze was called; instance client's was not.
        assert "prompt" in di_client_calls

    @pytest.mark.asyncio
    async def test_instance_client_used_when_di_is_none(self) -> None:
        """When analysis_client=None, self._client is used."""
        captured: dict = {}
        instance_client = _make_mock_client(capture_kwargs=captured)
        az = DevOpsAnalyzer(client=instance_client)
        await az.analyze_scan(
            org_name="AcmeCorp",
            scan_results=[_make_result()],
            category_scores=_make_category_scores(),
            overall_score=75.0,
        )
        assert "prompt" in captured


# ---------------------------------------------------------------------------
# Tests: analyze_scan — fallback on AnalysisClientError
# ---------------------------------------------------------------------------


class TestAnalyzeScanFallback:
    """Tests that a fallback AnalysisResult is returned on client failure."""

    @pytest.mark.asyncio
    async def test_fallback_returned_on_client_error(self) -> None:
        failing_client = _make_mock_client(raise_error="API down")
        az = DevOpsAnalyzer(client=failing_client)
        result = await az.analyze_scan(
            org_name="FailCorp",
            scan_results=[_make_result()],
            category_scores=_make_category_scores(),
            overall_score=50.0,
        )
        assert isinstance(result, AnalysisResult)
        # Fallback includes the org_name in the executive summary.
        assert "FailCorp" in result.executive_summary

    @pytest.mark.asyncio
    async def test_fallback_on_json_parse_failure(self) -> None:
        """If the AI returns non-JSON, fallback result is produced."""
        bad_json_client = _make_mock_client(response_text="This is not JSON at all.")
        az = DevOpsAnalyzer(client=bad_json_client)
        result = await az.analyze_scan(
            org_name="ParseCorp",
            scan_results=[_make_result()],
            category_scores=_make_category_scores(),
            overall_score=60.0,
        )
        assert isinstance(result, AnalysisResult)


# ---------------------------------------------------------------------------
# Tests: analyze_scan — structured output path
# ---------------------------------------------------------------------------


class TestAnalyzeScanStructuredOutput:
    """Tests for the structured output detection logic in analyze_scan."""

    @pytest.mark.asyncio
    async def test_json_schema_passed_when_provider_supports_structured_output(self) -> None:
        """When provider.supports_structured_output is True, json_schema= is
        forwarded to AnalysisClient.analyze()."""
        provider = FakeProviderWithStructuredOutput()
        client = AnalysisClient(provider=provider)
        az = DevOpsAnalyzer(client=client)

        await az.analyze_scan(
            org_name="StructCorp",
            scan_results=[_make_result()],
            category_scores=_make_category_scores(),
            overall_score=80.0,
        )

        # The provider should have received the json_schema dict.
        assert provider.last_json_schema is not None
        assert isinstance(provider.last_json_schema, dict)
        # Schema dict must include at least a "properties" key (JSON Schema shape).
        assert "properties" in provider.last_json_schema or "title" in provider.last_json_schema

    @pytest.mark.asyncio
    async def test_json_schema_not_passed_when_provider_lacks_structured_output(self) -> None:
        """When provider.supports_structured_output is False, json_schema=None
        is forwarded to chat(), meaning the schema was injected into the prompt."""
        provider = FakeProviderWithoutStructuredOutput()
        client = AnalysisClient(provider=provider)
        az = DevOpsAnalyzer(client=client)

        await az.analyze_scan(
            org_name="PlainCorp",
            scan_results=[_make_result()],
            category_scores=_make_category_scores(),
            overall_score=70.0,
        )

        # Provider's chat() receives json_schema=None because the analyzer
        # injected the schema into the prompt text instead.
        assert provider.last_json_schema is None

    @pytest.mark.asyncio
    async def test_prompt_contains_schema_when_no_native_support(self) -> None:
        """When the provider lacks native structured output, the prompt contains
        the JSON schema text."""
        captured: dict = {}

        class CapturingProvider:
            provider_id = "openai_compatible"
            supports_structured_output = False
            supports_tool_use = False

            async def chat(
                self, messages, tools=None, max_tokens=8192, temperature=0.0, json_schema=None
            ):
                captured["messages"] = messages
                captured["json_schema"] = json_schema
                return LLMResponse(text=_minimal_analysis_result_json(), finish_reason="stop")

            async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
                return
                yield  # pragma: no cover

        client = AnalysisClient(provider=CapturingProvider())
        az = DevOpsAnalyzer(client=client)
        await az.analyze_scan(
            org_name="NoCorp",
            scan_results=[_make_result()],
            category_scores=_make_category_scores(),
            overall_score=65.0,
        )

        # The user message should contain the JSON schema string.
        user_msg = captured["messages"][1].content
        assert "properties" in user_msg or "executive_summary" in user_msg
        # json_schema= passed to chat must be None.
        assert captured["json_schema"] is None

    @pytest.mark.asyncio
    async def test_prompt_contains_placeholder_when_native_support(self) -> None:
        """When the provider supports structured output, the prompt text contains
        only a short placeholder, not the full JSON schema."""
        captured: dict = {}

        class CapturingStructuredProvider:
            provider_id = "anthropic"
            supports_structured_output = True
            supports_tool_use = True

            async def chat(
                self, messages, tools=None, max_tokens=8192, temperature=0.0, json_schema=None
            ):
                captured["messages"] = messages
                captured["json_schema"] = json_schema
                return LLMResponse(text=_minimal_analysis_result_json(), finish_reason="stop")

            async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
                return
                yield  # pragma: no cover

        client = AnalysisClient(provider=CapturingStructuredProvider())
        az = DevOpsAnalyzer(client=client)
        await az.analyze_scan(
            org_name="StructCorp",
            scan_results=[_make_result()],
            category_scores=_make_category_scores(),
            overall_score=85.0,
        )

        user_msg = captured["messages"][1].content
        # Full JSON schema should NOT be embedded in the prompt.
        assert '"properties"' not in user_msg or "Schema provided natively" in user_msg
        # The native schema dict must have been forwarded.
        assert captured["json_schema"] is not None

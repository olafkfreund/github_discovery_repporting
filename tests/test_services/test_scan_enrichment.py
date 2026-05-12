from __future__ import annotations

"""Unit tests for scan_enrichment_service.

Tests use in-memory SQLite via the shared db_session fixture. The LLM
provider is always mocked so no real API calls are made.
"""

import json
import uuid
from json import dumps
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.llm.base import LLMProviderError, LLMResponse
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import AuthType, CheckStatus, Platform, ScanStatus, Severity
from backend.models.finding import Finding
from backend.models.llm import LLMConnection
from backend.models.scan import Scan
from backend.schemas.finding import FindingEnrichment
from backend.services import scan_enrichment_service as svc
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENRICHMENT_JSON = json.dumps(
    {
        "explanation": "This finding matters because secrets in plaintext are easily leaked.",
        "suggested_remediation_summary": "Move the secret to a vault and reference it via env.",
        "confidence": "high",
        "skill_versions": {},
    }
)


def _mock_response(
    text: str = _ENRICHMENT_JSON,
    input_tokens: int = 200,
    output_tokens: int = 100,
) -> LLMResponse:
    return LLMResponse(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=0.001,
    )


def _mock_provider(
    *, response: LLMResponse | None = None, raises: Exception | None = None
) -> MagicMock:
    """Build a mock LLMProvider whose chat() method returns *response* or raises *raises*."""
    provider = MagicMock()
    provider.supports_structured_output = False
    if raises is not None:
        provider.chat = AsyncMock(side_effect=raises)
    else:
        provider.chat = AsyncMock(return_value=response or _mock_response())
    return provider


async def _make_customer(db: AsyncSession, *, enrichment: bool = False) -> Customer:
    slug = f"cust-{uuid.uuid4().hex[:8]}"
    customer = Customer(name=slug, slug=slug, enable_scan_enrichment=enrichment)
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(db: AsyncSession, customer_id: uuid.UUID) -> PlatformConnection:
    conn = PlatformConnection(
        customer_id=customer_id,
        platform=Platform.github,
        display_name="Test",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(dumps({"token": "tok"})),
        org_or_group="test-org",
    )
    db.add(conn)
    await db.flush()
    return conn


async def _make_llm_connection(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    is_default: bool = True,
) -> LLMConnection:
    from backend.models.enums import LLMProviderEnum

    llm = LLMConnection(
        customer_id=customer_id,
        name=f"llm-{uuid.uuid4().hex[:6]}",
        provider=LLMProviderEnum.anthropic,
        model="claude-opus-4-6",
        is_default=is_default,
        api_key_encrypted=secrets_service.encrypt("sk-fake"),
    )
    db.add(llm)
    await db.flush()
    return llm


async def _make_scan(
    db: AsyncSession,
    customer_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> Scan:
    scan = Scan(
        customer_id=customer_id,
        connection_id=connection_id,
        status=ScanStatus.completed,
    )
    db.add(scan)
    await db.flush()
    return scan


async def _make_finding(
    db: AsyncSession,
    scan_id: uuid.UUID,
    *,
    check_id: str = "SEC-001",
    severity: Severity = Severity.high,
    status: CheckStatus = CheckStatus.failed,
) -> Finding:
    finding = Finding(
        scan_id=scan_id,
        category="secrets_mgmt",
        check_id=check_id,
        check_name=f"Check {check_id}",
        severity=severity,
        status=status,
        weight=1.0,
        score=0.0,
    )
    db.add(finding)
    await db.flush()
    return finding


def _make_resolved_skill(name: str = "test-skill") -> MagicMock:
    skill = MagicMock()
    skill.name = name
    skill.body = "# Skill\n\nThis skill explains how to fix it."
    skill.sha256 = "abc123"
    skill.source = "builtin"
    skill.applies_to = ["SEC-001"]
    return skill


# ---------------------------------------------------------------------------
# Test: gating off (enable_scan_enrichment=False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrichment_skipped_when_disabled(db_session: AsyncSession) -> None:
    """enrich_findings makes zero LLM calls when customer.enable_scan_enrichment=False."""
    customer = await _make_customer(db_session, enrichment=False)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    provider = _mock_provider()
    with patch.object(svc, "_build_provider", return_value=provider):
        await svc.enrich_findings(db_session, scan)

    provider.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Test: no LLM connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrichment_skipped_no_llm_connection(db_session: AsyncSession) -> None:
    """enrich_findings logs a warning and returns when no LLMConnection exists."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    provider = _mock_provider()
    with patch.object(svc, "_build_provider", return_value=provider):
        # No exception should be raised.
        await svc.enrich_findings(db_session, scan)

    provider.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Test: info findings are skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_info_findings_skipped(db_session: AsyncSession) -> None:
    """Info-severity findings are excluded from enrichment even if failing."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    info_finding = await _make_finding(
        db_session, scan.id, check_id="SEC-001", severity=Severity.info
    )
    # Also add a non-info failing finding that has no matching skill.
    await _make_finding(db_session, scan.id, check_id="SEC-002", severity=Severity.low)
    await _make_finding(db_session, scan.id, check_id="SEC-003", severity=Severity.high)

    provider = _mock_provider()

    with (
        patch.object(svc, "_build_provider", return_value=provider),
        patch(
            "backend.services.scan_enrichment_service.skill_service.resolve_for_scan",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        await svc.enrich_findings(db_session, scan)

    # The info finding must not have been enriched.
    assert info_finding.ai_enrichment is None
    # Provider never called because no skills matched.
    provider.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Test: findings with no matching skills are skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_findings_without_matching_skills_skipped(db_session: AsyncSession) -> None:
    """Failing findings whose check_id has no scan_enrichment skill stay unenriched."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    finding = await _make_finding(db_session, scan.id, check_id="REPO-042")

    provider = _mock_provider()
    # resolve_for_scan returns empty list for this check_id.
    with (
        patch.object(svc, "_build_provider", return_value=provider),
        patch(
            "backend.services.scan_enrichment_service.skill_service.resolve_for_scan",
            new_callable=AsyncMock,
            return_value={"REPO-042": []},
        ),
    ):
        await svc.enrich_findings(db_session, scan)

    provider.chat.assert_not_called()
    assert finding.ai_enrichment is None


# ---------------------------------------------------------------------------
# Test: happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_enriches_finding(db_session: AsyncSession) -> None:
    """A failing finding with a matching skill gets ai_enrichment populated."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    finding = await _make_finding(db_session, scan.id, check_id="SEC-001")
    skill = _make_resolved_skill("sec-skill")

    provider = _mock_provider(response=_mock_response())

    with (
        patch.object(svc, "_build_provider", return_value=provider),
        patch(
            "backend.services.scan_enrichment_service.skill_service.resolve_for_scan",
            new_callable=AsyncMock,
            return_value={"SEC-001": [skill]},
        ),
    ):
        await svc.enrich_findings(db_session, scan)

    provider.chat.assert_called_once()
    assert finding.ai_enrichment is not None
    enrichment = FindingEnrichment.model_validate(finding.ai_enrichment)
    assert enrichment.confidence == "high"
    assert "sec-skill" in enrichment.skill_versions


# ---------------------------------------------------------------------------
# Test: findings cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_findings_cap_limits_enrichment(db_session: AsyncSession) -> None:
    """At most SCAN_ENRICHMENT_MAX_FINDINGS findings are enriched per scan."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    check_ids = [f"SEC-{i:03d}" for i in range(20)]
    findings = [await _make_finding(db_session, scan.id, check_id=cid) for cid in check_ids]

    skill = _make_resolved_skill("cap-skill")
    skills_map = {cid: [skill] for cid in check_ids}

    provider = _mock_provider()

    cap = 5
    with (
        patch.object(svc, "_build_provider", return_value=provider),
        patch(
            "backend.services.scan_enrichment_service.skill_service.resolve_for_scan",
            new_callable=AsyncMock,
            return_value=skills_map,
        ),
        patch.object(svc.settings, "SCAN_ENRICHMENT_MAX_FINDINGS", cap),
    ):
        await svc.enrich_findings(db_session, scan)

    enriched = sum(1 for f in findings if f.ai_enrichment is not None)
    assert enriched == cap
    assert provider.chat.call_count == cap


# ---------------------------------------------------------------------------
# Test: tokens cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tokens_cap_stops_enrichment(db_session: AsyncSession) -> None:
    """Enrichment stops once cumulative token count exceeds SCAN_ENRICHMENT_MAX_TOKENS_PER_SCAN."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    check_ids = [f"IAM-{i:03d}" for i in range(10)]
    findings = [await _make_finding(db_session, scan.id, check_id=cid) for cid in check_ids]

    # Each call costs 4001 tokens; cap is 5000.
    # The cap check runs at the TOP of the loop (before processing):
    #   iteration 1: total=0 < 5000 → enrich, total becomes 4001
    #   iteration 2: total=4001 < 5000 → enrich, total becomes 8002
    #   iteration 3: total=8002 >= 5000 → stop
    # So exactly 2 findings are enriched.
    high_token_response = _mock_response(input_tokens=3000, output_tokens=1001)
    skill = _make_resolved_skill("tok-skill")
    skills_map = {cid: [skill] for cid in check_ids}

    provider = _mock_provider(response=high_token_response)

    with (
        patch.object(svc, "_build_provider", return_value=provider),
        patch(
            "backend.services.scan_enrichment_service.skill_service.resolve_for_scan",
            new_callable=AsyncMock,
            return_value=skills_map,
        ),
        patch.object(svc.settings, "SCAN_ENRICHMENT_MAX_TOKENS_PER_SCAN", 5000),
    ):
        await svc.enrich_findings(db_session, scan)

    enriched = sum(1 for f in findings if f.ai_enrichment is not None)
    assert enriched == 2
    # Remaining 8 findings must not have been enriched.
    assert provider.chat.call_count == 2


# ---------------------------------------------------------------------------
# Test: LLM failure on one finding doesn't abort others
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_failure_on_one_finding_continues(db_session: AsyncSession) -> None:
    """If LLM raises on the second finding, the first is enriched and the third is still attempted."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    # Create 3 findings with distinct check_ids so we can order them deterministically.
    f1 = await _make_finding(db_session, scan.id, check_id="AAA-001")
    f2 = await _make_finding(db_session, scan.id, check_id="BBB-002")
    f3 = await _make_finding(db_session, scan.id, check_id="CCC-003")

    skill = _make_resolved_skill("err-skill")
    skills_map = {
        "AAA-001": [skill],
        "BBB-002": [skill],
        "CCC-003": [skill],
    }

    # First call succeeds, second raises, third succeeds.
    provider = MagicMock()
    provider.supports_structured_output = False
    provider.chat = AsyncMock(
        side_effect=[
            _mock_response(),
            LLMProviderError("provider unavailable"),
            _mock_response(),
        ]
    )

    with (
        patch.object(svc, "_build_provider", return_value=provider),
        patch(
            "backend.services.scan_enrichment_service.skill_service.resolve_for_scan",
            new_callable=AsyncMock,
            return_value=skills_map,
        ),
    ):
        # Must not raise.
        await svc.enrich_findings(db_session, scan)

    assert f1.ai_enrichment is not None
    assert f2.ai_enrichment is None  # errored
    assert f3.ai_enrichment is not None


# ---------------------------------------------------------------------------
# Test: malformed JSON response is handled gracefully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_json_response_skips_finding(db_session: AsyncSession) -> None:
    """When the LLM returns non-JSON text, the finding is skipped without raising."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    finding = await _make_finding(db_session, scan.id, check_id="SEC-999")
    skill = _make_resolved_skill("bad-json-skill")

    bad_response = _mock_response(text="this is definitely not JSON { oops")
    provider = _mock_provider(response=bad_response)

    with (
        patch.object(svc, "_build_provider", return_value=provider),
        patch(
            "backend.services.scan_enrichment_service.skill_service.resolve_for_scan",
            new_callable=AsyncMock,
            return_value={"SEC-999": [skill]},
        ),
    ):
        # Must not raise.
        await svc.enrich_findings(db_session, scan)

    assert finding.ai_enrichment is None


# ---------------------------------------------------------------------------
# Test: markdown code-fence stripping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_parsed_correctly(db_session: AsyncSession) -> None:
    """JSON wrapped in ```json ... ``` fences is unwrapped before parsing."""
    customer = await _make_customer(db_session, enrichment=True)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    finding = await _make_finding(db_session, scan.id, check_id="CICD-010")
    skill = _make_resolved_skill("fence-skill")

    fenced_text = f"```json\n{_ENRICHMENT_JSON}\n```"
    provider = _mock_provider(response=_mock_response(text=fenced_text))

    with (
        patch.object(svc, "_build_provider", return_value=provider),
        patch(
            "backend.services.scan_enrichment_service.skill_service.resolve_for_scan",
            new_callable=AsyncMock,
            return_value={"CICD-010": [skill]},
        ),
    ):
        await svc.enrich_findings(db_session, scan)

    assert finding.ai_enrichment is not None
    enrichment = FindingEnrichment.model_validate(finding.ai_enrichment)
    assert enrichment.confidence == "high"


# ---------------------------------------------------------------------------
# Test: _format_skill_block_for_enrichment
# ---------------------------------------------------------------------------


def test_format_skill_block_no_skills() -> None:
    """Empty skill list returns the fallback placeholder string."""
    result = svc._format_skill_block_for_enrichment([], 6000)
    assert "(no skills configured" in result


def test_format_skill_block_under_budget() -> None:
    """Skills under budget are concatenated verbatim."""
    s1 = _make_resolved_skill("alpha")
    s1.body = "Alpha body."
    s2 = _make_resolved_skill("beta")
    s2.body = "Beta body."
    result = svc._format_skill_block_for_enrichment([s1, s2], 100_000)
    assert "### alpha" in result
    assert "Alpha body." in result
    assert "### beta" in result


def test_format_skill_block_truncates_over_budget() -> None:
    """Skills over budget are truncated with a [truncated] marker."""
    skill = _make_resolved_skill("big-skill")
    skill.body = "x" * 20_000
    result = svc._format_skill_block_for_enrichment([skill], 500)
    assert "[truncated]" in result


# ---------------------------------------------------------------------------
# Test: _pick_default_llm_connection fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pick_default_prefers_is_default_flag(db_session: AsyncSession) -> None:
    """_pick_default_llm_connection returns the connection with is_default=True."""
    customer = await _make_customer(db_session)
    await _make_llm_connection(db_session, customer.id, is_default=False)
    default = await _make_llm_connection(db_session, customer.id, is_default=True)

    result = await svc._pick_default_llm_connection(db_session, customer.id)
    assert result is not None
    assert result.id == default.id


@pytest.mark.asyncio
async def test_pick_default_falls_back_to_first(db_session: AsyncSession) -> None:
    """When no connection has is_default=True, the first row is returned."""
    customer = await _make_customer(db_session)
    await _make_llm_connection(db_session, customer.id, is_default=False)

    result = await svc._pick_default_llm_connection(db_session, customer.id)
    assert result is not None


@pytest.mark.asyncio
async def test_pick_default_returns_none_when_no_connections(db_session: AsyncSession) -> None:
    """Returns None when the customer has no LLM connections at all."""
    customer = await _make_customer(db_session)
    result = await svc._pick_default_llm_connection(db_session, customer.id)
    assert result is None

from __future__ import annotations

"""Post-scan LLM enrichment pass.

Consults active skills for failing findings; produces structured
FindingEnrichment data persisted to Finding.ai_enrichment.

Gated by Customer.enable_scan_enrichment (default False — opt-in).
Per-scan caps prevent runaway costs. Never raises into the scan
pipeline; on error logs and returns.
"""

import json as _json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.llm.base import LLMMessage, LLMProvider
from backend.llm.factory import get_llm_provider
from backend.models.customer import Customer
from backend.models.finding import Finding
from backend.models.llm import LLMConnection
from backend.models.scan import Scan
from backend.schemas.finding import FindingEnrichment
from backend.services import llm_connection_service, skill_service
from backend.services.skill_service import ResolvedSkill

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


_SKILL_BUDGET_FOR_ENRICHMENT = 6_000  # bytes; tighter than remediation budget


async def enrich_findings(
    session: AsyncSession,
    scan: Scan,
) -> None:
    """Run the enrichment pass for *scan*.

    Loads the Customer + default LLMConnection; iterates failing findings;
    makes one LLM call per finding with matching scan_enrichment skills;
    persists Finding.ai_enrichment. Caps enforced.

    Never raises. On any unrecoverable error, logs and returns early.

    Args:
        session: Active async database session.
        scan: The completed :class:`~backend.models.scan.Scan` to enrich.
    """
    customer = await session.get(Customer, scan.customer_id)
    if customer is None or not customer.enable_scan_enrichment:
        return

    llm_conn = await _pick_default_llm_connection(session, customer.id)
    if llm_conn is None:
        logger.warning(
            "scan_enrichment: customer %s has enrichment enabled but no LLMConnection; skipping.",
            customer.id,
        )
        return

    provider = _build_provider(llm_conn)

    # Load findings, filter to failing + non-info.
    findings = await _load_eligible_findings(session, scan.id)
    if not findings:
        return

    # Compute connection_id for skill resolution. Use scan.connection_id.
    skills_by_check = await skill_service.resolve_for_scan(
        session,
        scan.connection_id,
        {f.check_id for f in findings},
    )

    total_tokens = 0
    processed = 0
    for finding in findings:
        if processed >= settings.SCAN_ENRICHMENT_MAX_FINDINGS:
            logger.info("scan_enrichment: hit findings cap (%d) for scan %s", processed, scan.id)
            break
        if total_tokens >= settings.SCAN_ENRICHMENT_MAX_TOKENS_PER_SCAN:
            logger.info("scan_enrichment: hit tokens cap (%d) for scan %s", total_tokens, scan.id)
            break

        matching_skills = skills_by_check.get(finding.check_id, [])
        if not matching_skills:
            continue

        try:
            enrichment, tokens_used = await _enrich_one_finding(provider, finding, matching_skills)
        except Exception:  # noqa: BLE001
            logger.exception("scan_enrichment: failed for finding %s", finding.id)
            continue  # never fail the scan on enrichment errors

        finding.ai_enrichment = enrichment.model_dump()
        await session.flush()
        total_tokens += tokens_used
        processed += 1

    await session.commit()
    logger.info(
        "scan_enrichment: enriched %d findings (%d tokens) for scan %s",
        processed,
        total_tokens,
        scan.id,
    )


async def _pick_default_llm_connection(
    session: AsyncSession, customer_id: UUID
) -> LLMConnection | None:
    """Return the customer's default LLMConnection, or any if none flagged default.

    Args:
        session: Active async database session.
        customer_id: UUID of the owning customer.

    Returns:
        The preferred :class:`LLMConnection` or ``None`` if none exist.
    """
    stmt = select(LLMConnection).where(LLMConnection.customer_id == customer_id)
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return None
    for r in rows:
        if r.is_default:
            return r
    return rows[0]


def _build_provider(llm_conn: LLMConnection) -> LLMProvider:
    """Construct an :class:`LLMProvider` from an :class:`LLMConnection`.

    Args:
        llm_conn: Persisted LLM connection row with encrypted credentials.

    Returns:
        A concrete :class:`LLMProvider` instance ready for use.
    """
    config = llm_connection_service.to_provider_config(llm_conn)
    return get_llm_provider(config)


async def _load_eligible_findings(session: AsyncSession, scan_id: UUID) -> list[Finding]:
    """Load failing, non-info findings for *scan_id* ordered by severity then check_id.

    Args:
        session: Active async database session.
        scan_id: UUID of the scan whose findings to query.

    Returns:
        Ordered list of :class:`Finding` instances eligible for enrichment.
    """
    from backend.models.enums import CheckStatus, Severity  # noqa: PLC0415

    stmt = (
        select(Finding)
        .where(Finding.scan_id == scan_id)
        .where(Finding.status == CheckStatus.failed)
        .where(Finding.severity != Severity.info)
        .order_by(Finding.severity.desc(), Finding.check_id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _enrich_one_finding(
    provider: LLMProvider,
    finding: Finding,
    skills: list[ResolvedSkill],
) -> tuple[FindingEnrichment, int]:
    """Make one LLM call to enrich *finding* with guidance from *skills*.

    Builds a prompt from finding evidence + skill bodies. Uses the provider's
    structured-output path if supported; falls back to prompt-injected JSON
    Schema + manual parse otherwise.

    Args:
        provider: Concrete LLM provider to call.
        finding: The failing :class:`Finding` to enrich.
        skills: Resolved skills matching this finding's check_id.

    Returns:
        Tuple of (enrichment schema instance, tokens_used).

    Raises:
        Exception: Any LLM or parse error is allowed to bubble so the caller
            can log and continue.
    """
    skill_block = _format_skill_block_for_enrichment(skills, _SKILL_BUDGET_FOR_ENRICHMENT)
    system = (
        "You are a DevOps best-practices analyst. The user will give you a single "
        "failing finding from an automated scan along with relevant guidance from "
        "the team's skills library. Return a structured assessment.\n\n"
        f"## Skills\n\n{skill_block}"
    )
    user = (
        f"## Finding\n\n"
        f"check_id: {finding.check_id}\n"
        f"severity: {finding.severity}\n"
        f"detail: {finding.detail}\n"
        f"evidence: {finding.evidence}\n\n"
        "Return JSON with the FindingEnrichment shape (explanation, "
        "suggested_remediation_summary, confidence, skill_versions)."
    )
    messages = [
        LLMMessage(role="system", content=system),
        LLMMessage(role="user", content=user),
    ]

    if getattr(type(provider), "supports_structured_output", False):
        json_schema = FindingEnrichment.model_json_schema()
        response = await provider.chat(messages=messages, max_tokens=1500, json_schema=json_schema)
    else:
        # Append schema to the user prompt for providers without native JSON mode.
        messages[-1] = LLMMessage(
            role="user",
            content=user + "\n\nSchema:\n" + str(FindingEnrichment.model_json_schema()),
        )
        response = await provider.chat(messages=messages, max_tokens=1500)

    # Manual parse — handles both structured-output text and schema-injected fallback.
    text = response.text.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
        text = text.rsplit("```", 1)[0].strip()
    parsed: dict = _json.loads(text)

    # Fill skill_versions from resolved skills as ground truth.
    # Built-in skills are always v1; custom skills carry their DB version.
    parsed["skill_versions"] = {s.name: 1 for s in skills}

    enrichment = FindingEnrichment.model_validate(parsed)
    return enrichment, response.input_tokens + response.output_tokens


def _format_skill_block_for_enrichment(skills: list[ResolvedSkill], budget_bytes: int) -> str:
    """Concatenate skill bodies with longest-first truncation.

    Mirrors the agent runner helper pattern: fits all skills within *budget_bytes*
    by proportional truncation when the total would exceed the limit.

    Args:
        skills: Resolved skills to format.
        budget_bytes: Maximum byte budget for the combined output.

    Returns:
        A formatted markdown string of skill bodies.
    """
    if not skills:
        return "(no skills configured for this finding)"
    entries = [(s.name, s.body) for s in skills]
    total = sum(len(name.encode()) + len(body.encode()) + 8 for name, body in entries)
    if total <= budget_bytes:
        return "\n\n".join(f"### {name}\n{body}" for name, body in entries)
    n = len(entries)
    per = max(budget_bytes // n - 64, 256)
    out = []
    for name, body in sorted(entries, key=lambda e: len(e[1]), reverse=True):
        if len(body) > per:
            body = body[:per] + "\n\n[truncated]"
        out.append((name, body))
    out.sort(key=lambda e: e[0])
    return "\n\n".join(f"### {name}\n{body}" for name, body in out)

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from backend.models.enums import Category, CheckStatus, Severity
from backend.schemas.platform_data import OrgAssessmentData, RepoAssessmentData


@dataclass
class ScanCheck:
    """Metadata that describes a single discrete check within a scanner."""

    check_id: str
    check_name: str
    category: Category
    severity: Severity
    weight: float = 1.0
    description: str = ""


@dataclass
class CheckResult:
    """The outcome of evaluating one :class:`ScanCheck` against repository data.

    Score is computed automatically from the check weight and the resulting
    status:

    * ``passed``  → ``weight * 1.0``
    * ``warning`` → ``weight * 0.5``
    * all others  → ``0.0``
    """

    check: ScanCheck
    status: CheckStatus
    detail: str = ""
    evidence: dict[str, Any] | None = None
    score: float = field(init=False)

    def __post_init__(self) -> None:
        if self.status is CheckStatus.passed:
            self.score = self.check.weight * 1.0
        elif self.status is CheckStatus.warning:
            self.score = self.check.weight * 0.5
        else:
            self.score = 0.0


class Scanner(Protocol):
    """Structural protocol that every repo-level scanner must satisfy."""

    category: Category
    weight: float  # category-level weight used by the orchestrator

    def checks(self) -> list[ScanCheck]:
        """Return the full list of :class:`ScanCheck` objects this scanner owns."""
        ...

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Evaluate all checks against *data* and return a result for each."""
        ...


class OrgScanner(Protocol):
    """Structural protocol for org-level scanners."""

    category: Category
    weight: float

    def checks(self) -> list[ScanCheck]:
        """Return the full list of :class:`ScanCheck` objects this scanner owns."""
        ...

    def evaluate_org(self, data: OrgAssessmentData) -> list[CheckResult]:
        """Evaluate all checks against org-level *data*."""
        ...


class BaseScanner:
    """Concrete base class providing shared helpers for all scanner implementations.

    Subclasses must define ``_CHECKS`` as a class-level tuple of
    :class:`ScanCheck` instances.  The ``checks()``, ``_check_map``,
    ``_bool_check()``, and ``_manual_review()`` helpers are then available
    to every evaluate / evaluate_org implementation without duplication.
    """

    _CHECKS: ClassVar[tuple[ScanCheck, ...]] = ()

    def checks(self) -> list[ScanCheck]:
        """Return the full list of :class:`ScanCheck` objects this scanner owns."""
        return list(self._CHECKS)

    @functools.cached_property
    def _check_map(self) -> dict[str, ScanCheck]:
        """Build and cache a ``{check_id: ScanCheck}`` lookup for fast access."""
        return {c.check_id: c for c in self._CHECKS}

    def _bool_check(
        self,
        check_id: str,
        condition: bool,
        *,
        passed: str,
        failed: str,
        evidence: dict[str, Any] | None = None,
    ) -> CheckResult:
        """Return a :class:`CheckResult` whose status depends on *condition*.

        Args:
            check_id: Identifier of the :class:`ScanCheck` to evaluate.
            condition: When ``True`` the result is ``passed``; otherwise ``failed``.
            passed: Detail message used when *condition* is ``True``.
            failed: Detail message used when *condition* is ``False``.
            evidence: Optional evidence dict attached to the result.

        Returns:
            A :class:`CheckResult` with the appropriate status and detail.
        """
        check = self._check_map[check_id]
        status = CheckStatus.passed if condition else CheckStatus.failed
        detail = passed if condition else failed
        return CheckResult(check=check, status=status, detail=detail, evidence=evidence if condition else None)

    def _manual_review(self, check_id: str, subject: str) -> CheckResult:
        """Return a ``warning`` :class:`CheckResult` recommending manual review.

        Args:
            check_id: Identifier of the :class:`ScanCheck` to evaluate.
            subject: Short description of what could not be verified automatically.

        Returns:
            A :class:`CheckResult` with ``warning`` status and a standard detail
            message in the form ``"{subject} could not be verified automatically.
            Manual review recommended."``.
        """
        check = self._check_map[check_id]
        detail = f"{subject} could not be verified automatically. Manual review recommended."
        return CheckResult(check=check, status=CheckStatus.warning, detail=detail)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

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
    evidence: dict | None = None
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

from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import PullRequestInfo, RepoAssessmentData


class CollaborationScanner:
    """Evaluates repository practices that support healthy team collaboration.

    Category weight: 0.04 (simplified for 16-domain architecture; many checks
    moved to repo_governance and sdlc_process scanners).
    """

    category: Category = Category.collaboration
    weight: float = 0.04

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="COLLAB-001",
            check_name="Issue templates configured",
            category=Category.collaboration,
            severity=Severity.low,
            weight=0.5,
            description="Issue templates should be configured to guide contributors.",
        ),
        ScanCheck(
            check_id="COLLAB-002",
            check_name="Discussion board enabled",
            category=Category.collaboration,
            severity=Severity.low,
            weight=0.5,
            description="GitHub Discussions or equivalent should be enabled for community engagement.",
        ),
        ScanCheck(
            check_id="COLLAB-003",
            check_name="Team notifications configured",
            category=Category.collaboration,
            severity=Severity.low,
            weight=0.5,
            description="Team notification settings should be configured for timely communication.",
        ),
        ScanCheck(
            check_id="COLLAB-004",
            check_name="Project boards used",
            category=Category.collaboration,
            severity=Severity.low,
            weight=0.5,
            description="Project boards should be used for work tracking and visibility.",
        ),
        ScanCheck(
            check_id="COLLAB-005",
            check_name="Wiki or documentation site",
            category=Category.collaboration,
            severity=Severity.low,
            weight=0.5,
            description="A wiki or documentation site should be available for knowledge sharing.",
        ),
        ScanCheck(
            check_id="COLLAB-006",
            check_name="Response time to PRs < 24h",
            category=Category.collaboration,
            severity=Severity.medium,
            weight=1.0,
            description="Pull requests should receive initial review within 24 hours.",
        ),
        ScanCheck(
            check_id="COLLAB-007",
            check_name="Stale issue/PR management",
            category=Category.collaboration,
            severity=Severity.low,
            weight=0.5,
            description="A process for managing stale issues and PRs should be in place.",
        ),
    ]

    def checks(self) -> list[ScanCheck]:
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        check_map = {c.check_id: c for c in self._CHECKS}
        results: list[CheckResult] = []

        # COLLAB-001
        check = check_map["COLLAB-001"]
        if data.has_issue_templates:
            results.append(
                CheckResult(
                    check=check, status=CheckStatus.passed, detail="Issue templates are configured."
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check, status=CheckStatus.failed, detail="No issue templates found."
                )
            )

        # COLLAB-002
        check = check_map["COLLAB-002"]
        if data.has_discussions_enabled:
            results.append(
                CheckResult(
                    check=check, status=CheckStatus.passed, detail="Discussion board is enabled."
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail="Discussion board status could not be verified. Manual review recommended.",
                )
            )

        # COLLAB-003
        check = check_map["COLLAB-003"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail="Team notification configuration could not be verified automatically. Manual review recommended.",
            )
        )

        # COLLAB-004
        check = check_map["COLLAB-004"]
        if data.has_project_boards:
            results.append(
                CheckResult(
                    check=check, status=CheckStatus.passed, detail="Project boards are in use."
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail="Project board usage could not be verified. Manual review recommended.",
                )
            )

        # COLLAB-005
        check = check_map["COLLAB-005"]
        if data.has_wiki:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="Wiki or documentation site is available.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail="Wiki availability could not be verified. Manual review recommended.",
                )
            )

        # COLLAB-006 (PR response time — cannot fully verify, use proxy)
        check = check_map["COLLAB-006"]
        recent_prs: list[PullRequestInfo] = data.recent_prs
        merged_prs = [pr for pr in recent_prs if pr.merged]
        if not merged_prs:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No recently merged pull requests available for analysis.",
                )
            )
        else:
            reviewed_count = sum(1 for pr in merged_prs if pr.review_count >= 1)
            coverage = reviewed_count / len(merged_prs)
            coverage_pct = round(coverage * 100, 1)
            evidence = {
                "merged_pr_count": len(merged_prs),
                "reviewed_pr_count": reviewed_count,
                "review_coverage_pct": coverage_pct,
            }
            if coverage > 0.90:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.passed,
                        detail=f"{coverage_pct}% of merged PRs received timely reviews.",
                        evidence=evidence,
                    )
                )
            elif coverage > 0.75:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.warning,
                        detail=f"{coverage_pct}% of merged PRs received reviews (threshold: >90%).",
                        evidence=evidence,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"Only {coverage_pct}% of merged PRs received reviews.",
                        evidence=evidence,
                    )
                )

        # COLLAB-007
        check = check_map["COLLAB-007"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail="Stale issue/PR management could not be verified automatically. Manual review recommended.",
            )
        )

        return results

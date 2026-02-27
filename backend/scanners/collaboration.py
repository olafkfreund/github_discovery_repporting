from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import PullRequestInfo, RepoAssessmentData


class CollaborationScanner:
    """Evaluates repository practices that support healthy team collaboration.

    Category weight: 0.10.
    """

    category: Category = Category.collaboration
    weight: float = 0.10

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="COLLAB-001",
            check_name="CODEOWNERS file present",
            category=Category.collaboration,
            severity=Severity.medium,
            weight=1.0,
            description="A CODEOWNERS file must define ownership for code areas to auto-assign reviewers.",
        ),
        ScanCheck(
            check_id="COLLAB-002",
            check_name="PR template exists",
            category=Category.collaboration,
            severity=Severity.low,
            weight=0.5,
            description="A pull-request template must guide contributors toward complete PR descriptions.",
        ),
        ScanCheck(
            check_id="COLLAB-003",
            check_name="Contributing guide exists",
            category=Category.collaboration,
            severity=Severity.low,
            weight=0.5,
            description="A CONTRIBUTING guide must document how external and internal contributors should work.",
        ),
        ScanCheck(
            check_id="COLLAB-004",
            check_name="PRs have reviews",
            category=Category.collaboration,
            severity=Severity.high,
            weight=1.5,
            description="More than 75% of recently merged pull requests must have received at least one review.",
        ),
        ScanCheck(
            check_id="COLLAB-005",
            check_name="Average PR size <500 lines",
            category=Category.collaboration,
            severity=Severity.medium,
            weight=1.0,
            description="The average pull-request size (additions + deletions) must be below 500 lines.",
        ),
    ]

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def checks(self) -> list[ScanCheck]:
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        check_map = {c.check_id: c for c in self._CHECKS}
        results: list[CheckResult] = []

        # COLLAB-001
        check = check_map["COLLAB-001"]
        if data.has_codeowners:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="A CODEOWNERS file is present."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No CODEOWNERS file was found."))

        # COLLAB-002
        check = check_map["COLLAB-002"]
        if data.has_pr_template:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="A pull-request template is present."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No pull-request template was found."))

        # COLLAB-003
        check = check_map["COLLAB-003"]
        if data.has_contributing_guide:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="A contributing guide is present."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No contributing guide was found."))

        # COLLAB-004  (review coverage on merged PRs)
        check = check_map["COLLAB-004"]
        recent_prs: list[PullRequestInfo] = data.recent_prs
        merged_prs = [pr for pr in recent_prs if pr.merged]
        if not merged_prs:
            results.append(CheckResult(check=check, status=CheckStatus.not_applicable, detail="No recently merged pull requests available for analysis."))
        else:
            reviewed_count = sum(1 for pr in merged_prs if pr.review_count >= 1)
            coverage = reviewed_count / len(merged_prs)
            coverage_pct = round(coverage * 100, 1)
            evidence = {
                "merged_pr_count": len(merged_prs),
                "reviewed_pr_count": reviewed_count,
                "review_coverage_pct": coverage_pct,
            }
            if coverage > 0.75:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.passed,
                        detail=f"{coverage_pct}% of merged PRs received at least one review.",
                        evidence=evidence,
                    )
                )
            elif coverage > 0.50:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.warning,
                        detail=f"Only {coverage_pct}% of merged PRs were reviewed (threshold: >75%).",
                        evidence=evidence,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"Only {coverage_pct}% of merged PRs were reviewed (below 50%).",
                        evidence=evidence,
                    )
                )

        # COLLAB-005  (average PR size)
        check = check_map["COLLAB-005"]
        if not recent_prs:
            results.append(CheckResult(check=check, status=CheckStatus.not_applicable, detail="No recent pull requests available for size analysis."))
        else:
            avg_size = sum(pr.additions + pr.deletions for pr in recent_prs) / len(recent_prs)
            avg_size_rounded = round(avg_size, 1)
            evidence = {
                "pr_count": len(recent_prs),
                "average_changed_lines": avg_size_rounded,
            }
            if avg_size < 500:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.passed,
                        detail=f"Average PR size is {avg_size_rounded} lines (threshold: <500).",
                        evidence=evidence,
                    )
                )
            elif avg_size < 1000:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.warning,
                        detail=f"Average PR size is {avg_size_rounded} lines (above 500-line threshold).",
                        evidence=evidence,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"Average PR size is {avg_size_rounded} lines, exceeding 1000 lines.",
                        evidence=evidence,
                    )
                )

        return results

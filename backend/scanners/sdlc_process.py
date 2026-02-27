from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import PullRequestInfo, RepoAssessmentData


class SDLCProcessScanner:
    """Evaluates Software Development Lifecycle (SDLC) process maturity.

    Category weight: 0.06.
    """

    category: Category = Category.sdlc_process
    weight: float = 0.06

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="SDLC-001",
            check_name="PR template exists",
            category=Category.sdlc_process,
            severity=Severity.low,
            weight=0.5,
            description="A pull-request template must guide contributors toward complete PR descriptions.",
        ),
        ScanCheck(
            check_id="SDLC-002",
            check_name="Contributing guide exists",
            category=Category.sdlc_process,
            severity=Severity.low,
            weight=0.5,
            description="A CONTRIBUTING guide must document how contributors should participate in the project.",
        ),
        ScanCheck(
            check_id="SDLC-003",
            check_name="PRs have reviews before merge",
            category=Category.sdlc_process,
            severity=Severity.high,
            weight=1.5,
            description="More than 75% of recently merged pull requests must have received at least one review.",
        ),
        ScanCheck(
            check_id="SDLC-004",
            check_name="Average PR size less than 500 lines",
            category=Category.sdlc_process,
            severity=Severity.medium,
            weight=1.0,
            description="The average pull-request size (additions + deletions) should be below 500 lines.",
        ),
        ScanCheck(
            check_id="SDLC-005",
            check_name="Branching strategy documented",
            category=Category.sdlc_process,
            severity=Severity.low,
            weight=0.5,
            description="The repository branching strategy (e.g. GitFlow, trunk-based) must be documented.",
        ),
        ScanCheck(
            check_id="SDLC-006",
            check_name="Release process defined",
            category=Category.sdlc_process,
            severity=Severity.medium,
            weight=1.0,
            description="A documented release process must exist to ensure consistent and repeatable deployments.",
        ),
        ScanCheck(
            check_id="SDLC-007",
            check_name="Semantic versioning used",
            category=Category.sdlc_process,
            severity=Severity.low,
            weight=0.5,
            description="Releases must follow semantic versioning (MAJOR.MINOR.PATCH) to communicate change impact.",
        ),
        ScanCheck(
            check_id="SDLC-008",
            check_name="Feature flags framework present",
            category=Category.sdlc_process,
            severity=Severity.low,
            weight=0.5,
            description="A feature flag framework must be available to decouple deployment from feature release.",
        ),
        ScanCheck(
            check_id="SDLC-009",
            check_name="Hotfix process documented",
            category=Category.sdlc_process,
            severity=Severity.medium,
            weight=1.0,
            description="A documented hotfix process must exist for expedited patching of production issues.",
        ),
        ScanCheck(
            check_id="SDLC-010",
            check_name="Definition of done documented",
            category=Category.sdlc_process,
            severity=Severity.low,
            weight=0.5,
            description="A definition of done must be documented to align the team on completion criteria.",
        ),
        ScanCheck(
            check_id="SDLC-011",
            check_name="Architecture Decision Records present",
            category=Category.sdlc_process,
            severity=Severity.medium,
            weight=1.0,
            description="An ADR directory must exist to record significant architectural decisions and their rationale.",
        ),
        ScanCheck(
            check_id="SDLC-012",
            check_name="API documentation maintained",
            category=Category.sdlc_process,
            severity=Severity.medium,
            weight=1.0,
            description="Up-to-date API documentation (e.g. OpenAPI spec, generated docs) must be present.",
        ),
    ]

    def checks(self) -> list[ScanCheck]:
        """Return the full catalogue of SDLC process checks."""
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every SDLC-xxx check against *data* and return one result each."""
        check_map = {c.check_id: c for c in self._CHECKS}
        results: list[CheckResult] = []

        # SDLC-001: PR template exists
        check = check_map["SDLC-001"]
        if data.has_pr_template:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A pull-request template is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No pull-request template was found.",
                )
            )

        # SDLC-002: Contributing guide exists
        check = check_map["SDLC-002"]
        if data.has_contributing_guide:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A contributing guide is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No contributing guide was found.",
                )
            )

        # SDLC-003: PRs have reviews before merge (review coverage on merged PRs)
        check = check_map["SDLC-003"]
        recent_prs: list[PullRequestInfo] = data.recent_prs
        merged_prs = [pr for pr in recent_prs if pr.merged]
        if not merged_prs:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No recently merged pull requests available for review coverage analysis.",
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

        # SDLC-004: Average PR size less than 500 lines
        check = check_map["SDLC-004"]
        if not recent_prs:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No recent pull requests available for size analysis.",
                )
            )
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

        # SDLC-005: Branching strategy documented
        check = check_map["SDLC-005"]
        if data.has_branching_strategy_doc:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A branching strategy document is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No branching strategy documentation was found.",
                )
            )

        # SDLC-006: Release process defined
        check = check_map["SDLC-006"]
        if data.has_release_process_doc:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A release process document is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No release process documentation was found.",
                )
            )

        # SDLC-007: Semantic versioning used (cannot verify directly via API)
        check = check_map["SDLC-007"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Semantic versioning adoption could not be verified automatically. "
                    "Confirm that release tags follow the MAJOR.MINOR.PATCH format."
                ),
            )
        )

        # SDLC-008: Feature flags framework present
        check = check_map["SDLC-008"]
        if data.has_feature_flags:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A feature flags framework or configuration is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No feature flags framework was detected in the repository.",
                )
            )

        # SDLC-009: Hotfix process documented
        check = check_map["SDLC-009"]
        if data.has_hotfix_process_doc:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A hotfix process document is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No hotfix process documentation was found.",
                )
            )

        # SDLC-010: Definition of done documented
        check = check_map["SDLC-010"]
        if data.has_definition_of_done:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A definition of done document is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No definition of done documentation was found.",
                )
            )

        # SDLC-011: Architecture Decision Records present
        check = check_map["SDLC-011"]
        if data.has_adr_directory:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="An Architecture Decision Records (ADR) directory is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No ADR directory was detected. Consider adopting ADRs to document architectural decisions.",
                )
            )

        # SDLC-012: API documentation maintained
        check = check_map["SDLC-012"]
        if data.has_api_docs:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="API documentation is present in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No API documentation was detected (e.g. OpenAPI spec, generated docs).",
                )
            )

        return results

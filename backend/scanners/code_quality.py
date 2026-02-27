from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import CIWorkflow, RepoAssessmentData


class CodeQualityScanner:
    """Evaluates static-quality tooling and test-framework configuration.

    Category weight: 0.06 (adjusted for 16-domain architecture).
    """

    category: Category = Category.code_quality
    weight: float = 0.06

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="CQ-001",
            check_name="Linter configuration present",
            category=Category.code_quality,
            severity=Severity.medium,
            weight=1.0,
            description="A linter must be configured and executed in the CI pipeline.",
        ),
        ScanCheck(
            check_id="CQ-002",
            check_name="Test framework configured",
            category=Category.code_quality,
            severity=Severity.high,
            weight=1.5,
            description="A test framework must be configured and executed in the CI pipeline.",
        ),
        ScanCheck(
            check_id="CQ-003",
            check_name="Code coverage tool present",
            category=Category.code_quality,
            severity=Severity.medium,
            weight=1.0,
            description="A code-coverage measurement tool should be configured and reporting results.",
        ),
        ScanCheck(
            check_id="CQ-004",
            check_name="Code coverage > 60%",
            category=Category.code_quality,
            severity=Severity.medium,
            weight=1.0,
            description="Code coverage should exceed 60% to ensure adequate test coverage.",
        ),
        ScanCheck(
            check_id="CQ-005",
            check_name="README exists and non-empty",
            category=Category.code_quality,
            severity=Severity.low,
            weight=0.5,
            description="The repository must contain a README file with meaningful content.",
        ),
        ScanCheck(
            check_id="CQ-006",
            check_name="EditorConfig/Prettier consistent",
            category=Category.code_quality,
            severity=Severity.low,
            weight=0.5,
            description="An EditorConfig or Prettier configuration should enforce consistent formatting.",
        ),
        ScanCheck(
            check_id="CQ-007",
            check_name="Type checking configured",
            category=Category.code_quality,
            severity=Severity.medium,
            weight=1.0,
            description="A type-checking tool (mypy, pyright, tsc) should be configured.",
        ),
        ScanCheck(
            check_id="CQ-008",
            check_name="Code complexity below threshold",
            category=Category.code_quality,
            severity=Severity.medium,
            weight=1.0,
            description="Code complexity should be measured and kept below acceptable thresholds.",
        ),
        ScanCheck(
            check_id="CQ-009",
            check_name="Technical debt tracking",
            category=Category.code_quality,
            severity=Severity.low,
            weight=0.5,
            description="Technical debt should be tracked and managed systematically.",
        ),
    ]

    def checks(self) -> list[ScanCheck]:
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        workflows: list[CIWorkflow] = data.ci_workflows
        check_map = {c.check_id: c for c in self._CHECKS}
        results: list[CheckResult] = []

        # CQ-001 (linter presence proxied through CI workflow flag)
        check = check_map["CQ-001"]
        lint_workflows = [w for w in workflows if w.has_lint]
        if lint_workflows:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail=f"{len(lint_workflows)} workflow(s) include a lint step.",
                    evidence={"lint_workflow_names": [w.name for w in lint_workflows]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No workflow includes a linting step.",
                )
            )

        # CQ-002 (test framework proxied through CI workflow flag)
        check = check_map["CQ-002"]
        test_workflows = [w for w in workflows if w.has_tests]
        if test_workflows:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail=f"{len(test_workflows)} workflow(s) include a test-execution step.",
                    evidence={"test_workflow_names": [w.name for w in test_workflows]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No workflow includes a test-execution step.",
                )
            )

        # CQ-003 (coverage tooling)
        check = check_map["CQ-003"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail="Code-coverage tooling presence could not be verified automatically. Manual review recommended.",
            )
        )

        # CQ-004 (code coverage > 60%)
        check = check_map["CQ-004"]
        if data.test_coverage_percent is not None:
            if data.test_coverage_percent >= 60.0:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.passed,
                        detail=f"Code coverage is {data.test_coverage_percent:.1f}% (threshold: 60%).",
                        evidence={"coverage_percent": data.test_coverage_percent},
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"Code coverage is {data.test_coverage_percent:.1f}% (below 60% threshold).",
                        evidence={"coverage_percent": data.test_coverage_percent},
                    )
                )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="Code coverage data not available.",
                )
            )

        # CQ-005
        check = check_map["CQ-005"]
        if data.has_readme:
            results.append(
                CheckResult(
                    check=check, status=CheckStatus.passed, detail="A README file is present."
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No README file was found in the repository.",
                )
            )

        # CQ-006 (EditorConfig/Prettier)
        check = check_map["CQ-006"]
        if data.has_editorconfig:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="EditorConfig or formatter configuration is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No EditorConfig or formatter configuration found.",
                )
            )

        # CQ-007 (type checking)
        check = check_map["CQ-007"]
        if data.has_type_checking:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="Type-checking configuration is present.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No type-checking configuration found.",
                )
            )

        # CQ-008 (code complexity)
        check = check_map["CQ-008"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail="Code complexity measurement could not be verified automatically. Manual review recommended.",
            )
        )

        # CQ-009 (technical debt tracking)
        check = check_map["CQ-009"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail="Technical debt tracking could not be verified automatically. Manual review recommended.",
            )
        )

        return results

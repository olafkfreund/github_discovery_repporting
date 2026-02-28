from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import CIWorkflow, RepoAssessmentData


class CodeQualityScanner(BaseScanner):
    """Evaluates static-quality tooling and test-framework configuration.

    Category weight: 0.06 (adjusted for 16-domain architecture).
    """

    category: Category = Category.code_quality
    weight: float = 0.06

    _CHECKS = (
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
    )

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        workflows: list[CIWorkflow] = data.ci_workflows
        results: list[CheckResult] = []

        # CQ-001 (linter presence proxied through CI workflow flag)
        lint_workflows = [w for w in workflows if w.has_lint]
        results.append(
            self._bool_check(
                "CQ-001",
                bool(lint_workflows),
                passed=f"{len(lint_workflows)} workflow(s) include a lint step.",
                failed="No workflow includes a linting step.",
                evidence={"lint_workflow_names": [w.name for w in lint_workflows]} if lint_workflows else None,
            )
        )

        # CQ-002 (test framework proxied through CI workflow flag)
        test_workflows = [w for w in workflows if w.has_tests]
        results.append(
            self._bool_check(
                "CQ-002",
                bool(test_workflows),
                passed=f"{len(test_workflows)} workflow(s) include a test-execution step.",
                failed="No workflow includes a test-execution step.",
                evidence={"test_workflow_names": [w.name for w in test_workflows]} if test_workflows else None,
            )
        )

        # CQ-003 (coverage tooling)
        results.append(self._manual_review("CQ-003", "Code-coverage tooling presence"))

        # CQ-004 (code coverage > 60%)
        if data.test_coverage_percent is not None:
            if data.test_coverage_percent >= 60.0:
                results.append(
                    CheckResult(
                        check=self._check_map["CQ-004"],
                        status=CheckStatus.passed,
                        detail=f"Code coverage is {data.test_coverage_percent:.1f}% (threshold: 60%).",
                        evidence={"coverage_percent": data.test_coverage_percent},
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=self._check_map["CQ-004"],
                        status=CheckStatus.failed,
                        detail=f"Code coverage is {data.test_coverage_percent:.1f}% (below 60% threshold).",
                        evidence={"coverage_percent": data.test_coverage_percent},
                    )
                )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["CQ-004"],
                    status=CheckStatus.not_applicable,
                    detail="Code coverage data not available.",
                )
            )

        # CQ-005
        results.append(
            self._bool_check(
                "CQ-005",
                data.has_readme,
                passed="A README file is present.",
                failed="No README file was found in the repository.",
            )
        )

        # CQ-006 (EditorConfig/Prettier)
        results.append(
            self._bool_check(
                "CQ-006",
                data.has_editorconfig,
                passed="EditorConfig or formatter configuration is present.",
                failed="No EditorConfig or formatter configuration found.",
            )
        )

        # CQ-007 (type checking)
        results.append(
            self._bool_check(
                "CQ-007",
                data.has_type_checking,
                passed="Type-checking configuration is present.",
                failed="No type-checking configuration found.",
            )
        )

        # CQ-008 (code complexity)
        results.append(self._manual_review("CQ-008", "Code complexity measurement"))

        # CQ-009 (technical debt tracking)
        results.append(self._manual_review("CQ-009", "Technical debt tracking"))

        return results

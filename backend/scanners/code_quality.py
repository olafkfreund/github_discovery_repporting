from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import CIWorkflow, RepoAssessmentData


class CodeQualityScanner:
    """Evaluates static-quality tooling and test-framework configuration.

    Category weight: 0.20.
    """

    category: Category = Category.code_quality
    weight: float = 0.20

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
            check_name="Static analysis in pipeline",
            category=Category.code_quality,
            severity=Severity.medium,
            weight=1.0,
            description="At least one static-analysis tool (SAST or linter) must run in the pipeline.",
        ),
        ScanCheck(
            check_id="CQ-005",
            check_name="README exists and non-empty",
            category=Category.code_quality,
            severity=Severity.low,
            weight=0.5,
            description="The repository must contain a README file with meaningful content.",
        ),
    ]

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def checks(self) -> list[ScanCheck]:
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        workflows: list[CIWorkflow] = data.ci_workflows
        check_map = {c.check_id: c for c in self._CHECKS}
        results: list[CheckResult] = []

        # CQ-001  (linter presence proxied through CI workflow flag)
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
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No workflow includes a linting step."))

        # CQ-002  (test framework proxied through CI workflow flag)
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
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No workflow includes a test-execution step."))

        # CQ-003  (coverage tooling — always warning, not reliably detectable via API)
        check = check_map["CQ-003"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Code-coverage tooling presence could not be verified automatically. "
                    "Manual review recommended."
                ),
            )
        )

        # CQ-004  (static analysis: security scan or lint in any workflow)
        check = check_map["CQ-004"]
        analysis_workflows = [w for w in workflows if w.has_security_scan or w.has_lint]
        if analysis_workflows:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail=f"{len(analysis_workflows)} workflow(s) include static-analysis steps.",
                    evidence={"analysis_workflow_names": [w.name for w in analysis_workflows]},
                )
            )
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No workflow includes a static-analysis step (SAST or linter)."))

        # CQ-005
        check = check_map["CQ-005"]
        if data.has_readme:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="A README file is present."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No README file was found in the repository."))

        return results

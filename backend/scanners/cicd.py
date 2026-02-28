from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import CIWorkflow, RepoAssessmentData, WorkflowRun


class CICDScanner(BaseScanner):
    """Evaluates the maturity of the repository's CI/CD pipeline configuration.

    Category weight: 0.10 (expanded from 0.20 in the 16-domain architecture).
    """

    category: Category = Category.cicd
    weight: float = 0.10

    _CHECKS = (
        ScanCheck(
            check_id="CICD-001",
            check_name="CI pipeline exists",
            category=Category.cicd,
            severity=Severity.critical,
            weight=2.0,
            description="At least one CI/CD workflow definition must be present in the repository.",
        ),
        ScanCheck(
            check_id="CICD-002",
            check_name="Pipeline runs on PRs",
            category=Category.cicd,
            severity=Severity.high,
            weight=1.5,
            description="At least one workflow must be triggered on pull-request events.",
        ),
        ScanCheck(
            check_id="CICD-003",
            check_name="Pipeline includes tests",
            category=Category.cicd,
            severity=Severity.high,
            weight=1.5,
            description="At least one workflow must execute a test suite.",
        ),
        ScanCheck(
            check_id="CICD-004",
            check_name="Pipeline includes linting",
            category=Category.cicd,
            severity=Severity.medium,
            weight=1.0,
            description="At least one workflow must run a linter or static-format check.",
        ),
        ScanCheck(
            check_id="CICD-005",
            check_name="Pipeline includes security scanning",
            category=Category.cicd,
            severity=Severity.high,
            weight=1.5,
            description="At least one workflow must include a security or SAST scanning step.",
        ),
        ScanCheck(
            check_id="CICD-006",
            check_name="Deployment automation exists",
            category=Category.cicd,
            severity=Severity.medium,
            weight=1.0,
            description="At least one workflow must contain a deployment step.",
        ),
        ScanCheck(
            check_id="CICD-007",
            check_name="Environment approvals configured",
            category=Category.cicd,
            severity=Severity.medium,
            weight=1.0,
            description="Deployment environments should require manual approval gates before promotion.",
        ),
        ScanCheck(
            check_id="CICD-008",
            check_name="Pipeline success rate >95%",
            category=Category.cicd,
            severity=Severity.medium,
            weight=1.0,
            description="The recent pipeline success rate across all workflows must exceed 95%.",
        ),
        ScanCheck(
            check_id="CICD-009",
            check_name="Average build time <10 min",
            category=Category.cicd,
            severity=Severity.low,
            weight=0.5,
            description="The average CI run duration across recent workflow executions must be under 10 minutes.",
        ),
        ScanCheck(
            check_id="CICD-010",
            check_name="Reusable workflows used",
            category=Category.cicd,
            severity=Severity.low,
            weight=0.5,
            description="Workflows should use reusable workflow calls to reduce duplication.",
        ),
        ScanCheck(
            check_id="CICD-011",
            check_name="Pipeline caching configured",
            category=Category.cicd,
            severity=Severity.low,
            weight=0.5,
            description="CI pipelines should use caching to speed up builds.",
        ),
        ScanCheck(
            check_id="CICD-012",
            check_name="Artifact signing enabled",
            category=Category.cicd,
            severity=Severity.medium,
            weight=1.0,
            description="Build artifacts should be signed to ensure integrity.",
        ),
        ScanCheck(
            check_id="CICD-013",
            check_name="Deployment rollback capability",
            category=Category.cicd,
            severity=Severity.medium,
            weight=1.0,
            description="Deployment workflows should include rollback capability.",
        ),
        ScanCheck(
            check_id="CICD-014",
            check_name="Multi-environment pipeline",
            category=Category.cicd,
            severity=Severity.medium,
            weight=1.0,
            description="Pipeline should support multiple environments (staging, production).",
        ),
    )

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        workflows: list[CIWorkflow] = data.ci_workflows
        results: list[CheckResult] = []

        # CICD-001
        if workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-001"],
                    status=CheckStatus.passed,
                    detail=f"{len(workflows)} CI/CD workflow(s) detected.",
                    evidence={
                        "workflow_count": len(workflows),
                        "names": [w.name for w in workflows],
                    },
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-001"],
                    status=CheckStatus.failed,
                    detail="No CI/CD workflow definitions were found.",
                )
            )

        # CICD-002
        pr_workflows = [w for w in workflows if "pull_request" in w.trigger_events]
        if pr_workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-002"],
                    status=CheckStatus.passed,
                    detail=f"{len(pr_workflows)} workflow(s) trigger on pull_request events.",
                    evidence={"pr_workflow_names": [w.name for w in pr_workflows]},
                )
            )
        elif not workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-002"],
                    status=CheckStatus.failed,
                    detail="No workflows exist; cannot evaluate PR triggers.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-002"],
                    status=CheckStatus.failed,
                    detail="No workflow triggers on pull_request events.",
                )
            )

        # CICD-003
        test_workflows = [w for w in workflows if w.has_tests]
        if test_workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-003"],
                    status=CheckStatus.passed,
                    detail=f"{len(test_workflows)} workflow(s) include a test step.",
                    evidence={"test_workflow_names": [w.name for w in test_workflows]},
                )
            )
        elif not workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-003"],
                    status=CheckStatus.failed,
                    detail="No workflows exist; cannot evaluate test coverage.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-003"],
                    status=CheckStatus.failed,
                    detail="No workflow includes a test-execution step.",
                )
            )

        # CICD-004
        lint_workflows = [w for w in workflows if w.has_lint]
        if lint_workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-004"],
                    status=CheckStatus.passed,
                    detail=f"{len(lint_workflows)} workflow(s) include a lint step.",
                    evidence={"lint_workflow_names": [w.name for w in lint_workflows]},
                )
            )
        elif not workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-004"],
                    status=CheckStatus.failed,
                    detail="No workflows exist; cannot evaluate linting.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-004"],
                    status=CheckStatus.failed,
                    detail="No workflow includes a linting step.",
                )
            )

        # CICD-005
        sec_workflows = [w for w in workflows if w.has_security_scan]
        if sec_workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-005"],
                    status=CheckStatus.passed,
                    detail=f"{len(sec_workflows)} workflow(s) include a security-scanning step.",
                    evidence={"security_workflow_names": [w.name for w in sec_workflows]},
                )
            )
        elif not workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-005"],
                    status=CheckStatus.failed,
                    detail="No workflows exist; cannot evaluate security scanning.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-005"],
                    status=CheckStatus.failed,
                    detail="No workflow includes a security-scanning step.",
                )
            )

        # CICD-006
        deploy_workflows = [w for w in workflows if w.has_deploy]
        if deploy_workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-006"],
                    status=CheckStatus.passed,
                    detail=f"{len(deploy_workflows)} workflow(s) include a deployment step.",
                    evidence={"deploy_workflow_names": [w.name for w in deploy_workflows]},
                )
            )
        elif not workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-006"],
                    status=CheckStatus.failed,
                    detail="No workflows exist; cannot evaluate deployment automation.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-006"],
                    status=CheckStatus.failed,
                    detail="No workflow includes a deployment step.",
                )
            )

        # CICD-007
        results.append(self._manual_review("CICD-007", "Environment approval gates"))

        # CICD-008 (pipeline success rate)
        all_runs: list[WorkflowRun] = [run for w in workflows for run in w.recent_runs]
        if not all_runs:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-008"],
                    status=CheckStatus.not_applicable,
                    detail="No recent workflow runs available for analysis.",
                )
            )
        else:
            completed_runs = [r for r in all_runs if r.conclusion is not None]
            if not completed_runs:
                results.append(
                    CheckResult(
                        check=self._check_map["CICD-008"],
                        status=CheckStatus.not_applicable,
                        detail="No completed workflow runs found.",
                    )
                )
            else:
                success_count = sum(1 for r in completed_runs if r.conclusion == "success")
                rate = success_count / len(completed_runs)
                rate_pct = round(rate * 100, 1)
                evidence = {
                    "total_runs": len(completed_runs),
                    "success_runs": success_count,
                    "success_rate_pct": rate_pct,
                }
                if rate >= 0.95:
                    results.append(
                        CheckResult(
                            check=self._check_map["CICD-008"],
                            status=CheckStatus.passed,
                            detail=f"Pipeline success rate is {rate_pct}% (threshold: 95%).",
                            evidence=evidence,
                        )
                    )
                elif rate >= 0.80:
                    results.append(
                        CheckResult(
                            check=self._check_map["CICD-008"],
                            status=CheckStatus.warning,
                            detail=f"Pipeline success rate is {rate_pct}% (below 95% threshold).",
                            evidence=evidence,
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            check=self._check_map["CICD-008"],
                            status=CheckStatus.failed,
                            detail=f"Pipeline success rate is only {rate_pct}% (below 80%).",
                            evidence=evidence,
                        )
                    )

        # CICD-009 (average build time)
        timed_runs = [r for r in all_runs if r.duration_seconds is not None]
        if not timed_runs:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-009"],
                    status=CheckStatus.not_applicable,
                    detail="No duration data available for recent workflow runs.",
                )
            )
        else:
            avg_seconds = sum(r.duration_seconds for r in timed_runs if r.duration_seconds is not None) / len(timed_runs)
            avg_minutes = round(avg_seconds / 60, 1)
            evidence = {
                "average_duration_seconds": round(avg_seconds, 1),
                "average_duration_minutes": avg_minutes,
                "sample_size": len(timed_runs),
            }
            if avg_seconds < 600:
                results.append(
                    CheckResult(
                        check=self._check_map["CICD-009"],
                        status=CheckStatus.passed,
                        detail=f"Average build time is {avg_minutes} min (threshold: 10 min).",
                        evidence=evidence,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=self._check_map["CICD-009"],
                        status=CheckStatus.failed,
                        detail=f"Average build time is {avg_minutes} min, exceeding the 10-minute threshold.",
                        evidence=evidence,
                    )
                )

        # CICD-010 (reusable workflows)
        results.append(self._manual_review("CICD-010", "Reusable workflow usage"))

        # CICD-011 (pipeline caching)
        results.append(self._manual_review("CICD-011", "Pipeline caching configuration"))

        # CICD-012 (artifact signing)
        results.append(self._manual_review("CICD-012", "Artifact signing"))

        # CICD-013 (deployment rollback)
        results.append(self._manual_review("CICD-013", "Deployment rollback capability"))

        # CICD-014 (multi-environment pipeline)
        if deploy_workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-014"],
                    status=CheckStatus.warning,
                    detail="Deployment workflows exist but multi-environment staging could not be verified. Manual review recommended.",
                )
            )
        elif not workflows:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-014"],
                    status=CheckStatus.failed,
                    detail="No workflows exist; cannot evaluate multi-environment pipeline.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["CICD-014"],
                    status=CheckStatus.failed,
                    detail="No deployment workflows found; multi-environment pipeline not detected.",
                )
            )

        return results

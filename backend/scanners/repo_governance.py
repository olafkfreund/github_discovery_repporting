from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import BranchProtection, RepoAssessmentData


class RepoGovernanceScanner(BaseScanner):
    """Evaluates repository governance practices including branch protection,
    code ownership, and merge hygiene.

    Checks REPO-001 through REPO-007 mirror the branch-protection evaluations
    used by the security scanner and are applied directly to the repository's
    default branch.  Checks REPO-008 onward cover structural governance
    artefacts and settings that cannot always be verified via the standard API.

    Category weight: 0.10.
    """

    category: Category = Category.repo_governance
    weight: float = 0.10

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS = (
        ScanCheck(
            check_id="REPO-001",
            check_name="Default branch protected",
            category=Category.repo_governance,
            severity=Severity.critical,
            weight=2.0,
            description="The repository's default branch must have branch-protection rules enabled.",
        ),
        ScanCheck(
            check_id="REPO-002",
            check_name="PR reviews required",
            category=Category.repo_governance,
            severity=Severity.high,
            weight=1.5,
            description="At least one approving review must be required before merging a pull request.",
        ),
        ScanCheck(
            check_id="REPO-003",
            check_name="Minimum 2 approvals required",
            category=Category.repo_governance,
            severity=Severity.medium,
            weight=1.0,
            description="Two or more approving reviews must be required before a pull request can be merged.",
        ),
        ScanCheck(
            check_id="REPO-004",
            check_name="Stale reviews dismissed on push",
            category=Category.repo_governance,
            severity=Severity.medium,
            weight=1.0,
            description="Existing approvals must be invalidated when new commits are pushed to an open PR.",
        ),
        ScanCheck(
            check_id="REPO-005",
            check_name="Admin enforcement enabled",
            category=Category.repo_governance,
            severity=Severity.high,
            weight=1.5,
            description="Branch-protection rules must apply to repository administrators without exception.",
        ),
        ScanCheck(
            check_id="REPO-006",
            check_name="Force push disabled",
            category=Category.repo_governance,
            severity=Severity.high,
            weight=1.5,
            description="Force-pushing to the default branch must be prohibited to preserve commit history.",
        ),
        ScanCheck(
            check_id="REPO-007",
            check_name="Signed commits required",
            category=Category.repo_governance,
            severity=Severity.low,
            weight=0.5,
            description="All commits merged to the default branch must be GPG-signed to verify authorship.",
        ),
        ScanCheck(
            check_id="REPO-008",
            check_name="CODEOWNERS file present",
            category=Category.repo_governance,
            severity=Severity.medium,
            weight=1.0,
            description="A CODEOWNERS file must define explicit ownership for code areas to auto-assign reviewers.",
        ),
        ScanCheck(
            check_id="REPO-009",
            check_name="Branch naming convention enforced",
            category=Category.repo_governance,
            severity=Severity.low,
            weight=0.5,
            description="Branch names must follow a documented convention (e.g. feat/, fix/, chore/) for traceability.",
        ),
        ScanCheck(
            check_id="REPO-010",
            check_name="Tag protection rules configured",
            category=Category.repo_governance,
            severity=Severity.medium,
            weight=1.0,
            description="Tag protection rules must restrict who can create or delete version tags.",
        ),
        ScanCheck(
            check_id="REPO-011",
            check_name="Auto-delete head branches enabled",
            category=Category.repo_governance,
            severity=Severity.low,
            weight=0.5,
            description="Merged PR branches must be deleted automatically to keep the branch list manageable.",
        ),
        ScanCheck(
            check_id="REPO-012",
            check_name="Merge strategy restricted",
            category=Category.repo_governance,
            severity=Severity.low,
            weight=0.5,
            description=(
                "The allowed merge strategies (merge commit, squash, rebase) must be explicitly "
                "restricted to maintain a clean and auditable commit history."
            ),
        ),
    )

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every REPO-xxx check against *data* and return one result each."""
        bp: BranchProtection | None = data.branch_protection
        results: list[CheckResult] = []

        # ---- Branch-protection checks (REPO-001 – REPO-007) ----------

        # REPO-001
        if bp is None:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-001"],
                    status=CheckStatus.failed,
                    detail="No branch-protection data found.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "REPO-001",
                    bp.is_protected,
                    passed="Default branch is protected.",
                    failed="Default branch protection is not enabled.",
                )
            )

        # REPO-002
        if bp is None:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-002"],
                    status=CheckStatus.failed,
                    detail="No branch-protection data found.",
                )
            )
        elif bp.required_reviews >= 1:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-002"],
                    status=CheckStatus.passed,
                    detail=f"Required approvals: {bp.required_reviews}.",
                    evidence={"required_reviews": bp.required_reviews},
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-002"],
                    status=CheckStatus.failed,
                    detail="No PR reviews are required before merging.",
                    evidence={"required_reviews": bp.required_reviews},
                )
            )

        # REPO-003
        if bp is None:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-003"],
                    status=CheckStatus.failed,
                    detail="No branch-protection data found.",
                )
            )
        elif bp.required_reviews >= 2:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-003"],
                    status=CheckStatus.passed,
                    detail=f"Required approvals: {bp.required_reviews}.",
                    evidence={"required_reviews": bp.required_reviews},
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-003"],
                    status=CheckStatus.failed,
                    detail=f"Only {bp.required_reviews} approval(s) required; minimum is 2.",
                    evidence={"required_reviews": bp.required_reviews},
                )
            )

        # REPO-004
        if bp is None:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-004"],
                    status=CheckStatus.failed,
                    detail="No branch-protection data found.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "REPO-004",
                    bp.dismiss_stale_reviews,
                    passed="Stale reviews are dismissed when new commits are pushed.",
                    failed="Stale reviews are not dismissed when new commits are pushed to an open PR.",
                )
            )

        # REPO-005
        if bp is None:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-005"],
                    status=CheckStatus.failed,
                    detail="No branch-protection data found.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "REPO-005",
                    bp.enforce_admins,
                    passed="Branch-protection rules are enforced for administrators.",
                    failed="Branch-protection rules are not enforced for repository administrators.",
                )
            )

        # REPO-006
        if bp is None:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-006"],
                    status=CheckStatus.failed,
                    detail="No branch-protection data found.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "REPO-006",
                    not bp.allow_force_pushes,
                    passed="Force pushes to the default branch are disabled.",
                    failed="Force pushes to the default branch are permitted.",
                )
            )

        # REPO-007
        if bp is None:
            results.append(
                CheckResult(
                    check=self._check_map["REPO-007"],
                    status=CheckStatus.failed,
                    detail="No branch-protection data found.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "REPO-007",
                    bp.require_signed_commits,
                    passed="Signed commits are required on the default branch.",
                    failed="Signed commits are not required.",
                )
            )

        # ---- Structural governance checks (REPO-008 – REPO-012) ------

        # REPO-008
        results.append(
            self._bool_check(
                "REPO-008",
                data.has_codeowners,
                passed="A CODEOWNERS file is present.",
                failed="No CODEOWNERS file was found. Add one to auto-assign reviewers based on code ownership.",
            )
        )

        # REPO-009  (branch naming convention — cannot verify via standard API)
        results.append(self._manual_review("REPO-009", "Branch naming convention enforcement"))

        # REPO-010  (tag protection rules — cannot verify via standard API)
        results.append(self._manual_review("REPO-010", "Tag protection rule configuration"))

        # REPO-011  (auto-delete head branches — cannot verify via standard API)
        results.append(self._manual_review("REPO-011", "Automatic head-branch deletion after merge"))

        # REPO-012  (merge strategy restricted — cannot verify via standard API)
        results.append(self._manual_review("REPO-012", "Allowed merge strategies (merge commit, squash, rebase)"))

        return results

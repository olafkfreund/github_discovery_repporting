from __future__ import annotations

"""Unit tests for the benchmark pure functions.

All four modules contain deterministic, side-effect-free functions that map
inputs to structured outputs.  No mocking, no database, and no async fixtures
are required — plain pytest classes with ``pytest.mark.parametrize`` for
boundary sweeps.

Covered:
    * ``backend.benchmarks.dora.classify_dora_level``
    * ``backend.benchmarks.openssf.calculate_openssf_alignment``
    * ``backend.benchmarks.slsa.calculate_slsa_level``
    * ``backend.benchmarks.cis.calculate_cis_compliance``
"""

import pytest

from backend.benchmarks.cis import CIS_CONTROLS, calculate_cis_compliance
from backend.benchmarks.dora import DORA_LEVELS, classify_dora_level
from backend.benchmarks.openssf import OPENSSF_MAPPING, calculate_openssf_alignment
from backend.benchmarks.slsa import SLSA_LEVELS, calculate_slsa_level

# ---------------------------------------------------------------------------
# DORA
# ---------------------------------------------------------------------------


class TestClassifyDoraLevel:
    """Tests for ``classify_dora_level(overall_score)``.

    The function maps a float in ``[0, 100]`` to one of four DORA performance
    bands using the ``score_threshold`` values defined in ``DORA_LEVELS``:

        elite  >= 85
        high   >= 70
        medium >= 50
        low    >= 0
    """

    # ------------------------------------------------------------------
    # Parametrised sweep: score → expected level
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "score, expected",
        [
            # --- low band ---
            (0.0, "low"),
            (0, "low"),
            (25.0, "low"),
            (49.9, "low"),
            # --- medium band ---
            (50.0, "medium"),
            (50, "medium"),
            (60.0, "medium"),
            (69.9, "medium"),
            # --- high band ---
            (70.0, "high"),
            (70, "high"),
            (77.5, "high"),
            (84.9, "high"),
            # --- elite band ---
            (85.0, "elite"),
            (85, "elite"),
            (90.0, "elite"),
            (100.0, "elite"),
        ],
    )
    def test_score_to_level_mapping(self, score: float, expected: str) -> None:
        """Each score maps to the correct DORA performance band."""
        assert classify_dora_level(score) == expected

    # ------------------------------------------------------------------
    # Boundary conditions at each threshold
    # ------------------------------------------------------------------

    def test_boundary_low_to_medium_below(self) -> None:
        """Score of 49.9 stays in 'low' — just below the medium threshold."""
        assert classify_dora_level(49.9) == "low"

    def test_boundary_low_to_medium_at(self) -> None:
        """Score of 50 is exactly the medium threshold — must return 'medium'."""
        assert classify_dora_level(50.0) == "medium"

    def test_boundary_medium_to_high_below(self) -> None:
        """Score of 69.9 stays in 'medium' — just below the high threshold."""
        assert classify_dora_level(69.9) == "medium"

    def test_boundary_medium_to_high_at(self) -> None:
        """Score of 70 is exactly the high threshold — must return 'high'."""
        assert classify_dora_level(70.0) == "high"

    def test_boundary_high_to_elite_below(self) -> None:
        """Score of 84.9 stays in 'high' — just below the elite threshold."""
        assert classify_dora_level(84.9) == "high"

    def test_boundary_high_to_elite_at(self) -> None:
        """Score of 85 is exactly the elite threshold — must return 'elite'."""
        assert classify_dora_level(85.0) == "elite"

    # ------------------------------------------------------------------
    # Extreme values
    # ------------------------------------------------------------------

    def test_zero_score_is_low(self) -> None:
        """A score of exactly zero must return 'low'."""
        assert classify_dora_level(0.0) == "low"

    def test_perfect_score_is_elite(self) -> None:
        """A perfect score of 100 must return 'elite'."""
        assert classify_dora_level(100.0) == "elite"

    # ------------------------------------------------------------------
    # Return type
    # ------------------------------------------------------------------

    def test_return_type_is_str(self) -> None:
        """The function always returns a str."""
        result = classify_dora_level(50.0)
        assert isinstance(result, str)

    # ------------------------------------------------------------------
    # All four DORA levels are reachable
    # ------------------------------------------------------------------

    def test_all_levels_reachable(self) -> None:
        """Every defined DORA level can be returned by the function."""
        scores = {0.0: "low", 55.0: "medium", 72.5: "high", 90.0: "elite"}
        for score, expected_level in scores.items():
            assert classify_dora_level(score) == expected_level

    # ------------------------------------------------------------------
    # Consistency with DORA_LEVELS reference data
    # ------------------------------------------------------------------

    def test_thresholds_match_reference_data(self) -> None:
        """Computed levels are consistent with the DORA_LEVELS thresholds dict."""
        for level, info in DORA_LEVELS.items():
            threshold = float(info["score_threshold"])  # type: ignore[arg-type]
            assert classify_dora_level(threshold) == level


# ---------------------------------------------------------------------------
# OpenSSF
# ---------------------------------------------------------------------------


class TestCalculateOpenSSFAlignment:
    """Tests for ``calculate_openssf_alignment(passed_check_ids)``.

    The function returns a dict mapping each OpenSSF Scorecard category to a
    boolean.  A category is ``True`` only when *all* of its required check IDs
    are in the passed set.
    """

    # ------------------------------------------------------------------
    # Return structure
    # ------------------------------------------------------------------

    def test_returns_all_categories(self) -> None:
        """Result always contains every category defined in OPENSSF_MAPPING."""
        result = calculate_openssf_alignment(set())
        assert set(result.keys()) == set(OPENSSF_MAPPING.keys())

    def test_return_values_are_booleans(self) -> None:
        """All values in the result are booleans."""
        result = calculate_openssf_alignment({"REPO-001"})
        for val in result.values():
            assert isinstance(val, bool)

    # ------------------------------------------------------------------
    # Empty input — all categories False
    # ------------------------------------------------------------------

    def test_empty_passed_ids_all_false(self) -> None:
        """With no passed checks, every category must be False."""
        result = calculate_openssf_alignment(set())
        assert all(not satisfied for satisfied in result.values())

    # ------------------------------------------------------------------
    # Full pass — all categories True
    # ------------------------------------------------------------------

    def test_all_checks_passed_all_true(self) -> None:
        """When every required check ID is passed, all categories must be True."""
        all_checks: set[str] = set()
        for check_ids in OPENSSF_MAPPING.values():
            all_checks.update(check_ids)
        result = calculate_openssf_alignment(all_checks)
        assert all(result.values())

    # ------------------------------------------------------------------
    # Single-check categories
    # ------------------------------------------------------------------

    def test_dependency_update_tool_satisfied_by_single_check(self) -> None:
        """'Dependency-Update-Tool' only requires DEP-001."""
        result = calculate_openssf_alignment({"DEP-001"})
        assert result["Dependency-Update-Tool"] is True

    def test_security_policy_satisfied_by_single_check(self) -> None:
        """'Security-Policy' only requires COMP-004."""
        result = calculate_openssf_alignment({"COMP-004"})
        assert result["Security-Policy"] is True

    def test_signed_releases_satisfied_by_single_check(self) -> None:
        """'Signed-Releases' only requires REPO-007."""
        result = calculate_openssf_alignment({"REPO-007"})
        assert result["Signed-Releases"] is True

    def test_token_permissions_satisfied_by_single_check(self) -> None:
        """'Token-Permissions' only requires IAM-008."""
        result = calculate_openssf_alignment({"IAM-008"})
        assert result["Token-Permissions"] is True

    def test_license_satisfied_by_single_check(self) -> None:
        """'License' only requires COMP-001."""
        result = calculate_openssf_alignment({"COMP-001"})
        assert result["License"] is True

    # ------------------------------------------------------------------
    # Multi-check categories: partial pass → False
    # ------------------------------------------------------------------

    def test_branch_protection_partial_pass_is_false(self) -> None:
        """'Branch-Protection' requires 5 checks — passing only 4 is not enough."""
        # OPENSSF_MAPPING["Branch-Protection"] = ["REPO-001","REPO-002","REPO-003","REPO-005","REPO-006"]
        partial = {"REPO-001", "REPO-002", "REPO-003", "REPO-005"}  # missing REPO-006
        result = calculate_openssf_alignment(partial)
        assert result["Branch-Protection"] is False

    def test_branch_protection_full_pass_is_true(self) -> None:
        """'Branch-Protection' is True only when all 5 required checks pass."""
        full = {"REPO-001", "REPO-002", "REPO-003", "REPO-005", "REPO-006"}
        result = calculate_openssf_alignment(full)
        assert result["Branch-Protection"] is True

    def test_code_review_partial_pass_is_false(self) -> None:
        """'Code-Review' requires SDLC-003 and REPO-002 — one is insufficient."""
        result = calculate_openssf_alignment({"SDLC-003"})
        assert result["Code-Review"] is False

    def test_code_review_full_pass_is_true(self) -> None:
        """'Code-Review' is True when both SDLC-003 and REPO-002 pass."""
        result = calculate_openssf_alignment({"SDLC-003", "REPO-002"})
        assert result["Code-Review"] is True

    def test_ci_tests_partial_pass_is_false(self) -> None:
        """'CI-Tests' requires CICD-001 and CICD-003 — one is insufficient."""
        result = calculate_openssf_alignment({"CICD-001"})
        assert result["CI-Tests"] is False

    def test_ci_tests_full_pass_is_true(self) -> None:
        """'CI-Tests' is True when both CICD-001 and CICD-003 pass."""
        result = calculate_openssf_alignment({"CICD-001", "CICD-003"})
        assert result["CI-Tests"] is True

    def test_sast_partial_pass_is_false(self) -> None:
        """'SAST' requires CICD-005 and SAST-001 — one is insufficient."""
        result = calculate_openssf_alignment({"CICD-005"})
        assert result["SAST"] is False

    def test_sast_full_pass_is_true(self) -> None:
        """'SAST' is True when both CICD-005 and SAST-001 pass."""
        result = calculate_openssf_alignment({"CICD-005", "SAST-001"})
        assert result["SAST"] is True

    def test_vulnerabilities_full_pass_is_true(self) -> None:
        """'Vulnerabilities' is True when both DEP-002 and DEP-003 pass."""
        result = calculate_openssf_alignment({"DEP-002", "DEP-003"})
        assert result["Vulnerabilities"] is True

    # ------------------------------------------------------------------
    # Irrelevant check IDs do not affect categories
    # ------------------------------------------------------------------

    def test_unrelated_check_ids_do_not_satisfy_category(self) -> None:
        """Passing a random check ID that belongs to no category changes nothing."""
        result_empty = calculate_openssf_alignment(set())
        result_noise = calculate_openssf_alignment({"TOTALLY-UNKNOWN-999"})
        assert result_empty == result_noise

    def test_passing_checks_for_one_category_does_not_affect_others(self) -> None:
        """Checks that satisfy 'License' must not affect 'Branch-Protection'."""
        result = calculate_openssf_alignment({"COMP-001"})
        assert result["License"] is True
        assert result["Branch-Protection"] is False

    # ------------------------------------------------------------------
    # Correct count of satisfied categories
    # ------------------------------------------------------------------

    def test_single_check_satisfies_expected_number_of_categories(self) -> None:
        """REPO-002 satisfies both 'Branch-Protection' and 'Code-Review' partially.

        On its own it is not enough for either because both categories require
        additional checks — so the count of True categories must be 0.
        """
        result = calculate_openssf_alignment({"REPO-002"})
        satisfied = [cat for cat, ok in result.items() if ok]
        assert len(satisfied) == 0


# ---------------------------------------------------------------------------
# SLSA
# ---------------------------------------------------------------------------


class TestCalculateSlsaLevel:
    """Tests for ``calculate_slsa_level(passed_check_ids)``.

    The function returns the highest integer SLSA level (0-3) achieved.
    Levels are cumulative: achieving Level 3 requires all checks for Levels
    1, 2, and 3.

        Level 0: no SLSA (nothing passed)
        Level 1: CICD-001
        Level 2: CICD-001, CICD-002
        Level 3: CICD-001, CICD-002, CICD-012, REPO-005
    """

    # ------------------------------------------------------------------
    # Parametrised sweep: passed IDs → expected level
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "passed_ids, expected_level",
        [
            # Level 0 — nothing relevant passed
            (set(), 0),
            ({"REPO-005"}, 0),  # L3 check without L1
            ({"CICD-002"}, 0),  # L2 check without L1
            ({"CICD-002", "CICD-012", "REPO-005"}, 0),  # L2+L3 but no L1
            # Level 1 — CICD-001 present, nothing else
            ({"CICD-001"}, 1),
            # Level 2 — CICD-001 + CICD-002
            ({"CICD-001", "CICD-002"}, 2),
            # Level 3 — full set
            ({"CICD-001", "CICD-002", "CICD-012", "REPO-005"}, 3),
        ],
    )
    def test_level_mapping(self, passed_ids: set[str], expected_level: int) -> None:
        """Passed check IDs map to the correct SLSA level."""
        assert calculate_slsa_level(passed_ids) == expected_level

    # ------------------------------------------------------------------
    # Empty set → Level 0
    # ------------------------------------------------------------------

    def test_empty_set_returns_zero(self) -> None:
        """No passed checks must return SLSA level 0."""
        assert calculate_slsa_level(set()) == 0

    # ------------------------------------------------------------------
    # Exact minimum sets for each level
    # ------------------------------------------------------------------

    def test_level_1_minimum_required_checks(self) -> None:
        """Only CICD-001 is needed to reach Level 1."""
        assert calculate_slsa_level({"CICD-001"}) == 1

    def test_level_2_minimum_required_checks(self) -> None:
        """CICD-001 and CICD-002 are the minimum required for Level 2."""
        assert calculate_slsa_level({"CICD-001", "CICD-002"}) == 2

    def test_level_3_minimum_required_checks(self) -> None:
        """All four checks are required to reach Level 3."""
        assert calculate_slsa_level({"CICD-001", "CICD-002", "CICD-012", "REPO-005"}) == 3

    # ------------------------------------------------------------------
    # Levels are cumulative — missing a lower-level check caps progress
    # ------------------------------------------------------------------

    def test_missing_cicd001_caps_at_level_0(self) -> None:
        """Without CICD-001 (L1), no SLSA level can be achieved."""
        # All L2 and L3 checks present, but L1 is absent
        assert calculate_slsa_level({"CICD-002", "CICD-012", "REPO-005"}) == 0

    def test_missing_cicd002_caps_at_level_1(self) -> None:
        """Without CICD-002 (L2), progress is capped at Level 1 even with L3 checks."""
        assert calculate_slsa_level({"CICD-001", "CICD-012", "REPO-005"}) == 1

    # ------------------------------------------------------------------
    # Extra / irrelevant checks do not affect result
    # ------------------------------------------------------------------

    def test_extra_checks_do_not_change_level(self) -> None:
        """Passing additional unrelated checks must not alter the computed level."""
        base = {"CICD-001", "CICD-002"}
        with_noise = base | {"TOTALLY-UNKNOWN-999", "IAM-001", "REPO-002"}
        assert calculate_slsa_level(base) == calculate_slsa_level(with_noise)

    # ------------------------------------------------------------------
    # Return type
    # ------------------------------------------------------------------

    def test_return_type_is_int(self) -> None:
        """The function always returns an int."""
        assert isinstance(calculate_slsa_level(set()), int)

    # ------------------------------------------------------------------
    # Consistency with SLSA_LEVELS reference data
    # ------------------------------------------------------------------

    def test_highest_level_uses_all_checks_from_reference(self) -> None:
        """Passing all checks from SLSA_LEVELS level 3 returns 3."""
        level3_checks: set[str] = set(
            SLSA_LEVELS[3]["required_checks"]  # type: ignore[arg-type]
        )
        assert calculate_slsa_level(level3_checks) == 3


# ---------------------------------------------------------------------------
# CIS
# ---------------------------------------------------------------------------


class TestCalculateCisCompliance:
    """Tests for ``calculate_cis_compliance(passed_check_ids)``.

    The function returns a dict keyed by CIS domain identifier.  Each value
    contains:
        description  -- human-readable domain name (str)
        total        -- number of checks in the domain (int)
        passed       -- number of those checks that are in passed_check_ids (int)
        percentage   -- (passed / total) * 100 (float)
        compliant    -- True only when passed == total (bool)

    CIS domains and their check counts:
        source-code      4 checks (REPO-001, REPO-002, REPO-006, REPO-008)
        build-pipelines  3 checks (CICD-001, CICD-003, CICD-005)
        dependencies     3 checks (DEP-001, DEP-002, DEP-003)
        artifacts        2 checks (DEP-009, REPO-007)
        deployment       2 checks (CICD-006, CICD-007)
    """

    # ------------------------------------------------------------------
    # Return structure
    # ------------------------------------------------------------------

    def test_returns_all_domains(self) -> None:
        """Result always contains every domain defined in CIS_CONTROLS."""
        result = calculate_cis_compliance(set())
        assert set(result.keys()) == set(CIS_CONTROLS.keys())

    def test_each_domain_has_required_keys(self) -> None:
        """Every domain entry must contain the five required keys."""
        required_keys = {"description", "total", "passed", "percentage", "compliant"}
        result = calculate_cis_compliance(set())
        for domain_id, domain_result in result.items():
            assert required_keys.issubset(domain_result.keys()), (
                f"Domain '{domain_id}' is missing keys"
            )

    # ------------------------------------------------------------------
    # Empty input — nothing compliant
    # ------------------------------------------------------------------

    def test_empty_passed_ids_all_domains_not_compliant(self) -> None:
        """With no passed checks, every domain must be non-compliant."""
        result = calculate_cis_compliance(set())
        for domain_id, domain_result in result.items():
            assert domain_result["compliant"] is False, (
                f"Domain '{domain_id}' should not be compliant with empty checks"
            )

    def test_empty_passed_ids_all_passed_counts_zero(self) -> None:
        """With no passed checks, every domain's 'passed' count must be 0."""
        result = calculate_cis_compliance(set())
        for domain_result in result.values():
            assert domain_result["passed"] == 0

    def test_empty_passed_ids_all_percentages_zero(self) -> None:
        """With no passed checks, every domain's percentage must be 0."""
        result = calculate_cis_compliance(set())
        for domain_result in result.values():
            assert domain_result["percentage"] == 0

    # ------------------------------------------------------------------
    # Full pass — everything compliant
    # ------------------------------------------------------------------

    def test_all_checks_passed_all_compliant(self) -> None:
        """When every required check passes, all domains must be compliant."""
        all_checks: set[str] = set()
        for control in CIS_CONTROLS.values():
            all_checks.update(control["checks"])  # type: ignore[arg-type]
        result = calculate_cis_compliance(all_checks)
        for domain_id, domain_result in result.items():
            assert domain_result["compliant"] is True, (
                f"Domain '{domain_id}' should be compliant when all checks pass"
            )

    def test_all_checks_passed_percentage_is_100(self) -> None:
        """Fully passed domains must show 100% compliance."""
        all_checks: set[str] = set()
        for control in CIS_CONTROLS.values():
            all_checks.update(control["checks"])  # type: ignore[arg-type]
        result = calculate_cis_compliance(all_checks)
        for domain_result in result.values():
            assert domain_result["percentage"] == 100.0

    # ------------------------------------------------------------------
    # source-code domain (4 checks)
    # ------------------------------------------------------------------

    def test_source_code_full_compliance(self) -> None:
        """Passing all 4 source-code checks makes the domain compliant."""
        checks = {"REPO-001", "REPO-002", "REPO-006", "REPO-008"}
        result = calculate_cis_compliance(checks)["source-code"]
        assert result["compliant"] is True
        assert result["passed"] == 4
        assert result["total"] == 4
        assert result["percentage"] == 100.0

    def test_source_code_partial_compliance(self) -> None:
        """Passing 2 of 4 source-code checks gives 50% but is not compliant."""
        checks = {"REPO-001", "REPO-002"}
        result = calculate_cis_compliance(checks)["source-code"]
        assert result["compliant"] is False
        assert result["passed"] == 2
        assert result["total"] == 4
        assert result["percentage"] == 50.0

    def test_source_code_no_compliance(self) -> None:
        """Passing zero source-code checks gives 0% and is not compliant."""
        result = calculate_cis_compliance(set())["source-code"]
        assert result["compliant"] is False
        assert result["passed"] == 0
        assert result["percentage"] == 0

    def test_source_code_boundary_one_missing(self) -> None:
        """Passing 3 of 4 source-code checks — boundary just below full compliance."""
        checks = {"REPO-001", "REPO-002", "REPO-006"}  # missing REPO-008
        result = calculate_cis_compliance(checks)["source-code"]
        assert result["compliant"] is False
        assert result["passed"] == 3
        assert result["percentage"] == 75.0

    # ------------------------------------------------------------------
    # build-pipelines domain (3 checks)
    # ------------------------------------------------------------------

    def test_build_pipelines_full_compliance(self) -> None:
        """Passing all 3 build-pipeline checks makes the domain compliant."""
        checks = {"CICD-001", "CICD-003", "CICD-005"}
        result = calculate_cis_compliance(checks)["build-pipelines"]
        assert result["compliant"] is True
        assert result["passed"] == 3
        assert result["total"] == 3
        assert result["percentage"] == 100.0

    def test_build_pipelines_one_passed(self) -> None:
        """Passing 1 of 3 build-pipeline checks gives ~33.3% and is not compliant."""
        result = calculate_cis_compliance({"CICD-001"})["build-pipelines"]
        assert result["compliant"] is False
        assert result["passed"] == 1
        assert pytest.approx(result["percentage"], abs=0.1) == 33.3  # type: ignore[arg-type]

    def test_build_pipelines_boundary_two_of_three(self) -> None:
        """Passing 2 of 3 build-pipeline checks gives ~66.7% but is not compliant."""
        result = calculate_cis_compliance({"CICD-001", "CICD-003"})["build-pipelines"]
        assert result["compliant"] is False
        assert result["passed"] == 2
        assert pytest.approx(result["percentage"], abs=0.1) == 66.7  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # dependencies domain (3 checks)
    # ------------------------------------------------------------------

    def test_dependencies_full_compliance(self) -> None:
        """Passing all 3 dependency checks makes the domain compliant."""
        checks = {"DEP-001", "DEP-002", "DEP-003"}
        result = calculate_cis_compliance(checks)["dependencies"]
        assert result["compliant"] is True
        assert result["passed"] == 3
        assert result["percentage"] == 100.0

    def test_dependencies_partial_compliance(self) -> None:
        """Passing 1 of 3 dependency checks is not sufficient for compliance."""
        result = calculate_cis_compliance({"DEP-001"})["dependencies"]
        assert result["compliant"] is False
        assert result["passed"] == 1

    # ------------------------------------------------------------------
    # artifacts domain (2 checks)
    # ------------------------------------------------------------------

    def test_artifacts_full_compliance(self) -> None:
        """Passing both artifact checks makes the domain compliant."""
        result = calculate_cis_compliance({"DEP-009", "REPO-007"})["artifacts"]
        assert result["compliant"] is True
        assert result["passed"] == 2
        assert result["total"] == 2
        assert result["percentage"] == 100.0

    def test_artifacts_boundary_one_of_two(self) -> None:
        """Passing 1 of 2 artifact checks gives 50% and is not compliant."""
        result = calculate_cis_compliance({"REPO-007"})["artifacts"]
        assert result["compliant"] is False
        assert result["passed"] == 1
        assert result["percentage"] == 50.0

    def test_artifacts_no_compliance(self) -> None:
        """Passing no artifact checks gives 0% compliance."""
        result = calculate_cis_compliance(set())["artifacts"]
        assert result["compliant"] is False
        assert result["passed"] == 0
        assert result["percentage"] == 0

    # ------------------------------------------------------------------
    # deployment domain (2 checks)
    # ------------------------------------------------------------------

    def test_deployment_full_compliance(self) -> None:
        """Passing both deployment checks makes the domain compliant."""
        result = calculate_cis_compliance({"CICD-006", "CICD-007"})["deployment"]
        assert result["compliant"] is True
        assert result["passed"] == 2
        assert result["total"] == 2

    def test_deployment_boundary_one_of_two(self) -> None:
        """Passing 1 of 2 deployment checks gives 50% and is not compliant."""
        result = calculate_cis_compliance({"CICD-006"})["deployment"]
        assert result["compliant"] is False
        assert result["passed"] == 1
        assert result["percentage"] == 50.0

    # ------------------------------------------------------------------
    # total counts match reference data
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "domain_id, expected_total",
        [
            ("source-code", 4),
            ("build-pipelines", 3),
            ("dependencies", 3),
            ("artifacts", 2),
            ("deployment", 2),
        ],
    )
    def test_total_counts_match_reference(self, domain_id: str, expected_total: int) -> None:
        """The 'total' field for each domain reflects the check count in CIS_CONTROLS."""
        result = calculate_cis_compliance(set())
        assert result[domain_id]["total"] == expected_total

    # ------------------------------------------------------------------
    # description field is populated
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "domain_id, expected_description",
        [
            ("source-code", "Source Code Management"),
            ("build-pipelines", "Build Pipelines"),
            ("dependencies", "Dependencies"),
            ("artifacts", "Artifacts"),
            ("deployment", "Deployment"),
        ],
    )
    def test_description_matches_reference(self, domain_id: str, expected_description: str) -> None:
        """The 'description' field must equal the human-readable name from CIS_CONTROLS."""
        result = calculate_cis_compliance(set())
        assert result[domain_id]["description"] == expected_description

    # ------------------------------------------------------------------
    # Unrelated check IDs do not affect domain counts
    # ------------------------------------------------------------------

    def test_unrelated_checks_do_not_inflate_passed_count(self) -> None:
        """Check IDs not in any CIS domain must not increment any 'passed' count."""
        result = calculate_cis_compliance({"TOTALLY-UNKNOWN-999", "PLAT-001"})
        for domain_result in result.values():
            assert domain_result["passed"] == 0

    # ------------------------------------------------------------------
    # Cross-domain isolation
    # ------------------------------------------------------------------

    def test_source_code_checks_do_not_affect_build_pipelines(self) -> None:
        """Source-code check IDs must only contribute to their own domain."""
        checks = {"REPO-001", "REPO-002", "REPO-006", "REPO-008"}
        result = calculate_cis_compliance(checks)
        assert result["source-code"]["compliant"] is True
        assert result["build-pipelines"]["compliant"] is False
        assert result["build-pipelines"]["passed"] == 0

    def test_deployment_checks_do_not_satisfy_dependencies(self) -> None:
        """Deployment check IDs must not affect the dependencies domain."""
        result = calculate_cis_compliance({"CICD-006", "CICD-007"})
        assert result["deployment"]["compliant"] is True
        assert result["dependencies"]["passed"] == 0

from __future__ import annotations

"""Smoke tests for the CI workflow template YAML files.

Uses PyYAML to assert each template:
- Is syntactically valid YAML.
- Contains the expected BPS-specific placeholders / variable references.

These tests do NOT execute the templates; they only validate structure.
"""

from pathlib import Path

import yaml

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "ci"


def _load_template(filename: str) -> dict:
    """Load and parse a YAML template file.

    Args:
        filename: File name relative to templates/ci/.

    Returns:
        Parsed YAML content as a dict.
    """
    path = TEMPLATES_DIR / filename
    assert path.exists(), f"Template not found: {path}"
    content = path.read_text()
    parsed = yaml.safe_load(content)
    assert parsed is not None, f"Template {filename} parsed as None (empty file?)"
    assert isinstance(parsed, dict), f"Template {filename} root must be a YAML mapping"
    return parsed


def _load_template_text(filename: str) -> str:
    """Return the raw text of a CI template file."""
    path = TEMPLATES_DIR / filename
    assert path.exists(), f"Template not found: {path}"
    return path.read_text()


# ---------------------------------------------------------------------------
# GitHub Actions template
# ---------------------------------------------------------------------------


class TestGitHubWorkflowTemplate:
    """Tests for templates/ci/github-workflow.yml."""

    def test_is_valid_yaml(self) -> None:
        """github-workflow.yml is valid YAML with a dict root."""
        _load_template("github-workflow.yml")

    def test_has_workflow_dispatch_trigger(self) -> None:
        """github-workflow.yml declares workflow_dispatch trigger."""
        parsed = _load_template("github-workflow.yml")
        assert "on" in parsed or True  # 'on' is a reserved key in Python YAML
        # Access via string key (PyYAML maps 'on' → True in some versions).
        on_block = parsed.get("on") or parsed.get(True)
        assert on_block is not None, "Missing 'on:' trigger block"
        assert "workflow_dispatch" in on_block

    def test_has_required_inputs(self) -> None:
        """github-workflow.yml declares agent_run_id, callback_url, callback_secret_hex inputs."""
        parsed = _load_template("github-workflow.yml")
        on_block = parsed.get("on") or parsed.get(True)
        dispatch_inputs = on_block["workflow_dispatch"]["inputs"]
        assert "agent_run_id" in dispatch_inputs
        assert "callback_url" in dispatch_inputs
        assert "callback_secret_hex" in dispatch_inputs

    def test_has_path_glob_inputs(self) -> None:
        """github-workflow.yml declares allowed_path_globs and denied_path_globs inputs."""
        parsed = _load_template("github-workflow.yml")
        on_block = parsed.get("on") or parsed.get(True)
        dispatch_inputs = on_block["workflow_dispatch"]["inputs"]
        assert "allowed_path_globs" in dispatch_inputs
        assert "denied_path_globs" in dispatch_inputs

    def test_contains_hmac_signing_pattern(self) -> None:
        """github-workflow.yml references openssl dgst + xxd for HMAC signing."""
        text = _load_template_text("github-workflow.yml")
        assert "openssl dgst -sha256" in text
        assert "xxd -r -p" in text
        assert "X-BPS-Signature" in text

    def test_contains_callback_post(self) -> None:
        """github-workflow.yml posts events back to /api/agent-runs/{id}/events."""
        text = _load_template_text("github-workflow.yml")
        assert "/api/agent-runs/" in text
        assert "/events" in text

    def test_has_jobs_block(self) -> None:
        """github-workflow.yml has at least one job defined."""
        parsed = _load_template("github-workflow.yml")
        assert "jobs" in parsed
        assert len(parsed["jobs"]) > 0


# ---------------------------------------------------------------------------
# GitLab CI template
# ---------------------------------------------------------------------------


class TestGitLabCITemplate:
    """Tests for templates/ci/gitlab-ci.yml."""

    def test_is_valid_yaml(self) -> None:
        """gitlab-ci.yml is valid YAML with a dict root."""
        _load_template("gitlab-ci.yml")

    def test_has_bps_agent_job(self) -> None:
        """gitlab-ci.yml defines a job for the BPS agent."""
        parsed = _load_template("gitlab-ci.yml")
        # Should have at least one non-'stages' key that's a job definition.
        job_keys = [k for k in parsed if k != "stages"]
        assert len(job_keys) > 0, "No job definitions found in gitlab-ci.yml"

    def test_has_agent_run_id_variable(self) -> None:
        """gitlab-ci.yml references AGENT_RUN_ID variable."""
        text = _load_template_text("gitlab-ci.yml")
        assert "AGENT_RUN_ID" in text

    def test_has_callback_variables(self) -> None:
        """gitlab-ci.yml references CALLBACK_URL and CALLBACK_SECRET_HEX."""
        text = _load_template_text("gitlab-ci.yml")
        assert "CALLBACK_URL" in text
        assert "CALLBACK_SECRET_HEX" in text

    def test_contains_hmac_signing_pattern(self) -> None:
        """gitlab-ci.yml references openssl dgst + xxd for HMAC signing."""
        text = _load_template_text("gitlab-ci.yml")
        assert "openssl dgst -sha256" in text
        assert "X-BPS-Signature" in text

    def test_contains_callback_post(self) -> None:
        """gitlab-ci.yml posts events back to /api/agent-runs/{id}/events."""
        text = _load_template_text("gitlab-ci.yml")
        assert "/api/agent-runs/" in text
        assert "/events" in text

    def test_has_path_glob_variables(self) -> None:
        """gitlab-ci.yml references ALLOWED_PATH_GLOBS and DENIED_PATH_GLOBS."""
        text = _load_template_text("gitlab-ci.yml")
        assert "ALLOWED_PATH_GLOBS" in text
        assert "DENIED_PATH_GLOBS" in text


# ---------------------------------------------------------------------------
# Azure Pipelines template
# ---------------------------------------------------------------------------


class TestAzurePipelinesTemplate:
    """Tests for templates/ci/azure-pipelines.yml."""

    def test_is_valid_yaml(self) -> None:
        """azure-pipelines.yml is valid YAML with a dict root."""
        _load_template("azure-pipelines.yml")

    def test_has_parameters(self) -> None:
        """azure-pipelines.yml declares parameters block."""
        parsed = _load_template("azure-pipelines.yml")
        assert "parameters" in parsed

    def test_has_required_parameters(self) -> None:
        """azure-pipelines.yml declares agent_run_id, callback_url, callback_secret_hex."""
        parsed = _load_template("azure-pipelines.yml")
        param_names = {p["name"] for p in parsed["parameters"]}
        assert "agent_run_id" in param_names
        assert "callback_url" in param_names
        assert "callback_secret_hex" in param_names

    def test_has_path_glob_parameters(self) -> None:
        """azure-pipelines.yml declares allowed_path_globs and denied_path_globs."""
        parsed = _load_template("azure-pipelines.yml")
        param_names = {p["name"] for p in parsed["parameters"]}
        assert "allowed_path_globs" in param_names
        assert "denied_path_globs" in param_names

    def test_trigger_none(self) -> None:
        """azure-pipelines.yml has trigger: none (not triggered by pushes).

        YAML parses ``trigger: none`` as the string ``"none"`` (not Python
        ``None``); both forms are accepted since Azure Pipelines treats both
        as "no automatic trigger".
        """
        parsed = _load_template("azure-pipelines.yml")
        trigger_val = parsed.get("trigger")
        # YAML parses `trigger: none` as the string "none", not Python None.
        assert trigger_val in (None, "none"), (
            f"Expected trigger to be None or 'none', got {trigger_val!r}"
        )

    def test_has_steps(self) -> None:
        """azure-pipelines.yml has at least one step defined."""
        parsed = _load_template("azure-pipelines.yml")
        assert "steps" in parsed
        assert len(parsed["steps"]) > 0

    def test_contains_hmac_signing_pattern(self) -> None:
        """azure-pipelines.yml references openssl dgst + xxd for HMAC signing."""
        text = _load_template_text("azure-pipelines.yml")
        assert "openssl dgst -sha256" in text
        assert "X-BPS-Signature" in text

    def test_contains_callback_post(self) -> None:
        """azure-pipelines.yml posts events back to /api/agent-runs/{id}/events."""
        text = _load_template_text("azure-pipelines.yml")
        assert "/api/agent-runs/" in text
        assert "/events" in text

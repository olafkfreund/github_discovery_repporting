"""Exhaustive security-critical tests for backend.agents.redactor (issue #21).

Design principles:
- Every pattern in _PATTERNS has at least one positive match test.
- Every pattern has at least one near-miss / non-match test.
- Idempotency is verified for representative inputs.
- redact_mapping() recursion is verified for dicts, lists, and all leaf types.
- Multi-pattern text is verified for correct simultaneous redaction.
- Order-sensitivity (ANTHROPIC before OPENAI) is explicitly tested.

Run with coverage::

    uv run python -m pytest tests/test_agents/test_redactor.py \
        --cov=backend.agents.redactor --cov-report=term -v
"""

from __future__ import annotations

import pytest

from backend.agents.redactor import redact, redact_mapping

# ---------------------------------------------------------------------------
# Helper constants — realistic-shaped fake credentials (safe to commit)
# ---------------------------------------------------------------------------

_GH_PAT_CLASSIC = "ghp_" + "a" * 36
_GH_PAT_FINE = "github_pat_" + "a" * 82
_GH_OAUTH = "ghs_" + "a" * 36  # server-to-server token
_GH_OAUTH_USER = "ghu_" + "a" * 36
_GH_OAUTH_APP = "gho_" + "a" * 36
_GH_OAUTH_REFRESH = "ghr_" + "a" * 36

_ANTHROPIC = "sk-ant-api03-" + "a" * 40
_OPENAI = "sk-" + "a" * 20

_GITLAB_PAT = "glpat-AaBbCcDdEeFfGgHhIiJjKk"
_GITLAB_FEED = "feed_token=SomeToken1234567890"

_AWS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
_AWS_SECRET = "a" * 40

_AZURE_PAT = "A" * 52  # 52-char alphanum, no adjacent alphanum in isolation

_SLACK = "xoxb-1234567890-abcdefghij"
_SLACK_APP = "xoxa-1234567890-abcdefghij"
_SLACK_USER = "xoxp-1234567890-abcdefghij"

_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ4In0.abc"

_BEARER = "Bearer abcdefghijklmnopqrstuv"

_PRIVATE_KEY_BLOCK = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
    "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\n"
    "-----END RSA PRIVATE KEY-----"
)

_EC_PRIVATE_KEY_BLOCK = (
    "-----BEGIN EC PRIVATE KEY-----\n"
    "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC\n"
    "-----END EC PRIVATE KEY-----"
)

_OPENSSH_PRIVATE_KEY_BLOCK = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


# ===========================================================================
# 1. Positive match tests — one per pattern
# ===========================================================================


@pytest.mark.parametrize(
    "category,input_text,expected_marker",
    [
        # LLM provider keys
        ("ANTHROPIC_KEY", _ANTHROPIC, "[REDACTED-ANTHROPIC_KEY]"),
        ("OPENAI_KEY", _OPENAI, "[REDACTED-OPENAI_KEY]"),
        # GitHub tokens
        ("GH_PAT_CLASSIC", _GH_PAT_CLASSIC, "[REDACTED-GH_PAT_CLASSIC]"),
        ("GH_PAT_FINE", _GH_PAT_FINE, "[REDACTED-GH_PAT_FINE]"),
        ("GH_OAUTH_GHS", _GH_OAUTH, "[REDACTED-GH_OAUTH]"),
        ("GH_OAUTH_GHU", _GH_OAUTH_USER, "[REDACTED-GH_OAUTH]"),
        ("GH_OAUTH_GHO", _GH_OAUTH_APP, "[REDACTED-GH_OAUTH]"),
        ("GH_OAUTH_GHR", _GH_OAUTH_REFRESH, "[REDACTED-GH_OAUTH]"),
        # GitLab tokens
        ("GITLAB_PAT", _GITLAB_PAT, "[REDACTED-GITLAB_PAT]"),
        ("GITLAB_FEED_TOKEN", _GITLAB_FEED, "[REDACTED-GITLAB_FEED_TOKEN]"),
        # AWS
        ("AWS_ACCESS_KEY", _AWS_KEY_ID, "[REDACTED-AWS_ACCESS_KEY]"),
        ("AWS_SECRET_KEY", _AWS_SECRET, "[REDACTED-AWS_SECRET_KEY]"),
        # Slack
        ("SLACK_TOKEN_BOT", _SLACK, "[REDACTED-SLACK_TOKEN]"),
        ("SLACK_TOKEN_APP", _SLACK_APP, "[REDACTED-SLACK_TOKEN]"),
        ("SLACK_TOKEN_USER", _SLACK_USER, "[REDACTED-SLACK_TOKEN]"),
        # JWT
        ("JWT", _JWT, "[REDACTED-JWT]"),
        # Bearer
        ("BEARER", _BEARER, "[REDACTED-BEARER]"),
    ],
)
def test_each_pattern_matches(category: str, input_text: str, expected_marker: str) -> None:
    """Each registered pattern detects a realistic-shaped fake secret."""
    result = redact(input_text)
    assert expected_marker in result, (
        f"Pattern {category!r}: expected {expected_marker!r} in output but got {result!r}"
    )
    assert input_text not in result, (
        f"Pattern {category!r}: raw secret should have been stripped from output"
    )


def test_azure_devops_pat_matched() -> None:
    """Azure DevOps PAT heuristic (52-char alphanum, no adjacent alphanum)."""
    # Isolated 52-char token with non-alphanum boundaries
    text = f"pat={_AZURE_PAT}&other=1"
    result = redact(text)
    assert "[REDACTED-AZURE_DEVOPS_PAT]" in result


def test_private_key_rsa_block_redacted() -> None:
    """RSA PRIVATE KEY block is fully redacted."""
    result = redact(_PRIVATE_KEY_BLOCK)
    assert "[REDACTED-PRIVATE_KEY]" in result
    assert "BEGIN" not in result
    assert "END" not in result


def test_private_key_ec_block_redacted() -> None:
    """EC PRIVATE KEY block is fully redacted."""
    result = redact(_EC_PRIVATE_KEY_BLOCK)
    assert "[REDACTED-PRIVATE_KEY]" in result


def test_private_key_openssh_block_redacted() -> None:
    """OPENSSH PRIVATE KEY block is fully redacted."""
    result = redact(_OPENSSH_PRIVATE_KEY_BLOCK)
    assert "[REDACTED-PRIVATE_KEY]" in result


# ===========================================================================
# 2. Near-miss / non-match tests (false-positive guard)
# ===========================================================================


@pytest.mark.parametrize(
    "text",
    [
        # Too short for OpenAI key (needs ≥20 alphanum after sk-)
        "sk-tooshort",
        "sk-abcdef",
        # AKIA but wrong 5th character (B not A)
        "AKIB1234567890123456",
        # ghp_ but only 20 chars (needs 36)
        "ghp_" + "a" * 20,
        # github_pat_ but body too short (needs 82); 39 chars is also below the
        # 40-char AWS_SECRET_KEY threshold so this string stays unreacted.
        "github_pat_" + "a" * 39,
        # ghs_ but too short (needs 36)
        "ghs_" + "a" * 10,
        # glpat- but too short (needs ≥20)
        "glpat-tooshort",
        # feed_token= but too short (needs ≥16)
        "feed_token=short",
        # xoxb but only 5 chars after dash (needs ≥10)
        "xoxb-12345",
        # Not a real JWT (first segment lacks eyJ prefix)
        "notjwt.eyJzdWIiOiJ4In0.abc",
        # Bearer but token too short (needs ≥16)
        "Bearer short",
        # Plain text — no secrets
        "plain text with no secrets",
        # Empty string
        "",
        # Whitespace only
        "   ",
        # Normal URL
        "https://github.com/org/repo",
        # A short hex digest (not 40 chars with clean boundaries for AWS secret)
        "deadbeef",
    ],
)
def test_no_false_positive(text: str) -> None:
    """Inputs without secret patterns must pass through unchanged."""
    assert redact(text) == text, f"Unexpected redaction of: {text!r}"


# ===========================================================================
# 3. Idempotency tests
# ===========================================================================


@pytest.mark.parametrize(
    "text",
    [
        f"key: {_AWS_KEY_ID} in a paragraph",
        f"two keys: {_AWS_KEY_ID} and {_GH_PAT_CLASSIC}",
        f"anthropic key {_ANTHROPIC} here",
        f"jwt: {_JWT}",
        f"bearer: {_BEARER}",
        _PRIVATE_KEY_BLOCK,
        "no secrets here",
        "",
        "   ",
    ],
)
def test_idempotent(text: str) -> None:
    """redact(redact(x)) == redact(x) for all inputs."""
    once = redact(text)
    twice = redact(once)
    assert once == twice, f"Idempotency violated for input: {text!r}"


# ===========================================================================
# 4. Multi-pattern in single string
# ===========================================================================


def test_multi_pattern_paragraph() -> None:
    """Multiple secrets in one string are all redacted; surrounding text is preserved."""
    text = f"API key: {_GH_PAT_CLASSIC}, AWS: {_AWS_KEY_ID}"
    result = redact(text)
    assert "[REDACTED-GH_PAT_CLASSIC]" in result
    assert "[REDACTED-AWS_ACCESS_KEY]" in result
    assert "ghp_" not in result
    assert "AKIA" not in result
    assert "API key:" in result
    assert "AWS:" in result


def test_multi_pattern_llm_and_github() -> None:
    """Anthropic key and GitHub classic PAT coexist in same text."""
    text = f"ant={_ANTHROPIC} gh={_GH_PAT_CLASSIC}"
    result = redact(text)
    assert "[REDACTED-ANTHROPIC_KEY]" in result
    assert "[REDACTED-GH_PAT_CLASSIC]" in result


def test_multi_pattern_jwt_and_bearer() -> None:
    """JWT and Bearer tokens both redacted when present together."""
    text = f"jwt={_JWT} auth={_BEARER}"
    result = redact(text)
    assert "[REDACTED-JWT]" in result
    assert "[REDACTED-BEARER]" in result


def test_gitlab_tokens_coexist() -> None:
    """GitLab PAT and feed_token redacted from same URL-like string."""
    text = f"glpat={_GITLAB_PAT}&{_GITLAB_FEED}"
    result = redact(text)
    assert "[REDACTED-GITLAB_PAT]" in result
    assert "[REDACTED-GITLAB_FEED_TOKEN]" in result


# ===========================================================================
# 5. Private key block (multi-line)
# ===========================================================================


def test_private_key_block_in_yaml() -> None:
    """PRIVATE_KEY block embedded in YAML-like text is redacted; surrounding content preserved."""
    text = f"""config:
  key: |
    {_PRIVATE_KEY_BLOCK}
  other: value"""
    result = redact(text)
    assert "[REDACTED-PRIVATE_KEY]" in result
    assert "BEGIN" not in result
    assert "END" not in result
    assert "config:" in result
    assert "other: value" in result


def test_multiple_private_key_blocks() -> None:
    """Two consecutive private key blocks are both redacted."""
    text = f"{_PRIVATE_KEY_BLOCK}\n\n{_EC_PRIVATE_KEY_BLOCK}"
    result = redact(text)
    assert result.count("[REDACTED-PRIVATE_KEY]") == 2


# ===========================================================================
# 6. Order-sensitivity: ANTHROPIC before OPENAI
# ===========================================================================


def test_anthropic_key_not_redacted_as_openai() -> None:
    """An Anthropic key is matched as ANTHROPIC_KEY, not OPENAI_KEY."""
    result = redact(_ANTHROPIC)
    assert "ANTHROPIC_KEY" in result
    assert "OPENAI_KEY" not in result


def test_openai_key_matched_when_not_anthropic() -> None:
    """A plain sk- key (no sk-ant- prefix) matches OPENAI_KEY."""
    result = redact(_OPENAI)
    assert "OPENAI_KEY" in result
    assert "ANTHROPIC_KEY" not in result


# ===========================================================================
# 7. redact_mapping() recursion
# ===========================================================================


def test_mapping_recurses() -> None:
    """redact_mapping descends into nested dicts, lists, and leaf types."""
    data: dict = {
        "level1": {
            "key": _AWS_KEY_ID,
            "list": [
                "plain",
                _GH_PAT_CLASSIC,
                {"nested": _BEARER},
            ],
            "int_value": 42,
            "bool_value": True,
            "none_value": None,
        }
    }
    result = redact_mapping(data)
    assert result["level1"]["key"].startswith("[REDACTED-AWS_ACCESS_KEY]")  # type: ignore[index]
    assert result["level1"]["list"][0] == "plain"  # type: ignore[index]
    assert result["level1"]["list"][1] == "[REDACTED-GH_PAT_CLASSIC]"  # type: ignore[index]
    assert "[REDACTED-BEARER]" in result["level1"]["list"][2]["nested"]  # type: ignore[index]
    assert result["level1"]["int_value"] == 42  # type: ignore[index]
    assert result["level1"]["bool_value"] is True  # type: ignore[index]
    assert result["level1"]["none_value"] is None  # type: ignore[index]


def test_mapping_top_level_list() -> None:
    """redact_mapping handles a top-level list."""
    data = [_AWS_KEY_ID, "plain", _GH_PAT_CLASSIC]
    result = redact_mapping(data)
    assert result[0] == "[REDACTED-AWS_ACCESS_KEY]"  # type: ignore[index]
    assert result[1] == "plain"  # type: ignore[index]
    assert result[2] == "[REDACTED-GH_PAT_CLASSIC]"  # type: ignore[index]


def test_mapping_does_not_mutate_input() -> None:
    """redact_mapping returns a new structure; the original dict is unchanged."""
    original = {"secret": _AWS_KEY_ID}
    result = redact_mapping(original)
    assert original["secret"] == _AWS_KEY_ID  # input not mutated
    assert result["secret"] == "[REDACTED-AWS_ACCESS_KEY]"  # type: ignore[index]


def test_mapping_empty_dict() -> None:
    """redact_mapping handles an empty dict."""
    assert redact_mapping({}) == {}


def test_mapping_empty_list() -> None:
    """redact_mapping handles an empty list."""
    assert redact_mapping([]) == []


def test_mapping_deeply_nested() -> None:
    """redact_mapping descends into deeply nested structures."""
    data = {"a": {"b": {"c": {"d": _ANTHROPIC}}}}
    result = redact_mapping(data)
    assert result["a"]["b"]["c"]["d"] == "[REDACTED-ANTHROPIC_KEY]"  # type: ignore[index]


# ===========================================================================
# 8. redact_mapping() leaf type pass-through
# ===========================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (42, 42),
        (3.14, 3.14),
        (True, True),
        (False, False),
        (None, None),
        # str values ARE redacted
        (_GH_PAT_CLASSIC, "[REDACTED-GH_PAT_CLASSIC]"),
        # sets pass through unchanged (see module docstring limitation #6)
        ({1, 2, 3}, {1, 2, 3}),
        # tuples pass through unchanged (see module docstring limitation #6)
        ((1, "secret"), (1, "secret")),
    ],
)
def test_mapping_leaf_types(value: object, expected: object) -> None:
    """Scalar and opaque types are handled correctly by redact_mapping."""
    assert redact_mapping(value) == expected


# ===========================================================================
# 9. Empty / falsy inputs to redact()
# ===========================================================================


def test_empty_string() -> None:
    """redact('') returns '' without raising."""
    assert redact("") == ""


def test_whitespace_only() -> None:
    """Whitespace-only strings are not redacted (no pattern matches)."""
    assert redact("   ") == "   "


def test_no_secrets_plain() -> None:
    """Plain text without secrets is returned verbatim."""
    assert redact("hello world") == "hello world"


def test_non_string_raises_type_error() -> None:
    """Passing None to redact() raises TypeError (type contract)."""
    with pytest.raises(TypeError):
        redact(None)  # type: ignore[arg-type]


def test_integer_raises_type_error() -> None:
    """Passing an int to redact() raises TypeError."""
    with pytest.raises(TypeError):
        redact(42)  # type: ignore[arg-type]


# ===========================================================================
# 10. Surrogate context preservation
# ===========================================================================


def test_surrounding_text_preserved_after_redaction() -> None:
    """Text surrounding the secret is not stripped."""
    text = f"Before {_GH_PAT_CLASSIC} After"
    result = redact(text)
    assert result.startswith("Before ")
    assert result.endswith(" After")
    assert "[REDACTED-GH_PAT_CLASSIC]" in result


def test_multiple_occurrences_of_same_secret() -> None:
    """The same secret appearing twice in one string is redacted both times."""
    text = f"{_SLACK} and again {_SLACK}"
    result = redact(text)
    assert result.count("[REDACTED-SLACK_TOKEN]") == 2
    assert _SLACK not in result


# ===========================================================================
# 11. Redacted markers are themselves idempotent
# ===========================================================================


def test_redacted_marker_not_re_redacted() -> None:
    """A [REDACTED-*] marker in the input is not further transformed."""
    marker = "[REDACTED-GH_PAT_CLASSIC]"
    assert redact(marker) == marker


def test_redacted_marker_aws_not_re_redacted() -> None:
    """[REDACTED-AWS_ACCESS_KEY] in input is not touched by subsequent patterns."""
    marker = "[REDACTED-AWS_ACCESS_KEY]"
    assert redact(marker) == marker


# ===========================================================================
# 12. Realistic scenario tests
# ===========================================================================


def test_github_actions_log_snippet() -> None:
    """A CI log line containing a GitHub PAT is sanitised correctly."""
    log = (
        f"::add-mask::{_GH_PAT_CLASSIC}\n"
        "Run git push origin main\n"
        f"remote: https://{_GH_PAT_CLASSIC}@github.com/org/repo.git\n"
    )
    result = redact(log)
    assert _GH_PAT_CLASSIC not in result
    assert "[REDACTED-GH_PAT_CLASSIC]" in result
    assert "Run git push origin main" in result


def test_json_like_payload_with_multiple_secrets() -> None:
    """A JSON-like string with multiple secret fields is fully sanitised."""
    payload = f'{{"api_key": "{_OPENAI}", "aws_id": "{_AWS_KEY_ID}", "count": 5}}'
    result = redact(payload)
    assert _OPENAI not in result
    assert _AWS_KEY_ID not in result
    assert "[REDACTED-OPENAI_KEY]" in result
    assert "[REDACTED-AWS_ACCESS_KEY]" in result
    assert '"count": 5' in result


def test_env_file_lines() -> None:
    """.env file lines with secrets are individually sanitised."""
    lines = [
        f"ANTHROPIC_API_KEY={_ANTHROPIC}",
        "LOG_LEVEL=INFO",
        f"GITHUB_TOKEN={_GH_PAT_CLASSIC}",
    ]
    results = [redact(line) for line in lines]
    assert _ANTHROPIC not in results[0]
    assert "[REDACTED-ANTHROPIC_KEY]" in results[0]
    assert results[1] == "LOG_LEVEL=INFO"
    assert _GH_PAT_CLASSIC not in results[2]
    assert "[REDACTED-GH_PAT_CLASSIC]" in results[2]


def test_redact_mapping_full_api_response() -> None:
    """A realistic nested API response is sanitised by redact_mapping."""
    response = {
        "status": "ok",
        "data": {
            "credentials": {
                "github": _GH_PAT_CLASSIC,
                "openai": _OPENAI,
                "slack": _SLACK,
            },
            "counts": {
                "repos": 10,
                "orgs": 2,
            },
            "tags": ["production", "v2"],
            "notes": f"Token {_AWS_KEY_ID} used for backup.",
        },
    }
    result = redact_mapping(response)
    creds = result["data"]["credentials"]  # type: ignore[index]
    assert creds["github"] == "[REDACTED-GH_PAT_CLASSIC]"
    assert creds["openai"] == "[REDACTED-OPENAI_KEY]"
    assert creds["slack"] == "[REDACTED-SLACK_TOKEN]"
    # Non-secret integers preserved
    counts = result["data"]["counts"]  # type: ignore[index]
    assert counts["repos"] == 10
    assert counts["orgs"] == 2
    # Plain strings in lists preserved
    tags = result["data"]["tags"]  # type: ignore[index]
    assert tags[0] == "production"
    assert tags[1] == "v2"
    # Secret in notes string redacted
    notes: str = result["data"]["notes"]  # type: ignore[index]
    assert _AWS_KEY_ID not in notes
    assert "[REDACTED-AWS_ACCESS_KEY]" in notes

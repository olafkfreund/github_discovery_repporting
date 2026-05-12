"""Secret-redaction utilities for pre-LLM payload scrubbing (REQ-030, REQ-080).

This module provides a pure, side-effect-free redaction layer that strips
secret-shaped substrings from arbitrary text before the text is stored in
the database or forwarded to a downstream language model.

Design principles
-----------------
- **Pure functions** — no I/O, no logging, no global state mutated at call time.
- **Idempotent** — ``redact(redact(x)) == redact(x)`` for all inputs.
- **Order-sensitive** — patterns in ``_PATTERNS`` are applied in declaration
  order; the most specific prefix must come first.  For example,
  ``sk-ant-`` is listed before ``sk-`` so the Anthropic key pattern
  claims the match before the generic OpenAI key pattern fires.
- **Compile-once** — all ``re.Pattern`` objects are compiled at import time;
  no per-call compilation overhead.

Known limitations
-----------------
The following secret shapes are intentionally **not** detected:

1. **Generic high-entropy strings** without a fixed, machine-readable prefix.
   Detection would require entropy analysis (e.g. Shannon entropy > 4.5 bits/char)
   and would produce an unacceptably high false-positive rate on base64-encoded
   images, binary fields, and hash digests.

2. **Custom in-house credential formats** — formats specific to an organisation
   that are not publicly documented cannot be covered by a static rule set.

3. **Encrypted ciphertexts** — a Fernet token or AES-GCM blob may incidentally
   match the AWS secret-key or Azure DevOps PAT heuristic.  Such false positives
   are accepted: the replacement ``[REDACTED-*]`` marker is safe and the
   ciphertext is meaningless outside the system that encrypted it.

4. **AWS secret access key (false positives)** — the 40-character base64-ish
   pattern used here is intentionally generous.  Long base64 payloads (e.g.
   encoded images, PEM bodies embedded in JSON) may be erroneously redacted.
   Callers should strip or encode binary payloads before passing text to
   :func:`redact`.

5. **Azure DevOps PAT (false positives)** — Azure PATs are 52-character
   base64 strings with no fixed prefix, so the rule relies on a length-and-
   character-class heuristic with negative lookbehind/lookahead word boundaries.
   Short SHA-256 hex substrings or UUIDs immediately adjacent to alphanumeric
   context may match.  The trade-off is accepted for this internal tool where
   the cost of a missed PAT far outweighs the cost of a false redaction.

6. **Tuples, sets, and arbitrary objects** — :func:`redact_mapping` only
   recurses into ``dict`` and ``list`` containers and applies :func:`redact`
   to ``str`` leaves.  Tuples, sets, and custom objects pass through unchanged.
   Callers must normalise their data before passing in if these types may carry
   secrets.
"""

from __future__ import annotations

import re
from typing import Any, Final

# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------
# Each entry is a (category_name, compiled_pattern) pair.
# ORDER MATTERS — apply most-specific patterns first so that e.g. the
# ``sk-ant-`` Anthropic prefix is consumed before the generic ``sk-``
# OpenAI rule can fire on the same substring.

_PATTERNS: Final[list[tuple[str, re.Pattern[str]]]] = [
    # ---- LLM provider keys ------------------------------------------------
    # Anthropic: sk-ant-<apiXX>-<40+ alphanum/dash/underscore>
    # Must precede the OpenAI rule because the Anthropic prefix starts with sk-.
    ("ANTHROPIC_KEY", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    # OpenAI: sk- followed by ≥20 alphanumeric characters.
    # Word boundaries prevent matching the Anthropic "sk-ant-" form (already
    # consumed above) and avoid matching inside longer tokens.
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    # ---- GitHub tokens ----------------------------------------------------
    # Classic PAT: ghp_ + exactly 36 alphanum chars.
    ("GH_PAT_CLASSIC", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    # Fine-grained PAT: github_pat_ + exactly 82 chars (underscore-separated).
    ("GH_PAT_FINE", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
    # OAuth / server-to-server / user-to-server / refresh tokens.
    # Prefixes: ghs_ gho_ ghu_ ghr_
    ("GH_OAUTH", re.compile(r"\bgh[osur]_[A-Za-z0-9]{36}\b")),
    # ---- GitLab tokens ----------------------------------------------------
    # Personal access token: glpat- + ≥20 alphanum/dash/underscore.
    ("GITLAB_PAT", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b")),
    # Feed token: URL-parameter style.
    ("GITLAB_FEED_TOKEN", re.compile(r"feed_token=[A-Za-z0-9_\-]{16,}")),
    # ---- JWT (heuristic) --------------------------------------------------
    # Three dot-separated base64url segments where the first two decode to JSON.
    # The eyJ prefix ({"  base64url-encoded) is the stable anchor.
    # MUST precede AWS_SECRET_KEY: the base64url character set used by JWT
    # overlaps with the 40-char base64 pattern, so a JWT header segment of the
    # right length would otherwise be consumed by the AWS heuristic first.
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")),
    # ---- HTTP Bearer header -----------------------------------------------
    # Matches the token portion of an Authorization: Bearer … header or any
    # inline "Bearer <token>" string with ≥16 alphanum/dash/dot chars.
    # MUST precede AWS_SECRET_KEY for the same reason as JWT above.
    ("BEARER", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{16,}")),
    # ---- AWS --------------------------------------------------------------
    # Access Key ID: AKIA + exactly 16 uppercase alphanumeric chars.
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Secret Access Key: heuristic 40-char base64-ish with negative
    # lookbehind/lookahead to avoid matching inside longer base64 blobs.
    # FALSE POSITIVE RISK: long base64 payloads (e.g. encoded images) may match.
    # See module-level docstring for the accepted trade-off.
    ("AWS_SECRET_KEY", re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])")),
    # ---- Azure DevOps -----------------------------------------------------
    # PAT: 52-char base64 string; no fixed prefix.  Relies on word-boundary
    # heuristic.  FALSE POSITIVE RISK documented in module docstring.
    ("AZURE_DEVOPS_PAT", re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]{52}(?![A-Za-z0-9])")),
    # ---- Slack ------------------------------------------------------------
    # Bot, app, user, refresh, and workspace tokens.
    # Prefixes: xoxa- xoxb- xoxp- xoxr- xoxs-
    ("SLACK_TOKEN", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    # ---- PEM private key blocks -------------------------------------------
    # Multiline match for BEGIN/END PRIVATE KEY blocks (RSA, EC, OPENSSH, etc.).
    # re.DOTALL not needed because [\s\S] matches any character including newlines.
    (
        "PRIVATE_KEY",
        re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----"),
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact(text: str) -> str:
    """Strip secret-shaped substrings and return the sanitised output.

    Each pattern match is replaced with ``[REDACTED-<CATEGORY>]`` where
    ``<CATEGORY>`` is the uppercase category name from the pattern registry
    (e.g. ``[REDACTED-ANTHROPIC_KEY]``).

    Properties
    ----------
    - **Pure** — no I/O, no logging, no side effects.
    - **Idempotent** — ``redact(redact(x)) == redact(x)`` for all inputs.
    - **Order-sensitive** — patterns are applied in ``_PATTERNS`` order; the
      most specific match wins.

    Args:
        text: Arbitrary text to sanitise.  Must be a ``str``; passing ``None``
            raises ``TypeError``.  Pass an empty string explicitly when the
            caller has no content to sanitise.

    Returns:
        The sanitised text with every secret-shaped substring replaced by a
        ``[REDACTED-*]`` marker.  Non-secret content is preserved verbatim.

    Raises:
        TypeError: If *text* is not a ``str`` (e.g. ``None`` passed by
            accident).

    Example::

        >>> redact("token: ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        'token: [REDACTED-GH_PAT_CLASSIC]'

        >>> redact("")
        ''
    """
    if not isinstance(text, str):
        raise TypeError(f"redact() requires a str argument, got {type(text).__name__!r}")
    if not text:
        return text
    result = text
    for name, pattern in _PATTERNS:
        result = pattern.sub(f"[REDACTED-{name}]", result)
    return result


def redact_mapping(
    data: dict[str, Any] | list[Any] | Any,
) -> dict[str, Any] | list[Any] | Any:
    """Recursively apply :func:`redact` to every string value in *data*.

    Container types (``dict``, ``list``) are walked depth-first; new instances
    are returned — the input structure is **not mutated**.

    Leaf-type behaviour
    -------------------
    - ``str`` — passed through :func:`redact`.
    - ``int``, ``float``, ``bool``, ``None`` — returned unchanged.
    - ``set``, ``tuple``, and all other types — returned unchanged.
      Callers should normalise these before passing in if they may carry
      secrets (see module-level docstring, limitation #6).

    Args:
        data: Arbitrary nested structure of ``dict``, ``list``, ``str``, and
            scalar values.

    Returns:
        A new structure of the same shape with all string leaves sanitised.

    Example::

        >>> redact_mapping({"key": "AKIAIOSFODNN7EXAMPLE", "count": 1})
        {'key': '[REDACTED-AWS_ACCESS_KEY]', 'count': 1}
    """
    if isinstance(data, dict):
        return {k: redact_mapping(v) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_mapping(item) for item in data]
    if isinstance(data, str):
        return redact(data)
    # int, float, bool, None, set, tuple, custom objects — pass through
    return data

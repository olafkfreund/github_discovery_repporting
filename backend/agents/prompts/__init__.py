"""Prompt loader for the agent remediation subsystem.

Provides :func:`load_prompt` — a cached loader that reads per-check operator
prompt templates and returns their content together with a SHA256 hex digest
for prompt-versioning audit (REQ-052).

Templates live under ``backend/agents/prompts/per_check/`` and use
``{placeholder}`` syntax for ``str.format(**ctx)`` substitution by the
runner (issue #26).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "per_check"


@lru_cache(maxsize=64)
def load_prompt(filename: str) -> tuple[str, str]:
    """Return ``(content, sha256_hex)`` for a prompt template file.

    The function is memoised with :func:`functools.lru_cache` so the file is
    only read from disk once per process lifetime per unique filename.

    Args:
        filename: Relative filename under
            ``backend/agents/prompts/per_check/`` (e.g. ``"generic.md"``,
            ``"REPO-001.md"``).

    Returns:
        A 2-tuple of:
        - ``content``: Raw template text as a UTF-8 string.
        - ``sha256_hex``: 64-character lowercase hex digest of the template
          content (encoded UTF-8), recorded on AgentStep rows for audit.

    Raises:
        FileNotFoundError: If *filename* does not exist in the prompts
            directory.
    """
    path = _PROMPTS_DIR / filename
    content = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content, sha

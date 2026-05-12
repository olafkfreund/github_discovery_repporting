from __future__ import annotations

"""Built-in skill library and registry loader.

Skills are authoritative prose documents (markdown files) that the agent system
injects into its context when remediating findings or enriching scan results.

Built-in skills live as ``.md`` files under ``backend/skills/library/``.  Each file
starts with a YAML frontmatter block delimited by ``---`` markers, followed by the
skill body.

The :func:`get_skill_registry` function parses and validates every file at import time
(lazy, cached) and returns a dict keyed by skill slug.
"""

import functools
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.scanners.registry import CATEGORY_DISPLAY_NAMES, get_scanner_registry
from backend.schemas.skill import SkillFrontmatter

_LIBRARY_DIR = Path(__file__).parent / "library"


@dataclass(frozen=True)
class BuiltinSkill:
    """Parsed and validated representation of a built-in skill markdown file.

    Attributes:
        name: Slug (matches the file stem and the ``name`` frontmatter field).
        frontmatter: Validated :class:`~backend.schemas.skill.SkillFrontmatter`.
        body: Markdown body text following the closing ``---`` delimiter.
        sha256: Hex-encoded SHA-256 digest of the full file content.
    """

    name: str
    frontmatter: SkillFrontmatter
    body: str
    sha256: str


def _parse_skill_file(path: Path) -> BuiltinSkill:
    """Parse one markdown file and return a validated :class:`BuiltinSkill`.

    The file must start with ``---``, contain a YAML block, close with ``---``,
    and be followed by the body text.  The frontmatter ``name`` field must match
    the file stem.  Every entry in ``applies_to`` must correspond to a real
    check ID from the scanner registry.

    Args:
        path: Absolute path to the ``.md`` skill file.

    Returns:
        A validated :class:`BuiltinSkill` instance.

    Raises:
        ValueError: When the file is malformed, the name mismatches the stem,
            the category is unrecognised, or an ``applies_to`` ID is unknown.
    """
    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        raise ValueError(f"{path}: missing YAML frontmatter (file must start with ---)")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: malformed frontmatter (no closing --- found)")

    fm_dict = yaml.safe_load(parts[1])
    fm = SkillFrontmatter.model_validate(fm_dict)
    body = parts[2].lstrip("\n")

    if fm.name != path.stem:
        raise ValueError(
            f"{path}: frontmatter name {fm.name!r} must match filename stem {path.stem!r}"
        )

    valid_categories = set(CATEGORY_DISPLAY_NAMES.keys()) | {"general"}
    if fm.category not in valid_categories:
        raise ValueError(f"{path}: category {fm.category!r} not in {sorted(valid_categories)}")

    # Validate applies_to against the live scanner registry.
    all_check_ids: set[str] = set()
    for cat in get_scanner_registry():
        for check in cat.checks:
            all_check_ids.add(check.check_id)

    unknown = set(fm.applies_to) - all_check_ids
    if unknown:
        raise ValueError(f"{path}: applies_to contains unknown check_ids: {sorted(unknown)}")

    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return BuiltinSkill(name=fm.name, frontmatter=fm, body=body, sha256=sha)


@functools.lru_cache(maxsize=1)
def get_skill_registry() -> dict[str, BuiltinSkill]:
    """Walk ``backend/skills/library/*.md``, parse each file, and return a registry.

    The result is cached after the first call.  Call
    ``get_skill_registry.cache_clear()`` to reset the cache in tests.

    Returns:
        A dict mapping skill slug (name) to :class:`BuiltinSkill`, ordered by name.

    Raises:
        ValueError: When any file fails validation or a duplicate slug is found.
    """
    skills: dict[str, BuiltinSkill] = {}
    for path in sorted(_LIBRARY_DIR.glob("*.md")):
        skill = _parse_skill_file(path)
        if skill.name in skills:
            raise ValueError(f"Duplicate skill name {skill.name!r} in skill library")
        skills[skill.name] = skill
    return skills

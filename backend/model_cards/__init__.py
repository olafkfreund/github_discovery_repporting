"""Built-in model cards (REQ-050)."""

from __future__ import annotations

import functools
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ModelCardMetadata:
    """Immutable metadata descriptor for a built-in model card.

    Attributes:
        slug: Filename stem used as the URL-safe identifier
            (``<provider>__<model>``).
        provider: LLM provider string (e.g. ``"anthropic"``, ``"openai"``).
        model: Model identifier as used in API calls.
        display_name: Human-readable name for the UI.
        context_window: Maximum token context window for the model.
        supports_tool_use: Whether the model supports structured tool calls.
        supports_structured_output: Whether the model supports JSON schema
            structured output.
        training_data_class: Broad classification of training data
            (e.g. ``"web_general"``).
        training_data_cutoff: ISO-8601 year-month of training data cutoff,
            or ``None`` if not published.
        license: License or access model (e.g. ``"proprietary"``).
        refreshed_at: ISO-8601 date this card was last reviewed.
    """

    slug: str
    provider: str
    model: str
    display_name: str
    context_window: int
    supports_tool_use: bool
    supports_structured_output: bool
    training_data_class: str
    training_data_cutoff: str | None
    license: str
    refreshed_at: str


_CARDS_DIR = Path(__file__).parent

_REQUIRED_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {
        "provider",
        "model",
        "display_name",
        "context_window",
        "supports_tool_use",
        "supports_structured_output",
        "training_data_class",
        "license",
        "refreshed_at",
    }
)


def _parse_card_file(path: Path) -> tuple[ModelCardMetadata, str, str]:
    """Parse a single model card ``.md`` file.

    The file must begin with a YAML frontmatter block delimited by ``---``.
    The slug derived from ``provider + '__' + model`` in the frontmatter must
    match the filename stem.

    Args:
        path: Absolute path to the ``.md`` card file.

    Returns:
        A 3-tuple of ``(metadata, body, sha256_hex)`` where *body* is the
        markdown content after the frontmatter block and *sha256_hex* is the
        64-character hex digest of the full file text.

    Raises:
        ValueError: If the frontmatter is missing, malformed, has missing keys,
            or if the derived slug does not match the filename stem.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path.name}: malformed frontmatter (no closing ---)")
    fm = yaml.safe_load(parts[1])
    body = parts[2].lstrip("\n")

    missing = _REQUIRED_FRONTMATTER_KEYS - fm.keys()
    if missing:
        raise ValueError(f"{path.name}: missing frontmatter keys {sorted(missing)}")

    expected_slug = path.stem
    derived_slug = f"{fm['provider']}__{fm['model']}"
    if derived_slug != expected_slug:
        raise ValueError(
            f"{path.name}: slug mismatch — expected '{expected_slug}', derived '{derived_slug}'"
        )

    metadata = ModelCardMetadata(
        slug=expected_slug,
        provider=fm["provider"],
        model=fm["model"],
        display_name=fm["display_name"],
        context_window=int(fm["context_window"]),
        supports_tool_use=bool(fm["supports_tool_use"]),
        supports_structured_output=bool(fm["supports_structured_output"]),
        training_data_class=fm["training_data_class"],
        training_data_cutoff=fm.get("training_data_cutoff"),
        license=fm["license"],
        refreshed_at=fm["refreshed_at"],
    )
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return metadata, body, sha


@functools.lru_cache(maxsize=1)
def get_model_card_registry() -> dict[str, ModelCardMetadata]:
    """Return ``{slug: ModelCardMetadata}`` for all shipped model cards.

    Walks ``backend/model_cards/*.md`` at import time, parses each file,
    and returns a dict keyed by slug. The result is cached for the lifetime
    of the process.

    Returns:
        A mapping from card slug to :class:`ModelCardMetadata`.

    Raises:
        ValueError: If any card file fails validation or if duplicate slugs
            are detected.
    """
    cards: dict[str, ModelCardMetadata] = {}
    for path in sorted(_CARDS_DIR.glob("*.md")):
        metadata, _body, _sha = _parse_card_file(path)
        if metadata.slug in cards:
            raise ValueError(f"Duplicate card slug '{metadata.slug}'")
        cards[metadata.slug] = metadata
    return cards


@functools.lru_cache(maxsize=32)
def load_model_card_content(slug: str) -> tuple[str, str]:
    """Return ``(body, sha256_hex)`` for *slug*.

    The file is read from disk once per unique slug per process lifetime.
    Pattern mirrors :func:`backend.agent_profiles.load_profile_content`.

    Args:
        slug: One of the shipped model card slugs
            (e.g. ``"anthropic__claude-opus-4-7"``).

    Returns:
        A 2-tuple of:
        - ``body``: Markdown content after the YAML frontmatter block.
        - ``sha256_hex``: 64-character lowercase hex digest of the full file.

    Raises:
        KeyError: If *slug* does not match any known card.
    """
    if slug not in get_model_card_registry():
        raise KeyError(f"Unknown model card slug: {slug!r}")
    path = _CARDS_DIR / f"{slug}.md"
    _metadata, body, sha = _parse_card_file(path)
    return body, sha

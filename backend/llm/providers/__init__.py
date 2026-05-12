from __future__ import annotations

"""Concrete LLM provider shims backed by LiteLLM.

Each sub-module in this package wraps a single LLM provider and delegates to
:func:`litellm.acompletion` with the appropriate model-prefix and credentials.
"""

from __future__ import annotations

import pytest

from backend.agents.tools import get_tool_registry, tool_schemas

_EXPECTED_NAMES = {
    "read_file",
    "write_file",
    "edit_file",
    "run_command",
    "git_diff",
    "git_status",
    "provider_api",
    "recipe_success_check",
}


class TestGetToolRegistry:
    def test_returns_exactly_eight_tools(self) -> None:
        registry = get_tool_registry()
        assert len(registry) == 8

    def test_expected_names_present(self) -> None:
        registry = get_tool_registry()
        assert set(registry.keys()) == _EXPECTED_NAMES

    @pytest.mark.parametrize("tool_name", sorted(_EXPECTED_NAMES))
    def test_tool_has_name_attribute(self, tool_name: str) -> None:
        registry = get_tool_registry()
        tool = registry[tool_name]
        assert tool.name == tool_name

    @pytest.mark.parametrize("tool_name", sorted(_EXPECTED_NAMES))
    def test_tool_has_description(self, tool_name: str) -> None:
        registry = get_tool_registry()
        tool = registry[tool_name]
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0

    @pytest.mark.parametrize("tool_name", sorted(_EXPECTED_NAMES))
    def test_tool_has_arguments_schema(self, tool_name: str) -> None:
        registry = get_tool_registry()
        tool = registry[tool_name]
        assert isinstance(tool.arguments_schema, dict)

    @pytest.mark.parametrize("tool_name", sorted(_EXPECTED_NAMES))
    def test_arguments_schema_is_valid_json_schema(self, tool_name: str) -> None:
        registry = get_tool_registry()
        schema = registry[tool_name].arguments_schema
        # A valid JSON Schema object must be a dict with a 'type' or '$schema' or 'properties' key.
        # Pydantic generates schemas with 'type' and optionally 'properties'.
        assert "type" in schema or "properties" in schema or "$schema" in schema

    def test_each_call_returns_fresh_instance_set(self) -> None:
        registry_a = get_tool_registry()
        registry_b = get_tool_registry()
        # They should be equal in content but not the same dict object.
        assert registry_a is not registry_b
        assert set(registry_a.keys()) == set(registry_b.keys())


class TestToolSchemas:
    def test_returns_list_of_eight(self) -> None:
        schemas = tool_schemas()
        assert len(schemas) == 8

    def test_each_schema_has_required_keys(self) -> None:
        for schema in tool_schemas():
            assert "name" in schema
            assert "description" in schema
            assert "parameters" in schema

    def test_names_match_registry(self) -> None:
        schema_names = {s["name"] for s in tool_schemas()}
        assert schema_names == _EXPECTED_NAMES

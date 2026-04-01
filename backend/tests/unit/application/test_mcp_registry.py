from __future__ import annotations

from application.services.mcp_registry import (
    build_mcp_tool_name,
    expand_env_vars_in_string,
    extract_mcp_tool_display_name,
    get_mcp_display_name,
    get_mcp_prefix,
    get_tool_name_for_permission_check,
    mcp_info_from_string,
    normalize_name_for_mcp,
)


def test_normalize_name_for_mcp_replaces_invalid_characters():
    assert normalize_name_for_mcp("GitHub.com tools") == "GitHub_com_tools"


def test_normalize_name_for_mcp_collapses_claude_ai_server_prefix():
    assert normalize_name_for_mcp("claude.ai github.com") == "claude_ai_github_com"


def test_expand_env_vars_in_string_supports_defaults_and_missing_vars():
    result = expand_env_vars_in_string(
        "https://${HOST}/tool/${TOKEN:-fallback}/${MISSING}",
        env={"HOST": "example.com"},
    )

    assert result.expanded == "https://example.com/tool/fallback/${MISSING}"
    assert result.missing_vars == ["MISSING"]


def test_mcp_string_helpers_round_trip_tool_names():
    full_name = build_mcp_tool_name("github.com", "Add comment")

    assert full_name == "mcp__github_com__Add_comment"
    assert get_mcp_prefix("github.com") == "mcp__github_com__"
    assert get_mcp_display_name(full_name, "github.com") == "Add_comment"
    parts = mcp_info_from_string(full_name)
    assert parts is not None
    assert parts.server_name == "github_com"
    assert parts.tool_name == "Add_comment"


def test_get_tool_name_for_permission_check_prefers_mcp_qualified_name():
    tool = {
        "name": "Add comment",
        "mcpInfo": {"serverName": "github.com", "toolName": "Add comment"},
    }

    assert get_tool_name_for_permission_check(tool) == "mcp__github_com__Add_comment"


def test_extract_mcp_tool_display_name_strips_server_prefix_and_suffix():
    assert (
        extract_mcp_tool_display_name("github - Add comment to issue (MCP)")
        == "Add comment to issue"
    )

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

CLAUDEAI_SERVER_PREFIX = "claude.ai "
MCP_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_-]")
ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


@dataclass(frozen=True)
class ExpandedEnvValue:
    expanded: str
    missing_vars: list[str]


@dataclass(frozen=True)
class MCPNameParts:
    server_name: str
    tool_name: str | None = None


def normalize_name_for_mcp(name: str) -> str:
    normalized = MCP_NAME_PATTERN.sub("_", name)
    if name.startswith(CLAUDEAI_SERVER_PREFIX):
        normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def expand_env_vars_in_string(
    value: str,
    env: Mapping[str, str] | None = None,
) -> ExpandedEnvValue:
    source_env = os.environ if env is None else env
    missing_vars: list[str] = []

    def replace(match: re.Match[str]) -> str:
        var_content = match.group(1)
        var_name, default_value = _split_default(var_content)
        env_value = source_env.get(var_name)
        if env_value is not None:
            return env_value
        if default_value is not None:
            return default_value
        missing_vars.append(var_name)
        return match.group(0)

    expanded = ENV_VAR_PATTERN.sub(replace, value)
    return ExpandedEnvValue(expanded=expanded, missing_vars=missing_vars)


def mcp_info_from_string(tool_string: str) -> MCPNameParts | None:
    parts = tool_string.split("__")
    if len(parts) < 2 or parts[0] != "mcp" or not parts[1]:
        return None
    tool_name = "__".join(parts[2:]) if len(parts) > 2 else None
    return MCPNameParts(server_name=parts[1], tool_name=tool_name)


def get_mcp_prefix(server_name: str) -> str:
    return f"mcp__{normalize_name_for_mcp(server_name)}__"


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    return f"{get_mcp_prefix(server_name)}{normalize_name_for_mcp(tool_name)}"


def get_tool_name_for_permission_check(tool: Mapping[str, object]) -> str:
    mcp_info = tool.get("mcpInfo")
    if isinstance(mcp_info, dict):
        server_name = mcp_info.get("serverName")
        tool_name = mcp_info.get("toolName")
        if isinstance(server_name, str) and isinstance(tool_name, str):
            return build_mcp_tool_name(server_name, tool_name)
    name = tool.get("name")
    return name if isinstance(name, str) else ""


def get_mcp_display_name(full_name: str, server_name: str) -> str:
    return full_name.removeprefix(get_mcp_prefix(server_name))


def extract_mcp_tool_display_name(user_facing_name: str) -> str:
    without_suffix = re.sub(r"\s*\(MCP\)\s*$", "", user_facing_name).strip()
    dash_index = without_suffix.find(" - ")
    if dash_index != -1:
        return without_suffix[dash_index + 3 :].strip()
    return without_suffix


def _split_default(var_content: str) -> tuple[str, str | None]:
    if ":-" not in var_content:
        return var_content, None
    name, default = var_content.split(":-", 1)
    return name, default

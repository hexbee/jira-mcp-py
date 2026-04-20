from __future__ import annotations

import os
from dataclasses import dataclass

from .schemas import ISSUE_FIELDS_ALLOWLIST, SEARCH_FIELDS_ALLOWLIST, resolve_fields


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {value}")


def _read_int(name: str, default: int, *, minimum: int | None = None) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    parsed = int(value)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


def _read_float(name: str, default: float, *, minimum: float | None = None) -> float:
    value = os.getenv(name)
    if value is None:
        return default

    parsed = float(value)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


def _normalize_path(value: str, *, default: str) -> str:
    normalized = (value or default).strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/") or "/"


def _parse_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default

    parts = [item.strip() for item in value.split(",")]
    return tuple(item for item in parts if item)


@dataclass(frozen=True)
class AppConfig:
    jira_base_url: str
    jira_pat: str
    jira_rest_prefix: str
    jira_timeout_seconds: float
    jira_verify_ssl: bool
    jira_max_results: int
    jira_default_search_fields: tuple[str, ...]
    jira_default_issue_fields: tuple[str, ...]
    mcp_name: str
    mcp_host: str
    mcp_port: int
    mcp_path: str
    mcp_log_level: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        jira_base_url = _require_env("JIRA_BASE_URL").rstrip("/")
        jira_rest_prefix = _normalize_path(os.getenv("JIRA_REST_PREFIX", "/rest/api/2"), default="/rest/api/2")
        mcp_path = _normalize_path(os.getenv("MCP_PATH", "/mcp"), default="/mcp")
        search_fields = _parse_csv(
            "JIRA_DEFAULT_SEARCH_FIELDS",
            ("summary", "status", "priority", "issuetype", "project", "assignee", "updated"),
        )
        issue_fields = _parse_csv(
            "JIRA_DEFAULT_ISSUE_FIELDS",
            (
                "summary",
                "status",
                "priority",
                "issuetype",
                "project",
                "assignee",
                "reporter",
                "description",
                "labels",
                "updated",
                "created",
            ),
        )

        return cls(
            jira_base_url=jira_base_url,
            jira_pat=_require_env("JIRA_PAT"),
            jira_rest_prefix=jira_rest_prefix,
            jira_timeout_seconds=_read_float("JIRA_TIMEOUT_SECONDS", 15.0, minimum=0.1),
            jira_verify_ssl=_read_bool("JIRA_VERIFY_SSL", True),
            jira_max_results=_read_int("JIRA_MAX_RESULTS", 25, minimum=1),
            jira_default_search_fields=tuple(
                resolve_fields(
                    search_fields,
                    default_fields=search_fields,
                    allowed_fields=SEARCH_FIELDS_ALLOWLIST,
                )
            ),
            jira_default_issue_fields=tuple(
                resolve_fields(
                    issue_fields,
                    default_fields=issue_fields,
                    allowed_fields=ISSUE_FIELDS_ALLOWLIST,
                )
            ),
            mcp_name=os.getenv("MCP_NAME", "jira-readonly"),
            mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
            mcp_port=_read_int("MCP_PORT", 8000, minimum=1),
            mcp_path=mcp_path,
            mcp_log_level=os.getenv("MCP_LOG_LEVEL", "INFO").upper(),
        )

    def jira_api_url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        return f"{self.jira_base_url}{self.jira_rest_prefix}{normalized}"

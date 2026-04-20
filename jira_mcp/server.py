from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import re
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from .config import AppConfig
from .jira_client import JiraAuthError, JiraClient, JiraNotFoundError, JiraRequestError
from .schemas import (
    ISSUE_FIELDS_ALLOWLIST,
    SEARCH_FIELDS_ALLOWLIST,
    resolve_expands,
    resolve_fields,
    sanitize_issue,
    sanitize_myself,
    sanitize_search_results,
)

ISSUE_KEY_PATTERN = re.compile(r"^(?:[A-Za-z][A-Za-z0-9_]*-\d+|\d+)$")


@dataclass
class AppState:
    config: AppConfig
    jira: JiraClient


def create_server(config: AppConfig | None = None) -> FastMCP[AppState]:
    app_config = config or AppConfig.from_env()

    @asynccontextmanager
    async def lifespan(_: FastMCP[AppState]):
        jira = JiraClient(app_config)
        try:
            yield AppState(config=app_config, jira=jira)
        finally:
            await jira.aclose()

    mcp = FastMCP(
        name=app_config.mcp_name,
        instructions="Readonly Jira Data Center tools for identity checks, issue search, and issue lookup.",
        host=app_config.mcp_host,
        port=app_config.mcp_port,
        streamable_http_path=app_config.mcp_path,
        log_level=app_config.mcp_log_level,
        json_response=True,
        lifespan=lifespan,
    )

    @mcp.tool(description="Validate Jira connectivity and return the current Jira identity.", structured_output=True)
    async def whoami(ctx: Context) -> dict[str, Any]:
        state = _get_state(ctx)
        authorization_header = _get_jira_authorization(ctx)
        try:
            payload = await state.jira.get_myself(authorization_header=authorization_header)
        except (JiraAuthError, JiraNotFoundError, JiraRequestError) as exc:
            raise ValueError(str(exc)) from exc
        return sanitize_myself(payload)

    @mcp.tool(
        description="Search Jira issues with JQL. Results are paginated and restricted to a safe field allowlist.",
        structured_output=True,
    )
    async def search_issues(
        jql: str,
        start_at: int = 0,
        max_results: int | None = None,
        fields: list[str] | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        state = _get_state(ctx)
        authorization_header = _get_jira_authorization(ctx)
        cleaned_jql = jql.strip()
        if not cleaned_jql:
            raise ValueError("jql cannot be empty")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if max_results is not None and max_results < 1:
            raise ValueError("max_results must be >= 1")

        selected_fields = resolve_fields(
            fields,
            default_fields=state.config.jira_default_search_fields,
            allowed_fields=SEARCH_FIELDS_ALLOWLIST,
        )
        requested_max = max_results if max_results is not None else state.config.jira_max_results
        bounded_max_results = max(1, min(requested_max, state.config.jira_max_results))

        try:
            payload = await state.jira.search_issues(
                authorization_header=authorization_header,
                jql=cleaned_jql,
                start_at=start_at,
                max_results=bounded_max_results,
                fields=selected_fields,
            )
        except (JiraAuthError, JiraNotFoundError, JiraRequestError) as exc:
            raise ValueError(str(exc)) from exc
        return sanitize_search_results(payload, jql=cleaned_jql, selected_fields=selected_fields)

    @mcp.tool(
        description="Fetch a single Jira issue by key or numeric id. Field and expand options are intentionally restricted.",
        structured_output=True,
    )
    async def get_issue(
        issue_key: str,
        fields: list[str] | None = None,
        expand: list[str] | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        state = _get_state(ctx)
        authorization_header = _get_jira_authorization(ctx)
        cleaned_issue_key = issue_key.strip()
        if not cleaned_issue_key:
            raise ValueError("issue_key cannot be empty")
        if not ISSUE_KEY_PATTERN.fullmatch(cleaned_issue_key):
            raise ValueError("issue_key must be a Jira issue key like ABC-123 or a numeric id")

        selected_fields = resolve_fields(
            fields,
            default_fields=state.config.jira_default_issue_fields,
            allowed_fields=ISSUE_FIELDS_ALLOWLIST,
        )
        selected_expands = resolve_expands(expand)

        try:
            payload = await state.jira.get_issue(
                cleaned_issue_key,
                authorization_header=authorization_header,
                fields=selected_fields,
                expands=selected_expands,
            )
        except (JiraAuthError, JiraNotFoundError, JiraRequestError) as exc:
            raise ValueError(str(exc)) from exc
        return {
            "issue": sanitize_issue(payload, selected_fields=selected_fields, expands=selected_expands),
            "fields": selected_fields,
            "expand": selected_expands,
        }

    return mcp


def run_server() -> None:
    try:
        create_server().run(transport="streamable-http")
    except KeyboardInterrupt:
        # Suppress the expected traceback when stopping the server with Ctrl+C.
        pass


def _get_state(ctx: Context) -> AppState:
    return ctx.request_context.lifespan_context


def _get_jira_authorization(ctx: Context) -> str:
    request_context = getattr(ctx, "request_context", None)
    request = getattr(request_context, "request", None)
    headers = getattr(request, "headers", None)

    if headers is None:
        raise ValueError(
            "Authorization header is unavailable for this request. Configure it under "
            "`mcp_servers.jira.http_headers` in `~/.codex/config.toml`."
        )

    authorization_header = headers.get("authorization", "").strip()
    if not authorization_header:
        raise ValueError(
            "Missing Authorization header. Configure it under `mcp_servers.jira.http_headers` "
            "in `~/.codex/config.toml`."
        )
    if not authorization_header.lower().startswith("bearer "):
        raise ValueError("Authorization header must use the format `Bearer <jira_pat>`.")
    if not authorization_header[7:].strip():
        raise ValueError("Authorization header must include a non-empty Jira PAT.")

    return authorization_header

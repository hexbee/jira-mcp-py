from __future__ import annotations

from collections.abc import Iterable
from typing import Any

MAX_STRING_LENGTH = 2000
SEARCH_FIELDS_ALLOWLIST = {
    "assignee",
    "created",
    "issuetype",
    "labels",
    "priority",
    "project",
    "reporter",
    "resolution",
    "status",
    "summary",
    "updated",
}
ISSUE_FIELDS_ALLOWLIST = SEARCH_FIELDS_ALLOWLIST | {"description"}
ISSUE_EXPAND_ALLOWLIST = {"names", "schema"}


def resolve_fields(
    requested_fields: Iterable[str] | None,
    *,
    default_fields: tuple[str, ...],
    allowed_fields: set[str],
) -> list[str]:
    if requested_fields is None:
        fields = list(default_fields)
    else:
        fields = [field.strip() for field in requested_fields if field and field.strip()]

    unknown_fields = [field for field in fields if field not in allowed_fields]
    if unknown_fields:
        allowed = ", ".join(sorted(allowed_fields))
        invalid = ", ".join(sorted(set(unknown_fields)))
        raise ValueError(f"Unsupported fields: {invalid}. Allowed fields: {allowed}")

    if not fields:
        raise ValueError("At least one field must be requested")

    return _dedupe_preserve_order(fields)


def resolve_expands(requested_expands: Iterable[str] | None) -> list[str]:
    if requested_expands is None:
        return []

    expands = [value.strip() for value in requested_expands if value and value.strip()]
    unknown_expands = [value for value in expands if value not in ISSUE_EXPAND_ALLOWLIST]
    if unknown_expands:
        allowed = ", ".join(sorted(ISSUE_EXPAND_ALLOWLIST))
        invalid = ", ".join(sorted(set(unknown_expands)))
        raise ValueError(f"Unsupported expands: {invalid}. Allowed expands: {allowed}")

    return _dedupe_preserve_order(expands)


def sanitize_myself(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "self",
        "name",
        "key",
        "accountId",
        "displayName",
        "emailAddress",
        "active",
        "timeZone",
        "locale",
    )
    return {key: sanitize_value(payload.get(key)) for key in keys if key in payload}


def sanitize_issue(payload: dict[str, Any], *, selected_fields: list[str], expands: list[str] | None = None) -> dict[str, Any]:
    fields_payload = payload.get("fields") or {}
    issue = {
        "id": sanitize_value(payload.get("id")),
        "key": sanitize_value(payload.get("key")),
        "self": sanitize_value(payload.get("self")),
        "fields": {field: sanitize_value(fields_payload.get(field)) for field in selected_fields},
    }

    expands = expands or []
    if "names" in expands and "names" in payload:
        issue["names"] = sanitize_value(payload.get("names"))
    if "schema" in expands and "schema" in payload:
        issue["schema"] = sanitize_value(payload.get("schema"))

    return issue


def sanitize_search_results(payload: dict[str, Any], *, jql: str, selected_fields: list[str]) -> dict[str, Any]:
    issues = payload.get("issues") or []
    return {
        "jql": jql,
        "start_at": sanitize_value(payload.get("startAt")),
        "max_results": sanitize_value(payload.get("maxResults")),
        "total": sanitize_value(payload.get("total")),
        "fields": selected_fields,
        "issues": [sanitize_issue(issue, selected_fields=selected_fields) for issue in issues],
    }


def sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) <= MAX_STRING_LENGTH:
            return value
        return f"{value[:MAX_STRING_LENGTH]}... [truncated {len(value) - MAX_STRING_LENGTH} chars]"

    if isinstance(value, list):
        return [sanitize_value(item) for item in value]

    if isinstance(value, dict):
        return {str(key): sanitize_value(item) for key, item in value.items()}

    return str(value)


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered

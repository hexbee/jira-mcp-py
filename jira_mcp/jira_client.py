from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .config import AppConfig


class JiraClientError(RuntimeError):
    pass


class JiraAuthError(JiraClientError):
    pass


class JiraNotFoundError(JiraClientError):
    pass


class JiraRequestError(JiraClientError):
    pass


class JiraClient:
    def __init__(self, config: AppConfig):
        self._config = config
        self._client = httpx.AsyncClient(
            timeout=config.jira_timeout_seconds,
            verify=config.jira_verify_ssl,
            headers={
                "Accept": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_myself(self, *, authorization_header: str) -> dict[str, Any]:
        return await self._get("/myself", authorization_header=authorization_header)

    async def search_issues(
        self,
        *,
        authorization_header: str,
        jql: str,
        start_at: int,
        max_results: int,
        fields: list[str],
    ) -> dict[str, Any]:
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ",".join(fields),
        }
        return await self._get("/search", params=params, authorization_header=authorization_header)

    async def get_issue(
        self,
        issue_key: str,
        *,
        authorization_header: str,
        fields: list[str],
        expands: list[str],
    ) -> dict[str, Any]:
        params: dict[str, str] = {"fields": ",".join(fields)}
        if expands:
            params["expand"] = ",".join(expands)
        return await self._get(
            f"/issue/{quote(issue_key, safe='')}",
            params=params,
            authorization_header=authorization_header,
        )

    async def _get(
        self,
        path: str,
        *,
        authorization_header: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(
                self._config.jira_api_url(path),
                params=params,
                headers={"Authorization": authorization_header},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise JiraRequestError("Request to Jira timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise self._map_http_error(exc.response) from exc
        except httpx.HTTPError as exc:
            raise JiraRequestError(f"Request to Jira failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise JiraRequestError("Jira returned a non-JSON response") from exc

        if not isinstance(payload, dict):
            raise JiraRequestError("Unexpected Jira response format")
        return payload

    def _map_http_error(self, response: httpx.Response) -> JiraClientError:
        message = self._extract_error_message(response)
        if response.status_code in {401, 403}:
            return JiraAuthError(message or f"Jira authentication failed (HTTP {response.status_code})")
        if response.status_code == 404:
            return JiraNotFoundError(message or "Jira resource was not found")
        return JiraRequestError(message or f"Jira request failed (HTTP {response.status_code})")

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""

        messages: list[str] = []
        if isinstance(payload, dict):
            error_messages = payload.get("errorMessages")
            if isinstance(error_messages, list):
                messages.extend(str(item) for item in error_messages if item)

            errors = payload.get("errors")
            if isinstance(errors, dict):
                messages.extend(f"{key}: {value}" for key, value in errors.items() if value)

        return "; ".join(messages).strip()

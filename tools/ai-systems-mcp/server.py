#!/usr/bin/env python3
"""MCP server for creating and reading boards/cards in a WeKan instance."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from mcp.server import MCPServer


class WekanConfigError(ValueError):
    """Raised when the WeKan MCP runtime is missing required configuration."""


class WekanAPIError(RuntimeError):
    """Raised when WeKan returns an HTTP or application-level API error."""


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class WekanConfig:
    base_url: str
    api_token: str | None
    user_id: str | None
    username: str | None
    email: str | None
    password: str | None
    timeout_seconds: float
    verify_tls: bool

    @classmethod
    def from_env(cls) -> "WekanConfig":
        return cls(
            base_url=os.getenv("WEKAN_BASE_URL", "http://127.0.0.1:3000").rstrip("/"),
            api_token=os.getenv("WEKAN_API_TOKEN") or None,
            user_id=os.getenv("WEKAN_USER_ID") or None,
            username=os.getenv("WEKAN_USERNAME") or None,
            email=os.getenv("WEKAN_EMAIL") or None,
            password=os.getenv("WEKAN_PASSWORD") or None,
            timeout_seconds=float(os.getenv("WEKAN_TIMEOUT_SECONDS", "20")),
            verify_tls=_env_bool("WEKAN_VERIFY_TLS", True),
        )

    @property
    def can_authenticate(self) -> bool:
        if self.api_token and self.user_id:
            return True
        return bool((self.username or self.email) and self.password)

    def public_view(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "verify_tls": self.verify_tls,
            "has_api_token": bool(self.api_token),
            "has_user_id": bool(self.user_id),
            "has_username": bool(self.username),
            "has_email": bool(self.email),
            "has_password": bool(self.password),
            "can_authenticate": self.can_authenticate,
        }


class WekanClient:
    def __init__(self, config: WekanConfig):
        self.config = config
        self._api_token = config.api_token
        self._user_id = config.user_id

    @property
    def user_id(self) -> str | None:
        return self._user_id

    async def _login(self) -> None:
        if self._api_token and self._user_id:
            return
        if not (self.config.username or self.config.email) or not self.config.password:
            raise WekanConfigError(
                "Missing WeKan credentials. Set WEKAN_API_TOKEN + WEKAN_USER_ID, "
                "or set WEKAN_USERNAME/WEKAN_EMAIL + WEKAN_PASSWORD."
            )

        body: dict[str, str] = {"password": self.config.password}
        if self.config.email:
            body["email"] = self.config.email
        else:
            body["username"] = self.config.username or ""

        data = await self._request_without_auth("POST", "/users/login", json_body=body)
        if not isinstance(data, dict) or not data.get("token") or not data.get("id"):
            raise WekanAPIError("WeKan login response did not include id and token")

        self._api_token = str(data["token"])
        self._user_id = str(data["id"])

    async def _request_without_auth(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._send_request(
            method,
            path,
            json_body=json_body,
            headers={"Accept": "application/json"},
        )
        return self._decode_response(response, method, path)

    async def _send_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        """Send one request, retrying only safe reads on transient failures."""

        attempts = 3 if method.upper() == "GET" else 1
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=self.config.timeout_seconds,
                    verify=self.config.verify_tls,
                    # API redirects are configuration/auth failures, not a safe
                    # way to replay writes. A 301 may turn POST into GET and make
                    # the WeKan HTML landing page look like a successful result.
                    follow_redirects=False,
                ) as client:
                    response = await client.request(
                        method,
                        f"{self.config.base_url}{path}",
                        json=json_body,
                        headers=headers,
                    )
            except httpx.TransportError:
                if attempt + 1 >= attempts:
                    raise
                await asyncio.sleep(0.2 * (2**attempt))
                continue

            if response.status_code not in {502, 503, 504} or attempt + 1 >= attempts:
                return response
            await asyncio.sleep(0.2 * (2**attempt))

        raise WekanAPIError(f"{method} {path} exhausted retries")

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        for auth_attempt in range(2):
            await self._login()
            if not self._api_token:
                raise WekanConfigError("Missing WeKan API token after login")

            response = await self._send_request(
                method,
                path,
                json_body=json_body,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self._api_token}",
                },
            )
            can_relogin = bool(
                (self.config.username or self.config.email) and self.config.password
            )
            if response.status_code == 401 and auth_attempt == 0 and can_relogin:
                self._api_token = None
                self._user_id = None
                continue
            return self._decode_response(response, method, path)

        raise WekanAPIError(f"{method} {path} authentication retry failed")

    def _decode_response(self, response: httpx.Response, method: str, path: str) -> Any:
        if 300 <= response.status_code < 400:
            location = response.headers.get("location", "<missing>")
            raise WekanAPIError(
                f"{method} {path} returned unexpected HTTP {response.status_code} "
                f"redirect to {location}; verify WEKAN_BASE_URL and that the REST API is enabled"
            )

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                payload: Any = response.json()
            except ValueError as error:
                raise WekanAPIError(
                    f"{method} {path} returned invalid JSON with HTTP {response.status_code}"
                ) from error
        else:
            payload = response.text

        if response.status_code >= 400:
            reason = payload
            if isinstance(payload, dict):
                reason = payload.get("reason") or payload.get("error") or payload
            raise WekanAPIError(f"{method} {path} failed with HTTP {response.status_code}: {reason}")

        if isinstance(payload, dict) and "error" in payload and "_id" not in payload:
            reason = payload.get("reason") or payload.get("message") or payload.get("error")
            raise WekanAPIError(f"{method} {path} failed: {reason}")

        return payload


def _tool_error(error: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "error": type(error).__name__,
        "message": str(error),
    }


async def _safe_call(operation: str, func) -> dict[str, Any]:
    try:
        result = await func()
        if isinstance(result, dict):
            return {"ok": True, **result}
        return {"ok": True, operation: result}
    except Exception as error:  # noqa: BLE001 - MCP tools should return useful errors.
        return _tool_error(error)


def _clean_body(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _query(values: dict[str, Any]) -> str:
    clean = {key: value for key, value in values.items() if value not in (None, "")}
    return f"?{urlencode(clean)}" if clean else ""


def _resource_id(value: str, name: str) -> str:
    """Validate an opaque WeKan id before placing it in a REST path."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]+", value):
        raise WekanConfigError(f"{name} must be a non-empty alphanumeric WeKan id")
    return quote(value, safe="")


def _require_confirmation(confirm: bool, operation: str) -> None:
    if not confirm:
        raise WekanConfigError(
            f"{operation} is destructive; call again with confirm=true after verifying the ids"
        )


async def _default_swimlane_id(client: WekanClient, board_id: str) -> str:
    board_path = _resource_id(board_id, "board_id")
    swimlanes = await client.request("GET", f"/api/boards/{board_path}/swimlanes")
    if not isinstance(swimlanes, list) or not swimlanes:
        raise WekanAPIError(f"Board {board_id} does not have an active swimlane")
    first = swimlanes[0]
    if not isinstance(first, dict) or not first.get("_id"):
        raise WekanAPIError(f"Board {board_id} returned an invalid swimlane list")
    return str(first["_id"])


async def _visible_user_boards(client: WekanClient) -> list[Any]:
    await client._login()
    if not client.user_id:
        raise WekanConfigError("Missing WeKan user id after login")
    user_id = _resource_id(client.user_id, "user_id")
    boards = await client.request("GET", f"/api/users/{user_id}/boards")
    if not isinstance(boards, list):
        raise WekanAPIError("WeKan user boards response was not a list")
    return boards


def _server(
    config: WekanConfig | None = None,
    client: WekanClient | None = None,
) -> MCPServer:
    config = config or (client.config if client is not None else WekanConfig.from_env())
    client = client or WekanClient(config)

    server = MCPServer(
        name="wekan-mcp",
        title="WeKan Board MCP",
        description="Create and inspect boards, lists, and cards in this WeKan instance.",
        instructions=(
            "Use wekan_health_status before board work. Prefer archive_card over delete_card. "
            "Destructive tools require confirm=true. Use search_cards for paginated discovery; "
            "use member, label, comment, checklist, list, swimlane, and board lifecycle tools "
            "only within the authenticated user's WeKan permissions."
        ),
        version="0.3.0",
    )

    @server.tool()
    async def wekan_health_status() -> dict[str, Any]:
        """Check WeKan reachability and whether MCP auth is configured."""

        async def run() -> dict[str, Any]:
            app_status = await client._request_without_auth("GET", "/")
            auth_probe: dict[str, Any] | None = None
            if config.can_authenticate:
                boards = await _visible_user_boards(client)
                auth_probe = {
                    "authenticated": True,
                    "board_discovery_endpoint": "/api/users/{userId}/boards",
                    "boards_visible": len(boards),
                    "user_id": client.user_id,
                }
            return {
                "base_url": config.base_url,
                "app_reachable": isinstance(app_status, str) and len(app_status) > 0,
                "auth": config.public_view(),
                "auth_probe": auth_probe,
            }

        return await _safe_call("health", run)

    @server.tool()
    async def list_boards() -> dict[str, Any]:
        """List boards visible to the authenticated WeKan user."""

        async def run() -> dict[str, Any]:
            boards = await _visible_user_boards(client)
            return {
                "count": len(boards),
                "boards": boards,
            }

        return await _safe_call("boards", run)

    @server.tool()
    async def get_board(board_id: str) -> dict[str, Any]:
        """Read one board by id."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            board = await client.request("GET", f"/api/boards/{board_path}")
            return {"board": board}

        return await _safe_call("board", run)

    @server.tool()
    async def create_board(
        title: str,
        permission: str = "private",
        owner: str | None = None,
        color: str = "belize",
    ) -> dict[str, Any]:
        """Create a board in WeKan."""

        async def run() -> dict[str, Any]:
            if not title.strip():
                raise WekanConfigError("title is required")
            body = _clean_body(
                {
                    "title": title.strip(),
                    "permission": permission,
                    "owner": owner,
                    "color": color,
                }
            )
            created = await client.request("POST", "/api/boards", json_body=body)
            return {
                "board": created,
                "board_id": created.get("_id") if isinstance(created, dict) else None,
                "default_swimlane_id": (
                    created.get("defaultSwimlaneId") if isinstance(created, dict) else None
                ),
            }

        return await _safe_call("board", run)

    @server.tool()
    async def list_lists(board_id: str) -> dict[str, Any]:
        """List non-archived lists on a board."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            lists = await client.request("GET", f"/api/boards/{board_path}/lists")
            return {
                "count": len(lists) if isinstance(lists, list) else None,
                "lists": lists,
            }

        return await _safe_call("lists", run)

    @server.tool()
    async def list_swimlanes(board_id: str) -> dict[str, Any]:
        """List non-archived swimlanes on a board."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            swimlanes = await client.request("GET", f"/api/boards/{board_path}/swimlanes")
            return {
                "count": len(swimlanes) if isinstance(swimlanes, list) else None,
                "swimlanes": swimlanes,
            }

        return await _safe_call("swimlanes", run)

    @server.tool()
    async def create_list(
        board_id: str,
        title: str,
        swimlane_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a list on a board."""

        async def run() -> dict[str, Any]:
            if not title.strip():
                raise WekanConfigError("title is required")
            board_path = _resource_id(board_id, "board_id")
            created = await client.request(
                "POST",
                f"/api/boards/{board_path}/lists",
                json_body=_clean_body({"title": title.strip(), "swimlaneId": swimlane_id}),
            )
            return {
                "list": created,
                "list_id": created.get("_id") if isinstance(created, dict) else None,
            }

        return await _safe_call("list", run)

    @server.tool()
    async def list_cards(board_id: str, list_id: str) -> dict[str, Any]:
        """List non-archived cards in a board list."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            cards = await client.request(
                "GET",
                f"/api/boards/{board_path}/lists/{list_path}/cards",
            )
            return {
                "count": len(cards) if isinstance(cards, list) else None,
                "cards": cards,
            }

        return await _safe_call("cards", run)

    @server.tool()
    async def create_card(
        board_id: str,
        list_id: str,
        title: str,
        description: str = "",
        author_id: str | None = None,
        swimlane_id: str | None = None,
        members: list[str] | None = None,
        assignees: list[str] | None = None,
        received_at: str | None = None,
        start_at: str | None = None,
        due_at: str | None = None,
        end_at: str | None = None,
    ) -> dict[str, Any]:
        """Create a card in a board list."""

        async def run() -> dict[str, Any]:
            if not title.strip():
                raise WekanConfigError("title is required")
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            effective_author = author_id or client.user_id
            if not effective_author:
                await client._login()
                effective_author = client.user_id
            if not effective_author:
                raise WekanConfigError(
                    "author_id is required when WEKAN_USER_ID is not configured and login is unavailable"
                )
            effective_swimlane_id = swimlane_id or await _default_swimlane_id(client, board_id)

            body = _clean_body(
                {
                    "title": title.strip(),
                    "description": description,
                    "authorId": effective_author,
                    "swimlaneId": effective_swimlane_id,
                    "members": members,
                    "assignees": assignees,
                    "receivedAt": received_at,
                    "startAt": start_at,
                    "dueAt": due_at,
                    "endAt": end_at,
                }
            )
            created = await client.request(
                "POST",
                f"/api/boards/{board_path}/lists/{list_path}/cards",
                json_body=body,
            )
            return {
                "card": created,
                "card_id": created.get("_id") if isinstance(created, dict) else None,
                "author_id": effective_author,
                "swimlane_id": effective_swimlane_id,
            }

        return await _safe_call("card", run)

    @server.tool()
    async def get_card(
        card_id: str,
        board_id: str | None = None,
        list_id: str | None = None,
    ) -> dict[str, Any]:
        """Read one card, optionally requiring it to belong to a board and list."""

        async def run() -> dict[str, Any]:
            card_path = _resource_id(card_id, "card_id")
            if (board_id is None) != (list_id is None):
                raise WekanConfigError("board_id and list_id must be provided together")
            if board_id is None:
                card = await client.request("GET", f"/api/cards/{card_path}")
            else:
                board_path = _resource_id(board_id, "board_id")
                list_path = _resource_id(list_id or "", "list_id")
                card = await client.request(
                    "GET",
                    f"/api/boards/{board_path}/lists/{list_path}/cards/{card_path}",
                )
            return {"card": card}

        return await _safe_call("card", run)

    @server.tool()
    async def update_card(
        board_id: str,
        list_id: str,
        card_id: str,
        title: str | None = None,
        description: str | None = None,
        color: str | None = None,
        sort: float | None = None,
        parent_id: str | None = None,
        label_ids: list[str] | None = None,
        members: list[str] | None = None,
        assignees: list[str] | None = None,
        received_at: str | None = None,
        start_at: str | None = None,
        due_at: str | None = None,
        end_at: str | None = None,
    ) -> dict[str, Any]:
        """Update editable card fields without moving or archiving the card."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            card_path = _resource_id(card_id, "card_id")
            clean_title = title.strip() if title is not None else None
            if title is not None and not clean_title:
                raise WekanConfigError("title must not be empty")
            body = _clean_body(
                {
                    "title": clean_title,
                    "description": description,
                    "color": color,
                    "sort": sort,
                    "parentId": parent_id,
                    "labelIds": label_ids,
                    "members": members,
                    "assignees": assignees,
                    "receivedAt": received_at,
                    "startAt": start_at,
                    "dueAt": due_at,
                    "endAt": end_at,
                }
            )
            if not body:
                raise WekanConfigError("at least one card field is required")
            updated = await client.request(
                "PUT",
                f"/api/boards/{board_path}/lists/{list_path}/cards/{card_path}",
                json_body=body,
            )
            return {"card": updated, "card_id": card_id}

        return await _safe_call("card", run)

    @server.tool()
    async def move_card(
        board_id: str,
        list_id: str,
        card_id: str,
        to_list_id: str,
        to_swimlane_id: str,
        to_board_id: str | None = None,
    ) -> dict[str, Any]:
        """Move a card within a board or to another writable board."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            card_path = _resource_id(card_id, "card_id")
            _resource_id(to_list_id, "to_list_id")
            _resource_id(to_swimlane_id, "to_swimlane_id")
            if to_board_id is None or to_board_id == board_id:
                body = {"listId": to_list_id, "swimlaneId": to_swimlane_id}
            else:
                _resource_id(to_board_id, "to_board_id")
                body = {
                    "newBoardId": to_board_id,
                    "newListId": to_list_id,
                    "newSwimlaneId": to_swimlane_id,
                }
            moved = await client.request(
                "PUT",
                f"/api/boards/{board_path}/lists/{list_path}/cards/{card_path}",
                json_body=body,
            )
            return {
                "card": moved,
                "card_id": card_id,
                "to_board_id": to_board_id or board_id,
                "to_list_id": to_list_id,
                "to_swimlane_id": to_swimlane_id,
            }

        return await _safe_call("card", run)

    async def set_card_archive_state(
        board_id: str,
        list_id: str,
        card_id: str,
        action: str,
    ) -> dict[str, Any]:
        board_path = _resource_id(board_id, "board_id")
        list_path = _resource_id(list_id, "list_id")
        card_path = _resource_id(card_id, "card_id")
        changed = await client.request(
            "POST",
            f"/api/boards/{board_path}/lists/{list_path}/cards/{card_path}/{action}",
            json_body={},
        )
        return {"card": changed, "card_id": card_id, "archived": action == "archive"}

    @server.tool()
    async def archive_card(board_id: str, list_id: str, card_id: str) -> dict[str, Any]:
        """Archive a card while keeping it recoverable."""

        async def run() -> dict[str, Any]:
            return await set_card_archive_state(board_id, list_id, card_id, "archive")

        return await _safe_call("card", run)

    @server.tool()
    async def unarchive_card(board_id: str, list_id: str, card_id: str) -> dict[str, Any]:
        """Restore an archived card."""

        async def run() -> dict[str, Any]:
            return await set_card_archive_state(board_id, list_id, card_id, "unarchive")

        return await _safe_call("card", run)

    @server.tool()
    async def copy_card(
        board_id: str,
        list_id: str,
        card_id: str,
        to_list_id: str | None = None,
        to_swimlane_id: str | None = None,
        to_board_id: str | None = None,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Deep-copy a card, including its supported child data."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            card_path = _resource_id(card_id, "card_id")
            destination_board = to_board_id or board_id
            if destination_board != board_id and to_list_id is None:
                raise WekanConfigError(
                    "to_list_id is required when copying a card to another board"
                )
            _resource_id(destination_board, "to_board_id")
            if to_list_id is not None:
                _resource_id(to_list_id, "to_list_id")
            if to_swimlane_id is not None:
                _resource_id(to_swimlane_id, "to_swimlane_id")
            if position is not None and position < 0:
                raise WekanConfigError("position must be zero or greater")
            destination_swimlane = to_swimlane_id or await _default_swimlane_id(
                client, destination_board
            )
            body = _clean_body(
                {
                    "toBoardId": destination_board,
                    "toListId": to_list_id or list_id,
                    "toSwimlaneId": destination_swimlane,
                    "position": position,
                }
            )
            copied = await client.request(
                "POST",
                f"/api/boards/{board_path}/lists/{list_path}/cards/{card_path}/copy",
                json_body=body,
            )
            return {
                "card": copied,
                "card_id": copied.get("_id") if isinstance(copied, dict) else None,
            }

        return await _safe_call("card", run)

    @server.tool()
    async def delete_card(
        board_id: str,
        list_id: str,
        card_id: str,
        confirm: bool = False,
        author_id: str | None = None,
    ) -> dict[str, Any]:
        """Permanently delete a card and its child data. Requires confirm=true."""

        async def run() -> dict[str, Any]:
            _require_confirmation(confirm, "delete_card")
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            card_path = _resource_id(card_id, "card_id")
            effective_author = author_id or client.user_id
            deleted = await client.request(
                "DELETE",
                f"/api/boards/{board_path}/lists/{list_path}/cards/{card_path}",
                json_body=_clean_body({"authorId": effective_author}),
            )
            return {"card": deleted, "card_id": card_id, "deleted": True}

        return await _safe_call("card", run)

    @server.tool()
    async def list_users() -> dict[str, Any]:
        """List WeKan user ids and usernames visible to the authenticated user."""

        async def run() -> dict[str, Any]:
            users = await client.request("GET", "/api/users")
            return {"count": len(users) if isinstance(users, list) else None, "users": users}

        return await _safe_call("users", run)

    @server.tool()
    async def list_board_members(board_id: str) -> dict[str, Any]:
        """List board membership records and role flags."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            board = await client.request("GET", f"/api/boards/{board_path}")
            members = board.get("members", []) if isinstance(board, dict) else []
            return {"count": len(members), "members": members}

        return await _safe_call("members", run)

    @server.tool()
    async def add_board_member(
        board_id: str,
        user_id: str,
        role: str = "normal",
    ) -> dict[str, Any]:
        """Add or reactivate a board member with a named WeKan role."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            user_path = _resource_id(user_id, "user_id")
            added = await client.request(
                "POST",
                f"/api/boards/{board_path}/members/{user_path}/add",
                json_body={"action": "add", "role": role},
            )
            return {"member": added, "board_id": board_id, "user_id": user_id, "role": role}

        return await _safe_call("member", run)

    @server.tool()
    async def set_board_member_role(
        board_id: str,
        user_id: str,
        role: str,
    ) -> dict[str, Any]:
        """Change an active board member's named role."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            user_path = _resource_id(user_id, "user_id")
            changed = await client.request(
                "POST",
                f"/api/boards/{board_path}/members/{user_path}",
                json_body={"role": role},
            )
            return {
                "member": changed,
                "board_id": board_id,
                "user_id": user_id,
                "role": role,
            }

        return await _safe_call("member", run)

    @server.tool()
    async def remove_board_member(
        board_id: str,
        user_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Deactivate a board member. Requires confirm=true."""

        async def run() -> dict[str, Any]:
            _require_confirmation(confirm, "remove_board_member")
            board_path = _resource_id(board_id, "board_id")
            user_path = _resource_id(user_id, "user_id")
            removed = await client.request(
                "POST",
                f"/api/boards/{board_path}/members/{user_path}/remove",
                json_body={"action": "remove"},
            )
            return {"member": removed, "board_id": board_id, "user_id": user_id}

        return await _safe_call("member", run)

    @server.tool()
    async def list_labels(board_id: str) -> dict[str, Any]:
        """List labels configured on a board."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            board = await client.request("GET", f"/api/boards/{board_path}")
            labels = board.get("labels", []) if isinstance(board, dict) else []
            return {"count": len(labels), "labels": labels}

        return await _safe_call("labels", run)

    @server.tool()
    async def create_label(board_id: str, name: str, color: str) -> dict[str, Any]:
        """Create a board label, or return the existing matching label id."""

        async def run() -> dict[str, Any]:
            if not name.strip():
                raise WekanConfigError("name is required")
            board_path = _resource_id(board_id, "board_id")
            created = await client.request(
                "PUT",
                f"/api/boards/{board_path}/labels",
                json_body={"label": {"name": name.strip(), "color": color}},
            )
            label_id = created.get("_id") if isinstance(created, dict) else created
            return {"label": created, "label_id": label_id}

        return await _safe_call("label", run)

    @server.tool()
    async def update_label(
        board_id: str,
        label_id: str,
        name: str | None = None,
        color: str | None = None,
    ) -> dict[str, Any]:
        """Update a board label's name and/or color."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            label_path = _resource_id(label_id, "label_id")
            clean_name = name.strip() if name is not None else None
            if name is not None and not clean_name:
                raise WekanConfigError("name must not be empty")
            body = _clean_body({"name": clean_name, "color": color})
            if not body:
                raise WekanConfigError("name or color is required")
            updated = await client.request(
                "PUT",
                f"/api/boards/{board_path}/labels/{label_path}",
                json_body=body,
            )
            return {"label": updated, "label_id": label_id}

        return await _safe_call("label", run)

    @server.tool()
    async def delete_label(
        board_id: str,
        label_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Delete a board label and remove it from cards. Requires confirm=true."""

        async def run() -> dict[str, Any]:
            _require_confirmation(confirm, "delete_label")
            board_path = _resource_id(board_id, "board_id")
            label_path = _resource_id(label_id, "label_id")
            deleted = await client.request(
                "DELETE",
                f"/api/boards/{board_path}/labels/{label_path}",
                json_body={},
            )
            return {"label": deleted, "label_id": label_id, "deleted": True}

        return await _safe_call("label", run)

    @server.tool()
    async def set_card_labels(
        board_id: str,
        card_ids: list[str],
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Atomically add/remove labels across one or more cards."""

        async def run() -> dict[str, Any]:
            if not card_ids:
                raise WekanConfigError("card_ids must not be empty")
            if not add_label_ids and not remove_label_ids:
                raise WekanConfigError("add_label_ids or remove_label_ids is required")
            for index, card_id in enumerate(card_ids):
                _resource_id(card_id, f"card_ids[{index}]")
            board_path = _resource_id(board_id, "board_id")
            changed = await client.request(
                "POST",
                f"/api/boards/{board_path}/cards/labels",
                json_body={
                    "cardIds": card_ids,
                    "addLabelIds": add_label_ids or [],
                    "removeLabelIds": remove_label_ids or [],
                },
            )
            return {"cards": changed}

        return await _safe_call("labels", run)

    @server.tool()
    async def list_comments(board_id: str, card_id: str) -> dict[str, Any]:
        """List comments on a card."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            card_path = _resource_id(card_id, "card_id")
            comments = await client.request(
                "GET", f"/api/boards/{board_path}/cards/{card_path}/comments"
            )
            return {
                "count": len(comments) if isinstance(comments, list) else None,
                "comments": comments,
            }

        return await _safe_call("comments", run)

    @server.tool()
    async def get_comment(board_id: str, card_id: str, comment_id: str) -> dict[str, Any]:
        """Read one card comment."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            card_path = _resource_id(card_id, "card_id")
            comment_path = _resource_id(comment_id, "comment_id")
            comment = await client.request(
                "GET",
                f"/api/boards/{board_path}/cards/{card_path}/comments/{comment_path}",
            )
            return {"comment": comment}

        return await _safe_call("comment", run)

    @server.tool()
    async def create_comment(board_id: str, card_id: str, comment: str) -> dict[str, Any]:
        """Add a non-empty comment to a card."""

        async def run() -> dict[str, Any]:
            clean_comment = comment.strip()
            if not clean_comment:
                raise WekanConfigError("comment is required")
            board_path = _resource_id(board_id, "board_id")
            card_path = _resource_id(card_id, "card_id")
            created = await client.request(
                "POST",
                f"/api/boards/{board_path}/cards/{card_path}/comments",
                json_body={"comment": clean_comment},
            )
            return {
                "comment": created,
                "comment_id": created.get("_id") if isinstance(created, dict) else None,
            }

        return await _safe_call("comment", run)

    @server.tool()
    async def delete_comment(
        board_id: str,
        card_id: str,
        comment_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Delete a comment when permitted. Requires confirm=true."""

        async def run() -> dict[str, Any]:
            _require_confirmation(confirm, "delete_comment")
            board_path = _resource_id(board_id, "board_id")
            card_path = _resource_id(card_id, "card_id")
            comment_path = _resource_id(comment_id, "comment_id")
            deleted = await client.request(
                "DELETE",
                f"/api/boards/{board_path}/cards/{card_path}/comments/{comment_path}",
                json_body={},
            )
            return {"comment": deleted, "comment_id": comment_id, "deleted": True}

        return await _safe_call("comment", run)

    @server.tool()
    async def list_checklists(board_id: str, card_id: str) -> dict[str, Any]:
        """List checklists on a card."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            card_path = _resource_id(card_id, "card_id")
            checklists = await client.request(
                "GET", f"/api/boards/{board_path}/cards/{card_path}/checklists"
            )
            return {
                "count": len(checklists) if isinstance(checklists, list) else None,
                "checklists": checklists,
            }

        return await _safe_call("checklists", run)

    @server.tool()
    async def get_checklist(
        board_id: str,
        card_id: str,
        checklist_id: str,
    ) -> dict[str, Any]:
        """Read one checklist including its items."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            card_path = _resource_id(card_id, "card_id")
            checklist_path = _resource_id(checklist_id, "checklist_id")
            checklist = await client.request(
                "GET",
                f"/api/boards/{board_path}/cards/{card_path}/checklists/{checklist_path}",
            )
            return {"checklist": checklist}

        return await _safe_call("checklist", run)

    @server.tool()
    async def create_checklist(
        board_id: str,
        card_id: str,
        title: str,
        items: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a checklist and optional initial items."""

        async def run() -> dict[str, Any]:
            clean_title = title.strip()
            if not clean_title:
                raise WekanConfigError("title is required")
            clean_items = [item.strip() for item in (items or []) if item.strip()]
            board_path = _resource_id(board_id, "board_id")
            card_path = _resource_id(card_id, "card_id")
            created = await client.request(
                "POST",
                f"/api/boards/{board_path}/cards/{card_path}/checklists",
                json_body={"title": clean_title, "items": clean_items},
            )
            return {
                "checklist": created,
                "checklist_id": created.get("_id") if isinstance(created, dict) else None,
            }

        return await _safe_call("checklist", run)

    @server.tool()
    async def delete_checklist(
        board_id: str,
        card_id: str,
        checklist_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Delete a checklist and its items. Requires confirm=true."""

        async def run() -> dict[str, Any]:
            _require_confirmation(confirm, "delete_checklist")
            board_path = _resource_id(board_id, "board_id")
            card_path = _resource_id(card_id, "card_id")
            checklist_path = _resource_id(checklist_id, "checklist_id")
            deleted = await client.request(
                "DELETE",
                f"/api/boards/{board_path}/cards/{card_path}/checklists/{checklist_path}",
                json_body={},
            )
            return {"checklist": deleted, "checklist_id": checklist_id, "deleted": True}

        return await _safe_call("checklist", run)

    @server.tool()
    async def get_list(board_id: str, list_id: str) -> dict[str, Any]:
        """Read one active list."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            value = await client.request("GET", f"/api/boards/{board_path}/lists/{list_path}")
            return {"list": value}

        return await _safe_call("list", run)

    @server.tool()
    async def update_list(
        board_id: str,
        list_id: str,
        title: str | None = None,
        color: str | None = None,
        starred: bool | None = None,
        wip_limit: int | None = None,
    ) -> dict[str, Any]:
        """Update list title, color, starred state, or WIP limit."""

        async def run() -> dict[str, Any]:
            clean_title = title.strip() if title is not None else None
            if title is not None and not clean_title:
                raise WekanConfigError("title must not be empty")
            if wip_limit is not None and wip_limit < 0:
                raise WekanConfigError("wip_limit must be zero or greater")
            wip_limit_body = None
            if wip_limit is not None:
                # Lists.wipLimit is an object in WeKan's persisted schema. Keep
                # the MCP input convenient: zero disables the limit while a
                # positive value enables a hard limit.
                wip_limit_body = {
                    "value": max(1, wip_limit),
                    "enabled": wip_limit > 0,
                    "soft": False,
                }
            body = _clean_body(
                {
                    "title": clean_title,
                    "color": color,
                    "starred": starred,
                    "wipLimit": wip_limit_body,
                }
            )
            if not body:
                raise WekanConfigError("at least one list field is required")
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            value = await client.request(
                "PUT", f"/api/boards/{board_path}/lists/{list_path}", json_body=body
            )
            return {"list": value, "list_id": list_id}

        return await _safe_call("list", run)

    async def transfer_list(
        action: str,
        board_id: str,
        list_id: str,
        to_board_id: str | None,
        to_swimlane_id: str | None,
        position: int | None,
        title: str | None,
    ) -> dict[str, Any]:
        board_path = _resource_id(board_id, "board_id")
        list_path = _resource_id(list_id, "list_id")
        if to_board_id is not None:
            _resource_id(to_board_id, "to_board_id")
        if to_swimlane_id is not None:
            _resource_id(to_swimlane_id, "to_swimlane_id")
        if position is not None and position < 0:
            raise WekanConfigError("position must be zero or greater")
        clean_title = title.strip() if title is not None else None
        if title is not None and not clean_title:
            raise WekanConfigError("title must not be empty")
        body = _clean_body(
            {
                "toBoardId": to_board_id,
                "toSwimlaneId": to_swimlane_id,
                "position": position,
                "title": clean_title,
            }
        )
        value = await client.request(
            "POST", f"/api/boards/{board_path}/lists/{list_path}/{action}", json_body=body
        )
        resulting_id = value.get("_id") if isinstance(value, dict) else None
        return {"list": value, "list_id": resulting_id or list_id, "action": action}

    @server.tool()
    async def copy_list(
        board_id: str,
        list_id: str,
        to_board_id: str | None = None,
        to_swimlane_id: str | None = None,
        position: int | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Deep-copy a list and its cards."""

        async def run() -> dict[str, Any]:
            return await transfer_list(
                "copy", board_id, list_id, to_board_id, to_swimlane_id, position, title
            )

        return await _safe_call("list", run)

    @server.tool()
    async def move_list(
        board_id: str,
        list_id: str,
        to_board_id: str | None = None,
        to_swimlane_id: str | None = None,
        position: int | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Move/reposition a list and its cards."""

        async def run() -> dict[str, Any]:
            return await transfer_list(
                "move", board_id, list_id, to_board_id, to_swimlane_id, position, title
            )

        return await _safe_call("list", run)

    @server.tool()
    async def delete_list(
        board_id: str,
        list_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Soft-delete a list and cascade its cards. Requires confirm=true."""

        async def run() -> dict[str, Any]:
            _require_confirmation(confirm, "delete_list")
            board_path = _resource_id(board_id, "board_id")
            list_path = _resource_id(list_id, "list_id")
            value = await client.request(
                "DELETE", f"/api/boards/{board_path}/lists/{list_path}", json_body={}
            )
            return {"list": value, "list_id": list_id, "deleted": True, "soft_delete": True}

        return await _safe_call("list", run)

    @server.tool()
    async def get_swimlane(board_id: str, swimlane_id: str) -> dict[str, Any]:
        """Read one active swimlane."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            swimlane_path = _resource_id(swimlane_id, "swimlane_id")
            value = await client.request(
                "GET", f"/api/boards/{board_path}/swimlanes/{swimlane_path}"
            )
            return {"swimlane": value}

        return await _safe_call("swimlane", run)

    @server.tool()
    async def create_swimlane(
        board_id: str,
        title: str,
        sort: float | None = None,
    ) -> dict[str, Any]:
        """Create a swimlane."""

        async def run() -> dict[str, Any]:
            clean_title = title.strip()
            if not clean_title:
                raise WekanConfigError("title is required")
            board_path = _resource_id(board_id, "board_id")
            value = await client.request(
                "POST",
                f"/api/boards/{board_path}/swimlanes",
                json_body=_clean_body({"title": clean_title, "sort": sort}),
            )
            return {
                "swimlane": value,
                "swimlane_id": value.get("_id") if isinstance(value, dict) else None,
            }

        return await _safe_call("swimlane", run)

    @server.tool()
    async def update_swimlane(board_id: str, swimlane_id: str, title: str) -> dict[str, Any]:
        """Rename a swimlane."""

        async def run() -> dict[str, Any]:
            clean_title = title.strip()
            if not clean_title:
                raise WekanConfigError("title is required")
            board_path = _resource_id(board_id, "board_id")
            swimlane_path = _resource_id(swimlane_id, "swimlane_id")
            value = await client.request(
                "PUT",
                f"/api/boards/{board_path}/swimlanes/{swimlane_path}",
                json_body={"title": clean_title},
            )
            return {"swimlane": value, "swimlane_id": swimlane_id}

        return await _safe_call("swimlane", run)

    async def transfer_swimlane(
        action: str,
        board_id: str,
        swimlane_id: str,
        to_board_id: str | None,
        position: int | None,
        title: str | None,
    ) -> dict[str, Any]:
        board_path = _resource_id(board_id, "board_id")
        swimlane_path = _resource_id(swimlane_id, "swimlane_id")
        value = await client.request(
            "POST",
            f"/api/boards/{board_path}/swimlanes/{swimlane_path}/{action}",
            json_body=_clean_body(
                {"toBoardId": to_board_id, "position": position, "title": title}
            ),
        )
        resulting_id = value.get("_id") if isinstance(value, dict) else None
        return {
            "swimlane": value,
            "swimlane_id": resulting_id or swimlane_id,
            "action": action,
        }

    @server.tool()
    async def copy_swimlane(
        board_id: str,
        swimlane_id: str,
        to_board_id: str | None = None,
        position: int | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Deep-copy a swimlane, its lists, and cards."""

        async def run() -> dict[str, Any]:
            return await transfer_swimlane(
                "copy", board_id, swimlane_id, to_board_id, position, title
            )

        return await _safe_call("swimlane", run)

    @server.tool()
    async def move_swimlane(
        board_id: str,
        swimlane_id: str,
        to_board_id: str | None = None,
        position: int | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Move/reposition a swimlane and all child data."""

        async def run() -> dict[str, Any]:
            return await transfer_swimlane(
                "move", board_id, swimlane_id, to_board_id, position, title
            )

        return await _safe_call("swimlane", run)

    @server.tool()
    async def delete_swimlane(
        board_id: str,
        swimlane_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Delete a swimlane and cascade child data. Requires confirm=true."""

        async def run() -> dict[str, Any]:
            _require_confirmation(confirm, "delete_swimlane")
            board_path = _resource_id(board_id, "board_id")
            swimlane_path = _resource_id(swimlane_id, "swimlane_id")
            value = await client.request(
                "DELETE",
                f"/api/boards/{board_path}/swimlanes/{swimlane_path}",
                json_body={},
            )
            return {"swimlane": value, "swimlane_id": swimlane_id, "deleted": True}

        return await _safe_call("swimlane", run)

    @server.tool()
    async def update_board(board_id: str, title: str) -> dict[str, Any]:
        """Rename a board."""

        async def run() -> dict[str, Any]:
            clean_title = title.strip()
            if not clean_title:
                raise WekanConfigError("title is required")
            board_path = _resource_id(board_id, "board_id")
            value = await client.request(
                "PUT", f"/api/boards/{board_path}/title", json_body={"title": clean_title}
            )
            return {"board": value, "board_id": board_id}

        return await _safe_call("board", run)

    @server.tool()
    async def copy_board(board_id: str, title: str | None = None) -> dict[str, Any]:
        """Deep-copy a board."""

        async def run() -> dict[str, Any]:
            board_path = _resource_id(board_id, "board_id")
            value = await client.request(
                "POST",
                f"/api/boards/{board_path}/copy",
                json_body=_clean_body({"title": title.strip() if title else None}),
            )
            board_copy_id = value.get("_id") if isinstance(value, dict) else value
            return {"board": value, "board_id": board_copy_id}

        return await _safe_call("board", run)

    @server.tool()
    async def delete_board(board_id: str, confirm: bool = False) -> dict[str, Any]:
        """Permanently delete a board and child data. Requires confirm=true."""

        async def run() -> dict[str, Any]:
            _require_confirmation(confirm, "delete_board")
            board_path = _resource_id(board_id, "board_id")
            value = await client.request(
                "DELETE", f"/api/boards/{board_path}", json_body={}
            )
            return {"board": value, "board_id": board_id, "deleted": True}

        return await _safe_call("board", run)

    @server.tool()
    async def search_cards(
        query: str | None = None,
        board_id: str | None = None,
        list_id: str | None = None,
        swimlane_id: str | None = None,
        member_id: str | None = None,
        assignee_id: str | None = None,
        label_id: str | None = None,
        archived: bool = False,
        due_from: str | None = None,
        due_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search visible cards with server-side filters and pagination."""

        async def run() -> dict[str, Any]:
            if limit < 1 or limit > 100:
                raise WekanConfigError("limit must be between 1 and 100")
            if offset < 0 or offset > 10000:
                raise WekanConfigError("offset must be between 0 and 10000")
            for value, name in (
                (board_id, "board_id"),
                (list_id, "list_id"),
                (swimlane_id, "swimlane_id"),
                (member_id, "member_id"),
                (assignee_id, "assignee_id"),
                (label_id, "label_id"),
            ):
                if value is not None:
                    _resource_id(value, name)
            params = {
                "query": query.strip() if query else None,
                "boardId": board_id,
                "listId": list_id,
                "swimlaneId": swimlane_id,
                "memberId": member_id,
                "assigneeId": assignee_id,
                "labelId": label_id,
                "archived": str(archived).lower(),
                "dueFrom": due_from,
                "dueTo": due_to,
                "limit": limit,
                "offset": offset,
            }
            result = await client.request("GET", f"/api/search/cards{_query(params)}")
            return {"search": result}

        return await _safe_call("search", run)

    @server.resource(
        "wekan://config",
        name="WeKan MCP Config",
        description="Safe view of the WeKan MCP runtime configuration.",
        mime_type="application/json",
    )
    def wekan_config() -> str:
        """Read runtime configuration without exposing tokens or passwords."""
        return json.dumps(config.public_view(), ensure_ascii=False, indent=2)

    @server.resource(
        "wekan://quickstart",
        name="WeKan MCP Quickstart",
        description="How to use the WeKan board/card tools.",
        mime_type="text/markdown",
    )
    def quickstart() -> str:
        """Read short usage notes."""
        return (
            "# WeKan MCP\n\n"
            "Set `WEKAN_BASE_URL` and either `WEKAN_API_TOKEN` + `WEKAN_USER_ID`, "
            "or `WEKAN_USERNAME`/`WEKAN_EMAIL` + `WEKAN_PASSWORD`. Call "
            "`wekan_health_status`, then use the board/card collaboration tools. "
            "Permanent delete and membership-removal tools require `confirm=true`.\n"
        )

    @server.prompt()
    def board_planning_prompt(goal: str) -> str:
        """Create a concise prompt for turning a project goal into WeKan cards."""
        return (
            "Turn this project goal into a practical WeKan board plan. Return the "
            "board title, list names, and card titles/descriptions.\n\n"
            f"Goal:\n{goal}"
        )

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the WeKan MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP transport to use. Defaults to stdio.",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8000")))
    parser.add_argument(
        "--streamable-http-path",
        default=os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp"),
        help="Path for streamable HTTP transport. Defaults to /mcp.",
    )
    parser.add_argument(
        "--stateful-http",
        action="store_true",
        help="Require MCP clients to preserve session ids for streamable HTTP.",
    )
    args = parser.parse_args()

    try:
        server = _server()
    except WekanConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.transport == "stdio":
        server.run(transport="stdio")
    elif args.transport == "sse":
        server.run(transport="sse", host=args.host, port=args.port)
    else:
        stateless_http = _env_bool("MCP_STATELESS_HTTP", True) and not args.stateful_http
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path=args.streamable_http_path,
            stateless_http=stateless_http,
        )


if __name__ == "__main__":
    main()

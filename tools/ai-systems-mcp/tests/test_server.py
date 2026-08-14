from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock

import httpx


SERVER_FILE = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("wekan_mcp_server_tests", SERVER_FILE)
assert SPEC and SPEC.loader
SERVER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


FOUNDATION_TOOLS = [
    "wekan_health_status",
    "list_boards",
    "get_board",
    "create_board",
    "list_lists",
    "list_swimlanes",
    "create_list",
    "list_cards",
    "create_card",
]
PHASE_1_CARD_TOOLS = [
    "get_card",
    "update_card",
    "move_card",
    "archive_card",
    "unarchive_card",
    "copy_card",
    "delete_card",
]
PHASE_2_COLLABORATION_TOOLS = [
    "list_users",
    "list_board_members",
    "add_board_member",
    "set_board_member_role",
    "remove_board_member",
    "list_labels",
    "create_label",
    "update_label",
    "delete_label",
    "set_card_labels",
    "list_comments",
    "get_comment",
    "create_comment",
    "delete_comment",
    "list_checklists",
    "get_checklist",
    "create_checklist",
    "delete_checklist",
]
PHASE_3_STRUCTURE_TOOLS = [
    "get_list",
    "update_list",
    "copy_list",
    "move_list",
    "delete_list",
    "get_swimlane",
    "create_swimlane",
    "update_swimlane",
    "copy_swimlane",
    "move_swimlane",
    "delete_swimlane",
    "update_board",
    "copy_board",
    "delete_board",
]
PHASE_4_SEARCH_TOOLS = ["search_cards"]
ALL_PHASE_TOOLS = [
    FOUNDATION_TOOLS,
    PHASE_1_CARD_TOOLS,
    PHASE_2_COLLABORATION_TOOLS,
    PHASE_3_STRUCTURE_TOOLS,
    PHASE_4_SEARCH_TOOLS,
]


class FakeWekanClient:
    def __init__(self) -> None:
        self.config = SERVER.WekanConfig(
            base_url="https://wekan.invalid",
            api_token="token",
            user_id="user1",
            username=None,
            email=None,
            password=None,
            timeout_seconds=1,
            verify_tls=True,
        )
        self.user_id = "user1"
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []
        self.responses: list[object] = []

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
    ) -> object:
        self.calls.append((method, path, json_body))
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return {"_id": "result1"}

    async def _request_without_auth(self, *_args, **_kwargs) -> str:
        return "ok"

    async def _login(self) -> None:
        return None


class WekanMcpToolTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = FakeWekanClient()
        self.server = SERVER._server(client=self.client)

    async def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = await self.server.call_tool(name, arguments)
        assert result.structured_content is not None
        return result.structured_content

    async def test_tool_manifest_contains_every_phase_in_order(self) -> None:
        tools = await self.server.list_tools()
        expected = [name for phase in ALL_PHASE_TOOLS for name in phase]
        self.assertEqual([tool.name for tool in tools], expected)
        self.assertEqual([len(phase) for phase in ALL_PHASE_TOOLS], [9, 7, 18, 14, 1])
        self.assertEqual(len(expected), 49)
        self.assertEqual(len(set(expected)), 49)

    async def test_foundation_route_contracts(self) -> None:
        self.client.responses = [
            [],
            [],
            {"_id": "board1"},
            {"_id": "board2", "defaultSwimlaneId": "swim2"},
            [],
            [],
            {"_id": "list2"},
            [],
            [{"_id": "swim1"}],
            {"_id": "card1"},
        ]
        await self.call("wekan_health_status", {})
        await self.call("list_boards", {})
        await self.call("get_board", {"board_id": "board1"})
        await self.call("create_board", {"title": "Roadmap"})
        await self.call("list_lists", {"board_id": "board1"})
        await self.call("list_swimlanes", {"board_id": "board1"})
        await self.call("create_list", {"board_id": "board1", "title": "Todo"})
        await self.call("list_cards", {"board_id": "board1", "list_id": "list1"})
        await self.call(
            "create_card",
            {"board_id": "board1", "list_id": "list1", "title": "Ship it"},
        )
        self.assertEqual(
            [call[:2] for call in self.client.calls],
            [
                ("GET", "/api/users/user1/boards"),
                ("GET", "/api/users/user1/boards"),
                ("GET", "/api/boards/board1"),
                ("POST", "/api/boards"),
                ("GET", "/api/boards/board1/lists"),
                ("GET", "/api/boards/board1/swimlanes"),
                ("POST", "/api/boards/board1/lists"),
                ("GET", "/api/boards/board1/lists/list1/cards"),
                ("GET", "/api/boards/board1/swimlanes"),
                ("POST", "/api/boards/board1/lists/list1/cards"),
            ],
        )

    async def test_get_card_supports_unscoped_and_scoped_routes(self) -> None:
        await self.call("get_card", {"card_id": "card1"})
        await self.call(
            "get_card",
            {"board_id": "board1", "list_id": "list1", "card_id": "card1"},
        )
        self.assertEqual(self.client.calls[0][:2], ("GET", "/api/cards/card1"))
        self.assertEqual(
            self.client.calls[1][:2],
            ("GET", "/api/boards/board1/lists/list1/cards/card1"),
        )

    async def test_get_card_rejects_half_scoped_ids(self) -> None:
        result = await self.call("get_card", {"board_id": "board1", "card_id": "card1"})
        self.assertFalse(result["ok"])
        self.assertIn("provided together", str(result["message"]))
        self.assertEqual(self.client.calls, [])

    async def test_update_card_preserves_empty_arrays_and_description(self) -> None:
        result = await self.call(
            "update_card",
            {
                "board_id": "board1",
                "list_id": "list1",
                "card_id": "card1",
                "description": "",
                "label_ids": [],
                "members": [],
                "assignees": [],
                "sort": 0,
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            self.client.calls[-1],
            (
                "PUT",
                "/api/boards/board1/lists/list1/cards/card1",
                {
                    "description": "",
                    "sort": 0.0,
                    "labelIds": [],
                    "members": [],
                    "assignees": [],
                },
            ),
        )

    async def test_move_card_uses_same_board_and_cross_board_contracts(self) -> None:
        await self.call(
            "move_card",
            {
                "board_id": "board1",
                "list_id": "list1",
                "card_id": "card1",
                "to_list_id": "list2",
                "to_swimlane_id": "swim2",
            },
        )
        await self.call(
            "move_card",
            {
                "board_id": "board1",
                "list_id": "list1",
                "card_id": "card1",
                "to_board_id": "board2",
                "to_list_id": "list2",
                "to_swimlane_id": "swim2",
            },
        )
        self.assertEqual(
            self.client.calls[0][2], {"listId": "list2", "swimlaneId": "swim2"}
        )
        self.assertEqual(
            self.client.calls[1][2],
            {
                "newBoardId": "board2",
                "newListId": "list2",
                "newSwimlaneId": "swim2",
            },
        )

    async def test_archive_and_unarchive_use_explicit_routes(self) -> None:
        await self.call(
            "archive_card", {"board_id": "board1", "list_id": "list1", "card_id": "card1"}
        )
        await self.call(
            "unarchive_card",
            {"board_id": "board1", "list_id": "list1", "card_id": "card1"},
        )
        self.assertTrue(self.client.calls[0][1].endswith("/card1/archive"))
        self.assertTrue(self.client.calls[1][1].endswith("/card1/unarchive"))

    async def test_copy_card_uses_default_swimlane(self) -> None:
        self.client.responses = [[{"_id": "swim1"}], {"_id": "copy1"}]
        result = await self.call(
            "copy_card",
            {"board_id": "board1", "list_id": "list1", "card_id": "card1"},
        )
        self.assertEqual(result["card_id"], "copy1")
        self.assertEqual(self.client.calls[1][2]["toSwimlaneId"], "swim1")

    async def test_copy_card_requires_a_destination_list_across_boards(self) -> None:
        result = await self.call(
            "copy_card",
            {
                "board_id": "board1",
                "list_id": "list1",
                "card_id": "card1",
                "to_board_id": "board2",
            },
        )
        self.assertFalse(result["ok"])
        self.assertIn("to_list_id is required", str(result["message"]))
        self.assertEqual(self.client.calls, [])

    async def test_delete_card_requires_confirmation(self) -> None:
        preview = await self.call(
            "delete_card",
            {"board_id": "board1", "list_id": "list1", "card_id": "card1"},
        )
        self.assertFalse(preview["ok"])
        self.assertIn("confirm=true", str(preview["message"]))
        self.assertEqual(self.client.calls, [])

        deleted = await self.call(
            "delete_card",
            {
                "board_id": "board1",
                "list_id": "list1",
                "card_id": "card1",
                "confirm": True,
            },
        )
        self.assertTrue(deleted["deleted"])
        self.assertEqual(self.client.calls[-1][0], "DELETE")

    async def test_every_destructive_tool_requires_confirmation(self) -> None:
        cases = [
            (
                "delete_card",
                {"board_id": "board1", "list_id": "list1", "card_id": "card1"},
            ),
            ("remove_board_member", {"board_id": "board1", "user_id": "user2"}),
            ("delete_label", {"board_id": "board1", "label_id": "label1"}),
            (
                "delete_comment",
                {"board_id": "board1", "card_id": "card1", "comment_id": "comment1"},
            ),
            (
                "delete_checklist",
                {"board_id": "board1", "card_id": "card1", "checklist_id": "check1"},
            ),
            ("delete_list", {"board_id": "board1", "list_id": "list1"}),
            (
                "delete_swimlane",
                {"board_id": "board1", "swimlane_id": "swim1"},
            ),
            ("delete_board", {"board_id": "board1"}),
        ]
        for name, arguments in cases:
            with self.subTest(tool=name):
                result = await self.call(name, arguments)
                self.assertFalse(result["ok"])
                self.assertIn("confirm=true", str(result["message"]))
        self.assertEqual(self.client.calls, [])

    async def test_phase_2_read_routes(self) -> None:
        self.client.responses = [
            [],
            {"members": [{"userId": "user1"}]},
            {"labels": [{"_id": "label1"}]},
            [],
            {"_id": "comment1"},
            [],
            {"_id": "check1"},
        ]
        await self.call("list_users", {})
        await self.call("list_board_members", {"board_id": "board1"})
        await self.call("list_labels", {"board_id": "board1"})
        await self.call("list_comments", {"board_id": "board1", "card_id": "card1"})
        await self.call(
            "get_comment",
            {"board_id": "board1", "card_id": "card1", "comment_id": "comment1"},
        )
        await self.call("list_checklists", {"board_id": "board1", "card_id": "card1"})
        await self.call(
            "get_checklist",
            {"board_id": "board1", "card_id": "card1", "checklist_id": "check1"},
        )
        self.assertEqual(
            [call[:2] for call in self.client.calls],
            [
                ("GET", "/api/users"),
                ("GET", "/api/boards/board1"),
                ("GET", "/api/boards/board1"),
                ("GET", "/api/boards/board1/cards/card1/comments"),
                ("GET", "/api/boards/board1/cards/card1/comments/comment1"),
                ("GET", "/api/boards/board1/cards/card1/checklists"),
                ("GET", "/api/boards/board1/cards/card1/checklists/check1"),
            ],
        )

    async def test_phase_3_read_and_confirmed_delete_routes(self) -> None:
        await self.call("get_list", {"board_id": "board1", "list_id": "list1"})
        await self.call(
            "delete_list",
            {"board_id": "board1", "list_id": "list1", "confirm": True},
        )
        await self.call(
            "get_swimlane", {"board_id": "board1", "swimlane_id": "swim1"}
        )
        await self.call(
            "delete_swimlane",
            {"board_id": "board1", "swimlane_id": "swim1", "confirm": True},
        )
        await self.call("delete_board", {"board_id": "board1", "confirm": True})
        self.assertEqual(
            [call[:2] for call in self.client.calls],
            [
                ("GET", "/api/boards/board1/lists/list1"),
                ("DELETE", "/api/boards/board1/lists/list1"),
                ("GET", "/api/boards/board1/swimlanes/swim1"),
                ("DELETE", "/api/boards/board1/swimlanes/swim1"),
                ("DELETE", "/api/boards/board1"),
            ],
        )

    async def test_member_tools_use_named_role_and_confirm_removal(self) -> None:
        await self.call(
            "add_board_member",
            {"board_id": "board1", "user_id": "user2", "role": "readonly"},
        )
        await self.call(
            "set_board_member_role",
            {"board_id": "board1", "user_id": "user2", "role": "normal"},
        )
        preview = await self.call(
            "remove_board_member", {"board_id": "board1", "user_id": "user2"}
        )
        self.assertFalse(preview["ok"])
        self.assertEqual(self.client.calls[0][2], {"action": "add", "role": "readonly"})
        self.assertEqual(self.client.calls[1][2], {"role": "normal"})

    async def test_label_tools_use_crud_and_atomic_card_routes(self) -> None:
        self.client.responses = ["label1", {"_id": "label1"}, {"_id": "label1"}, {}]
        created = await self.call(
            "create_label", {"board_id": "board1", "name": "Bug", "color": "red"}
        )
        await self.call(
            "update_label", {"board_id": "board1", "label_id": "label1", "color": "green"}
        )
        await self.call(
            "delete_label",
            {"board_id": "board1", "label_id": "label1", "confirm": True},
        )
        await self.call(
            "set_card_labels",
            {
                "board_id": "board1",
                "card_ids": ["card1"],
                "add_label_ids": ["label1"],
            },
        )
        self.assertEqual(created["label_id"], "label1")
        self.assertEqual(self.client.calls[0][0:2], ("PUT", "/api/boards/board1/labels"))
        self.assertEqual(
            self.client.calls[1][0:2], ("PUT", "/api/boards/board1/labels/label1")
        )
        self.assertEqual(self.client.calls[2][0], "DELETE")
        self.assertEqual(self.client.calls[3][1], "/api/boards/board1/cards/labels")

    async def test_comment_and_checklist_create_and_delete_contracts(self) -> None:
        self.client.responses = [
            {"_id": "comment1"},
            {"_id": "comment1"},
            {"_id": "check1"},
            {"_id": "check1"},
        ]
        await self.call(
            "create_comment",
            {"board_id": "board1", "card_id": "card1", "comment": " Ready "},
        )
        await self.call(
            "delete_comment",
            {
                "board_id": "board1",
                "card_id": "card1",
                "comment_id": "comment1",
                "confirm": True,
            },
        )
        await self.call(
            "create_checklist",
            {
                "board_id": "board1",
                "card_id": "card1",
                "title": "QA",
                "items": [" One ", "", "Two"],
            },
        )
        await self.call(
            "delete_checklist",
            {
                "board_id": "board1",
                "card_id": "card1",
                "checklist_id": "check1",
                "confirm": True,
            },
        )
        self.assertEqual(self.client.calls[0][2], {"comment": "Ready"})
        self.assertEqual(self.client.calls[1][0], "DELETE")
        self.assertEqual(self.client.calls[2][2], {"title": "QA", "items": ["One", "Two"]})
        self.assertEqual(self.client.calls[3][0], "DELETE")

    async def test_list_lifecycle_routes_and_zero_wip_limit(self) -> None:
        await self.call(
            "update_list",
            {"board_id": "board1", "list_id": "list1", "wip_limit": 0, "starred": False},
        )
        await self.call(
            "copy_list",
            {
                "board_id": "board1",
                "list_id": "list1",
                "position": 0,
                "title": "Copy",
            },
        )
        await self.call(
            "move_list",
            {"board_id": "board1", "list_id": "list1", "to_board_id": "board2"},
        )
        preview = await self.call(
            "delete_list", {"board_id": "board1", "list_id": "list1"}
        )
        self.assertFalse(preview["ok"])
        self.assertEqual(
            self.client.calls[0][2],
            {
                "starred": False,
                "wipLimit": {"value": 1, "enabled": False, "soft": False},
            },
        )
        self.assertTrue(self.client.calls[1][1].endswith("/lists/list1/copy"))
        self.assertEqual(self.client.calls[1][2]["title"], "Copy")
        self.assertTrue(self.client.calls[2][1].endswith("/lists/list1/move"))

    async def test_swimlane_lifecycle_routes(self) -> None:
        await self.call(
            "create_swimlane", {"board_id": "board1", "title": "Delivery", "sort": 0}
        )
        await self.call(
            "update_swimlane",
            {"board_id": "board1", "swimlane_id": "swim1", "title": "Build"},
        )
        await self.call(
            "copy_swimlane",
            {"board_id": "board1", "swimlane_id": "swim1", "position": 0},
        )
        await self.call(
            "move_swimlane",
            {"board_id": "board1", "swimlane_id": "swim1", "to_board_id": "board2"},
        )
        self.assertEqual(self.client.calls[0][2], {"title": "Delivery", "sort": 0.0})
        self.assertEqual(self.client.calls[1][0], "PUT")
        self.assertTrue(self.client.calls[2][1].endswith("/swimlanes/swim1/copy"))
        self.assertTrue(self.client.calls[3][1].endswith("/swimlanes/swim1/move"))

    async def test_board_lifecycle_requires_confirmation_for_delete(self) -> None:
        await self.call("update_board", {"board_id": "board1", "title": "Roadmap"})
        await self.call("copy_board", {"board_id": "board1", "title": "Roadmap copy"})
        preview = await self.call("delete_board", {"board_id": "board1"})
        self.assertFalse(preview["ok"])
        self.assertEqual(self.client.calls[0][1], "/api/boards/board1/title")
        self.assertEqual(self.client.calls[1][1], "/api/boards/board1/copy")

    async def test_search_cards_builds_paginated_server_side_query(self) -> None:
        result = await self.call(
            "search_cards",
            {
                "query": " login bug ",
                "board_id": "board1",
                "label_id": "label1",
                "archived": True,
                "limit": 25,
                "offset": 50,
            },
        )
        self.assertTrue(result["ok"])
        method, path, body = self.client.calls[-1]
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        self.assertTrue(path.startswith("/api/search/cards?"))
        self.assertIn("query=login+bug", path)
        self.assertIn("boardId=board1", path)
        self.assertIn("labelId=label1", path)
        self.assertIn("archived=true", path)
        self.assertIn("limit=25", path)
        self.assertIn("offset=50", path)

    async def test_search_cards_rejects_unbounded_pages(self) -> None:
        result = await self.call("search_cards", {"limit": 101})
        self.assertFalse(result["ok"])
        self.assertIn("between 1 and 100", str(result["message"]))

    async def test_api_permission_errors_remain_structured(self) -> None:
        self.client.responses = [SERVER.WekanAPIError("HTTP 403: denied")]
        result = await self.call("get_card", {"card_id": "card1"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "WekanAPIError")
        self.assertIn("403", str(result["message"]))


class WekanClientAuthTests(IsolatedAsyncioTestCase):
    async def test_redirect_is_rejected_without_replaying_a_write(self) -> None:
        config = SERVER.WekanConfig(
            base_url="https://wekan.invalid",
            api_token="token",
            user_id="user1",
            username=None,
            email=None,
            password=None,
            timeout_seconds=1,
            verify_tls=True,
        )
        client = SERVER.WekanClient(config)

        class StubHttpClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def request(self, *_args, **_kwargs):
                return httpx.Response(301, headers={"location": "/"})

        with mock.patch.object(
            SERVER.httpx, "AsyncClient", return_value=StubHttpClient()
        ) as async_client:
            response = await client._send_request(
                "POST", "/api/boards", json_body={}, headers={"Accept": "application/json"}
            )

        self.assertFalse(async_client.call_args.kwargs["follow_redirects"])
        with self.assertRaisesRegex(SERVER.WekanAPIError, "unexpected HTTP 301"):
            client._decode_response(response, "POST", "/api/boards")

    async def test_invalid_json_is_reported_as_a_structured_api_error(self) -> None:
        config = SERVER.WekanConfig(
            base_url="https://wekan.invalid",
            api_token="token",
            user_id="user1",
            username=None,
            email=None,
            password=None,
            timeout_seconds=1,
            verify_tls=True,
        )
        client = SERVER.WekanClient(config)
        response = httpx.Response(
            200,
            content=b"{broken",
            headers={"content-type": "application/json"},
        )
        with self.assertRaisesRegex(SERVER.WekanAPIError, "invalid JSON"):
            client._decode_response(response, "GET", "/api/boards")

    async def test_request_reauthenticates_once_after_401(self) -> None:
        config = SERVER.WekanConfig(
            base_url="https://wekan.invalid",
            api_token=None,
            user_id=None,
            username="admin",
            email=None,
            password="secret",
            timeout_seconds=1,
            verify_tls=True,
        )
        client = SERVER.WekanClient(config)
        login_count = 0

        async def login() -> None:
            nonlocal login_count
            if client._api_token and client._user_id:
                return
            login_count += 1
            client._api_token = f"token{login_count}"
            client._user_id = "user1"

        responses = [
            httpx.Response(401, json={"error": "expired"}),
            httpx.Response(200, json={"_id": "board1"}),
        ]

        async def send(*_args, **_kwargs) -> httpx.Response:
            return responses.pop(0)

        client._login = login  # type: ignore[method-assign]
        client._send_request = send  # type: ignore[method-assign]
        result = await client.request("GET", "/api/boards/board1")

        self.assertEqual(result, {"_id": "board1"})
        self.assertEqual(login_count, 2)

    async def test_get_retries_transport_and_gateway_failures(self) -> None:
        config = SERVER.WekanConfig(
            base_url="https://wekan.invalid",
            api_token="token",
            user_id="user1",
            username=None,
            email=None,
            password=None,
            timeout_seconds=1,
            verify_tls=True,
        )
        client = SERVER.WekanClient(config)
        outcomes: list[object] = [
            httpx.ConnectError("offline"),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]

        class StubHttpClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def request(self, *_args, **_kwargs):
                outcome = outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        with (
            mock.patch.object(SERVER.httpx, "AsyncClient", return_value=StubHttpClient()),
            mock.patch.object(SERVER.asyncio, "sleep", new=mock.AsyncMock()),
        ):
            response = await client._send_request(
                "GET", "/api/boards", json_body=None, headers={"Accept": "application/json"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(outcomes, [])

    async def test_write_transport_failure_is_not_retried(self) -> None:
        config = SERVER.WekanConfig(
            base_url="https://wekan.invalid",
            api_token="token",
            user_id="user1",
            username=None,
            email=None,
            password=None,
            timeout_seconds=1,
            verify_tls=True,
        )
        client = SERVER.WekanClient(config)
        attempts = 0

        class StubHttpClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def request(self, *_args, **_kwargs):
                nonlocal attempts
                attempts += 1
                raise httpx.ConnectError("offline")

        with mock.patch.object(SERVER.httpx, "AsyncClient", return_value=StubHttpClient()):
            with self.assertRaises(httpx.ConnectError):
                await client._send_request(
                    "POST", "/api/boards", json_body={}, headers={"Accept": "application/json"}
                )
        self.assertEqual(attempts, 1)

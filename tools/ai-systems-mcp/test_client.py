#!/usr/bin/env python3
"""Smoke-test the WeKan MCP server over stdio."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_DIR = Path(__file__).resolve().parent
EXPECTED_TOOL_COUNT = 49


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _structured(result: Any) -> dict[str, Any]:
    data = getattr(result, "structured_content", None)
    if data is None:
        data = getattr(result, "structuredContent", None)
    if not isinstance(data, dict):
        raise RuntimeError(f"Tool returned no structured content: {_jsonable(result)}")
    return data


async def _call_ok(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    data = _structured(result)
    if not data.get("ok"):
        raise RuntimeError(f"{name} failed: {data.get('message') or data}")
    return data


async def _live_crud(session: ClientSession) -> dict[str, Any]:
    """Exercise representative write paths on disposable boards, then clean up."""

    board_ids: list[str] = []
    summary: dict[str, Any] = {}
    try:
        board = await _call_ok(
            session,
            "create_board",
            {"title": "MCP live CRUD smoke", "permission": "private"},
        )
        board_id = str(board["board_id"])
        board_ids.append(board_id)
        await _call_ok(
            session,
            "update_board",
            {"board_id": board_id, "title": "MCP live CRUD smoke (active)"},
        )
        await _call_ok(session, "get_board", {"board_id": board_id})
        await _call_ok(session, "list_board_members", {"board_id": board_id})
        swimlane_id = board.get("default_swimlane_id")
        if not swimlane_id:
            lanes = await _call_ok(session, "list_swimlanes", {"board_id": board_id})
            swimlane_id = lanes["swimlanes"][0]["_id"]

        todo = await _call_ok(
            session, "create_list", {"board_id": board_id, "title": "Todo"}
        )
        doing = await _call_ok(
            session, "create_list", {"board_id": board_id, "title": "Doing"}
        )
        todo_id = str(todo["list_id"])
        doing_id = str(doing["list_id"])
        await _call_ok(
            session,
            "update_list",
            {"board_id": board_id, "list_id": doing_id, "wip_limit": 0},
        )
        await _call_ok(
            session, "get_list", {"board_id": board_id, "list_id": doing_id}
        )

        lane = await _call_ok(
            session,
            "create_swimlane",
            {"board_id": board_id, "title": "Secondary lane", "sort": 0},
        )
        lane_id = str(lane["swimlane_id"])
        await _call_ok(
            session,
            "update_swimlane",
            {"board_id": board_id, "swimlane_id": lane_id, "title": "QA lane"},
        )
        await _call_ok(
            session,
            "get_swimlane",
            {"board_id": board_id, "swimlane_id": lane_id},
        )
        card = await _call_ok(
            session,
            "create_card",
            {
                "board_id": board_id,
                "list_id": todo_id,
                "title": "Verify MCP CRUD",
                "swimlane_id": swimlane_id,
            },
        )
        card_id = str(card["card_id"])
        await _call_ok(session, "get_card", {"card_id": card_id})
        await _call_ok(
            session,
            "update_card",
            {
                "board_id": board_id,
                "list_id": todo_id,
                "card_id": card_id,
                "description": "live smoke",
                "label_ids": [],
            },
        )
        await _call_ok(
            session,
            "move_card",
            {
                "board_id": board_id,
                "list_id": todo_id,
                "card_id": card_id,
                "to_list_id": doing_id,
                "to_swimlane_id": swimlane_id,
            },
        )
        await _call_ok(
            session,
            "archive_card",
            {"board_id": board_id, "list_id": doing_id, "card_id": card_id},
        )
        await _call_ok(
            session,
            "unarchive_card",
            {"board_id": board_id, "list_id": doing_id, "card_id": card_id},
        )
        copied_card = await _call_ok(
            session,
            "copy_card",
            {
                "board_id": board_id,
                "list_id": doing_id,
                "card_id": card_id,
                "to_list_id": todo_id,
                "to_swimlane_id": swimlane_id,
                "position": 0,
            },
        )
        await _call_ok(
            session,
            "delete_card",
            {
                "board_id": board_id,
                "list_id": todo_id,
                "card_id": copied_card["card_id"],
                "confirm": True,
            },
        )

        label = await _call_ok(
            session,
            "create_label",
            {"board_id": board_id, "name": "Smoke", "color": "green"},
        )
        label_id = str(label["label_id"])
        await _call_ok(session, "list_labels", {"board_id": board_id})
        await _call_ok(
            session,
            "update_label",
            {"board_id": board_id, "label_id": label_id, "name": "Smoke tested"},
        )
        await _call_ok(
            session,
            "set_card_labels",
            {"board_id": board_id, "card_ids": [card_id], "add_label_ids": [label_id]},
        )

        comment = await _call_ok(
            session,
            "create_comment",
            {"board_id": board_id, "card_id": card_id, "comment": "MCP smoke comment"},
        )
        await _call_ok(
            session,
            "get_comment",
            {
                "board_id": board_id,
                "card_id": card_id,
                "comment_id": comment["comment_id"],
            },
        )
        await _call_ok(
            session, "list_comments", {"board_id": board_id, "card_id": card_id}
        )
        await _call_ok(
            session,
            "delete_comment",
            {
                "board_id": board_id,
                "card_id": card_id,
                "comment_id": comment["comment_id"],
                "confirm": True,
            },
        )
        checklist = await _call_ok(
            session,
            "create_checklist",
            {
                "board_id": board_id,
                "card_id": card_id,
                "title": "Smoke checklist",
                "items": ["Created", "Verified"],
            },
        )
        await _call_ok(
            session,
            "get_checklist",
            {
                "board_id": board_id,
                "card_id": card_id,
                "checklist_id": checklist["checklist_id"],
            },
        )
        await _call_ok(
            session, "list_checklists", {"board_id": board_id, "card_id": card_id}
        )
        await _call_ok(
            session,
            "delete_checklist",
            {
                "board_id": board_id,
                "card_id": card_id,
                "checklist_id": checklist["checklist_id"],
                "confirm": True,
            },
        )
        search = await _call_ok(
            session,
            "search_cards",
            {"board_id": board_id, "query": "Verify MCP CRUD", "limit": 10},
        )
        await _call_ok(
            session,
            "delete_label",
            {"board_id": board_id, "label_id": label_id, "confirm": True},
        )

        copied_list = await _call_ok(
            session,
            "copy_list",
            {"board_id": board_id, "list_id": doing_id, "position": 0},
        )
        await _call_ok(
            session,
            "move_list",
            {
                "board_id": board_id,
                "list_id": copied_list["list_id"],
                "position": 1,
            },
        )
        await _call_ok(
            session,
            "delete_list",
            {
                "board_id": board_id,
                "list_id": copied_list["list_id"],
                "confirm": True,
            },
        )
        copied_lane = await _call_ok(
            session,
            "copy_swimlane",
            {"board_id": board_id, "swimlane_id": lane_id, "position": 0},
        )
        await _call_ok(
            session,
            "move_swimlane",
            {
                "board_id": board_id,
                "swimlane_id": copied_lane["swimlane_id"],
                "position": 1,
            },
        )
        await _call_ok(
            session,
            "delete_swimlane",
            {
                "board_id": board_id,
                "swimlane_id": copied_lane["swimlane_id"],
                "confirm": True,
            },
        )

        copied_board = await _call_ok(
            session,
            "copy_board",
            {"board_id": board_id, "title": "MCP live CRUD smoke copy"},
        )
        copied_board_id = copied_board.get("board_id")
        if not copied_board_id:
            raise RuntimeError(f"copy_board returned no board_id: {copied_board}")
        board_ids.append(str(copied_board_id))
        summary = {
            "board_id": board_id,
            "card_id": card_id,
            "search": search.get("search"),
            "tool_count": EXPECTED_TOOL_COUNT,
        }
        return summary
    finally:
        cleanup_errors = []
        for board_id in reversed(board_ids):
            try:
                await _call_ok(
                    session, "delete_board", {"board_id": board_id, "confirm": True}
                )
            except Exception as error:  # noqa: BLE001 - cleanup must try every board.
                cleanup_errors.append(f"{board_id}: {error}")
        if cleanup_errors:
            raise RuntimeError(f"Live CRUD cleanup failed: {'; '.join(cleanup_errors)}")


async def _run(server_python: str, call_boards: bool, live_crud: bool) -> None:
    env = os.environ.copy()

    params = StdioServerParameters(
        command=server_python,
        args=[str(SERVER_DIR / "server.py"), "--transport", "stdio"],
        env=env,
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_items = getattr(tools, "tools", None)
            if not isinstance(tool_items, list) or len(tool_items) != EXPECTED_TOOL_COUNT:
                actual = len(tool_items) if isinstance(tool_items, list) else "unknown"
                raise RuntimeError(
                    f"Expected {EXPECTED_TOOL_COUNT} MCP tools, received {actual}"
                )
            print("TOOLS")
            print(json.dumps(_jsonable(tools), indent=2))

            resources = await session.list_resources()
            print("RESOURCES")
            print(json.dumps(_jsonable(resources), indent=2))

            config = await session.read_resource("wekan://config")
            print("READ_CONFIG")
            print(json.dumps(_jsonable(config), indent=2))

            quickstart = await session.read_resource("wekan://quickstart")
            print("READ_QUICKSTART")
            print(json.dumps(_jsonable(quickstart), indent=2))

            prompts = await session.list_prompts()
            print("PROMPTS")
            print(json.dumps(_jsonable(prompts), indent=2))

            health = await session.call_tool("wekan_health_status", {})
            print("HEALTH")
            print(json.dumps(_jsonable(health), indent=2))

            if call_boards:
                boards = await session.call_tool("list_boards", {})
                print("LIST_BOARDS")
                print(json.dumps(_jsonable(boards), indent=2))

            if live_crud:
                result = await _live_crud(session)
                print("LIVE_CRUD")
                print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the WeKan MCP server.")
    parser.add_argument("--python", default=sys.executable, help="Python executable to run server.py.")
    parser.add_argument(
        "--call-boards",
        action="store_true",
        help="Also call list_boards. Requires valid WeKan credentials.",
    )
    parser.add_argument(
        "--live-crud",
        action="store_true",
        help="Run a destructive disposable-board CRUD smoke and clean it up.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.python, args.call_boards, args.live_crud))


if __name__ == "__main__":
    main()

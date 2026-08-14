# WeKan MCP

MCP server nay expose board/list/card tools cho WeKan, ung dung Trello-like cua
du an. Endpoint nay KHONG ket noi den Trello official va khong can Trello API
key.

The server is local-only by default:

```text
http://127.0.0.1:8000/mcp
```

Transport:

```text
streamable-http
```

Server-side MCP tu xu ly WeKan auth. Vi server giu quyen tao board/list/card,
khong expose endpoint nay ra Internet neu khong co lop authentication va access
control o reverse proxy. Khong commit hoac gui WeKan token/password cho MCP
client.

## For Agents

Neu client ho tro remote MCP URL, cau hinh:

```json
{
  "mcpServers": {
    "wekan": {
      "url": "http://127.0.0.1:8000/mcp",
      "transport": "streamable-http"
    }
  }
}
```

Neu client yeu cau headers cho streamable HTTP, dung:

```json
{
  "Accept": "application/json, text/event-stream",
  "Content-Type": "application/json"
}
```

Endpoint local chay stateless HTTP de tranh loi `400 Missing session ID` voi
nhung client khong giu MCP session header tot.

## Tool List

Server version 0.3 exposes 49 tools. `wekan_health_status` checks runtime and
authentication before any board work.

Boards:

- `list_boards`, `get_board`, `create_board`, `update_board`, `copy_board`,
  `delete_board`.

Lists and swimlanes:

- `list_lists`, `get_list`, `create_list`, `update_list`, `copy_list`,
  `move_list`, `delete_list`.
- `list_swimlanes`, `get_swimlane`, `create_swimlane`, `update_swimlane`,
  `copy_swimlane`, `move_swimlane`, `delete_swimlane`.

Cards:

- `list_cards`, `get_card`, `create_card`, `update_card`, `move_card`,
  `archive_card`, `unarchive_card`, `copy_card`, `delete_card`.
- `search_cards` performs permission-aware server-side search with filters and
  pagination. It does not scan board/list/card data from the MCP process.

Collaboration:

- Users and members: `list_users`, `list_board_members`, `add_board_member`,
  `set_board_member_role`, `remove_board_member`.
- Labels: `list_labels`, `create_label`, `update_label`, `delete_label`,
  `set_card_labels`.
- Comments: `list_comments`, `get_comment`, `create_comment`, `delete_comment`.
- Checklists: `list_checklists`, `get_checklist`, `create_checklist`,
  `delete_checklist`.

`delete_*` and `remove_board_member` require `confirm=true`. Prefer
`archive_card` when the card may need to be restored. WeKan REST permissions
remain authoritative; MCP does not elevate a read-only or comment-only user.

## Common Workflow

1. Kiem tra ket noi:

```json
{
  "name": "wekan_health_status",
  "arguments": {}
}
```

2. Tao board:

```json
{
  "name": "create_board",
  "arguments": {
    "title": "My Project Board",
    "permission": "private"
  }
}
```

Response quan trong:

```json
{
  "ok": true,
  "board_id": "...",
  "default_swimlane_id": "..."
}
```

3. Tao list:

```json
{
  "name": "create_list",
  "arguments": {
    "board_id": "...",
    "title": "Todo"
  }
}
```

Response quan trong:

```json
{
  "ok": true,
  "list_id": "..."
}
```

4. Tao card:

```json
{
  "name": "create_card",
  "arguments": {
    "board_id": "...",
    "list_id": "...",
    "title": "Write first draft",
    "description": "Short, actionable card description."
  }
}
```

Response quan trong:

```json
{
  "ok": true,
  "card_id": "...",
  "author_id": "admin",
  "swimlane_id": "..."
}
```

5. Update, move or archive the card:

```json
{
  "name": "update_card",
  "arguments": {
    "board_id": "...",
    "list_id": "...",
    "card_id": "...",
    "description": "Implementation notes",
    "due_at": "2026-08-20T09:00:00.000Z"
  }
}
```

6. Xac minh card:

```json
{
  "name": "list_cards",
  "arguments": {
    "board_id": "...",
    "list_id": "..."
  }
}
```

## Tool Arguments

`create_board`:

```json
{
  "title": "Required board title",
  "permission": "private",
  "owner": null,
  "color": "belize"
}
```

`create_list`:

```json
{
  "board_id": "required",
  "title": "required",
  "swimlane_id": null
}
```

`create_card`:

```json
{
  "board_id": "required",
  "list_id": "required",
  "title": "required",
  "description": "",
  "author_id": null,
  "swimlane_id": null,
  "members": null,
  "assignees": null,
  "received_at": null,
  "start_at": null,
  "due_at": null,
  "end_at": null
}
```

Date fields should be ISO-like date strings accepted by WeKan, for example
`2026-08-10T09:00:00.000Z`.

`search_cards` accepts `query`, `board_id`, `list_id`, `swimlane_id`,
`member_id`, `assignee_id`, `label_id`, `archived`, `due_from`, `due_to`,
`limit` (1-100), and `offset` (0-10000).

## Raw HTTP Smoke Tests

Initialize:

```sh
curl -sS http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-03-26",
      "capabilities": {},
      "clientInfo": { "name": "curl-smoke", "version": "1" }
    }
  }'
```

List tools:

```sh
curl -sS http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

Call health:

```sh
curl -sS http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "wekan_health_status",
      "arguments": {}
    }
  }'
```

Healthy response should include:

```json
{
  "ok": true,
  "base_url": "http://wekan-ui:8080",
  "auth_probe": {
    "authenticated": true,
    "user_id": "admin"
  }
}
```

## Error Handling

Tools return structured JSON. Successful calls return `ok: true`. Failed calls
return:

```json
{
  "ok": false,
  "error": "ErrorClass",
  "message": "Human readable reason"
}
```

Common cases:

- `ConnectError` - MCP container cannot reach WeKan. Check Docker network and
  `WEKAN_BASE_URL`.
- `Missing WeKan credentials` - server env is missing token or login credentials.
- `Swimlane ID is required` - old server version, or direct WeKan REST call did
  not include `swimlaneId`. Use the MCP `create_card` tool; it fills default
  swimlane automatically.
- `400 Missing session ID` - client is speaking stateful streamable HTTP. The
  server is configured stateless; reconnect to the configured endpoint
  or verify the request path is exactly `/mcp`.

## Local Configuration

Set base URL:

```sh
export WEKAN_BASE_URL=http://127.0.0.1:3000
```

Then configure auth by token:

```sh
export WEKAN_API_TOKEN=...
export WEKAN_USER_ID=...
```

Or let the MCP server log in automatically:

```sh
export WEKAN_USERNAME=admin
export WEKAN_PASSWORD=...
# or WEKAN_EMAIL=admin@example.com
```

Optional settings:

```sh
export WEKAN_TIMEOUT_SECONDS=20
export WEKAN_VERIFY_TLS=true
export MCP_STATELESS_HTTP=true
```

## Install Locally

```sh
cd tools/ai-systems-mcp
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run Locally

For local MCP clients:

```sh
python server.py --transport stdio
```

For streamable HTTP:

```sh
python server.py --transport streamable-http --host 127.0.0.1 --port 8000
```

The streamable HTTP path defaults to `/mcp`.

## Local Smoke Test

List MCP tools/resources and call the health tool:

```sh
python test_client.py
```

Also call `list_boards` when credentials are configured:

```sh
python test_client.py --call-boards
```

Run the disposable-board CRUD smoke only against a test instance. It exercises
representative board/list/swimlane/card, label, comment, checklist, search, copy,
move, archive and delete paths, then requires successful cleanup:

```sh
python test_client.py --live-crud
```

The smoke test also fails if the server does not expose exactly 49 tools.

`list_boards` should include private boards owned by or shared with the
authenticated user. If it returns `0` while `get_board` by a known private board
id works, rebuild/restart the MCP server so it is using
`/api/users/:userId/boards` instead. `/api/boards` chi list public boards.

## Docker Runtime

Compose maps the container to `127.0.0.1:18080` by default:

```sh
cd tools/ai-systems-mcp
docker compose up -d --build
```

By default compose joins the external Docker network
`WEKAN_DOCKER_NETWORK=wekan-ui_wekan-ui` and reaches WeKan at
`WEKAN_BASE_URL=http://wekan-ui:8080`. Override those values when the WeKan
container/network uses different names.

Keep `MCP_BIND=127.0.0.1` unless an authenticated reverse proxy is in front of
the service. TLS alone is not client authentication: a public unauthenticated
MCP endpoint would give anyone the WeKan privileges configured in the server.

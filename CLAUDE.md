# ksa-desk-agent

Zoho Desk triage agent for the KSA support team. When a ticket is created, a Zoho Desk Workflow Rule fires a webhook to this FastAPI service. The service silently applies a domain-based label and performs LLM-driven internal triage (priority, category, status, assignee) — no customer-facing replies, no internal comments.

## Architecture

```
Zoho Desk Workflow Rule
  └─► Custom Function (Deluge)
        └─► POST /webhook/desk  (X-Webhook-Secret header)
              └─► FastAPI (background task)
                    ├─ extract email domain (Python, no API)
                    ├─ check freemail list (Python, no API)
                    └─► claude --print subprocess
                          └─► zoho-desk MCP (registered in ~/.claude.json)
                                ├─ ZohoDesk_getTicket
                                ├─ ZohoDesk_getLabels / createLabel
                                ├─ ZohoDesk_updateTicket  (label + triage fields)
                                └─ ZohoDesk_getAgents
```

**Key design decisions:**
- No Anthropic API key required — the agent runs via `claude --print` subprocess using the existing claude.ai OAuth session.
- Zoho access goes through the `zoho-desk` MCP server registered in `~/.claude.json` via `claude mcp add`. Token refresh uses `zoho_client_id/secret/refresh_token` in `.env`.
- Silent triage only: no replies to customer, no internal comments. All reasoning goes to structlog JSON logs.
- Domain labels use the prefix `domain:<value>` (e.g. `domain:acme.com`). Free-mail domains are skipped.

## Current status (as of 2026-05-04)

**Pending: one-time interactive MCP OAuth auth.**

The `zoho-desk` MCP server has been registered in `~/.claude.json` and the Zoho OAuth token refresh logic is wired up in `runner.py`. However, the Zoho MCP server uses an OAuth PKCE flow — it will not accept a raw Bearer token header until the user has completed the browser-based OAuth consent once in an interactive Claude session.

**To unblock:** run `claude` in a terminal from the project directory. Claude will detect that `zoho-desk` needs authorization and print a URL. Open the URL in a browser, approve the Zoho consent screen, then `/exit`. After that, all subprocesses will reuse the cached credential and the token-refresh logic keeps it alive.

Once unblocked, the full pipeline is working end-to-end (webhook → FastAPI → subprocess → MCP → Zoho Desk).

## Project layout

```
src/desk_agent/
├── config.py          Settings loaded from .env (pydantic-settings)
├── logging.py         structlog JSON renderer
├── main.py            FastAPI app + lifespan (uvicorn entry point)
├── webhook.py         POST /webhook/desk — secret check, 202 + BackgroundTask
├── agent/
│   ├── prompts.py     SYSTEM_PROMPT + build_user_message()
│   └── runner.py      run_triage() — claude --print subprocess + token refresh
├── domain/
│   ├── freemail.py    FREEMAIL_DOMAINS frozenset + is_freemail()
│   └── labeler.py     ⚠️ UNUSED in main pipeline — kept for tests only
└── zoho/
    ├── mcp.py         ⚠️ UNUSED in main pipeline — raw JSON-RPC client (requires OAuth Bearer)
    └── models.py      ZohoLabel dataclass (used by labeler tests)

tests/
├── conftest.py        Sets env vars before imports
├── test_freemail.py
├── test_labeler.py    Tests labeler.py in isolation (mocks zoho_mcp)
└── test_webhook.py
```

## Environment (`.env`)

```
ZOHO_MCP_URL=https://anoopsadcmcp-150001164898.zohomcp.sa/mcp/303ef72757ee1c32f6b36758c03610da/message
WEBHOOK_SECRET=<32+ char random string>
LOG_LEVEL=INFO
CLAUDE_BIN=/opt/homebrew/bin/claude

# Zoho OAuth — used by runner.py to refresh the MCP server token before each subprocess call.
# Get from: api-console.zoho.sa → Self-Client → generate grant code with scopes below → exchange for tokens.
# Required scopes: Desk.tickets.READ,Desk.tickets.UPDATE,Desk.basic.READ,Desk.contacts.READ,Desk.settings.READ,Desk.settings.WRITE
ZOHO_CLIENT_ID=<from api-console.zoho.sa>
ZOHO_CLIENT_SECRET=<from api-console.zoho.sa>
ZOHO_REFRESH_TOKEN=<long-lived refresh token>
```

**No ANTHROPIC_API_KEY needed.** The `claude` CLI uses the machine's claude.ai OAuth session.

## Running locally

```bash
# Install deps
pip3 install fastapi "uvicorn[standard]" httpx pydantic-settings structlog python-dotenv pytest pytest-asyncio

# Register the Zoho MCP server (one-time — writes to ~/.claude.json)
claude mcp add zoho-desk "https://anoopsadcmcp-150001164898.zohomcp.sa/mcp/303ef72757ee1c32f6b36758c03610da/message" \
  --transport http --scope user \
  --header "Authorization: Bearer <initial-access-token>"

# Complete OAuth PKCE auth (one-time interactive step — see Current Status above)
cd "/Users/anoop-ksa0043/AI Workspace/ksa-desk-agent"
claude   # approve zoho-desk when prompted, then /exit

# Run server (port 8000)
PYTHONPATH=src python3 -m uvicorn desk_agent.main:app --reload --port 8000

# Expose via tunnel (separate terminal)
cloudflared tunnel --url http://localhost:8000

# Run tests
PYTHONPATH=src python3 -m pytest tests/ -v
```

## Zoho Desk workflow setup

In Zoho Desk → Setup → Automation → Workflow Rules → New Rule:
- **Module**: Tickets | **Trigger**: On Create
- **Action**: Custom Function → paste the Deluge below

```javascript
ticketId = ticket.get("id");
departmentId = ticket.get("departmentId");
contactEmail = ticket.get("contact").get("email");

headers = Map();
headers.put("X-Webhook-Secret", "<WEBHOOK_SECRET from .env>");
headers.put("Content-Type", "application/json");

body = Map();
body.put("ticketId", ticketId);
body.put("departmentId", departmentId);
body.put("contactEmail", contactEmail);

response = invokeurl
[
    url: "https://<tunnel-url>/webhook/desk"
    type: POST
    parameters: body.toString()
    headers: headers
];

info response;
```

## Agent tool surface (allowlist)

The subprocess uses `--allowedTools` to restrict Claude to these MCP tools only. Any other tool (sendReply, createTicketComment, deleteTicket, etc.) is blocked.

```
mcp__zoho-desk__ZohoDesk_getTicket
mcp__zoho-desk__ZohoDesk_getThreads
mcp__zoho-desk__ZohoDesk_getThread
mcp__zoho-desk__ZohoDesk_updateTicket
mcp__zoho-desk__ZohoDesk_getAgents
mcp__zoho-desk__ZohoDesk_getAgent
mcp__zoho-desk__ZohoDesk_getDepartments
mcp__zoho-desk__ZohoDesk_getDepartment
mcp__zoho-desk__ZohoDesk_getLabels
mcp__zoho-desk__ZohoDesk_getLabel
mcp__zoho-desk__ZohoDesk_createLabel
mcp__zoho-desk__ZohoDesk_getContacts
mcp__zoho-desk__ZohoDesk_getContact
```

MCP tool prefix derives from the server name: a server named `zoho-desk` gets prefix `mcp__zoho-desk__`.

## Known quirks

- **`--allowedTools` eats positional args**: In `claude --print`, the `--allowedTools` flag is variadic. Passing the prompt as a positional argument after it causes the CLI to treat the prompt as another tool name. Fix applied: prompt is passed via `stdin` instead.
- **`--permission-mode bypassPermissions`**: Required for non-interactive subprocess use so MCP tool calls don't block waiting for a terminal approval prompt.
- **DXT/remote MCP tools don't work in subprocesses**: MCP servers loaded by the Claude Code desktop app (shown with UUID-based prefixes like `mcp__91633071-82c9-4768-baac-d7da79796f03__`) are session-scoped to the desktop app. A `claude --print` subprocess starts a fresh session and cannot see them. Solution: register the MCP server explicitly via `claude mcp add --scope user`, which writes to `~/.claude.json`.
- **`mcpServers` is NOT valid in `~/.claude/settings.json`**: The settings schema rejects it. MCP servers must be registered via `claude mcp add` (writes to `~/.claude.json`) or via a project `.mcp.json` file.
- **Zoho MCP uses OAuth PKCE, not plain Bearer**: Even with a valid `Authorization: Bearer` header in `~/.claude.json`, the Zoho-hosted MCP server initiates an OAuth PKCE consent flow on first connection. This requires one interactive browser authorization. After that, the cached credential is reused automatically and the token-refresh logic in `runner.py` keeps it alive.
- **No `claude mcp update` command**: To update the Bearer token in `~/.claude.json`, patch the file directly: `data["mcpServers"]["zoho-desk"]["headers"]["Authorization"] = f"Bearer {token}"`.
- **Zoho label scopes**: `Desk.labels.READ` / `Desk.labels.WRITE` are not valid Zoho API scopes. Use `Desk.settings.READ` and `Desk.settings.WRITE` instead — they cover label CRUD.
- **`zoho/mcp.py` is vestigial**: An earlier iteration used a raw JSON-RPC client. Kept because labeler tests reference it. Not called in production.
- **Python 3.9**: The `mcp` Python package requires 3.10+. All MCP interaction goes through the `claude` CLI subprocess.

## Key IDs (SA org)

- **orgId**: `150000605092`
- **MEA Services - KSA** (primary dept): `7655000000203029`

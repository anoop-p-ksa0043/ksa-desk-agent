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
                          └─► anupz-corp-server1 MCP (claude.ai session)
                                ├─ ZohoDesk_getTicket
                                ├─ ZohoDesk_getLabels / createLabel
                                ├─ ZohoDesk_updateTicket  (label + triage fields)
                                └─ ZohoDesk_getAgents
```

**Key design decisions:**
- No Anthropic API key required — the agent runs via `claude --print` subprocess using the existing claude.ai OAuth session.
- No Zoho REST API credentials in `.env` — all Zoho access goes through the `anupz-corp-server1` claude.ai-hosted MCP server.
- Silent triage only: no replies to customer, no internal comments. All reasoning goes to structlog JSON logs.
- Domain labels use the prefix `domain:<value>` (e.g. `domain:acme.com`). Free-mail domains are skipped.

## Current blocker (as of 2026-05-04)

The `anupz-corp-server1` MCP server returns `SCOPE_MISMATCH` for all Zoho Desk API calls. This means the server's Zoho OAuth token is missing Desk scopes. Fix: go to **claude.ai → Settings → Integrations → anupz-corp-server1 → Reconnect**, and approve these Zoho scopes:
- `Desk.tickets.READ`
- `Desk.tickets.UPDATE`
- `Desk.basic.READ`
- `Desk.contacts.READ`
- `Desk.settings.READ`

After re-authorizing, the end-to-end pipeline works (verified: CLI subprocess calls MCP tools, Claude processes and calls updateTicket).

## Project layout

```
src/desk_agent/
├── config.py          Settings loaded from .env (pydantic-settings)
├── logging.py         structlog JSON renderer
├── main.py            FastAPI app + lifespan (uvicorn entry point)
├── webhook.py         POST /webhook/desk — secret check, 202 + BackgroundTask
├── agent/
│   ├── prompts.py     SYSTEM_PROMPT + build_user_message()
│   └── runner.py      run_triage() — claude --print subprocess
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
LOG_LEVEL=INFO           # optional
CLAUDE_BIN=claude        # optional, override if claude not on PATH
```

**No ANTHROPIC_API_KEY needed.** The `claude` CLI uses the machine's claude.ai OAuth session.

## Running locally

```bash
# Install deps
pip3 install fastapi "uvicorn[standard]" httpx pydantic-settings structlog python-dotenv pytest pytest-asyncio

# Run server (port 8000)
cd "/Users/anup/AI Workspace/ksa-desk-agent"
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
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getTicket
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getThreads
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getThread
mcp__claude_ai_anupz-corp-server1__ZohoDesk_updateTicket
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getAgents
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getAgent
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getDepartments
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getDepartment
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getLabels
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getLabel
mcp__claude_ai_anupz-corp-server1__ZohoDesk_createLabel
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getContacts
mcp__claude_ai_anupz-corp-server1__ZohoDesk_getContact
```

## Known quirks

- **`--allowedTools` eats positional args**: In `claude --print`, the `--allowedTools` flag is variadic. Passing the prompt as a positional argument after it causes the CLI to treat the prompt as another tool name. Fix applied: prompt is passed via `stdin` instead.
- **`--permission-mode bypassPermissions`**: Required for non-interactive subprocess use so MCP tool calls don't block waiting for a terminal approval prompt.
- **`zoho/mcp.py` is vestigial**: An earlier iteration used a raw JSON-RPC client to call the Zoho-hosted MCP server directly. That server requires a Bearer OAuth token (401 without it) so we switched to the claude.ai-hosted `anupz-corp-server1` path via CLI. The file is kept because the labeler tests still reference it, but it is not called in production flow.
- **Python 3.9**: The `mcp` Python package requires 3.10+. All MCP interaction goes through the `claude` CLI subprocess, which handles its own MCP connections.

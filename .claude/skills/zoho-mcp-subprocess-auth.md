# Skill: Configure a Zoho MCP Server for claude --print Subprocesses

## Problem

`claude --print` subprocesses start a fresh CLI session. They cannot see MCP servers that are loaded by the Claude Code desktop app (those appear with UUID-based prefixes like `mcp__91633071-...`). Any attempt to use those tools in a subprocess results in "tools not available" errors.

## Solution Pattern

### 1. Register the server with `claude mcp add` (user scope)

```bash
claude mcp add <server-name> "<mcp-url>" \
  --transport http \
  --scope user \
  --header "Authorization: Bearer <initial-access-token>"
```

This writes to `~/.claude.json` (NOT `~/.claude/settings.json` — `mcpServers` is not a valid key there).

### 2. Complete OAuth PKCE auth interactively (one-time)

Zoho's MCP server uses OAuth PKCE, not plain Bearer token auth. Even with a valid Bearer header, it initiates a consent flow on first connection. Run `claude` interactively in the project directory, approve the browser consent when prompted, then `/exit`. After that, the cached credential is reused automatically.

### 3. Wire token refresh in runner.py

The Zoho access token expires in 1 hour. Before spawning each subprocess, fetch a fresh token via the Zoho refresh endpoint and patch `~/.claude.json` directly (there is no `claude mcp update` command):

```python
def _update_mcp_token(access_token: str) -> None:
    claude_json = Path.home() / ".claude.json"
    data = json.loads(claude_json.read_text())
    data["mcpServers"]["zoho-desk"]["headers"]["Authorization"] = f"Bearer {access_token}"
    claude_json.write_text(json.dumps(data, indent=2))
```

Refresh call:
```python
async with httpx.AsyncClient() as client:
    resp = await client.post(
        "https://accounts.zoho.sa/oauth/v2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
    )
    access_token = resp.json()["access_token"]
```

### 4. Use the correct tool prefix

A server named `zoho-desk` exposes tools as `mcp__zoho-desk__ZohoDesk_*`. Pass this as `--allowedTools` in the subprocess command.

## Zoho OAuth Self-Client Setup (SA datacenter)

1. Go to `api-console.zoho.sa` → Self-Client → Generate Code
2. Scopes: `Desk.tickets.READ,Desk.tickets.UPDATE,Desk.basic.READ,Desk.contacts.READ,Desk.settings.READ,Desk.settings.WRITE`
   - Note: `Desk.labels.READ/WRITE` are **not** valid scopes — use `Desk.settings.*` for label access
3. Exchange the grant code (no `redirect_uri` for self-client):
   ```bash
   curl -X POST "https://accounts.zoho.sa/oauth/v2/token" \
     -d "grant_type=authorization_code" \
     -d "client_id=YOUR_CLIENT_ID" \
     -d "client_secret=YOUR_CLIENT_SECRET" \
     -d "code=YOUR_GRANT_CODE"
   ```
4. Store `refresh_token`, `client_id`, `client_secret` in `.env`.

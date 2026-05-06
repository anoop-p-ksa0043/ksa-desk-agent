from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

import httpx

from desk_agent.agent.prompts import SYSTEM_PROMPT, build_user_message
from desk_agent.config import settings
from desk_agent.logging import logger

_MCP_SERVER_NAME = "zoho-desk"
_MCP_PREFIX = f"mcp__{_MCP_SERVER_NAME}__"

_ALLOWED_TOOLS = ",".join([
    f"{_MCP_PREFIX}ZohoDesk_getTicket",
    f"{_MCP_PREFIX}ZohoDesk_getThreads",
    f"{_MCP_PREFIX}ZohoDesk_getThread",
    f"{_MCP_PREFIX}ZohoDesk_updateTicket",
    f"{_MCP_PREFIX}ZohoDesk_getAgents",
    f"{_MCP_PREFIX}ZohoDesk_getAgent",
    f"{_MCP_PREFIX}ZohoDesk_getDepartments",
    f"{_MCP_PREFIX}ZohoDesk_getDepartment",
    f"{_MCP_PREFIX}ZohoDesk_getLabels",
    f"{_MCP_PREFIX}ZohoDesk_getLabel",
    f"{_MCP_PREFIX}ZohoDesk_createLabel",
    f"{_MCP_PREFIX}ZohoDesk_getContacts",
    f"{_MCP_PREFIX}ZohoDesk_getContact",
])

_PROJECT_DIR = "/Users/anoop-ksa0043/AI Workspace/ksa-desk-agent"
_ZOHO_TOKEN_URL = "https://accounts.zoho.sa/oauth/v2/token"


async def _refresh_zoho_token() -> str | None:
    """Exchange refresh token for a fresh access token. Returns the new token or None."""
    if not all([settings.zoho_client_id, settings.zoho_client_secret, settings.zoho_refresh_token]):
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _ZOHO_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.zoho_client_id,
                "client_secret": settings.zoho_client_secret,
                "refresh_token": settings.zoho_refresh_token,
            },
        )
        resp.raise_for_status()
        return resp.json().get("access_token")


def _update_mcp_token(access_token: str) -> None:
    """Patch the Bearer token for zoho-desk in ~/.claude.json."""
    claude_json = Path.home() / ".claude.json"
    data = json.loads(claude_json.read_text())
    data.setdefault("mcpServers", {}).setdefault(_MCP_SERVER_NAME, {}).setdefault("headers", {})
    data["mcpServers"][_MCP_SERVER_NAME]["headers"]["Authorization"] = f"Bearer {access_token}"
    claude_json.write_text(json.dumps(data, indent=2))


async def run_triage(
    ticket_id: str,
    department_id: str,
    sender_domain: str,
    is_freemail: bool = False,
) -> None:
    log = logger.bind(ticket_id=ticket_id)
    log.info("agent_started", department_id=department_id, sender_domain=sender_domain)

    # Refresh Zoho token before each run so the subprocess always has a valid token.
    try:
        new_token = await _refresh_zoho_token()
        if new_token:
            _update_mcp_token(new_token)
            log.info("zoho_token_refreshed")
    except Exception as exc:
        log.warning("zoho_token_refresh_failed", error=str(exc))

    prompt = build_user_message(ticket_id, department_id, sender_domain, is_freemail)

    cmd = [
        settings.claude_bin, "--print",
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
        "--system-prompt", SYSTEM_PROMPT,
        "--allowedTools", _ALLOWED_TOOLS,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_PROJECT_DIR,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=120,
        )

        if proc.returncode != 0:
            log.error(
                "agent_cli_error",
                returncode=proc.returncode,
                stderr=stderr.decode()[:500],
            )
            return

        output = _parse_cli_output(stdout.decode())
        log.info(
            "agent_completed",
            ticket_id=ticket_id,
            result=output.get("result", "")[:400],
            num_turns=output.get("num_turns"),
        )

    except asyncio.TimeoutError:
        log.error("agent_timeout", ticket_id=ticket_id)
    except Exception as exc:
        log.error("agent_failed", ticket_id=ticket_id, error=str(exc), exc_info=True)


def _parse_cli_output(raw: str) -> Dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"result": raw}

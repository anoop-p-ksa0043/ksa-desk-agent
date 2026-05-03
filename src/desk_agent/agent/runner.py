from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from desk_agent.agent.prompts import SYSTEM_PROMPT, build_user_message
from desk_agent.config import settings
from desk_agent.logging import logger

# Prefix for the claude.ai-hosted Zoho Desk MCP server
_MCP_PREFIX = "mcp__claude_ai_anupz-corp-server1__"

# Safe read + label + single-write tools only. Blocks reply, comment, delete, merge, etc.
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

# Project directory — claude --print must run here so MCP session is loaded
_PROJECT_DIR = "/Users/anup/AI Workspace/ksa-desk-agent"


async def run_triage(
    ticket_id: str,
    department_id: str,
    sender_domain: str,
    is_freemail: bool = False,
) -> None:
    """
    Runs the Claude Code CLI triage agent for a single ticket.
    Uses the claude.ai session (no API key needed) with the anupz-corp-server1 MCP.
    Handles domain labeling + triage in one pass.
    Never raises — caller treats any exception as a non-fatal skip.
    """
    log = logger.bind(ticket_id=ticket_id)
    log.info("agent_started", department_id=department_id, sender_domain=sender_domain)

    prompt = build_user_message(ticket_id, department_id, sender_domain, is_freemail)

    # Prompt is passed via stdin — passing it as a positional arg after --allowedTools
    # causes the variadic --allowedTools parser to consume it as another tool name.
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

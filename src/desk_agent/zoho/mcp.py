from __future__ import annotations

"""
Minimal MCP-over-HTTP client for calling Zoho Desk MCP tools directly from Python.

The Zoho MCP server uses the MCP streamable-http transport (POST JSON-RPC to a
single endpoint). We implement just enough of the protocol to call tools without
the `mcp` package (which requires Python 3.10+).

Session lifecycle:
  1. POST initialize request → get server capabilities + session ID
  2. POST tools/call requests with the session ID header
"""

import json
import re
import uuid
from typing import Any, Dict, Optional

import httpx

from desk_agent.config import settings

_SESSION_ID_HEADER = "Mcp-Session-Id"


class ZohoMCPClient:
    def __init__(self) -> None:
        self._url = settings.zoho_mcp_url
        self._session_id: Optional[str] = None
        self._http: Optional[httpx.AsyncClient] = None

    async def _ensure_session(self) -> None:
        if self._session_id:
            return
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)

        resp = await self._http.post(
            self._url,
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "desk-agent", "version": "0.1.0"},
                },
            },
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        )
        resp.raise_for_status()

        # Session ID may be in response header
        self._session_id = resp.headers.get(_SESSION_ID_HEADER, "init")

        # Send initialized notification (fire-and-forget)
        await self._http.post(
            self._url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=self._headers(),
        )

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self._session_id and self._session_id != "init":
            h[_SESSION_ID_HEADER] = self._session_id
        return h

    def _parse_body(self, resp: httpx.Response) -> Any:
        """Parse JSON-RPC response, handling SSE-wrapped responses."""
        ct = resp.headers.get("content-type", "")
        text = resp.text
        if "text/event-stream" in ct:
            # Extract JSON from SSE: find 'data: {...}' lines
            for line in text.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        return json.loads(payload)
            raise ValueError(f"No data line found in SSE response: {text[:200]}")
        return resp.json()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        await self._ensure_session()
        resp = await self._http.post(  # type: ignore[union-attr]
            self._url,
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        body = self._parse_body(resp)
        if "error" in body:
            raise RuntimeError(f"MCP tool error: {body['error']}")
        return body.get("result", {})

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._session_id = None


zoho_mcp = ZohoMCPClient()

from __future__ import annotations

from typing import Dict, Optional

from desk_agent.domain.freemail import is_freemail
from desk_agent.logging import logger
from desk_agent.zoho.mcp import zoho_mcp
from desk_agent.zoho.models import ZohoLabel

# In-process cache: label name → ZohoLabel (avoids repeated list calls per run)
_label_cache: Dict[str, ZohoLabel] = {}


def _extract_domain(email: str) -> Optional[str]:
    email = email.strip().lower()
    if "@" not in email:
        return None
    return email.split("@", 1)[1]


def _label_name(domain: str) -> str:
    return f"domain:{domain}"


async def _get_label_by_name(name: str) -> Optional[ZohoLabel]:
    if name in _label_cache:
        return _label_cache[name]
    # Refresh cache from MCP server
    result = await zoho_mcp.call_tool("ZohoDesk_getLabels", {})
    labels = result.get("data") or result.get("labels") or []
    for item in labels:
        lbl = ZohoLabel(id=item["id"], name=item["name"], color=item.get("color"))
        _label_cache[lbl.name] = lbl
    return _label_cache.get(name)


async def _ensure_label(name: str) -> ZohoLabel:
    existing = await _get_label_by_name(name)
    if existing:
        return existing
    result = await zoho_mcp.call_tool("ZohoDesk_createLabel", {"name": name})
    item = result.get("data") or result
    lbl = ZohoLabel(id=item["id"], name=item["name"], color=item.get("color"))
    _label_cache[lbl.name] = lbl
    return lbl


async def apply_domain_label(ticket_id: str, contact_email: Optional[str]) -> Optional[str]:
    """
    Extracts domain from contact_email, ensures a matching label exists,
    and assigns it to the ticket. Returns the label name applied, or None if skipped.
    """
    if not contact_email:
        logger.info("domain_label_skipped", ticket_id=ticket_id, reason="no_email")
        return None

    domain = _extract_domain(contact_email)
    if not domain:
        logger.info("domain_label_skipped", ticket_id=ticket_id, reason="invalid_email", email=contact_email)
        return None

    if is_freemail(domain):
        logger.info("domain_label_skipped", ticket_id=ticket_id, reason="freemail", domain=domain)
        return None

    label_name = _label_name(domain)
    label = await _ensure_label(label_name)

    # Assign label to ticket via updateTicket (labelIds field)
    await zoho_mcp.call_tool("ZohoDesk_updateTicket", {
        "id": ticket_id,
        "labelIds": [label.id],
    })

    logger.info("domain_label_applied", ticket_id=ticket_id, domain=domain, label_id=label.id)
    return label_name

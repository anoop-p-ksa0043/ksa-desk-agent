from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel

from desk_agent.agent.runner import run_triage
from desk_agent.config import settings
from desk_agent.domain.freemail import is_freemail
from desk_agent.logging import logger


class DeskWebhookPayload(BaseModel):
    ticketId: str
    departmentId: Optional[str] = None
    contactEmail: Optional[str] = None   # Deluge passes this to avoid an extra fetch


async def _verify_secret(x_webhook_secret: Optional[str] = Header(default=None)) -> None:
    if x_webhook_secret is None or not secrets.compare_digest(
        x_webhook_secret, settings.webhook_secret
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")


def _extract_domain(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].lower()


async def _process_ticket(
    ticket_id: str,
    department_id: Optional[str],
    contact_email: Optional[str],
) -> None:
    log = logger.bind(ticket_id=ticket_id)
    try:
        domain = _extract_domain(contact_email)
        freemail = is_freemail(domain) if domain else False

        log.info(
            "triage_pipeline_started",
            ticket_id=ticket_id,
            domain=domain,
            is_freemail=freemail,
        )

        await run_triage(
            ticket_id=ticket_id,
            department_id=department_id or "",
            sender_domain=domain or "",
            is_freemail=freemail,
        )
    except Exception as exc:
        log.error("triage_pipeline_failed", error=str(exc), exc_info=True)


async def handle_desk_webhook(
    payload: DeskWebhookPayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_verify_secret),
) -> Dict[str, Any]:
    logger.info(
        "webhook_received",
        ticket_id=payload.ticketId,
        department_id=payload.departmentId,
    )
    background_tasks.add_task(
        _process_ticket,
        payload.ticketId,
        payload.departmentId,
        payload.contactEmail,
    )
    return {"status": "accepted", "ticketId": payload.ticketId}

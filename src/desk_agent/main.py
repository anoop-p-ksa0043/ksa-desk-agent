from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from desk_agent.config import settings
from desk_agent.logging import configure_logging, logger
from desk_agent.webhook import handle_desk_webhook
from desk_agent.zoho.mcp import zoho_mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    logger.info("startup", mcp_url=settings.zoho_mcp_url[:40] + "...")
    yield
    await zoho_mcp.close()
    logger.info("shutdown_complete")


app = FastAPI(title="Zoho Desk Triage Agent", version="0.1.0", lifespan=lifespan)

app.add_api_route(
    "/webhook/desk",
    handle_desk_webhook,
    methods=["POST"],
    status_code=202,
    summary="Receive Zoho Desk workflow trigger",
)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    zoho_mcp_url: str      # Zoho-hosted MCP server URL (auth token embedded in path)
    webhook_secret: str
    log_level: str = "INFO"
    claude_bin: str = "claude"   # path to claude CLI, override if not on PATH


settings = Settings()

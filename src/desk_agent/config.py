from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    zoho_mcp_url: str
    webhook_secret: str
    log_level: str = "INFO"
    claude_bin: str = "claude"

    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""


settings = Settings()

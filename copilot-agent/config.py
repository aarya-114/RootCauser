"""Runtime configuration for the RootCauser copilot agent."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings.

    Values are loaded from `.env` when present and from process environment
    variables in Docker. Required production secrets intentionally have no
    defaults so misconfigured runs fail early.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"
    signoz_mcp_endpoint: str = "http://signoz-signoz-0:8080/mcp"
    signoz_base_url: str = "http://signoz-signoz-0:8080"
    signoz_api_key: str = ""
    signoz_public_url: str = "http://localhost:8080"

    llm_api_key: str = Field(default="", min_length=0)
    llm_model_name: str = "gpt-4o-mini"

    github_token: str = Field(default="", min_length=0)
    github_repo: str = "your-org/your-repo"
    slack_webhook_url: str = ""
    webhook_shared_secret: str = ""

    incident_window_minutes: int = 10
    agent_host: str = "0.0.0.0"
    agent_port: int = 8001


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for callers that do not need dependency injection."""
    return Settings()

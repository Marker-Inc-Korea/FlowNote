from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import Request


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLOWNOTE_", env_file=".env", extra="ignore")

    environment: str = Field(
        default="local",
        validation_alias=AliasChoices("FLOWNOTE_ENVIRONMENT", "FLOWNOTE_ENV"),
    )
    api_host: str = "127.0.0.1"
    api_port: int = 5184
    database_url: str = "sqlite:///./data/flownote.sqlite3"
    test_database_url: str = "sqlite:///./data/flownote.test.sqlite3"
    database_echo: bool = False
    storage_root: str = "./storage"
    field_comment_attachment_max_bytes: int = 20 * 1024 * 1024
    controlled_copy_max_bytes: int = 500 * 1024 * 1024
    controlled_copy_ticket_expires_seconds: int = 60
    session_cookie_name: str = "flownote_session"
    access_token_secret: str = "flownote-local-dev-token-secret-change-before-operation"
    access_token_expires_minutes: int = 480
    refresh_token_expires_days: int = 14
    ai_external_call_enabled: bool = False
    ai_readiness_gate_enabled: bool = True
    ai_provider: str = "UNCONFIGURED"
    ai_model: str = "UNCONFIGURED"
    ai_customer_scope: str = "DEFAULT"
    ai_site_scope: str = "DEFAULT"
    ai_provider_excerpt_max_chars: int = Field(default=600, ge=100, le=4000)
    ai_provider_max_sources: int = Field(default=12, ge=1, le=100)
    ai_retention_scheduler_enabled: bool = True
    ai_retention_scheduler_interval_seconds: int = Field(default=3600, ge=60, le=86400)


settings = Settings()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings

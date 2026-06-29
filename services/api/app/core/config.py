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
    field_note_attachment_max_bytes: int = 20 * 1024 * 1024
    session_cookie_name: str = "flownote_session"
    access_token_secret: str = "flownote-local-dev-token-secret-change-before-operation"
    access_token_expires_minutes: int = 480


settings = Settings()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings

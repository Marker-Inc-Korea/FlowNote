from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    session_cookie_name: str = "flownote_session"


settings = Settings()

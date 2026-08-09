from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import Request


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLOWNOTE_", env_file=".env", extra="ignore", populate_by_name=True
    )

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
    android_view_grant_expires_seconds: int = 60
    android_view_auto_close_seconds: int = 300
    android_view_max_bytes: int = 50 * 1024 * 1024
    android_view_max_text_bytes: int = 5 * 1024 * 1024
    android_view_max_pdf_pages: int = 200
    session_cookie_name: str = "flownote_session"
    initial_admin_password: str = ""
    access_token_secret: str = "flownote-local-dev-token-secret-change-before-operation"
    access_token_expires_minutes: int = 480
    refresh_token_expires_days: int = 14
    customer_scope: str | None = None
    site_scope: str | None = None
    field_comment_independent_review_required: bool = True
    document_approval_workflow_enforced: bool = True
    document_approval_requester_reviewer_separation: bool | None = None
    document_approval_requester_publisher_separation: bool | None = None
    ai_external_call_enabled: bool = False
    ai_readiness_gate_enabled: bool = True
    ai_provider: str = "UNCONFIGURED"
    ai_model: str = "UNCONFIGURED"
    ai_customer_scope: str = "DEFAULT"
    ai_site_scope: str = "DEFAULT"
    ai_provider_excerpt_max_chars: int = Field(default=600, ge=100, le=4000)
    ai_provider_max_sources: int = Field(default=12, ge=1, le=100)
    ai_provider_adapter_mode: str = "DISABLED"
    ai_fake_scenarios: str = "SUCCESS"
    ai_provider_endpoint: str = ""
    ai_network_test_scope_enabled: bool = False
    ai_network_timeout_seconds: int = Field(default=30, ge=1, le=120)
    ai_provider_max_attempts: int = Field(default=3, ge=1, le=5)
    ai_provider_response_max_bytes: int = Field(default=65536, ge=1024, le=1048576)
    ai_retention_scheduler_enabled: bool = True
    ai_retention_scheduler_interval_seconds: int = Field(default=3600, ge=60, le=86400)
    restore_fault_code: str = ""
    restore_block_reason: str = ""
    restore_pilot_run_id: str = ""
    restore_backup_set_id: str = ""
    restore_approval_id: str = ""
    restore_responsible_owner: str = ""

    @model_validator(mode="after")
    def reject_public_example_secrets_outside_development(self) -> "Settings":
        environment = self.environment.strip().lower()
        if environment not in {"local", "test"}:
            forbidden_secrets = {
                "flownote-local-dev-token-secret-change-before-operation",
                "replace-with-a-long-site-specific-secret",
            }
            if self.access_token_secret in forbidden_secrets or len(self.access_token_secret) < 32:
                raise ValueError(
                    "FLOWNOTE_ACCESS_TOKEN_SECRET must be a site-specific secret of at least "
                    "32 characters outside local and test environments."
                )
        return self

    @property
    def effective_customer_scope(self) -> str:
        return (self.customer_scope or self.ai_customer_scope).strip()

    @property
    def effective_site_scope(self) -> str:
        return (self.site_scope or self.ai_site_scope).strip()


settings = Settings()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings

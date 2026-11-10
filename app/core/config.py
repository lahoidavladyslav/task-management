from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Example values in .env.example / docker-compose.yml contain this marker.
PLACEHOLDER_SECRET_MARKER = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Task Management API"
    environment: Literal["development", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str
    db_echo: bool = False

    secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    max_active_tasks_per_user: int = 10

    docs_enabled: bool = True

    rate_limit_enabled: bool = True
    auth_rate_limit_attempts: int = Field(default=60, ge=1)
    auth_rate_limit_window_seconds: float = Field(default=60, gt=0)

    overdue_worker_enabled: bool = True
    overdue_check_interval_seconds: float = 60

    @field_validator("secret_key")
    @classmethod
    def _secret_key_must_be_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters long")
        return value

    @property
    def uses_placeholder_secret(self) -> bool:
        return PLACEHOLDER_SECRET_MARKER in self.secret_key.get_secret_value().lower()

    @model_validator(mode="after")
    def _production_requires_real_secret(self) -> "Settings":
        if self.environment == "production" and self.uses_placeholder_secret:
            raise ValueError(
                "SECRET_KEY is still a placeholder value; set a long random secret "
                "(for example: python -c 'import secrets; print(secrets.token_urlsafe(48))')"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

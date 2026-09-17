from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_SECRET = "super-secret-key-change-in-production"  # noqa: S105


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://fabbi:fabbi_secret@localhost:5432/postgres"
    )
    # Echoing every statement leaks row data into stdout and is a large
    # throughput hit, so it is opt-in rather than on by default.
    DB_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str = INSECURE_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS: comma-separated list of allowed browser origins.
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in {"production", "prod"}

    @field_validator("CORS_ORIGINS")
    @classmethod
    def reject_wildcard_origin(cls, value: str) -> str:
        # "*" cannot be combined with credentialed requests; browsers reject the
        # pair and it would make every site a trusted origin.
        if "*" in value:
            raise ValueError(
                "CORS_ORIGINS must list explicit origins; '*' is not allowed "
                "because the API is used with credentials."
            )
        return value

    @model_validator(mode="after")
    def require_real_secret_in_production(self) -> "Settings":
        if self.is_production and self.JWT_SECRET == INSECURE_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET is still the shipped default. Set a unique secret "
                "before running with ENVIRONMENT=production."
            )
        return self


settings = Settings()

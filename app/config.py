from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    api_keys: str = ""
    cron_secret: str = ""
    cors_origins: str = ""

    @property
    def sqlalchemy_database_url(self) -> str:
        # asyncpg needs the "postgresql+asyncpg://" scheme and doesn't accept
        # a "sslmode" query param the way psycopg2 does — SSL is passed via
        # connect_args instead (see app/db.py).
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        if "?" in url:
            url = url.split("?", 1)[0]
        return url

    @property
    def api_key_set(self) -> set[str]:
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

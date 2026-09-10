from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    api_keys: str = ""
    cron_secret: str = ""
    cors_origins: str = ""

    # Si es False, iniciar producción NO valida que haya stock físico
    # suficiente para las líneas de insumo de la orden: la RESERVA (al
    # generar) y el CONSUMO (al iniciar) se siguen registrando igual, así que
    # el insumo puede quedar en negativo.
    #
    # Está en False a propósito: pedido explícito del usuario para no frenar
    # producción mientras el stock cargado no refleja la realidad. Es un
    # estado temporal — se vuelve a prender con
    # STOCK_FALTANTES_BLOQUEA_INICIO=true, sin tocar código.
    stock_faltantes_bloquea_inicio: bool = False
    # MOTOR_GRAFO=true hace que el preview y la generación exploten la receta por
    # el grafo de procesos en vez de por `costos` + `producto_base_id`. Arranca
    # apagado a propósito: cambia lo que se reserva de insumos, y el criterio
    # para prenderlo es el reporte de comparación de F3
    # (masa-procesos-y-maquinaria, tareas 5.9 y 5.14).
    motor_grafo: bool = False

    secret_key: str = ""
    access_token_expire_days: int = 7
    base_url: str = "http://localhost:8000"
    frontend_urls: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""

    @property
    def frontend_urls_set(self) -> set[str]:
        return {u.strip().rstrip("/") for u in self.frontend_urls.split(",") if u.strip()}

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

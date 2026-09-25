from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central config. Every value here is overridden by an env var of the
    same name (case-insensitive) — see .env.example.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    app_name: str = "Strata"
    environment: str = "development"

    # --- Database ---
    # postgresql+asyncpg://user:password@host:port/dbname
    database_url: str

    # --- Auth ---
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- Redis (used later for caching / worker queue) ---
    redis_url: str = "redis://localhost:6379/0"


# Import this singleton everywhere instead of re-instantiating Settings()
settings = Settings()

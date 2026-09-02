"""
Application settings.

Everything configurable lives here and is loaded from environment variables
(or a local `.env` file). Import the shared `settings` object anywhere you need
a value; it is created once and reused.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load values from a `.env` file sitting next to the backend, and ignore
    # any extra env vars we don't explicitly declare.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Security ---
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    DEVICE_TOKEN_EXPIRE_DAYS: int = 3650

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./sentinel.db"

    # --- Evidence storage ---
    # Where failed-unlock photos are written on disk. Kept out of the static
    # folder on purpose: photos are served only through an authenticated,
    # owner-gated endpoint, never as public static files.
    EVIDENCE_DIR: str = "./evidence"
    MAX_PHOTO_BYTES: int = 5 * 1024 * 1024   # 5 MB upload cap

    # --- First super admin (used only by seed.py) ---
    FIRST_SUPERADMIN_EMAIL: str = "admin@example.com"
    FIRST_SUPERADMIN_PASSWORD: str = "change-me-now"

    # --- Deployment ---
    # "dev" or "production". In production we do NOT auto-create tables on
    # startup; Alembic migrations own the schema instead.
    ENVIRONMENT: str = "dev"

    # Comma-separated list of browser origins allowed to call the API (the
    # dashboard's URL). "*" allows any origin — fine for local dev, but set a
    # real value in production.
    CORS_ORIGINS: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def sqlalchemy_url(self) -> str:
        """Normalize the DB URL so it uses our installed driver (psycopg v3).

        Hosts like Render/Heroku hand out 'postgres://' or 'postgresql://' URLs,
        which SQLAlchemy would route to psycopg2 (not installed). Rewrite them to
        the explicit 'postgresql+psycopg://' form.
        """
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


# A single shared instance used across the app.
settings = Settings()

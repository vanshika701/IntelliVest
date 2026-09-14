from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, loaded from environment variables / .env.

    Every setting has a sane local-dev default so the app runs out of the
    box; production deployments override these via real env vars, never by
    editing this file.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "IntelliVest AI"
    environment: str = "development"
    log_level: str = "INFO"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "intellivest"

    # Off in tests (see tests/conftest.py) so the test suite doesn't spin
    # up a real background scheduler on every TestClient-based test.
    enable_scheduler: bool = True

    # Frontend origins allowed to call this API (CORS)
    cors_origins: list[str] = ["http://localhost:5173"]

    # JWT authentication — Phase 2
    jwt_secret_key: str = "CHANGE-ME-IN-PRODUCTION-USE-A-REAL-SECRET"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 24 hours for dev convenience

    # External API keys — needed from Phase 1 onward, optional for now so
    # the app still boots without them during Phase 0.
    news_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None


settings = Settings()

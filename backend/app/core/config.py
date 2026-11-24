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

    # Phase 5 sentiment model: a Hugging Face model id, or a local path to
    # a fine-tuned checkpoint. Changing it makes the scoring job re-score
    # every article with the new model.
    sentiment_model: str = "ProsusAI/finbert"

    # Phase 5 news summaries. "extractive" = classical baseline; "ml" = our
    # trained model (placeholder until it exists, see summarization/ml.py).
    summarizer_provider: str = "extractive"
    summarizer_max_words: int = 100
    summarizer_cache_ttl_min: int = 60
    ml_summarizer_url: str | None = None
    # Append (article text, summary, method, version) lines to a JSONL file
    # to build evaluation/training data for the trained model.
    log_summaries: bool = False
    # Relative paths resolve against the repo root.
    summary_log_path: str = "data/summarization_log.jsonl"

    # Phase 8 budget explanations. "template" (default) = the engine's own
    # sentences; "anthropic" = Claude rephrases them (needs `pip install
    # anthropic` and ANTHROPIC_API_KEY). Numbers always come from the engine.
    budget_explainer_provider: str = "template"
    budget_explainer_model: str = "claude-opus-5-5"

    # External API keys — needed from Phase 1 onward, optional for now so
    # the app still boots without them during Phase 0.
    alpha_vantage_api_key: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None


settings = Settings()

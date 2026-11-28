from pydantic import SecretStr
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

    # Phase 5 sentiment model (the default): a Hugging Face model id, or a
    # local path to a fine-tuned checkpoint. Changing it makes the scoring
    # job re-score every article with the new model. DistilRoBERTa won the
    # 2026-11-28 comparison (ml/compare_sentiment_models.py, ml/log.md).
    sentiment_model: str = "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis"
    # Other models users can pick on the instrument page, comma-separated.
    # Each is loaded and scores every article too, so each costs memory and time.
    sentiment_extra_models: str = "ProsusAI/finbert"

    # Phase 5 news summaries: the default summarizer (users can pick any in
    # summarization/factory.py SUMMARIZERS). T5-small won the 2026-11-28
    # comparison (ml/compare_summarizers.py); "extractive" is the classical
    # baseline; "ml" = our own model server (placeholder, see summarization/ml.py).
    summarizer_provider: str = "t5-small"
    summarizer_max_words: int = 100
    summarizer_cache_ttl_min: int = 60
    ml_summarizer_url: str | None = None
    # Append (article text, summary, method, version) lines to a JSONL file
    # to build evaluation/training data for the trained model.
    log_summaries: bool = False
    # Relative paths resolve against the repo root.
    summary_log_path: str = "data/summarization_log.jsonl"

    # Phase 4 stock predictor, made by ml/train_stock_predictor.py; its
    # metrics.json sits next to it. Relative paths resolve against the repo root.
    stock_predictor_path: str = "ml/models/stock_predictor/model.joblib"
    # The LSTM + LightGBM ensemble (4.0.0), made by ml/train_hybrid_lstm_lightgbm.py --final.
    stock_predictor_ensemble_path: str = "ml/models/stock_predictor_hybrid/model.joblib"
    # Which one users get unless they pick the other: "lstm_lgbm" or "lgbm".
    prediction_model: str = "lstm_lgbm"

    # Phase 8 budget explanations. "template" (default) = the engine's own
    # sentences; "groq" or "gemini" = a free-tier LLM rephrases them, if its key
    # is set. Numbers always come from the engine.
    budget_explainer_provider: str = "template"
    budget_explainer_model: str = ""  # empty = the provider's default
    groq_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

    # Phase 10 blockchain. Off by default; nothing below is used until it is
    # on. Checked at startup by app/services/blockchain/config.py. Test
    # networks only.
    blockchain_enabled: bool = False
    blockchain_rpc_url: str = "http://127.0.0.1:8545"
    blockchain_chain_id: int = 31337
    # Relative paths resolve against the repo root.
    blockchain_deployment_path: str = "blockchain/deployments/local.json"
    # One key per role, so one leaked key can't act for the others.
    blockchain_sentiment_private_key: SecretStr | None = None
    blockchain_stock_private_key: SecretStr | None = None
    blockchain_advisor_private_key: SecretStr | None = None
    blockchain_relayer_private_key: SecretStr | None = None
    blockchain_sip_runner_private_key: SecretStr | None = None
    # Model versions registered on chain for each signer (see
    # backend/scripts/register_models.py). Unset: that evidence step is skipped.
    blockchain_sentiment_model_version: str | None = None
    blockchain_stock_model_version: str | None = None
    # Blocks to wait before trusting an event (0 locally; a few on a testnet).
    blockchain_confirmations: int = 0
    # Where the event reader starts: the deployment block on a testnet.
    blockchain_start_block: int = 0

    # External API keys — needed from Phase 1 onward, optional for now so
    # the app still boots without them during Phase 0.
    alpha_vantage_api_key: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None


settings = Settings()

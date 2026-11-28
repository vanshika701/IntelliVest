"""The only place that knows about concrete summarizer implementations.

SUMMARIZER_PROVIDER picks the default; users can pick any key in
SUMMARIZERS per request (the model picker on the instrument page).
Results of the 2026-11-28 comparison (ml/compare_summarizers.py) are in
ml/log.md and the README.
"""

from functools import lru_cache

from app.core.config import settings
from app.services.summarization.base import Summarizer
from app.services.summarization.extractive import ExtractiveSummarizer
from app.services.summarization.huggingface import HuggingFaceSummarizer
from app.services.summarization.ml import MlSummarizer

# key -> (label, description, Hugging Face id or None, max input tokens, prefix)
SUMMARIZERS: dict[str, tuple[str, str, str | None, int, str]] = {
    "extractive": ("Extractive (TF-IDF)", "Picks the key sentences from the articles; instant", None, 0, ""),
    "distilbart": (
        "DistilBART",
        "BART distilled, trained on CNN/DailyMail news; about 13 s per summary on CPU",
        "sshleifer/distilbart-cnn-12-6",
        1024,
        "",
    ),
    "bart-large-cnn": (
        "BART-large",
        "Trained on CNN/DailyMail news; about 18 s per summary on CPU",
        "facebook/bart-large-cnn",
        1024,
        "",
    ),
    "pegasus-financial": (
        "PEGASUS (financial)",
        "Fine-tuned on financial news; short, headline-like; about 15 s per summary on CPU",
        "human-centered-summarization/financial-summarization-pegasus",
        512,
        "",
    ),
    "t5-small": (
        "T5-small",
        "Best ROUGE and figure accuracy in our test; about 6 s per summary on CPU",
        "Falconsai/text_summarization",
        512,
        "summarize: ",
    ),
}
# "ml" (our own trained model behind a server) stays selectable by config only.
PROVIDERS = (*SUMMARIZERS, "ml")


class UnknownSummarizer(ValueError):
    """A summarizer key that isn't in PROVIDERS."""


@lru_cache(maxsize=len(PROVIDERS))
def _build(provider: str) -> Summarizer:
    if provider == "extractive":
        return ExtractiveSummarizer()
    if provider == "ml":
        return MlSummarizer(settings.ml_summarizer_url)
    if provider in SUMMARIZERS:
        _, _, model_id, max_tokens, prefix = SUMMARIZERS[provider]
        return HuggingFaceSummarizer(model_id, max_tokens, prefix)
    raise UnknownSummarizer(f"Unknown SUMMARIZER_PROVIDER or model {provider!r}; expected one of {', '.join(PROVIDERS)}")


def default_summarizer() -> str:
    return settings.summarizer_provider.strip().lower()


def get_summarizer(provider: str | None = None) -> Summarizer:
    """The summarizer `provider` names (default: SUMMARIZER_PROVIDER)."""
    return _build((provider or default_summarizer()).strip().lower())


def available_summarizers() -> list[dict]:
    default = default_summarizer()
    return [
        {
            "key": key,
            "label": label,
            "description": description,
            "version": model_id,
            "available": True,
            "default": key == default,
        }
        for key, (label, description, model_id, _, _) in SUMMARIZERS.items()
    ]

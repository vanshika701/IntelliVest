"""Placeholder for OUR trained summarization model (final submission).

TODO(ml-model): implement `summarize`. Two supported deployment options:

1. Model server (recommended — keeps torch/model weights out of the API
   process). Serve the fine-tuned seq2seq model (BART/T5/Pegasus) with a
   small FastAPI app and set ML_SUMMARIZER_URL to it. Expected contract:

       POST {ML_SUMMARIZER_URL}/summarize
       request:  {"items": [{"id": "0", "title": "...", "text": "...", "max_words": 100}]}
       response: {"model": "bart-base-finetuned-indian-fin-news",
                  "model_version": "2026-12-01",
                  "items": [{"id": "0", "summary": "..."}]}
       errors:   non-2xx -> whole request failed; an item may instead carry
                 {"id": "0", "error": "..."} to fail just that item.

   Override `summarize_batch` to send all items in one request (the
   service calls it with up to 5 articles), mapping per-item errors to
   SummaryFailure so one bad article doesn't fail the rest.

2. In-process: load the model once in __init__ (e.g. transformers
   `AutoModelForSeq2SeqLM` from ml/models/<name>) and generate directly.

Whichever option: pass each output through `trim_to_words(summary,
item.max_words)` (textutils) so the <= max_words guarantee holds even if
generation overshoots, set `method` to include the model version (it is
part of the cache key), and report latency. Then set
SUMMARIZER_PROVIDER=ml and compare against the extractive baseline with
`python -m scripts.eval_summarizer --provider ml --references ...`.
"""

from app.services.summarization.base import Summarizer, SummaryInput, SummaryResult


class MlSummarizer(Summarizer):
    provider = "ml"

    def __init__(self, endpoint_url: str | None, timeout_seconds: float = 20.0) -> None:
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self.method = "ml-model@unreleased"

    def summarize(self, item: SummaryInput) -> SummaryResult:
        raise NotImplementedError(
            "MlSummarizer is a placeholder until our trained model is ready — see this module's "
            "docstring for the contract. Use SUMMARIZER_PROVIDER=extractive meanwhile."
        )

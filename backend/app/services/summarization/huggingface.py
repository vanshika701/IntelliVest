"""Pretrained Hugging Face summarization models, run in-process (Phase 5).

The models compared in ml/compare_summarizers.py, behind the same
Summarizer interface as the extractive baseline, so the news digest can
use any of them. Weights download into ml/models/hf_cache/ on first use.

Only one of these models is kept in memory at a time (the largest needs
about 2.3 GB): picking another unloads the previous one. Generation uses
the same settings as the comparison, and the output always goes through
trim_to_words so the word limit holds.
"""

import os
import threading
import time
from pathlib import Path

from app.services.summarization.base import Summarizer, SummaryInput, SummaryResult
from app.services.summarization.textutils import count_words, first_words, trim_to_words

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# English news runs about 1.3 tokens per word; a little slack for the prefix.
WORDS_PER_TOKEN = 0.7

_CACHE_DIR = Path(__file__).resolve().parents[4] / "ml" / "models" / "hf_cache"
_lock = threading.Lock()
# (model id, tokenizer, model) of the one model in memory.
_current: tuple[str, object, object] | None = None


def _load(model_id: str) -> tuple[object, object]:
    global _current
    with _lock:
        if _current is None or _current[0] != model_id:
            _current = None  # free the previous model before loading the next
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=_CACHE_DIR)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_id, cache_dir=_CACHE_DIR).eval()
            _current = (model_id, tokenizer, model)
        return _current[1], _current[2]


class HuggingFaceSummarizer(Summarizer):
    provider = "huggingface"

    def __init__(self, model_id: str, max_input_tokens: int, prefix: str = "") -> None:
        self.model_id = model_id
        self.max_input_tokens = max_input_tokens
        self.prefix = prefix  # T5-style models need a task prefix
        self.method = f"hf:{model_id}"

    def input_text(self, item: SummaryInput) -> str:
        """What the model reads. These models see only their first
        max_input_tokens (512 tokens is about 380 words), so for the
        multi-article digest each article gets an equal share of its opening
        words (leads carry the key facts); otherwise only the first one or
        two articles would ever be summarized."""
        documents = [d for d in item.documents if d.strip()]
        if len(documents) < 2:
            return item.text.strip() or item.title
        budget = max(40, int(self.max_input_tokens * WORDS_PER_TOKEN) // len(documents))
        return "\n".join(first_words(d, budget) for d in documents)

    def summarize(self, item: SummaryInput) -> SummaryResult:
        import torch

        began = time.perf_counter()
        text = self.input_text(item)
        tokenizer, model = _load(self.model_id)
        inputs = tokenizer(
            self.prefix + text, truncation=True, max_length=self.max_input_tokens, return_tensors="pt"
        )
        with _lock, torch.inference_mode():
            ids = model.generate(
                **inputs,
                num_beams=4,
                max_new_tokens=160,
                min_new_tokens=30,
                no_repeat_ngram_size=3,
                early_stopping=True,
            )
        raw = tokenizer.decode(ids[0], skip_special_tokens=True).replace("<n>", " ")
        summary = trim_to_words(" ".join(raw.split()), item.max_words)
        return SummaryResult(
            summary=summary,
            word_count=count_words(summary),
            provider=self.provider,
            method=self.method,
            latency_ms=(time.perf_counter() - began) * 1000,
        )

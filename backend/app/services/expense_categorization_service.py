"""Service layer for ML-based expense categorization (Phase 3).

Loads the artifact trained offline by ml/train_expense_categorizer.py —
this module never trains anything itself, it only loads and predicts,
per the "training happens offline, the trained model is saved as an
artifact and loaded by the backend service layer at inference time"
pattern every ML phase in this project follows.

Paper/dataset grounding: mitulshah/transaction-categorization (Hugging
Face, MIT license), benchmarked against DFTSen (Discover Artificial
Intelligence, Springer, 2026) — see ml/train_expense_categorizer.py and
the generated metrics.json for full details.
"""

import json
import logging
from pathlib import Path

import joblib

logger = logging.getLogger(__name__)

# backend/app/services/this_file.py -> parents[3] is the repo root, next
# to ml/ — backend and ml are sibling top-level directories.
_MODEL_DIR = Path(__file__).resolve().parents[3] / "ml" / "models" / "expense_categorizer"

_vectorizer = None
_model = None
_model_info: dict | None = None
_load_attempted = False


def _load_artifacts() -> None:
    """Load the vectorizer/model/metrics once, on first use.

    If the artifacts don't exist yet (e.g. a teammate cloned the repo
    but hasn't run the training script), this logs a clear warning once
    and leaves categorization unavailable — callers fall back to
    "Uncategorized" rather than the app crashing or every expense
    create/CSV-import request failing.
    """
    global _vectorizer, _model, _model_info, _load_attempted
    if _load_attempted:
        return
    _load_attempted = True

    vectorizer_path = _MODEL_DIR / "vectorizer.joblib"
    model_path = _MODEL_DIR / "model.joblib"
    metrics_path = _MODEL_DIR / "metrics.json"

    if not (vectorizer_path.exists() and model_path.exists()):
        logger.warning(
            "Expense categorization model not found at %s — auto-categorization "
            "disabled, expenses will fall back to 'Uncategorized'. Run "
            "`python3 ml/train_expense_categorizer.py` to generate it.",
            _MODEL_DIR,
        )
        return

    _vectorizer = joblib.load(vectorizer_path)
    _model = joblib.load(model_path)
    if metrics_path.exists():
        _model_info = json.loads(metrics_path.read_text())
    logger.info("Expense categorization model loaded from %s", _MODEL_DIR)


def is_available() -> bool:
    _load_artifacts()
    return _model is not None


def predict_category(description: str) -> tuple[str, float] | None:
    """Predict a category for a transaction description.

    Returns (category, confidence) or None if the model isn't available
    — callers must handle the None case by falling back to a default
    category rather than assuming this always succeeds.
    """
    _load_artifacts()
    if _model is None or _vectorizer is None:
        return None

    cleaned = description.strip().lower()
    features = _vectorizer.transform([cleaned])
    category = _model.predict(features)[0]
    confidence = float(_model.predict_proba(features).max())
    return category, confidence


def get_model_info() -> dict | None:
    """Return the training-time metrics — this is the "visible accuracy
    metric" Phase 3's exit criteria calls for. None if the model hasn't
    been trained yet."""
    _load_artifacts()
    return _model_info

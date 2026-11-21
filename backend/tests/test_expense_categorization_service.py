"""Tests for the ML expense-categorization service.

Two kinds of test here, deliberately kept separate:
1. Hermetic unit tests of the graceful-degradation path (model missing)
   — these must pass in any environment, including a fresh clone where
   nobody has run ml/train_expense_categorizer.py yet.
2. An integration test against the real trained artifact, skipped
   automatically if it isn't present, so CI/fresh clones don't fail on
   a training step this test suite was never meant to require.
"""

import pytest

from app.services import expense_categorization_service as svc


@pytest.fixture(autouse=True)
def reset_service_state(monkeypatch: pytest.MonkeyPatch):
    """Each test gets a clean slate — the service caches the loaded
    model in module globals, which would otherwise leak between tests."""
    monkeypatch.setattr(svc, "_vectorizer", None)
    monkeypatch.setattr(svc, "_model", None)
    monkeypatch.setattr(svc, "_model_info", None)
    monkeypatch.setattr(svc, "_load_attempted", False)


def test_predict_category_returns_none_when_model_directory_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(svc, "_MODEL_DIR", tmp_path / "does-not-exist")

    assert svc.is_available() is False
    assert svc.predict_category("Starbucks - USA Store") is None
    assert svc.get_model_info() is None


def test_predict_category_uses_the_real_trained_model_if_present() -> None:
    if not svc.is_available():
        pytest.skip(
            "Model not trained on this machine — run "
            "ml/train_expense_categorizer.py to enable this test."
        )

    result = svc.predict_category("Starbucks Coffee - USA Branch")
    assert result is not None
    category, confidence = result
    assert isinstance(category, str)
    assert 0.0 <= confidence <= 1.0

    info = svc.get_model_info()
    assert info is not None
    assert "selected_model" in info
    assert 0.0 <= info["models_compared"][info["selected_model"]]["accuracy"] <= 1.0

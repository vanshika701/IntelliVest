"""Which models users can pick for predictions, sentiment and summaries."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id
from app.schemas.models import ModelCatalog
from app.services.prediction_service import available_models
from app.services.sentiment_service import available_sentiment_models
from app.services.summarization.factory import available_summarizers

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(get_current_user_id)])


@router.get("", response_model=ModelCatalog)
async def list_models():
    """Every selectable model per feature; `default` marks the one used
    when a request names none (the best in our comparisons, see README)."""
    return {
        "prediction": available_models(),
        "sentiment": available_sentiment_models(),
        "summarizer": available_summarizers(),
    }

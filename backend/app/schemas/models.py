"""Schemas for the model catalog (GET /models)."""

from pydantic import BaseModel


class ModelOption(BaseModel):
    key: str  # what to pass as ?model=
    label: str
    description: str
    version: str | None = None
    # False: the model's file isn't on this server (e.g. not trained yet).
    available: bool
    default: bool


class ModelCatalog(BaseModel):
    prediction: list[ModelOption]
    sentiment: list[ModelOption]
    summarizer: list[ModelOption]

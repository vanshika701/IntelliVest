"""Phase 8 routes: budget setup, rule-based analysis, savings goals."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id
from app.core.budget_config import CATEGORY_BY_ID
from app.schemas.budget import Basis, BudgetProfileIn, ExplainIn, GoalIn
from app.services import budget_service

router = APIRouter(prefix="/budget", tags=["budget"])

_NO_PROFILE = "Set up your budget first (monthly income and estimates)."


@router.get("/categories")
async def get_categories():
    """The fixed category list, benchmarks and assumptions (from budget_config)."""
    return budget_service.categories_meta()


@router.get("/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    profile = await budget_service.get_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_PROFILE)
    return {**profile, "warnings": budget_service.profile_warnings(profile)}


@router.put("/profile")
async def put_profile(body: BudgetProfileIn, user_id: str = Depends(get_current_user_id)):
    profile = await budget_service.save_profile(user_id, body.model_dump())
    return {**profile, "warnings": budget_service.profile_warnings(profile)}


@router.get("/overview")
async def get_overview(user_id: str = Depends(get_current_user_id)):
    return await budget_service.overview(user_id)


@router.get("/analysis")
async def get_analysis(basis: Basis = "auto", user_id: str = Depends(get_current_user_id)):
    result = await budget_service.analysis(user_id, basis)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_PROFILE)
    return result


@router.get("/health-score")
async def get_health_score(user_id: str = Depends(get_current_user_id)):
    return await budget_service.get_health_score(user_id)


@router.get("/improve")
async def get_improve(
    focus: str = Query("all", description="Category id, or 'all' for the whole budget"),
    basis: Basis = "auto",
    user_id: str = Depends(get_current_user_id),
):
    if focus != "all" and focus not in CATEGORY_BY_ID:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown category")
    result = await budget_service.improve(user_id, focus, basis)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_PROFILE)
    return result


@router.get("/goals")
async def get_goals(user_id: str = Depends(get_current_user_id)):
    return await budget_service.list_goals(user_id)


@router.post("/goals", status_code=status.HTTP_201_CREATED)
async def create_goal(body: GoalIn, user_id: str = Depends(get_current_user_id)):
    return await budget_service.create_goal(user_id, body.model_dump())


@router.post("/goals/preview")
async def preview_goal(body: GoalIn, goal_id: str | None = None, user_id: str = Depends(get_current_user_id)):
    """Compute a plan without saving it (used while the user tweaks
    inputs). `goal_id` is the saved goal being edited, if any."""
    return await budget_service.preview_goal(user_id, body.model_dump(), goal_id)


@router.put("/goals/{goal_id}")
async def update_goal(goal_id: str, body: GoalIn, user_id: str = Depends(get_current_user_id)):
    updated = await budget_service.update_goal(user_id, goal_id, body.model_dump())
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return updated


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(goal_id: str, user_id: str = Depends(get_current_user_id)):
    if not await budget_service.delete_goal(user_id, goal_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")


@router.post("/explain")
async def explain(body: ExplainIn, user_id: str = Depends(get_current_user_id)):
    """Plain-language version of the engine's output (template, or LLM if enabled)."""
    if body.kind == "improve" and body.focus not in (None, "all") and body.focus not in CATEGORY_BY_ID:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown category")
    result = await budget_service.explain(user_id, body.kind, body.focus, body.goal_id, body.basis)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nothing to explain yet")
    return result

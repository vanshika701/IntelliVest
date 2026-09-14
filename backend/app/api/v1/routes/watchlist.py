"""Watchlist routes — add, list (enriched with prices), update notes, remove."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemResponse, WatchlistItemUpdate
from app.services.watchlist_service import add_to_watchlist, get_enriched_watchlist, remove_item, update_item

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemResponse])
async def get_watchlist(user_id: str = Depends(get_current_user_id)):
    return await get_enriched_watchlist(user_id)


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_item(body: WatchlistItemCreate, user_id: str = Depends(get_current_user_id)):
    item_id = await add_to_watchlist(user_id, body.model_dump())
    if item_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{body.ticker} is already in your watchlist",
        )
    return {"id": item_id}


@router.patch("/{item_id}")
async def patch_item(
    item_id: str, body: WatchlistItemUpdate, user_id: str = Depends(get_current_user_id)
):
    updated = await update_item(user_id, item_id, body.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return {"status": "updated"}


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: str, user_id: str = Depends(get_current_user_id)):
    deleted = await remove_item(user_id, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

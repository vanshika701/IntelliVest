"""Alert routes — create, list, toggle, delete price proximity alerts."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas.alert import AlertCreate, AlertResponse
from app.services.alert_service import add_alert, list_alerts, remove_alert, toggle

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
async def get_alerts(user_id: str = Depends(get_current_user_id)):
    return await list_alerts(user_id)


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_alert_route(body: AlertCreate, user_id: str = Depends(get_current_user_id)):
    alert_id = await add_alert(user_id, body.model_dump())
    return {"id": alert_id}


@router.patch("/{alert_id}/toggle")
async def toggle_alert(alert_id: str, is_active: bool, user_id: str = Depends(get_current_user_id)):
    updated = await toggle(user_id, alert_id, is_active)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return {"status": "toggled", "is_active": is_active}


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_route(alert_id: str, user_id: str = Depends(get_current_user_id)):
    deleted = await remove_alert(user_id, alert_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

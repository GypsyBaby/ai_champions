from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_employee

router = APIRouter()


@router.get("/notifications", response_model=list[schemas.NotificationRead])
def list_notifications(
    type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    q = db.query(models.Notification).filter(models.Notification.recipient_id == employee.id)
    if type:
        q = q.filter(models.Notification.type == type)
    return q.order_by(models.Notification.created_at.desc()).all()


@router.post("/notifications/{notification_id}/read", response_model=schemas.NotificationRead)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    obj = db.query(models.Notification).get(notification_id)
    if not obj or obj.recipient_id != employee.id:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    obj.is_read = True
    db.commit()
    db.refresh(obj)
    return obj

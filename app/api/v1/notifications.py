"""
Notification API endpoints.

Mounted at /api/v1/notifications (registered in main.py).

Endpoints:
- GET    /notifications                  — list current user's notifications (paginated)
- GET    /notifications/unread-count     — badge count for bell icon
- POST   /notifications/{id}/read        — mark one as read
- POST   /notifications/read-all         — mark all as read
- DELETE /notifications/{id}             — delete one
- DELETE /notifications/clear-all        — delete all read notifications

All endpoints require authentication and scope to current user_id.
"""
from __future__ import annotations

from datetime import datetime
from app.core.security import utcnow
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ===== Pydantic schemas =====

class NotificationOut(BaseModel):
    id: int
    event_type: str
    title: str
    message: str
    icon: str
    link: Optional[str] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int
    page: int
    per_page: int


class UnreadCountOut(BaseModel):
    unread_count: int


# ===== Endpoints =====

@router.get("", tags=['Notifications'], response_model=NotificationListOut)
def list_notifications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False, description="If true, only return unread notifications"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List notifications for current authenticated user.
    Newest first. Paginated.
    """
    base = db.query(Notification).filter(Notification.user_id == current_user["id"])
    if unread_only:
        base = base.filter(Notification.is_read == False)  # noqa: E712

    total = base.count()
    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user["id"], Notification.is_read == False)  # noqa: E712
        .count()
    )

    items = (
        base.order_by(Notification.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
        unread_count=unread_count,
        page=page,
        per_page=per_page,
    )


@router.get("/unread-count", tags=['Notifications'], response_model=UnreadCountOut)
def get_unread_count(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Quick count for the bell badge — no pagination needed."""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user["id"], Notification.is_read == False)  # noqa: E712
        .count()
    )
    return UnreadCountOut(unread_count=count)


@router.post("/{notification_id}/read", tags=['Notifications'], response_model=NotificationOut)
def mark_as_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a single notification as read. Idempotent."""
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user["id"])
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not notif.is_read:
        notif.is_read = True
        notif.read_at = utcnow()
        db.commit()
        db.refresh(notif)

    return NotificationOut.model_validate(notif)


@router.post("/read-all", tags=['Notifications'])
def mark_all_as_read(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all current user's notifications as read."""
    now = utcnow()
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == current_user["id"], Notification.is_read == False)  # noqa: E712
        .update({"is_read": True, "read_at": now}, synchronize_session=False)
    )
    db.commit()
    return {"marked_read": updated}


@router.delete("/{notification_id}", tags=['Notifications'])
def delete_notification(
    notification_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a single notification (user-owned)."""
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user["id"])
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.delete(notif)
    db.commit()
    return {"deleted": True, "id": notification_id}


@router.delete("/clear-all", tags=['Notifications'])
def clear_read_notifications(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete all read notifications for current user. Keeps unread."""
    deleted = (
        db.query(Notification)
        .filter(Notification.user_id == current_user["id"], Notification.is_read == True)  # noqa: E712
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}
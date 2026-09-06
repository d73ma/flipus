"""
Notification service — create and manage in-app notifications.

Centralized so we don't sprinkle Notification() construction across
the codebase. All callers go through `create_notification` or
`create_notifications_bulk`.

Design notes:
- `create_notification` is the single entry point for emitting events.
- `actor_user_id` lets us skip self-notifications (e.g. admin who
  approves doesn't need a "you approved" ping).
- TTL/cleanup is handled by APScheduler job, not here.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.notification import Notification

logger = logging.getLogger(__name__)


# Event-type constants (single source of truth, referenced by frontend too)
class EventType:
    KUITANSI_APPROVED = "KUITANSI_APPROVED"
    KUITANSI_REJECTED = "KUITANSI_REJECTED"
    KUITANSI_DRAFT_CREATED = "KUITANSI_DRAFT_CREATED"
    WEEKLY_BLAST_DONE = "WEEKLY_BLAST_DONE"
    BACKUP_COMPLETED = "BACKUP_COMPLETED"
    BACKUP_FAILED = "BACKUP_FAILED"
    PENDETA_REGISTERED = "PENDETA_REGISTERED"
    AUDITOR_REGISTERED = "AUDITOR_REGISTERED"
    ADMIN_REGISTERED = "ADMIN_REGISTERED"
    TENANT_SUSPENDED = "TENANT_SUSPENDED"
    TENANT_ACTIVATED = "TENANT_ACTIVATED"


# Icon helpers per event type (single source of truth)
EVENT_ICONS = {
    EventType.KUITANSI_APPROVED: "✅",
    EventType.KUITANSI_REJECTED: "❌",
    EventType.KUITANSI_DRAFT_CREATED: "📝",
    EventType.WEEKLY_BLAST_DONE: "�",
    EventType.BACKUP_COMPLETED: "💾",
    EventType.BACKUP_FAILED: "⚠️",
    EventType.PENDETA_REGISTERED: "⛪",
    EventType.AUDITOR_REGISTERED: "🔍",
    EventType.ADMIN_REGISTERED: "�",
    EventType.TENANT_SUSPENDED: "🚫",
    EventType.TENANT_ACTIVATED: "🟢",
}


def create_notification(
    db: Session,
    *,
    user_id: int,
    tenant_id: int,
    event_type: str,
    title: str,
    message: str,
    link: str | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    extra_data: dict | None = None,
    actor_user_id: int | None = None,
    icon: str | None = None,
    commit: bool = True,
) -> Notification:
    """
    Create a single in-app notification.

    Skips if `user_id == actor_user_id` (don't notify yourself).

    Args:
        commit: If True (default), commit immediately. If False, the
                caller is responsible for committing (useful inside
                larger transactions).
    """
    # Don't notify yourself
    if actor_user_id is not None and user_id == actor_user_id:
        logger.debug(f"Skipping self-notification for user {user_id} ({event_type})")
        return None

    notif = Notification(
        user_id=user_id,
        tenant_id=tenant_id,
        event_type=event_type,
        title=title,
        message=message,
        icon=icon or EVENT_ICONS.get(event_type, "🔔"),
        link=link,
        related_entity_type=related_entity_type,
        related_entity_id=str(related_entity_id) if related_entity_id is not None else None,
        extra_data=extra_data,
        is_read=False,
    )
    db.add(notif)
    if commit:
        db.commit()
        db.refresh(notif)
    return notif


def create_notifications_bulk(
    db: Session,
    user_ids: Iterable[int],
    *,
    tenant_id: int,
    event_type: str,
    title: str,
    message: str,
    link: str | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    extra_data: dict | None = None,
    actor_user_id: int | None = None,
    commit: bool = True,
) -> list[Notification]:
    """Create notifications for multiple users at once."""
    created = []
    for uid in user_ids:
        n = create_notification(
            db,
            user_id=uid,
            tenant_id=tenant_id,
            event_type=event_type,
            title=title,
            message=message,
            link=link,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            extra_data=extra_data,
            actor_user_id=actor_user_id,  # pass-through; None means no self-skip
            commit=False,
        )
        if n is not None:
            created.append(n)
    if commit and created:
        db.commit()
        for n in created:
            db.refresh(n)
    return created


def cleanup_old_notifications(db: Session, retention_days: int = 90) -> int:
    """
    Delete notifications older than `retention_days`.
    Called by APScheduler daily. Returns number deleted.
    """
    cutoff = utcnow() - timedelta(days=retention_days)
    deleted = (
        db.query(Notification)
        .filter(Notification.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info(f"Cleaned up {deleted} notifications older than {retention_days} days")
    return deleted

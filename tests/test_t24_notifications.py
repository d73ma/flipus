"""
FLIPUS v1.3 — Tahap 24 Notification Center Tests.

Tests notification creation, retrieval, marking read, deletion,
cleanup, and self-skip logic.

Run:
    .venv/bin/python3 -m pytest tests/test_t24_notifications.py -v
"""

from datetime import timedelta

from app.core.security import utcnow
from app.models.notification import Notification
from app.services.notification_service import (
    EventType,
    cleanup_old_notifications,
    create_notification,
    create_notifications_bulk,
)


class TestNotificationCreation:
    """Test notification service create functions."""

    def test_create_single_notification(self, test_db, jemaat_a, bendahara_a):
        db = test_db()
        notif = create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.KUITANSI_APPROVED,
            title="Test title",
            message="Test message",
        )
        assert notif.id is not None
        assert notif.is_read is False
        assert notif.icon == "✅"  # KUITANSI_APPROVED icon
        db.close()

    def test_self_skip_actor_not_notified(
        self, test_db, jemaat_a, bendahara_a
    ):
        """Actor tidak menerima notifikasi untuk aksi-nya sendiri."""
        db = test_db()
        notif = create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.KUITANSI_APPROVED,
            title="Self test",
            message="Should be skipped",
            actor_user_id=bendahara_a.id,  # same as user_id
        )
        assert notif is None
        # Verify no row in DB
        count = db.query(Notification).count()
        assert count == 0
        db.close()

    def test_bulk_creation(self, test_db, jemaat_a, bendahara_a, ketua_a):
        db = test_db()
        notifs = create_notifications_bulk(
            db,
            user_ids=[bendahara_a.id, ketua_a.id],
            tenant_id=jemaat_a.id,
            event_type=EventType.BACKUP_COMPLETED,
            title="Bulk test",
            message="Bulk message",
        )
        assert len(notifs) == 2
        db.close()


class TestNotificationAPI:
    """Test /v1/notifications/ endpoints."""

    def test_unread_count_initially_zero(self, client, bendahara_token):
        resp = client.get(
            "/api/v1/notifications/unread-count",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 0

    def test_list_returns_only_own_notifications(
        self, client, test_db, bendahara_token, ketua_token, jemaat_a, bendahara_a, ketua_a
    ):
        db = test_db()
        create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.KUITANSI_APPROVED,
            title="Bendahara notif",
            message="Visible to bendahara only",
        )
        create_notification(
            db,
            user_id=ketua_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.KUITANSI_DRAFT_CREATED,
            title="Ketua notif",
            message="Visible to ketua only",
        )
        db.close()

        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Bendahara notif"

    def test_unread_count_after_creation(
        self, client, test_db, bendahara_token, jemaat_a, bendahara_a
    ):
        db = test_db()
        create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.BACKUP_COMPLETED,
            title="Backup",
            message="Backup done",
        )
        create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.WEEKLY_BLAST_DONE,
            title="Blast",
            message="Blast done",
        )
        db.close()

        resp = client.get(
            "/api/v1/notifications/unread-count",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.json()["unread_count"] == 2

    def test_mark_as_read(
        self, client, test_db, bendahara_token, jemaat_a, bendahara_a
    ):
        db = test_db()
        notif = create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.KUITANSI_APPROVED,
            title="Read test",
            message="Read me",
        )
        notif_id = notif.id
        db.close()

        resp = client.post(
            f"/api/v1/notifications/{notif_id}/read",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True
        assert resp.json()["read_at"] is not None

    def test_mark_all_read(
        self, client, test_db, bendahara_token, jemaat_a, bendahara_a
    ):
        db = test_db()
        for i in range(3):
            create_notification(
                db,
                user_id=bendahara_a.id,
                tenant_id=jemaat_a.id,
                event_type=EventType.BACKUP_COMPLETED,
                title=f"Backup {i}",
                message=f"Backup {i}",
            )
        db.close()

        resp = client.post(
            "/api/v1/notifications/read-all",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 3

        # Verify count
        count_resp = client.get(
            "/api/v1/notifications/unread-count",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert count_resp.json()["unread_count"] == 0

    def test_delete_notification(
        self, client, test_db, bendahara_token, jemaat_a, bendahara_a
    ):
        db = test_db()
        notif = create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.BACKUP_COMPLETED,
            title="Delete me",
            message="Delete me",
        )
        notif_id = notif.id
        db.close()

        resp = client.delete(
            f"/api/v1/notifications/{notif_id}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200

        list_resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert list_resp.json()["total"] == 0

    def test_cannot_access_other_users_notification(
        self, client, test_db, ketua_token, jemaat_a, bendahara_a
    ):
        """User A cannot mark-read User B's notification."""
        db = test_db()
        notif = create_notification(
            db,
            user_id=bendahara_a.id,  # belongs to bendahara
            tenant_id=jemaat_a.id,
            event_type=EventType.KUITANSI_APPROVED,
            title="Other user's notif",
            message="Should not be accessible",
        )
        notif_id = notif.id
        db.close()

        # Ketua tries to read bendahara's notif
        resp = client.post(
            f"/api/v1/notifications/{notif_id}/read",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 404


class TestNotificationCleanup:
    """Test retention cleanup."""

    def test_cleanup_removes_old_notifications(
        self, test_db, jemaat_a, bendahara_a
    ):
        db = test_db()
        # Create old notification
        old_notif = create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.BACKUP_COMPLETED,
            title="Old notif",
            message="Should be deleted",
        )
        # Manually backdate it
        old_notif.created_at = utcnow() - timedelta(days=100)
        db.commit()

        # Create fresh notification
        create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.BACKUP_COMPLETED,
            title="Fresh notif",
            message="Should remain",
        )

        deleted = cleanup_old_notifications(db, retention_days=90)
        assert deleted == 1

        # Verify only fresh remains
        remaining = db.query(Notification).count()
        assert remaining == 1
        assert db.query(Notification).first().title == "Fresh notif"
        db.close()


class TestNotificationTriggerIntegration:
    """Test that triggers actually create notifications."""

    def test_draft_create_notifies_ketua(
        self, client, bendahara_token, ketua_token, jemaat_a, ketua_a
    ):
        """Bendahara creates draft → Ketua gets notification."""
        # Bendahara creates kuitansi
        client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"perpuluhan_x_angka": 100000, "pt_angka": 50000},
        )

        # Ketua checks notifications
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["event_type"] == EventType.KUITANSI_DRAFT_CREATED
        assert data["items"][0]["link"] == "/ketua"

    def test_approve_notifies_bendahara(
        self, client, bendahara_token, ketua_token, jemaat_a, bendahara_a
    ):
        """Ketua approves → Bendahara gets notification."""
        # Bendahara creates
        create_resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"perpuluhan_x_angka": 100000, "pt_angka": 50000},
        )
        kuitansi_id = create_resp.json()["id"]

        # Ketua approves
        client.post(
            f"/api/v1/dashboard/kuitansi/{kuitansi_id}/approve",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )

        # Bendahara checks notif
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["event_type"] == EventType.KUITANSI_APPROVED
        assert data["items"][0]["link"] == "/bendahara"

    def test_reject_notifies_bendahara_with_reason(
        self, client, bendahara_token, ketua_token, jemaat_a
    ):
        """Ketua rejects → Bendahara gets notification with reason."""
        create_resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"perpuluhan_x_angka": 100000, "pt_angka": 50000},
        )
        kuitansi_id = create_resp.json()["id"]

        client.post(
            f"/api/v1/dashboard/kuitansi/{kuitansi_id}/reject",
            headers={"Authorization": f"Bearer {ketua_token}"},
            json={"reason": "Nominal tidak valid"},
        )

        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["event_type"] == EventType.KUITANSI_REJECTED
        # Reason should be in message
        assert "tidak valid" in data["items"][0]["message"]

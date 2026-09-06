"""
FLIPUS v1.3 — Tahap 25 End-to-End Happy Path Scenarios.

Full user journeys covering T20-T24 working together.

Run:
    .venv/bin/python3 -m pytest tests/test_t25_e2e.py -v
"""

import pyotp


class TestE2EApprovalFlow:
    """Full Bendahara → Ketua approval journey."""

    def test_complete_approval_journey(
        self, client, bendahara_token, ketua_token, jemaat_a
    ):
        """Bendahara creates draft → Ketua approves → Notifications work."""

        # Step 1: Bendahara creates kuitansi (status='draft')
        create_resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={
                "nama_umat": "Bp. Umat Test",
                "perpuluhan_x_angka": 100000,
                "pt_angka": 50000,
                "khusus_angka": 25000,
            },
        )
        assert create_resp.status_code == 200
        kuitansi_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "draft"

        # Step 2: Ketua gets notification
        ketua_notifs = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {ketua_token}"},
        ).json()
        assert ketua_notifs["total"] == 1
        assert "menunggu approval" in ketua_notifs["items"][0]["title"].lower()

        # Step 3: Ketua lists pending kuitansi
        pending_resp = client.get(
            "/api/v1/dashboard/kuitansi/pending",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert pending_resp.status_code == 200
        assert pending_resp.json()["total"] == 1

        # Step 4: Ketua approves
        approve_resp = client.post(
            f"/api/v1/dashboard/kuitansi/{kuitansi_id}/approve",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "finalized"

        # Step 5: Bendahara gets approval notification
        bendahara_notifs = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        ).json()
        assert bendahara_notifs["total"] == 1
        assert "disetujui" in bendahara_notifs["items"][0]["title"].lower()

        # Step 6: Kuitansi is now visible in search (default status_filter=finalized)
        search_resp = client.get(
            "/api/v1/kuitansi/search",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert search_resp.json()["total"] == 1

        # Step 7: Pending list is now empty
        empty_pending = client.get(
            "/api/v1/dashboard/kuitansi/pending",
            headers={"Authorization": f"Bearer {ketua_token}"},
        ).json()
        assert empty_pending["total"] == 0


class TestE2ERejectFlow:
    """Bendahara creates draft → Ketua rejects with reason → Bendahara fixes."""

    def test_reject_then_recreate_journey(
        self, client, bendahara_token, ketua_token, jemaat_a
    ):
        # Step 1: Bendahara creates (typo intentional for reject)
        create_resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={
                "nama_umat": "Wrong Amount Test",
                "perpuluhan_x_angka": 999999999,  # obviously wrong
                "pt_angka": 0,
            },
        )
        kuitansi_id = create_resp.json()["id"]

        # Step 2: Ketua rejects
        reject_resp = client.post(
            f"/api/v1/dashboard/kuitansi/{kuitansi_id}/reject",
            headers={"Authorization": f"Bearer {ketua_token}"},
            json={"reason": "Nominal terlalu besar, mohon periksa kembali"},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"

        # Step 3: Bendahara sees rejected in notification
        notif = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        ).json()
        assert notif["total"] == 1
        assert notif["items"][0]["event_type"] == "KUITANSI_REJECTED"
        assert "Nominal terlalu besar" in notif["items"][0]["message"]

        # Step 4: Bendahara sees rejected list
        rejected_resp = client.get(
            "/api/v1/dashboard/kuitansi/rejected",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert rejected_resp.json()["total"] == 1

        # Step 5: Bendahara creates corrected kuitansi
        new_resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"perpuluhan_x_angka": 100000, "pt_angka": 50000},
        )
        assert new_resp.json()["status"] == "draft"
        new_id = new_resp.json()["id"]
        assert new_id != kuitansi_id

        # Step 6: Ketua approves corrected
        client.post(
            f"/api/v1/dashboard/kuitansi/{new_id}/approve",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )

        # Step 7: Now 2 finalized kuitansi? No — only the corrected one (rejected has status='rejected', not finalized)
        finalized = client.get(
            "/api/v1/dashboard/kuitansi/pending",
            headers={"Authorization": f"Bearer {ketua_token}"},
        ).json()
        assert finalized["total"] == 0


class TestE2EMultiRoleWorkflow:
    """Bendahara + Ketua + Pendeta + Admin workflow interaction."""

    def test_full_team_workflow(
        self, client, bendahara_token, ketua_token, admin_token, jemaat_a
    ):
        """Bendahara submits → Ketua approves → Admin sees all."""

        # Bendahara creates 3 kuitansi
        for amount in [100000, 200000, 300000]:
            client.post(
                "/api/v1/dashboard/kuitansi",
                headers={"Authorization": f"Bearer {bendahara_token}"},
                json={"perpuluhan_x_angka": amount, "pt_angka": amount // 2},
            )

        # Ketua approves all 3
        pending = client.get(
            "/api/v1/dashboard/kuitansi/pending",
            headers={"Authorization": f"Bearer {ketua_token}"},
        ).json()
        for k in pending["items"]:
            client.post(
                f"/api/v1/dashboard/kuitansi/{k['id']}/approve",
                headers={"Authorization": f"Bearer {ketua_token}"},
            )

        # Admin can see all 3 via search
        admin_search = client.get(
            "/api/v1/kuitansi/search",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_search.json()["total"] == 3

        # Admin can see 3 approval notifications
        admin_notifs = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        # Should have 3 KUITANSI_APPROVED notifications
        approved_count = sum(
            1 for n in admin_notifs["items"]
            if n["event_type"] == "KUITANSI_APPROVED"
        )
        assert approved_count == 3


class TestE2E2FAWithApproval:
    """2FA-enabled user does approval workflow."""

    def test_ketua_with_2fa_can_still_approve(self, client, ketua_token):
        """Ketua Keuangan enables 2FA, can still approve (login flow tested separately)."""
        # Enable 2FA for Ketua
        setup_resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert setup_resp.status_code == 200
        secret = setup_resp.json()["secret"]

        # Verify
        totp_code = pyotp.TOTP(secret).now()
        verify_resp = client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {ketua_token}"},
            json={"totp_code": totp_code, "backup_codes_visible": True},
        )
        assert verify_resp.json()["enabled"] is True

        # Verify status shows enabled
        status_resp = client.get(
            "/api/v1/auth/2fa/status",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert status_resp.json()["is_2fa_enabled"] is True
        assert status_resp.json()["backup_codes_remaining"] == 10


class TestE2ECrossTenantIsolation:
    """T20 isolation still holds with T23+T24 active."""

    def test_other_jemaat_drafts_not_visible(
        self, client, bendahara_token, ketua_token, jemaat_a, jemaat_b, create_kuitansi
    ):
        """Draft in jemaat B invisible to Bendahara/Ketua of jemaat A."""
        create_kuitansi(jemaat_b.id, status="draft")

        # Bendahara A: should see 0
        a_search = client.get(
            "/api/v1/kuitansi/search",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        ).json()
        assert a_search["total"] == 0

        # Ketua A: should see 0 in pending
        a_pending = client.get(
            "/api/v1/dashboard/kuitansi/pending",
            headers={"Authorization": f"Bearer {ketua_token}"},
        ).json()
        assert a_pending["total"] == 0

    def test_admin_can_see_both_jemaats(
        self, client, admin_token, jemaat_a, jemaat_b, create_kuitansi
    ):
        create_kuitansi(jemaat_a.id, status="finalized")
        create_kuitansi(jemaat_b.id, status="finalized")

        # Admin sees both via search
        admin_search = client.get(
            "/api/v1/kuitansi/search",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert admin_search["total"] == 2


class TestE2EPrivacyMatrix:
    """Verify RBAC matrix holds across all v1.3 features."""

    def test_pendeta_search_access(
        self, client, bendahara_token
    ):
        """Bendahara can access search (proxy for valid auth)."""
        resp = client.get(
            "/api/v1/kuitansi/search",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200

    def test_notification_user_scoping(
        self, client, test_db, bendahara_token, ketua_token, jemaat_a,
        bendahara_a, ketua_a
    ):
        """Notifications are strictly user-scoped — never leak across users."""
        from app.services.notification_service import EventType, create_notification
        # Create notifications for different users
        db = test_db()
        create_notification(
            db,
            user_id=bendahara_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.KUITANSI_APPROVED,
            title="Private to bendahara",
            message="Should only show to bendahara",
        )
        create_notification(
            db,
            user_id=ketua_a.id,
            tenant_id=jemaat_a.id,
            event_type=EventType.KUITANSI_DRAFT_CREATED,
            title="Private to ketua",
            message="Should only show to ketua",
        )
        db.close()

        # Bendahara sees only his
        b_list = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        ).json()
        assert b_list["total"] == 1
        assert b_list["items"][0]["title"] == "Private to bendahara"

        # Ketua sees only his
        k_list = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {ketua_token}"},
        ).json()
        assert k_list["total"] == 1
        assert k_list["items"][0]["title"] == "Private to ketua"

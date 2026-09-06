"""
FLIPUS v1.3 — Tahap 23 Approval + 2FA Tests.

Tests the approval workflow (Bendahara draft → Ketua approve/reject)
and TOTP 2FA (setup, verify, login flow, backup codes).

Run:
    .venv/bin/python3 -m pytest tests/test_t23_approval_2fa.py -v
"""


import pytest

# pyotp is required for TOTP tests. Skip gracefully if not installed (CI may not have it).
pyotp = pytest.importorskip("pyotp", reason="pyotp not available")


# ===== T23.1 APPROVAL WORKFLOW =====

class TestKuitansiApproval:
    """Approval workflow: Bendahara creates draft → Ketua approves."""

    def test_bendahara_creates_draft(
        self, client, bendahara_token, jemaat_a, ketua_a
    ):
        """Bendahara POST kuitansi → status='draft'."""
        resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={
                "nama_umat": "Test Umat",
                "perpuluhan_x_angka": 100000,
                "pt_angka": 50000,
                "khusus_angka": 0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["needs_approval"] is True

    def test_ketua_creates_finalized(
        self, client, ketua_token, jemaat_a
    ):
        """Ketua Keuangan POST kuitansi → status='finalized'."""
        resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {ketua_token}"},
            json={
                "nama_umat": "Test Umat",
                "perpuluhan_x_angka": 100000,
                "pt_angka": 50000,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"

    def test_approve_draft_changes_status_to_finalized(
        self, client, bendahara_token, ketua_token, jemaat_a
    ):
        """Ketua approve draft → status='finalized'."""
        # Bendahara creates draft
        create_resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"perpuluhan_x_angka": 100000, "pt_angka": 50000},
        )
        kuitansi_id = create_resp.json()["id"]

        # Ketua approves
        approve_resp = client.post(
            f"/api/v1/dashboard/kuitansi/{kuitansi_id}/approve",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert approve_resp.status_code == 200
        data = approve_resp.json()
        assert data["status"] == "finalized"
        assert data["approved_by_user_id"] is not None

    def test_approve_non_draft_returns_400(
        self, client, ketua_token, jemaat_a, create_kuitansi
    ):
        """Cannot approve already-finalized kuitansi."""
        k = create_kuitansi(jemaat_a.id, status="finalized")
        resp = client.post(
            f"/api/v1/dashboard/kuitansi/{k.id}/approve",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 400

    def test_bendahara_cannot_approve(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """Bendahara cannot approve own drafts."""
        k = create_kuitansi(jemaat_a.id, status="draft")
        resp = client.post(
            f"/api/v1/dashboard/kuitansi/{k.id}/approve",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 403

    def test_reject_requires_reason(
        self, client, bendahara_token, ketua_token, jemaat_a
    ):
        """Reject tanpa reason → 400."""
        create_resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"perpuluhan_x_angka": 100000, "pt_angka": 50000},
        )
        kuitansi_id = create_resp.json()["id"]

        reject_resp = client.post(
            f"/api/v1/dashboard/kuitansi/{kuitansi_id}/reject",
            headers={"Authorization": f"Bearer {ketua_token}"},
            json={"reason": ""},  # empty
        )
        assert reject_resp.status_code == 400

    def test_reject_with_reason_changes_status(
        self, client, bendahara_token, ketua_token, jemaat_a
    ):
        """Reject with valid reason → status='rejected'."""
        create_resp = client.post(
            "/api/v1/dashboard/kuitansi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"perpuluhan_x_angka": 100000, "pt_angka": 50000},
        )
        kuitansi_id = create_resp.json()["id"]

        reject_resp = client.post(
            f"/api/v1/dashboard/kuitansi/{kuitansi_id}/reject",
            headers={"Authorization": f"Bearer {ketua_token}"},
            json={"reason": "Nominal tidak sesuai amplop asli"},
        )
        assert reject_resp.status_code == 200
        data = reject_resp.json()
        assert data["status"] == "rejected"
        assert "tidak sesuai" in data["rejected_reason"]

    def test_list_pending_kuitansi(
        self, client, ketua_token, jemaat_a, create_kuitansi
    ):
        """Ketua can list drafts in jemaat."""
        create_kuitansi(jemaat_a.id, status="draft")
        create_kuitansi(jemaat_a.id, status="draft")
        create_kuitansi(jemaat_a.id, status="finalized")

        resp = client.get(
            "/api/v1/dashboard/kuitansi/pending",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_cross_tenant_approve_blocked(
        self, client, ketua_token, jemaat_a, jemaat_b, create_kuitansi
    ):
        """Ketua from jemaat A cannot approve kuitansi from jemaat B."""
        k = create_kuitansi(jemaat_b.id, status="draft")
        resp = client.post(
            f"/api/v1/dashboard/kuitansi/{k.id}/approve",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 403


# ===== T23.2 TOTP 2FA =====

class TestTwoFactorSetup:
    """TOTP 2FA setup and verify."""

    def test_status_initially_disabled(
        self, client, bendahara_token
    ):
        """New user has 2FA disabled."""
        resp = client.get(
            "/api/v1/auth/2fa/status",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_2fa_enabled"] is False

    def test_setup_returns_qr_and_secret(
        self, client, bendahara_token
    ):
        """Setup returns QR code + manual secret."""
        resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "secret" in data
        assert "qr_code" in data
        assert data["qr_code"].startswith("data:image/png;base64,")
        # otpauth_url format
        assert "otpauth://totp/" in data["otpauth_url"]

    def test_verify_with_valid_totp_enables_2fa(
        self, client, bendahara_token
    ):
        """Verify with correct TOTP enables 2FA and returns backup codes."""
        setup_resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        secret = setup_resp.json()["secret"]
        totp_code = pyotp.TOTP(secret).now()

        verify_resp = client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": totp_code, "backup_codes_visible": True},
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        # TwoFactorVerifyOut has field "enabled" (not "is_2fa_enabled")
        assert data["enabled"] is True
        assert len(data.get("backup_codes", [])) == 10

    def test_verify_with_invalid_totp_rejected(
        self, client, bendahara_token
    ):
        """Verify with wrong TOTP rejected."""
        client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )

        verify_resp = client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": "000000", "backup_codes_visible": True},
        )
        assert verify_resp.status_code == 400


class TestTwoFactorLogin:
    """Login flow with 2FA enabled."""

    def test_login_with_2fa_returns_partial_token(self, client, bendahara_token):
        """After enable, login returns partial_token instead of full JWT."""
        # Enable 2FA
        setup_resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        secret = setup_resp.json()["secret"]
        totp_code = pyotp.TOTP(secret).now()
        client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": totp_code, "backup_codes_visible": True},
        )

        # Try login again — should get 2FA required
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "bendahara", "password": "Bendahara123!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("requires_2fa") is True
        assert "partial_token" in data

    def test_login_with_totp_in_request(self, client, bendahara_token):
        """Combined login: username + password + totp_code in one POST."""
        setup_resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        secret = setup_resp.json()["secret"]
        totp_code = pyotp.TOTP(secret).now()
        client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": totp_code, "backup_codes_visible": True},
        )

        # Combined login
        totp_now = pyotp.TOTP(secret).now()
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "bendahara",
                "password": "Bendahara123!",
                "totp_code": totp_now,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data.get("requires_2fa") is not True

    def test_login_step2_with_totp(self, client, bendahara_token):
        """Two-step login: partial_token + TOTP → full JWT."""
        setup_resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        secret = setup_resp.json()["secret"]
        totp_code = pyotp.TOTP(secret).now()
        client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": totp_code, "backup_codes_visible": True},
        )

        # Step 1: get partial_token
        resp1 = client.post(
            "/api/v1/auth/login",
            json={"username": "bendahara", "password": "Bendahara123!"},
        )
        partial_token = resp1.json()["partial_token"]

        # Step 2: submit TOTP
        totp_now = pyotp.TOTP(secret).now()
        resp2 = client.post(
            "/api/v1/auth/2fa/login",
            json={"partial_token": partial_token, "totp_code": totp_now},
        )
        assert resp2.status_code == 200
        assert "access_token" in resp2.json()


class TestBackupCodes:
    """Backup code flow."""

    def test_backup_codes_format(self, client, bendahara_token):
        """Backup codes have ABC12-DEF34 format."""
        setup_resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        secret = setup_resp.json()["secret"]
        totp_code = pyotp.TOTP(secret).now()
        verify_resp = client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": totp_code, "backup_codes_visible": True},
        )
        codes = verify_resp.json()["backup_codes"]
        assert len(codes) == 10
        for code in codes:
            # Format: ABC12-DEF34
            assert len(code) == 11
            assert code[5] == "-"

    def test_backup_code_login_single_use(self, client, bendahara_token):
        """Backup code can be used once, then invalidated."""
        setup_resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        secret = setup_resp.json()["secret"]
        totp_code = pyotp.TOTP(secret).now()
        verify_resp = client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": totp_code, "backup_codes_visible": True},
        )
        backup_code = verify_resp.json()["backup_codes"][0]

        # Login with backup code
        resp1 = client.post(
            "/api/v1/auth/login",
            json={"username": "bendahara", "password": "Bendahara123!"},
        )
        partial_token = resp1.json()["partial_token"]

        resp2 = client.post(
            "/api/v1/auth/2fa/login",
            json={"partial_token": partial_token, "totp_code": backup_code},
        )
        assert resp2.status_code == 200

        # Second use should fail
        resp3 = client.post(
            "/api/v1/auth/login",
            json={"username": "bendahara", "password": "Bendahara123!"},
        )
        partial_token_2 = resp3.json()["partial_token"]

        resp4 = client.post(
            "/api/v1/auth/2fa/login",
            json={"partial_token": partial_token_2, "totp_code": backup_code},
        )
        assert resp4.status_code == 400


class TestTwoFactorDisable:
    """2FA disable flow."""

    def test_disable_requires_totp_and_password(self, client, bendahara_token):
        """Disable 2FA requires both TOTP and password."""
        setup_resp = client.post(
            "/api/v1/auth/2fa/setup",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        secret = setup_resp.json()["secret"]
        totp_code = pyotp.TOTP(secret).now()
        client.post(
            "/api/v1/auth/2fa/verify",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": totp_code, "backup_codes_visible": True},
        )

        # Disable
        totp_now = pyotp.TOTP(secret).now()
        resp = client.post(
            "/api/v1/auth/2fa/disable",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"totp_code": totp_now, "password": "Bendahara123!"},
        )
        assert resp.status_code == 200

        # Status should now show disabled
        status_resp = client.get(
            "/api/v1/auth/2fa/status",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert status_resp.json()["is_2fa_enabled"] is False

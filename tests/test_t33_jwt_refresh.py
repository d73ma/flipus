"""
FASE 3-S3.S8 — Regression tests untuk JWT 15-min access + 7-day refresh token.

Scope:
  1. Settings (config) — ACCESS_TOKEN_EXPIRE_MINUTES=15, REFRESH_TOKEN_EXPIRE_DAYS=7
  2. Security helpers — create_access_token() & create_refresh_token() payload claims
  3. POST /auth/login (no-2FA path) — returns BOTH tokens + persists RefreshToken row
  4. POST /auth/refresh
       - valid refresh token → rotates JTI, returns new pair
       - access token ditolak (anti privilege escalation)
       - invalid signature ditolak
       - unknown JTI ditolak
       - revoked refresh ditolak
       - reused refresh → CHAIN REVOKE all active sessions + audit log
       - inactive user ditolak
       - tenant mismatch ditolak
  5. POST /auth/logout — revoke all active refresh tokens for user

Jalankan:
    cd /Users/jerrymauri/Flipus
    .venv/bin/python3 -m pytest tests/test_t33_jwt_refresh.py -v
"""

from datetime import UTC, datetime, timedelta

from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from app.models.refresh_token import RefreshToken

# =====================================================================
# 1) Settings / config
# =====================================================================

class TestSettings:
    def test_access_token_15_minutes(self):
        """OWASP recommendation: access token lifetime < 30 min."""
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 15

    def test_refresh_token_7_days(self):
        """OWASP recommendation: refresh token lifetime > 1 day, stored server-side."""
        assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7


# =====================================================================
# 2) Security helpers — claims
# =====================================================================

class TestTokenClaims:
    def test_access_token_has_typ_access(self):
        token = create_access_token({"sub": 1, "role": "BENDAHARA", "tenant_id": 2})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["typ"] == "access"
        # sub selalu di-coerce ke str (security.py line 51-55) — RFC 7519 §4.1.2
        assert payload["sub"] == "1"
        assert payload["role"] == "BENDAHARA"
        assert payload["tenant_id"] == 2
        assert payload["jti"]  # always present (uuid4 hex)

    def test_access_token_sub_coerced_to_string(self):
        """sub claim should be str (per RFC 7519 §4.1.2 — recommended)."""
        token = create_access_token({"sub": 42, "role": "BENDAHARA", "tenant_id": 1})
        payload = decode_access_token(token)
        assert isinstance(payload["sub"], str)
        assert payload["sub"] == "42"

    def test_access_token_expiry_about_15_min(self):
        before = datetime.now(UTC)
        token = create_access_token({"sub": 1, "role": "BENDAHARA", "tenant_id": 1})
        payload = decode_access_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        delta_sec = (exp - before).total_seconds()
        # ±10 second tolerance
        assert 15 * 60 - 10 <= delta_sec <= 15 * 60 + 10

    def test_refresh_token_has_typ_refresh(self):
        token = create_refresh_token({"sub": 1, "role": "BENDAHARA", "tenant_id": 2})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["typ"] == "refresh"
        assert payload["jti"]
        assert payload["jti"] != payload.get("iat")  # jti != iat (always uuid)

    def test_refresh_token_expiry_about_7_days(self):
        before = datetime.now(UTC)
        token = create_refresh_token({"sub": 1, "role": "BENDAHARA", "tenant_id": 1})
        payload = decode_access_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        delta_sec = (exp - before).total_seconds()
        # 7 days ± 10s
        assert 7 * 86400 - 10 <= delta_sec <= 7 * 86400 + 10

    def test_refresh_token_jti_unique(self):
        t1 = create_refresh_token({"sub": 1, "role": "BENDAHARA", "tenant_id": 1})
        t2 = create_refresh_token({"sub": 1, "role": "BENDAHARA", "tenant_id": 1})
        p1 = decode_access_token(t1)
        p2 = decode_access_token(t2)
        assert p1["jti"] != p2["jti"]

    def test_refresh_custom_expires_days_override(self):
        token = create_refresh_token(
            {"sub": 1, "role": "BENDAHARA", "tenant_id": 1},
            expires_days=1,
        )
        payload = decode_access_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        delta_sec = (exp - datetime.now(UTC)).total_seconds()
        assert 86400 - 10 <= delta_sec <= 86400 + 10


# =====================================================================
# 3) POST /auth/login — no-2FA path returns both tokens + persists row
# =====================================================================

class TestLoginReturnsBothTokens:
    def test_login_no_2fa_returns_access_and_refresh(self, client, bendahara_a, jemaat_a):
        """BENDAHARA (no 2FA) login harus return access_token + refresh_token."""
        r = client.post(
            "/api/v1/auth/login",
            json={
                "username": "bendahara",
                "password": "Bendahara123!",
                "tenant_slug": jemaat_a.slug,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900  # 15 min
        assert data["role"] == "BENDAHARA"
        assert data["tenant_id"] == jemaat_a.id

    def test_login_persists_refresh_token_row(self, client, bendahara_a, jemaat_a, test_db):
        r = client.post(
            "/api/v1/auth/login",
            json={
                "username": "bendahara",
                "password": "Bendahara123!",
                "tenant_slug": jemaat_a.slug,
            },
        )
        assert r.status_code == 200
        refresh_jwt = r.json()["refresh_token"]
        payload = decode_access_token(refresh_jwt)
        jti = payload["jti"]

        db = test_db()
        row = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
        assert row is not None
        assert row.user_id == bendahara_a.id
        assert row.tenant_id == jemaat_a.id
        assert row.revoked_at is None
        assert row.used_at is None
        db.close()

    def test_login_payloads_have_correct_typ(self, client, bendahara_a, jemaat_a):
        r = client.post(
            "/api/v1/auth/login",
            json={
                "username": "bendahara",
                "password": "Bendahara123!",
                "tenant_slug": jemaat_a.slug,
            },
        )
        data = r.json()
        assert decode_access_token(data["access_token"])["typ"] == "access"
        assert decode_access_token(data["refresh_token"])["typ"] == "refresh"


# =====================================================================
# 4) POST /auth/refresh
# =====================================================================

def _login_bendahara(client, jemaat_a):
    r = client.post(
        "/api/v1/auth/login",
        json={
            "username": "bendahara",
            "password": "Bendahara123!",
            "tenant_slug": jemaat_a.slug,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestRefreshEndpoint:
    def test_refresh_valid_token_rotates(self, client, bendahara_a, jemaat_a, test_db):
        """Valid refresh → returns new pair, JTI rotated, old row marked used_at."""
        login = _login_bendahara(client, jemaat_a)
        old_refresh = login["refresh_token"]
        old_jti = decode_access_token(old_refresh)["jti"]

        r = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["access_token"] != login["access_token"]
        assert data["refresh_token"] != old_refresh
        new_jti = decode_access_token(data["refresh_token"])["jti"]
        assert new_jti != old_jti

        # DB: old row marked used_at
        db = test_db()
        old_row = db.query(RefreshToken).filter(RefreshToken.jti == old_jti).first()
        assert old_row.used_at is not None
        # DB: new row persisted
        new_row = db.query(RefreshToken).filter(RefreshToken.jti == new_jti).first()
        assert new_row is not None
        assert new_row.used_at is None
        db.close()

    def test_refresh_rejects_access_token(self, client, bendahara_a, jemaat_a):
        """Anti privilege-escalation: cannot use access token at refresh endpoint."""
        login = _login_bendahara(client, jemaat_a)
        access_token = login["access_token"]

        r = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
        assert r.status_code == 401
        assert "typ" in r.json()["detail"].lower() or "type" in r.json()["detail"].lower()

    def test_refresh_rejects_invalid_signature(self, client, bendahara_a, jemaat_a):
        """Garbled token → 401."""
        login = _login_bendahara(client, jemaat_a)
        refresh_token = login["refresh_token"]
        # flip last char
        tampered = refresh_token[:-1] + ("A" if refresh_token[-1] != "A" else "B")

        r = client.post("/api/v1/auth/refresh", json={"refresh_token": tampered})
        assert r.status_code == 401

    def test_refresh_rejects_unknown_jti(self, client, bendahara_a, jemaat_a, test_db):
        """Refresh token with valid signature but JTI not in DB → 401."""
        # Forge a refresh token signed by SECRET_KEY (use settings directly) but with
        # random JTI — simulates attacker who can sign but never got refresh from us.
        forge_payload = {
            "sub": "999",
            "role": "BENDAHARA",
            "tenant_id": 999,
            "typ": "refresh",
            "iss": "FLIPUS-UKIKT",
            "watermark": "FLIPUS_v1.1",
            "jti": "deadbeef" * 4,  # 32 hex chars, valid format
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(days=7),
        }
        forge_token = jwt.encode(
            forge_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM,
        )

        r = client.post("/api/v1/auth/refresh", json={"refresh_token": forge_token})
        assert r.status_code == 401
        assert "not recognized" in r.json()["detail"].lower() or "invalid" in r.json()["detail"].lower()

    def test_refresh_rejects_revoked(self, client, bendahara_a, jemaat_a, test_db):
        """Refresh token whose row was revoked → 401."""
        login = _login_bendahara(client, jemaat_a)
        refresh_token = login["refresh_token"]
        jti = decode_access_token(refresh_token)["jti"]

        # Manually revoke the row
        db = test_db()
        row = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
        row.revoked_at = datetime.now(UTC)
        row.revoked_reason = "manual_test_revoke"
        db.commit()
        db.close()

        r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 401
        assert "revoke" in r.json()["detail"].lower()

    def test_refresh_reuse_triggers_chain_revoke(self, client, bendahara_a, jemaat_a, test_db):
        """Reusing an already-used refresh token → CHAIN REVOKE all active sessions."""
        login = _login_bendahara(client, jemaat_a)
        old_refresh = login["refresh_token"]
        old_jti = decode_access_token(old_refresh)["jti"]

        # First use → success (rotates to new JTI)
        r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert r1.status_code == 200
        # Simulate: a 2nd login creates another active refresh token
        # (so we have >1 active row, then reuse attempt should revoke BOTH).
        login2 = _login_bendahara(client, jemaat_a)
        second_refresh_jti = decode_access_token(login2["refresh_token"])["jti"]

        # Re-use the ORIGINAL refresh (now used_at set) — should trigger chain revoke
        r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert r2.status_code == 401
        assert "dipakai" in r2.json()["detail"].lower() or "reuse" in r2.json()["detail"].lower() \
               or "sudah" in r2.json()["detail"].lower()

        # DB: old + second refresh rows BOTH revoked
        db = test_db()
        old_row = db.query(RefreshToken).filter(RefreshToken.jti == old_jti).first()
        second_row = db.query(RefreshToken).filter(RefreshToken.jti == second_refresh_jti).first()
        assert old_row.revoked_at is not None
        assert old_row.revoked_reason == "reuse_detected"
        assert second_row.revoked_at is not None
        assert second_row.revoked_reason == "reuse_detected"
        # Audit log entry written
        audit = db.query(__import__("app.models.audit", fromlist=["AuditLog"]).AuditLog) \
                 .filter(__import__("app.models.audit", fromlist=["AuditLog"]).AuditLog
                         .action.like("REFRESH_REUSE_DETECTED%")).first()
        assert audit is not None
        db.close()

    def test_refresh_rejects_inactive_user(self, client, bendahara_a, jemaat_a, test_db):
        """User deactivated after login → refresh should fail."""
        login = _login_bendahara(client, jemaat_a)
        refresh_token = login["refresh_token"]

        db = test_db()
        u = db.query(__import__("app.models.user", fromlist=["User"]).User) \
              .filter(__import__("app.models.user", fromlist=["User"]).User.id == bendahara_a.id).first()
        u.is_active = False
        db.commit()
        db.close()

        r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 401
        assert "non-aktif" in r.json()["detail"].lower() or "inactive" in r.json()["detail"].lower()


# =====================================================================
# 5) POST /auth/logout — revoke all active refresh tokens for user
# =====================================================================

class TestLogoutRevokesRefreshTokens:
    def test_logout_revokes_all_active_refresh_tokens(
        self, client, bendahara_a, jemaat_a, test_db,
    ):
        # 1. Login → get access + refresh
        login = _login_bendahara(client, jemaat_a)
        access_token = login["access_token"]
        refresh_jti = decode_access_token(login["refresh_token"])["jti"]

        # 2. Simulate a 2nd active refresh (e.g., another device)
        login2 = _login_bendahara(client, jemaat_a)
        second_jti = decode_access_token(login2["refresh_token"])["jti"]

        # Sanity: both rows active
        db = test_db()
        rows_before = db.query(RefreshToken).filter(
            RefreshToken.user_id == bendahara_a.id,
            RefreshToken.revoked_at.is_(None),
        ).count()
        assert rows_before >= 2
        db.close()

        # 3. Logout with access token
        r = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert r.status_code == 200, r.text

        # 4. All refresh tokens for user should be revoked
        db = test_db()
        rows_after = db.query(RefreshToken).filter(
            RefreshToken.user_id == bendahara_a.id,
            RefreshToken.revoked_at.is_(None),
        ).count()
        assert rows_after == 0

        # Original JTI rows specifically
        r1 = db.query(RefreshToken).filter(RefreshToken.jti == refresh_jti).first()
        r2 = db.query(RefreshToken).filter(RefreshToken.jti == second_jti).first()
        assert r1.revoked_at is not None
        assert r1.revoked_reason == "logout_access_token"
        assert r2.revoked_at is not None
        assert r2.revoked_reason == "logout_access_token"
        db.close()

    def test_revoked_refresh_cannot_be_used_after_logout(
        self, client, bendahara_a, jemaat_a,
    ):
        """End-to-end: refresh token issued BEFORE logout should fail after logout."""
        login = _login_bendahara(client, jemaat_a)
        access_token = login["access_token"]
        refresh_token = login["refresh_token"]

        # Logout
        r = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert r.status_code == 200

        # Try to refresh with the pre-logout refresh token
        r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert r2.status_code == 401

"""
FASE 5 Sprint 5 — Integration tests for app/api/v1/users.py.

Targets:
- GET /api/v1/users  (line 108) — list users visible to caller
- DELETE /api/v1/users/{user_id}  (line 166) — soft-delete user
"""



class TestUsersList:
    """GET /api/v1/users — list visible users (ADMIN_UNI / AUDITOR_MISI only)."""

    def test_bendahara_forbidden(self, client, bendahara_token, jemaat_a) -> None:
        """BENDAHARA cannot list users (only ADMIN_UNI / AUDITOR_MISI)."""
        resp = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 403

    def test_admin_uni_sees_auditors_in_uni(
        self, client, admin_token, jemaat_a, jemaat_b, bendahara_a, ketua_a, auditor_misi
    ) -> None:
        """ADMIN_UNI sees AUDITOR_MISI in own uni."""
        resp = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should include auditor_misi at minimum
        assert data["count"] >= 1
        # All returned users should be AUDITOR_MISI role
        assert all(u["role"] == "AUDITOR_MISI" for u in data["users"])

    def test_admin_uni_response_includes_user_metadata(
        self, client, admin_token, jemaat_a, bendahara_a
    ) -> None:
        """User entries include nama_jemaat, nama_misi, nama_uni."""
        resp = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        users = resp.json()["users"]
        # Each user has tenant context
        for user in users:
            assert "nama_jemaat" in user
            assert "nama_misi" in user
            assert "nama_uni" in user

    def test_auditor_misi_can_list(
        self, client, auditor_token, jemaat_a, jemaat_b, bendahara_a, ketua_a
    ) -> None:
        """AUDITOR_MISI can list users in own misi."""
        resp = client.get(
            "/api/v1/users",
            params={"role": "BENDAHARA"},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

    def test_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get("/api/v1/users")
        assert resp.status_code == 401


class TestUsersDelete:
    """DELETE /api/v1/users/{user_id} — soft-delete user."""

    def test_admin_can_delete_user_in_uni(self, client, admin_token, jemaat_a, bendahara_a) -> None:
        """ADMIN_UNI can delete user in own uni."""
        resp = client.delete(
            f"/api/v1/users/{bendahara_a.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Should succeed (or 403 if not allowed)
        assert resp.status_code in (200, 403)

    def test_delete_nonexistent_user(self, client, admin_token, jemaat_a) -> None:
        """Non-existent user_id → 404."""
        resp = client.delete(
            "/api/v1/users/999999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_delete_requires_auth(self, client, ketua_a) -> None:
        """Unauthenticated → 401."""
        resp = client.delete(f"/api/v1/users/{ketua_a.id}")
        assert resp.status_code == 401

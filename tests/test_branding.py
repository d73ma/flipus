"""
FLIPUS v1.3 — Tahap 21 Branding Tests.

Test:
- TestHexColorValidation: format hex color
- TestLogoValidation: file size, MIME type, extension
- TestBrandingUpdate: PATCH branding endpoint
- TestLogoUpload: POST logo endpoint
- TestLogoRemove: DELETE logo endpoint
- TestPublicLogoServe: GET /tenants/logo/{id} (no auth)
- TestRBAC: non-admin can't update branding
- TestColorBranding: PDF generator pakai tenant color

Run: pytest tests/test_branding.py -v
"""

import pytest
import io
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.branding_service import (
    _validate_hex_color,
    _validate_logo_file,
    ALLOWED_LOGO_EXTENSIONS,
    MAX_LOGO_SIZE_BYTES,
)


# ===== Hex Color Validation =====

class TestHexColorValidation:
    def test_valid_6_digit_hex(self):
        assert _validate_hex_color("#1B4332") == "#1b4332"
        assert _validate_hex_color("#FFFFFF") == "#ffffff"
        assert _validate_hex_color("#abcdef") == "#abcdef"

    def test_valid_3_digit_hex_normalized(self):
        assert _validate_hex_color("#FFF") == "#ffffff"
        assert _validate_hex_color("#abc") == "#aabbcc"

    def test_invalid_color_no_hash(self):
        with pytest.raises(ValueError):
            _validate_hex_color("1B4332")

    def test_invalid_color_wrong_length(self):
        with pytest.raises(ValueError):
            _validate_hex_color("#12345")
        with pytest.raises(ValueError):
            _validate_hex_color("#1234567")

    def test_invalid_color_non_hex_chars(self):
        with pytest.raises(ValueError):
            _validate_hex_color("#ZZZZZZ")

    def test_empty_color(self):
        with pytest.raises(ValueError):
            _validate_hex_color("")

    def test_case_insensitive(self):
        assert _validate_hex_color("#FFffFF") == "#ffffff"
        assert _validate_hex_color("#aBcDeF") == "#abcdef"


# ===== Logo File Validation =====

class TestLogoFileValidation:
    def test_valid_png(self):
        ext = _validate_logo_file("logo.png", "image/png", 50000)
        assert ext == ".png"

    def test_valid_jpg(self):
        ext = _validate_logo_file("logo.jpg", "image/jpeg", 50000)
        assert ext == ".jpg"

    def test_valid_svg(self):
        ext = _validate_logo_file("logo.svg", "image/svg+xml", 50000)
        assert ext == ".svg"

    def test_too_big(self):
        with pytest.raises(ValueError, match="terlalu besar"):
            _validate_logo_file("logo.png", "image/png", MAX_LOGO_SIZE_BYTES + 1)

    def test_invalid_mime(self):
        with pytest.raises(ValueError, match="tidak didukung"):
            _validate_logo_file("logo.gif", "image/gif", 50000)

    def test_invalid_ext(self):
        with pytest.raises(ValueError, match="tidak didukung"):
            _validate_logo_file("logo.bmp", "image/bmp", 50000)


# ===== Integration Tests =====

class TestBrandingUpdate:
    """Test PATCH branding endpoint."""

    def test_admin_can_update_branding(self, client, test_db):
        """Admin uni can update tenant's branding."""
        # Setup: AdminUni + tenant
        from app.models.master import Uni
        from app.core.security import hash_password, generate_tenant_signature
        from app.models.tenant import Tenant
        from app.models.user import User

        db = test_db()
        uni = Uni(nama_resmi="UKIKT", kode="UKIKT")
        db.add(uni)
        db.commit()
        db.refresh(uni)

        admin_tenant = Tenant(
            tenant_signature=generate_tenant_signature("UKIKT", "[ADMIN-UNI]", "[ADMIN-UKIKT]"),
            nama_uni="UKIKT",
            nama_kantor_misi="[ADMIN-UNI]",
            nama_jemaat_lokal="[ADMIN-UKIKT]",
            slug="admin-ukikt",
            misi_konferens_id=None,
        )
        db.add(admin_tenant)
        db.commit()
        db.refresh(admin_tenant)

        admin = User(
            tenant_id=admin_tenant.id,
            username="admin_ukikt",
            password_hash=hash_password("Adm1n1234!"),
            nama_lengkap="Admin",
            role="ADMIN_UNI",
            is_active=True,
        )
        db.add(admin)
        db.commit()

        # Create a tenant in same uni
        t = Tenant(
            tenant_signature=generate_tenant_signature("UKIKT", "DK Minahasa", "Jemaat X"),
            nama_uni="UKIKT",
            nama_kantor_misi="DK Minahasa",
            nama_jemaat_lokal="Jemaat X",
            slug="jemaat-x",
            misi_konferens_id=None,
        )
        db.add(t)
        db.commit()
        db.refresh(t)

        # Login as admin
        resp = client.post("/api/v1/auth/login", json={"username": "admin_ukikt", "password": "Adm1n1234!"})
        token = resp.json()["access_token"]

        # Update branding
        resp = client.patch(
            f"/api/v1/tenants/{t.id}/branding",
            json={"primary_color": "#1e3a8a", "secondary_color": "#eff6ff", "footer_text": "GMAHK UKIKT"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["primary_color"] == "#1e3a8a"
        assert data["secondary_color"] == "#eff6ff"
        assert data["footer_text"] == "GMAHK UKIKT"

    def test_invalid_color_rejected(self, client, test_db):
        """Invalid hex color -> 400."""
        from app.models.master import Uni
        from app.core.security import hash_password, generate_tenant_signature
        from app.models.tenant import Tenant
        from app.models.user import User

        db = test_db()
        uni = Uni(nama_resmi="UKIKT", kode="UKIKT")
        db.add(uni)
        db.commit()
        db.refresh(uni)

        admin_tenant = Tenant(
            tenant_signature=generate_tenant_signature("UKIKT", "[ADMIN-UNI]", "[ADMIN-UKIKT]"),
            nama_uni="UKIKT",
            nama_kantor_misi="[ADMIN-UNI]",
            nama_jemaat_lokal="[ADMIN-UKIKT]",
            slug="admin-ukikt",
            misi_konferens_id=None,
        )
        db.add(admin_tenant)
        db.commit()
        db.refresh(admin_tenant)

        admin = User(
            tenant_id=admin_tenant.id,
            username="admin_ukikt",
            password_hash=hash_password("Adm1n1234!"),
            nama_lengkap="Admin",
            role="ADMIN_UNI",
            is_active=True,
        )
        db.add(admin)
        db.commit()

        # Login
        resp = client.post("/api/v1/auth/login", json={"username": "admin_ukikt", "password": "Adm1n1234!"})
        token = resp.json()["access_token"]

        # Try invalid color
        resp = client.patch(
            f"/api/v1/tenants/{admin_tenant.id}/branding",
            json={"primary_color": "not-a-color"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_non_admin_cannot_update_branding(self, client, test_db):
        """Non-admin can't update branding."""
        from app.core.security import hash_password, generate_tenant_signature
        from app.models.tenant import Tenant
        from app.models.user import User

        db = test_db()
        t = Tenant(
            tenant_signature=generate_tenant_signature("UKIKT", "DK Minahasa", "Jemaat X"),
            nama_uni="UKIKT",
            nama_kantor_misi="DK Minahasa",
            nama_jemaat_lokal="Jemaat X",
            slug="jemaat-x",
            misi_konferens_id=None,
        )
        db.add(t)
        db.commit()
        db.refresh(t)

        u = User(
            tenant_id=t.id,
            username="bendum",
            password_hash=hash_password("Bendahara123!"),
            nama_lengkap="Bendahara",
            role="BENDAHARA",
            is_active=True,
        )
        db.add(u)
        db.commit()

        resp = client.post("/api/v1/auth/login", json={"username": "bendum", "password": "Bendahara123!"})
        token = resp.json()["access_token"]

        resp = client.patch(
            f"/api/v1/tenants/{t.id}/branding",
            json={"primary_color": "#abcdef"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


class TestLogoUpload:
    """Test POST logo endpoint."""

    def test_admin_can_upload_logo(self, client, test_db, tmp_path):
        """Admin uploads a PNG logo."""
        from app.models.master import Uni
        from app.core.security import hash_password, generate_tenant_signature
        from app.models.tenant import Tenant
        from app.models.user import User

        db = test_db()

        # Mock STORAGE_ROOT ke tmp_path
        with patch("app.services.branding_service.STORAGE_ROOT", tmp_path):
            uni = Uni(nama_resmi="UKIKT", kode="UKIKT")
            db.add(uni)
            db.commit()
            db.refresh(uni)

            admin_tenant = Tenant(
                tenant_signature=generate_tenant_signature("UKIKT", "[ADMIN-UNI]", "[ADMIN-UKIKT]"),
                nama_uni="UKIKT",
                nama_kantor_misi="[ADMIN-UNI]",
                nama_jemaat_lokal="[ADMIN-UKIKT]",
                slug="admin-ukikt",
                misi_konferens_id=None,
            )
            db.add(admin_tenant)
            db.commit()
            db.refresh(admin_tenant)

            admin = User(
                tenant_id=admin_tenant.id,
                username="admin_ukikt",
                password_hash=hash_password("Adm1n1234!"),
                nama_lengkap="Admin",
                role="ADMIN_UNI",
                is_active=True,
            )
            db.add(admin)
            db.commit()

            # Login
            resp = client.post("/api/v1/auth/login", json={"username": "admin_ukikt", "password": "Adm1n1234!"})
            token = resp.json()["access_token"]

            # Create fake PNG (1x1 pixel)
            from PIL import Image
            img = Image.new("RGB", (100, 100), color="red")
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            resp = client.post(
                f"/api/v1/tenants/{admin_tenant.id}/logo",
                files={"file": ("test.png", img_bytes, "image/png")},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "uploaded"
            assert data["logo_url"].endswith(".png")

    def test_too_big_rejected(self, client, test_db):
        """File > 1MB rejected."""
        from app.models.master import Uni
        from app.core.security import hash_password, generate_tenant_signature
        from app.models.tenant import Tenant
        from app.models.user import User

        db = test_db()
        uni = Uni(nama_resmi="UKIKT", kode="UKIKT")
        db.add(uni)
        db.commit()
        db.refresh(uni)

        admin_tenant = Tenant(
            tenant_signature=generate_tenant_signature("UKIKT", "[ADMIN-UNI]", "[ADMIN-UKIKT]"),
            nama_uni="UKIKT",
            nama_kantor_misi="[ADMIN-UNI]",
            nama_jemaat_lokal="[ADMIN-UKIKT]",
            slug="admin-ukikt",
            misi_konferens_id=None,
        )
        db.add(admin_tenant)
        db.commit()
        db.refresh(admin_tenant)

        admin = User(
            tenant_id=admin_tenant.id,
            username="admin_ukikt",
            password_hash=hash_password("Adm1n1234!"),
            nama_lengkap="Admin",
            role="ADMIN_UNI",
            is_active=True,
        )
        db.add(admin)
        db.commit()

        # Login
        resp = client.post("/api/v1/auth/login", json={"username": "admin_ukikt", "password": "Adm1n1234!"})
        token = resp.json()["access_token"]

        # Send 2MB file
        big_file = b"a" * (2 * 1024 * 1024)
        resp = client.post(
            f"/api/v1/tenants/{admin_tenant.id}/logo",
            files={"file": ("big.png", io.BytesIO(big_file), "image/png")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "terlalu besar" in resp.json()["detail"].lower()

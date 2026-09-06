"""
FASE 5 Sprint 5 — Unit + integration tests for app/services/user_creator.py.

Covers:
- Username generators (_username_for_pendeta/auditor/admin)
- register_pendeta happy path
"""

from app.services.user_creator import (
    _username_for_admin,
    _username_for_auditor,
    _username_for_pendeta,
)


class TestUsernameGenerators:
    """Pure functions for username formatting."""

    def test_pendeta_username(self) -> None:
        assert _username_for_pendeta("NT") == "pendeta_nt"

    def test_pendeta_username_uppercase_normalized(self) -> None:
        assert _username_for_pendeta("NATAAN") == "pendeta_nataan"

    def test_pendeta_username_truncates_long_input(self) -> None:
        """Long initial truncated to 8 chars."""
        result = _username_for_pendeta("ABCDEFGHIJKLMNOP")
        assert len(result.split("_")[1]) <= 8

    def test_pendeta_username_empty_fallback(self) -> None:
        """Empty input falls back to 'jt'."""
        assert _username_for_pendeta("") == "pendeta_jt"
        assert _username_for_pendeta("   ") == "pendeta_jt"

    def test_auditor_username(self) -> None:
        assert _username_for_auditor("DK.MIN") == "auditor_dk.min"

    def test_auditor_username_truncates(self) -> None:
        result = _username_for_auditor("A" * 30)
        assert len(result.split("_")[1]) <= 16

    def test_auditor_username_empty_fallback(self) -> None:
        assert _username_for_auditor("") == "auditor_misi"

    def test_admin_username(self) -> None:
        assert _username_for_admin("UIKT") == "admin_uikt"

    def test_admin_username_truncates(self) -> None:
        result = _username_for_admin("UKIKT-LONG")
        assert len(result.split("_")[1]) <= 8

    def test_admin_username_empty_fallback(self) -> None:
        assert _username_for_admin("") == "admin_uni"


class TestRegisterPendeta:
    """register_pendeta — creates Tenant + User (Pendeta) atomically."""

    def test_register_pendeta_happy_path(self, test_db, uni_dk, misi_minahasa) -> None:
        """Should create tenant + user and return tuple (user, password, tenant)."""
        from app.services.user_creator import register_pendeta

        user, password, tenant = register_pendeta(
            db=test_db(),
            uni=uni_dk,
            misi=misi_minahasa,
            nama_jemaat="Jemaat Test Pendeta",
            initial_jemaat="TP",
            nama_pendeta="Pdt. Test",
            wa_pendeta="6281234567009",
            nama_ketua="Sdr. Ketua",
            wa_ketua="6281234567010",
            nama_bendahara="Sdr. Bendahara",
            wa_bendahara="6281234567011",
        )
        assert user.role == "PENDETA"
        assert user.username.startswith("pendeta_")
        assert len(password) >= 8  # T49 policy
        assert tenant.nama_jemaat_lokal == "Jemaat Test Pendeta"

    def test_register_pendeta_persentase_config_created(self, test_db, uni_dk, misi_minahasa) -> None:
        """PersentaseConfig MISI scope should be created for the new tenant."""
        from app.models.master import PersentaseConfig
        from app.services.user_creator import register_pendeta

        register_pendeta(
            db=test_db(),
            uni=uni_dk,
            misi=misi_minahasa,
            nama_jemaat="Jemaat Pendeta 2",
            initial_jemaat="JP",
            nama_pendeta="Pdt. X",
            wa_pendeta="6281234567012",
            nama_ketua="K",
            wa_ketua="6281234567013",
            nama_bendahara="B",
            wa_bendahara="6281234567014",
        )
        # PersentaseConfig MISI for this misi should exist (or already)
        cfg = (
            test_db()
            .query(PersentaseConfig)
            .filter(
                PersentaseConfig.scope == "MISI",
                PersentaseConfig.ref_id == misi_minahasa.id,
            )
            .first()
        )
        assert cfg is not None

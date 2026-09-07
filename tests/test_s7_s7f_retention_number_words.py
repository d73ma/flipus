"""
FASE 5 Sprint 7 — Unit tests for app/services/retention_daemon.py + number_to_words.py.

Covers:
- run_retention_purge: purge old kuitansi (nama/WA/foto → PURGED, is_purged=True),
  skip already-purged, file removal, cutoff date.
- terbilang (number_to_words): edge cases (0, ribuan, jutaan, miliaran, triliun,
  negatif, seribu vs satu ribu).
"""

import os
from datetime import timedelta

from app.core.security import utcnow


class TestRetentionPurge:
    def test_purges_old_records(self, test_db, jemaat_a) -> None:
        from app.models.transaction import Kuitansi
        from app.services.retention_daemon import run_retention_purge

        db = test_db()
        old = utcnow() - timedelta(days=31 * 30)
        k = Kuitansi(
            tenant_id=jemaat_a.id,
            id_rekap_mingguan="RK-OLD",
            nomor_kuitansi="OLD-1",
            tanggal_sabat="2020-01-04",
            nama_umat_encrypted="encrypted-name",
            nomor_whatsapp_encrypted="encrypted-wa",
            foto_amplop_path=None,
            perpuluhan_x_angka=1000,
            pt_angka=0,
            khusus_angka=0,
            total_pemberian_angka=1000,
            status="finalized",
            is_purged=False,
            created_at=old,
        )
        db.add(k)
        db.commit()
        db.close()

        result = run_retention_purge(test_db())
        assert result["status"] == "OK"
        assert result["purged_count"] == 1

        # Verify purged
        db = test_db()
        refreshed = db.query(Kuitansi).get(k.id)
        assert refreshed.is_purged is True
        assert refreshed.nama_umat_encrypted is None
        assert refreshed.nomor_whatsapp_encrypted is None
        assert refreshed.foto_amplop_path == "PURGED"
        db.close()

    def test_skips_recent_records(self, test_db, jemaat_a) -> None:
        from app.models.transaction import Kuitansi
        from app.services.retention_daemon import run_retention_purge

        db = test_db()
        recent = utcnow() - timedelta(days=5)
        k = Kuitansi(
            tenant_id=jemaat_a.id,
            id_rekap_mingguan="RK-RECENT",
            nomor_kuitansi="RECENT-1",
            tanggal_sabat="2026-09-05",
            nama_umat_encrypted="encrypted-name",
            perpuluhan_x_angka=1000,
            pt_angka=0,
            khusus_angka=0,
            total_pemberian_angka=1000,
            status="finalized",
            is_purged=False,
            created_at=recent,
        )
        db.add(k)
        db.commit()
        db.close()

        result = run_retention_purge(test_db())
        assert result["purged_count"] == 0

    def test_skips_already_purged(self, test_db, jemaat_a) -> None:
        from app.models.transaction import Kuitansi
        from app.services.retention_daemon import run_retention_purge

        db = test_db()
        old = utcnow() - timedelta(days=31 * 30)
        k = Kuitansi(
            tenant_id=jemaat_a.id,
            id_rekap_mingguan="RK-PURGED",
            nomor_kuitansi="PURGED-1",
            tanggal_sabat="2020-01-04",
            nama_umat_encrypted=None,
            perpuluhan_x_angka=1000,
            total_pemberian_angka=1000,
            status="finalized",
            is_purged=True,
            created_at=old,
        )
        db.add(k)
        db.commit()
        db.close()

        # Already purged → not counted again
        result = run_retention_purge(test_db())
        assert result["purged_count"] == 0

    def test_removes_photo_file(self, test_db, jemaat_a, tmp_path) -> None:
        from app.models.transaction import Kuitansi
        from app.services.retention_daemon import run_retention_purge

        # Create a real temp file
        photo = tmp_path / "amplop.jpg"
        photo.write_bytes(b"fake-jpg")

        db = test_db()
        old = utcnow() - timedelta(days=31 * 30)
        k = Kuitansi(
            tenant_id=jemaat_a.id,
            id_rekap_mingguan="RK-PHOTO",
            nomor_kuitansi="PHOTO-1",
            tanggal_sabat="2020-01-04",
            nama_umat_encrypted="encrypted-name",
            foto_amplop_path=str(photo),
            perpuluhan_x_angka=1000,
            total_pemberian_angka=1000,
            status="finalized",
            is_purged=False,
            created_at=old,
        )
        db.add(k)
        db.commit()
        db.close()

        result = run_retention_purge(test_db())
        assert result["files_removed"] == 1
        assert not os.path.exists(str(photo))


class TestTerbilang:
    def test_zero(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(0) == "Nol Rupiah"

    def test_ones(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(1) == "Satu Rupiah"
        assert terbilang(11) == "Sebelas Rupiah"

    def test_belas(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(12) == "Dua Belas Rupiah"
        assert terbilang(19) == "Sembilan Belas Rupiah"

    def test_puluh(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(20) == "Dua Puluh Rupiah"
        assert terbilang(25) == "Dua Puluh Lima Rupiah"

    def test_ratus(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(100) == "Seratus Rupiah"
        assert terbilang(150) == "Seratus Lima Puluh Rupiah"
        assert terbilang(250) == "Dua Ratus Lima Puluh Rupiah"

    def test_ribu(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(1000) == "Seribu Rupiah"
        assert terbilang(1500) == "Seribu Lima Ratus Rupiah"
        assert terbilang(5000) == "Lima Ribu Rupiah"

    def test_juta(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(1_000_000) == "Satu Juta Rupiah"
        assert terbilang(2_500_000) == "Dua Juta Lima Ratus Ribu Rupiah"

    def test_miliar(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(1_000_000_000) == "Satu Miliar Rupiah"
        assert terbilang(1_250_000_000) == "Satu Miliar Dua Ratus Lima Puluh Juta Rupiah"

    def test_triliun(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(1_000_000_000_000) == "Satu Triliun Rupiah"

    def test_negative_uses_abs(self) -> None:
        from app.utils.number_to_words import terbilang

        assert terbilang(-5000) == "Lima Ribu Rupiah"

    def test_complex_number(self) -> None:
        from app.utils.number_to_words import terbilang

        # 123.456.789
        result = terbilang(123_456_789)
        assert "Seratus Dua Puluh Tiga Juta" in result

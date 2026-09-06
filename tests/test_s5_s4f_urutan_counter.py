"""
FASE 5 Sprint 4 — Unit tests for app/services/urutan_counter.py.

Covers get_next_urutan: empty DB → 1, with rows → count + 1, multi-month filter.
"""

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.transaction import Kuitansi
from app.services.urutan_counter import get_next_urutan


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _add_kuitansi(session: Session, tenant_id: int, tanggal_sabat: str, nomor: str) -> None:
    k = Kuitansi(
        tenant_id=tenant_id,
        id_rekap_mingguan=f"RK-{tanggal_sabat.replace('-', '')}-test",
        nomor_kuitansi=nomor,
        tanggal_sabat=tanggal_sabat,
        nama_umat_encrypted="encrypted",
    )
    session.add(k)
    session.commit()


class TestGetNextUrutan:
    def test_empty_db_returns_one(self) -> None:
        session = _make_session()
        try:
            urutan = get_next_urutan(session, tenant_id=1)
            assert urutan == 1
        finally:
            session.close()

    def test_with_existing_kuitansi_in_month(self) -> None:
        session = _make_session()
        try:
            _add_kuitansi(session, tenant_id=1, tanggal_sabat="2026-08-07", nomor="001/NT/VIII/26")
            _add_kuitansi(session, tenant_id=1, tanggal_sabat="2026-08-14", nomor="002/NT/VIII/26")
            urutan = get_next_urutan(session, tenant_id=1, bulan=8, tahun=2026)
            assert urutan == 3
        finally:
            session.close()

    def test_filter_by_month(self) -> None:
        """August has 2, September has 1 — month filter should isolate them."""
        session = _make_session()
        try:
            _add_kuitansi(session, tenant_id=1, tanggal_sabat="2026-08-07", nomor="001/NT/VIII/26")
            _add_kuitansi(session, tenant_id=1, tanggal_sabat="2026-08-14", nomor="002/NT/VIII/26")
            _add_kuitansi(session, tenant_id=1, tanggal_sabat="2026-09-04", nomor="001/NT/IX/26")
            # August → 3, September → 2
            assert get_next_urutan(session, tenant_id=1, bulan=8, tahun=2026) == 3
            assert get_next_urutan(session, tenant_id=1, bulan=9, tahun=2026) == 2
        finally:
            session.close()

    def test_filter_by_tenant(self) -> None:
        """Different tenants should have independent counters."""
        session = _make_session()
        try:
            _add_kuitansi(session, tenant_id=1, tanggal_sabat="2026-08-07", nomor="001/NT/VIII/26")
            _add_kuitansi(session, tenant_id=2, tanggal_sabat="2026-08-07", nomor="001/KB/VIII/26")
            _add_kuitansi(session, tenant_id=2, tanggal_sabat="2026-08-14", nomor="002/KB/VIII/26")
            assert get_next_urutan(session, tenant_id=1, bulan=8, tahun=2026) == 2
            assert get_next_urutan(session, tenant_id=2, bulan=8, tahun=2026) == 3
        finally:
            session.close()

    def test_default_month_uses_now(self) -> None:
        """bulan/tahun=None → use current month."""
        session = _make_session()
        try:
            now = datetime.now()
            iso_prefix = f"{now.year:04d}-{now.month:02d}"
            _add_kuitansi(session, tenant_id=1, tanggal_sabat=f"{iso_prefix}-07", nomor="001")
            urutan = get_next_urutan(session, tenant_id=1)
            assert urutan == 2
        finally:
            session.close()

"""
v2.0 M1 — Quick Input endpoint untuk PWA & mobile-first.

Jerry (2026-08-27): Bendahara input kuitansi via PWA form (mobile-first).
Beda dari kuitansi.create existing (web form): Quick Input support kategori fleksibel
(auto-create kategori baru jika nama belum ada), batch save dalam 1 request (optional),
dan return kategori_baru list untuk UI feedback.

Endpoint:
- POST /api/v1/kuitansi/quick-input
  Body: {
    nama_pemberi: str,
    items: [{kategori_nama: str, nominal: int}],  // minimal 1 item, nominal > 0
    tanggal_sabat: str (YYYY-MM-DD) optional, default=sabat_berjalan
    simpan_lanjut: bool (default false) — kalau true, batch save mode
  }
  Response: {
    ok: true,
    nomor_kuitansi: "001/NT/I/27",
    total_pemberian: int,
    kategori_baru: [str],  // kategori yang auto-created saat ini
    kategori_existing: [str],
    tanggal_sabat: str
  }

RBAC:
- BENDAHARA only (input keuangan eksklusif Bendahara per Jerry 2026-08-27)
"""
import sys
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.tenant_scope import (
    TenantScope, require_tenant_scope,
)
from app.core.security import encrypt_pii
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.models.kategori_pemasukan import KategoriPemasukan, KuitansiKategori
from app.models.audit import AuditLog
from app.utils.kategori_alias import generate_alias, normalize_nama, is_valid_nama
from app.utils.sabat_counter import get_effective_sabat_for_input
from app.utils.nomor_kuitansi import generate_nomor_kuitansi, generate_id_rekap_mingguan

router = APIRouter()


# ===== Schemas =====

class QuickInputItem(BaseModel):
    kategori_nama: str
    nominal: int

    @field_validator("nominal")
    @classmethod
    def validate_nominal(cls, v):
        if v < 0:
            raise ValueError("nominal harus >= 0")
        if v > 999_999_999:
            raise ValueError("nominal terlalu besar (max 999.999.999)")
        return v

    @field_validator("kategori_nama")
    @classmethod
    def validate_nama(cls, v):
        if not v or not v.strip():
            raise ValueError("kategori_nama wajib diisi")
        if not is_valid_nama(v):
            raise ValueError("kategori_nama max 30 char, alpha-numeric + spasi saja")
        return v.strip()


class QuickInputRequest(BaseModel):
    nama_pemberi: str
    items: List[QuickInputItem]
    tanggal_sabat: Optional[str] = None  # override; default = sabat berjalan
    simpan_lanjut: bool = False  # kalau true, batch save (multiple kuitansi sekaligus)

    model_config = ConfigDict(from_attributes=True)


class QuickInputResponse(BaseModel):
    ok: bool
    nomor_kuitansi: str
    total_pemberian: int
    kategori_baru: List[str]
    kategori_existing: List[str]
    tanggal_sabat: str


# ===== Helpers =====

def _get_or_create_kategori(db: Session, tenant_id: int, nama: str) -> tuple[KategoriPemasukan, bool]:
    """
    Get existing kategori by normalized nama (case-insensitive), or create new.

    Returns: (KategoriPemasukan, is_new: bool)
    """
    norm = normalize_nama(nama)
    # Strip "Persembahan " prefix for matching
    match_alias = generate_alias(nama)

    existing = (
        db.query(KategoriPemasukan)
        .filter(
            KategoriPemasukan.tenant_id == tenant_id,
            KategoriPemasukan.is_aktif == True,
        )
        .filter(
            (KategoriPemasukan.alias == match_alias) |
            (KategoriPemasukan.nama == norm)
        )
        .first()
    )
    if existing:
        return existing, False

    # Auto-create
    # Avoid alias collision by appending number suffix
    base_alias = match_alias
    alias = base_alias
    suffix = 1
    while (
        db.query(KategoriPemasukan)
        .filter(KategoriPemasukan.tenant_id == tenant_id, KategoriPemasukan.alias == alias)
        .first()
    ):
        suffix += 1
        alias = f"{base_alias}{suffix}"
        if suffix > 99:
            raise HTTPException(500, f"Gagal generate alias unik untuk '{nama}'")

    # Urutan = max existing + 1
    max_urutan = (
        db.query(KategoriPemasukan)
        .filter(KategoriPemasukan.tenant_id == tenant_id)
        .count()
    )

    k = KategoriPemasukan(
        tenant_id=tenant_id,
        nama=norm,
        alias=alias,
        urutan=max_urutan + 1,
        is_rutin=False,  # auto-created selalu non-rutin
        is_aktif=True,
    )
    db.add(k)
    db.flush()  # get k.id
    return k, True


def _generate_nomor_for_kuitansi(db: Session, tenant: Tenant, tanggal: str) -> str:
    """
    Generate nomor kuitansi dengan format existing: 001/NT/I/27
    Counter reset per bulan Romawi.
    """
    tgl_obj = datetime.strptime(tanggal, "%Y-%m-%d")
    # Count existing kuitansi bulan ini untuk counter
    bulan_romawi_map = {1:"I",2:"II",3:"III",4:"IV",5:"V",6:"VI",7:"VII",8:"VIII",9:"IX",10:"X",11:"XI",12:"XII"}
    bulan_romawi = bulan_romawi_map[tgl_obj.month]
    tahun_2d = str(tgl_obj.year)[-2:].zfill(2)

    existing = (
        db.query(Kuitansi)
        .filter(
            Kuitansi.tenant_id == tenant.id,
            Kuitansi.nomor_kuitansi.like(f"%/{tenant.initial_jemaat}/{bulan_romawi}/{tahun_2d}"),
            Kuitansi.is_purged == False,
        )
        .count()
    )
    urutan = existing + 1
    return generate_nomor_kuitansi(urutan, tenant.initial_jemaat, tgl_obj)


# ===== Endpoint =====

@router.post("/kuitansi/quick-input", tags=['QuickInput'], response_model=QuickInputResponse)
def quick_input(
    body: QuickInputRequest,
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """
    v2.0 Quick Input endpoint — PWA friendly.

    FASE4-S6E: pakai TenantScope (gantikan inline tenant_id = current_user).
    Tenant baru di-bind ke primary_tenant_id caller (BENDAHARA selalu single-tenant).

    Validasi:
    - scope.role == BENDAHARA
    - scope.primary_tenant_id aktif
    - Minimal 1 item dengan nominal > 0
    - nama_pemberi: 1-100 char

    Flow:
    1. Validasi RBAC + tenant
    2. Tentukan tanggal_sabat (override atau sabat_berjalan)
    3. Untuk setiap item: get_or_create kategori
    4. Generate nomor_kuitansi (counter per bulan)
    5. Insert Kuitansi + KuitansiKategori pivot rows
    6. Audit log + return response
    """
    # RBAC: hanya Bendahara yang boleh input keuangan
    if scope.role != "BENDAHARA":
        raise HTTPException(403, "Hanya Bendahara yang boleh input kuitansi keuangan")

    tenant_id = scope.primary_tenant_id
    if not tenant_id:
        raise HTTPException(400, "User tidak terkait dengan tenant/jemaat")

    # Validasi nama_pemberi
    if not body.nama_pemberi or not body.nama_pemberi.strip():
        raise HTTPException(400, "nama_pemberi wajib diisi")
    if len(body.nama_pemberi) > 100:
        raise HTTPException(400, "nama_pemberi max 100 char")
    nama = body.nama_pemberi.strip()

    # Validasi items
    if not body.items or len(body.items) == 0:
        raise HTTPException(400, "Minimal 1 item dengan nominal > 0")
    valid_items = [it for it in body.items if it.nominal > 0]
    if not valid_items:
        raise HTTPException(400, "Minimal 1 item dengan nominal > 0")

    # Tenant aktif
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(404, f"Tenant {tenant_id} tidak aktif atau tidak ditemukan")

    # Tentukan tanggal_sabat (T111 rule: kalau lewat sabat, pakai sabat terakhir)
    if body.tanggal_sabat:
        try:
            datetime.strptime(body.tanggal_sabat, "%Y-%m-%d")
            tanggal = body.tanggal_sabat
        except ValueError:
            raise HTTPException(400, "tanggal_sabat format harus YYYY-MM-DD")
    else:
        sabat_info = get_effective_sabat_for_input()
        tanggal = sabat_info["tanggal_sabat"]

    # Get/create kategori
    kategori_baru_list = []
    kategori_existing_list = []
    pivot_data = []  # (kategori_obj, nominal)

    for it in valid_items:
        kat, is_new = _get_or_create_kategori(db, tenant_id, it.kategori_nama)
        pivot_data.append((kat, it.nominal))
        if is_new:
            kategori_baru_list.append(kat.nama)
        else:
            kategori_existing_list.append(kat.nama)

    # Hitung total
    total = sum(n for _, n in pivot_data)

    # Generate nomor_kuitansi (counter per bulan Romawi)
    nomor = _generate_nomor_for_kuitansi(db, tenant, tanggal)

    # Generate id_rekap_mingguan
    tgl_obj = datetime.strptime(tanggal, "%Y-%m-%d")
    id_rekap = generate_id_rekap_mingguan(tgl_obj)

    # Insert Kuitansi
    nama_umat_encrypted = encrypt_pii(nama) if nama else None
    k = Kuitansi(
        tenant_id=tenant_id,
        id_rekap_mingguan=id_rekap,
        nomor_kuitansi=nomor,
        tanggal_sabat=tanggal,
        nama_umat_encrypted=nama_umat_encrypted,
        # Populate legacy fields (backward-compat dengan reporting v1.5)
        perpuluhan_x_angka=sum(n for k, n in pivot_data if k.alias == "X"),
        pt_angka=sum(n for k, n in pivot_data if k.alias == "PT"),
        khusus_angka=sum(n for k, n in pivot_data if k.alias == "KHUS"),
        total_pemberian_angka=total,
        # Status (v2.0: DRAFT dulu, approval Ketua→Pendeta)
        # Untuk v1.5 backward-compat, default 'finalized'
        status="finalized",
        created_by_user_id=scope.user_id,
        created_via="pwa",  # v2.0: distinct from 'web'/'ocr'/'wa'
    )
    db.add(k)
    db.flush()  # get k.id

    # Insert pivot rows
    for kat_obj, nominal in pivot_data:
        pivot = KuitansiKategori(
            kuitansi_id=k.id,
            kategori_id=kat_obj.id,
            nominal=nominal,
        )
        db.add(pivot)

    # Hitung porsi Model B (reuse existing utility, sama pattern dengan scanner.py)
    # pct config loaded dari PersentaseConfig per tenant.misi_konferens_id
    from app.utils.porsi_calculator import compute_porsi
    if tenant.misi_konferens_id is None:
        pct = {"pct_x_jemaat": 1.0, "pct_pt_jemaat": 0.5, "pct_khusus_jemaat": 0.0,
               "pct_x_uni": 0.0, "pct_pt_uni": 0.0, "pct_khusus_uni": 0.0}
    else:
        from app.models.master import PersentaseConfig
        cfg = (
            db.query(PersentaseConfig)
            .filter(PersentaseConfig.scope == "MISI")
            .filter(PersentaseConfig.ref_id == tenant.misi_konferens_id)
            .first()
        )
        pct = {
            "pct_x_jemaat": cfg.pct_x_jemaat if cfg else 1.0,
            "pct_pt_jemaat": cfg.pct_pt_jemaat if cfg else 0.5,
            "pct_khusus_jemaat": cfg.pct_khusus_jemaat if cfg else 0.0,
            "pct_x_uni": cfg.pct_x_uni if cfg else 0.0,
            "pct_pt_uni": cfg.pct_pt_uni if cfg else 0.0,
            "pct_khusus_uni": cfg.pct_khusus_uni if cfg else 0.0,
        }
    p = compute_porsi(
        x=k.perpuluhan_x_angka,
        pt=k.pt_angka,
        kh=k.khusus_angka,
        pct_x_jemaat=pct["pct_x_jemaat"],
        pct_pt_jemaat=pct["pct_pt_jemaat"],
        pct_khusus_jemaat=pct["pct_khusus_jemaat"],
        pct_x_uni=pct["pct_x_uni"],
        pct_pt_uni=pct["pct_pt_uni"],
        pct_khusus_uni=pct["pct_khusus_uni"],
    )
    # Map new compute_porsi keys → legacy Kuitansi fields
    k.porsi_kantor_misi = p["pm_x"] + p["pm_pt"] + p["pm_kh"]
    k.porsi_kas_jemaat = p["pj_x"] + p["pj_pt"] + p["pj_kh"]
    k.porsi_khusus_misi = p["pm_kh"]  # porsi khusus yang ke misi
    k.porsi_khusus_jemaat = p["pj_kh"]  # porsi khusus yang ke jemaat

    # Audit log (pattern: scanner.py — action encode user_id, payload_hash=nomor)
    db.add(AuditLog(
        tenant_id=tenant_id,
        action=f"QUICK_INPUT_CREATE_user_{scope.user_id}_count_{len(pivot_data)}_new_{len(kategori_baru_list)}",
        payload_hash=nomor,
        porsi_dana_misi=k.porsi_kantor_misi,
    ))

    db.commit()

    return QuickInputResponse(
        ok=True,
        nomor_kuitansi=nomor,
        total_pemberian=total,
        kategori_baru=kategori_baru_list,
        kategori_existing=kategori_existing_list,
        tanggal_sabat=tanggal,
    )


# ===== v2.0 M2: GET /kategori/list — untuk autocomplete UI =====
class KategoriListItem(BaseModel):
    id: int
    nama: str
    alias: str
    is_rutin: bool
    urutan: int


@router.get("/kategori/list", tags=['QuickInput'], response_model=List[KategoriListItem])
def list_kategori(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """
    v2.0 M2 — List kategori aktif untuk tenant user (untuk autocomplete UI QuickInput).

    FASE4-S6E: pakai TenantScope.visible_tenant_ids (cross-tenant audit aware).

    RBAC: semua role yang sudah login boleh lihat (read-only).
    Auto-create kategori BARU tetap hanya BENDAHARA (lihat endpoint quick-input).

    Return diurutkan: rutin dulu (X, PT) → lalu by urutan → lalu by nama.
    Limit: 100 (cukup untuk dropdown autocomplete).
    """
    if not scope.visible_tenant_ids:
        return []

    rows = (
        db.query(KategoriPemasukan)
        .filter(KategoriPemasukan.tenant_id.in_(scope.visible_tenant_ids))
        .filter(KategoriPemasukan.is_aktif == True)
        .order_by(
            KategoriPemasukan.is_rutin.desc(),  # rutin (X, PT) di atas
            KategoriPemasukan.urutan.asc(),
            KategoriPemasukan.nama.asc(),
        )
        .limit(100)
        .all()
    )
    return [
        KategoriListItem(
            id=r.id,
            nama=r.nama,
            alias=r.alias,
            is_rutin=r.is_rutin,
            urutan=r.urutan,
        )
        for r in rows
    ]
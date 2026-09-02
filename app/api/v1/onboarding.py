from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_admin_bootstrap_dependency
from app.services.tenant_service import register_tenant

router = APIRouter()

class OnboardingIn(BaseModel):
    nama_uni: str
    nama_kantor_misi: str
    nama_jemaat_lokal: str
    nama_pendeta: str
    nama_ketua_keuangan: str
    nama_bendahara: str

class TenantOut(BaseModel):
    id: int
    tenant_signature: str
    nama_uni: str
    nama_kantor_misi: str
    nama_jemaat_lokal: str
    nama_pendeta: str
    nama_ketua_keuangan: str
    nama_bendahara: str

@router.post("/register-tenant", tags=['Onboarding'], response_model=TenantOut)
def register(
    payload: OnboardingIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_bootstrap_dependency),
):
    """
    Daftarkan tenant (jemaat) baru ke FLIPUS.

    SECURITY: Wajib header `X-Admin-Token`. Endpoint ini hanya untuk Jerry/admin
    saat onboarding jemaat baru. Bukan user-facing.
    """
    t = register_tenant(
        db,
        payload.nama_uni,
        payload.nama_kantor_misi,
        payload.nama_jemaat_lokal,
        payload.nama_pendeta,
        payload.nama_ketua_keuangan,
        payload.nama_bendahara,
    )
    return TenantOut(
        id=t.id,
        tenant_signature=t.tenant_signature,
        nama_uni=t.nama_uni,
        nama_kantor_misi=t.nama_kantor_misi,
        nama_jemaat_lokal=t.nama_jemaat_lokal,
        nama_pendeta=t.nama_pendeta,
        nama_ketua_keuangan=t.nama_ketua_keuangan,
        nama_bendahara=t.nama_bendahara,
    )

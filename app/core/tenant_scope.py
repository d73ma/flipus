"""
FASE 4 Sprint 5 — TenantScope: isolasi data multi-organisasi (defense-in-depth).

**Tujuan:**
Pusatkan logik RBAC tenant visibility supaya:
1. Tidak ada endpoint yang QUERY data transaksional tanpa filter tenant.
2. Cross-tenant leakage MUST impossible secara default — kalau filter lupa,
   query akan return 0 row (empty `visible_tenant_ids` → empty result).

**Penggunaan:**
```python
from app.core.tenant_scope import TenantScope, require_tenant_scope

@router.get("/notifications")
def list_notifications(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    return db.query(Notification).filter(
        Notification.tenant_id.in_(scope.visible_tenant_ids)
    ).all()
```

Atau pakai helper auto-filter:
```python
from app.core.tenant_scope import tenant_filter

q = tenant_filter(db.query(Kuitansi), Kuitansi, scope)
```

**RBAC matrix (5 role):**
| Role            | visible_tenant_ids                                  |
|-----------------|-----------------------------------------------------|
| BENDAHARA       | [tenant sendiri]                                    |
| KETUA_KEUANGAN  | [tenant sendiri]                                    |
| PENDETA         | [tenant sendiri]                                    |
| AUDITOR_MISI    | semua jemaat dengan misi_konferens_id yg sama       |
| ADMIN_UNI       | semua jemaat di uni yg sama (via misi → jemaat chain) |

**Backward compat:**
- `kuitansi.py` punya `_get_visible_tenant_ids(db, current)` lama — akan di-deprecate
  pelan-pelan di Sprint 5-B/5-C. Untuk sekarang logika di sini adalah single source of truth.

**Keamanan tambahan:**
- `visible_tenant_ids` selalu di-construct dari database lookup (bukan dari JWT claim),
  sehingga kalau JWT claim di-tamper, query tetap aman.
- Kalau caller punya `tenant_id` yang TIDAK ada di DB, `primary_tenant_id` jadi None
  dan `visible_tenant_ids` jadi [] → query return empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.database import get_db
from app.models.master import MisiKonferens, Uni
from app.models.tenant import Tenant


# Role yang punya akses lintas jemaat (RBAC 5-tier FLIPUS)
ROLE_JEMAAT_ONLY = {"BENDAHARA", "KETUA_KEUANGAN", "PENDETA"}
ROLE_AUDITOR_MISI = "AUDITOR_MISI"
ROLE_ADMIN_UNI = "ADMIN_UNI"
ALL_ROLES = ROLE_JEMAAT_ONLY | {ROLE_AUDITOR_MISI, ROLE_ADMIN_UNI}


@dataclass(frozen=True)
class TenantScope:
    """
    Resolved tenant visibility untuk current user (immutable setelah construction).

    Attributes:
        role: Role user (salah satu dari 5 RBAC roles).
        primary_tenant_id: Tenant 'milik' user sendiri (selalu tunggal).
                           Bisa None kalau tenant record sudah hilang dari DB.
        visible_tenant_ids: List tenant yang BOLEH diakses caller. Selalu List[int]
                            (kosong = tidak boleh akses apa-apa).
        user_id: User ID dari caller (untuk audit/logging).
        is_cross_tenant: True kalau caller bisa akses >1 tenant
                         (AUDITOR_MISI / ADMIN_UNI).
    """

    role: str
    primary_tenant_id: Optional[int]
    visible_tenant_ids: List[int] = field(default_factory=list)
    user_id: Optional[int] = None
    is_cross_tenant: bool = False

    def can_see(self, tenant_id: int) -> bool:
        """True kalau caller BOLEH akses tenant_id (untuk sanity check di service)."""
        return int(tenant_id) in self.visible_tenant_ids

    def __contains__(self, tenant_id: int) -> bool:
        return self.can_see(tenant_id)


# ===== Core resolver =====

def resolve_tenant_scope(db: Session, current: dict) -> TenantScope:
    """
    Pure function (no FastAPI dependency) — return TenantScope untuk current user.

    Args:
        db: SQLAlchemy session.
        current: Dict dari `get_current_user()` —
                 minimal berisi keys: id, tenant_id, role.

    Returns:
        TenantScope. Kalau caller tidak punya akses apapun, visible_tenant_ids = []
        (empty) — endpoint yang filter by `in_()` otomatis return kosong, BUKAN 403.
        Caller boleh raise 403 manual kalau mau UX strict (lihat `require_tenant_scope`).

    Raises:
        ValueError: kalau role tidak dikenal (programming error).
    """
    role = current.get("role", "")
    user_id = current.get("id")
    raw_tenant_id = current.get("tenant_id")

    if role not in ALL_ROLES:
        raise ValueError(
            f"resolve_tenant_scope: role '{role}' tidak dikenal. "
            f"Expected salah satu dari {sorted(ALL_ROLES)}."
        )

    # Primary tenant — kalau record hilang dari DB, treat sebagai "no access"
    primary: Optional[Tenant] = None
    if raw_tenant_id is not None:
        primary = db.query(Tenant).filter(Tenant.id == raw_tenant_id).first()

    if role in ROLE_JEMAAT_ONLY:
        # Single-tenant access: jemaat level only
        if primary is None:
            visible_ids: List[int] = []
        else:
            visible_ids = [primary.id]

    elif role == ROLE_AUDITOR_MISI:
        # Cross-misi: semua jemaat dengan misi_konferens_id yang sama
        if primary is None or not getattr(primary, "misi_konferens_id", None):
            visible_ids = []
        else:
            visible_ids = [
                t.id
                for t in db.query(Tenant)
                .filter(Tenant.misi_konferens_id == primary.misi_konferens_id)
                .all()
            ]

    elif role == ROLE_ADMIN_UNI:
        # Cross-uni: chain uni → misi → jemaat
        if primary is None or not getattr(primary, "nama_uni", None):
            visible_ids = []
        else:
            uni = db.query(Uni).filter(Uni.nama_resmi == primary.nama_uni).first()
            if uni is None:
                visible_ids = []
            else:
                misi_ids = [
                    m.id
                    for m in db.query(MisiKonferens).filter(MisiKonferens.uni_id == uni.id).all()
                ]
                if not misi_ids:
                    visible_ids = []
                else:
                    visible_ids = [
                        t.id
                        for t in db.query(Tenant)
                        .filter(Tenant.misi_konferens_id.in_(misi_ids))
                        .all()
                    ]
    else:
        # Unreachable — di-handle raise di atas
        raise ValueError(f"unhandled role: {role}")  # pragma: no cover

    return TenantScope(
        role=role,
        primary_tenant_id=primary.id if primary else None,
        visible_tenant_ids=visible_ids,
        user_id=user_id,
        is_cross_tenant=(role in {ROLE_AUDITOR_MISI, ROLE_ADMIN_UNI}),
    )


# ===== FastAPI dependency =====

def require_tenant_scope(
    db: Session = Depends(get_db),
    current: dict = Depends(__import__("app.api.v1.auth", fromlist=["get_current_user"]).get_current_user),
) -> TenantScope:
    """
    FastAPI dependency — pakai di endpoint:
    ```
    def endpoint(scope: TenantScope = Depends(require_tenant_scope)):
        ...
    ```

    Lazy import untuk `get_current_user` supaya tidak terjadi circular import
    (auth.py tidak perlu import tenant_scope.py).
    """
    scope = resolve_tenant_scope(db, current)
    if not scope.visible_tenant_ids:
        # Caller punya kredensial valid tapi scope kosong — bisa terjadi kalau:
        # 1. AUDITOR_MISI tenant tidak punya misi_konferens_id (orphan)
        # 2. ADMIN_UNI nama_uni tidak match ke tabel Uni (legacy tenant)
        # 3. Tenant record sudah dihapus
        # UX: explicit 403 supaya tidak silently return empty results.
        from fastapi import HTTPException, status as _status
        raise HTTPException(
            _status.HTTP_403_FORBIDDEN,
            f"Tenant scope kosong untuk role '{scope.role}'. "
            f"Periksa konfigurasi misi/unii tenant (id={scope.primary_tenant_id}).",
        )
    return scope


# ===== Query helpers =====

def tenant_filter(query, model, scope: TenantScope):
    """
    Apply tenant filter ke SQLAlchemy `Query` ATAU `Select`.

    Pakai:
    ```python
    q = db.query(Kuitansi)
    q = tenant_filter(q, Kuitansi, scope)  # WHERE kuitansi.tenant_id IN (scope.visible)
    ```

    Penting: model HARUS punya kolom `tenant_id`. Kalau tidak, raise AttributeError.
    """
    if not hasattr(model, "tenant_id"):
        raise AttributeError(
            f"Model {model.__name__} tidak punya kolom 'tenant_id'. "
            f"Gunakan filter manual atau ganti model."
        )
    return query.filter(model.tenant_id.in_(scope.visible_tenant_ids))


def assert_can_access(scope: TenantScope, tenant_id: int) -> None:
    """
    Hard guard — raise PermissionError kalau caller TIDAK boleh akses tenant_id.

    Pakai di service layer atau endpoint yang menerima tenant_id dari request body
    (bukan dari JWT) — misal upload file dengan tenant_id field.

    Raises:
        PermissionError: 403-equivalent.
    """
    if not scope.can_see(tenant_id):
        from fastapi import HTTPException, status as _status
        raise HTTPException(
            _status.HTTP_403_FORBIDDEN,
            f"Tenant {tenant_id} tidak ada dalam scope caller.",
        )


__all__ = [
    "TenantScope",
    "resolve_tenant_scope",
    "require_tenant_scope",
    "tenant_filter",
    "assert_can_access",
    "ROLE_JEMAAT_ONLY",
    "ROLE_AUDITOR_MISI",
    "ROLE_ADMIN_UNI",
    "ALL_ROLES",
]
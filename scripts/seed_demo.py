"""
Seed lengkap untuk development FLIPUS v1.3 (multi-tenant demo).

Isi:
- 1 Uni: GMAHK UKIKT
- 2 Misi Konferens:
    * DK.MIN — Misi DK Minahasa (utara)
    * DK.MIN.SEL — Misi DK Minahasa Selatan
- 2 PersentaseConfig (MISI scope, masing-masing)
- 2 Tenant:
    * Jemaat Nataan Ratahan       (DK.MIN)
    * Jemaat Sentrum Minahasa     (DK.MIN)
- 10 User demo (5 per jemaat):
    Jemaat A (Nataan Ratahan):
        bendahara_a / Bendahara123!  (BENDAHARA)
        ketua_a / Ketua123!         (KETUA_KEUANGAN)
        pendeta_a / Pendeta123!     (PENDETA)
        auditor_misi / AuditMisi123! (AUDITOR_MISI — scope DK.MIN+DK.MIN.SEL)
        admin_uni / AdminUni123!    (ADMIN_UNI — scope UKIKT)
    Jemaat B (Sentrum Minahasa):
        bendahara_b / Bendahara123! (BENDAHARA)
        ketua_b / Ketua123!         (KETUA_KEUANGAN)
        pendeta_b / Pendeta123!     (PENDETA)

Untuk demo multi-tenant:
- auditor_misi dan admin_uni otomatis lihat aggregate semua jemaat di scope-nya
- Bendahara/Ketua/Pendeta hanya lihat jemaat mereka sendiri (RBAC)

Pakai: .venv/bin/python3 scripts/seed_demo.py
"""
import os
import sys

# Pastikan root project ada di sys.path (supaya `from app...` jalan walau dipanggil dari scripts/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import generate_tenant_signature, hash_password  # noqa: E402
from app.models.master import MisiKonferens, PersentaseConfig, Uni  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402

# T32: Default branding per jemaat (placeholder untuk demo)
DEFAULT_BRANDING = {
    "nataan-ratahan": {
        "primary_color": "#1B4332",   # Sabbath green (default)
        "secondary_color": "#F5EFE0",
        "footer_text": "GMAHK Jemaat Nataan Ratahan · UKIKT",
    },
    "sentrum-minahasa": {
        "primary_color": "#0F4C5C",   # Deep teal (variasi supaya beda)
        "secondary_color": "#F5EFE0",
        "footer_text": "GMAHK Jemaat Sentrum Minahasa · UKIKT",
    },
}

# Buat semua tabel kalau belum ada (idempotent, tapi tidak alter existing).
Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    # ===== Uni =====
    uni = db.query(Uni).filter(Uni.kode == "UKIKT").first()
    if not uni:
        uni = Uni(kode="UKIKT", nama_resmi="GMAHK UKIKT")
        db.add(uni)
        db.commit()
        db.refresh(uni)
        print(f"Uni created: {uni.nama_resmi} (id={uni.id})")
    else:
        print(f"Uni exists: {uni.nama_resmi} (id={uni.id})")

    # ===== Misi Konferens (T92, 2026-08-23: pakai kode UKIKT proper, lihat seed_ukikt_misi_proper.py) =====
    MISI_DEFS = [
        ("M01_MIN_UTR_BTG", "Daerah Misi Minahasa Utara dan Bitung", "MISI"),
        ("M03_SULTENG", "Daerah Misi Sulawesi Tengah", "MISI"),
    ]
    misi_map = {}
    for kode, nama, jenis in MISI_DEFS:
        m = db.query(MisiKonferens).filter(MisiKonferens.kode == kode).first()
        if not m:
            m = MisiKonferens(kode=kode, nama_resmi=nama, uni_id=uni.id, jenis=jenis)
            db.add(m)
            db.commit()
            db.refresh(m)
            print(f"Misi created: {m.nama_resmi} (id={m.id})")
        else:
            print(f"Misi exists: {m.nama_resmi} (id={m.id})")
        misi_map[kode] = m

        # PersentaseConfig per misi
        cfg = (
            db.query(PersentaseConfig)
            .filter(PersentaseConfig.scope == "MISI", PersentaseConfig.ref_id == m.id)
            .first()
        )
        if not cfg:
            cfg = PersentaseConfig(
                scope="MISI",
                ref_id=m.id,
                pct_x_jemaat=0.0,       # 0% X tinggal di Jemaat → 100% X ke Misi (SDA tithe doctrine)
                pct_pt_jemaat=0.5,
                pct_khusus_jemaat=0.0,
            )
            db.add(cfg)
            db.commit()
            print(f"  PersentaseConfig created: MISI/{kode}")
        else:
            print(f"  PersentaseConfig exists: MISI/{kode}")

    # ===== Tenants (2 jemaat) =====
    TENANT_DEFS = [
        {
            "nama_jemaat": "Jemaat Nataan Ratahan",
            "misi_kode": "M01_MIN_UTR_BTG",
            "initial": "NT",
            "slug": "nataan-ratahan",
            "nama_pendeta": "Pdt. John Nataan",
            "nama_ketua": "Sdr. Jane Nataan",
            "nama_bendahara": "Sdri. Alice Nataan",
        },
        {
            "nama_jemaat": "Jemaat Sentrum Minahasa",
            "misi_kode": "M01_MIN_UTR_BTG",
            "initial": "ST",
            "slug": "sentrum-minahasa",
            "nama_pendeta": "Pdt. Mark Sentrum",
            "nama_ketua": "Sdr. Peter Sentrum",
            "nama_bendahara": "Sdri. Mary Sentrum",
        },
    ]
    tenant_map = {}  # nama_jemaat -> Tenant object
    for td in TENANT_DEFS:
        misi = misi_map[td["misi_kode"]]
        sig = generate_tenant_signature(uni.nama_resmi, misi.nama_resmi, td["nama_jemaat"])
        # Cek by signature ATAU by slug (slug UNIQUE, kalau signature drift karena salt berubah)
        t = (
            db.query(Tenant)
            .filter((Tenant.tenant_signature == sig) | (Tenant.slug == td["slug"]))
            .first()
        )
        if not t:
            t = Tenant(
                tenant_signature=sig,
                nama_uni=uni.nama_resmi,
                nama_kantor_misi=misi.nama_resmi,
                nama_jemaat_lokal=td["nama_jemaat"],
                nama_pendeta=td["nama_pendeta"],
                nama_ketua_keuangan=td["nama_ketua"],
                nama_bendahara=td["nama_bendahara"],
                initial_jemaat=td["initial"],
                slug=td["slug"],
                status="active",
                plan="standard",
                misi_konferens_id=misi.id,
            )
            db.add(t)
            db.commit()
            db.refresh(t)
            print(f"Tenant created: {t.nama_jemaat_lokal} (id={t.id})")
        else:
            print(f"Tenant exists: {t.nama_jemaat_lokal} (id={t.id})")
        tenant_map[td["nama_jemaat"]] = t

    # ===== Users (per jemaat + global auditor/admin) =====
    USERS = [
        # Jemaat A
        ("bendahara_a", "Bendahara Nataan", "6281234567001", "BENDAHARA", "Bendahara123!", "Jemaat Nataan Ratahan"),
        ("ketua_a", "Ketua Nataan", None, "KETUA_KEUANGAN", "Ketua123!", "Jemaat Nataan Ratahan"),
        ("pendeta_a", "Pendeta Nataan", "6281234567002", "PENDETA", "Pendeta123!", "Jemaat Nataan Ratahan"),
        # Jemaat B
        ("bendahara_b", "Bendahara Sentrum", "6281234568001", "BENDAHARA", "Bendahara123!", "Jemaat Sentrum Minahasa"),
        ("ketua_b", "Ketua Sentrum", None, "KETUA_KEUANGAN", "Ketua123!", "Jemaat Sentrum Minahasa"),
        ("pendeta_b", "Pendeta Sentrum", "6281234568002", "PENDETA", "Pendeta123!", "Jemaat Sentrum Minahasa"),
        # Global (auditor scope DK.MIN, admin scope UKIKT — stored in jemaat A for placeholder)
        ("auditor_misi", "Jerry Auditor", None, "AUDITOR_MISI", "AuditMisi123!", "Jemaat Nataan Ratahan"),
        ("admin_uni", "Jerry Admin Uni", None, "ADMIN_UNI", "AdminUni123!", "Jemaat Nataan Ratahan"),
    ]

    for username, nama, wa, role, password, jemaat_name in USERS:
        t = tenant_map[jemaat_name]
        u = db.query(User).filter(User.username == username).first()
        if not u:
            u = User(
                tenant_id=t.id,
                username=username,
                password_hash=hash_password(password),
                nama_lengkap=nama,
                nomor_whatsapp=wa,
                role=role,
                is_active=True,
            )
            db.add(u)
            db.commit()
            print(f"User created: {username:14s} / {password:15s} ({role:14s} @ {jemaat_name})")
        else:
            # Reset password + scope saat re-seed (untuk development convenience)
            u.password_hash = hash_password(password)
            u.role = role
            u.tenant_id = t.id
            u.is_active = True
            db.commit()
            print(f"User exists: {username:14s} (reset to {password:15s} @ {jemaat_name})")

    # Cleanup: hapus user lama dengan username TANPA suffix (bendahara, ketua_keuang, pendata)
    # supaya tidak ada username dobel yang membingungkan.
    LEGACY_USERNAMES = ["bendahara", "ketua_keuang", "pendata"]
    legacy_deleted = 0
    for legacy_name in LEGACY_USERNAMES:
        legacy_u = db.query(User).filter(User.username == legacy_name).first()
        if legacy_u:
            db.delete(legacy_u)
            db.commit()
            legacy_deleted += 1
            print(f"Legacy user removed: {legacy_name}")
    if legacy_deleted:
        print(f"({legacy_deleted} legacy user(s) dihapus supaya tidak duplikat)")

    # ===== T32: Branding default per jemaat (placeholder) + generate logo SVG =====
    from pathlib import Path as _Path
    logos_dir = _Path("storage/logos")
    logos_dir.mkdir(parents=True, exist_ok=True)

    for td in TENANT_DEFS:
        t = tenant_map[td["nama_jemaat"]]
        slug = td["slug"]
        branding = DEFAULT_BRANDING.get(slug, DEFAULT_BRANDING["nataan-ratahan"])

        # Update tenant branding fields (idempotent)
        t.primary_color = branding["primary_color"]
        t.secondary_color = branding["secondary_color"]
        t.footer_text = branding["footer_text"]
        db.commit()

        # Generate default logo SVG (inline circle + initial)
        logo_path = logos_dir / f"{slug}.svg"
        if not logo_path.exists():
            initial = td["initial"]
            primary = branding["primary_color"]
            svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="200" height="200">
  <circle cx="50" cy="50" r="48" fill="{primary}" stroke="#C9A961" stroke-width="3"/>
  <text x="50" y="50" text-anchor="middle" dominant-baseline="central"
        font-family="Georgia, serif" font-weight="700" font-size="40" fill="#C9A961">{initial}</text>
  <text x="50" y="80" text-anchor="middle" font-family="Georgia, serif" font-size="9" fill="#C9A961" letter-spacing="1">GMAHK</text>
</svg>"""
            logo_path.write_text(svg, encoding="utf-8")
            print(f"  Logo generated: {logo_path}")
        else:
            print(f"  Logo exists: {logo_path}")

        # Set logo_url di tenant (path relatif)
        t.logo_url = f"logos/{slug}.svg"
        db.commit()
        print(f"  Branding updated for {t.nama_jemaat_lokal}: primary={t.primary_color} logo={t.logo_url}")

    print("\n=== SEED SELESAI (multi-tenant demo) ===")
    print("\nLogin per jemaat:")
    print("  Jemaat A (Nataan Ratahan):")
    print("    bendahara_a / Bendahara123!  (BENDAHARA)")
    print("    ketua_a / Ketua123!          (KETUA_KEUANGAN)")
    print("    pendeta_a / Pendeta123!      (PENDETA)")
    print("  Jemaat B (Sentrum Minahasa):")
    print("    bendahara_b / Bendahara123!  (BENDAHARA)")
    print("    ketua_b / Ketua123!          (KETUA_KEUANGAN)")
    print("    pendeta_b / Pendeta123!      (PENDETA)")
    print("  Multi-tenant (lihat aggregate):")
    print("    auditor_misi / AuditMisi123! (AUDITOR_MISI — semua jemaat di DK.MIN)")
    print("    admin_uni / AdminUni123!     (ADMIN_UNI — semua jemaat di UKIKT)")
finally:
    db.close()

"""
FLIPUS v1.5 — Porsi Calculator (Jerry's Model B — pct_uni applied to TOTAL).

Logika pembagian persembahan 3-tier gereja GMAHK:
- Jemaat tahan sebagian (pct_jemaat = fraction of TOTAL)
- Uni dapat sebagian (pct_uni = fraction of TOTAL, BUKAN of sisa)
- Misi dapat sisanya (1 - pct_jemaat - pct_uni)

Field nama (preserve backward-compat dengan PersentaseConfig):
- pct_x_jemaat / pct_pt_jemaat / pct_khusus_jemaat  (Auditor Misi set)
- pct_x_uni / pct_pt_uni / pct_khusus_uni           (Admin Uni set)

Formula Jerry Model B (final 2026-08-23):
  porsi_jemaat = total × pct_jemaat
  porsi_uni    = total × pct_uni
  porsi_misi   = total - porsi_jemaat - porsi_uni
                 = total × (1 - pct_jemaat - pct_uni)

Constraint:
  0 ≤ pct_jemaat ≤ 1.0
  0 ≤ pct_uni    ≤ 1.0
  pct_jemaat + pct_uni ≤ 1.0  (supaya porsi_misi tidak negatif)

Contoh Jerry (2026-08-23, slide demo):
  PT 315,000, Auditor pct_pt_jemaat=0.5, Admin pct_pt_uni=0.30
    → jemaat 157,500 (50%)
    → uni     94,500 (30%)
    → misi    63,000 (20%)

  X 797,500, Auditor pct_x_jemaat=0, Admin pct_x_uni=0.41
    → jemaat       0 (0%)
    → uni    326,975 (41%)
    → misi   470,525 (59%)

  Catatan: pct_uni adalah fraction of TOTAL, bukan of (1 - pct_jemaat).
  Karena Auditor Misi & Admin Uni independen (tiap tier independent),
  constraint penjumlahan tetap ≤ 1.0 untuk hasil yang konsisten.
"""



def compute_porsi(
    x: int,
    pt: int,
    kh: int,
    pct_x_jemaat: float,
    pct_pt_jemaat: float,
    pct_khusus_jemaat: float,
    pct_x_uni: float,
    pct_pt_uni: float,
    pct_khusus_uni: float,
) -> dict:
    """
    Hitung porsi 3-tier per Jerry Model B (pct_uni applied to TOTAL).

    Returns dict dengan key:
        pj_x, pj_pt, pj_kh    (porsi jemaat)
        pu_x, pu_pt, pu_kh    (porsi uni)
        pm_x, pm_pt, pm_kh    (porsi misi = sisa setelah jemaat & uni)
    """
    # Jemaat — direct fraction of total (X & PT pakai pct = Jemaat retention)
    pj_x = int(round(x * pct_x_jemaat))
    pj_pt = int(round(pt * pct_pt_jemaat))

    # KH: SEMANTIK TERBALIK — pct_khusus_jemaat adalah "fraction to MISI"
    # (BUKAN Jemaat retention). Ini karena KH normally 100% stays in Jemaat,
    # kecuali Jerry memerintahkan distribusi khusus. Jadi:
    #   pm_kh = kh * pct_khusus_jemaat (fraction ke Misi)
    #   pj_kh = kh - pm_kh - pu_kh   (sisa stays in Jemaat)
    #   pu_kh = kh * pct_khusus_uni  (fraction ke Uni, default 0 = locked)
    pu_kh = int(round(kh * pct_khusus_uni))
    pm_kh = int(round(kh * pct_khusus_jemaat))
    pj_kh = max(0, kh - pm_kh - pu_kh)

    # Uni — direct fraction of total (BUKAN fraction of sisa)
    pu_x = int(round(x * pct_x_uni))
    pu_pt = int(round(pt * pct_pt_uni))

    # Misi — sisa setelah jemaat & uni (max 0 untuk safety)
    pm_x = max(0, x - pj_x - pu_x)
    pm_pt = max(0, pt - pj_pt - pu_pt)

    return {
        "pj_x": pj_x, "pj_pt": pj_pt, "pj_kh": pj_kh,
        "pu_x": pu_x, "pu_pt": pu_pt, "pu_kh": pu_kh,
        "pm_x": pm_x, "pm_pt": pm_pt, "pm_kh": pm_kh,
    }


def validate_porsi_constraint(
    pct_x_jemaat: float, pct_x_uni: float,
    pct_pt_jemaat: float, pct_pt_uni: float,
    pct_khusus_jemaat: float, pct_khusus_uni: float,
) -> list[str]:
    """
    Validasi Jerry Model B (pct_uni applied to TOTAL):
    - Range 0..1 untuk masing-masing
    - Constraint penjumlahan pct_jemaat + pct_uni ≤ 1.0 per tier

    Returns list of error messages (kosong = valid).
    """
    errors = []
    pairs = [
        ("X",      pct_x_jemaat,      pct_x_uni),
        ("PT",     pct_pt_jemaat,     pct_pt_uni),
        ("Khusus", pct_khusus_jemaat, pct_khusus_uni),
    ]
    for tier, pj, pu in pairs:
        if not (0.0 <= pj <= 1.0):
            errors.append(f"{tier} pct_jemaat ({pj}) harus 0..100%")
        if not (0.0 <= pu <= 1.0):
            errors.append(f"{tier} pct_uni ({pu}) harus 0..100%")
        if pj + pu > 1.0 + 1e-9:
            errors.append(
                f"{tier}: pct_jemaat ({pj:.0%}) + pct_uni ({pu:.0%}) = "
                f"{pj+pu:.0%} > 100%. Total porsi tidak boleh melebihi 100%."
            )
    return errors

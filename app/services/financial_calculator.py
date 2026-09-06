"""
FLIPUS v1.1 — Financial calculator dengan persentase configurable.

Aturan GMAHK (default, bisa diubah oleh Auditor via persentase_config):
- X (Perpuluhan)  -> 100% ke Kantor Misi (pct_x_jemaat = 1.0)
- PT (Persembahan Terpadu) -> 50% Misi + 50% Kas Jemaat (pct_pt_jemaat = 0.5)
- Khusus (Persembahan Khusus) -> 50% Misi + 50% Kas Jemaat (pct_khusus_jemaat = 0.5)

Untuk Auditor/Admin Uni, hitung porsi 2-layer:
- Layer 1 (Jemaat→Misi): Porsi_X_Misi = X * pct_x_jemaat
- Layer 2 (Misi→Uni): Porsi_X_Uni = Porsi_X_Misi * pct_x_uni
"""



def calculate_distribution(
    perpuluhan_x: int,
    pt: int,
    khusus: int = 0,
    pct_x_jemaat: float = 1.0,
    pct_pt_jemaat: float = 0.5,
    pct_khusus_jemaat: float = 0.5,
    pct_x_uni: float = 0.0,
    pct_pt_uni: float = 0.0,
    pct_khusus_uni: float = 0.0,
) -> dict:
    """
    Hitung distribusi persembahan sesuai konfigurasi persentase.

    Returns dict dengan keys:
        - total
        - porsi_kantor_misi (total yang ke Misi, net-of-Uni)
        - porsi_kas_jemaat  (sisa di Jemaat)
        - porsi_khusus_misi, porsi_khusus_jemaat (breakdown Khusus)
        - porsi_x_uni, porsi_pt_uni, porsi_khusus_uni (potongan Uni)
        - porsi_x_misi_net, porsi_pt_misi_net, porsi_khusus_misi_net (sisa di Misi setelah dipotong Uni)
    """
    if perpuluhan_x < 0 or pt < 0 or khusus < 0:
        raise ValueError("Nominal tidak boleh negatif")

    # Layer 1: Jemaat → Misi
    porsi_x_misi = int(perpuluhan_x * pct_x_jemaat)
    porsi_pt_misi = int(pt * pct_pt_jemaat)
    porsi_khusus_misi = int(khusus * pct_khusus_jemaat)

    # Kas Jemaat = total - porsi_misi
    porsi_x_jemaat = perpuluhan_x - porsi_x_misi
    porsi_pt_jemaat = pt - porsi_pt_misi
    porsi_khusus_jemaat = khusus - porsi_khusus_misi

    # Layer 2: Misi → Uni (potong dari porsi_misi)
    porsi_x_uni = int(porsi_x_misi * pct_x_uni)
    porsi_pt_uni = int(porsi_pt_misi * pct_pt_uni)
    porsi_khusus_uni = int(porsi_khusus_misi * pct_khusus_uni)

    # Sisa di Misi setelah dipotong Uni
    porsi_x_misi_net = porsi_x_misi - porsi_x_uni
    porsi_pt_misi_net = porsi_pt_misi - porsi_pt_uni
    porsi_khusus_misi_net = porsi_khusus_misi - porsi_khusus_uni

    # Total untuk display
    total = perpuluhan_x + pt + khusus
    total_porsi_misi = porsi_x_misi + porsi_pt_misi + porsi_khusus_misi
    total_porsi_jemaat = porsi_x_jemaat + porsi_pt_jemaat + porsi_khusus_jemaat
    total_porsi_uni = porsi_x_uni + porsi_pt_uni + porsi_khusus_uni

    return {
        "total": total,
        "porsi_kantor_misi": total_porsi_misi,   # total ke Misi (sebelum dipotong Uni)
        "porsi_kas_jemaat": total_porsi_jemaat,  # total sisa di Jemaat
        "porsi_khusus_misi": porsi_khusus_misi,
        "porsi_khusus_jemaat": porsi_khusus_jemaat,
        # Layer 2 (untuk Auditor/Admin Uni)
        "porsi_x_uni": porsi_x_uni,
        "porsi_pt_uni": porsi_pt_uni,
        "porsi_khusus_uni": porsi_khusus_uni,
        "porsi_x_misi_net": porsi_x_misi_net,
        "porsi_pt_misi_net": porsi_pt_misi_net,
        "porsi_khusus_misi_net": porsi_khusus_misi_net,
        "total_porsi_uni": total_porsi_uni,
    }

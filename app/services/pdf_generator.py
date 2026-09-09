"""
FLIPUS v1.1 — PDF Generator untuk rekap mingguan.

Output: PDF A4 dengan header resmi (logo tenant kalau ada, nama Uni/Misi/Jemaat),
nama pejabat vertikal), tabel kuitansi (aggregate only), grand total, distribusi.
grand total, dan distribusi porsi.

Privacy:
- Tidak ada nama pemberi (aggregate only)
- Hanya aggregate X, PT, Khusus per kuitansi
- Nomor kuitansi auto-generated, tidak ada PII

Format mengikuti spec:
- Logo Gereja Advent: pojok kanan atas (placeholder image atau text logo)
- Nama Uni: tengah atas
- Nama Misi/Konferens: di bawah Uni (susunan vertikal)
- Nama Jemaat: kiri atas tabel
- Nama Pendeta/Ketua/Bendahara: di bawah tabel (vertikal)
"""

from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.models.transaction import Kuitansi
from app.utils.number_to_words import bilang as rupiah_to_words

# Tahap 21: branding-aware colors
DEFAULT_PRIMARY = "#1B4332"  # hijau tua (default green)
DEFAULT_SECONDARY = "#F5EFE0"  # cream (default)
COLOR_GOLD = colors.HexColor("#B8860B")  # gold accent (tetap)
COLOR_GRAY = colors.HexColor("#666666")
COLOR_BORDER = colors.HexColor("#CCCCCC")


def _hex_to_reportlab(hex_color: str):
    """Convert hex color string to reportlab colors object."""
    return colors.HexColor(hex_color)


def _get_tenant_colors(tenant: Tenant) -> tuple:
    """Return (primary_color, secondary_color) untuk tenant, fallback ke default."""
    primary = tenant.primary_color or DEFAULT_PRIMARY
    secondary = tenant.secondary_color or DEFAULT_SECONDARY
    return _hex_to_reportlab(primary), _hex_to_reportlab(secondary)


def _load_logo_image(path: Path, max_height_cm: float = 2.0):
    """Load reportlab Image dari path, scale ke max height. None kalau gagal."""
    try:
        img = Image(str(path))
        if img.imageHeight > max_height_cm * cm:
            ratio = (max_height_cm * cm) / img.imageHeight
            img.drawWidth = img.imageWidth * ratio
            img.drawHeight = img.imageHeight * ratio
        return img
    except Exception:
        return None


def _get_logo_image(tenant: Tenant, max_height_cm: float = 2.0):
    """Return logo tenant (storage) ATAU logo asli FLIPUS — else None."""
    if not tenant.logo_url:
        return None
    logo_path = Path("storage") / tenant.logo_url.lstrip("/")
    if not logo_path.exists():
        return None
    if logo_path.suffix.lower() == ".svg":
        return None
    return _load_logo_image(logo_path, max_height_cm)


def _get_flipus_logo_image(max_height_cm: float = 2.0):
    """Logo asli FLIPUS (app/static/gmahk-logo.png) — fallback saat tenant tanpa logo."""
    logo_path = Path(__file__).resolve().parent.parent / "static" / "gmahk-logo.png"
    if not logo_path.exists():
        return None
    return _load_logo_image(logo_path, max_height_cm)


def _fmt_rupiah(amount: int) -> str:
    """Format integer jadi '1.500.000' (titik ribuan Indonesia, tanpa prefix).

    (Tadinya 'Rp 1.500.000' — sesuai permintaan Jerry, semua cell nominal
    dalam tabel PDF kini tanpa prefix 'Rp'; footer note menjelaskan satuan.)
    """
    if amount is None:
        return "0"
    return f"{amount:,}".replace(",", ".")


def abbreviate_khusus(nama_jenis: str) -> str:
    """Singkatkan nama jenis persembahan khusus jadi kode kolom (uppercase).

    Aturan Jerry (2026-09-09):
    - 1 kata: ambil 4 huruf pertama → "PEMBANGUNAN"→"PEMB", "PENDIDIKAN"→"PEND"
    - 2+ kata: huruf pertama tiap kata → "SEKOLAH SABAT"→"SS", "ULANG TAHUN"→"UT"
    - 3 kata: huruf pertama 3 kata dipakai → "SEKOLAH SABAT ANAK"→"SSA"
    - Max 4 huruf kalau perlu (default: [1,1,1,1]); dinaikkan 2-huruf-tiap-kata
      hanya oleh resolver konflik.
    """
    words = [w for w in (nama_jenis or "").upper().split() if w]
    if not words:
        return "KHS"
    if len(words) == 1:
        return words[0][:4]
    if len(words) == 2:
        return (words[0][0] + words[1][0])[:4]
    # 3+ kata: huruf pertama tiap kata, max 4
    return "".join(w[0] for w in words[:4])


def _resolve_khusus_abbrevs(special_jenis: list[str]) -> dict[str, str]:
    """Assign unique abbreviation per jenis; naikkan granularity kalau konflik.

    Level resolusi: [1,1,1,1] (default) → [2,2,2,2] (2 huruf awal tiap kata)
    → [3,3,3,3] → [4,4,4,4] → per-kata prefix 1..n (fallback = full 4-char).
    """
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for nama in special_jenis:
        words = [w for w in nama.upper().split() if w]
        if not words:
            mapping[nama] = "KHS"
            continue
        abbrev = abbreviate_khusus(nama)
        level = 1
        while abbrev in used:
            # coba 2 huruf awal tiap kata
            if level == 1:
                abbrev = ("".join(w[:2] for w in words))[:4] if len(words) > 1 else (words[0][:4])
            elif level == 2:
                abbrev = ("".join(w[:3] for w in words))[:4] if len(words) > 1 else words[0][:4]
            elif level == 3:
                abbrev = ("".join(w[:4] for w in words))[:4] if len(words) > 1 else words[0][:4]
            else:
                # unique suffix
                abbrev = (abbrev[:3] + str(level - 3))[:4]
            level += 1
            if level > 8:
                break
        mapping[nama] = abbrev
        used.add(abbrev)
    return mapping


def _compute_kategori_breakdown(db, kuitansi_ids: list[int]) -> tuple[list[str], dict[int, dict[str, int]]]:
    """
    Ambil breakdown per-jenis persembahan khusus (selain X & PT) dari pivot.

    Returns:
        special_jenis: ordered list of UPPERCASE nama jenis yang muncul.
        breakdown: {kuitansi_id: {jenis_upper: nominal}}
    """
    if not db or not kuitansi_ids:
        return [], {}
    from app.models.kategori_pemasukan import KategoriPemasukan, KuitansiKategori

    pivots = db.query(KuitansiKategori).filter(KuitansiKategori.kuitansi_id.in_(kuitansi_ids)).all()
    if not pivots:
        return [], {}

    kategori_ids = {p.kategori_id for p in pivots}
    kategori_by_id = {
        k.id: k for k in db.query(KategoriPemasukan).filter(KategoriPemasukan.id.in_(kategori_ids)).all()
    }

    breakdown: dict[int, dict[str, int]] = {}
    special_jenis: list[str] = []
    seen: set[str] = set()
    for p in pivots:
        kat = kategori_by_id.get(p.kategori_id)
        if not kat:
            continue
        if kat.alias in ("X", "PT"):
            continue
        nama_upper = (kat.nama or "").upper()
        if not nama_upper:
            continue
        if nama_upper not in seen:
            seen.add(nama_upper)
            special_jenis.append(nama_upper)
        row = breakdown.setdefault(p.kuitansi_id, {})
        row[nama_upper] = row.get(nama_upper, 0) + (p.nominal or 0)

    return special_jenis, breakdown


def _build_styles(primary_color=colors.HexColor("#1B4332")):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="HeaderTitle",
            parent=styles["Heading1"],
            fontSize=14,
            alignment=TA_CENTER,
            textColor=primary_color,
            spaceAfter=2,
            fontName="Helvetica-Bold",
        )
    )
    styles.add(
        ParagraphStyle(
            name="HeaderSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            alignment=TA_CENTER,
            textColor=primary_color,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="JemaatName",
            parent=styles["Normal"],
            fontSize=11,
            alignment=TA_LEFT,
            textColor=primary_color,
            fontName="Helvetica-Bold",
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="OfficialName",
            parent=styles["Normal"],
            fontSize=9,
            alignment=TA_LEFT,
        )
    )
    return styles


def _build_header_table(
    uni_name: str,
    misi_name: str,
    jemaat_name: str,
    primary_color=colors.HexColor("#1B4332"),
    logo_image=None,
) -> Table:
    """
    Header sesuai spec + Tahap 21 branding:
    - Kiri: nama Jemaat (di atas tabel)
    - Tengah: nama Uni (atas) + nama Misi (bawah, susunan vertikal)
    - Kanan: logo tenant (kalau ada) atau placeholder text
    """
    # Logo: image kalau ada, else fallback text "FLIPUS"
    if logo_image is not None:
        logo_cell = logo_image
    else:
        logo_cell = Paragraph(
            "<b>FLIPUS</b><br/><font size=8>GMAHK UKIKT</font>",
            ParagraphStyle("logo", alignment=TA_RIGHT, fontSize=12, textColor=COLOR_GOLD),
        )
    nama_uni = Paragraph(
        f"<b>{uni_name}</b>",
        ParagraphStyle("uni", alignment=TA_CENTER, fontSize=11, textColor=primary_color),
    )
    nama_misi = Paragraph(
        f"{misi_name}",
        ParagraphStyle("misi", alignment=TA_CENTER, fontSize=9, textColor=COLOR_GRAY),
    )

    nama_jemaat = Paragraph(
        f"<b>{jemaat_name}</b>",
        ParagraphStyle("jemaat", alignment=TA_LEFT, fontSize=11, textColor=primary_color),
    )

    # 3-column header: Logo | Uni/Misi | Jemaat
    uni_block = Table([[nama_uni], [nama_misi]], colWidths=[8 * cm])
    uni_block.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    header_table = Table(
        [[logo_cell, uni_block, nama_jemaat]],
        colWidths=[4 * cm, 9 * cm, 5 * cm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, 0), 1, primary_color),
            ]
        )
    )
    return header_table


def _build_footer_table(pendeta: str, ketua: str, bendahara: str) -> Table:
    """
    Footer tanda tangan HORIZONTAL 3 kolom sejajar (Pendeta | Ketua | Bendahara).
    Tiap kolom: spasi 60pt kosong → garis tanda tangan → nama (bold 10pt)
    → jabatan (regular 9pt). Rata tengah, tidak tumpuk vertikal.
    """
    def _sig_cell(nama: str, jabatan: str) -> Paragraph:
        nama_html = f"<b>{nama}</b>" if nama else "<br/>"
        return Paragraph(
            f"<br/><br/><br/>___________<br/>{nama_html}<br/>{jabatan}",
            ParagraphStyle(
                "sig_cell",
                fontSize=9,
                alignment=TA_CENTER,
                leading=14,
            ),
        )

    cells = [
        _sig_cell(pendeta, "Pendeta"),
        _sig_cell(ketua, "Ketua"),
        _sig_cell(bendahara, "Bendahara"),
    ]

    # 3 kolom sama lebar (landscape usable 25.7cm → 8.5cm tiap kolom)
    table = Table([cells], colWidths=[8.5 * cm] * 3)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 40),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def generate_mingguan_pdf(
    kuitansi_list: list[Kuitansi],
    tenant: Tenant,
    id_rekap_mingguan: str,
    tanggal_sabat_iso: str,
    output_path: str | None = None,
    db: Session | None = None,
) -> bytes:
    # Tahap 21: tenant branding — logo tenant, fallback logo asli FLIPUS
    primary_color, secondary_color = _get_tenant_colors(tenant)
    logo_image = _get_logo_image(tenant) or _get_flipus_logo_image()
    """
    Generate PDF rekap mingguan — aggregate only (TIDAK ada nama pemberi).

    Args:
        kuitansi_list: list of Kuitansi objects (filtered by id_rekap)
        tenant: Tenant object (untuk nama_jemaat, nama_uni, dll)
        id_rekap_mingguan: id rekap (misal 'FLIPUS-2026-DEMO-001')
        tanggal_sabat_iso: ISO date (misal '2026-08-22')
        output_path: kalau diisi, save ke file. Kalau None, return bytes.

    Returns:
        bytes (PDF binary) atau path jika output_path diisi.
    """
    styles = _build_styles(primary_color)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    elements = []

    # === HEADER ===
    elements.append(
        _build_header_table(
            uni_name=tenant.nama_uni,
            misi_name=tenant.nama_kantor_misi,
            jemaat_name=tenant.nama_jemaat_lokal,
            primary_color=primary_color,
            logo_image=logo_image,
        )
    )
    elements.append(Spacer(1, 8))

    # Title
    elements.append(
        Paragraph(
            "<b>LAPORAN PENERIMAAN PERPULUHAN & PERSEMBAHAN</b>",
            ParagraphStyle("title", parent=styles["HeaderTitle"], fontSize=13),
        )
    )
    elements.append(
        Paragraph(
            f"ID Rekap: <b>{id_rekap_mingguan}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Tanggal Sabat: <b>{tanggal_sabat_iso}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Total Kuitansi: <b>{len(kuitansi_list)}</b>",
            styles["HeaderSubtitle"],
        )
    )
    elements.append(Spacer(1, 10))

    # === TABEL KUITANSI (aggregate only — no nama pemberi) ===
    # Kolom "Khusus" kini DINAMIS: setiap jenis persembahan khusus (selain
    # X/PT) jadi kolom terpisah. Header pakai SINGKATAN (abbreviate_khusus)
    # supaya kolom ramping; legend di bawah tabel jelaskan kode-nya.
    kuitansi_ids = [k.id for k in kuitansi_list]
    special_jenis, kategori_breakdown = _compute_kategori_breakdown(db, kuitansi_ids)
    abbrev_map = _resolve_khusus_abbrevs(special_jenis)

    header = ["No", "No. Kuitansi", "X", "PT"] + [abbrev_map[j] for j in special_jenis] + [
        "Total",
        "Porsi Misi",
        "Porsi Jemaat",
    ]
    data = [header]

    sum_x = sum_pt = 0
    sum_misi = sum_jemaat = 0
    sum_special: dict[str, int] = {j: 0 for j in special_jenis}

    for idx, k in enumerate(kuitansi_list, 1):
        kb = kategori_breakdown.get(k.id, {})
        row = [
            str(idx),
            k.nomor_kuitansi,
            _fmt_rupiah(k.perpuluhan_x_angka),
            _fmt_rupiah(k.pt_angka),
        ]
        for j in special_jenis:
            val = kb.get(j, 0)
            row.append(_fmt_rupiah(val) if val else "-")
            sum_special[j] += val
        row += [
            _fmt_rupiah(k.total_pemberian_angka),
            _fmt_rupiah(k.porsi_kantor_misi),
            _fmt_rupiah(k.porsi_kas_jemaat),
        ]
        data.append(row)
        sum_x += k.perpuluhan_x_angka
        sum_pt += k.pt_angka
        sum_misi += k.porsi_kantor_misi
        sum_jemaat += k.porsi_kas_jemaat

    # Grand total row — TANPA tag <b>: Table style sudah set FONTNAME
    # Helvetica-Bold untuk baris terakhir. Tag literal <b> akan tercetak
    # sebagai teks harfiah karena cell berupa string (bukan Paragraph).
    grand_total = sum_x + sum_pt
    _grand = [
        "",
        "GRAND TOTAL",
        _fmt_rupiah(sum_x),
        _fmt_rupiah(sum_pt),
    ]
    for j in special_jenis:
        _grand.append(_fmt_rupiah(sum_special[j]) if sum_special[j] else "-")
    _grand += [
        _fmt_rupiah(grand_total),
        _fmt_rupiah(sum_misi),
        _fmt_rupiah(sum_jemaat),
    ]
    data.append(_grand)

    # Dynamic colWidths (landscape A4 = 29.7cm, margin 2cm → 25.7cm usable)
    _fixed_start = [1 * cm, 3.2 * cm, 1.6 * cm, 1.6 * cm]
    _fixed_end = [2.2 * cm, 2.0 * cm, 2.0 * cm]
    _used = sum([1, 3.2, 1.6, 1.6, 2.2, 2.0, 2.0])  # cm
    _available = 25.7 - _used
    colWidths = _fixed_start
    if special_jenis:
        _w = (_available / len(special_jenis)) * cm
        colWidths += [_w] * len(special_jenis)
    colWidths += _fixed_end

    table = Table(
        data,
        colWidths=colWidths,
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), primary_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                # Body
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (1, 1), (1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                # Grand total row
                ("BACKGROUND", (0, -1), (-1, -1), primary_color),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                # Borders
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("BOX", (0, 0), (-1, -1), 1, primary_color),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 4))

    # Legend singkatan kolom khusus
    if special_jenis and abbrev_map:
        _legend_parts = [f"{abbrev_map[j]}={j.title()}" for j in special_jenis]
        elements.append(
            Paragraph(
                f"<i>Keterangan: {', '.join(_legend_parts)}</i>",
                ParagraphStyle("legend_khusus", fontSize=8, alignment=TA_LEFT, textColor=COLOR_GRAY),
            )
        )
        elements.append(Spacer(1, 2))

    # Footer note — jelaskan satuan (nominal tanpa prefix Rp di cell)
    elements.append(
        Paragraph(
            "<i>Catatan: Nominal dalam bentuk Rupiah (Rp)</i>",
            ParagraphStyle("footer_note", fontSize=8, alignment=TA_LEFT, textColor=COLOR_GRAY),
        )
    )
    elements.append(Spacer(1, 10))

    # Terbilang
    elements.append(
        Paragraph(
            f"<b>Terbilang:</b> {rupiah_to_words(grand_total)} rupiah",
            ParagraphStyle("terbilang", fontSize=10, fontName="Helvetica-Bold"),
        )
    )
    elements.append(Spacer(1, 10))

    # Distribution summary box
    dist_data = [
        ["Penyaluran", "Nominal"],
        ["Kantor Misi", _fmt_rupiah(sum_misi)],
        ["Kas Jemaat", _fmt_rupiah(sum_jemaat)],
        ["TOTAL", _fmt_rupiah(sum_misi + sum_jemaat)],
    ]
    dist_table = Table(dist_data, colWidths=[6 * cm, 6 * cm])
    dist_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), secondary_color),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("BACKGROUND", (0, -1), (-1, -1), COLOR_GOLD),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(dist_table)
    elements.append(Spacer(1, 16))

    # === FOOTER (pejabat) ===
    elements.append(
        _build_footer_table(
            pendeta=tenant.nama_pendeta or "",
            ketua=tenant.nama_ketua_keuangan or "",
            bendahara=tenant.nama_bendahara or "",
        )
    )
    # Tahap 21: optional footer text dari tenant
    if tenant.footer_text:
        elements.append(Spacer(1, 4))
        elements.append(
            Paragraph(
                f"<i>{tenant.footer_text}</i>",
                ParagraphStyle("footer_text", fontSize=8, alignment=TA_LEFT, textColor=COLOR_GRAY),
            )
        )
    elements.append(Spacer(1, 6))

    # Generator watermark
    elements.append(
        Paragraph(
            f"<font size=7 color=gray>Dokumen ini dihasilkan otomatis oleh FLIPUS v1.1 pada "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. ID: {id_rekap_mingguan}</font>",
            ParagraphStyle("footer", alignment=TA_RIGHT, fontSize=7, textColor=COLOR_GRAY),
        )
    )

    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        return pdf_bytes

    return pdf_bytes


_STATUS_LABEL = {
    "draft": "Draft",
    "pending_approval": "Pending Approval",
    "approved_ketua": "Disetujui Ketua",
    "approved": "Disetujui",
    "rejected": "Ditolak",
}


def generate_pengeluaran_pdf(
    pengeluaran_list,
    kategori_map: dict[int, str],
    tenant: Tenant,
    start_date: str,
    end_date: str,
    output_path: str | None = None,
) -> bytes:
    """Generate PDF Laporan Pengeluaran (LANDSCAPE A4, tanpa prefix Rp).

    Kolom: No | Tanggal | Kategori | Penerima | Metode Bayar | Jumlah |
    Deskripsi | Status Approval. Grand total + footer note satuan Rupiah.
    """
    primary_color, secondary_color = _get_tenant_colors(tenant)
    logo_image = _get_logo_image(tenant) or _get_flipus_logo_image()
    styles = _build_styles(primary_color)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    elements = []

    # === HEADER ===
    elements.append(
        _build_header_table(
            uni_name=tenant.nama_uni,
            misi_name=tenant.nama_kantor_misi,
            jemaat_name=tenant.nama_jemaat_lokal,
            primary_color=primary_color,
            logo_image=logo_image,
        )
    )
    elements.append(Spacer(1, 8))

    # Title + subtitle
    elements.append(
        Paragraph(
            "<b>LAPORAN PENGELUARAN JEMAAT</b>",
            ParagraphStyle("title", parent=styles["HeaderTitle"], fontSize=13),
        )
    )
    elements.append(
        Paragraph(
            f"Periode: <b>{start_date}</b> s/d <b>{end_date}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Total Transaksi: <b>{len(pengeluaran_list)}</b>",
            styles["HeaderSubtitle"],
        )
    )
    elements.append(Spacer(1, 10))

    # === TABEL ===
    header = [
        "No",
        "Tanggal",
        "Kategori",
        "Penerima",
        "Metode Bayar",
        "Jumlah",
        "Deskripsi",
        "Status Approval",
    ]
    data = [header]

    total_jumlah = 0
    for idx, p in enumerate(pengeluaran_list, 1):
        total_jumlah += p.jumlah or 0
        data.append(
            [
                str(idx),
                p.tanggal,
                kategori_map.get(p.kategori_pengeluaran_id, "-"),
                p.penerima or "-",
                p.metode_bayar or "-",
                _fmt_rupiah(p.jumlah),
                p.deskripsi or "-",
                _STATUS_LABEL.get(p.status, p.status or "-"),
            ]
        )

    data.append(
        [
            "",
            "",
            "",
            "",
            "",
            _fmt_rupiah(total_jumlah),
            "GRAND TOTAL",
            "",
        ]
    )

    table = Table(
        data,
        colWidths=[0.8 * cm, 2.2 * cm, 3.0 * cm, 3.0 * cm, 2.4 * cm, 2.4 * cm, 6.5 * cm, 3.0 * cm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), primary_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
                ("ALIGN", (5, 1), (5, -1), "RIGHT"),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (1, 1), (1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, -1), (-1, -1), primary_color),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("BOX", (0, 0), (-1, -1), 1, primary_color),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 4))

    elements.append(
        Paragraph(
            "<i>Catatan: Nominal dalam bentuk Rupiah (Rp)</i>",
            ParagraphStyle("footer_note", fontSize=8, alignment=TA_LEFT, textColor=COLOR_GRAY),
        )
    )
    elements.append(Spacer(1, 10))

    elements.append(
        Paragraph(
            f"<b>Terbilang:</b> {rupiah_to_words(total_jumlah)} rupiah",
            ParagraphStyle("terbilang", fontSize=10, fontName="Helvetica-Bold"),
        )
    )
    elements.append(Spacer(1, 16))

    # === FOOTER ===
    elements.append(
        _build_footer_table(
            pendeta=tenant.nama_pendeta or "",
            ketua=tenant.nama_ketua_keuangan or "",
            bendahara=tenant.nama_bendahara or "",
        )
    )
    elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(
            f"<font size=7 color=gray>Dokumen ini dihasilkan otomatis oleh FLIPUS pada "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</font>",
            ParagraphStyle("footer", alignment=TA_RIGHT, fontSize=7, textColor=COLOR_GRAY),
        )
    )

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        return pdf_bytes

    return pdf_bytes

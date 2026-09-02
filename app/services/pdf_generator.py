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
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image,
)
from reportlab.pdfgen import canvas

from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.utils.number_to_words import bilang as rupiah_to_words


# Tahap 21: branding-aware colors
DEFAULT_PRIMARY = "#1B4332"   # hijau tua (default green)
DEFAULT_SECONDARY = "#F5EFE0"  # cream (default)
COLOR_GOLD = colors.HexColor("#B8860B")    # gold accent (tetap)
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


def _get_logo_image(tenant: Tenant, max_height_cm: float = 2.0):
    """Return reportlab Image kalau tenant punya logo, else None."""
    if not tenant.logo_url:
        return None
    logo_path = Path("storage") / tenant.logo_url.lstrip("/")
    if not logo_path.exists():
        return None
    if logo_path.suffix.lower() == ".svg":
        return None
    try:
        img = Image(str(logo_path))
        if img.imageHeight > max_height_cm * cm:
            ratio = (max_height_cm * cm) / img.imageHeight
            img.drawWidth = img.imageWidth * ratio
            img.drawHeight = img.imageHeight * ratio
        return img
    except Exception:
        return None


def _fmt_rupiah(amount: int) -> str:
    """Format integer jadi 'Rp 1.500.000'."""
    return f"Rp {amount:,}".replace(",", ".")


def _build_styles(primary_color=colors.HexColor("#1B4332")):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="HeaderTitle",
        parent=styles["Heading1"],
        fontSize=14,
        alignment=TA_CENTER,
        textColor=primary_color,
        spaceAfter=2,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        name="HeaderSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=primary_color,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="JemaatName",
        parent=styles["Normal"],
        fontSize=11,
        alignment=TA_LEFT,
        textColor=primary_color,
        fontName="Helvetica-Bold",
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="OfficialName",
        parent=styles["Normal"],
        fontSize=9,
        alignment=TA_LEFT,
    ))
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
    # Logo: image kalau ada, else placeholder text
    if logo_image is not None:
        logo_cell = logo_image
    else:
        logo_cell = Paragraph(
            "<b>[LOGO GMAHK]</b><br/><font size=8>Advent</font>",
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
    uni_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    header_table = Table(
        [[logo_cell, uni_block, nama_jemaat]],
        colWidths=[4 * cm, 9 * cm, 5 * cm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, primary_color),
    ]))
    return header_table


def _build_footer_table(pendeta: str, ketua: str, bendahara: str) -> Table:
    """
    Footer sesuai spec:
    - Nama Pendeta/Ketua/Bendahara disusun vertikal di bawah tabel
    - Posisi: kiri
    """
    names_html = ""
    if pendeta:
        names_html += f"<b>Pdt. {pendeta}</b><br/>Pendeta<br/><br/>"
    if ketua:
        names_html += f"<b>{ketua}</b><br/>Ketua<br/><br/>"
    if bendahara:
        names_html += f"<b>{bendahara}</b><br/>Bendahara"

    cell = Paragraph(
        names_html,
        ParagraphStyle("officials", fontSize=9, alignment=TA_LEFT),
    )

    table = Table([[cell]], colWidths=[8 * cm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def generate_mingguan_pdf(
    kuitansi_list: List[Kuitansi],
    tenant: Tenant,
    id_rekap_mingguan: str,
    tanggal_sabat_iso: str,
    output_path: Optional[str] = None,
) -> bytes:
    # Tahap 21: tenant branding
    primary_color, secondary_color = _get_tenant_colors(tenant)
    logo_image = _get_logo_image(tenant)
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
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    elements = []

    # === HEADER ===
    elements.append(_build_header_table(
        uni_name=tenant.nama_uni,
        misi_name=tenant.nama_kantor_misi,
        jemaat_name=tenant.nama_jemaat_lokal,
        primary_color=primary_color,
        logo_image=logo_image,
    ))
    elements.append(Spacer(1, 8))

    # Title
    elements.append(Paragraph(
        "<b>LAPORAN PENERIMAAN PERPULUHAN & PERSEMBAHAN</b>",
        ParagraphStyle("title", parent=styles["HeaderTitle"], fontSize=13),
    ))
    elements.append(Paragraph(
        f"ID Rekap: <b>{id_rekap_mingguan}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Tanggal Sabat: <b>{tanggal_sabat_iso}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Total Kuitansi: <b>{len(kuitansi_list)}</b>",
        styles["HeaderSubtitle"],
    ))
    elements.append(Spacer(1, 10))

    # === TABEL KUITANSI (aggregate only — no nama pemberi) ===
    data = [["No", "No. Kuitansi", "X", "PT", "Khusus", "Total", "Porsi Misi", "Porsi Jemaat"]]

    sum_x = sum_pt = sum_khusus = 0
    sum_misi = sum_jemaat = 0

    for idx, k in enumerate(kuitansi_list, 1):
        data.append([
            str(idx),
            k.nomor_kuitansi,
            _fmt_rupiah(k.perpuluhan_x_angka),
            _fmt_rupiah(k.pt_angka),
            _fmt_rupiah(k.khusus_angka) if k.khusus_angka else "-",
            _fmt_rupiah(k.total_pemberian_angka),
            _fmt_rupiah(k.porsi_kantor_misi),
            _fmt_rupiah(k.porsi_kas_jemaat),
        ])
        sum_x += k.perpuluhan_x_angka
        sum_pt += k.pt_angka
        sum_khusus += k.khusus_angka
        sum_misi += k.porsi_kantor_misi
        sum_jemaat += k.porsi_kas_jemaat

    # Grand total row
    grand_total = sum_x + sum_pt
    data.append([
        "",
        "<b>GRAND TOTAL</b>",
        f"<b>{_fmt_rupiah(sum_x)}</b>",
        f"<b>{_fmt_rupiah(sum_pt)}</b>",
        f"<b>{_fmt_rupiah(sum_khusus) if sum_khusus else '-'}</b>",
        f"<b>{_fmt_rupiah(grand_total)}</b>",
        f"<b>{_fmt_rupiah(sum_misi)}</b>",
        f"<b>{_fmt_rupiah(sum_jemaat)}</b>",
    ])

    table = Table(
        data,
        colWidths=[1 * cm, 3.8 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
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
    ]))
    elements.append(table)
    elements.append(Spacer(1, 10))

    # Terbilang
    elements.append(Paragraph(
        f"<b>Terbilang:</b> {rupiah_to_words(grand_total)} rupiah",
        ParagraphStyle("terbilang", fontSize=10, fontName="Helvetica-Bold"),
    ))
    elements.append(Spacer(1, 10))

    # Distribution summary box
    dist_data = [
        ["Penyaluran", "Nominal"],
        ["Kantor Misi", _fmt_rupiah(sum_misi)],
        ["Kas Jemaat", _fmt_rupiah(sum_jemaat)],
        ["TOTAL", _fmt_rupiah(sum_misi + sum_jemaat)],
    ]
    dist_table = Table(dist_data, colWidths=[6 * cm, 6 * cm])
    dist_table.setStyle(TableStyle([
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
    ]))
    elements.append(dist_table)
    elements.append(Spacer(1, 16))

    # === FOOTER (pejabat) ===
    elements.append(_build_footer_table(
        pendeta=tenant.nama_pendeta or "",
        ketua=tenant.nama_ketua_keuangan or "",
        bendahara=tenant.nama_bendahara or "",
    ))
    # Tahap 21: optional footer text dari tenant
    if tenant.footer_text:
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            f"<i>{tenant.footer_text}</i>",
            ParagraphStyle("footer_text", fontSize=8, alignment=TA_LEFT, textColor=COLOR_GRAY),
        ))
    elements.append(Spacer(1, 6))

    # Generator watermark
    elements.append(Paragraph(
        f"<font size=7 color=gray>Dokumen ini dihasilkan otomatis oleh FLIPUS v1.1 pada "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. ID: {id_rekap_mingguan}</font>",
        ParagraphStyle("footer", alignment=TA_RIGHT, fontSize=7, textColor=COLOR_GRAY),
    ))

    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        return pdf_bytes

    return pdf_bytes

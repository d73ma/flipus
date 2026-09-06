"""Terbilang Rupiah Indonesia (max ratusan trilian)."""

SATUAN = ["", "Satu", "Dua", "Tiga", "Empat", "Lima", "Enam", "Tujuh",
          "Delapan", "Sembilan", "Sepuluh", "Sebelas"]

def _below_thousand(n: int) -> str:
    if n == 0:
        return ""
    if n < 12:
        return SATUAN[n]
    if n < 20:
        return SATUAN[n - 10] + " Belas"
    if n < 100:
        return SATUAN[n // 10] + " Puluh " + _below_thousand(n % 10)
    # 100..199 → "Seratus" (bukan "Satu Ratus") per ejaan Indonesia.
    if n < 200:
        return "Seratus " + _below_thousand(n - 100)
    ratusan = SATUAN[n // 100] + " Ratus"
    return ratusan + " " + _below_thousand(n % 100)

def _chunk(n: int, sisa: str = "") -> str:
    if n == 0:
        return sisa.strip() or "Nol"
    if n < 1000:
        # FIX 2026-08-23: Urutan Indonesian — SISA (ribu/juta) DULU, baru n.
        # Sebelum: "_below_thousand(n) + sisa" → "Lima Ratus Delapan Ratus Ribu" (SALAH)
        # Sesudah: "sisa + _below_thousand(n)" → "Delapan Ratus Ribu Lima Ratus" (BENAR)
        return (sisa + " " + _below_thousand(n)).strip()
    ribu = _below_thousand(n // 1000) + " Ribu"
    if n < 2000:
        ribu = "Seribu"
    return _chunk(n % 1000, ribu + " " + sisa).strip()

def _id_short(n: int) -> str:
    return _chunk(n).strip()

def _format_besar(n: int) -> str:
    if n == 0:
        return ""
    if n < 1_000:
        return _id_short(n)
    if n < 1_000_000:
        # Special case 1000..1999 → "Seribu X" (bukan "Satu Ribu X") per ejaan.
        if 1000 <= n < 2000:
            sisa = _id_short(n - 1000)
            if sisa == "Nol":
                return "Seribu"
            return "Seribu " + sisa
        ribu = _id_short(n // 1_000) + " Ribu"
        sisa = _id_short(n % 1_000)
        if sisa == "Nol":
            return ribu  # 2000 → "Dua Ribu", 500.000 → "Lima Ratus Ribu"
        return ribu + " " + sisa
    if n < 1_000_000_000:
        juta = _id_short(n // 1_000_000) + " Juta"
        sisa = _id_short(n % 1_000_000)
        if sisa == "Nol":
            return juta  # 1.000.000 → "Satu Juta"
        return juta + " " + sisa
    if n < 1_000_000_000_000:
        miliar = _id_short(n // 1_000_000_000) + " Miliar"
        sisa = _id_short(n % 1_000_000_000)
        if sisa == "Nol":
            return miliar
        return miliar + " " + sisa
    triliun = _id_short(n // 1_000_000_000_000) + " Triliun"
    sisa = _id_short(n % 1_000_000_000_000)
    if sisa == "Nol":
        return triliun
    return triliun + " " + sisa

def terbilang(angka: int) -> str:
    if angka == 0:
        return "Nol Rupiah"
    return _format_besar(abs(angka)).replace("  ", " ").strip() + " Rupiah"


# Alias — legacy callers from earlier Tahap used various names
bilang = terbilang
rupiah_to_words = terbilang  # S4-D.R1: unify naming across kuitansi.py / whatsapp.py / pdf_generator.py

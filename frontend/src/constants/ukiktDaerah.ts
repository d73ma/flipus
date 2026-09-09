/**
 * FLIPUS — daftar Daerah Misi/Konferens untuk Uni GMAHK UKIKT (v1).
 *
 * Sumber kebenaran untuk dropdown "Daerah Misi/Konferens" di semua halaman:
 * - /register/pendeta
 * - /register/auditor
 * - profil jemaat (admin uni)
 * - filter daftar auditor (admin uni)
 * - (backend auto-ensure master data yang sama)
 *
 * Urutan persis seperti permintaan Jerry (2026-09-09):
 * grup "Daerah Konferens" (3) → grup "Daerah Misi" (10). Total 13.
 */
export const UKIKT_KONFERENS: string[] = [
  'Daerah Konferens Minahasa',
  'Daerah Konferens Manado & Maluku Utara',
  'Daerah Konferens Sulselbartra',
];

export const UKIKT_MISI: string[] = [
  'Daerah Misi Minut & Bitung',
  'Daerah Misi Bolmong-Gorontalo',
  'Daerah Misi Nusa Utara',
  'Daerah Misi Sulawesi Tengah',
  'Daerah Misi Luwu & Tana Toraja',
  'Daerah Misi Papua',
  'Daerah Misi Papua Tengah',
  'Daerah Misi Papua Barat',
  'Daerah Misi Papua Barat Daya',
  'Daerah Misi Maluku',
];

/** Gabungan 13 label (urutan: konferens dulu, baru misi). */
export const UKIKT_DAERAH: string[] = [...UKIKT_KONFERENS, ...UKIKT_MISI];
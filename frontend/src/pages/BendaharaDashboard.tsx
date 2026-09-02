import { useState, useEffect, Fragment } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/api';
import { CountUp } from '../components/Chart';
import { SabatFilterPanel } from '../components/SabatFilterPanel';
import type { SabatFilter } from '../components/SabatFilterPanel';
import { YtdBarChart } from '../components/YtdBarChart';

// ===== T94 Section 8: WA staging types =====
interface WaStagingItem {
  id: number;
  staging_id: number | null;
  temp_nomor: string | null;
  tanggal_sabat: string;
  perpuluhan_x: number;
  pt: number;
  khusus: number;
  total: number;
  wa_sender: string | null;
  wa_message_id: string | null;
  created_at: string | null;
}

interface WaStagingResponse {
  count: number;
  last_web_upload_at: string | null;
  items: WaStagingItem[];
}

// ===== Inline table styles (Tailwind fallback — bullet-proof) =====
const thStyle: React.CSSProperties = {
  padding: '10px 12px',
  textAlign: 'left',
  fontWeight: 600,
  fontSize: 11,
  letterSpacing: '0.04em',
  textTransform: 'uppercase',
  whiteSpace: 'nowrap',
};
const tdStyle: React.CSSProperties = {
  padding: '10px 12px',
  fontSize: 12,
  verticalAlign: 'middle',
};

// ===== Types =====
interface SabatInfoOut {
  sabat_ke: number;
  tanggal_sabat: string;
  hari: string;
  tahun: number;
  bulan_romawi: string;
  bulan_nama: string;
  next_urutan_hint: number;
}

interface SabatIniItem {
  no: number;
  id_kuitansi: number;
  nomor_kuitansi: string;
  nama_pemberi: string | null;
  tanggal_sabat: string;
  perpuluhan_x_angka: number;
  pt_angka: number;
  khusus_angka: number;
  total: number;
  porsi_misi_x: number;
  porsi_misi_pt: number;
  porsi_misi_kh: number;
  porsi_uni_x: number;
  porsi_uni_pt: number;
  porsi_uni_kh: number;
  porsi_jemaat_x: number;
  porsi_jemaat_pt: number;
  porsi_jemaat_kh: number;
  id_rekap_mingguan: string;
}

interface SabatIniOut {
  scope: string;
  sabat_ke: number;
  tanggal_sabat: string;
  hari: string;
  bulan_nama: string;
  tahun: number;
  items: SabatIniItem[];
  grand_total_x: number;
  grand_total_pt: number;
  grand_total_khusus: number;
  grand_total_semua: number;
  grand_total_porsi_misi_x: number;
  grand_total_porsi_misi_pt: number;
  grand_total_porsi_misi_kh: number;
  grand_total_porsi_uni_x: number;
  grand_total_porsi_uni_pt: number;
  grand_total_porsi_uni_kh: number;
  grand_total_porsi_jemaat: number;
  grand_total_porsi_jemaat_x: number;
  grand_total_porsi_jemaat_pt: number;
  grand_total_porsi_jemaat_kh: number;
  grand_total_huruf: string;
}

interface TenantProfile {
  id: number;
  nama_jemaat_lokal: string;
  nama_uni: string;
  nama_kantor_misi: string;
  misi_konferens_id?: number;
}

interface PersentaseConfig {
  id: number;
  scope: 'MISI' | 'UNI';
  ref_id: number;
  pct_x_jemaat: number;
  pct_pt_jemaat: number;
  pct_khusus_jemaat: number;
  pct_x_uni: number;
  pct_pt_uni: number;
  pct_khusus_uni: number;
}

interface LaporanKeuanganResult {
  sabat_from: number;
  sabat_to: number;
  tahun: number;
  jumlah_kuitansi: number;
  grand_total_x: number;
  grand_total_pt: number;
  grand_total_khusus: number;
  grand_total_porsi_misi: number;
  grand_total_porsi_jemaat: number;
  grand_total_huruf: string;
  pdf_filename: string;
  pdf_size_bytes: number;
  pdf_url: string;
  blast_results: { role: string; status: string; [k: string]: any }[];
}

const BendaharaDashboard = () => {
  const [sabatInfo, setSabatInfo] = useState<SabatInfoOut | null>(null);
  const [sabatIni, setSabatIni] = useState<SabatIniOut | null>(null);
  const [tenantProfile, setTenantProfile] = useState<TenantProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<SabatFilter>({ mode: 'sabat_ini' });

  // Blast modal
  const [blastModal, setBlastModal] = useState<'pendeta' | 'ketua' | null>(null);
  const [blastLoading, setBlastLoading] = useState(false);

  // Laporan Keuangan modal
  const [laporanModal, setLaporanModal] = useState(false);
  const [laporanFrom, setLaporanFrom] = useState(1);
  const [laporanTo, setLaporanTo] = useState(34);
  const [laporanResult, setLaporanResult] = useState<LaporanKeuanganResult | null>(null);
  const [laporanLoading, setLaporanLoading] = useState(false);
  const [laporanError, setLaporanError] = useState('');

  // T39: read-only MISI percentage (set by Auditor Misi)
  const [pctMisi, setPctMisi] = useState<PersentaseConfig | null>(null);

  // T94 Section 8: WA staging items (dari Bendahara chat via WhatsApp)
  const [stagingItems, setStagingItems] = useState<WaStagingItem[]>([]);
  const [stagingLoading, setStagingLoading] = useState(false);
  const [lastWebUploadAt, setLastWebUploadAt] = useState<string | null>(null);
  const [waCollapsed, setWaCollapsed] = useState(false);
  const [selectedStagingIds, setSelectedStagingIds] = useState<Set<number>>(new Set());
  const [stagingActionLoading, setStagingActionLoading] = useState(false);
  const [stagingError, setStagingError] = useState<string | null>(null);

  const fetchSabatInfo = async () => {
    try {
      const r = await api.get<SabatInfoOut>('/v1/reports/sabat-info');
      setSabatInfo(r.data);
      setLaporanFrom(Math.max(1, r.data.sabat_ke - 3));
      setLaporanTo(r.data.sabat_ke);
    } catch (e) {}
  };

  const fetchTenantProfile = async () => {
    try {
      const r = await api.get('/v1/tenants/me');
      setTenantProfile(r.data);
    } catch (e) {}
  };

  const fetchSabatIni = async () => {
    setLoading(true);
    try {
      const r = await api.get<SabatIniOut>('/v1/agregat/sabat-ini');
      setSabatIni(r.data);
    } catch (err: any) {
      console.warn('Gagal load sabat-ini:', err.response?.data?.detail);
      setSabatIni(null);
    } finally {
      setLoading(false);
    }
  };

  // T39: fetch MISI persentase (read-only) yang ditetapkan Auditor Misi.
  const fetchPersentaseMisi = async () => {
    if (!tenantProfile?.misi_konferens_id) return;
    try {
      const r = await api.get<PersentaseConfig>('/v1/master/persentase', {
        params: { scope: 'MISI', ref_id: tenantProfile.misi_konferens_id },
      });
      setPctMisi(r.data);
    } catch (e) {
      setPctMisi(null);
    }
  };

  useEffect(() => {
    fetchSabatInfo();
    fetchTenantProfile();
    fetchSabatIni();
  }, []);

  // T39: setelah tenantProfile ada (ada misi_konferens_id), fetch persentase MISI
  useEffect(() => {
    if (tenantProfile?.misi_konferens_id) fetchPersentaseMisi();
  }, [tenantProfile?.misi_konferens_id]);

  // T94 Section 8: fetch WA staging items on mount
  const fetchStaging = async () => {
    setStagingLoading(true);
    setStagingError(null);
    try {
      const r = await api.get<WaStagingResponse>('/v1/kuitansi/staging');
      setStagingItems(r.data.items);
      setLastWebUploadAt(r.data.last_web_upload_at);
      // Auto-expand kalau ada items, auto-collapse kalau kosong dan first load
      setWaCollapsed(r.data.items.length === 0);
    } catch (err: any) {
      setStagingError(err.response?.data?.detail || err.message || 'Gagal load staging');
      setStagingItems([]);
    } finally {
      setStagingLoading(false);
    }
  };

  useEffect(() => {
    fetchStaging();
  }, []);

  // Hitung daysSinceLastWebUpload untuk warning card
  const daysSinceLastWeb = lastWebUploadAt
    ? Math.floor((Date.now() - new Date(lastWebUploadAt).getTime()) / (1000 * 60 * 60 * 24))
    : null;

  // T94 Section 8: delete satu staging item
  const handleDeleteStagingItem = async (itemId: number) => {
    if (!window.confirm('Hapus staging item ini? Data asli tersimpan di WA (siap di-input ulang).')) return;
    setStagingActionLoading(true);
    setStagingError(null);
    try {
      await api.delete(`/v1/kuitansi/staging/${itemId}`);
      setSelectedStagingIds((prev) => {
        const next = new Set(prev);
        next.delete(itemId);
        return next;
      });
      await fetchStaging();
    } catch (err: any) {
      setStagingError(err.response?.data?.detail || err.message || 'Gagal hapus');
    } finally {
      setStagingActionLoading(false);
    }
  };

  // T94 Section 8: finalize selected (atau all) ke kuitansi final
  const handleFinalizeStaging = async (ids: number[]) => {
    if (ids.length === 0) {
      window.alert('Pilih minimal 1 item untuk disimpan.');
      return;
    }
    if (!window.confirm(`Simpan ${ids.length} item ke Kuitansi Final? Nomor kuitansi akan di-generate otomatis (counter per bulan).`)) {
      return;
    }
    setStagingActionLoading(true);
    setStagingError(null);
    try {
      const r = await api.post('/v1/kuitansi/finalize-staging', {
        staging_ids: ids,
        tanggal_sabat: sabatInfo?.tanggal_sabat,  // T110: override ke sabat berjalan
      });
      const okMsg = `✅ ${r.data.finalized_count} kuitansi berhasil difinalisasi:\n` +
        r.data.items.map((it: any) => `  • ${it.nomor_kuitansi} (${it.tanggal_sabat})`).join('\n');
      window.alert(okMsg);
      setSelectedStagingIds(new Set());
      await fetchStaging();
      // T110 (2026-08-26): override tanggal_sabat ke sabat berjalan + refresh tabel sabat_ini
      await fetchSabatIni();
    } catch (err: any) {
      setStagingError(err.response?.data?.detail || err.message || 'Gagal finalize');
    } finally {
      setStagingActionLoading(false);
    }
  };

  const toggleStagingSelected = (id: number) => {
    setSelectedStagingIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // ===== Blast handlers =====
  const handleBlast = async (target: 'pendeta' | 'ketua') => {
    if (!sabatInfo || !sabatIni) return;
    setBlastLoading(true);
    try {
      // T36: blast from /v1/reports/blast-weekly (existing endpoint)
      // Untuk ketua dengan sanitize nama, kita pakai endpoint blast-weekly juga
      // karena generate_mingguan_pdf sudah aggregate only (tanpa nama pemberi)
      // v1.5-C: idempotency_key — UUID per click, cegah double-blast kalau user
      // pencet tombol dua kali sebelum request pertama selesai.
      const idemKey = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      await api.post('/v1/reports/blast-weekly', {
        id_rekap_mingguan: sabatIni.items[0]?.id_rekap_mingguan || `RK-${sabatInfo.tanggal_sabat.replace(/-/g, '')}`,
        target_role: target,  // hint backend untuk lookup Ketua vs Pendeta
        idempotency_key: idemKey,
      });
      alert(`✅ WA Blast berhasil dikirim ke ${target === 'pendeta' ? 'Pendeta' : 'Ketua'}!`);
      setBlastModal(null);
    } catch (err: any) {
      // Tampilkan detail error dari backend (bukan generic fallback).
      // Backend sekarang throw 502 dengan .detail berisi reason Fonnte + info target.
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.reason ||
        err.message ||
        `Gagal kirim WA ke ${target}`;
      alert(`❌ Gagal kirim WA ke ${target === 'pendeta' ? 'Pendeta' : 'Ketua'}\n\n${detail}`);
    } finally {
      setBlastLoading(false);
    }
  };

  // ===== Laporan Keuangan handler =====
  const handleGenerateLaporan = async () => {
    setLaporanLoading(true);
    setLaporanError('');
    try {
      const r = await api.post<LaporanKeuanganResult>('/v1/reports/keuangan', {
        sabat_from: Math.min(laporanFrom, laporanTo),
        sabat_to: Math.max(laporanFrom, laporanTo),
        tahun: sabatInfo?.tahun,
        blast_targets: ['PENDETA', 'KETUA_KEUANGAN'],
        sanitize_nama_for_ketua: true,
      });
      setLaporanResult(r.data);
    } catch (err: any) {
      setLaporanError(err.response?.data?.detail || 'Gagal generate laporan');
    } finally {
      setLaporanLoading(false);
    }
  };

  const title = tenantProfile?.nama_jemaat_lokal
    ? `Bendahara ${tenantProfile.nama_jemaat_lokal}`
    : 'Dashboard Bendahara';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* ===== Header ===== */}
      <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, color: '#1B4332', margin: 0, fontWeight: 700 }}>{title}</h2>
          {sabatInfo && (
            <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
              {sabatInfo.hari}, {new Date(sabatInfo.tanggal_sabat).getDate()} {sabatInfo.bulan_nama} {sabatInfo.tahun}{' '}
              – Sabat ke {sabatInfo.sabat_ke}
            </p>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link
            to="/bendahara/quick"
            style={{
              padding: '10px 18px',
              background: '#0F4C3A',
              color: '#C9A961',
              border: '1px solid #C9A961',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 600,
              textDecoration: 'none',
              boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
            }}
            title="v2.0 PWA — install-able ke home screen"
          >
            ⚡ Quick Input (PWA)
          </Link>
          <Link
            to="/bendahara/ocr"
            style={{
              padding: '10px 18px',
              background: '#1B4332',
              color: 'white',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 500,
              textDecoration: 'none',
              boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
            }}
          >
            📸 Upload Foto Amplop
          </Link>
        </div>
      </div>

      {/* T39: Panel read-only persentase MISI (ditetapkan Auditor Misi) */}
      {pctMisi && (
        <div style={{
          background: 'linear-gradient(135deg, #1B4332 0%, #0d2418 100%)',
          color: 'white',
          borderRadius: 16,
          padding: 20,
          border: '1px solid rgba(184, 134, 11, 0.3)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 14, margin: 0, fontWeight: 600, opacity: 0.95 }}>
              📊 Persentase Porsi Misi (ditetapkan Auditor Misi)
            </h3>
            <span style={{ fontSize: 10, opacity: 0.6, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Read-only</span>
          </div>
          <p style={{ fontSize: 11, opacity: 0.65, margin: '0 0 12px 0' }}>
            Nilai ini ditetapkan oleh Auditor Misi dan otomatis diterapkan ke kalkulator PORSI MISI di tabel di bawah.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 10, padding: 12 }}>
              <p style={{ fontSize: 10, opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                Perpuluhan ke Misi
              </p>
              <p style={{ fontSize: 22, fontWeight: 700, color: '#B8860B', margin: 0 }}>
                {/* pct_x_jemaat = Jemaat retention → 0% ret = 100% ke Misi (inverse) */}
                {Math.round((1 - pctMisi.pct_x_jemaat) * 100)}%
              </p>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 10, padding: 12 }}>
              <p style={{ fontSize: 10, opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                Persembahan ke Misi
              </p>
              <p style={{ fontSize: 22, fontWeight: 700, color: '#B8860B', margin: 0 }}>
                {/* pct_pt_jemaat = Jemaat retention → inverse untuk display */}
                {Math.round((1 - pctMisi.pct_pt_jemaat) * 100)}%
              </p>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 10, padding: 12 }}>
              <p style={{ fontSize: 10, opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                Persembahan Khusus
              </p>
              <p style={{ fontSize: 22, fontWeight: 700, color: '#B8860B', margin: 0 }}>
                {/* pct_khusus_jemaat = fraction to MISI (semantic inverse dari x/pt) — display langsung */}
                {Math.round(pctMisi.pct_khusus_jemaat * 100)}%
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ===== T94 Section 8: Item Staging dari WhatsApp ===== */}
      <div style={{
        background: stagingItems.length > 0
          ? 'linear-gradient(135deg, #fef9e7 0%, #fffbf0 100%)'
          : 'white',
        borderRadius: 16,
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        border: stagingItems.length > 0 ? '1px solid #f0d97a' : '1px solid #f0f0eb',
        overflow: 'hidden',
      }}>
        {/* Header (clickable untuk collapse) */}
        <div
          onClick={() => setWaCollapsed((c) => !c)}
          style={{
            padding: '14px 24px',
            background: stagingItems.length > 0 ? '#B8860B' : '#1B4332',
            color: 'white',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            userSelect: 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, color: stagingItems.length > 0 ? '#fffbe6' : '#B8860B', margin: 0, fontWeight: 700 }}>
              📥 Dari WA — Item Staging
            </h3>
            {stagingItems.length > 0 && (
              <span style={{
                background: '#fee2e2',
                color: '#991b1b',
                padding: '3px 10px',
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: '0.04em',
              }}>
                {stagingItems.length} ITEM PERLU DIREVIEW
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 11, opacity: 0.85 }}>
              {waCollapsed ? 'Buka' : 'Tutup'}
            </span>
            <span style={{ fontSize: 18, transform: waCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
              ▼
            </span>
          </div>
        </div>

        {!waCollapsed && (
          <div>
            {/* Warning card: kalau 1 minggu tidak ada upload via web/ocr */}
            {daysSinceLastWeb !== null && daysSinceLastWeb >= 7 && stagingItems.length > 0 && (
              <div style={{
                margin: '12px 24px 0 24px',
                background: '#fffbeb',
                border: '1px solid #fcd34d',
                borderLeft: '4px solid #d97706',
                padding: 12,
                borderRadius: 10,
                fontSize: 12,
                color: '#78350f',
              }}>
                <strong>⚠️ Sudah {daysSinceLastWeb} hari tidak ada upload via web/OCR.</strong>
                <span style={{ display: 'block', marginTop: 4 }}>
                  Untuk audit trail yang lengkap, lanjutkan input kuitansi via OCR juga
                  (foto amplop fisik tetap wajib di file terpisah).
                </span>
              </div>
            )}
            {daysSinceLastWeb === null && stagingItems.length > 0 && (
              <div style={{
                margin: '12px 24px 0 24px',
                background: '#fef2f2',
                border: '1px solid #fecaca',
                borderLeft: '4px solid #dc2626',
                padding: 12,
                borderRadius: 10,
                fontSize: 12,
                color: '#7f1d1d',
              }}>
                <strong>⚠️ Belum pernah upload via web/OCR.</strong>
                <span style={{ display: 'block', marginTop: 4 }}>
                  Audit trail foto amplop masih kosong. Pertimbangkan upload via OCR juga.
                </span>
              </div>
            )}

            {stagingError && (
              <div style={{
                margin: '12px 24px 0 24px',
                background: '#fef2f2',
                border: '1px solid #fecaca',
                color: '#b91c1c',
                padding: 12,
                borderRadius: 10,
                fontSize: 12,
              }}>
                {stagingError}
              </div>
            )}

            {stagingLoading ? (
              <div style={{ padding: 32, textAlign: 'center', color: '#888', fontSize: 13 }}>
                Memuat staging items...
              </div>
            ) : stagingItems.length === 0 ? (
              <div style={{ padding: 32, textAlign: 'center', color: '#888' }}>
                <p style={{ margin: 0, fontSize: 13 }}>📭 Belum ada item dari WhatsApp.</p>
                <p style={{ margin: '8px 0 0 0', fontSize: 11, color: '#9ca3af' }}>
                  Bendahara bisa chat ke nomor Fonnte FLIPUS dengan format: "X 100rb, PT 50rb, KH 25rb"
                </p>
              </div>
            ) : (
              <>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, marginTop: 12 }}>
                    <thead>
                      <tr style={{ background: '#f5f5ee', color: '#374151' }}>
                        <th style={{ ...thStyle, width: 36 }}>
                          <input
                            type="checkbox"
                            checked={selectedStagingIds.size === stagingItems.length && stagingItems.length > 0}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedStagingIds(new Set(stagingItems.map((it) => it.id)));
                              } else {
                                setSelectedStagingIds(new Set());
                              }
                            }}
                          />
                        </th>
                        <th style={thStyle}>No. Staging</th>
                        <th style={thStyle}>Nama Pemberi</th>
                        <th style={thStyle}>Tanggal Sabat</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>X</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>PT</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>KH</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>Total</th>
                        <th style={thStyle}>WA Sender</th>
                        <th style={thStyle}>Waktu</th>
                        <th style={thStyle}>Aksi</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stagingItems.map((item, idx) => {
                        const mainBg = idx % 2 === 0 ? '#fffdf5' : 'white';
                        return (
                          <tr key={item.id} style={{ background: mainBg, borderBottom: '1px solid #f0e8c4' }}>
                            <td style={tdStyle}>
                              <input
                                type="checkbox"
                                checked={selectedStagingIds.has(item.id)}
                                onChange={() => toggleStagingSelected(item.id)}
                                disabled={stagingActionLoading}
                              />
                            </td>
                            <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11, color: '#92400e' }}>
                              {item.temp_nomor || `STG-${item.staging_id || item.id}`}
                            </td>
                            <td style={{ ...tdStyle, fontWeight: 500, color: '#1B4332' }}>
                              {item.nama_pemberi || 'Umat WA'}
                            </td>
                            <td style={tdStyle}>{item.tanggal_sabat}</td>
                            <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {item.perpuluhan_x.toLocaleString()}</td>
                            <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {item.pt.toLocaleString()}</td>
                            <td style={{ ...tdStyle, textAlign: 'right', color: item.khusus > 0 ? '#374151' : '#9ca3af' }}>
                              {item.khusus > 0 ? `Rp ${item.khusus.toLocaleString()}` : '—'}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#92400e' }}>
                              Rp {item.total.toLocaleString()}
                            </td>
                            <td style={{ ...tdStyle, fontSize: 11, color: '#6b7280' }}>
                              {item.wa_sender || '—'}
                            </td>
                            <td style={{ ...tdStyle, fontSize: 11, color: '#6b7280' }}>
                              {item.created_at
                                ? new Date(item.created_at).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' })
                                : '—'}
                            </td>
                            <td style={tdStyle}>
                              <button
                                onClick={() => handleDeleteStagingItem(item.id)}
                                disabled={stagingActionLoading}
                                style={{
                                  padding: '4px 10px',
                                  background: '#fef2f2',
                                  border: '1px solid #fecaca',
                                  color: '#b91c1c',
                                  borderRadius: 6,
                                  fontSize: 11,
                                  fontWeight: 500,
                                  cursor: stagingActionLoading ? 'wait' : 'pointer',
                                  opacity: stagingActionLoading ? 0.5 : 1,
                                }}
                                title="Hapus staging item"
                              >
                                Hapus
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Footer: aksi global */}
                <div style={{
                  padding: '14px 24px',
                  borderTop: '1px solid #f0d97a',
                  background: '#fef9e7',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  flexWrap: 'wrap',
                }}>
                  <p style={{ fontSize: 12, color: '#6b7280', margin: 0, flex: 1, minWidth: 200 }}>
                    Setelah di-finalize, staging items akan mendapat nomor kuitansi otomatis
                    (counter per bulan per jemaat, sesuai T66).
                  </p>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button
                      onClick={() => handleFinalizeStaging(Array.from(selectedStagingIds))}
                      disabled={stagingActionLoading || selectedStagingIds.size === 0}
                      style={{
                        padding: '10px 16px',
                        background: selectedStagingIds.size > 0 ? '#B8860B' : '#d1d5db',
                        color: 'white',
                        borderRadius: 10,
                        fontSize: 13,
                        fontWeight: 600,
                        border: 'none',
                        cursor: (stagingActionLoading || selectedStagingIds.size === 0) ? 'not-allowed' : 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      💾 Simpan {selectedStagingIds.size > 0 ? `${selectedStagingIds.size} Terpilih` : 'yang Dipilih'}
                    </button>
                    <button
                      onClick={() => handleFinalizeStaging(stagingItems.map((it) => it.id))}
                      disabled={stagingActionLoading}
                      style={{
                        padding: '10px 16px',
                        background: '#1B4332',
                        color: 'white',
                        borderRadius: 10,
                        fontSize: 13,
                        fontWeight: 600,
                        border: 'none',
                        cursor: stagingActionLoading ? 'wait' : 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      💾 Simpan Semua ({stagingItems.length}) ke Kuitansi Final
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* ===== Filter ===== */}
      <SabatFilterPanel
        onApply={setFilter}
        defaultSabat={sabatInfo?.sabat_ke || 1}
        sabatKeSekarang={sabatInfo?.sabat_ke || 34}
      />

      {/* ===== Tabel Persembahan Sabat Ini ===== */}
      <div style={{ background: 'white', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.05)', border: '1px solid #f0f0eb', overflow: 'hidden' }}>
        <div style={{ padding: '14px 24px', borderBottom: '1px solid #f0f0eb', background: '#1B4332', color: 'white' }}>
          <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, color: '#B8860B', margin: 0, fontWeight: 700 }}>
            Tabel Persembahan Sabat Ini
          </h3>
          {sabatInfo && (
            <p style={{ fontSize: 12, opacity: 0.85, marginTop: 4 }}>
              Tanggal: {sabatInfo.tanggal_sabat} (Sabat ke-{sabatInfo.sabat_ke})
            </p>
          )}
        </div>

        {loading ? (
          <div style={{ padding: 48, textAlign: 'center', color: '#888' }}>Memuat data...</div>
        ) : sabatIni && sabatIni.items.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#1B4332', color: 'white' }}>
                  <th style={thStyle}>No</th>
                  <th style={thStyle}>No. Kuitansi</th>
                  <th style={thStyle}>Nama Umat</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>X</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>PT</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Khusus</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {sabatIni.items.map((item, idx) => {
                  const mainBg = idx % 2 === 0 ? '#fafaf5' : 'white';
                  return (
                  <Fragment key={item.id_kuitansi}>
                  <tr style={{ background: mainBg, borderBottom: '1px solid #e5e7eb' }}>
                    <td style={{ ...tdStyle, color: '#6b7280' }}>{item.no}</td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>{item.nomor_kuitansi}</td>
                    <td style={tdStyle}>{item.nama_pemberi || '—'}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 500 }}>Rp {item.perpuluhan_x_angka.toLocaleString()}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 500 }}>Rp {item.pt_angka.toLocaleString()}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', color: '#6b7280' }}>
                      {item.khusus_angka > 0 ? `Rp ${item.khusus_angka.toLocaleString()}` : '—'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#1B4332' }}>
                      Rp {item.total.toLocaleString()}
                    </td>
                  </tr>
                  <tr style={{ background: '#f0f9ff', borderBottom: '1px dotted #bae6fd' }}>
                    <td colSpan={7} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#0369a1' }}>
                      <strong>🏠 Porsi Jemaat</strong> (X/PT/KH):&nbsp;
                      <span style={{ fontWeight: 600 }}>X</span> {item.porsi_jemaat_x.toLocaleString()}
                      {' · '}<span style={{ fontWeight: 600 }}>PT</span> {item.porsi_jemaat_pt.toLocaleString()}
                      {item.khusus_angka > 0 && (
                        <>
                          {' · '}<span style={{ fontWeight: 600 }}>KH</span> {item.porsi_jemaat_kh.toLocaleString()}
                        </>
                      )}
                    </td>
                  </tr>
                  <tr style={{ background: '#f0fdf4', borderBottom: '1px dotted #d1fae5' }}>
                    <td colSpan={7} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#047857' }}>
                      <strong>↗ Porsi Misi</strong> (X/PT/KH):&nbsp;
                      <span style={{ fontWeight: 600 }}>X</span> {item.porsi_misi_x.toLocaleString()}
                      {' · '}<span style={{ fontWeight: 600 }}>PT</span> {item.porsi_misi_pt.toLocaleString()}
                      {item.khusus_angka > 0 && (
                        <>
                          {' · '}<span style={{ fontWeight: 600 }}>KH</span> {item.porsi_misi_kh.toLocaleString()}
                        </>
                      )}
                    </td>
                  </tr>
                  <tr style={{ background: '#fffbeb', borderBottom: '2px solid #1B4332' }}>
                    <td colSpan={7} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#b45309' }}>
                      <strong>↗ Porsi Uni</strong> (X/PT/KH):&nbsp;
                      <span style={{ fontWeight: 600 }}>X</span> {item.porsi_uni_x.toLocaleString()}
                      {' · '}<span style={{ fontWeight: 600 }}>PT</span> {item.porsi_uni_pt.toLocaleString()}
                      {item.khusus_angka > 0 && (
                        <>
                          {' · '}<span style={{ fontWeight: 600 }}>KH</span> {item.porsi_uni_kh.toLocaleString()}
                        </>
                      )}
                    </td>
                  </tr>
                  </Fragment>
                  );
                })}
              </tbody>
              <tfoot>
                <tr style={{ background: '#FAF9F5', borderTop: '2px solid #1B4332', fontWeight: 700, color: '#1B4332' }}>
                  <td colSpan={3} style={tdStyle}>Total Keseluruhan</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {sabatIni.grand_total_x.toLocaleString()}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {sabatIni.grand_total_pt.toLocaleString()}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {sabatIni.grand_total_khusus.toLocaleString()}</td>
                  <td style={{ ...tdStyle, textAlign: 'right', color: '#B8860B' }}>
                    Rp {sabatIni.grand_total_semua.toLocaleString()}
                  </td>
                </tr>
                <tr style={{ background: '#f0f9ff' }}>
                  <td colSpan={7} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#0369a1' }}>
                    <strong>Total Porsi Jemaat</strong> (X/PT/KH):&nbsp;
                    <span style={{ fontWeight: 600 }}>X</span> {sabatIni.grand_total_porsi_jemaat_x.toLocaleString()}
                    {' · '}<span style={{ fontWeight: 600 }}>PT</span> {sabatIni.grand_total_porsi_jemaat_pt.toLocaleString()}
                    {sabatIni.grand_total_khusus > 0 && (
                      <>
                        {' · '}<span style={{ fontWeight: 600 }}>KH</span> {sabatIni.grand_total_porsi_jemaat_kh.toLocaleString()}
                      </>
                    )}
                  </td>
                </tr>
                <tr style={{ background: '#f0fdf4' }}>
                  <td colSpan={7} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#047857' }}>
                    <strong>Total Porsi Misi</strong> (X/PT/KH):&nbsp;
                    <span style={{ fontWeight: 600 }}>X</span> {sabatIni.grand_total_porsi_misi_x.toLocaleString()}
                    {' · '}<span style={{ fontWeight: 600 }}>PT</span> {sabatIni.grand_total_porsi_misi_pt.toLocaleString()}
                    {sabatIni.grand_total_khusus > 0 && (
                      <>
                        {' · '}<span style={{ fontWeight: 600 }}>KH</span> {sabatIni.grand_total_porsi_misi_kh.toLocaleString()}
                      </>
                    )}
                  </td>
                </tr>
                <tr style={{ background: '#fffbeb', borderTop: '2px solid #1B4332' }}>
                  <td colSpan={7} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#b45309' }}>
                    <strong>Total Porsi Uni</strong> (X/PT/KH):&nbsp;
                    <span style={{ fontWeight: 600 }}>X</span> {sabatIni.grand_total_porsi_uni_x.toLocaleString()}
                    {' · '}<span style={{ fontWeight: 600 }}>PT</span> {sabatIni.grand_total_porsi_uni_pt.toLocaleString()}
                    {sabatIni.grand_total_khusus > 0 && (
                      <>
                        {' · '}<span style={{ fontWeight: 600 }}>KH</span> {sabatIni.grand_total_porsi_uni_kh.toLocaleString()}
                      </>
                    )}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <div style={{ padding: 48, textAlign: 'center', color: '#888' }}>
            {sabatInfo
              ? `Belum ada kuitansi untuk Sabat ke-${sabatInfo.sabat_ke} (${sabatInfo.tanggal_sabat}).`
              : 'Memuat info sabat...'}
          </div>
        )}

        {sabatIni && sabatIni.items.length > 0 && (
          <div style={{ padding: '12px 24px', background: '#FAF9F5', fontSize: 12, color: '#374151', borderTop: '1px solid #e5e7eb' }}>
            <span style={{ fontWeight: 600 }}>Terbilang:</span> {sabatIni.grand_total_huruf}
          </div>
        )}
      </div>

      {/* ===== Blast buttons ===== */}
      {sabatIni && sabatIni.items.length > 0 && (
        <div style={{ background: 'white', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.05)', border: '1px solid #f0f0eb', padding: 20 }}>
          <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, color: '#1B4332', margin: '0 0 12px 0', fontWeight: 700 }}>📲 Kirim Laporan via WhatsApp</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 10 }}>
            <button
              onClick={() => setBlastModal('pendeta')}
              style={{
                padding: '12px 18px',
                background: '#B8860B',
                color: 'white',
                borderRadius: 10,
                fontSize: 13,
                fontWeight: 500,
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
              }}
            >
              💬 Blast ke Pendeta (data lengkap)
            </button>
            <button
              onClick={() => setBlastModal('ketua')}
              style={{
                padding: '12px 18px',
                background: '#1B4332',
                color: 'white',
                borderRadius: 10,
                fontSize: 13,
                fontWeight: 500,
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
              }}
            >
              🛡️ Blast ke Ketua (tanpa nama umat)
            </button>
          </div>
          <p style={{ fontSize: 11, color: '#6b7280', marginTop: 12, margin: '12px 0 0 0' }}>
            Format: PDF attachment + caption ringkasan. Blast ke Ketua otomatis menghilangkan nama perorangan.
          </p>
        </div>
      )}

      {/* ===== Grafik YTD ===== */}
      <YtdBarChart scope={tenantProfile?.nama_jemaat_lokal || ''} />

      {/* ===== Laporan Keuangan ===== */}
      <div style={{ background: 'white', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.05)', border: '1px solid #f0f0eb', padding: 20 }}>
        <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 240 }}>
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, color: '#1B4332', margin: 0, fontWeight: 700 }}>📑 Laporan Keuangan</h3>
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
              Pilih rentang sabat untuk laporan rapat jemaat. PDF akan otomatis terkirim ke Pendeta & Ketua.
            </p>
          </div>
          <button
            onClick={() => setLaporanModal(true)}
            style={{
              padding: '10px 18px',
              background: '#1B4332',
              color: 'white',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 500,
              border: 'none',
              cursor: 'pointer',
              boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
              whiteSpace: 'nowrap',
            }}
          >
            Buat Laporan Keuangan
          </button>
        </div>
      </div>

      {/* ===== Blast confirmation modal ===== */}
      {blastModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 16 }}>
          <div style={{ background: 'white', borderRadius: 16, padding: 24, maxWidth: 480, width: '100%' }}>
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, color: '#1B4332', margin: '0 0 16px 0', fontWeight: 700 }}>
              Konfirmasi Blast ke {blastModal === 'pendeta' ? 'Pendeta' : 'Ketua'}
            </h3>
            <p style={{ color: '#4b5563', marginBottom: 16, fontSize: 13 }}>
              Kirim rekap sabat ini via WhatsApp?
              {blastModal === 'ketua' && (
                <span style={{ display: 'block', marginTop: 8, fontSize: 12, color: '#d97706' }}>
                  ⚠️ Nama umat akan dihilangkan (versi aggregate).
                </span>
              )}
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => handleBlast(blastModal)}
                disabled={blastLoading}
                style={{
                  flex: 1,
                  padding: '12px 16px',
                  background: '#B8860B',
                  color: 'white',
                  borderRadius: 10,
                  fontSize: 13,
                  fontWeight: 500,
                  border: 'none',
                  cursor: blastLoading ? 'wait' : 'pointer',
                  opacity: blastLoading ? 0.5 : 1,
                }}
              >
                {blastLoading ? 'Mengirim...' : 'Ya, Kirim'}
              </button>
              <button
                onClick={() => setBlastModal(null)}
                style={{
                  flex: 1,
                  padding: '12px 16px',
                  border: '1px solid #d1d5db',
                  background: 'white',
                  borderRadius: 10,
                  fontSize: 13,
                  fontWeight: 500,
                  cursor: 'pointer',
                  color: '#374151',
                }}
              >
                Batal
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== Laporan Keuangan modal ===== */}
      {laporanModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 16, overflowY: 'auto' }}>
          <div style={{ background: 'white', borderRadius: 16, padding: 24, maxWidth: 560, width: '100%', margin: '32px auto' }}>
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, color: '#1B4332', margin: '0 0 16px 0', fontWeight: 700 }}>
              📑 Buat Laporan Keuangan
            </h3>

            {!laporanResult ? (
              <>
                <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
                  Pilih rentang sabat untuk laporan. PDF akan otomatis di-generate dan di-blast ke Pendeta + Ketua.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Dari Sabat ke-</label>
                    <input
                      type="number"
                      min={1}
                      max={54}
                      value={laporanFrom}
                      onChange={(e) => setLaporanFrom(parseInt(e.target.value) || 1)}
                      style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 10, fontSize: 13, outline: 'none', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Sampai Sabat ke-</label>
                    <input
                      type="number"
                      min={1}
                      max={54}
                      value={laporanTo}
                      onChange={(e) => setLaporanTo(parseInt(e.target.value) || sabatInfo?.sabat_ke || 34)}
                      style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 10, fontSize: 13, outline: 'none', boxSizing: 'border-box' }}
                    />
                  </div>
                </div>

                {laporanError && (
                  <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: 12, borderRadius: 10, fontSize: 12, marginBottom: 16 }}>
                    {laporanError}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={handleGenerateLaporan}
                    disabled={laporanLoading}
                    style={{
                      flex: 1,
                      padding: '12px 16px',
                      background: '#1B4332',
                      color: 'white',
                      borderRadius: 10,
                      fontSize: 13,
                      fontWeight: 500,
                      border: 'none',
                      cursor: laporanLoading ? 'wait' : 'pointer',
                      opacity: laporanLoading ? 0.5 : 1,
                    }}
                  >
                    {laporanLoading ? '⏳ Generating...' : 'Generate & Blast'}
                  </button>
                  <button
                    onClick={() => {
                      setLaporanModal(false);
                      setLaporanResult(null);
                      setLaporanError('');
                    }}
                    style={{
                      padding: '12px 18px',
                      border: '1px solid #d1d5db',
                      background: 'white',
                      borderRadius: 10,
                      fontSize: 13,
                      fontWeight: 500,
                      cursor: 'pointer',
                      color: '#374151',
                    }}
                  >
                    Batal
                  </button>
                </div>
              </>
            ) : (
              <>
                <div style={{ background: '#ecfdf5', border: '1px solid #a7f3d0', color: '#065f46', padding: 16, borderRadius: 10, marginBottom: 16 }}>
                  <p style={{ fontWeight: 600, margin: 0 }}>✅ Laporan berhasil di-generate</p>
                  <p style={{ fontSize: 12, marginTop: 4 }}>
                    Sabat {laporanResult.sabat_from}–{laporanResult.sabat_to} tahun {laporanResult.tahun}
                    · {laporanResult.jumlah_kuitansi} kuitansi
                  </p>
                </div>

                <div style={{ background: '#FAF9F5', padding: 16, borderRadius: 10, marginBottom: 16, fontSize: 12 }}>
                  <p style={{ margin: '4px 0' }}>Total Perpuluhan: <span style={{ fontWeight: 700 }}>Rp {laporanResult.grand_total_x.toLocaleString()}</span></p>
                  <p style={{ margin: '4px 0' }}>Total PT: <span style={{ fontWeight: 700 }}>Rp {laporanResult.grand_total_pt.toLocaleString()}</span></p>
                  <p style={{ margin: '4px 0' }}>Total Khusus: <span style={{ fontWeight: 700 }}>Rp {laporanResult.grand_total_khusus.toLocaleString()}</span></p>
                  <p style={{ margin: '4px 0' }}>Porsi Jemaat: <span style={{ fontWeight: 700 }}>Rp {laporanResult.grand_total_porsi_jemaat.toLocaleString()}</span></p>
                  <p style={{ margin: '4px 0' }}>Porsi Misi: <span style={{ fontWeight: 700 }}>Rp {laporanResult.grand_total_porsi_misi.toLocaleString()}</span></p>
                  <p style={{ fontSize: 11, color: '#6b7280', marginTop: 8 }}>
                    <em>Terbilang: {laporanResult.grand_total_huruf}</em>
                  </p>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <p style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 8 }}>📲 Hasil Blast:</p>
                  {laporanResult.blast_results.length === 0 ? (
                    <p style={{ fontSize: 12, color: '#6b7280' }}>Tidak ada target blast.</p>
                  ) : (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                      {laporanResult.blast_results.map((b, i) => (
                        <li key={i} style={{ fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#f9fafb', padding: '8px 12px', marginBottom: 4, borderRadius: 6 }}>
                          <span><strong>{b.role}</strong> → {b.phone || b.nama || '?'}</span>
                          <span style={{
                            color: b.status === 'sent' ? '#059669' : b.status === 'skipped' ? '#6b7280' : '#dc2626',
                            fontWeight: 600,
                          }}>
                            {b.status}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <a
                  href={laporanResult.pdf_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: 'block',
                    textAlign: 'center',
                    width: '100%',
                    padding: '12px 16px',
                    background: '#B8860B',
                    color: 'white',
                    borderRadius: 10,
                    fontSize: 13,
                    fontWeight: 500,
                    textDecoration: 'none',
                    marginBottom: 8,
                    boxSizing: 'border-box',
                  }}
                >
                  📄 Download PDF ({Math.round(laporanResult.pdf_size_bytes / 1024)} KB)
                </a>

                <button
                  onClick={() => {
                    setLaporanModal(false);
                    setLaporanResult(null);
                  }}
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    border: '1px solid #d1d5db',
                    background: 'white',
                    borderRadius: 10,
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: 'pointer',
                    color: '#374151',
                    boxSizing: 'border-box',
                  }}
                >
                  Tutup
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default BendaharaDashboard;
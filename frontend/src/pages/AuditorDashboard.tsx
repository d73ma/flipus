import { useState, useEffect, Fragment } from 'react';
import api from '../lib/api';
import { SabatFilterPanel } from '../components/SabatFilterPanel';
import type { SabatFilter } from '../components/SabatFilterPanel';
import { YtdBarChart } from '../components/YtdBarChart';

interface SabatInfoOut {
  sabat_ke: number;
  tanggal_sabat: string;
  hari: string;
  tahun: number;
  bulan_nama: string;
  bulan_romawi: string;
}

interface PersentaseRow {
  no: number;
  tenant_id: number;
  entity_name: string;
  jumlah_kuitansi: number;
  total_x: number;
  total_pt: number;
  total_khusus: number;
  total_semua: number;
  porsi_uni_x: number;
  porsi_uni_pt: number;
  porsi_uni_kh: number;
  porsi_misi_x: number;
  porsi_misi_pt: number;
  porsi_misi_kh: number;
  porsi_jemaat: number;
  porsi_jemaat_x: number;
  porsi_jemaat_pt: number;
  porsi_jemaat_kh: number;
}

interface SabatIniOut {
  scope: string;
  sabat_ke: number;
  tanggal_sabat: string;
  hari: string;
  bulan_nama: string;
  tahun: number;
  items: PersentaseRow[];
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

interface MisiInfo {
  id: number;
  nama_resmi: string;
  uni_id?: number;
}

interface UniInfo {
  id: number;
  nama_resmi?: string;
}

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

const AuditorDashboard = () => {
  const [sabatInfo, setSabatInfo] = useState<SabatInfoOut | null>(null);
  const [sabatIni, setSabatIni] = useState<SabatIniOut | null>(null);
  const [misiInfo, setMisiInfo] = useState<MisiInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<SabatFilter>({ mode: 'sabat_ini' });

  // Percentage dialog
  const [pct, setPct] = useState<PersentaseConfig | null>(null);
  const [pctEditing, setPctEditing] = useState(false);
  const [pctX, setPctX] = useState(50);
  const [pctPT, setPctPT] = useState(50);
  const [pctSaving, setPctSaving] = useState(false);

  // Read-only display of UNI-level percentages (set by Admin Uni)
  const [pctUni, setPctUni] = useState<PersentaseConfig | null>(null);

  const fetchSabatInfo = async () => {
    try {
      const r = await api.get<SabatInfoOut>('/v1/reports/sabat-info');
      setSabatInfo(r.data);
    } catch (e) {}
  };

  const fetchMisiInfo = async () => {
    try {
      const r = await api.get('/v1/tenants/me');
      setMisiInfo({
        id: r.data.misi_konferens_id,
        nama_resmi: r.data.nama_kantor_misi || 'Misi',
        uni_id: r.data.uni_id,
      });
    } catch (e) {}
  };

  const fetchPersentaseUni = async () => {
    if (!misiInfo?.uni_id) return;
    try {
      const r = await api.get<PersentaseConfig>('/v1/master/persentase', {
        params: { scope: 'UNI', ref_id: misiInfo.uni_id },
      });
      setPctUni(r.data);
    } catch (e) {
      setPctUni(null);
    }
  };

  const fetchSabatIni = async () => {
    setLoading(true);
    try {
      const r = await api.get<SabatIniOut>('/v1/agregat/sabat-ini');
      setSabatIni(r.data);
    } catch (err: any) {
      console.warn('Gagal load sabat-ini:', err);
      setSabatIni(null);
    } finally {
      setLoading(false);
    }
  };

  const fetchPersentase = async () => {
    if (!misiInfo?.id) return;
    try {
      const r = await api.get<PersentaseConfig>('/v1/master/persentase', {
        params: { scope: 'MISI', ref_id: misiInfo.id },
      });
      // ===== Model "Uni + Misi ≤ 100, Jemaat = sisa" (Jerry 2026-09-09) =====
      // Slider = PORSI MISI LANGSUNG. pct_x_jemaat (MISI row) menyimpan
      // DERIVED jemaat = 100 - misi - uni. Display: misi = 1 - jemaat - uni.
      setPct(r.data);
      setPctX(Math.max(0, Math.round((1 - r.data.pct_x_jemaat - (pctUni?.pct_x_uni ?? 0)) * 100)));
      setPctPT(Math.max(0, Math.round((1 - r.data.pct_pt_jemaat - (pctUni?.pct_pt_uni ?? 0)) * 100)));
    } catch (e) {}
  };

  useEffect(() => {
    fetchSabatInfo();
    fetchMisiInfo();
    fetchSabatIni();
  }, []);

  useEffect(() => {
    if (misiInfo?.id) fetchPersentase();
  }, [misiInfo?.id]);

  useEffect(() => {
    if (misiInfo?.uni_id) fetchPersentaseUni();
  }, [misiInfo?.uni_id]);

  // Setelah pctUni siap, re-load pct MISI (karena display misi = 1 - jemaat - uni)
  useEffect(() => {
    if (misiInfo?.id && pctUni) fetchPersentase();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pctUni]);

  const handleSavePct = async () => {
    if (!misiInfo?.id) return;
    setPctSaving(true);
    try {
      // ===== Model "Uni + Misi ≤ 100, Jemaat = sisa" (Jerry 2026-09-09) =====
      // Slider = PORSI MISI. Save: pct_*_jemaat = DERIVED jemaat
      // = (100 - misi - uni)/100. KH tetap 0 (100% di Jemaat).
      const uniX = Math.round((pctUni?.pct_x_uni ?? 0) * 100);
      const uniPT = Math.round((pctUni?.pct_pt_uni ?? 0) * 100);
      await api.post('/v1/master/persentase', {
        scope: 'MISI',
        ref_id: misiInfo.id,
        pct_x_jemaat: Math.max(0, (100 - pctX - uniX) / 100),
        pct_pt_jemaat: Math.max(0, (100 - pctPT - uniPT) / 100),
        pct_khusus_jemaat: 0,
        pct_x_uni: pctUni?.pct_x_uni ?? 0,
        pct_pt_uni: pctUni?.pct_pt_uni ?? 0,
        pct_khusus_uni: pctUni?.pct_khusus_uni ?? 0,
      });
      alert('✅ Persentase berhasil diperbarui');
      setPctEditing(false);
      await fetchPersentase();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Gagal update persentase');
    } finally {
      setPctSaving(false);
    }
  };

  const title = misiInfo?.nama_resmi
    ? `Auditor Misi ${misiInfo.nama_resmi}`
    : 'Dashboard Auditor Misi';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div>
        <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, color: '#1B4332', margin: 0, fontWeight: 700 }}>
          {title}
        </h2>
        {sabatInfo && (
          <p style={{ color: '#6b7280', marginTop: 4, fontSize: 13 }}>
            {sabatInfo.hari}, {new Date(sabatInfo.tanggal_sabat).getDate()} {sabatInfo.bulan_nama} {sabatInfo.tahun}{' '}
            – Sabat ke {sabatInfo.sabat_ke}
          </p>
        )}
      </div>

      {/* ===== Percentage Dialog ===== */}
      {pct && (
        <div style={{
          background: 'linear-gradient(135deg, #0f3a3a 0%, #1c5252 100%)',
          color: 'white',
          borderRadius: 16,
          padding: 24,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, margin: 0, fontWeight: 600 }}>
              ⚙️ Pengaturan Persentase Porsi Misi
            </h3>
            {!pctEditing && (
              <button
                onClick={() => setPctEditing(true)}
                style={{
                  padding: '6px 14px',
                  background: 'rgba(255,255,255,0.1)',
                  border: 'none',
                  borderRadius: 10,
                  color: 'white',
                  fontSize: 12,
                  fontWeight: 500,
                  cursor: 'pointer',
                }}
              >
                Edit
              </button>
            )}
          </div>

          {!pctEditing ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
              <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 12, padding: 16 }}>
                <p style={{ fontSize: 11, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                  Perpuluhan (X) ke Misi
                </p>
                <p style={{ fontSize: 28, fontWeight: 700, color: '#fcd34d', margin: 0 }}>{pctX}%</p>
                <p style={{ fontSize: 11, opacity: 0.7, marginTop: 4 }}>
                  Ke Uni {Math.round((pctUni?.pct_x_uni ?? 0) * 100)}% · Sisa di Jemaat:{' '}
                  {Math.max(0, 100 - pctX - Math.round((pctUni?.pct_x_uni ?? 0) * 100))}%
                </p>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 12, padding: 16 }}>
                <p style={{ fontSize: 11, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                  Persembahan (PT) ke Misi
                </p>
                <p style={{ fontSize: 28, fontWeight: 700, color: '#fcd34d', margin: 0 }}>{pctPT}%</p>
                <p style={{ fontSize: 11, opacity: 0.7, marginTop: 4 }}>
                  Ke Uni {Math.round((pctUni?.pct_pt_uni ?? 0) * 100)}% · Sisa di Jemaat:{' '}
                  {Math.max(0, 100 - pctPT - Math.round((pctUni?.pct_pt_uni ?? 0) * 100))}%
                </p>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 12, padding: 16, opacity: 0.7 }}>
                <p style={{ fontSize: 11, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                  Khusus (KH) ke Misi
                </p>
                <p style={{ fontSize: 28, fontWeight: 700, color: '#fcd34d', margin: 0 }}>0%</p>
                <p style={{ fontSize: 11, opacity: 0.7, marginTop: 4 }}>🔒 Stand-by</p>
              </div>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, opacity: 0.9, marginBottom: 8 }}>
                  Perpuluhan ke Misi: <strong>{pctX}%</strong>
                </label>
                <input
                  type="range"
                  min={0}
                  max={100 - Math.round((pctUni?.pct_x_uni ?? 0) * 100)}
                  value={pctX}
                  onChange={(e) => setPctX(parseInt(e.target.value))}
                  style={{ width: '100%' }}
                />
                <p style={{ fontSize: 10, opacity: 0.65, marginTop: 6 }}>
                  Maksimal {100 - Math.round((pctUni?.pct_x_uni ?? 0) * 100)}% karena{' '}
                  {Math.round((pctUni?.pct_x_uni ?? 0) * 100)}% sudah dialokasikan ke Uni.
                </p>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, opacity: 0.9, marginBottom: 8 }}>
                  Persembahan ke Misi: <strong>{pctPT}%</strong>
                </label>
                <input
                  type="range"
                  min={0}
                  max={100 - Math.round((pctUni?.pct_pt_uni ?? 0) * 100)}
                  value={pctPT}
                  onChange={(e) => setPctPT(parseInt(e.target.value))}
                  style={{ width: '100%' }}
                />
                <p style={{ fontSize: 10, opacity: 0.65, marginTop: 6 }}>
                  Maksimal {100 - Math.round((pctUni?.pct_pt_uni ?? 0) * 100)}% karena{' '}
                  {Math.round((pctUni?.pct_pt_uni ?? 0) * 100)}% sudah dialokasikan ke Uni.
                </p>
              </div>
              <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8 }}>
                <button
                  onClick={handleSavePct}
                  disabled={pctSaving}
                  style={{
                    padding: '8px 18px',
                    background: '#f59e0b',
                    color: 'white',
                    border: 'none',
                    borderRadius: 10,
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: pctSaving ? 'wait' : 'pointer',
                    opacity: pctSaving ? 0.5 : 1,
                  }}
                >
                  {pctSaving ? 'Menyimpan...' : 'Simpan'}
                </button>
                <button
                  onClick={() => setPctEditing(false)}
                  style={{
                    padding: '8px 18px',
                    background: 'rgba(255,255,255,0.1)',
                    color: 'white',
                    border: 'none',
                    borderRadius: 10,
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  Batal
                </button>
              </div>
            </div>
          )}
          <p style={{ fontSize: 11, opacity: 0.7, marginTop: 12 }}>
            ℹ️ Nilai ini akan diterapkan ke semua jemaat di misi Anda dan tampil di dasbor Bendahara.
          </p>
        </div>
      )}

      {/* Read-only display of UNI-level percentages (set by Admin Uni) */}
      {pctUni && (
        <div style={{
          background: 'linear-gradient(135deg, #1B4332 0%, #0d2418 100%)',
          color: 'white',
          borderRadius: 16,
          padding: 20,
          border: '1px solid rgba(184, 134, 11, 0.3)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 14, margin: 0, fontWeight: 600, opacity: 0.95 }}>
              📊 Persentase Porsi Uni (ditetapkan Admin Uni)
            </h3>
            <span style={{ fontSize: 10, opacity: 0.6, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Read-only</span>
          </div>
          <p style={{ fontSize: 11, opacity: 0.65, margin: '0 0 12px 0' }}>
            Nilai ini ditetapkan oleh Admin Uni dan otomatis diterapkan ke kalkulator PORSI UNI di tabel di bawah.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 10, padding: 12 }}>
              <p style={{ fontSize: 10, opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                Perpuluhan ke Uni
              </p>
              <p style={{ fontSize: 22, fontWeight: 700, color: '#B8860B', margin: 0 }}>
                {Math.round(pctUni.pct_x_uni * 100)}%
              </p>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 10, padding: 12 }}>
              <p style={{ fontSize: 10, opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                Persembahan ke Uni
              </p>
              <p style={{ fontSize: 22, fontWeight: 700, color: '#B8860B', margin: 0 }}>
                {Math.round(pctUni.pct_pt_uni * 100)}%
              </p>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 10, padding: 12, opacity: 0.7 }}>
              <p style={{ fontSize: 10, opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 4px 0' }}>
                Khusus ke Uni
              </p>
              <p style={{ fontSize: 22, fontWeight: 700, color: '#B8860B', margin: 0 }}>
                {Math.round(pctUni.pct_khusus_uni * 100)}%
              </p>
              <p style={{ fontSize: 9, opacity: 0.7, marginTop: 2 }}>🔒 Stand-by</p>
            </div>
          </div>
        </div>
      )}

      {/* Filter */}
      <SabatFilterPanel
        onApply={setFilter}
        defaultSabat={sabatInfo?.sabat_ke || 1}
        sabatKeSekarang={sabatInfo?.sabat_ke || 34}
      />

      {/* Tabel Cross-Jemaat */}
      <div style={{ background: 'white', borderRadius: 16, boxShadow: '0 1px 2px rgba(0,0,0,0.04)', border: '1px solid #e5e7eb', overflow: 'hidden' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid #e5e7eb', background: '#1B4332', color: 'white' }}>
          <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 17, color: '#B8860B', margin: 0, fontWeight: 700 }}>
            Tabel Persembahan Semua Jemaat (Sabat Ini)
          </h3>
          {sabatInfo && (
            <p style={{ fontSize: 12, opacity: 0.8, marginTop: 4 }}>
              Tanggal: {sabatInfo.tanggal_sabat} (Sabat ke-{sabatInfo.sabat_ke}) · Aggregate per jemaat
            </p>
          )}
        </div>

        {loading ? (
          <div style={{ padding: 48, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>Memuat data...</div>
        ) : sabatIni && sabatIni.items.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#FAF9F5', borderBottom: '1px solid #e5e7eb' }}>
                  <th style={thStyle}>No</th>
                  <th style={thStyle}>Nama Jemaat</th>
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
                  <Fragment key={item.tenant_id}>
                  <tr style={{ background: mainBg, borderBottom: '1px solid #e5e7eb' }}>
                    <td style={{ ...tdStyle, color: '#6b7280' }}>{item.no}</td>
                    <td style={{ ...tdStyle, fontWeight: 500 }}>{item.entity_name}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {item.total_x.toLocaleString()}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {item.total_pt.toLocaleString()}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', color: '#6b7280' }}>
                      {item.total_khusus > 0 ? `Rp ${item.total_khusus.toLocaleString()}` : '—'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#1B4332' }}>
                      Rp {item.total_semua.toLocaleString()}
                    </td>
                  </tr>
                  <tr style={{ background: '#f0f9ff', borderBottom: '1px dotted #bae6fd' }}>
                    <td colSpan={6} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#0369a1' }}>
                      <strong>🏠 Porsi Jemaat</strong> (X/PT/KH):&nbsp;
                      <span style={{ fontWeight: 600 }}>X</span> {item.porsi_jemaat_x.toLocaleString()}
                      {' · '}<span style={{ fontWeight: 600 }}>PT</span> {item.porsi_jemaat_pt.toLocaleString()}
                      {item.total_khusus > 0 && (
                        <>
                          {' · '}<span style={{ fontWeight: 600 }}>KH</span> {item.porsi_jemaat_kh.toLocaleString()}
                        </>
                      )}
                    </td>
                  </tr>
                  <tr style={{ background: '#f0fdf4', borderBottom: '1px dotted #d1fae5' }}>
                    <td colSpan={6} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#047857' }}>
                      <strong>↗ Porsi Misi</strong> (X/PT/KH):&nbsp;
                      <span style={{ fontWeight: 600 }}>X</span> {item.porsi_misi_x.toLocaleString()}
                      {' · '}<span style={{ fontWeight: 600 }}>PT</span> {item.porsi_misi_pt.toLocaleString()}
                      {item.total_khusus > 0 && (
                        <>
                          {' · '}<span style={{ fontWeight: 600 }}>KH</span> {item.porsi_misi_kh.toLocaleString()}
                        </>
                      )}
                    </td>
                  </tr>
                  <tr style={{ background: '#faf5ff', borderBottom: '2px solid #1B4332' }}>
                    <td colSpan={6} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#7c3aed' }}>
                      <strong>↗ Porsi Uni</strong> (X/PT/KH):&nbsp;
                      <span style={{ fontWeight: 600 }}>X</span> {item.porsi_uni_x.toLocaleString()}
                      {' · '}<span style={{ fontWeight: 600 }}>PT</span> {item.porsi_uni_pt.toLocaleString()}
                      {item.total_khusus > 0 && (
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
                <tr style={{ background: '#1B4332', color: 'white', fontWeight: 700 }}>
                  <td colSpan={2} style={{ ...tdStyle, fontWeight: 700 }}>Total Keseluruhan</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {sabatIni.grand_total_x.toLocaleString()}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {sabatIni.grand_total_pt.toLocaleString()}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>Rp {sabatIni.grand_total_khusus.toLocaleString()}</td>
                  <td style={{ ...tdStyle, textAlign: 'right', color: '#B8860B' }}>
                    Rp {sabatIni.grand_total_semua.toLocaleString()}
                  </td>
                </tr>
                <tr style={{ background: '#f0f9ff' }}>
                  <td colSpan={6} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#0369a1' }}>
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
                  <td colSpan={6} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#047857' }}>
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
                <tr style={{ background: '#faf5ff', borderTop: '2px solid #1B4332' }}>
                  <td colSpan={6} style={{ ...tdStyle, textAlign: 'right', fontSize: 11, color: '#7c3aed' }}>
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
          <div style={{ padding: 48, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
            Belum ada kuitansi aggregate untuk misi ini di sabat berjalan.
          </div>
        )}

        {sabatIni && sabatIni.items.length > 0 && (
          <div style={{ padding: '12px 24px', background: '#FAF9F5', fontSize: 12, color: '#374151', borderTop: '1px solid #e5e7eb' }}>
            <span style={{ fontWeight: 600 }}>Terbilang:</span> {sabatIni.grand_total_huruf}
          </div>
        )}
      </div>

      {/* Grafik YTD */}
      <YtdBarChart scope={`Misi ${misiInfo?.nama_resmi || ''}`} />
    </div>
  );
};

export default AuditorDashboard;

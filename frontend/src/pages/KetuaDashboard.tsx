import { useState, useEffect } from 'react';
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

interface SabatIniItem {
  no: number;
  id_kuitansi: number;
  nomor_kuitansi: string;
  // Catatan: SABAT INI tabel untuk Ketua TIDAK menampilkan nama_pemberi (privacy)
  tanggal_sabat: string;
  perpuluhan_x_angka: number;
  pt_angka: number;
  khusus_angka: number;
  total: number;
  porsi_misi_x: number;
  porsi_misi_pt: number;
  porsi_jemaat_x: number;
  porsi_jemaat_pt: number;
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
  grand_total_porsi_jemaat: number;
  grand_total_huruf: string;
}

interface TenantProfile {
  id: number;
  nama_jemaat_lokal: string;
  nama_uni: string;
  nama_kantor_misi: string;
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

const KetuaDashboard = () => {
  const [sabatInfo, setSabatInfo] = useState<SabatInfoOut | null>(null);
  const [sabatIni, setSabatIni] = useState<SabatIniOut | null>(null);
  const [tenantProfile, setTenantProfile] = useState<TenantProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<SabatFilter>({ mode: 'sabat_ini' });

  const fetchSabatInfo = async () => {
    try {
      const r = await api.get<SabatInfoOut>('/v1/reports/sabat-info');
      setSabatInfo(r.data);
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
      console.warn('Gagal load sabat-ini:', err);
      setSabatIni(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSabatInfo();
    fetchTenantProfile();
    fetchSabatIni();
  }, []);

  const title = tenantProfile?.nama_jemaat_lokal
    ? `Ketua ${tenantProfile.nama_jemaat_lokal}`
    : 'Dashboard Ketua';

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

      {/* Filter */}
      <SabatFilterPanel
        onApply={setFilter}
        defaultSabat={sabatInfo?.sabat_ke || 1}
        sabatKeSekarang={sabatInfo?.sabat_ke || 34}
      />

      {/* Tabel Persembahan Sabat Ini — TANPA kolom nama umat (privacy) */}
      <div style={{ background: 'white', borderRadius: 16, boxShadow: '0 1px 2px rgba(0,0,0,0.04)', border: '1px solid #e5e7eb', overflow: 'hidden' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid #e5e7eb', background: '#1B4332', color: 'white' }}>
          <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 17, color: '#B8860B', margin: 0, fontWeight: 700 }}>
            Tabel Persembahan Sabat Ini
          </h3>
          {sabatInfo && (
            <p style={{ fontSize: 12, opacity: 0.8, marginTop: 4 }}>
              Tanggal: {sabatInfo.tanggal_sabat} (Sabat ke-{sabatInfo.sabat_ke}) — aggregate, tanpa nama pemberi
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
                  <th style={thStyle}>No. Kuitansi</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>X</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>PT</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Khusus</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Total</th>
                  <th style={{ ...thStyle, textAlign: 'right', background: '#f0f9ff' }}>Porsi Jemaat</th>
                  <th style={{ ...thStyle, textAlign: 'right', background: '#ecfdf5' }}>Porsi Misi</th>
                </tr>
              </thead>
              <tbody>
                {sabatIni.items.map((item, idx) => (
                  <tr key={item.id_kuitansi} style={{ borderBottom: '1px solid #f3f4f6', background: idx % 2 === 0 ? '#fafaf5' : 'white' }}>
                    <td style={{ ...tdStyle, color: '#6b7280' }}>{item.no}</td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>{item.nomor_kuitansi}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 500 }}>
                      Rp {item.perpuluhan_x_angka.toLocaleString()}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 500 }}>
                      Rp {item.pt_angka.toLocaleString()}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right', color: '#6b7280' }}>
                      {item.khusus_angka > 0 ? `Rp ${item.khusus_angka.toLocaleString()}` : '—'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#1B4332' }}>
                      Rp {item.total.toLocaleString()}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right', color: '#0369a1', fontSize: 11, background: '#f0f9ff' }}>
                      <div>X: Rp {item.porsi_jemaat_x.toLocaleString()}</div>
                      <div>PT: Rp {item.porsi_jemaat_pt.toLocaleString()}</div>
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right', color: '#047857', fontSize: 11, background: '#f0fdf4' }}>
                      <div>X: Rp {item.porsi_misi_x.toLocaleString()}</div>
                      <div>PT: Rp {item.porsi_misi_pt.toLocaleString()}</div>
                    </td>
                  </tr>
                ))}
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
                  <td style={{ ...tdStyle, textAlign: 'right', fontSize: 11 }}>
                    Rp {sabatIni.grand_total_porsi_jemaat.toLocaleString()}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right', fontSize: 11 }}>
                    X: Rp {sabatIni.grand_total_porsi_misi_x.toLocaleString()}<br />
                    PT: Rp {sabatIni.grand_total_porsi_misi_pt.toLocaleString()}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <div style={{ padding: 48, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
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

      {/* Grafik YTD */}
      <YtdBarChart scope={tenantProfile?.nama_jemaat_lokal || ''} />
    </div>
  );
};

export default KetuaDashboard;

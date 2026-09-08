/**
 * v2.0 M5 — Halaman Approval Pengeluaran untuk Ketua + Pendeta.
 *
 * Role-aware component:
 * - KETUA_KEUANGAN: approve status=pending_approval → approved_ketua
 * - PENDETA: approve status=approved_ketua → approved
 * - Keduanya bisa reject (dengan reason)
 *
 * Approval workflow (Jerry 2026-09-01):
 * - is_rutin=True → auto-approved saat Bendahara submit (tidak masuk antrian ini)
 * - is_rutin=False → butuh approval Ketua + Pendeta (dual-stage)
 */
import { useEffect, useState } from 'react';
import api from '../lib/api';

interface Pengeluaran {
  id: number;
  nomor_pengeluaran: string;
  tanggal: string;
  tanggal_sabat: string;
  kategori_pengeluaran_id: number;
  kategori_nama: string | null;
  kategori_alias: string | null;
  jumlah: number;
  deskripsi: string | null;
  penerima: string | null;
  metode_bayar: string | null;
  status: string;
  created_by_user_id: number | null;
  created_at: string;
  approved_ketua_at: string | null;
  approved_pendeta_at: string | null;
  rejected_at: string | null;
  rejected_reason: string | null;
}

interface Props {
  role: 'KETUA_KEUANGAN' | 'PENDETA';
}

// ========== Inline styles (anti-Tailwind misconfig) ==========
const containerStyle: React.CSSProperties = {
  maxWidth: 640,
  margin: '0 auto',
  padding: '0 16px 32px',
  fontFamily: "'Inter', sans-serif",
};

const headerStyle: React.CSSProperties = {
  fontFamily: "'Playfair Display', serif",
  fontSize: 24,
  fontWeight: 700,
  color: '#1B4332',
  marginBottom: 4,
};

const subtitleStyle: React.CSSProperties = {
  fontSize: 13,
  color: '#6b7280',
  marginBottom: 24,
};

const cardStyle: React.CSSProperties = {
  background: 'white',
  borderRadius: 12,
  padding: 20,
  boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
  marginBottom: 16,
};

const tabStyle = (active: boolean): React.CSSProperties => ({
  flex: 1,
  padding: '12px 16px',
  background: active ? '#1B4332' : 'white',
  color: active ? 'white' : '#1B4332',
  border: '1px solid #1B4332',
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: 48,
});

const approveBtnStyle: React.CSSProperties = {
  flex: 1,
  padding: '12px 16px',
  background: '#16a34a',
  color: 'white',
  border: 'none',
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: 48,
};

const rejectBtnStyle: React.CSSProperties = {
  flex: 1,
  padding: '12px 16px',
  background: '#dc2626',
  color: 'white',
  border: 'none',
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: 48,
};

const noteBtnStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  background: 'white',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: 8,
  fontSize: 13,
  cursor: 'pointer',
  minHeight: 'auto',
};

const STATUS_COLORS: Record<string, { bg: string; fg: string; label: string }> = {
  draft: { bg: '#f3f4f6', fg: '#6b7280', label: 'Draft' },
  pending_approval: { bg: '#fef3c7', fg: '#92400e', label: 'Menunggu Ketua' },
  approved_ketua: { bg: '#dbeafe', fg: '#1e40af', label: 'Menunggu Pendeta' },
  approved: { bg: '#d1fae5', fg: '#065f46', label: 'Disetujui' },
  rejected: { bg: '#fee2e2', fg: '#991b1b', label: 'Ditolak' },
};

function formatRupiah(n: number): string {
  return 'Rp ' + n.toLocaleString('id-ID');
}

export default function PengeluaranApproval({ role }: Props) {
  const [activeTab, setActiveTab] = useState<'pending' | 'history'>('pending');
  const [list, setList] = useState<Pengeluaran[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [actioningId, setActioningId] = useState<number | null>(null);
  const [noteForId, setNoteForId] = useState<number | null>(null);
  const [noteText, setNoteText] = useState('');
  const [rejectForId, setRejectForId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  // Determine which statuses to show per tab
  // Ketua: pending tab = ['pending_approval'], history = ['approved_ketua', 'approved', 'rejected']
  // Pendeta: pending tab = ['approved_ketua'], history = ['approved', 'rejected']
  const pendingStatuses = role === 'KETUA_KEUANGAN' ? ['pending_approval'] : ['approved_ketua'];
  const historyStatuses = ['approved', 'rejected'];

  useEffect(() => {
    loadList();
  }, [activeTab]);

  async function loadList() {
    setLoading(true);
    setError(null);
    try {
      const statuses = activeTab === 'pending' ? pendingStatuses : historyStatuses;
      // Fetch all (limit 100), filter client-side
      const resp = await api.get<Pengeluaran[]>('/v1/pengeluaran/list?limit=100');
      const filtered = resp.data.filter((p) => statuses.includes(p.status));
      setList(filtered);
    } catch (e: any) {
      setError(e.message || 'Gagal load list');
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove(id: number) {
    setActioningId(id);
    setError(null);
    try {
      const endpoint = role === 'KETUA_KEUANGAN' ? `/v1/pengeluaran/${id}/approve-ketua` : `/v1/pengeluaran/${id}/approve-pendeta`;
      await api.post(endpoint, { note: noteText.trim() || null });
      setSuccessMsg(`Pengeluaran ${role === 'KETUA_KEUANGAN' ? 'disetujui sebagai Ketua (lanjut ke Pendeta)' : 'final approved ✓'}`);
      setTimeout(() => setSuccessMsg(null), 4000);
      setNoteForId(null);
      setNoteText('');
      await loadList();
    } catch (e: any) {
      setError(e.message || 'Gagal approve');
    } finally {
      setActioningId(null);
    }
  }

  async function handleReject(id: number) {
    if (!rejectReason.trim() || rejectReason.length < 3) {
      setError('Alasan penolakan wajib diisi (min 3 karakter)');
      return;
    }
    setActioningId(id);
    setError(null);
    try {
      await api.post(`/v1/pengeluaran/${id}/reject`, { reason: rejectReason.trim() });
      setSuccessMsg('Pengeluaran ditolak');
      setTimeout(() => setSuccessMsg(null), 3000);
      setRejectForId(null);
      setRejectReason('');
      await loadList();
    } catch (e: any) {
      setError(e.message || 'Gagal reject');
    } finally {
      setActioningId(null);
    }
  }

  const pendingLabel = role === 'KETUA_KEUANGAN' ? 'Menunggu Approval Ketua' : 'Menunggu Approval Pendeta';

  return (
    <div style={containerStyle}>
      <h1 style={headerStyle}>💸 Approval Pengeluaran</h1>
      <p style={subtitleStyle}>
        Login sebagai <strong>{role === 'KETUA_KEUANGAN' ? 'Ketua Keuangan' : 'Pendeta'}</strong>.{' '}
        Pengeluaran rutin auto-skip — fokus ke non-rutin (perlu 2 approval).
      </p>

      {error && (
        <div style={{ ...cardStyle, borderLeft: '4px solid #dc2626', background: '#fef2f2' }}>
          <div style={{ color: '#991b1b', fontWeight: 600 }}>⚠ Error</div>
          <div style={{ color: '#7f1d1d', fontSize: 14, marginTop: 4 }}>{error}</div>
        </div>
      )}

      {successMsg && (
        <div style={{ ...cardStyle, borderLeft: '4px solid #16a34a', background: '#f0fdf4' }}>
          <div style={{ color: '#166534', fontWeight: 600 }}>✓ Sukses</div>
          <div style={{ color: '#14532d', fontSize: 14, marginTop: 4 }}>{successMsg}</div>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button onClick={() => setActiveTab('pending')} style={tabStyle(activeTab === 'pending')}>
          📥 Pending ({pendingLabel})
        </button>
        <button onClick={() => setActiveTab('history')} style={tabStyle(activeTab === 'history')}>
          📜 Riwayat
        </button>
      </div>

      {/* List */}
      {loading ? (
        <div style={cardStyle}>
          <div style={{ textAlign: 'center', color: '#6b7280', padding: 20 }}>Loading...</div>
        </div>
      ) : list.length === 0 ? (
        <div style={cardStyle}>
          <div style={{ textAlign: 'center', color: '#6b7280', padding: 20, fontStyle: 'italic' }}>
            {activeTab === 'pending' ? '✓ Tidak ada pending approval.' : 'Belum ada riwayat.'}
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {list.map((p) => {
            const sc = STATUS_COLORS[p.status] || STATUS_COLORS.draft;
            return (
              <div key={p.id} style={{ ...cardStyle, padding: 16 }}>
                {/* Top */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8, gap: 8 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6b7280' }}>{p.nomor_pengeluaran}</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#1B4332', marginTop: 2 }}>
                      {p.kategori_nama || `Kategori #${p.kategori_pengeluaran_id}`}
                    </div>
                  </div>
                  <span
                    style={{
                      background: sc.bg,
                      color: sc.fg,
                      padding: '4px 10px',
                      borderRadius: 999,
                      fontSize: 11,
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                      flexShrink: 0,
                    }}
                  >
                    {sc.label}
                  </span>
                </div>

                {/* Jumlah */}
                <div style={{ fontSize: 20, fontWeight: 700, color: '#1B4332', fontFamily: "'JetBrains Mono', monospace", marginBottom: 4 }}>
                  {formatRupiah(p.jumlah)}
                </div>

                {/* Meta */}
                <div style={{ fontSize: 12, color: '#6b7280', display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
                  <span>📅 {p.tanggal}</span>
                  {p.penerima && <span>👤 {p.penerima}</span>}
                  {p.metode_bayar && <span>💳 {p.metode_bayar}</span>}
                </div>

                {p.deskripsi && (
                  <div style={{ fontSize: 13, color: '#374151', marginBottom: 8, fontStyle: 'italic' }}>
                    "{p.deskripsi}"
                  </div>
                )}

                {/* History info */}
                {p.approved_ketua_at && (
                  <div style={{ fontSize: 11, color: '#1e40af', marginBottom: 4 }}>
                    ✓ Ketua approved: {new Date(p.approved_ketua_at).toLocaleString('id-ID')}
                  </div>
                )}
                {p.approved_pendeta_at && (
                  <div style={{ fontSize: 11, color: '#065f46', marginBottom: 4 }}>
                    ✓ Pendeta approved: {new Date(p.approved_pendeta_at).toLocaleString('id-ID')}
                  </div>
                )}
                {p.rejected_reason && (
                  <div style={{ background: '#fee2e2', color: '#991b1b', padding: '6px 10px', borderRadius: 6, marginBottom: 8, fontSize: 12 }}>
                    <strong>Ditolak:</strong> {p.rejected_reason}
                  </div>
                )}

                {/* Actions untuk pending */}
                {activeTab === 'pending' && (
                  <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {/* Note input (collapsible) */}
                    {noteForId === p.id && (
                      <div style={{ background: '#F5EFE0', padding: 10, borderRadius: 8 }}>
                        <label style={{ fontSize: 12, fontWeight: 600, color: '#1B4332', display: 'block', marginBottom: 6 }}>
                          Catatan (opsional)
                        </label>
                        <textarea
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            fontSize: 14,
                            border: '1px solid #d1d5db',
                            borderRadius: 6,
                            boxSizing: 'border-box',
                            minHeight: 60,
                            resize: 'vertical',
                            fontFamily: 'inherit',
                          }}
                          value={noteText}
                          onChange={(e) => setNoteText(e.target.value)}
                          placeholder="Tambahkan catatan approval..."
                          maxLength={255}
                        />
                      </div>
                    )}

                    {/* Reject input (collapsible) */}
                    {rejectForId === p.id && (
                      <div style={{ background: '#fee2e2', padding: 10, borderRadius: 8 }}>
                        <label style={{ fontSize: 12, fontWeight: 600, color: '#991b1b', display: 'block', marginBottom: 6 }}>
                          Alasan Penolakan (wajib, min 3 karakter)
                        </label>
                        <textarea
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            fontSize: 14,
                            border: '1px solid #fca5a5',
                            borderRadius: 6,
                            boxSizing: 'border-box',
                            minHeight: 60,
                            resize: 'vertical',
                            fontFamily: 'inherit',
                          }}
                          value={rejectReason}
                          onChange={(e) => setRejectReason(e.target.value)}
                          placeholder="misal: Tidak ada di RAPB 2026"
                          maxLength={500}
                        />
                      </div>
                    )}

                    {/* Buttons */}
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {(noteForId === p.id || rejectForId === p.id) ? (
                        <>
                          <button
                            onClick={() => {
                              if (noteForId === p.id) handleApprove(p.id);
                              else if (rejectForId === p.id) handleReject(p.id);
                            }}
                            disabled={actioningId === p.id}
                            style={noteForId === p.id ? approveBtnStyle : rejectBtnStyle}
                          >
                            {actioningId === p.id ? '...' : '✓ Konfirmasi'}
                          </button>
                          <button
                            onClick={() => {
                              setNoteForId(null);
                              setNoteText('');
                              setRejectForId(null);
                              setRejectReason('');
                            }}
                            style={{ ...noteBtnStyle, flex: 1 }}
                          >
                            Batal
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => setNoteForId(p.id)}
                            disabled={actioningId === p.id}
                            style={approveBtnStyle}
                          >
                            ✓ Approve
                          </button>
                          <button
                            onClick={() => setRejectForId(p.id)}
                            disabled={actioningId === p.id}
                            style={rejectBtnStyle}
                          >
                            ✕ Tolak
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
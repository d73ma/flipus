/**
 * v2.0 M5 — Halaman Pengeluaran untuk Bendahara.
 *
 * Features:
 * - Form input Pengeluaran (tanggal, kategori, jumlah, deskripsi, penerima, metode_bayar)
 * - Auto-create custom kategori Pengeluaran (inline di form)
 * - List Pengeluaran per tenant (filter by status + bulan)
 * - Edit draft + Submit (auto-approve kalau rutin, pending kalau non-rutin)
 * - Status badge color-coded
 *
 * Approval workflow (Jerry 2026-09-01):
 * - is_rutin=True (Listrik/Air/Telpon/Gaji Kostor) → auto-approved saat submit
 * - is_rutin=False → butuh approval Ketua + Pendeta (dual-stage)
 */
import { useEffect, useState } from 'react';
import api from '../lib/api';

interface KategoriOption {
  id: number;
  nama: string;
  alias: string;
  is_rutin: boolean;
  urutan: number;
}

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

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 13,
  fontWeight: 600,
  color: '#374151',
  marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '12px 14px',
  fontSize: 15,
  border: '1px solid #d1d5db',
  borderRadius: 8,
  boxSizing: 'border-box',
  outline: 'none',
  minHeight: 48,
};

const selectStyle: React.CSSProperties = { ...inputStyle, background: 'white', cursor: 'pointer' };

const textareaStyle: React.CSSProperties = {
  width: '100%',
  padding: '12px 14px',
  fontSize: 15,
  border: '1px solid #d1d5db',
  borderRadius: 8,
  boxSizing: 'border-box',
  outline: 'none',
  minHeight: 80,
  resize: 'vertical',
  fontFamily: 'inherit',
};

const primaryBtnStyle: React.CSSProperties = {
  width: '100%',
  padding: '14px 20px',
  background: '#1B4332',
  color: 'white',
  border: 'none',
  borderRadius: 10,
  fontSize: 15,
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: 48,
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  background: 'white',
  color: '#1B4332',
  border: '1px solid #1B4332',
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: 36,
};

const ghostBtnStyle: React.CSSProperties = {
  width: 40,
  height: 40,
  background: 'transparent',
  color: '#dc2626',
  border: '1px solid #fecaca',
  borderRadius: 8,
  fontSize: 18,
  cursor: 'pointer',
  flexShrink: 0,
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

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function PengeluaranInput() {
  const [kategoriList, setKategoriList] = useState<KategoriOption[]>([]);
  const [pengeluaranList, setPengeluaranList] = useState<Pengeluaran[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form state
  const [tanggal, setTanggal] = useState(todayISO());
  const [kategoriId, setKategoriId] = useState<number | ''>('');
  const [jumlah, setJumlah] = useState('');
  const [deskripsi, setDeskripsi] = useState('');
  const [penerima, setPenerima] = useState('');
  const [metodeBayar, setMetodeBayar] = useState('tunai');

  // Inline add kategori
  const [showAddKategori, setShowAddKategori] = useState(false);
  const [newKatNama, setNewKatNama] = useState('');
  const [newKatAlias, setNewKatAlias] = useState('');
  const [newKatRutin, setNewKatRutin] = useState(false);
  const [addingKategori, setAddingKategori] = useState(false);

  // Edit state
  const [editingId, setEditingId] = useState<number | null>(null);

  // Filter
  const [filterBulan, setFilterBulan] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });

  useEffect(() => {
    loadKategori();
    loadPengeluaran();
  }, [filterBulan]);

  async function loadKategori() {
    try {
      const resp = await api.get<KategoriOption[]>('/kategori-pengeluaran/list');
      setKategoriList(resp.data);
    } catch (e: any) {
      console.error('loadKategori failed', e);
    }
  }

  async function loadPengeluaran() {
    setLoading(true);
    try {
      const resp = await api.get<Pengeluaran[]>(`/pengeluaran/list?bulan=${filterBulan}&limit=100`);
      setPengeluaranList(resp.data);
    } catch (e: any) {
      setError(e.message || 'Gagal load pengeluaran');
    } finally {
      setLoading(false);
    }
  }

  async function handleAddKategori() {
    if (!newKatNama.trim() || !newKatAlias.trim()) {
      setError('Nama dan alias kategori wajib diisi');
      return;
    }
    setAddingKategori(true);
    setError(null);
    try {
      const resp = await api.post<KategoriOption>('/kategori-pengeluaran/create', {
        nama: newKatNama.trim(),
        alias: newKatAlias.trim().toUpperCase(),
        is_rutin: newKatRutin,
      });
      const created = resp.data;
      setKategoriList(
        [...kategoriList, created].sort((a, b) => (b.is_rutin ? 1 : 0) - (a.is_rutin ? 1 : 0) || a.urutan - b.urutan)
      );
      setKategoriId(created.id);
      setShowAddKategori(false);
      setNewKatNama('');
      setNewKatAlias('');
      setNewKatRutin(false);
      setSuccessMsg(`Kategori "${created.nama}" berhasil ditambahkan`);
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e: any) {
      setError(e.message || 'Gagal tambah kategori');
    } finally {
      setAddingKategori(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!kategoriId || !jumlah) {
      setError('Kategori dan jumlah wajib diisi');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        tanggal,
        kategori_pengeluaran_id: kategoriId,
        jumlah: parseInt(jumlah.replace(/\D/g, ''), 10),
        deskripsi: deskripsi.trim() || null,
        penerima: penerima.trim() || null,
        metode_bayar: metodeBayar,
      };
      if (editingId) {
        await api.put(`/pengeluaran/${editingId}/update`, payload);
      } else {
        await api.post('/pengeluaran/create', payload);
      }
      // Reset form
      setKategoriId('');
      setJumlah('');
      setDeskripsi('');
      setPenerima('');
      setEditingId(null);
      await loadPengeluaran();
      await loadKategori();
      setSuccessMsg(editingId ? 'Pengeluaran diupdate' : 'Pengeluaran dibuat (status: draft)');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e: any) {
      setError(e.message || 'Gagal simpan');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitForApproval(id: number) {
    setError(null);
    try {
      const resp = await api.post<Pengeluaran>(`/pengeluaran/${id}/submit`, {});
      const updated = resp.data;
      if (updated.status === 'approved') {
        setSuccessMsg('Pengeluaran RUTIN: auto-approved! ✓');
      } else if (updated.status === 'pending_approval') {
        setSuccessMsg('Pengeluaran NON-RUTIN: dikirim ke Ketua untuk approval');
      }
      setTimeout(() => setSuccessMsg(null), 4000);
      await loadPengeluaran();
    } catch (e: any) {
      setError(e.message || 'Gagal submit');
    }
  }

  async function handleDeleteDraft(_id: number) {
    if (!confirm('Hapus draft ini?')) return;
    // Untuk MVP, hapus via update dengan flag is_purged? Backend belum support delete endpoint.
    // Temporary: just inform user
    setError('Delete draft belum diimplementasi di backend. Update via form edit atau hubungi admin.');
  }

  function handleEdit(p: Pengeluaran) {
    if (p.status !== 'draft') return;
    setEditingId(p.id);
    setTanggal(p.tanggal);
    setKategoriId(p.kategori_pengeluaran_id);
    setJumlah(p.jumlah.toString());
    setDeskripsi(p.deskripsi || '');
    setPenerima(p.penerima || '');
    setMetodeBayar(p.metode_bayar || 'tunai');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function cancelEdit() {
    setEditingId(null);
    setKategoriId('');
    setJumlah('');
    setDeskripsi('');
    setPenerima('');
  }

  return (
    <div style={containerStyle}>
      <h1 style={headerStyle}>💸 Pengeluaran</h1>
      <p style={subtitleStyle}>
        Catat pengeluaran jemaat. Rutin (listrik/air/telpon/kostor) auto-approved. Lainnya perlu approval Ketua + Pendeta.
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

      {/* Form */}
      <div style={cardStyle}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: '#1B4332', marginBottom: 16 }}>
          {editingId ? '✏ Edit Draft' : '➕ Catat Pengeluaran'}
        </h2>
        <form onSubmit={handleSubmit}>
          {/* Tanggal + Kategori (side by side on desktop) */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <label style={labelStyle}>Tanggal</label>
              <input
                type="date"
                style={inputStyle}
                value={tanggal}
                onChange={(e) => setTanggal(e.target.value)}
                required
              />
            </div>
            <div style={{ flex: 1.4, minWidth: 0 }}>
              <label style={labelStyle}>
                Kategori{' '}
                <button
                  type="button"
                  onClick={() => setShowAddKategori(!showAddKategori)}
                  style={{ ...secondaryBtnStyle, padding: '2px 8px', fontSize: 11, minHeight: 'auto', display: 'inline-block', marginLeft: 4 }}
                >
                  {showAddKategori ? '× Batal' : '+ Tambah'}
                </button>
              </label>
              <select
                style={selectStyle}
                value={kategoriId}
                onChange={(e) => setKategoriId(parseInt(e.target.value) || '')}
                required
              >
                <option value="">-- Pilih Kategori --</option>
                {kategoriList.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.is_rutin ? '⭐ ' : ''}{k.nama} ({k.alias}){k.is_rutin ? ' — Rutin' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Inline add kategori */}
          {showAddKategori && (
            <div style={{ background: '#F5EFE0', padding: 12, borderRadius: 8, marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#1B4332', marginBottom: 8 }}>
                Tambah Kategori Custom
              </div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                <input
                  type="text"
                  placeholder="Nama (misal: Sosial)"
                  style={{ ...inputStyle, flex: 1, minWidth: 0 }}
                  value={newKatNama}
                  onChange={(e) => setNewKatNama(e.target.value)}
                  maxLength={50}
                />
                <input
                  type="text"
                  placeholder="Alias (SOS)"
                  style={{ ...inputStyle, flex: 0.5, minWidth: 0, textTransform: 'uppercase' }}
                  value={newKatAlias}
                  onChange={(e) => setNewKatAlias(e.target.value)}
                  maxLength={8}
                />
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={newKatRutin}
                  onChange={(e) => setNewKatRutin(e.target.checked)}
                />
                <span>Rutin (auto-approved, skip approval Ketua+Pendeta)</span>
              </label>
              <button
                type="button"
                onClick={handleAddKategori}
                disabled={addingKategori}
                style={{ ...primaryBtnStyle, padding: '8px 16px', fontSize: 13, minHeight: 'auto', width: 'auto' }}
              >
                {addingKategori ? 'Menyimpan...' : 'Simpan Kategori'}
              </button>
            </div>
          )}

          {/* Jumlah */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Jumlah (Rp)</label>
            <input
              type="text"
              inputMode="numeric"
              style={{ ...inputStyle, textAlign: 'right' }}
              value={jumlah ? parseInt(jumlah.replace(/\D/g, ''), 10).toLocaleString('id-ID') : ''}
              onChange={(e) => setJumlah(e.target.value)}
              placeholder="0"
              required
            />
          </div>

          {/* Penerima + Metode Bayar */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <label style={labelStyle}>Penerima (opsional)</label>
              <input
                type="text"
                style={inputStyle}
                value={penerima}
                onChange={(e) => setPenerima(e.target.value)}
                placeholder="Vendor / supplier / personil"
                maxLength={200}
              />
            </div>
            <div style={{ flex: 0.8, minWidth: 0 }}>
              <label style={labelStyle}>Metode Bayar</label>
              <select style={selectStyle} value={metodeBayar} onChange={(e) => setMetodeBayar(e.target.value)}>
                <option value="tunai">Tunai</option>
                <option value="transfer">Transfer</option>
                <option value="cek">Cek</option>
                <option value="lain">Lain-lain</option>
              </select>
            </div>
          </div>

          {/* Deskripsi */}
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Deskripsi (opsional)</label>
            <textarea
              style={textareaStyle}
              value={deskripsi}
              onChange={(e) => setDeskripsi(e.target.value)}
              placeholder="Catatan / detail transaksi"
              maxLength={500}
            />
          </div>

          {/* Submit button */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="submit" disabled={submitting} style={primaryBtnStyle}>
              {submitting ? 'Menyimpan...' : editingId ? '💾 Update Draft' : '💾 Simpan Draft'}
            </button>
            {editingId && (
              <button type="button" onClick={cancelEdit} style={{ ...secondaryBtnStyle, minHeight: 48 }}>
                Batal
              </button>
            )}
          </div>
        </form>
      </div>

      {/* Filter + List */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: '#1B4332' }}>📋 Daftar Pengeluaran</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: '#6b7280' }}>Bulan:</span>
            <input
              type="month"
              style={{ ...inputStyle, width: 'auto', minHeight: 'auto', padding: '6px 10px', fontSize: 13 }}
              value={filterBulan}
              onChange={(e) => setFilterBulan(e.target.value)}
            />
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', color: '#6b7280', padding: 20 }}>Loading...</div>
        ) : pengeluaranList.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#6b7280', padding: 20, fontStyle: 'italic' }}>
            Belum ada pengeluaran untuk {filterBulan}.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {pengeluaranList.map((p) => {
              const sc = STATUS_COLORS[p.status] || STATUS_COLORS.draft;
              return (
                <div
                  key={p.id}
                  style={{
                    background: '#FAF9F5',
                    border: '1px solid #e5e7eb',
                    borderRadius: 10,
                    padding: 14,
                  }}
                >
                  {/* Top: nomor + status badge */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8, gap: 8 }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#6b7280' }}>{p.nomor_pengeluaran}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#1B4332', marginTop: 2 }}>
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
                  <div style={{ fontSize: 12, color: '#6b7280', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    <span>📅 {p.tanggal}</span>
                    {p.penerima && <span>👤 {p.penerima}</span>}
                    {p.metode_bayar && <span>💳 {p.metode_bayar}</span>}
                  </div>

                  {p.deskripsi && (
                    <div style={{ fontSize: 13, color: '#374151', marginTop: 6, fontStyle: 'italic' }}>"{p.deskripsi}"</div>
                  )}

                  {p.rejected_reason && (
                    <div style={{ background: '#fee2e2', color: '#991b1b', padding: '6px 10px', borderRadius: 6, marginTop: 8, fontSize: 12 }}>
                      <strong>Ditolak:</strong> {p.rejected_reason}
                    </div>
                  )}

                  {/* Actions */}
                  {p.status === 'draft' && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                      <button
                        onClick={() => handleSubmitForApproval(p.id)}
                        style={{ ...primaryBtnStyle, padding: '8px 14px', fontSize: 13, minHeight: 'auto', width: 'auto', flex: 1 }}
                      >
                        📤 Submit {p.kategori_alias ? '(Rutin)' : '(Non-Rutin)'}
                      </button>
                      <button onClick={() => handleEdit(p)} style={{ ...secondaryBtnStyle }}>
                        ✏ Edit
                      </button>
                      <button onClick={() => handleDeleteDraft(p.id)} style={ghostBtnStyle} title="Hapus">
                        🗑
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
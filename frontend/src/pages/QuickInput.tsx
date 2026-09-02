/**
 * FLIPUS v2.0 M2 — Quick Input dynamic form.
 *
 * Upgrade dari M1 stub:
 * - Multi-item: bisa tambah/hapus baris kategori+nomial
 * - Autocomplete: load kategori list dari backend saat mount
 * - Pilih dari dropdown atau ketik kategori baru (auto-create)
 * - Total auto-compute live
 * - Mobile-first, inline styles, touch target ≥48px
 */
import { useEffect, useState } from 'react';
import { useAuth } from '../lib/auth';
import api from '../lib/api';

interface QuickInputResponse {
  ok: boolean;
  nomor_kuitansi: string;
  total_pemberian: number;
  kategori_baru: string[];
  kategori_existing: string[];
  tanggal_sabat: string;
}

interface KategoriOption {
  id: number;
  nama: string;
  alias: string;
  is_rutin: boolean;
  urutan: number;
}

interface ItemRow {
  id: string;          // local row id (uuid-ish)
  kategoriNama: string;
  nominal: string;     // raw string for rupiah formatting
}

const SABAT_GREEN = '#0F4C3A';
const SABAT_GOLD = '#C9A961';

const wrapStyle: React.CSSProperties = {
  maxWidth: 480,
  margin: '0 auto',
  padding: '16px 16px 32px',
  fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  minHeight: '100vh',
  background: '#f8faf9',
  boxSizing: 'border-box',
};

const cardStyle: React.CSSProperties = {
  background: '#ffffff',
  borderRadius: 12,
  padding: 20,
  marginBottom: 16,
  boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 48,
  padding: '0 12px',
  border: '1px solid #d1d5db',
  borderRadius: 8,
  fontSize: 16,
  boxSizing: 'border-box',
  background: '#ffffff',
  color: '#1f2937',
  outline: 'none',
};

const primaryButtonStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 48,
  background: SABAT_GREEN,
  color: '#ffffff',
  border: 'none',
  borderRadius: 8,
  fontSize: 16,
  fontWeight: 600,
  cursor: 'pointer',
  boxSizing: 'border-box',
};

const secondaryButtonStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 48,
  background: '#ffffff',
  color: SABAT_GREEN,
  border: `2px solid ${SABAT_GREEN}`,
  borderRadius: 8,
  fontSize: 16,
  fontWeight: 600,
  cursor: 'pointer',
  boxSizing: 'border-box',
};

const ghostButtonStyle: React.CSSProperties = {
  minWidth: 48,
  minHeight: 48,
  background: '#fef2f2',
  color: '#dc2626',
  border: '1px solid #fecaca',
  borderRadius: 8,
  fontSize: 18,
  fontWeight: 700,
  cursor: 'pointer',
  flexShrink: 0,
  padding: '0 12px',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 14,
  fontWeight: 600,
  color: '#374151',
  marginBottom: 8,
};

const helpStyle: React.CSSProperties = {
  fontSize: 12,
  color: '#6b7280',
  marginTop: 6,
};

const rowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  alignItems: 'flex-start',
  marginBottom: 12,
};

const colKatStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,  // critical: allow flex child to shrink + input not overflow
};

const colNomStyle: React.CSSProperties = {
  width: 130,
  minWidth: 0,
};

const totalBadgeStyle: React.CSSProperties = {
  background: SABAT_GREEN,
  color: SABAT_GOLD,
  padding: '12px 16px',
  borderRadius: 8,
  fontSize: 18,
  fontWeight: 700,
  textAlign: 'center',
  marginBottom: 12,
};

const formatRupiah = (digits: string): string => {
  if (!digits) return '';
  return new Intl.NumberFormat('id-ID').format(parseInt(digits, 10));
};

const parseRupiah = (formatted: string): number => {
  return parseInt(formatted.replace(/\D/g, ''), 10) || 0;
};

const newRowId = () => `r${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

const QuickInput = () => {
  const { isAuthenticated, role } = useAuth();

  const [kategoriOptions, setKategoriOptions] = useState<KategoriOption[]>([]);
  const [namaPemberi, setNamaPemberi] = useState('');
  const [rows, setRows] = useState<ItemRow[]>([
    { id: newRowId(), kategoriNama: '', nominal: '' },
  ]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<QuickInputResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load kategori list saat mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await api.get<KategoriOption[]>('/kategori/list');
        if (!cancelled) setKategoriOptions(resp.data);
      } catch (err: any) {
        // Silent fail — user bisa tetap ketik manual
        if (import.meta.env.DEV) console.warn('[kategori/list] fail:', err);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Detect PWA standalone
  useEffect(() => {
    const isStandalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      (window.navigator as any).standalone === true;
    if (import.meta.env.DEV && isStandalone) {
      console.log('[PWA] launched as standalone');
    }
  }, []);

  const updateRow = (id: string, patch: Partial<ItemRow>) => {
    setRows(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const addRow = () => {
    setRows([...rows, { id: newRowId(), kategoriNama: '', nominal: '' }]);
  };

  const removeRow = (id: string) => {
    if (rows.length === 1) {
      // Selalu minimal 1 row — clear saja
      setRows([{ id: newRowId(), kategoriNama: '', nominal: '' }]);
    } else {
      setRows(rows.filter((r) => r.id !== id));
    }
  };

  const total = rows.reduce((sum, r) => sum + parseRupiah(r.nominal), 0);
  const validRows = rows.filter(
    (r) => r.kategoriNama.trim() && parseRupiah(r.nominal) > 0
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);

    if (!namaPemberi.trim()) {
      setError('Nama pemberi wajib diisi');
      return;
    }
    if (validRows.length === 0) {
      setError('Minimal 1 item dengan kategori dan nominal > 0');
      return;
    }

    setSubmitting(true);
    try {
      const resp = await api.post<QuickInputResponse>('/kuitansi/quick-input', {
        nama_pemberi: namaPemberi.trim(),
        items: validRows.map((r) => ({
          kategori_nama: r.kategoriNama.trim(),
          nominal: parseRupiah(r.nominal),
        })),
      });
      setResult(resp.data);
      // Reset form
      setNamaPemberi('');
      setRows([{ id: newRowId(), kategoriNama: '', nominal: '' }]);
      // Reload kategori list (mungkin ada yang baru di-create)
      try {
        const refresh = await api.get<KategoriOption[]>('/kategori/list');
        setKategoriOptions(refresh.data);
      } catch (e) { /* silent */ }
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
        err.message ||
        'Gagal menyimpan kuitansi'
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <p style={{ color: '#dc2626' }}>Anda harus login terlebih dahulu.</p>
        </div>
      </div>
    );
  }

  if (role !== 'BENDAHARA') {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <p style={{ color: '#dc2626' }}>
            Quick Input khusus untuk Bendahara. Anda login sebagai {role}.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={wrapStyle}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          marginBottom: 16,
          padding: '8px 0',
        }}
      >
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 8,
            background: SABAT_GREEN,
            color: SABAT_GOLD,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 'bold',
            fontSize: 20,
            marginRight: 12,
          }}
        >
          F
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 18, color: SABAT_GREEN }}>
            Quick Input
          </h1>
          <p style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>
            Input kuitansi jemaat (mobile)
          </p>
        </div>
      </header>

      {result && (
        <div
          style={{
            ...cardStyle,
            background: '#ecfdf5',
            borderLeft: `4px solid ${SABAT_GREEN}`,
          }}
        >
          <p style={{ margin: 0, fontSize: 14, color: '#065f46' }}>
            ✓ Tersimpan: <strong>{result.nomor_kuitansi}</strong>
          </p>
          <p style={{ margin: '8px 0 0', fontSize: 14, color: '#065f46' }}>
            Total: Rp {result.total_pemberian.toLocaleString('id-ID')}
          </p>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: '#065f46' }}>
            Sabat: {result.tanggal_sabat}
          </p>
          {result.kategori_baru.length > 0 && (
            <p
              style={{
                margin: '8px 0 0',
                fontSize: 12,
                color: '#92400e',
                fontStyle: 'italic',
              }}
            >
              + Kategori baru otomatis dibuat: {result.kategori_baru.join(', ')}
            </p>
          )}
        </div>
      )}

      {error && (
        <div
          style={{
            ...cardStyle,
            background: '#fef2f2',
            borderLeft: '4px solid #dc2626',
          }}
        >
          <p style={{ margin: 0, fontSize: 14, color: '#991b1b' }}>
            ⚠ {error}
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit} style={cardStyle}>
        <div style={{ marginBottom: 16 }}>
          <label style={labelStyle}>Nama Pemberi</label>
          <input
            type="text"
            value={namaPemberi}
            onChange={(e) => setNamaPemberi(e.target.value)}
            placeholder="cth: Bpk. Yohanes"
            style={inputStyle}
            autoComplete="off"
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={labelStyle}>
            Item ({validRows.length} valid · {rows.length} baris)
          </label>
          {rows.map((row, idx) => (
            <div key={row.id} style={rowStyle}>
              <div style={colKatStyle}>
                <input
                  type="text"
                  value={row.kategoriNama}
                  onChange={(e) => updateRow(row.id, { kategoriNama: e.target.value })}
                  placeholder={idx === 0 ? "cth: Perpuluhan, PT, Pembangunan..." : "Kategori"}
                  style={inputStyle}
                  list="kategori-suggest"
                  autoComplete="off"
                />
              </div>
              <div style={colNomStyle}>
                <input
                  type="text"
                  inputMode="numeric"
                  value={formatRupiah(row.nominal)}
                  onChange={(e) => updateRow(row.id, { nominal: e.target.value })}
                  placeholder="0"
                  style={{ ...inputStyle, fontSize: 16, fontWeight: 600, textAlign: 'right' }}
                />
              </div>
              <button
                type="button"
                onClick={() => removeRow(row.id)}
                style={ghostButtonStyle}
                aria-label="Hapus item"
              >
                ✕
              </button>
            </div>
          ))}
          <datalist id="kategori-suggest">
            {kategoriOptions.map((k) => (
              <option key={k.id} value={k.nama}>
                {k.is_rutin ? `★ ${k.nama}` : k.nama} ({k.alias})
              </option>
            ))}
          </datalist>
        </div>

        <button
          type="button"
          onClick={addRow}
          style={secondaryButtonStyle}
        >
          + Tambah Item
        </button>

        {total > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={totalBadgeStyle}>
              Total: Rp {total.toLocaleString('id-ID')}
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || validRows.length === 0}
          style={{
            ...primaryButtonStyle,
            opacity: (submitting || validRows.length === 0) ? 0.5 : 1,
          }}
        >
          {submitting ? 'Menyimpan...' : '💾 Simpan Kuitansi'}
        </button>

        <p style={helpStyle}>
          Pilih dari dropdown atau ketik kategori baru. Kategori baru otomatis dibuat dengan alias pintar.
        </p>
      </form>

      <p
        style={{
          textAlign: 'center',
          fontSize: 12,
          color: '#6b7280',
          marginTop: 16,
        }}
      >
        v2.0 M2 · Quick Input mobile PWA
      </p>
    </div>
  );
};

export default QuickInput;

import { useState } from 'react';

/**
 * T43 Redesign: SabatFilterPanel — eye-catching collapse panel untuk filter
 * rentang sabat, dengan inline styles agar tahan PostCSS/Tailwind misconfig.
 *
 * Fitur:
 * - Header bar dengan icon funnel + label dinamis (Sembunyikan/Tampilkan)
 * - 4 mode filter: Sabat Ini / Per Bulan / Range Sabat / Semua
 * - onApply callback saat user klik "Terapkan Filter"
 *
 * Pakai:
 *   <SabatFilterPanel onApply={(filter) => setFilter(filter)} />
 */
export type SabatFilter = {
  mode: 'sabat_ini' | 'bulan' | 'range' | 'all';
  bulan?: string;       // YYYY-MM (untuk mode 'bulan')
  sabat_from?: number;  // untuk mode 'range'
  sabat_to?: number;    // untuk mode 'range'
};

const MODE_OPTIONS = [
  { key: 'sabat_ini', label: 'Sabat Ini', icon: '📅' },
  { key: 'bulan', label: 'Per Bulan', icon: '🗓️' },
  { key: 'range', label: 'Range Sabat', icon: '🔢' },
  { key: 'all', label: 'Semua', icon: '∞' },
] as const;

const primaryGreen = '#1B4332';
const goldAccent = '#B8860B';
const lightCream = '#FAF9F5';
const goldLight = '#fde68a';

export const SabatFilterPanel = ({
  onApply,
  defaultSabat = 1,
  defaultBulan = '',
  sabatKeSekarang = 34,
}: {
  onApply: (filter: SabatFilter) => void;
  defaultSabat?: number;
  defaultBulan?: string;
  sabatKeSekarang?: number;
}) => {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'sabat_ini' | 'bulan' | 'range' | 'all'>('sabat_ini');
  const [bulan, setBulan] = useState(defaultBulan);
  const [sabatFrom, setSabatFrom] = useState(defaultSabat);
  const [sabatTo, setSabatTo] = useState(sabatKeSekarang);

  const handleApply = () => {
    const filter: SabatFilter = { mode };
    if (mode === 'bulan' && bulan) filter.bulan = bulan;
    if (mode === 'range') {
      filter.sabat_from = Math.min(sabatFrom, sabatTo);
      filter.sabat_to = Math.max(sabatFrom, sabatTo);
    }
    onApply(filter);
    setOpen(false);
  };

  const handleReset = () => {
    setMode('sabat_ini');
    setBulan(defaultBulan);
    setSabatFrom(defaultSabat);
    setSabatTo(sabatKeSekarang);
    onApply({ mode: 'sabat_ini' });
    setOpen(false);
  };

  const summary =
    mode === 'sabat_ini' ? 'Sabat berjalan' :
    mode === 'bulan' && bulan ? `Bulan ${bulan}` :
    mode === 'range' ? `Sabat ${sabatFrom}–${sabatTo}` :
    mode === 'all' ? 'Semua data' :
    'Sabat berjalan';

  return (
    <div style={{
      background: 'white',
      borderRadius: 16,
      boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      border: '1px solid #f0f0eb',
      overflow: 'hidden',
    }}>
      {/* ===== Header / Toggle button ===== */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: '100%',
          padding: '14px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: open
            ? `linear-gradient(135deg, ${primaryGreen} 0%, #0d2418 100%)`
            : lightCream,
          color: open ? 'white' : primaryGreen,
          border: 'none',
          cursor: 'pointer',
          transition: 'all 0.2s',
          fontFamily: 'inherit',
        }}
        onMouseEnter={(e) => {
          if (!open) (e.currentTarget as HTMLButtonElement).style.background = '#f5f3ea';
        }}
        onMouseLeave={(e) => {
          if (!open) (e.currentTarget as HTMLButtonElement).style.background = lightCream;
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32,
            height: 32,
            borderRadius: 10,
            background: open ? 'rgba(255,255,255,0.15)' : 'white',
            border: open ? '1px solid rgba(255,255,255,0.2)' : `1px solid #e5e7eb`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16,
            transition: 'transform 0.2s',
            transform: open ? 'rotate(0deg)' : 'rotate(0deg)',
          }}>
            🔍
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
            <span style={{ fontWeight: 600, fontSize: 13, letterSpacing: '0.01em' }}>
              {open ? 'Sembunyikan Filter' : 'Tampilkan Filter'}
            </span>
            <span style={{
              fontSize: 11,
              opacity: open ? 0.7 : 0.6,
              color: open ? 'white' : '#6b7280',
              marginTop: 1,
            }}>
              Saat ini: <strong style={{ color: open ? goldLight : goldAccent }}>{summary}</strong>
            </span>
          </div>
        </div>
        <div style={{
          width: 28,
          height: 28,
          borderRadius: 8,
          background: open ? 'rgba(255,255,255,0.15)' : 'white',
          border: open ? '1px solid rgba(255,255,255,0.2)' : `1px solid #e5e7eb`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
          transition: 'transform 0.25s',
          fontSize: 14,
        }}>
          ▶
        </div>
      </button>

      {/* ===== Expandable body ===== */}
      {open && (
        <div style={{
          padding: '20px 24px 24px 24px',
          borderTop: `2px solid ${goldAccent}`,
          background: `linear-gradient(180deg, ${lightCream} 0%, white 100%)`,
        }}>
          {/* Mode selector */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 8,
            marginBottom: 18,
          }}>
            {MODE_OPTIONS.map((opt) => {
              const active = mode === opt.key;
              return (
                <button
                  key={opt.key}
                  onClick={() => setMode(opt.key)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: 12,
                    fontSize: 13,
                    fontWeight: 600,
                    border: active ? `2px solid ${goldAccent}` : '2px solid #e5e7eb',
                    background: active ? goldAccent : 'white',
                    color: active ? 'white' : '#374151',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                    transition: 'all 0.15s',
                    boxShadow: active ? '0 2px 4px rgba(184, 134, 11, 0.25)' : 'none',
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      (e.currentTarget as HTMLButtonElement).style.borderColor = goldAccent;
                      (e.currentTarget as HTMLButtonElement).style.background = '#fef3c7';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      (e.currentTarget as HTMLButtonElement).style.borderColor = '#e5e7eb';
                      (e.currentTarget as HTMLButtonElement).style.background = 'white';
                    }
                  }}
                >
                  <span style={{ fontSize: 16 }}>{opt.icon}</span>
                  <span>{opt.label}</span>
                </button>
              );
            })}
          </div>

          {/* Per-mode inputs */}
          {mode === 'bulan' && (
            <div style={{
              padding: 16,
              background: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              marginBottom: 16,
            }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                📆 Pilih Bulan
              </label>
              <input
                type="month"
                value={bulan}
                onChange={(e) => setBulan(e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  border: `2px solid ${bulan ? goldAccent : '#e5e7eb'}`,
                  borderRadius: 10,
                  fontSize: 14,
                  outline: 'none',
                  background: bulan ? '#fef3c7' : 'white',
                  boxSizing: 'border-box',
                  fontFamily: 'inherit',
                }}
              />
            </div>
          )}

          {mode === 'range' && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 12,
              padding: 16,
              background: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              marginBottom: 16,
            }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  ⬅️ Dari Sabat ke-
                </label>
                <input
                  type="number"
                  min={1}
                  max={54}
                  value={sabatFrom}
                  onChange={(e) => setSabatFrom(parseInt(e.target.value) || 1)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    border: `2px solid #e5e7eb`,
                    borderRadius: 10,
                    fontSize: 14,
                    outline: 'none',
                    background: 'white',
                    boxSizing: 'border-box',
                    fontFamily: 'inherit',
                  }}
                  onFocus={(e) => (e.currentTarget as HTMLInputElement).style.borderColor = goldAccent}
                  onBlur={(e) => (e.currentTarget as HTMLInputElement).style.borderColor = '#e5e7eb'}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  ➡️ Sampai Sabat ke-
                </label>
                <input
                  type="number"
                  min={1}
                  max={54}
                  value={sabatTo}
                  onChange={(e) => setSabatTo(parseInt(e.target.value) || sabatKeSekarang)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    border: `2px solid #e5e7eb`,
                    borderRadius: 10,
                    fontSize: 14,
                    outline: 'none',
                    background: 'white',
                    boxSizing: 'border-box',
                    fontFamily: 'inherit',
                  }}
                  onFocus={(e) => (e.currentTarget as HTMLInputElement).style.borderColor = goldAccent}
                  onBlur={(e) => (e.currentTarget as HTMLInputElement).style.borderColor = '#e5e7eb'}
                />
              </div>
            </div>
          )}

          {mode === 'sabat_ini' && (
            <div style={{
              padding: 14,
              background: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              marginBottom: 16,
              fontSize: 13,
              color: '#374151',
              lineHeight: 1.6,
            }}>
              <p style={{ margin: 0 }}>
                📌 Menampilkan data untuk <strong style={{ color: primaryGreen }}>sabat berjalan (ke-{sabatKeSekarang})</strong>.
                Klik <strong style={{ color: goldAccent }}>Terapkan</strong> untuk konfirmasi.
              </p>
            </div>
          )}

          {mode === 'all' && (
            <div style={{
              padding: 14,
              background: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              marginBottom: 16,
              fontSize: 13,
              color: '#374151',
              lineHeight: 1.6,
            }}>
              <p style={{ margin: 0 }}>
                📊 Menampilkan <strong style={{ color: primaryGreen }}>semua data</strong> yang tersedia
                (dari sabat pertama sampai sekarang).
              </p>
            </div>
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: 10, paddingTop: 4 }}>
            <button
              onClick={handleApply}
              style={{
                flex: 1,
                padding: '12px 20px',
                background: `linear-gradient(135deg, ${primaryGreen} 0%, #0d2418 100%)`,
                color: 'white',
                border: 'none',
                borderRadius: 12,
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
                boxShadow: '0 2px 6px rgba(27, 67, 50, 0.25)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                fontFamily: 'inherit',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 12px rgba(27, 67, 50, 0.35)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 2px 6px rgba(27, 67, 50, 0.25)';
              }}
            >
              <span>✓</span>
              <span>Terapkan Filter</span>
            </button>
            <button
              onClick={handleReset}
              style={{
                padding: '12px 20px',
                background: 'white',
                color: '#6b7280',
                border: '2px solid #e5e7eb',
                borderRadius: 12,
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                fontFamily: 'inherit',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = '#d1d5db';
                (e.currentTarget as HTMLButtonElement).style.background = '#f9fafb';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = '#e5e7eb';
                (e.currentTarget as HTMLButtonElement).style.background = 'white';
              }}
            >
              <span>↻</span>
              <span>Reset</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

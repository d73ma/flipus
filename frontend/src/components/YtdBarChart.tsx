import { useEffect, useState } from 'react';
import api from '../lib/api';
import { CountUp } from './Chart';

/**
 * T36 Redesign: YtdBarChart — 6 batang berdiri sendiri, kumulatif YTD.
 *
 * Pakai inline styles untuk layout critical (supaya tidak tergantung
 * Tailwind utility classes — bullet-proof terhadap PostCSS config issues).
 *
 * Endpoint: GET /v1/agregat/ytd
 * Return 6 angka: X, PT, Khusus, Misi X, Misi PT, Jemaat
 */
interface YtdResponse {
  scope: string;
  tahun: number;
  sabat_ke: number;
  total_perpuluhan: number;
  total_persembahan_terpadu: number;
  total_persembahan_khusus: number;
  total_porsi_misi_x: number;
  total_porsi_misi_pt: number;
  total_porsi_jemaat: number;
}

interface BarDef {
  label: string;
  shortLabel: string;
  value: number;
  color: string;
  group: 'penerimaan' | 'penyaluran';
}

const fmt = (n: number) =>
  'Rp ' + (n || 0).toLocaleString('id-ID');

const fmtCompact = (n: number) => {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'jt';
  if (n >= 1_000) return Math.round(n / 1_000) + 'k';
  return String(n);
};

export const YtdBarChart = ({
  scope = '',
  height = 220,
}: {
  scope?: string;
  height?: number;
}) => {
  const [data, setData] = useState<YtdResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchYtd = async () => {
      try {
        const r = await api.get<YtdResponse>('/v1/agregat/ytd');
        setData(r.data);
      } catch (e) {
        // silent
      } finally {
        setLoading(false);
      }
    };
    fetchYtd();
  }, []);

  const wrapperStyle: React.CSSProperties = {
    background: 'linear-gradient(135deg, #1B4332 0%, #152d22 100%)',
    color: 'white',
    borderRadius: 24,
    padding: '24px 28px',
    position: 'relative',
    overflow: 'hidden',
  };

  if (loading || !data) {
    return (
      <section style={wrapperStyle}>
        <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.5)', fontSize: 13 }}>
          Memuat grafik YTD…
        </div>
      </section>
    );
  }

  const bars: BarDef[] = [
    { label: 'Total Perpuluhan', shortLabel: 'X', value: data.total_perpuluhan, color: '#B8860B', group: 'penerimaan' },
    { label: 'Total Persembahan Terpadu', shortLabel: 'PT', value: data.total_persembahan_terpadu, color: '#a07408', group: 'penerimaan' },
    { label: 'Total Persembahan Khusus', shortLabel: 'Khusus', value: data.total_persembahan_khusus, color: '#d4a73e', group: 'penerimaan' },
    { label: 'Porsi Misi (X)', shortLabel: 'Misi X', value: data.total_porsi_misi_x, color: '#34a87a', group: 'penyaluran' },
    { label: 'Porsi Misi (PT)', shortLabel: 'Misi PT', value: data.total_porsi_misi_pt, color: '#5fbf94', group: 'penyaluran' },
    { label: 'Porsi Jemaat', shortLabel: 'Jemaat', value: data.total_porsi_jemaat, color: '#5fbcde', group: 'penyaluran' },
  ];

  const max = Math.max(...bars.map((b) => b.value), 1);
  const maxBarHeight = height - 40;
  const grandTotal = data.total_perpuluhan + data.total_persembahan_terpadu + data.total_persembahan_khusus;

  return (
    <section style={wrapperStyle}>
      {/* Decorative side lines */}
      <div aria-hidden style={{ position: 'absolute', inset: 0, pointerEvents: 'none', opacity: 0.15 }}>
        <div style={{ position: 'absolute', left: '5%', top: 0, bottom: 0, width: 1, background: 'linear-gradient(180deg, transparent, #B8860B, transparent)' }} />
        <div style={{ position: 'absolute', right: '5%', top: 0, bottom: 0, width: 1, background: 'linear-gradient(180deg, transparent, #B8860B, transparent)' }} />
      </div>

      <div style={{ position: 'relative' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <p style={{ fontSize: 10, opacity: 0.7, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 4 }}>
              Kumulatif YTD {scope && `· ${scope}`}
            </p>
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, color: '#B8860B', margin: 0, fontWeight: 700 }}>
              Grafik Batang Tahunan {data.tahun}
            </h3>
            <p style={{ fontSize: 11, opacity: 0.7, marginTop: 4 }}>
              Dari Sabat 1 sampai Sabat ke-{data.sabat_ke}
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <p style={{ fontSize: 10, opacity: 0.7, marginBottom: 4 }}>Total Penerimaan</p>
            <p style={{ fontFamily: 'monospace', fontSize: 18, fontWeight: 700, margin: 0 }}>
              <CountUp value={grandTotal} prefix="Rp " />
            </p>
          </div>
        </div>

        {/* Bars */}
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 10, marginTop: 24, height }}>
          {bars.map((bar, idx) => {
            const barHeight = Math.max((bar.value / max) * maxBarHeight, bar.value > 0 ? 6 : 0);
            return (
              <div
                key={idx}
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'flex-end',
                  position: 'relative',
                  height: '100%',
                  cursor: 'default',
                }}
                title={`${bar.label}: ${fmt(bar.value)}`}
              >
                {/* Value label on top */}
                {bar.value > 0 && (
                  <div style={{
                    position: 'absolute',
                    top: -16,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    fontSize: 9,
                    fontFamily: 'monospace',
                    opacity: 0.85,
                    whiteSpace: 'nowrap',
                    color: '#fff',
                  }}>
                    {fmtCompact(bar.value)}
                  </div>
                )}
                <div
                  style={{
                    width: '70%',
                    height: barHeight,
                    background: `linear-gradient(180deg, ${bar.color}, ${bar.color}dd)`,
                    borderRadius: '6px 6px 0 0',
                    transition: 'height 0.7s ease-out',
                    boxShadow: `0 -2px 8px ${bar.color}44`,
                  }}
                />
              </div>
            );
          })}
        </div>

        {/* X-axis labels */}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: 10 }}>
          {bars.map((bar, idx) => (
            <div key={idx} style={{
              flex: 1,
              textAlign: 'center',
              fontSize: 10,
              color: 'rgba(255,255,255,0.7)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }} title={bar.label}>
              {bar.shortLabel}
            </div>
          ))}
        </div>

        {/* Legend */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: 12,
          marginTop: 24,
          paddingTop: 16,
          borderTop: '1px solid rgba(255,255,255,0.12)',
        }}>
          {bars.map((bar, idx) => (
            <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 12,
                height: 12,
                borderRadius: 3,
                background: bar.color,
                flexShrink: 0,
              }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{
                  fontSize: 9,
                  opacity: 0.7,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  margin: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {bar.group === 'penerimaan' ? 'Penerimaan' : 'Penyaluran'}
                </p>
                <p style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 700, margin: '2px 0 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <CountUp value={bar.value} prefix="Rp " />
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

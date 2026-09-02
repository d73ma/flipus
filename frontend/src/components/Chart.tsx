import { useEffect, useState, useRef } from 'react';

// ===== CountUp component =====
export const CountUp = ({
  value,
  duration = 1200,
  prefix = '',
  suffix = '',
  className = '',
}: {
  value: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}) => {
  const [display, setDisplay] = useState(0);
  const startRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    startRef.current = null;
    const animate = (ts: number) => {
      if (startRef.current === null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.floor(value * eased));
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        setDisplay(value);
      }
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [value, duration]);

  return (
    <span className={className}>
      {prefix}
      {display.toLocaleString('id-ID')}
      {suffix}
    </span>
  );
};

// ===== MiniBarChart component =====
interface ChartItem {
  label: string;
  x: number;
  pt: number;
  khusus: number;
  total: number;
}

export const MiniBarChart = ({
  items,
  height = 140,
}: {
  items: ChartItem[];
  height?: number;
}) => {
  if (!items.length) {
    return (
      <div className="text-center text-gray-400 py-12 text-sm">
        Belum ada data untuk grafik
      </div>
    );
  }

  const max = Math.max(...items.map((i) => i.total), 1);
  const maxBarHeight = height - 40; // leave room for labels

  return (
    <div className="w-full">
      <div className="flex items-end justify-between gap-1" style={{ height }}>
        {items.map((item, idx) => {
          const totalHeight = (item.total / max) * maxBarHeight;
          const xHeight = item.total > 0 ? (item.x / item.total) * totalHeight : 0;
          const ptHeight = item.total > 0 ? (item.pt / item.total) * totalHeight : 0;
          const khHeight = totalHeight - xHeight - ptHeight;
          return (
            <div
              key={idx}
              className="flex-1 flex flex-col items-center justify-end group relative"
              style={{ height: '100%' }}
            >
              {/* Tooltip */}
              <div className="absolute bottom-full mb-1 hidden group-hover:block bg-sabbath-dark text-white text-[10px] rounded px-2 py-1 whitespace-nowrap z-10 pointer-events-none">
                {item.label}: Rp {item.total.toLocaleString('id-ID')}
                <br />
                <span className="text-[9px] opacity-80">
                  X {item.x.toLocaleString('id-ID')} · PT {item.pt.toLocaleString('id-ID')}
                  {item.khusus > 0 && ` · Kh ${item.khusus.toLocaleString('id-ID')}`}
                </span>
              </div>
              <div
                className="w-full rounded-t overflow-hidden flex flex-col justify-end"
                style={{ height: totalHeight, minHeight: 2 }}
              >
                {khHeight > 0 && (
                  <div className="bg-sabbath-gold" style={{ height: khHeight }} />
                )}
                {ptHeight > 0 && (
                  <div className="bg-sabbath-gold/60" style={{ height: ptHeight }} />
                )}
                {xHeight > 0 && (
                  <div className="bg-sabbath-dark" style={{ height: xHeight }} />
                )}
              </div>
            </div>
          );
        })}
      </div>
      {/* X-axis labels */}
      <div className="flex justify-between mt-2 text-[10px] text-gray-500">
        {items.map((item, idx) => (
          <div key={idx} className="flex-1 text-center truncate">
            {item.label}
          </div>
        ))}
      </div>
    </div>
  );
};

// ===== Hook: fetch chart data =====
export const useChartMingguan = (nWeeks: number = 8) => {
  const [data, setData] = useState<ChartItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [totals, setTotals] = useState({ x: 0, pt: 0, khusus: 0, all: 0 });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const { default: api } = await import('../lib/api');
        const r = await api.get(`/v1/agregat/chart/mingguan`, { params: { n_weeks: nWeeks } });
        setData(r.data.items || []);
        setTotals({
          x: r.data.total_x || 0,
          pt: r.data.total_pt || 0,
          khusus: r.data.total_khusus || 0,
          all: r.data.total_all || 0,
        });
      } catch (e) {
        // silent
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [nWeeks]);

  return { data, totals, loading };
};

// ===== T34 fully: Reusable hero section (chart + KPI) =====
export const WeeklyChartSection = ({
  title = 'Persembahan Jemaat',
  nWeeks = 8,
  scopeLabel,
}: {
  title?: string;
  nWeeks?: number;
  scopeLabel?: string;
}) => {
  const { data, totals, loading } = useChartMingguan(nWeeks);

  return (
    <section className="bg-gradient-to-br from-sabbath-dark to-sabbath-dark/95 text-white rounded-3xl p-6 md:p-8 overflow-hidden relative">
      <div className="absolute inset-0 opacity-10 pointer-events-none" aria-hidden>
        <div className="absolute left-[5%] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-sabbath-gold to-transparent" />
        <div className="absolute right-[5%] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-sabbath-gold to-transparent" />
      </div>
      <div className="relative">
        <div className="flex items-end justify-between mb-4">
          <div>
            <p className="text-xs opacity-70 tracking-[0.2em] uppercase mb-1">
              {nWeeks} Sabat Terakhir{scopeLabel ? ` · ${scopeLabel}` : ''}
            </p>
            <h3 className="font-display text-2xl text-sabbath-gold">{title}</h3>
          </div>
          <div className="text-right">
            <p className="text-xs opacity-70 mb-1">Total {nWeeks} minggu</p>
            <p className="font-mono text-2xl md:text-3xl font-bold">
              <CountUp value={totals.all} prefix="Rp " />
            </p>
          </div>
        </div>
        {loading ? (
          <div className="h-[140px] flex items-center justify-center text-white/40 text-sm">
            Memuat grafik…
          </div>
        ) : (
          <MiniBarChart items={data} height={140} />
        )}
        <div className="grid grid-cols-3 gap-4 mt-6 pt-5 border-t border-white/10">
          <div>
            <p className="text-xs opacity-70 uppercase tracking-wider">Perpuluhan (X)</p>
            <p className="font-mono text-lg font-bold text-sabbath-gold mt-1">
              <CountUp value={totals.x} prefix="Rp " />
            </p>
          </div>
          <div>
            <p className="text-xs opacity-70 uppercase tracking-wider">Persembahan (PT)</p>
            <p className="font-mono text-lg font-bold text-sabbath-gold/80 mt-1">
              <CountUp value={totals.pt} prefix="Rp " />
            </p>
          </div>
          <div>
            <p className="text-xs opacity-70 uppercase tracking-wider">Khusus</p>
            <p className="font-mono text-lg font-bold text-white/80 mt-1">
              <CountUp value={totals.khusus} prefix="Rp " />
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};
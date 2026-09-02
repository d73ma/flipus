import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../lib/api';
import { useAuth } from '../lib/auth';

interface KuitansiItem {
  id: number;
  nomor_kuitansi: string;
  id_rekap_mingguan: string;
  tanggal_sabat: string;
  nama_umat: string | null;
  nomor_whatsapp: string | null;
  perpuluhan_x_angka: number;
  pt_angka: number;
  khusus_angka: number;
  total_pemberian_angka: number;
  porsi_kantor_misi: number;
  porsi_kas_jemaat: number;
  tenant_id: number;
  nama_jemaat: string | null;
}

interface SearchResult {
  items: KuitansiItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

interface FilterMeta {
  total_kuitansi: number;
  total_x: number;
  total_pt: number;
  total_khusus: number;
  total_pemberian: number;
  date_range_from: string | null;
  date_range_to: string | null;
}

interface KuitansiSearchPanelProps {
  /** Scope label untuk display — "Semua Jemaat" / "Misi Anda" / "Jemaat Anda" */
  scopeLabel?: string;
  /** Apakah user boleh lihat nama_jemaat di tabel (untuk ADMIN_UNI/AUDITOR_MISI) */
  showJemaatColumn?: boolean;
  /** Default per_page — default 50 */
  defaultPerPage?: number;
}

const TIPE_OPTIONS = [
  { value: '', label: 'Semua tipe' },
  { value: 'x', label: 'Perpuluhan X saja' },
  { value: 'pt', label: 'Persembahan PT saja' },
  { value: 'khusus', label: 'Persembahan Khusus saja' },
  { value: 'x_pt', label: 'X atau PT' },
  { value: 'all_has_value', label: 'Yang ada nilainya' },
  { value: 'kosong', label: 'Nilai 0 (kosong)' },
];

const SORT_OPTIONS = [
  { value: 'tanggal_sabat', label: 'Tanggal Sabat' },
  { value: 'nominal', label: 'Nominal' },
  { value: 'created_at', label: 'Tanggal Input' },
];

export const KuitansiSearchPanel = ({
  scopeLabel = 'Data Anda',
  showJemaatColumn = false,
  defaultPerPage = 50,
}: KuitansiSearchPanelProps) => {
  // T89 (Jerry, 2026-08-23): PRIVASI FATAL — nama_umat & nomor_whatsapp
  // hanya boleh tampil untuk BENDAHARA / PENDETA.
  // Role lain (AUDITOR_MISI, ADMIN_UNI, KETUA_KEUANGAN) lihat masked data.
  const { role } = useAuth();
  const canSeePii = role === 'BENDAHARA' || role === 'PENDETA';

  // Filter state
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [tipe, setTipe] = useState('');
  const [nominalMin, setNominalMin] = useState('');
  const [nominalMax, setNominalMax] = useState('');
  const [nama, setNama] = useState('');
  const [idRekap, setIdRekap] = useState('');
  const [sortBy, setSortBy] = useState('tanggal_sabat');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(defaultPerPage);

  // Data
  const [data, setData] = useState<SearchResult | null>(null);
  const [meta, setMeta] = useState<FilterMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  // Debounce untuk search
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const buildParams = useCallback(() => {
    const params: Record<string, string | number> = {
      page,
      per_page: perPage,
      sort_by: sortBy,
      sort_order: sortOrder,
    };
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    if (tipe) params.tipe = tipe;
    if (nominalMin) params.nominal_min = parseInt(nominalMin, 10);
    if (nominalMax) params.nominal_max = parseInt(nominalMax, 10);
    if (nama.trim()) params.nama = nama.trim();
    if (idRekap.trim()) params.id_rekap = idRekap.trim();
    return params;
  }, [page, perPage, sortBy, sortOrder, dateFrom, dateTo, tipe, nominalMin, nominalMax, nama, idRekap]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = buildParams();
      const resp = await api.get<SearchResult>('/v1/kuitansi/search', { params });
      setData(resp.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal mencari data');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  const fetchMeta = useCallback(async () => {
    try {
      const resp = await api.get<FilterMeta>('/v1/kuitansi/filter-meta');
      setMeta(resp.data);
    } catch (err) {
      // silent
    }
  }, []);

  // Debounced fetch (untuk nama search)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchData();
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [fetchData]);

  // Meta fetch on mount
  useEffect(() => {
    fetchMeta();
  }, [fetchMeta]);

  const handleReset = () => {
    setDateFrom('');
    setDateTo('');
    setTipe('');
    setNominalMin('');
    setNominalMax('');
    setNama('');
    setIdRekap('');
    setSortBy('tanggal_sabat');
    setSortOrder('desc');
    setPage(1);
  };

  const handleExport = async (format: 'csv' | 'xlsx' | 'pdf') => {
    try {
      const params = buildParams();
      params.format = format;
      const resp = await api.get('/v1/kuitansi/export', {
        params,
        responseType: 'blob',
      });
      // Trigger download
      const url = window.URL.createObjectURL(new Blob([resp.data]));
      const link = document.createElement('a');
      link.href = url;
      const ext = format === 'csv' ? 'csv' : (format === 'xlsx' ? 'xlsx' : 'pdf');
      link.setAttribute('download', `kuitansi_${new Date().toISOString().slice(0, 10)}.${ext}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(err.response?.data?.detail || `Gagal export ${format.toUpperCase()}`);
    }
  };

  const formatRupiah = (n: number) => `Rp ${n.toLocaleString('id-ID')}`;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100 bg-sabbath-light/30">
        <div className="flex justify-between items-center mb-3">
          <div>
            <h3 className="text-xl font-playfair text-sabbath-dark">Pencarian Kuitansi</h3>
            <p className="text-xs text-gray-500 mt-0.5">Scope: {scopeLabel}</p>
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium border border-gray-300 bg-white text-gray-700 rounded-xl hover:bg-sabbath-light hover:border-sabbath-gold transition-all duration-150"
          >
            <span className="text-sm">⚙</span>
            {showFilters ? 'Sembunyikan Filter' : 'Tampilkan Filter'}
          </button>
        </div>

        {/* Quick search bar — T89: sembunyikan search by nama untuk non-BENDAHARA/PENDETA */}
        <div className="flex gap-2">
          {canSeePii ? (
            <input
              type="text"
              value={nama}
              onChange={(e) => setNama(e.target.value)}
              placeholder="Cari nama umat..."
              className="flex-1 px-3.5 py-2 text-sm border border-gray-300 bg-white rounded-xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent transition-all"
            />
          ) : (
            <div className="flex-1 px-3.5 py-2 border border-gray-200 rounded-xl bg-gray-50 text-xs text-gray-500 italic flex items-center gap-2">
              <span>🔒</span>
              <span>Pencarian nama hanya tersedia untuk Bendahara &amp; Pendeta (privasi)</span>
            </div>
          )}
          <button
            onClick={() => { setPage(1); fetchData(); }}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-5 py-2 text-sm font-medium bg-sabbath-green text-white rounded-xl hover:bg-sabbath-dark transition-all duration-150 disabled:opacity-50 shadow-sm"
          >
            {loading ? '⏳ Mencari...' : '🔍 Cari'}
          </button>
        </div>

        {/* Filter panel */}
        {showFilters && (
          <div className="bg-white border border-gray-200 p-4 rounded-xl mt-3 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Dari tanggal</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Sampai tanggal</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Tipe</label>
                <select
                  value={tipe}
                  onChange={(e) => setTipe(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent"
                >
                  {TIPE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Nominal min (Rp)</label>
                <input
                  type="number"
                  value={nominalMin}
                  onChange={(e) => setNominalMin(e.target.value)}
                  placeholder="0"
                  min="0"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Nominal max (Rp)</label>
                <input
                  type="number"
                  value={nominalMax}
                  onChange={(e) => setNominalMax(e.target.value)}
                  placeholder="999999999"
                  min="0"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">ID Rekap Mingguan</label>
                <input
                  type="text"
                  value={idRekap}
                  onChange={(e) => setIdRekap(e.target.value)}
                  placeholder="FLIPUS-XXX-XXX-001"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Sort by</label>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent"
                >
                  {SORT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Urutan</label>
                <select
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-sabbath-gold focus:border-transparent"
                >
                  <option value="desc">Descending</option>
                  <option value="asc">Ascending</option>
                </select>
              </div>
              <div className="flex items-end">
                <button
                  onClick={handleReset}
                  className="w-full px-3 py-2 border border-gray-300 bg-white text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
                >
                  Reset Filter
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Meta + Export */}
        <div className="flex justify-between items-center mt-3 pt-3 border-t border-gray-100">
          <div className="text-xs text-gray-500">
            {meta && (
              <>
                <span className="font-medium text-gray-700">{meta.total_kuitansi.toLocaleString()}</span> kuitansi
                {' '}· Σ <span className="font-medium text-gray-700 tabular-nums">{formatRupiah(meta.total_pemberian)}</span>
                {meta.date_range_from && meta.date_range_to && (
                  <> · <span className="text-gray-400">{meta.date_range_from}</span> s/d <span className="text-gray-400">{meta.date_range_to}</span></>
                )}
              </>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleExport('csv')}
              disabled={loading || !data?.items.length}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium border border-sabbath-green text-sabbath-green bg-white rounded-lg hover:bg-sabbath-green hover:text-white transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              📄 CSV
            </button>
            <button
              onClick={() => handleExport('xlsx')}
              disabled={loading || !data?.items.length}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium border border-sabbath-green text-sabbath-green bg-white rounded-lg hover:bg-sabbath-green hover:text-white transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              📊 Excel
            </button>
            <button
              onClick={() => handleExport('pdf')}
              disabled={loading || !data?.items.length}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium border border-sabbath-gold text-sabbath-gold bg-white rounded-lg hover:bg-sabbath-gold hover:text-white transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
              title="Download PDF (T73) — backup/archive list kuitansi dengan branding FLIPUS"
            >
              📑 PDF
            </button>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="m-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">
          {error}
        </div>
      )}

      {/* Results */}
      {data && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-2.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">No. Kuitansi</th>
                  <th className="px-3 py-2.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Tanggal</th>
                  {showJemaatColumn && (
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Jemaat</th>
                  )}
                  {/* T89: Sembunyikan kolom Nama Umat untuk role selain BENDAHARA/PENDETA. */}
                  {canSeePii && (
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Nama Umat</th>
                  )}
                  <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">X</th>
                  <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">PT</th>
                  <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Khusus</th>
                  <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Total</th>
                  <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Porsi Misi</th>
                  <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Porsi Jemaat</th>
                  <th className="px-3 py-2.5 text-center text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.items.map((k) => (
                  <tr key={k.id} className="hover:bg-sabbath-light/40 transition-colors">
                    <td className="px-3 py-2.5 font-mono text-[11px] text-gray-700 whitespace-nowrap">{k.nomor_kuitansi}</td>
                    <td className="px-3 py-2.5 text-[11px] text-gray-600 whitespace-nowrap">{k.tanggal_sabat}</td>
                    {showJemaatColumn && (
                      <td className="px-3 py-2.5 text-xs text-gray-700 whitespace-nowrap">{k.nama_jemaat || '-'}</td>
                    )}
                    {/* T89: Hanya render cell Nama Umat untuk BENDAHARA/PENDETA. */}
                    {canSeePii && (
                      <td className="px-3 py-2.5 text-xs text-gray-800 whitespace-nowrap">{k.nama_umat || '-'}</td>
                    )}
                    <td className="px-3 py-2.5 text-right text-[11px] tabular-nums text-gray-700 whitespace-nowrap">{k.perpuluhan_x_angka > 0 ? formatRupiah(k.perpuluhan_x_angka) : <span className="text-gray-300">—</span>}</td>
                    <td className="px-3 py-2.5 text-right text-[11px] tabular-nums text-gray-700 whitespace-nowrap">{k.pt_angka > 0 ? formatRupiah(k.pt_angka) : <span className="text-gray-300">—</span>}</td>
                    <td className="px-3 py-2.5 text-right text-[11px] tabular-nums text-gray-700 whitespace-nowrap">{k.khusus_angka > 0 ? formatRupiah(k.khusus_angka) : <span className="text-gray-300">—</span>}</td>
                    <td className="px-3 py-2.5 text-right text-xs font-semibold tabular-nums text-sabbath-dark whitespace-nowrap">{formatRupiah(k.total_pemberian_angka)}</td>
                    <td className="px-3 py-2.5 text-right text-xs font-semibold tabular-nums text-sabbath-green whitespace-nowrap">{formatRupiah(k.porsi_kantor_misi)}</td>
                    <td className="px-3 py-2.5 text-right text-xs font-semibold tabular-nums text-sabbath-gold whitespace-nowrap">{formatRupiah(k.porsi_kas_jemaat)}</td>
                    <td className="px-3 py-2.5 text-center whitespace-nowrap">
                      <button
                        onClick={() => window.open(`/api/v1/kuitansi/${k.id}/pdf`, '_blank')}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-md border border-sabbath-gold/60 text-sabbath-gold hover:bg-sabbath-gold hover:text-white transition-colors"
                        title="Download PDF kuitansi ini"
                      >
                        📄 PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data.total_pages > 1 && (
            <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/40 flex justify-between items-center">
              <div className="text-xs text-gray-600">
                Halaman <span className="font-medium text-gray-800">{data.page}</span> dari <span className="font-medium text-gray-800">{data.total_pages}</span> · <span className="text-gray-500">{data.total} total</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1.5 border border-gray-300 bg-white rounded-lg text-xs font-medium text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
                >
                  ← Prev
                </button>
                <select
                  value={perPage}
                  onChange={(e) => { setPerPage(parseInt(e.target.value, 10)); setPage(1); }}
                  className="px-2 py-1.5 border border-gray-300 bg-white rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                >
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                  <option value={250}>250 / page</option>
                </select>
                <button
                  onClick={() => setPage(Math.min(data.total_pages, page + 1))}
                  disabled={page >= data.total_pages}
                  className="px-3 py-1.5 border border-gray-300 bg-white rounded-lg text-xs font-medium text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
                >
                  Next →
                </button>
              </div>
            </div>
          )}

          {!data.items.length && !loading && (
            <div className="p-10 text-center text-sm text-gray-400">
              Tidak ada kuitansi cocok dengan filter saat ini
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default KuitansiSearchPanel;

import { } from 'react';

interface MingguanItem {
  id_rekap_mingguan: string;
  tanggal_sabat: string;
  jumlah_kuitansi: number;
  total_x: number;
  total_pt: number;
  total_khusus: number;
  total_semua: number;
  porsi_kantor_misi: number;
  porsi_kas_jemaat: number;
}

interface AgregatTableProps {
  mingguItems: MingguanItem[];
  bulan: string;
  onBulanChange: (val: string) => void;
  onRefresh: () => void;
  loading: boolean;
}

/**
 * Reusable table for per-week aggregate data.
 * Dipakai oleh PendetaDashboard, KetuaDashboard, AuditorDashboard, AdminDashboard.
 */
const AgregatTable = ({
  mingguItems, bulan, onBulanChange, onRefresh, loading,
}: AgregatTableProps) => {
  return (
    <div className="bg-white rounded-3xl shadow-sm">
      <div className="p-6 border-b border-gray-100">
        <div className="flex gap-4 items-center">
          <input
            type="month"
            value={bulan}
            onChange={(e) => onBulanChange(e.target.value)}
            className="flex-1 px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
          />
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-6 py-3 bg-sabbath-green text-white rounded-2xl font-medium hover:bg-opacity-90 transition-colors disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Cari'}
          </button>
        </div>
      </div>

      {mingguItems.length === 0 && !loading && (
        <div className="p-12 text-center text-gray-400">
          Tidak ada kuitansi untuk periode ini.
        </div>
      )}

      {mingguItems.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-sabbath-light">
              <tr>
                <th className="px-6 py-4 text-left text-sm font-medium text-gray-600">Tanggal Sabat</th>
                <th className="px-6 py-4 text-left text-sm font-medium text-gray-600">ID Rekap</th>
                <th className="px-6 py-4 text-right text-sm font-medium text-gray-600">Kuitansi</th>
                <th className="px-6 py-4 text-right text-sm font-medium text-gray-600">X</th>
                <th className="px-6 py-4 text-right text-sm font-medium text-gray-600">PT</th>
                <th className="px-6 py-4 text-right text-sm font-medium text-gray-600">Khusus</th>
                <th className="px-6 py-4 text-right text-sm font-medium text-gray-600">Porsi Misi</th>
                <th className="px-6 py-4 text-right text-sm font-medium text-gray-600">Porsi Jemaat</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {mingguItems.map((m, idx) => (
                <tr key={idx} className="hover:bg-sabbath-light transition-colors">
                  <td className="px-6 py-4 text-sm text-gray-800">{m.tanggal_sabat}</td>
                  <td className="px-6 py-4 font-mono text-xs text-gray-600">{m.id_rekap_mingguan}</td>
                  <td className="px-6 py-4 text-right text-sm">{m.jumlah_kuitansi}</td>
                  <td className="px-6 py-4 text-right font-medium">Rp {m.total_x.toLocaleString()}</td>
                  <td className="px-6 py-4 text-right font-medium">Rp {m.total_pt.toLocaleString()}</td>
                  <td className="px-6 py-4 text-right font-medium">Rp {m.total_khusus.toLocaleString()}</td>
                  <td className="px-6 py-4 text-right font-medium text-sabbath-green">Rp {m.porsi_kantor_misi.toLocaleString()}</td>
                  <td className="px-6 py-4 text-right font-medium">Rp {m.porsi_kas_jemaat.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default AgregatTable;

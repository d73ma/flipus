import { useState, useEffect } from 'react';
import api from '../lib/api';

interface PendingKuitansi {
  id: number;
  nomor_kuitansi: string;
  status: string;
  total_pemberian_angka: number;
  tanggal_sabat: string;
  approved_by_user_id: number | null;
  approved_at: string | null;
  rejected_by_user_id: number | null;
  rejected_at: string | null;
  rejected_reason: string | null;
  created_by_user_id: number | null;
}

interface ApprovalPanelProps {
  scope?: 'all' | 'mine';  // 'all' = cross-jemaat (Admin Uni), 'mine' = own tenant only
  title?: string;
}

export const ApprovalPanel = ({ scope = 'all', title = 'Menunggu Persetujuan' }: ApprovalPanelProps) => {
  const [pending, setPending] = useState<PendingKuitansi[]>([]);
  const [rejected, setRejected] = useState<PendingKuitansi[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [successMsg, setSuccessMsg] = useState('');

  const fetchPending = async () => {
    setLoading(true);
    setError('');
    try {
      const resp = await api.get('/v1/dashboard/kuitansi/pending');
      setPending(resp.data.items || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal load pending kuitansi');
    } finally {
      setLoading(false);
    }
  };

  const fetchRejected = async () => {
    try {
      const resp = await api.get('/v1/dashboard/kuitansi/rejected');
      setRejected(resp.data.items || []);
    } catch (err) {
      // silent
    }
  };

  useEffect(() => {
    fetchPending();
    fetchRejected();
  }, []);

  const handleApprove = async (id: number) => {
    if (!confirm('Approve kuitansi ini? Status berubah ke FINALIZED.')) return;
    setActionLoading(id);
    setError('');
    setSuccessMsg('');
    try {
      await api.post(`/v1/dashboard/kuitansi/${id}/approve`);
      setSuccessMsg(`Kuitansi #${id} berhasil di-approve`);
      await fetchPending();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal approve kuitansi');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async () => {
    if (!rejectingId) return;
    if (rejectReason.trim().length < 5) {
      setError('Alasan reject minimal 5 karakter');
      return;
    }
    setActionLoading(rejectingId);
    setError('');
    setSuccessMsg('');
    try {
      await api.post(`/v1/dashboard/kuitansi/${rejectingId}/reject`, {
        reason: rejectReason.trim(),
      });
      setSuccessMsg(`Kuitansi #${rejectingId} di-reject`);
      setRejectingId(null);
      setRejectReason('');
      await fetchPending();
      await fetchRejected();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal reject kuitansi');
    } finally {
      setActionLoading(null);
    }
  };

  const formatRupiah = (n: number) => `Rp ${n.toLocaleString('id-ID')}`;

  return (
    <div className="bg-white rounded-3xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-gray-100">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-2xl font-playfair text-sabbath-dark">{title}</h3>
            <p className="text-sm text-gray-500 mt-1">
              {pending.length > 0 ? (
                <span className="text-amber-600 font-medium">
                  {pending.length} kuitansi menunggu approval
                </span>
              ) : (
                <span className="text-green-600">Tidak ada kuitansi pending</span>
              )}
            </p>
          </div>
          <button
            onClick={() => { fetchPending(); fetchRejected(); }}
            disabled={loading}
            className="px-4 py-2 text-sm border border-gray-300 rounded-2xl hover:bg-gray-50"
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="m-6 bg-red-50 border border-red-200 text-red-600 p-4 rounded-2xl">
          {error}
        </div>
      )}

      {successMsg && (
        <div className="m-6 bg-green-50 border border-green-200 text-green-700 p-4 rounded-2xl">
          {successMsg}
        </div>
      )}

      {/* Pending list */}
      {pending.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-sabbath-light">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">No. Kuitansi</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Tanggal</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Nominal</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-600">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {pending.map((k) => (
                <tr key={k.id} className="hover:bg-sabbath-light">
                  <td className="px-4 py-3 font-mono text-xs text-gray-800">{k.nomor_kuitansi}</td>
                  <td className="px-4 py-3 text-xs text-gray-600">{k.tanggal_sabat}</td>
                  <td className="px-4 py-3 text-right text-sm font-bold text-sabbath-dark">{formatRupiah(k.total_pemberian_angka)}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2 justify-center">
                      <button
                        onClick={() => handleApprove(k.id)}
                        disabled={actionLoading === k.id}
                        className="px-3 py-1.5 bg-sabbath-green text-white rounded-lg text-xs font-medium hover:bg-opacity-90 disabled:opacity-50"
                      >
                        {actionLoading === k.id ? '...' : '✓ Approve'}
                      </button>
                      <button
                        onClick={() => { setRejectingId(k.id); setRejectReason(''); }}
                        disabled={actionLoading === k.id}
                        className="px-3 py-1.5 border border-red-300 text-red-600 rounded-lg text-xs font-medium hover:bg-red-50 disabled:opacity-50"
                      >
                        ✗ Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Reject modal */}
      {rejectingId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-3xl p-8 max-w-md w-full">
            <h3 className="text-2xl font-playfair text-sabbath-dark mb-4">Reject Kuitansi</h3>
            <p className="text-sm text-gray-600 mb-4">
              Kuitansi #{rejectingId} akan di-reject. Berikan alasan untuk Bendahara:
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={4}
              maxLength={500}
              placeholder="Misal: Nominal tidak sesuai dengan foto amplop..."
              className="w-full px-3 py-2 border border-gray-300 rounded-xl mb-2"
            />
            <p className="text-xs text-gray-500 mb-4">{rejectReason.length} / 500 karakter</p>
            <div className="flex gap-3">
              <button
                onClick={handleReject}
                disabled={actionLoading === rejectingId || rejectReason.trim().length < 5}
                className="flex-1 py-3 bg-red-600 text-white rounded-2xl font-medium hover:bg-red-700 disabled:opacity-50"
              >
                {actionLoading === rejectingId ? 'Memproses...' : 'Konfirmasi Reject'}
              </button>
              <button
                onClick={() => { setRejectingId(null); setRejectReason(''); }}
                className="flex-1 py-3 border border-gray-300 rounded-2xl font-medium hover:bg-gray-50"
              >
                Batal
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rejected list (for Bendahara visibility) */}
      {rejected.length > 0 && (
        <div className="p-6 bg-red-50 border-t border-red-100">
          <h4 className="text-sm font-bold text-red-700 mb-3">Kuitansi yang di-reject ({rejected.length})</h4>
          <div className="space-y-2">
            {rejected.slice(0, 5).map((k) => (
              <div key={k.id} className="bg-white rounded-xl p-3 border border-red-200">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-mono text-xs text-gray-800">{k.nomor_kuitansi}</p>
                    <p className="text-xs text-gray-500 mt-1">{k.tanggal_sabat} • {formatRupiah(k.total_pemberian_angka)}</p>
                  </div>
                  <span className="text-xs text-red-600 font-medium">REJECTED</span>
                </div>
                {k.rejected_reason && (
                  <p className="text-xs text-gray-600 mt-2 italic">Alasan: {k.rejected_reason}</p>
                )}
              </div>
            ))}
            {rejected.length > 5 && (
              <p className="text-xs text-gray-500 text-center mt-2">+{rejected.length - 5} lainnya</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ApprovalPanel;

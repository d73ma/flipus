import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/api';

interface ForgotPasswordOut {
  status: string;
  identifier: string;
  message: string;
  new_password_masked?: string;
}

const ForgotPassword = () => {
  const [identifier, setIdentifier] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ForgotPasswordOut | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    setResult(null);
    try {
      const r = await api.post<ForgotPasswordOut>('/v1/auth/forgot-password', { identifier });
      setResult(r.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal mengirim request');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-sabbath-light flex items-center justify-center p-6">
      <div className="bg-white p-8 rounded-2xl shadow-xl w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-display text-sabbath-dark mb-2">Lupa Password</h1>
          <p className="text-gray-600 text-sm">
            Masukkan username atau nomor WhatsApp Anda.
            Password baru akan dikirim via WhatsApp.
          </p>
        </div>

        {!result && (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="block text-sm font-medium mb-1">Username atau Nomor WA</label>
              <input
                type="text"
                required
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                placeholder="pendeta_nt atau 628123456789"
              />
            </div>
            {error && <div className="text-red-500 text-sm">{error}</div>}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-sabbath-dark hover:bg-black text-white font-medium py-4 rounded-xl disabled:opacity-50"
            >
              {loading ? 'Mengirim...' : 'Kirim Password Baru'}
            </button>
            <Link
              to="/login"
              className="block text-center text-sm text-gray-500 hover:text-sabbath-dark"
            >
              ← Kembali ke login
            </Link>
          </form>
        )}

        {result && (
          <div className="space-y-6">
            {result.status === 'sent' && (
              <div className="bg-green-50 border border-green-200 rounded-2xl p-6 text-center">
                <div className="text-4xl mb-3">✅</div>
                <h3 className="text-lg font-display text-sabbath-dark mb-2">Berhasil!</h3>
                <p className="text-sm text-gray-700">{result.message}</p>
              </div>
            )}

            {result.status === 'not_found' && (
              <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center">
                <div className="text-4xl mb-3">❌</div>
                <h3 className="text-lg font-display text-sabbath-dark mb-2">Tidak Ditemukan</h3>
                <p className="text-sm text-gray-700">{result.message}</p>
              </div>
            )}

            {result.status === 'rate_limited' && (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-center">
                <div className="text-4xl mb-3">⏳</div>
                <h3 className="text-lg font-display text-sabbath-dark mb-2">Tunggu Sebentar</h3>
                <p className="text-sm text-gray-700">{result.message}</p>
              </div>
            )}

            {result.status === 'no_wa' && (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-center">
                <div className="text-4xl mb-3">⚠️</div>
                <h3 className="text-lg font-display text-sabbath-dark mb-2">Nomor WA Kosong</h3>
                <p className="text-sm text-gray-700">{result.message}</p>
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => { setResult(null); setIdentifier(''); }}
                className="flex-1 py-3 border border-gray-300 rounded-2xl font-medium hover:bg-gray-50"
              >
                Coba Lagi
              </button>
              <Link
                to="/login"
                className="flex-1 text-center py-3 bg-sabbath-dark text-white rounded-2xl font-medium hover:bg-black"
              >
                Login
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ForgotPassword;
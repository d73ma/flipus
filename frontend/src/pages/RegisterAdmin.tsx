import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../lib/api';

interface Uni { id: number; kode: string; nama_resmi: string; }
interface CredentialsOut {
  username: string; password: string; password_masked: string;
  nomor_wa_target: string | null; wa_sent: boolean;
}
interface RegisterAdminOut {
  status: string; user_id: number; tenant_id: number; uni_id: number;
  nama_uni: string; nama_admin: string; credentials: CredentialsOut; message: string;
}

const RegisterAdmin = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<'form' | 'success'>('form');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<RegisterAdminOut | null>(null);

  const [uniList, setUniList] = useState<Uni[]>([]);
  const [uniId, setUniId] = useState<number | ''>('');

  const [namaBendaharaUni, setNamaBendaharaUni] = useState('');
  const [waBendaharaUni, setWaBendaharaUni] = useState('');
  const [namaAdminUni, setNamaAdminUni] = useState('');
  const [waAdminUni, setWaAdminUni] = useState('');

  useEffect(() => {
    api.get<Uni[]>('/v1/master/uni').then((r) => setUniList(r.data)).catch(() => setError('Gagal load master Uni'));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const payload = {
        uni_id: Number(uniId),
        nama_bendahara_uni: namaBendaharaUni,
        wa_bendahara_uni: waBendaharaUni || null,
        nama_admin_uni: namaAdminUni,
        wa_admin_uni: waAdminUni || null,
      };
      const r = await api.post<RegisterAdminOut>('/v1/register/admin', payload);
      setResult(r.data);
      setStep('success');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal submit pendaftaran');
    } finally {
      setLoading(false);
    }
  };

  if (step === 'success' && result) {
    return (
      <div className="min-h-screen bg-sabbath-light flex items-center justify-center p-6">
        <div className="bg-white rounded-3xl shadow-xl max-w-lg w-full p-8">
          <div className="text-center mb-6">
            <div className="w-16 h-16 bg-sabbath-charcoal text-white rounded-full flex items-center justify-center text-3xl mx-auto mb-4">✓</div>
            <h2 className="text-3xl font-display text-sabbath-dark mb-2">Admin Uni Terdaftar!</h2>
            <p className="text-gray-600">{result.message}</p>
          </div>

          <div className="bg-amber-50 border-2 border-amber-300 rounded-2xl p-6 mb-6">
            <p className="text-sm text-amber-800 font-medium mb-3">⚠️ Kredensial (simpan sekarang):</p>
            <div className="space-y-3">
              <div>
                <p className="text-xs text-gray-600">Username</p>
                <p className="font-mono text-lg font-bold text-sabbath-dark">{result.credentials.username}</p>
              </div>
              <div>
                <p className="text-xs text-gray-600">Password</p>
                <p className="font-mono text-lg font-bold text-sabbath-dark">{result.credentials.password}</p>
              </div>
            </div>
            {result.credentials.wa_sent && (
              <p className="text-xs text-green-700 mt-3">✓ Juga dikirim ke WA {result.credentials.nomor_wa_target}</p>
            )}
          </div>

          <button onClick={() => navigate('/login')}
            className="w-full bg-sabbath-dark text-white py-4 rounded-2xl font-medium hover:bg-black">
            Login Sekarang
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-sabbath-light">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/register" className="flex items-center gap-2 text-sabbath-dark hover:text-sabbath-gold">
            <span>←</span><span className="text-sm">Pilih peran lain</span>
          </Link>
          <Link to="/login" className="text-sm text-sabbath-dark hover:text-sabbath-gold">Login</Link>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="mb-8">
          <h2 className="text-4xl font-display text-sabbath-dark mb-2">Daftar sebagai Admin Uni</h2>
          <p className="text-gray-600">Isi data Uni dan pejabat. Persentase pembagian diatur setelah login di halaman Pengaturan.</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-3xl shadow-sm p-8 space-y-6">
          {error && <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-2xl text-sm">{error}</div>}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Uni *</label>
            <select required value={uniId} onChange={(e) => setUniId(e.target.value ? Number(e.target.value) : '')}
              className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold">
              <option value="">-- Pilih Uni --</option>
              {uniList.map((u) => <option key={u.id} value={u.id}>{u.nama_resmi}</option>)}
            </select>
          </div>

          <fieldset className="border-t border-gray-200 pt-6">
            <legend className="text-lg font-display text-sabbath-dark mb-4">Bendahara Uni</legend>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nama *</label>
                <input required value={namaBendaharaUni} onChange={(e) => setNamaBendaharaUni(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomor WA</label>
                <input type="tel" value={waBendaharaUni} onChange={(e) => setWaBendaharaUni(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
              </div>
            </div>
          </fieldset>

          <fieldset className="border-t border-gray-200 pt-6">
            <legend className="text-lg font-display text-sabbath-dark mb-4">Admin Uni</legend>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nama Admin *</label>
                <input required value={namaAdminUni} onChange={(e) => setNamaAdminUni(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomor WA</label>
                <input type="tel" value={waAdminUni} onChange={(e) => setWaAdminUni(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
              </div>
            </div>
          </fieldset>

          <div className="pt-6 border-t border-gray-200 flex gap-3">
            <Link to="/register" className="flex-1 text-center py-4 border border-gray-300 rounded-2xl font-medium hover:bg-gray-50">Batal</Link>
            <button type="submit" disabled={loading}
              className="flex-1 py-4 bg-sabbath-dark text-white rounded-2xl font-medium hover:bg-black disabled:opacity-50">
              {loading ? 'Mengirim...' : 'Submit Pendaftaran'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default RegisterAdmin;
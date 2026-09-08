import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../lib/api';

interface Uni {
  id: number;
  kode: string;
  nama_resmi: string;
}

interface Misi {
  id: number;
  uni_id: number;
  kode: string;
  nama_resmi: string;
  jenis: string;
}

interface CredentialsOut {
  username: string;
  password: string;
  password_masked: string;
  nomor_wa_target: string | null;
  wa_sent: boolean;
}

interface RegisterPendetaOut {
  status: string;
  user_id: number;
  tenant_id: number;
  nama_jemaat: string;
  nama_pendeta: string;
  credentials: CredentialsOut;
  message: string;
}

const RegisterPendeta = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<'form' | 'success'>('form');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<RegisterPendetaOut | null>(null);

  // Master data
  const [uniList, setUniList] = useState<Uni[]>([]);
  const [misiList, setMisiList] = useState<Misi[]>([]);

  // Form fields
  const [uniId, setUniId] = useState<number | ''>('');
  const [misiId, setMisiId] = useState<number | ''>('');
  const [namaJemaat, setNamaJemaat] = useState('');
  const [initialJemaat, setInitialJemaat] = useState('');
  const [namaPendeta, setNamaPendeta] = useState('');
  const [waPendeta, setWaPendeta] = useState('');
  const [namaKetua, setNamaKetua] = useState('');
  const [waKetua, setWaKetua] = useState('');
  const [namaBendahara, setNamaBendahara] = useState('');
  const [waBendahara, setWaBendahara] = useState('');

  useEffect(() => {
    api.get<Uni[]>('/v1/master/uni').then((r) => setUniList(r.data)).catch(() => setError('Gagal load master Uni'));
  }, []);

  useEffect(() => {
    if (uniId) {
      api.get<Misi[]>('/v1/master/misi', { params: { uni_id: uniId } }).then((r) => setMisiList(r.data));
    } else {
      setMisiList([]);
      setMisiId('');
    }
  }, [uniId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const payload = {
        uni_id: Number(uniId),
        misi_konferens_id: Number(misiId),
        nama_jemaat: namaJemaat,
        initial_jemaat: initialJemaat.toUpperCase(),
        nama_pendeta: namaPendeta,
        wa_pendeta: waPendeta || null,
        nama_ketua: namaKetua,
        wa_ketua: waKetua || null,
        nama_bendahara: namaBendahara || '',
        wa_bendahara: waBendahara || null,
      };
      const r = await api.post<RegisterPendetaOut>('/v1/register/pendeta', payload);
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
            <div className="w-16 h-16 bg-sabbath-green text-white rounded-full flex items-center justify-center text-3xl mx-auto mb-4">
              ✓
            </div>
            <h2 className="text-3xl font-display text-sabbath-dark mb-2">Pendaftaran Berhasil!</h2>
            <p className="text-gray-600">{result.message}</p>
          </div>

          <div className="bg-amber-50 border-2 border-amber-300 rounded-2xl p-6 mb-6">
            <p className="text-sm text-amber-800 font-medium mb-3">
              ⚠️ Simpan kredensial ini — ditampilkan sekali saja:
            </p>
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
              <p className="text-xs text-green-700 mt-3">
                ✓ Kredensial juga sudah dikirim ke WhatsApp {result.credentials.nomor_wa_target}
              </p>
            )}
          </div>

          <div className="space-y-3">
            <button
              onClick={() => navigate('/login')}
              className="w-full bg-sabbath-dark text-white py-4 rounded-2xl font-medium hover:bg-black transition-colors"
            >
              Login Sekarang
            </button>
            <Link
              to="/"
              className="block text-center text-sm text-gray-500 hover:text-sabbath-dark"
            >
              Kembali ke beranda
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-sabbath-light">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/register" className="flex items-center gap-2 text-sabbath-dark hover:text-sabbath-gold">
            <span>←</span>
            <span className="text-sm">Pilih peran lain</span>
          </Link>
          <Link to="/login" className="text-sm text-sabbath-dark hover:text-sabbath-gold">
            Login
          </Link>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="mb-8">
          <h2 className="text-4xl font-display text-sabbath-dark mb-2">Daftar sebagai Pendeta</h2>
          <p className="text-gray-600">
            Isi data jemaat, pejabat, dan Anda akan mendapat akun Pendeta untuk jemaat ini.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-3xl shadow-sm p-8 space-y-6">
          {error && <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-2xl text-sm">{error}</div>}

          {/* Uni & Misi */}
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Uni *</label>
              <select
                required
                value={uniId}
                onChange={(e) => setUniId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
              >
                <option value="">-- Pilih Uni --</option>
                {uniList.map((u) => (
                  <option key={u.id} value={u.id}>{u.nama_resmi}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Daerah Misi/Konferens *</label>
              <select
                required
                disabled={!uniId}
                value={misiId}
                onChange={(e) => setMisiId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold disabled:bg-gray-50"
              >
                <option value="">-- Pilih Misi --</option>
                {misiList.map((m) => (
                  <option key={m.id} value={m.id}>{m.nama_resmi}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Jemaat */}
          <div className="grid md:grid-cols-3 gap-4">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Nama Resmi Jemaat *</label>
              <input
                type="text"
                required
                value={namaJemaat}
                onChange={(e) => setNamaJemaat(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                placeholder="Jemaat Nataan"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Inisial (2-4 huruf) *</label>
              <input
                type="text"
                required
                minLength={2}
                maxLength={4}
                value={initialJemaat}
                onChange={(e) => setInitialJemaat(e.target.value.toUpperCase())}
                className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold uppercase font-mono"
                placeholder="NT"
              />
            </div>
          </div>

          {/* Pendeta */}
          <fieldset className="border-t border-gray-200 pt-6">
            <legend className="text-lg font-display text-sabbath-dark mb-4">Data Pendeta</legend>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nama Pendeta *</label>
                <input
                  type="text"
                  required
                  value={namaPendeta}
                  onChange={(e) => setNamaPendeta(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomor WA Pendeta</label>
                <input
                  type="tel"
                  value={waPendeta}
                  onChange={(e) => setWaPendeta(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                  placeholder="628123456789"
                />
              </div>
            </div>
          </fieldset>

          {/* Ketua */}
          <fieldset className="border-t border-gray-200 pt-6">
            <legend className="text-lg font-display text-sabbath-dark mb-4">Data Ketua</legend>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nama Ketua *</label>
                <input
                  type="text"
                  required
                  value={namaKetua}
                  onChange={(e) => setNamaKetua(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomor WA Ketua</label>
                <input
                  type="tel"
                  value={waKetua}
                  onChange={(e) => setWaKetua(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                  placeholder="628123456789"
                />
              </div>
            </div>
          </fieldset>

          {/* Bendahara */}
          <fieldset className="border-t border-gray-200 pt-6">
            <legend className="text-lg font-display text-sabbath-dark mb-4">Data Bendahara</legend>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nama Bendahara *</label>
                <input
                  type="text"
                  required
                  value={namaBendahara}
                  onChange={(e) => setNamaBendahara(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomor WA Bendahara *</label>
                <input
                  type="tel"
                  required
                  value={waBendahara}
                  onChange={(e) => setWaBendahara(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                  placeholder="628123456789"
                />
              </div>
            </div>
          </fieldset>

          <div className="pt-6 border-t border-gray-200 flex gap-3">
            <Link
              to="/register"
              className="flex-1 text-center py-4 border border-gray-300 rounded-2xl font-medium hover:bg-gray-50"
            >
              Batal
            </Link>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 py-4 bg-sabbath-dark text-white rounded-2xl font-medium hover:bg-black disabled:opacity-50"
            >
              {loading ? 'Mengirim...' : 'Submit Pendaftaran'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default RegisterPendeta;
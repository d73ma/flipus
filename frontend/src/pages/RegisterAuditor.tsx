import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../lib/api';

interface Uni { id: number; kode: string; nama_resmi: string; }
interface Misi { id: number; uni_id: number; kode: string; nama_resmi: string; jenis: string; }
interface CredentialsOut {
  username: string; password: string; password_masked: string;
  nomor_wa_target: string | null; wa_sent: boolean;
}
interface RegisterAuditorOut {
  status: string; user_id: number; tenant_id: number; misi_id: number;
  nama_misi: string; nama_auditor: string; credentials: CredentialsOut; message: string;
}

const RegisterAuditor = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<'form' | 'success'>('form');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<RegisterAuditorOut | null>(null);

  const [uniList, setUniList] = useState<Uni[]>([]);
  const [misiList, setMisiList] = useState<Misi[]>([]);

  const [uniId, setUniId] = useState<number | ''>('');
  const [misiId, setMisiId] = useState<number | ''>('');
  const [namaBendaharaMisi, setNamaBendaharaMisi] = useState('');
  const [waBendaharaMisi, setWaBendaharaMisi] = useState('');
  const [namaAuditor, setNamaAuditor] = useState('');
  const [waAuditor, setWaAuditor] = useState('');

  // Persentase (default 100% X ke misi, 50% PT)
  const [pctX, setPctX] = useState(1.0);
  const [pctPT, setPctPT] = useState(0.5);
  const [pctKhusus, setPctKhusus] = useState(0.0);

  useEffect(() => {
    api.get<Uni[]>('/v1/master/uni').then((r) => setUniList(r.data)).catch(() => setError('Gagal load master Uni'));
  }, []);

  useEffect(() => {
    if (uniId) {
      api.get<Misi[]>('/v1/master/misi', { params: { uni_id: uniId } }).then((r) => setMisiList(r.data));
    } else { setMisiList([]); setMisiId(''); }
  }, [uniId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const payload = {
        uni_id: Number(uniId),
        misi_konferens_id: Number(misiId),
        nama_bendahara_misi: namaBendaharaMisi,
        wa_bendahara_misi: waBendaharaMisi || null,
        nama_auditor: namaAuditor,
        wa_auditor: waAuditor || null,
        pct_x_jemaat: pctX,
        pct_pt_jemaat: pctPT,
        pct_khusus_jemaat: pctKhusus,
      };
      const r = await api.post<RegisterAuditorOut>('/v1/register/auditor', payload);
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
            <div className="w-16 h-16 bg-sabbath-gold text-white rounded-full flex items-center justify-center text-3xl mx-auto mb-4">✓</div>
            <h2 className="text-3xl font-display text-sabbath-dark mb-2">Auditor Terdaftar!</h2>
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

          <button
            onClick={() => navigate('/login')}
            className="w-full bg-sabbath-dark text-white py-4 rounded-2xl font-medium hover:bg-black"
          >
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
          <h2 className="text-4xl font-display text-sabbath-dark mb-2">Daftar sebagai Auditor Misi</h2>
          <p className="text-gray-600">Isi data misi, pejabat, dan persentase pembagian. Konfigurasi ini akan langsung berlaku untuk semua jemaat di misi Anda.</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-3xl shadow-sm p-8 space-y-6">
          {error && <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-2xl text-sm">{error}</div>}

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Uni *</label>
              <select required value={uniId} onChange={(e) => setUniId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold">
                <option value="">-- Pilih Uni --</option>
                {uniList.map((u) => <option key={u.id} value={u.id}>{u.nama_resmi}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Daerah Misi/Konferens *</label>
              <select required disabled={!uniId} value={misiId} onChange={(e) => setMisiId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold disabled:bg-gray-50">
                <option value="">-- Pilih Misi --</option>
                {misiList.map((m) => <option key={m.id} value={m.id}>{m.nama_resmi}</option>)}
              </select>
            </div>
          </div>

          <fieldset className="border-t border-gray-200 pt-6">
            <legend className="text-lg font-display text-sabbath-dark mb-4">Bendahara Misi</legend>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nama *</label>
                <input required value={namaBendaharaMisi} onChange={(e) => setNamaBendaharaMisi(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomor WA</label>
                <input type="tel" value={waBendaharaMisi} onChange={(e) => setWaBendaharaMisi(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
              </div>
            </div>
          </fieldset>

          <fieldset className="border-t border-gray-200 pt-6">
            <legend className="text-lg font-display text-sabbath-dark mb-4">Auditor</legend>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nama Auditor *</label>
                <input required value={namaAuditor} onChange={(e) => setNamaAuditor(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomor WA</label>
                <input type="tel" value={waAuditor} onChange={(e) => setWaAuditor(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
              </div>
            </div>
          </fieldset>

          <fieldset className="border-t border-gray-200 pt-6">
            <legend className="text-lg font-display text-sabbath-dark mb-4">Persentase Pembagian (Jemaat → Misi)</legend>
            <p className="text-sm text-gray-600 mb-4">
              Pengaturan ini akan langsung mempengaruhi kalkulasi di dasbor Bendahara semua jemaat di misi Anda.
            </p>
            <div className="grid md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">% X (Perpuluhan) *</label>
                <input type="number" required min={0} max={1} step={0.01} value={pctX} onChange={(e) => setPctX(Number(e.target.value))}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
                <p className="text-xs text-gray-500 mt-1">{(pctX * 100).toFixed(0)}% ke Misi</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">% PT *</label>
                <input type="number" required min={0} max={1} step={0.01} value={pctPT} onChange={(e) => setPctPT(Number(e.target.value))}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
                <p className="text-xs text-gray-500 mt-1">{(pctPT * 100).toFixed(0)}% ke Misi</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">% Khusus</label>
                <input type="number" min={0} max={1} step={0.01} value={pctKhusus} onChange={(e) => setPctKhusus(Number(e.target.value))}
                  className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-sabbath-gold" />
                <p className="text-xs text-gray-500 mt-1">{(pctKhusus * 100).toFixed(0)}% ke Misi</p>
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

export default RegisterAuditor;
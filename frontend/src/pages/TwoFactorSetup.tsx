import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { useAuth } from '../lib/auth';

interface TwoFactorStatus {
  is_2fa_enabled: boolean;
  backup_codes_remaining: number;
  twofa_enabled_at: string | null;
  last_2fa_used_at: string | null;
}

interface TwoFactorSetupData {
  secret: string;
  qr_code: string;  // base64 PNG data URI
  otpauth_url: string;
  issuer: string;
  username: string;
}

export const TwoFactorSetup = () => {
  const navigate = useNavigate();
  const { tenant } = useAuth();
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [setupData, setSetupData] = useState<TwoFactorSetupData | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [showBackupCodes, setShowBackupCodes] = useState(false);

  const [disableTotp, setDisableTotp] = useState('');
  const [disablePassword, setDisablePassword] = useState('');

  const [regenTotp, setRegenTotp] = useState('');

  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchStatus();
  }, []);

  const fetchStatus = async () => {
    try {
      const resp = await api.get<TwoFactorStatus>('/v1/auth/2fa/status');
      setStatus(resp.data);
    } catch (err: any) {
      setError('Gagal load status 2FA');
    }
  };

  const handleSetup = async () => {
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      const resp = await api.post<TwoFactorSetupData>('/v1/auth/2fa/setup');
      setSetupData(resp.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal generate secret');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      const resp = await api.post('/v1/auth/2fa/verify', {
        totp_code: verifyCode,
        backup_codes_visible: true,
      });
      setBackupCodes(resp.data.backup_codes || []);
      setShowBackupCodes(true);
      setSetupData(null);
      setVerifyCode('');
      await fetchStatus();
      setSuccess('2FA berhasil diaktifkan!');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Kode TOTP salah');
    } finally {
      setLoading(false);
    }
  };

  const handleDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirm('Yakin disable 2FA? Akun Anda akan kurang aman.')) return;
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      await api.post('/v1/auth/2fa/disable', {
        totp_code: disableTotp,
        password: disablePassword,
      });
      setDisableTotp('');
      setDisablePassword('');
      await fetchStatus();
      setSuccess('2FA berhasil dimatikan');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal disable 2FA');
    } finally {
      setLoading(false);
    }
  };

  const handleRegenBackupCodes = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      const resp = await api.post(`/v1/auth/2fa/backup-codes?totp_code=${regenTotp}`);
      setBackupCodes(resp.data.backup_codes || []);
      setShowBackupCodes(true);
      setRegenTotp('');
      await fetchStatus();
      setSuccess('Backup codes baru di-generate. Backup codes lama INVALID.');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal regenerate backup codes');
    } finally {
      setLoading(false);
    }
  };

  const downloadBackupCodes = () => {
    const text = [
      'FLIPUS 2FA Backup Codes',
      `Generated: ${new Date().toISOString()}`,
      `User: ${tenant?.nama_jemaat_lokal || ''}`,
      '',
      ...backupCodes.map((c, i) => `${i + 1}. ${c}`),
      '',
      'Setiap code hanya bisa dipakai SEKALI.',
      'SIMPAN file ini di tempat aman (password manager / encrypted storage).',
    ].join('\n');

    const blob = new Blob([text], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `flipus-backup-codes-${new Date().toISOString().slice(0, 10)}.txt`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  if (!status) {
    return <div className="p-8 text-gray-500">Loading...</div>;
  }

  return (
    <div
      className="min-h-screen p-8"
      style={{ backgroundColor: tenant?.secondary_color || '#F5EFE0' }}
    >
      <div className="max-w-3xl mx-auto">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-gray-600 hover:text-gray-900 mb-2"
        >
          ← Kembali
        </button>
        <h1 className="text-3xl font-bold mb-2" style={{ color: tenant?.primary_color || '#1B4332' }}>
          Autentikasi 2 Faktor (2FA)
        </h1>
        <p className="text-gray-600 mb-6">Tingkatkan keamanan akun Anda dengan TOTP</p>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl mb-4">
            {error}
          </div>
        )}
        {success && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-2xl mb-4">
            {success}
          </div>
        )}

        {/* Status card */}
        <div className="bg-white rounded-2xl shadow p-6 mb-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-xl font-bold mb-1">Status 2FA</h2>
              {status.is_2fa_enabled ? (
                <>
                  <p className="text-sm text-green-600 font-medium">✓ Aktif</p>
                  <p className="text-xs text-gray-500 mt-1">
                    Backup codes tersisa: {status.backup_codes_remaining} / 10
                  </p>
                  {status.last_2fa_used_at && (
                    <p className="text-xs text-gray-500">
                      Terakhir dipakai: {new Date(status.last_2fa_used_at).toLocaleString('id-ID')}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-gray-500">Belum aktif. Klik "Aktifkan 2FA" untuk memulai.</p>
              )}
            </div>
            {!status.is_2fa_enabled && (
              <button
                onClick={handleSetup}
                disabled={loading}
                className="px-6 py-3 text-white rounded-2xl font-medium hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: tenant?.primary_color || '#1B4332' }}
              >
                {loading ? 'Loading...' : 'Aktifkan 2FA'}
              </button>
            )}
          </div>
        </div>

        {/* Setup wizard (after clicking "Aktifkan 2FA") */}
        {setupData && !status.is_2fa_enabled && (
          <div className="bg-white rounded-2xl shadow p-6 mb-6">
            <h2 className="text-xl font-bold mb-4">Setup 2FA</h2>
            <ol className="list-decimal list-inside space-y-3 text-sm text-gray-700">
              <li>Install aplikasi Authenticator (Google Authenticator, Authy, 1Password, dll)</li>
              <li>Scan QR code di bawah ini</li>
              <li>Masukkan 6-digit kode yang muncul di app ke kolom di bawah</li>
            </ol>
            <div className="flex flex-col md:flex-row gap-6 mt-6">
              <div className="flex-shrink-0 text-center">
                <img
                  src={setupData.qr_code}
                  alt="QR Code"
                  className="w-48 h-48 border border-gray-200 rounded mx-auto"
                />
                <p className="text-xs text-gray-500 mt-2">Scan dengan Authenticator app</p>
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium mb-2">Atau masukkan secret manual:</p>
                <code className="block bg-gray-100 px-3 py-2 rounded text-xs font-mono break-all mb-4">
                  {setupData.secret}
                </code>
                <p className="text-sm font-medium mb-2">Atau klik link:</p>
                <a
                  href={setupData.otpauth_url}
                  className="text-xs text-blue-600 hover:underline break-all"
                >
                  {setupData.otpauth_url}
                </a>
              </div>
            </div>

            <form onSubmit={handleVerify} className="mt-6 pt-6 border-t border-gray-200">
              <label className="block text-sm font-medium mb-2">Kode 6-digit dari Authenticator</label>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={verifyCode}
                  onChange={(e) => setVerifyCode(e.target.value)}
                  maxLength={6}
                  className="flex-1 px-4 py-3 border border-gray-300 rounded-xl text-center text-2xl font-mono tracking-widest"
                  placeholder="123456"
                  required
                />
                <button
                  type="submit"
                  disabled={loading || verifyCode.length !== 6}
                  className="px-6 py-3 text-white rounded-2xl font-medium disabled:opacity-50"
                  style={{ backgroundColor: tenant?.primary_color || '#1B4332' }}
                >
                  {loading ? 'Verifying...' : 'Aktifkan'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Backup codes display (after enable or regenerate) */}
        {showBackupCodes && backupCodes.length > 0 && (
          <div className="bg-yellow-50 border border-yellow-300 rounded-2xl p-6 mb-6">
            <h2 className="text-xl font-bold text-yellow-900 mb-2">⚠ Backup Codes</h2>
            <p className="text-sm text-yellow-800 mb-4">
              Simpan 10 backup codes ini di tempat aman. Setiap code hanya bisa dipakai SEKALI
              untuk login kalau Anda kehilangan Authenticator device.
            </p>
            <div className="grid grid-cols-2 gap-2 bg-white p-4 rounded-xl font-mono text-sm">
              {backupCodes.map((code, i) => (
                <div key={i} className="px-3 py-2 bg-gray-50 rounded text-center">
                  <span className="text-gray-500 mr-2">{i + 1}.</span>{code}
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-4">
              <button
                onClick={downloadBackupCodes}
                className="px-4 py-2 bg-yellow-700 text-white rounded-xl text-sm font-medium hover:bg-yellow-800"
              >
                📥 Download .txt
              </button>
              <button
                onClick={() => setShowBackupCodes(false)}
                className="px-4 py-2 border border-gray-300 rounded-xl text-sm"
              >
                Saya sudah simpan
              </button>
            </div>
          </div>
        )}

        {/* Disable 2FA */}
        {status.is_2fa_enabled && (
          <div className="bg-white rounded-2xl shadow p-6 mb-6">
            <h2 className="text-xl font-bold mb-2">Disable 2FA</h2>
            <p className="text-sm text-gray-600 mb-4">
              Untuk konfirmasi, masukkan kode TOTP dan password Anda saat ini.
            </p>
            <form onSubmit={handleDisable} className="space-y-3">
              <input
                type="text"
                value={disableTotp}
                onChange={(e) => setDisableTotp(e.target.value)}
                maxLength={6}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl text-center text-xl font-mono tracking-widest"
                placeholder="Kode 2FA"
                required
              />
              <input
                type="password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl"
                placeholder="Password"
                required
              />
              <button
                type="submit"
                disabled={loading}
                className="w-full px-6 py-3 bg-red-600 text-white rounded-2xl font-medium hover:bg-red-700 disabled:opacity-50"
              >
                {loading ? 'Processing...' : 'Disable 2FA'}
              </button>
            </form>
          </div>
        )}

        {/* Regenerate backup codes */}
        {status.is_2fa_enabled && (
          <div className="bg-white rounded-2xl shadow p-6">
            <h2 className="text-xl font-bold mb-2">Regenerate Backup Codes</h2>
            <p className="text-sm text-gray-600 mb-4">
              Generate 10 backup codes baru. Backup codes lama akan INVALID.
            </p>
            <form onSubmit={handleRegenBackupCodes} className="flex gap-3">
              <input
                type="text"
                value={regenTotp}
                onChange={(e) => setRegenTotp(e.target.value)}
                maxLength={6}
                className="flex-1 px-4 py-3 border border-gray-300 rounded-xl text-center text-xl font-mono tracking-widest"
                placeholder="Kode 2FA"
                required
              />
              <button
                type="submit"
                disabled={loading}
                className="px-6 py-3 text-white rounded-2xl font-medium disabled:opacity-50"
                style={{ backgroundColor: tenant?.primary_color || '#1B4332' }}
              >
                {loading ? 'Loading...' : 'Regenerate'}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};

export default TwoFactorSetup;

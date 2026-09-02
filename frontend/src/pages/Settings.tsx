import { useState } from 'react';
import { useAuth } from '../lib/auth';
import ApprovalPanel from '../components/ApprovalPanel';
import KuitansiSearchPanel from '../components/KuitansiSearchPanel';
import api from '../lib/api';
import { useEffect } from 'react';

interface UserOut {
  id: number;
  username: string;
  nama_lengkap: string;
  role: string;
  nomor_whatsapp: string | null;
  is_active: boolean;
}

interface BackupItem {
  filename: string;
  size_bytes: number;
  created_at: string;
  kind: string;
}

interface AuditLogOut {
  id: number;
  tenant_id: number;
  action: string;
  payload_hash: string | null;
  porsi_dana_misi: number;
  created_at: string;
}

interface AuditLogsOut {
  logs: AuditLogOut[];
  count: number;
  page: number;
  per_page: number;
}

/**
 * T36 Redesign: Settings page — bundles all advanced panels moved out of dashboards.
 *
 * Sections (role-based visibility):
 * - Bendahara: Approval, Search
 * - Ketua: Approval
 * - Auditor: Approval, Search, User Management
 * - Admin: Approval, Search, User Management, Backup, Audit Logs
 */
const Settings = () => {
  const { role, tenant } = useAuth();
  const [activeTab, setActiveTab] = useState<string>('approval');

  // ===== User management state (Auditor/Admin) =====
  const [users, setUsers] = useState<UserOut[]>([]);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // ===== Backup state (Admin only) =====
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [backupLoading, setBackupLoading] = useState(false);

  // ===== Audit logs state (Admin only) =====
  const [logs, setLogs] = useState<AuditLogOut[]>([]);
  const [logsPage, setLogsPage] = useState(1);
  const [logsCount, setLogsCount] = useState(0);
  const [logsFilter, setLogsFilter] = useState('');

  // ===== Determine available tabs =====
  // v1.5-D: Change Password tab available untuk semua role
  const tabs: { key: string; label: string; icon: string }[] = [
    { key: 'password', label: 'Ganti Password', icon: '🔑' },
    { key: 'approval', label: 'Approval', icon: '✓' },
  ];
  if (role === 'BENDAHARA' || role === 'AUDITOR_MISI' || role === 'ADMIN_UNI') {
    tabs.push({ key: 'search', label: 'Pencarian Kuitansi', icon: '🔍' });
  }
  if (role === 'AUDITOR_MISI' || role === 'ADMIN_UNI') {
    tabs.push({ key: 'users', label: 'Manajemen User', icon: '👥' });
  }
  if (role === 'ADMIN_UNI') {
    tabs.push({ key: 'backup', label: 'Backup & Restore', icon: '💾' });
    tabs.push({ key: 'audit', label: 'Audit Logs', icon: '📋' });
  }
  if (role === 'ADMIN_UNI') {
    tabs.push({ key: 'branding', label: 'Branding Jemaat', icon: '🎨' });
  }

  // ===== Fetchers =====
  const fetchUsers = async () => {
    try {
      const r = await api.get('/v1/users');
      setUsers(r.data.users);
    } catch (e) {}
  };

  const fetchBackups = async () => {
    setBackupLoading(true);
    try {
      const r = await api.get('/v1/admin/backups');
      setBackups(r.data.backups);
    } catch (e) {}
    setBackupLoading(false);
  };

  const fetchLogs = async (page = 1) => {
    try {
      const params: any = { page, per_page: 50 };
      if (logsFilter) params.action_like = logsFilter;
      const r = await api.get<AuditLogsOut>('/v1/admin/audit-logs', { params });
      setLogs(r.data.logs);
      setLogsCount(r.data.count);
      setLogsPage(r.data.page);
    } catch (e) {}
  };

  useEffect(() => {
    if (activeTab === 'users') fetchUsers();
    if (activeTab === 'backup') fetchBackups();
    if (activeTab === 'audit') fetchLogs();
  }, [activeTab]);

  const handleDeleteUser = async (userId: number, name: string) => {
    if (!confirm(`Nonaktifkan akun ${name}?`)) return;
    setDeletingId(userId);
    try {
      await api.delete(`/v1/users/${userId}`);
      await fetchUsers();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Gagal nonaktifkan');
    } finally {
      setDeletingId(null);
    }
  };

  const handleBackup = async (method: 'binary' | 'sql') => {
    if (!confirm(`Generate backup (${method})?`)) return;
    try {
      const r = await api.post('/v1/admin/backup-db', null, { params: { method } });
      alert(`✓ Backup ${method}: ${r.data.filename} (${(r.data.size_bytes / 1024).toFixed(1)} KB)`);
      await fetchBackups();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Backup gagal');
    }
  };

  const handleRestore = async (filename: string) => {
    if (!confirm(`Restore dari ${filename}? Auto-backup dulu sebelum restore.\n\nLanjutkan?`)) return;
    try {
      await api.post('/v1/admin/restore-db', { filename });
      alert(`✓ Restore berhasil dari ${filename}. User harus login ulang.`);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Restore gagal');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl md:text-4xl font-display text-sabbath-dark">⚙️ Settings</h2>
        <p className="text-gray-600 mt-1">
          Panel admin, approval, backup, dan audit. {tenant && <span>· {tenant.nama_jemaat_lokal}</span>}
        </p>
      </div>

      {/* Tabs — pill/segmented style, smooth active state */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-2 bg-sabbath-light/40 border-b border-gray-100">
          <div className="flex flex-wrap gap-1.5">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl whitespace-nowrap transition-all duration-200 ${
                  activeTab === tab.key
                    ? 'bg-sabbath-dark text-white shadow-sm'
                    : 'text-gray-600 hover:bg-white hover:text-sabbath-dark hover:shadow-sm'
                }`}
              >
                <span className="text-base leading-none">{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="p-6">
          {/* v1.5-D: Change Password tab (semua role) */}
          {activeTab === 'password' && (
            <ChangePasswordPanel />
          )}

          {/* Approval tab */}
          {activeTab === 'approval' && (
            <ApprovalPanel scope="all" title="Approval Kuitansi" />
          )}

          {/* Search tab */}
          {activeTab === 'search' && (
            <KuitansiSearchPanel
              scopeLabel="Pencarian di jemaat Anda"
              showJemaatColumn={role !== 'BENDAHARA'}
            />
          )}

          {/* User Management tab */}
          {activeTab === 'users' && (
            <div className="space-y-3">
              <h3 className="font-display text-xl text-sabbath-dark mb-4">Daftar User Aktif</h3>
              {users.filter((u) => u.is_active).length === 0 ? (
                <p className="text-gray-400 text-center py-8">Belum ada user aktif.</p>
              ) : (
                users.filter((u) => u.is_active).map((u) => (
                  <div key={u.id} className="bg-sabbath-light rounded-2xl p-4 flex justify-between items-center">
                    <div>
                      <p className="font-medium text-sabbath-dark">{u.nama_lengkap}</p>
                      <p className="text-xs text-gray-500">
                        {u.role} • {u.username} • WA: {u.nomor_whatsapp || '—'}
                      </p>
                    </div>
                    <button
                      onClick={() => handleDeleteUser(u.id, u.nama_lengkap)}
                      disabled={deletingId === u.id}
                      className="px-4 py-2 bg-red-50 text-red-600 rounded-xl text-sm font-medium hover:bg-red-100 disabled:opacity-50"
                    >
                      {deletingId === u.id ? 'Memproses...' : 'Nonaktifkan'}
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Backup tab */}
          {activeTab === 'backup' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display text-xl text-sabbath-dark">Database Backup</h3>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleBackup('binary')}
                    className="px-4 py-2 bg-sabbath-dark text-white rounded-xl text-sm font-medium hover:bg-black"
                  >
                    Backup Binary
                  </button>
                  <button
                    onClick={() => handleBackup('sql')}
                    className="px-4 py-2 bg-sabbath-gold text-white rounded-xl text-sm font-medium hover:bg-amber-600"
                  >
                    Backup SQL
                  </button>
                </div>
              </div>

              {backupLoading && <p className="text-sm text-gray-500">Loading...</p>}

              <div className="space-y-2">
                {backups.length === 0 && !backupLoading && (
                  <p className="text-sm text-gray-400">Belum ada backup.</p>
                )}
                {backups.map((b) => (
                  <div key={b.filename} className="bg-sabbath-light rounded-xl p-3 flex justify-between items-center text-sm">
                    <div>
                      <p className="font-mono text-gray-800">{b.filename}</p>
                      <p className="text-xs text-gray-500">
                        {(b.size_bytes / 1024).toFixed(1)} KB • {new Date(b.created_at).toLocaleString()} • {b.kind}
                      </p>
                    </div>
                    <button
                      onClick={() => handleRestore(b.filename)}
                      className="px-3 py-1 bg-sabbath-dark text-white rounded-xl text-xs font-medium hover:bg-black"
                    >
                      Restore
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Audit Logs tab */}
          {activeTab === 'audit' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display text-xl text-sabbath-dark">Audit Logs</h3>
                <input
                  type="text"
                  value={logsFilter}
                  onChange={(e) => setLogsFilter(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && fetchLogs(1)}
                  placeholder="Filter action (e.g., BLAST, REGISTER)..."
                  className="px-4 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-sabbath-gold"
                />
              </div>

              <p className="text-sm text-gray-600 mb-4">{logsCount} total logs</p>

              <div className="space-y-2 max-h-96 overflow-y-auto">
                {logs.map((l) => (
                  <div key={l.id} className="bg-sabbath-light rounded-xl p-3 text-sm">
                    <div className="flex justify-between">
                      <span className="font-mono text-xs font-bold text-sabbath-dark">{l.action}</span>
                      <span className="text-xs text-gray-500">
                        {new Date(l.created_at).toLocaleString()}
                      </span>
                    </div>
                    {l.payload_hash && (
                      <p className="text-xs text-gray-500 mt-1 font-mono">hash: {l.payload_hash}</p>
                    )}
                    {l.porsi_dana_misi > 0 && (
                      <p className="text-xs text-sabbath-green mt-1">
                        Porsi Misi: Rp {l.porsi_dana_misi.toLocaleString()}
                      </p>
                    )}
                  </div>
                ))}
              </div>

              {logsCount > 50 && (
                <div className="flex justify-center gap-3 mt-4">
                  <button
                    onClick={() => fetchLogs(Math.max(1, logsPage - 1))}
                    disabled={logsPage === 1}
                    className="px-4 py-2 border border-gray-300 rounded-xl text-sm disabled:opacity-50"
                  >
                    ← Prev
                  </button>
                  <span className="px-4 py-2 text-sm">Page {logsPage}</span>
                  <button
                    onClick={() => fetchLogs(logsPage + 1)}
                    disabled={logs.length < 50}
                    className="px-4 py-2 border border-gray-300 rounded-xl text-sm disabled:opacity-50"
                  >
                    Next →
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Branding tab */}
          {activeTab === 'branding' && (
            <div className="space-y-3">
              <h3 className="font-display text-xl text-sabbath-dark mb-2">Branding Jemaat</h3>
              <p className="text-gray-600 text-sm mb-4">
                Setting logo, primary/secondary color, dan footer text untuk jemaat Anda.
                Halaman ini sudah ada di /settings/branding — klik tombol di bawah untuk akses.
              </p>
              <a
                href="/settings/branding"
                className="inline-block px-5 py-2.5 bg-sabbath-dark text-white rounded-xl font-medium hover:bg-black"
              >
                Buka Branding Settings
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Settings;

// ===== v1.5-D: ChangePasswordPanel component =====
const ChangePasswordPanel = () => {
  const { logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (newPassword !== confirmPassword) {
      setError('Password baru dan konfirmasi tidak cocok.');
      return;
    }
    if (newPassword.length < 10) {
      setError('Password baru minimal 10 karakter.');
      return;
    }
    if (newPassword === currentPassword) {
      setError('Password baru tidak boleh sama dengan yang lama.');
      return;
    }

    setSubmitting(true);
    try {
      const r = await api.post('/v1/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setSuccess(r.data.message || 'Password berhasil diganti. Anda akan di-logout dalam 3 detik.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      // Auto-logout setelah 3 detik (semua device akan invalidate)
      setTimeout(() => {
        logout();
      }, 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal ganti password.');
    } finally {
      setSubmitting(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 14px',
    border: '1px solid #d1d5db',
    borderRadius: 10,
    fontSize: 14,
    outline: 'none',
    boxSizing: 'border-box',
  };

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: 12,
    fontWeight: 600,
    color: '#374151',
    marginBottom: 6,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  };

  return (
    <div style={{ maxWidth: 480 }}>
      <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, color: '#1B4332', margin: '0 0 4px 0', fontWeight: 700 }}>
        🔑 Ganti Password
      </h3>
      <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 20px 0' }}>
        Ganti password FLIPUS Anda. Setelah sukses, <strong>semua session di device lain otomatis logout</strong>.
      </p>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <label style={labelStyle}>Password Lama</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            autoComplete="current-password"
            style={inputStyle}
          />
        </div>

        <div>
          <label style={labelStyle}>Password Baru</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={10}
            autoComplete="new-password"
            style={inputStyle}
          />
          <p style={{ fontSize: 11, color: '#9ca3af', margin: '4px 0 0 0' }}>
            Minimal 10 karakter. Disarankan kombinasi huruf besar + kecil + angka + simbol.
          </p>
        </div>

        <div>
          <label style={labelStyle}>Konfirmasi Password Baru</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            autoComplete="new-password"
            style={inputStyle}
          />
        </div>

        {error && (
          <div style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#b91c1c',
            padding: 12,
            borderRadius: 10,
            fontSize: 13,
          }}>
            ❌ {error}
          </div>
        )}

        {success && (
          <div style={{
            background: '#ecfdf5',
            border: '1px solid #a7f3d0',
            color: '#065f46',
            padding: 12,
            borderRadius: 10,
            fontSize: 13,
          }}>
            ✅ {success}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !currentPassword || !newPassword || !confirmPassword}
          style={{
            padding: '12px 18px',
            background: submitting ? '#9ca3af' : '#1B4332',
            color: 'white',
            borderRadius: 10,
            fontSize: 14,
            fontWeight: 600,
            border: 'none',
            cursor: submitting ? 'wait' : 'pointer',
            boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
          }}
        >
          {submitting ? '⏳ Menyimpan...' : '🔑 Ganti Password'}
        </button>
      </form>
    </div>
  );
};
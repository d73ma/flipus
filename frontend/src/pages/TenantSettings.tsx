import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import api from '../lib/api';

interface BrandingResponse {
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  footer_text: string | null;
  branding_updated_at: string | null;
  branding_updated_by: number | null;
}

const PALETTE_PRESETS = [
  { name: 'Sabbath Green', primary: '#1B4332', secondary: '#F5EFE0' },
  { name: 'Royal Blue', primary: '#1E3A8A', secondary: '#EFF6FF' },
  { name: 'Sunset Orange', primary: '#C2410C', secondary: '#FFF7ED' },
  { name: 'Forest Maroon', primary: '#7F1D1D', secondary: '#FEF2F2' },
  { name: 'Midnight Navy', primary: '#0F172A', secondary: '#F1F5F9' },
  { name: 'Amber Gold', primary: '#B8860B', secondary: '#FFFBEB' },
];

export const TenantSettings = () => {
  const { tenant, refreshTenant } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [branding, setBranding] = useState<BrandingResponse>({
    logo_url: null,
    primary_color: '#1B4332',
    secondary_color: '#F5EFE0',
    footer_text: null,
    branding_updated_at: null,
    branding_updated_by: null,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!tenant) return;
    fetchBranding();
  }, [tenant?.id]);

  const fetchBranding = async () => {
    if (!tenant) return;
    try {
      const resp = await api.get(`/v1/tenants/${tenant.id}/branding`);
      setBranding(resp.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal load branding');
    } finally {
      setLoading(false);
    }
  };

  const handleColorChange = (field: 'primary_color' | 'secondary_color', value: string) => {
    setBranding((prev) => ({ ...prev, [field]: value }));
  };

  const handlePreset = (preset: typeof PALETTE_PRESETS[0]) => {
    setBranding((prev) => ({
      ...prev,
      primary_color: preset.primary,
      secondary_color: preset.secondary,
    }));
  };

  const handleSave = async () => {
    if (!tenant) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await api.patch(`/v1/tenants/${tenant.id}/branding`, {
        primary_color: branding.primary_color,
        secondary_color: branding.secondary_color,
        footer_text: branding.footer_text,
      });
      setSuccess('Branding berhasil disimpan');
      await refreshTenant();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal simpan branding');
    } finally {
      setSaving(false);
    }
  };

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!tenant || !e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await api.post(`/v1/tenants/${tenant.id}/logo`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      // Refresh branding
      await fetchBranding();
      setSuccess(`Logo berhasil di-upload (${resp.data.size_bytes} bytes)`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal upload logo');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleLogoRemove = async () => {
    if (!tenant) return;
    if (!confirm('Hapus logo? Branding akan kembali ke default.')) return;
    setError(null);
    setSuccess(null);
    try {
      await api.delete(`/v1/tenants/${tenant.id}/logo`);
      await fetchBranding();
      setSuccess('Logo dihapus');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Gagal hapus logo');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-sabbath-cream">
        <div className="text-sabbath-dark text-xl">Memuat branding...</div>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen p-8"
      style={{ backgroundColor: branding.secondary_color }}
    >
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <button
              onClick={() => navigate(-1)}
              className="text-sm text-gray-600 hover:text-gray-900 mb-2"
            >
              ← Kembali
            </button>
            <h1 className="text-3xl font-bold" style={{ color: branding.primary_color }}>
              Branding Jemaat
            </h1>
            <p className="text-gray-600 mt-1">{tenant?.nama_jemaat_lokal}</p>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
            {error}
          </div>
        )}

        {success && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded mb-4">
            {success}
          </div>
        )}

        {/* Logo upload */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-xl font-bold mb-4" style={{ color: branding.primary_color }}>
            Logo Jemaat
          </h2>
          <div className="flex items-center gap-6">
            <div className="flex-shrink-0">
              {branding.logo_url ? (
                <img
                  src={`/api/v1/tenants/logo/${tenant?.id}?t=${Date.now()}`}
                  alt="Logo"
                  className="w-32 h-32 object-contain border border-gray-200 rounded"
                />
              ) : (
                <div
                  className="w-32 h-32 flex items-center justify-center border-2 border-dashed border-gray-300 rounded text-gray-400 text-sm text-center"
                >
                  Belum ada logo
                </div>
              )}
            </div>
            <div className="flex-1">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/svg+xml"
                onChange={handleLogoUpload}
                className="hidden"
                id="logo-upload"
              />
              <label
                htmlFor="logo-upload"
                className="inline-block px-4 py-2 rounded text-white font-medium cursor-pointer"
                style={{ backgroundColor: branding.primary_color }}
              >
                {uploading ? 'Mengupload...' : 'Upload Logo'}
              </label>
              {branding.logo_url && (
                <button
                  onClick={handleLogoRemove}
                  className="ml-2 px-4 py-2 rounded border border-red-300 text-red-600 hover:bg-red-50"
                >
                  Hapus Logo
                </button>
              )}
              <p className="text-xs text-gray-500 mt-2">
                Format: PNG, JPG, atau SVG. Maks 1MB. Akan di-resize ke 512px jika lebih besar.
              </p>
            </div>
          </div>
        </div>

        {/* Colors */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-xl font-bold mb-4" style={{ color: branding.primary_color }}>
            Warna Brand
          </h2>

          {/* Presets */}
          <div className="mb-4">
            <label className="text-sm text-gray-700 mb-2 block">Preset:</label>
            <div className="grid grid-cols-3 gap-2">
              {PALETTE_PRESETS.map((p) => (
                <button
                  key={p.name}
                  onClick={() => handlePreset(p)}
                  className="p-2 border border-gray-200 rounded hover:border-gray-400 text-left"
                  style={{ backgroundColor: p.secondary }}
                >
                  <div className="flex items-center gap-2">
                    <div
                      className="w-6 h-6 rounded"
                      style={{ backgroundColor: p.primary }}
                    />
                    <span className="text-xs font-medium" style={{ color: p.primary }}>
                      {p.name}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Custom colors */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-gray-700 mb-1 block">Primary Color</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={branding.primary_color}
                  onChange={(e) => handleColorChange('primary_color', e.target.value)}
                  className="w-12 h-10 rounded border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={branding.primary_color}
                  onChange={(e) => handleColorChange('primary_color', e.target.value)}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded font-mono text-sm"
                  pattern="^#[0-9a-fA-F]{6}$"
                />
              </div>
            </div>
            <div>
              <label className="text-sm text-gray-700 mb-1 block">Secondary Color</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={branding.secondary_color}
                  onChange={(e) => handleColorChange('secondary_color', e.target.value)}
                  className="w-12 h-10 rounded border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={branding.secondary_color}
                  onChange={(e) => handleColorChange('secondary_color', e.target.value)}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded font-mono text-sm"
                  pattern="^#[0-9a-fA-F]{6}$"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Footer text */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-xl font-bold mb-4" style={{ color: branding.primary_color }}>
            Footer Text (PDF + WhatsApp)
          </h2>
          <textarea
            value={branding.footer_text || ''}
            onChange={(e) =>
              setBranding((prev) => ({ ...prev, footer_text: e.target.value }))
            }
            maxLength={255}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded"
            placeholder="Misal: 'GMAHK UKIKT - melayani dengan sukacita'"
          />
          <p className="text-xs text-gray-500 mt-1">
            {branding.footer_text?.length || 0} / 255 karakter
          </p>
        </div>

        {/* Preview */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-xl font-bold mb-4" style={{ color: branding.primary_color }}>
            Preview
          </h2>
          <div
            className="p-6 rounded"
            style={{ backgroundColor: branding.secondary_color, color: branding.primary_color }}
          >
            <div className="flex items-center gap-4 mb-4">
              {branding.logo_url && (
                <img
                  src={`/api/v1/tenants/logo/${tenant?.id}?t=${Date.now()}`}
                  alt="Logo"
                  className="w-16 h-16 object-contain"
                />
              )}
              <div>
                <h3 className="text-2xl font-bold" style={{ color: branding.primary_color }}>
                  {tenant?.nama_jemaat_lokal}
                </h3>
                <p className="text-sm" style={{ color: branding.primary_color }}>
                  {tenant?.nama_kantor_misi}
                </p>
              </div>
            </div>
            <p className="mb-4">Ini preview branding jemaat Anda.</p>
            {branding.footer_text && (
              <p className="text-xs italic text-gray-600 mt-4">{branding.footer_text}</p>
            )}
          </div>
        </div>

        {/* Save button */}
        <div className="flex justify-end gap-3">
          <button
            onClick={() => navigate(-1)}
            className="px-6 py-2 border border-gray-300 rounded"
          >
            Batal
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2 rounded text-white font-medium"
            style={{ backgroundColor: branding.primary_color }}
          >
            {saving ? 'Menyimpan...' : 'Simpan Branding'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default TenantSettings;

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';

// T27-Redesign: Login split-screen pakai identitas LandingPage.
// Palette & motif sama dengan flipus.org/gmahk.flipus.org:
//   - sabbath-dark (#1B4332), sabbath-gold (#B8860B),
//     sabbath-cream (#F5EFE0), sabbath-light (#FAF9F5)
//   - Signature: kolom perpuluhan (6 vertical gold/cream lines)
//   - Typography: Playfair Display + Inter (font-body)

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [error, setError] = useState('');
  const [requires2fa, setRequires2fa] = useState(false);
  const [partialToken, setPartialToken] = useState<string | null>(null);

  const { login, loginStep2 } = useAuth();
  const navigate = useNavigate();

  const redirectByRole = () => {
    const role = localStorage.getItem('role');
    if (role === 'BENDAHARA') navigate('/bendahara');
    else if (role === 'KETUA_KEUANGAN') navigate('/ketua');
    else if (role === 'PENDETA') navigate('/pendeta');
    else if (role === 'AUDITOR_MISI') navigate('/auditor');
    else if (role === 'ADMIN_UNI') navigate('/admin');
    else navigate('/');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      const result = await login(username, password);
      if (result && result.requires_2fa) {
        setRequires2fa(true);
        setPartialToken(result.partial_token || null);
      } else {
        redirectByRole();
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed');
    }
  };

  const handleSubmit2FA = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (!partialToken) {
        setError('Session 2FA expired, silakan login ulang');
        setRequires2fa(false);
        return;
      }
      await loginStep2(partialToken, totpCode);
      redirectByRole();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Kode 2FA salah');
    }
  };

  const handleBack = () => {
    setRequires2fa(false);
    setPartialToken(null);
    setTotpCode('');
    setError('');
  };

  // ===== Styles (inline, bullet-proof) =====
  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '14px 16px',
    border: '1.5px solid #e5e7eb',
    borderRadius: 12,
    fontSize: 14,
    color: '#1B4332',
    background: '#FAF9F5',
    outline: 'none',
    boxSizing: 'border-box',
    fontFamily: "'Inter', sans-serif",
    transition: 'border-color 0.15s, background 0.15s',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: 11,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    color: '#1B4332',
    marginBottom: 6,
    fontWeight: 600,
  };

  // ===== BrandPanel (kiri) — split-screen background =====
  const BrandPanel = () => (
    <div
      style={{
        position: 'relative',
        background: 'linear-gradient(135deg, #1B4332 0%, #0d2418 100%)',
        color: 'white',
        display: 'flex',
        flexDirection: 'column',
        padding: '40px 48px',
        overflow: 'hidden',
        minHeight: '100vh',
      }}
    >
      {/* Signature: kolom perpuluhan motif */}
      <div aria-hidden style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
        <div style={{ position: 'absolute', left: '8%', top: 0, bottom: 0, width: 1, background: 'linear-gradient(180deg, transparent, #B8860B, transparent)', opacity: 0.5 }} />
        <div style={{ position: 'absolute', right: '8%', top: 0, bottom: 0, width: 1, background: 'linear-gradient(180deg, transparent, #B8860B, transparent)', opacity: 0.5 }} />
        <div style={{ position: 'absolute', left: '14%', top: 0, bottom: 0, width: 1, background: 'linear-gradient(180deg, transparent, #F5EFE0, transparent)', opacity: 0.7 }} />
        <div style={{ position: 'absolute', right: '14%', top: 0, bottom: 0, width: 1, background: 'linear-gradient(180deg, transparent, #F5EFE0, transparent)', opacity: 0.7 }} />
        <div style={{ position: 'absolute', left: '20%', top: 0, bottom: 0, width: 1, background: 'linear-gradient(180deg, transparent, #F5EFE0, transparent)', opacity: 0.4 }} />
        <div style={{ position: 'absolute', right: '20%', top: 0, bottom: 0, width: 1, background: 'linear-gradient(180deg, transparent, #F5EFE0, transparent)', opacity: 0.4 }} />
      </div>

      {/* Top: FLIPUS wordmark only (text-only, logo dipindah ke form panel) */}
      <div style={{ position: 'relative' }}>
        <Link to="/" style={{ display: 'inline-flex', flexDirection: 'column', textDecoration: 'none', lineHeight: 1.1 }}>
          <div style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: 'white', letterSpacing: '0.04em' }}>
            FLIPUS
          </div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.7)', letterSpacing: '0.2em', textTransform: 'uppercase', marginTop: 4 }}>
            GMAHK · UKIKT
          </div>
        </Link>
      </div>

      {/* Middle center: SISTEM PERPULUHAN GMAHK eyebrow + italic quote */}
      <div style={{ position: 'relative', flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ maxWidth: 460, textAlign: 'center' }}>
          <p style={{ fontSize: 10, letterSpacing: '0.3em', textTransform: 'uppercase', color: '#B8860B', marginBottom: 16, fontWeight: 600 }}>
            Sistem Perpuluhan GMAHK
          </p>
          <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, lineHeight: 1.4, fontStyle: 'italic', color: '#F5EFE0', margin: 0 }}>
            "Mewujudkan tata kelola persembahan yang terbuka, akuntabel, dan modern —
            untuk kemuliaan nama Tuhan."
          </p>
        </div>
      </div>

      {/* Bottom: small meta */}
      <div style={{ position: 'relative', textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.5)', letterSpacing: '0.2em', textTransform: 'uppercase' }}>
        v1.3 · © 2026 GMAHK UKIKT
      </div>
    </div>
  );

  // ===== 2FA Step 2 — same BrandPanel on left, 2FA form on right =====
  if (requires2fa) {
    return (
      <div style={{ display: 'flex', minHeight: '100vh', fontFamily: "'Inter', sans-serif" }}>
        <div style={{ flex: '0 0 45%' }}>
          <BrandPanel />
        </div>
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
            background: '#FAF9F5',
          }}
        >
          <div style={{ width: '100%', maxWidth: 380 }}>
            <p style={{ fontSize: 11, letterSpacing: '0.25em', textTransform: 'uppercase', color: '#1B4332', fontWeight: 600, marginBottom: 8 }}>
              Verifikasi 2 Langkah
            </p>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 32, color: '#1B4332', margin: '0 0 8px 0', fontWeight: 700 }}>
              Konfirmasi Kode
            </h1>
            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 32 }}>
              Login sebagai <strong style={{ color: '#1B4332' }}>{username}</strong>.
              Masukkan kode 6-digit dari Authenticator app.
            </p>

            <form onSubmit={handleSubmit2FA} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <label style={labelStyle}>Kode 2FA / Backup Code</label>
                <input
                  type="text"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  placeholder="123456"
                  maxLength={10}
                  autoFocus
                  required
                  style={{
                      ...inputStyle,
                      textAlign: 'center',
                      fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                      fontSize: 22,
                      letterSpacing: '0.3em',
                    }}
                />
                <p style={{ fontSize: 11, color: '#6b7280', marginTop: 6, textAlign: 'center' }}>
                  Atau backup code: ABC12-DEF34
                </p>
              </div>

              {error && (
                <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: 12, borderRadius: 10, fontSize: 12 }}>
                  {error}
                </div>
              )}

              <button
                type="submit"
                style={{
                  width: '100%',
                  padding: '14px 16px',
                  background: '#1B4332',
                  color: 'white',
                  border: 'none',
                  borderRadius: 12,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  letterSpacing: '0.02em',
                }}
              >
                Verifikasi
              </button>

              <button
                type="button"
                onClick={handleBack}
                style={{
                  width: '100%',
                  padding: '10px 16px',
                  background: 'transparent',
                  color: '#1B4332',
                  border: 'none',
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                ← Kembali ke login
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // ===== Standard login — split-screen =====
  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: "'Inter', sans-serif" }}>
      {/* BrandPanel — hidden on mobile */}
      <div className="hidden md:block" style={{ flex: '0 0 45%' }}>
        <BrandPanel />
      </div>

      {/* Form panel */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          background: '#FAF9F5',
        }}
      >
        <div style={{ width: '100%', maxWidth: 380 }}>
          {/* Top: Brand block — logo + FLIPUS + GMAHK · UKIKT */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
            <img
              src="/gmahk-logo.png"
              alt="GMAHK UKIKT"
              style={{ width: 44, height: 44, objectFit: 'contain', flexShrink: 0 }}
            />
            <div>
              <div style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#1B4332', lineHeight: 1.1 }}>
                FLIPUS
              </div>
              <div style={{ fontSize: 10, color: '#6b7280', letterSpacing: '0.2em', textTransform: 'uppercase', marginTop: 2 }}>
                GMAHK · UKIKT
              </div>
            </div>
          </div>

          <p style={{ fontSize: 11, letterSpacing: '0.25em', textTransform: 'uppercase', color: '#1B4332', fontWeight: 600, marginBottom: 8 }}>
            Sistem Perpuluhan GMAHK
          </p>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 36, color: '#1B4332', margin: '0 0 8px 0', fontWeight: 700, letterSpacing: '-0.01em' }}>
            Masuk ke FLIPUS
          </h1>
          <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 32 }}>
            Catatan perpuluhan &amp; persembahan sabat yang terbuka, akuntabel, dan modern.
          </p>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div>
              <label style={labelStyle}>Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="bendahara / pendeta / ketua_keuangan"
                required
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                style={inputStyle}
              />
            </div>

            {error && (
              <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: 12, borderRadius: 10, fontSize: 12 }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              style={{
                width: '100%',
                padding: '14px 16px',
                background: '#1B4332',
                color: 'white',
                border: 'none',
                borderRadius: 12,
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
                letterSpacing: '0.02em',
                marginTop: 4,
              }}
            >
              Masuk
            </button>
          </form>

          <div style={{ marginTop: 28, paddingTop: 20, borderTop: '1px solid #e5e7eb', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <Link to="/forgot-password" style={{ fontSize: 13, color: '#1B4332', textDecoration: 'none' }}>
              Lupa password?
            </Link>
            <p style={{ fontSize: 13, color: '#6b7280', margin: 0 }}>
              Belum punya akun?{' '}
              <Link to="/register/pendeta" style={{ color: '#1B4332', textDecoration: 'none', fontWeight: 600 }}>
                Daftar di sini
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
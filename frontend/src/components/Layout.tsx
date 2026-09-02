import { useEffect } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import NotificationBell from './NotificationBell';
import useDemoMode from '../lib/useDemoMode';

// T31-Redesign: Layout pakai identitas LandingPage.
//   - Brand block: G circle + FLIPUS wordmark + GMAHK·UKIKT subline
//   - Sidebar nav dengan active highlight + hover gold
//   - Header bg pakai tenant primary_color (gradient)
//   - Role badge style eyebrow pill (uppercase tracking)
//   - Palette: #1B4332 / #B8860B / #F5EFE0 / #FAF9F5

const navItems = [
  { to: '/bendahara', label: 'Bendahara', roles: ['BENDAHARA'] },
  { to: '/bendahara/pengeluaran', label: '💸 Pengeluaran', roles: ['BENDAHARA'] },
  { to: '/ketua', label: 'Ketua Keuangan', roles: ['BENDAHARA', 'KETUA_KEUANGAN'] },
  { to: '/ketua/pengeluaran', label: '💸 Approve Pengeluaran', roles: ['KETUA_KEUANGAN'] },
  { to: '/pendeta', label: 'Pendeta', roles: ['PENDETA'] },
  { to: '/pendeta/pengeluaran', label: '💸 Approve Pengeluaran', roles: ['PENDETA'] },
  { to: '/auditor', label: 'Auditor Misi', roles: ['AUDITOR_MISI'] },
  { to: '/admin', label: 'Admin Uni', roles: ['ADMIN_UNI'] },
];
const navItemsSettings = [
  { to: '/settings', label: '⚙️ Settings' },
  { to: '/notifications', label: '🔔 Notifikasi' },
];

// Brand block reusable (compact & full)
const BrandBlock = ({ size = 'sm' }: { size?: 'sm' | 'md' }) => {
  const isMd = size === 'md';
  const imgSize = isMd ? 40 : 36;
  return (
    <Link to="/" style={{ display: 'inline-flex', alignItems: 'center', gap: isMd ? 14 : 12, textDecoration: 'none' }}>
      <img
        src="/gmahk-logo.png"
        alt="GMAHK UKIKT"
        style={{ width: imgSize, height: imgSize, objectFit: 'contain', flexShrink: 0 }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
        <div
          style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: isMd ? 22 : 20,
            fontWeight: 700,
            color: '#1B4332',
            letterSpacing: '0.04em',
          }}
        >
          FLIPUS
        </div>
        <div
          style={{
            fontSize: 10,
            color: '#6b7280',
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            marginTop: 2,
          }}
        >
          GMAHK · UKIKT
        </div>
      </div>
    </Link>
  );
};

const Layout = () => {
  const { logout, role, tenant } = useAuth();
  const { isDemo, secondsLeft } = useDemoMode();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const root = document.documentElement;
    if (tenant?.primary_color) {
      root.style.setProperty('--tenant-primary', tenant.primary_color);
    }
    if (tenant?.secondary_color) {
      root.style.setProperty('--tenant-secondary', tenant.secondary_color);
    }
  }, [tenant?.primary_color, tenant?.secondary_color]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const primaryColor = tenant?.primary_color || '#1B4332';
  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + '/');

  const linkStyle = (active: boolean): React.CSSProperties => ({
    display: 'block',
    padding: '11px 14px',
    borderRadius: 10,
    fontSize: 14,
    fontWeight: 500,
    color: active ? '#1B4332' : '#374151',
    textDecoration: 'none',
    background: active ? '#FAF9F5' : 'transparent',
    borderLeft: active ? '3px solid #B8860B' : '3px solid transparent',
    transition: 'all 0.15s',
  });

  return (
    <div style={{ minHeight: '100vh', background: '#FAF9F5', fontFamily: "'Inter', sans-serif" }}>
      {/* Demo mode banner */}
      {isDemo && (
        <div
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 60,
            background: '#facc15',
            color: '#713f12',
            padding: '10px 24px',
            fontSize: 13,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '2px solid #eab308',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 16 }}>⚠️</span>
            <span>
              <strong>MODE DEMO</strong> — Anda masuk sebagai user demo.{' '}
              <span style={{ opacity: 0.85 }}>Tombol destruktif disabled.</span>
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontFamily: "'JetBrains Mono', 'Courier New', monospace", fontSize: 12 }}>
              Auto-logout: {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, '0')}
            </span>
            <button
              onClick={handleLogout}
              style={{
                padding: '4px 12px',
                background: '#713f12',
                color: '#fefce8',
                border: 'none',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Keluar Demo
            </button>
          </div>
        </div>
      )}

      {/* Header — gradient bg dari tenant primary color */}
      <header
        style={{
          background: `linear-gradient(135deg, ${primaryColor} 0%, ${primaryColor}dd 100%)`,
          color: 'white',
          position: 'sticky',
          top: 0,
          zIndex: 50,
          boxShadow: '0 1px 0 rgba(0,0,0,0.06)',
        }}
      >
        <div
          style={{
            maxWidth: 1280,
            margin: '0 auto',
            padding: '14px 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          {/* Brand */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* GMAHK logo + FLIPUS wordmark (LandingPage identity) */}
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12, color: 'white' }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 10,
                  background: 'rgba(255,255,255,0.95)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  padding: 4,
                }}
              >
                <img
                  src="/gmahk-logo.png"
                  alt="GMAHK"
                  style={{ width: 36, height: 36, objectFit: 'contain' }}
                />
              </div>
              <div style={{ lineHeight: 1.1 }}>
                <div
                  style={{
                    fontFamily: "'Playfair Display', serif",
                    fontSize: 20,
                    fontWeight: 700,
                    color: 'white',
                    letterSpacing: '0.04em',
                  }}
                >
                  FLIPUS
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: 'rgba(255,255,255,0.7)',
                    letterSpacing: '0.2em',
                    textTransform: 'uppercase',
                    marginTop: 2,
                  }}
                >
                  GMAHK · UKIKT
                </div>
              </div>
            </div>

            {/* Tenant info (separator dot) */}
            {tenant && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  paddingLeft: 16,
                  borderLeft: '1px solid rgba(255,255,255,0.2)',
                  color: 'rgba(255,255,255,0.85)',
                  fontSize: 12,
                }}
              >
                {tenant.logo_url ? (
                  <img
                    src={`/api/v1/tenants/logo/${tenant.id}?t=${Date.now()}`}
                    alt="Logo"
                    style={{ width: 36, height: 36, objectFit: 'contain', background: 'white', borderRadius: 6 }}
                  />
                ) : null}
                <div style={{ lineHeight: 1.25 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: 'white' }}>{tenant.nama_jemaat_lokal}</div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.7)' }}>{tenant.nama_uni}</div>
                </div>
              </div>
            )}
          </div>

          {/* Right: role badge + actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span
              style={{
                padding: '6px 14px',
                background: 'rgba(255,255,255,0.18)',
                border: '1px solid rgba(255,255,255,0.3)',
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 600,
                color: 'white',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
              }}
            >
              {role}
            </span>

            {role === 'ADMIN_UNI' && (
              <Link
                to="/settings/branding"
                style={{ fontSize: 13, color: 'rgba(255,255,255,0.85)', textDecoration: 'none' }}
              >
                ⚙ Branding
              </Link>
            )}

            <NotificationBell />

            <Link
              to="/settings/2fa"
              style={{ fontSize: 13, color: 'rgba(255,255,255,0.85)', textDecoration: 'none' }}
            >
              🔒 2FA
            </Link>

            <button
              onClick={handleLogout}
              style={{
                background: 'transparent',
                border: 'none',
                fontSize: 13,
                color: 'rgba(255,255,255,0.85)',
                cursor: 'pointer',
                padding: 0,
              }}
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div style={{ maxWidth: 1280, margin: '0 auto', display: 'flex' }}>
        {/* Sidebar */}
        <nav
          style={{
            position: 'relative',
            width: 256,
            background: 'white',
            borderRight: '1px solid #e5e7eb',
            minHeight: 'calc(100vh - 72px)',
            padding: '24px 16px',
          }}
        >
          {/* Brand block di sidebar (mini) */}
          <div style={{ padding: '0 6px 16px 6px', borderBottom: '1px solid #F5EFE0', marginBottom: 16 }}>
            <BrandBlock size="sm" />
            <p
              style={{
                fontSize: 10,
                color: '#6b7280',
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                marginTop: 10,
                fontWeight: 600,
              }}
            >
              Sistem Perpuluhan
            </p>
          </div>

          {/* Main nav */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 12 }}>
            {navItems.filter((item) => !item.roles || item.roles.includes(role)).map((item) => (
              <Link
                key={item.to}
                to={item.to}
                style={linkStyle(isActive(item.to))}
                onMouseEnter={(e) => {
                  if (!isActive(item.to)) {
                    (e.currentTarget as HTMLElement).style.background = '#FAF9F5';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive(item.to)) {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                {item.label}
              </Link>
            ))}
          </div>

          {/* Settings group */}
          <div
            style={{
              paddingTop: 16,
              marginTop: 16,
              borderTop: '1px solid #F5EFE0',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
            }}
          >
            {navItemsSettings.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                style={linkStyle(isActive(item.to))}
                onMouseEnter={(e) => {
                  if (!isActive(item.to)) {
                    (e.currentTarget as HTMLElement).style.background = '#FAF9F5';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive(item.to)) {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                {item.label}
              </Link>
            ))}
          </div>

          {/* Footer meta */}
          <div
            style={{
              position: 'absolute',
              bottom: 16,
              left: 16,
              right: 16,
              fontSize: 10,
              color: '#9ca3af',
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              textAlign: 'center',
              borderTop: '1px solid #F5EFE0',
              paddingTop: 12,
            }}
          >
            v1.3 · © 2026 GMAHK UKIKT
          </div>
        </nav>

        {/* Main */}
        <main style={{ flex: 1, padding: 32, minHeight: 'calc(100vh - 72px)' }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default Layout;
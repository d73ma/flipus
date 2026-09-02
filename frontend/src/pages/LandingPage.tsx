import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../lib/auth';

interface TenantPreview {
  slug: string;
  nama_jemaat: string;
  nama_uni: string;
  initial: string;
  primary_color: string;
  secondary_color: string;
  logo_url: string | null;
  footer_text: string | null;
  demo_user_count: number;
}

const LandingPage = () => {
  const { isAuthenticated } = useAuth();
  const [tenants, setTenants] = useState<TenantPreview[]>([]);

  useEffect(() => {
    fetch('/api/v1/demo/tenants')
      .then((r) => r.json())
      .then((data) => setTenants(Array.isArray(data) ? data : []))
      .catch(() => setTenants([]));
  }, []);

  // Kalau sudah login, tidak perlu lihat landing — langsung ke dashboard
  if (isAuthenticated) {
    const role = localStorage.getItem('role');
    const dest =
      role === 'BENDAHARA' ? '/bendahara' :
      role === 'KETUA_KEUANGAN' ? '/ketua' :
      role === 'PENDETA' ? '/pendeta' :
      role === 'AUDITOR_MISI' ? '/auditor' :
      role === 'ADMIN_UNI' ? '/admin' : '/login';
    window.location.href = dest;
    return null;
  }

  return (
    <div className="min-h-screen bg-white text-sabbath-charcoal font-body">
      {/* ============ HEADER ============ */}
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-sabbath-cream">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-full bg-white border-2 border-sabbath-gold flex items-center justify-center p-1.5">
              <img
                src="/gmahk-logo.png"
                alt="GMAHK UKIKT"
                style={{ width: 32, height: 32, objectFit: 'contain' }}
              />
            </div>
            <div className="leading-tight">
              <div className="font-display text-xl font-bold text-sabbath-dark tracking-wide">
                FLIPUS
              </div>
              <div className="text-[10px] text-gray-500 tracking-[0.18em] uppercase">
                GMAHK · UKIKT
              </div>
            </div>
          </Link>
          <nav className="hidden md:flex items-center gap-7 text-sm font-medium">
            <a href="#tentang" className="text-sabbath-charcoal hover:text-sabbath-dark transition-colors">Tentang</a>
            <a href="#fitur" className="text-sabbath-charcoal hover:text-sabbath-dark transition-colors">Fitur</a>
            <a href="#statistik" className="text-sabbath-charcoal hover:text-sabbath-dark transition-colors">Statistik</a>
            <a href="#demo" className="text-sabbath-charcoal hover:text-sabbath-dark transition-colors">Demo</a>
            <Link
              to="/login"
              className="px-4 py-2 bg-sabbath-dark text-white rounded-lg font-semibold hover:bg-black transition-colors"
            >
              Masuk
            </Link>
          </nav>
        </div>
      </header>

      {/* ============ HERO ============ */}
      <section className="relative px-6 pt-16 pb-24 bg-white overflow-hidden">
        {/* Signature: kolom perpuluhan pattern */}
        <div className="absolute inset-0 pointer-events-none" aria-hidden>
          <div className="absolute left-[8%] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-sabbath-gold/40 to-transparent" />
          <div className="absolute right-[8%] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-sabbath-gold/40 to-transparent" />
          <div className="absolute left-[14%] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-sabbath-cream to-transparent" />
          <div className="absolute right-[14%] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-sabbath-cream to-transparent" />
          <div className="absolute left-[20%] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-sabbath-cream/60 to-transparent" />
          <div className="absolute right-[20%] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-sabbath-cream/60 to-transparent" />
        </div>

        <div className="relative max-w-3xl mx-auto text-center">
          <span className="inline-block text-[11px] tracking-[0.25em] uppercase text-sabbath-dark/70 font-semibold mb-6 px-3.5 py-1.5 border border-sabbath-cream rounded-full bg-sabbath-light">
            Sistem Perpuluhan GMAHK
          </span>
          <h1 className="font-display text-6xl md:text-8xl font-bold text-sabbath-dark leading-[1.05] mb-6 tracking-tight">
            FLIPUS
          </h1>
          <p className="text-lg md:text-xl text-gray-600 max-w-xl mx-auto mb-9 leading-relaxed">
            Catatan perpuluhan &amp; persembahan sabat yang terbuka, akuntabel, dan modern —
            untuk pelayanan gereja di era digital.
          </p>
          <div className="flex justify-center gap-3 mb-16">
            <a
              href="#demo"
              className="px-7 py-3.5 bg-sabbath-dark text-white rounded-xl font-semibold hover:bg-black transition-all shadow-md hover:shadow-lg inline-flex items-center gap-2"
            >
              Lihat Demo
              <span>→</span>
            </a>
            <Link
              to="/login"
              className="px-7 py-3.5 border-[1.5px] border-sabbath-dark text-sabbath-dark rounded-xl font-semibold hover:bg-sabbath-light transition-colors"
            >
              Masuk
            </Link>
          </div>

          {/* Dashboard mockup (CSS-rendered) */}
          <div className="max-w-2xl mx-auto perspective-1200">
            <div className="bg-white rounded-2xl shadow-2xl border border-sabbath-cream overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 bg-sabbath-light border-b border-sabbath-cream">
                <div className="w-3 h-3 rounded-full bg-red-400" />
                <div className="w-3 h-3 rounded-full bg-yellow-400" />
                <div className="w-3 h-3 rounded-full bg-green-400" />
                <span className="font-mono text-[11px] text-gray-500 ml-3">
                  flipus.org/bendahara
                </span>
              </div>
              <div className="p-6">
                <div className="grid grid-cols-3 gap-3 mb-5">
                  <div className="p-4 bg-sabbath-light rounded-xl border border-sabbath-cream">
                    <div className="text-[10px] tracking-widest uppercase text-gray-500 mb-1.5">
                      Perpuluhan (X)
                    </div>
                    <div className="font-mono text-lg font-bold text-sabbath-dark">
                      Rp 8.450.000
                    </div>
                    <div className="text-[11px] text-sabbath-dark/70 mt-1">
                      ↑ 12% dari minggu lalu
                    </div>
                  </div>
                  <div className="p-4 bg-sabbath-light rounded-xl border border-sabbath-cream">
                    <div className="text-[10px] tracking-widest uppercase text-gray-500 mb-1.5">
                      Persembahan (PT)
                    </div>
                    <div className="font-mono text-lg font-bold text-sabbath-dark">
                      Rp 3.200.000
                    </div>
                    <div className="text-[11px] text-sabbath-dark/70 mt-1">
                      ↑ 5% dari minggu lalu
                    </div>
                  </div>
                  <div className="p-4 bg-sabbath-light rounded-xl border border-sabbath-cream">
                    <div className="text-[10px] tracking-widest uppercase text-gray-500 mb-1.5">
                      Kuitansi Sabat
                    </div>
                    <div className="font-mono text-lg font-bold text-sabbath-dark">38</div>
                    <div className="text-[11px] text-sabbath-dark/70 mt-1">
                      Sabat · 15 Ags 2026
                    </div>
                  </div>
                </div>
                <div className="h-24 bg-sabbath-light rounded-xl border border-sabbath-cream p-3.5">
                  <div className="flex items-end h-full gap-1.5">
                    {[35, 50, 42, 65, 58, 80, 72, 88, 95, 78, 90, 100].map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-t-sm bg-gradient-to-t from-sabbath-gold to-sabbath-dark opacity-85"
                        style={{ height: `${h}%` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ SLOGAN BAR ============ */}
      <section className="bg-sabbath-dark text-white py-10 px-6 text-center">
        <p className="max-w-3xl mx-auto font-display text-xl md:text-2xl italic leading-relaxed text-sabbath-gold">
          "Mewujudkan tata kelola persembahan yang terbuka, akuntabel, dan modern —
          untuk kemuliaan nama Tuhan."
        </p>
        <span className="block mt-3 text-[10px] tracking-[0.2em] uppercase text-white/60">
          FLIPUS · GMAHK UKIKT
        </span>
      </section>

      {/* ============ FEATURES ============ */}
      <section id="fitur" className="px-6 py-24 bg-white">
        <div className="max-w-5xl mx-auto">
          <div className="text-[11px] tracking-[0.25em] uppercase text-sabbath-dark/70 font-semibold mb-3.5">
            Fitur Utama
          </div>
          <h2 className="font-display text-4xl md:text-5xl text-sabbath-dark mb-3.5 leading-tight">
            Dibangun untuk tata kelola gereja
          </h2>
          <p className="text-base text-gray-600 max-w-xl mb-12">
            Tiga hal yang paling banyak diminta oleh bendahara, ketua, dan admin misi —
            langsung jadi sederhana.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Feature
              icon="⛪"
              title="Multi-Tenant"
              desc="Setiap jemaat, misi, dan uni punya ruang sendiri. Data terpisah, branding terpisah, persentasi pembagian dikontrol Auditor."
            />
            <Feature
              icon="📷"
              title="OCR Amplop"
              desc="Foto amplop perpuluhan, sistem otomatis membaca nominal. Bendahara tinggal verifikasi, simpan, kirim."
            />
            <Feature
              icon="📨"
              title="WA Otomatis"
              desc="Laporan mingguan ke Pendeta via WhatsApp dengan lampiran PDF. Auto-thanks ke pemberi kalau nomornya terbaca."
            />
          </div>
        </div>
      </section>

      {/* ============ JEMAAT PREVIEW (T32: Branding berbeda tiap jemaat) ============ */}
      {tenants.length > 0 && (
        <section id="jemaat" className="px-6 py-24 bg-sabbath-light border-y border-sabbath-cream">
          <div className="max-w-5xl mx-auto">
            <div className="text-[11px] tracking-[0.25em] uppercase text-sabbath-dark/70 font-semibold mb-3.5">
              Multi-Tenant Branding
            </div>
            <h2 className="font-display text-4xl md:text-5xl text-sabbath-dark mb-3.5 leading-tight">
              Setiap jemaat punya identitasnya sendiri
            </h2>
            <p className="text-base text-gray-600 max-w-xl mb-12">
              Pilih jemaat untuk masuk demo — warna, logo, dan footer bisa diatur
              sendiri oleh admin jemaat. Klik kartu untuk pengalaman multi-tenant.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-7">
              {tenants.map((t) => (
                <TenantBrandingCard key={t.slug} t={t} />
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ============ STATS ============ */}
      <section
        id="statistik"
        className="bg-sabbath-light py-14 px-6 border-y border-sabbath-cream"
      >
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-7 text-center">
          <Stat num="12" unit="+" label="Jemaat" />
          <Stat num="5" label="Misi Konferens" />
          <Stat num="1" label="Uni" />
          <Stat num="99.9" unit="%" label="Uptime" />
        </div>
      </section>

      {/* ============ DEMO CTA ============ */}
      <section id="demo" className="px-6 py-20 bg-white text-center">
        <div className="max-w-2xl mx-auto">
          <div className="text-[11px] tracking-[0.25em] uppercase text-sabbath-dark/70 font-semibold mb-3.5">
            Coba Sekarang
          </div>
          <h2 className="font-display text-3xl md:text-4xl text-sabbath-dark mb-4">
            Lihat FLIPUS dari sudut pandang setiap peran
          </h2>
          <p className="text-base text-gray-600 mb-9">
            Masuk sebagai Bendahara, Ketua, Pendeta, atau Auditor — tanpa daftar.
            Data dummy, banner mode demo, auto-expire 30 menit.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <DemoButton role="bendahara" label="Coba sebagai Bendahara" />
            <DemoButton role="ketua" label="Coba sebagai Ketua" />
            <DemoButton role="pendeta" label="Coba sebagai Pendeta" />
            <DemoButton role="auditor" label="Coba sebagai Auditor" />
          </div>
          <p className="mt-6 text-xs text-gray-400">
            Mode demo: tombol destruktif (delete, blast WA real, restore DB) otomatis disabled.
          </p>
        </div>
      </section>

      {/* ============ FOOTER ============ */}
      <footer className="bg-sabbath-dark text-white/70 px-6 py-12">
        <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-10 mb-8">
          <div>
            <h4 className="text-sabbath-gold text-[10px] tracking-[0.2em] uppercase mb-3 font-semibold">
              FLIPUS
            </h4>
            <p className="text-sm leading-relaxed">
              Sistem Informasi Perpuluhan &amp; Persembahan GMAHK UIKT.
              Dirancang untuk transparansi, akuntabilitas, dan kemuliaan Tuhan.
            </p>
          </div>
          <div>
            <h4 className="text-sabbath-gold text-[10px] tracking-[0.2em] uppercase mb-3 font-semibold">
              Kontak
            </h4>
            <p className="text-sm">GMAHK Uni Konferens Indonesia Kawasan Timur</p>
            <p className="text-sm">support@flipus.org</p>
          </div>
          <div>
            <h4 className="text-sabbath-gold text-[10px] tracking-[0.2em] uppercase mb-3 font-semibold">
              Tautan
            </h4>
            <a href="#tentang" className="block text-sm hover:text-sabbath-gold transition-colors">Tentang</a>
            <a href="#fitur" className="block text-sm hover:text-sabbath-gold transition-colors">Fitur</a>
            <Link to="/login" className="block text-sm hover:text-sabbath-gold transition-colors">Masuk</Link>
            <Link to="/register" className="block text-sm hover:text-sabbath-gold transition-colors">Daftar</Link>
          </div>
        </div>
        <div className="max-w-5xl mx-auto pt-5 border-t border-white/10 flex flex-wrap justify-between items-center gap-2 text-[11px] text-white/50">
          <span>© 2026 GMAHK UKIKT. All rights reserved.</span>
          <span>v1.3 · build 2026.08</span>
        </div>
      </footer>
    </div>
  );
};

// ============= SUB-COMPONENTS =============

const Feature = ({ icon, title, desc }: { icon: string; title: string; desc: string }) => (
  <div className="p-7 rounded-2xl bg-sabbath-light border border-sabbath-cream hover:shadow-lg hover:-translate-y-0.5 transition-all">
    <div className="w-12 h-12 rounded-xl bg-sabbath-dark text-sabbath-gold flex items-center justify-center text-2xl mb-5">
      {icon}
    </div>
    <h3 className="font-display text-2xl text-sabbath-dark mb-2">{title}</h3>
    <p className="text-sm text-gray-600 leading-relaxed">{desc}</p>
  </div>
);

const Stat = ({ num, unit, label }: { num: string; unit?: string; label: string }) => (
  <div>
    <div className="font-display text-4xl md:text-5xl font-bold text-sabbath-dark leading-none mb-2">
      {num}
      {unit && <span className="text-sabbath-gold text-3xl md:text-4xl">{unit}</span>}
    </div>
    <div className="text-[10px] tracking-[0.2em] uppercase text-gray-500">{label}</div>
  </div>
);

const DemoButton = ({ role, label }: { role: string; label: string }) => (
  <button
    onClick={async () => {
      try {
        const r = await fetch(`/api/v1/demo/login-as/${role}`);
        if (!r.ok) throw new Error('demo login failed');
        const data = await r.json();
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('role', data.role);
        localStorage.setItem('tenant_id', String(data.tenant_id));
        localStorage.setItem('tenant_slug', data.tenant_slug || '');
        localStorage.setItem('is_demo', 'true');
        localStorage.setItem(
          'demo_expires_at',
          String(Date.now() + (data.expires_in_minutes || 30) * 60 * 1000),
        );
        window.location.href = data.redirect_to || '/';
      } catch (e) {
        alert('Gagal masuk mode demo. Coba lagi nanti.');
      }
    }}
    className="px-5 py-2.5 rounded-lg text-sm font-semibold border-[1.5px] border-sabbath-dark text-sabbath-dark bg-white hover:bg-sabbath-light transition-colors"
  >
    {label}
  </button>
);

// ===== T32: Branding preview card (clickable → demo) =====
const TenantBrandingCard = ({ t }: { t: TenantPreview }) => {
  const [loading, setLoading] = useState(false);

  const enterDemo = async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/v1/demo/login-as/bendahara?tenant_slug=${t.slug}`);
      if (!r.ok) throw new Error('demo login failed');
      const data = await r.json();
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('role', data.role);
      localStorage.setItem('tenant_id', String(data.tenant_id));
      localStorage.setItem('tenant_slug', data.tenant_slug || '');
      localStorage.setItem('is_demo', 'true');
      localStorage.setItem(
        'demo_expires_at',
        String(Date.now() + (data.expires_in_minutes || 30) * 60 * 1000),
      );
      window.location.href = data.redirect_to || '/';
    } catch (e) {
      alert('Gagal masuk mode demo. Coba lagi nanti.');
      setLoading(false);
    }
  };

  // Logo URL handling — kalau path relatif (logos/x.svg), prefix dengan /api/v1/demo/tenants-logo atau langsung dari static
  // Default: kita serve dari /static/logos/ (sesuai seed_demo.py)
  const logoSrc = t.logo_url
    ? t.logo_url.startsWith('http')
      ? t.logo_url
      : `/storage/${t.logo_url}`
    : null;

  return (
    <div
      className="bg-white rounded-2xl border border-sabbath-cream overflow-hidden hover:shadow-2xl hover:-translate-y-1 transition-all group"
      style={{
        // Inject tenant primary color as accent
        ['--tenant-primary' as string]: t.primary_color,
        ['--tenant-secondary' as string]: t.secondary_color,
      }}
    >
      {/* Header strip dengan warna jemaat */}
      <div
        className="h-24 px-6 flex items-center justify-between relative overflow-hidden"
        style={{
          background: `linear-gradient(135deg, ${t.primary_color} 0%, ${t.primary_color}dd 100%)`,
          color: t.secondary_color || '#F5EFE0',
        }}
      >
        <div className="absolute inset-0 opacity-10" aria-hidden>
          <div className="absolute left-[20%] top-0 bottom-0 w-px bg-white" />
          <div className="absolute right-[20%] top-0 bottom-0 w-px bg-white" />
        </div>
        <div className="relative flex items-center gap-3">
          {logoSrc ? (
            <img src={logoSrc} alt={t.nama_jemaat} className="w-12 h-12 rounded-full bg-white p-1 border-2" style={{ borderColor: t.secondary_color }} />
          ) : (
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center font-display font-bold text-xl border-2"
              style={{
                backgroundColor: t.secondary_color,
                color: t.primary_color,
                borderColor: t.secondary_color,
              }}
            >
              {t.initial}
            </div>
          )}
          <div>
            <div className="text-[10px] tracking-[0.2em] uppercase opacity-80">
              {t.nama_uni}
            </div>
            <div className="font-display text-lg font-bold leading-tight">
              {t.nama_jemaat}
            </div>
          </div>
        </div>
      </div>
      {/* Body */}
      <div className="p-6">
        <div className="flex items-center gap-4 mb-5">
          <div className="flex items-center gap-2">
            <span
              className="w-6 h-6 rounded-full border-2 border-sabbath-cream"
              style={{ backgroundColor: t.primary_color }}
              title={t.primary_color}
            />
            <span className="text-xs text-gray-500 font-mono">{t.primary_color}</span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="w-6 h-6 rounded-full border-2 border-sabbath-cream"
              style={{ backgroundColor: t.secondary_color }}
              title={t.secondary_color}
            />
            <span className="text-xs text-gray-500 font-mono">{t.secondary_color}</span>
          </div>
        </div>
        <p className="text-xs text-gray-500 italic mb-4">
          {t.footer_text || 'Footer customisable'}
        </p>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-400 uppercase tracking-wider">
            {t.demo_user_count} user demo
          </span>
          <button
            onClick={enterDemo}
            disabled={loading}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all hover:shadow-lg disabled:opacity-50"
            style={{ backgroundColor: t.primary_color }}
          >
            {loading ? 'Loading...' : 'Coba Jemaat Ini →'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default LandingPage;
import { Link } from 'react-router-dom';

/**
 * Register page — role selector.
 * User memilih role (Pendeta / Auditor / Admin Uni), lalu di-redirect ke form spesifik.
 *
 * Public (no auth). Style Sabbath Ledger theme.
 */
const Register = () => {
  const roles = [
    {
      title: 'Pendeta',
      subtitle: 'Daftarkan jemaat Anda',
      desc: 'Isi data jemaat, pendeta, ketua, dan bendahara. Setelah submit, akun Pendeta otomatis aktif.',
      icon: '⛪',
      to: '/register/pendeta',
      color: 'sabbath-dark',
    },
    {
      title: 'Auditor Misi/Konferens',
      subtitle: 'Daftarkan misi Anda',
      desc: 'Isi data bendahara misi, auditor, dan persentase pembagian. Setelah submit, akun Auditor aktif.',
      icon: '📊',
      to: '/register/auditor',
      color: 'sabbath-gold',
    },
    {
      title: 'Admin Uni',
      subtitle: 'Daftarkan uni Anda',
      desc: 'Isi data bendahara uni, admin, dan persentase pembagian ke uni. Setelah submit, akun Admin aktif.',
      icon: '🏛️',
      to: '/register/admin',
      color: 'sabbath-charcoal',
    },
  ];

  return (
    <div className="min-h-screen bg-sabbath-light">
      {/* Top bar dengan logo FLIPUS */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-10 h-10 bg-sabbath-dark rounded-2xl flex items-center justify-center text-white font-bold text-xl">F</div>
            <div>
              <h1 className="text-2xl font-display text-sabbath-dark">FLIPUS</h1>
              <p className="text-xs text-gray-500">Sistem Akuntansi Jemaat Otomatis</p>
            </div>
          </Link>
          <Link
            to="/login"
            className="text-sm text-sabbath-dark hover:text-sabbath-gold font-medium"
          >
            Sudah punya akun? Login →
          </Link>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-16">
        <div className="text-center mb-12">
          <h2 className="text-4xl md:text-5xl font-display text-sabbath-dark mb-4">
            Daftar Akun FLIPUS
          </h2>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Pilih peran Anda. Setelah submit, Anda akan mendapat kredensial login
            yang ditampilkan <span className="font-bold text-sabbath-dark">sekali</span> — simpan dengan aman.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {roles.map((role) => (
            <Link
              key={role.to}
              to={role.to}
              className="group block bg-white rounded-3xl p-8 shadow-sm hover:shadow-xl transition-all hover:-translate-y-1 border border-gray-100"
            >
              <div className={`w-16 h-16 bg-${role.color} rounded-2xl flex items-center justify-center text-3xl mb-6 group-hover:scale-110 transition-transform`}>
                {role.icon}
              </div>
              <h3 className="text-2xl font-display text-sabbath-dark mb-2">
                {role.title}
              </h3>
              <p className="text-sabbath-gold font-medium mb-4">
                {role.subtitle}
              </p>
              <p className="text-gray-600 text-sm leading-relaxed mb-6">
                {role.desc}
              </p>
              <div className="flex items-center text-sabbath-dark font-medium group-hover:text-sabbath-gold transition-colors">
                <span>Daftar sebagai {role.title}</span>
                <span className="ml-2 group-hover:translate-x-1 transition-transform">→</span>
              </div>
            </Link>
          ))}
        </div>

        <div className="mt-12 bg-amber-50 border border-amber-200 rounded-2xl p-6 text-sm text-amber-800">
          <p className="font-medium mb-2">ℹ️ Penting:</p>
          <ul className="space-y-1 ml-4 list-disc">
            <li>Form ini hanya untuk pendaftaran pertama kali.</li>
            <li>Untuk pergantian struktural (pendeta baru, ketua baru, dll.), hubungi developer.</li>
            <li>Setelah submit, kredensial Anda akan muncul di halaman berikutnya — simpan sebelum meninggalkan halaman.</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default Register;
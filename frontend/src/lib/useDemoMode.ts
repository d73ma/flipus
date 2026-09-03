// FASE3-S4G (audit/FASE3_FRONTEND_REVIEW.md, item C-02):
//   Sebelumnya, saat demo timer expire, hook ini clear localStorage langsung
//   dan window.location.href tanpa memanggil logout() dari AuthContext.
//   Konsekuensi:
//     - Backend TIDAK di-notify (token JWT tidak masuk blacklist)
//     - React state tidak ter-reset sampai full reload
//   Fix: gunakan useAuth().logout() yang sudah memanggil POST /auth/logout
//   dan membersihkan semua state dengan benar.
//
// Catatan: logout() di auth.tsx melakukan window.location.href='/login',
// bukan '/?demo_expired=1'. Kita pertahankan UX demo_expired via query param
// dengan redirect manual ke LandingPage setelah logout selesai.
import { useEffect, useState } from 'react';
import { useAuth } from './auth';

const useDemoMode = () => {
  const { logout } = useAuth();
  const [isDemo, setIsDemo] = useState(() => localStorage.getItem('is_demo') === 'true');
  const [secondsLeft, setSecondsLeft] = useState(() => {
    const exp = localStorage.getItem('demo_expires_at');
    if (!exp) return 0;
    return Math.max(0, Math.floor((parseInt(exp) - Date.now()) / 1000));
  });

  useEffect(() => {
    if (!isDemo) return;
    const interval = setInterval(() => {
      const exp = localStorage.getItem('demo_expires_at');
      if (!exp) {
        setIsDemo(false);
        return;
      }
      const secs = Math.max(0, Math.floor((parseInt(exp) - Date.now()) / 1000));
      setSecondsLeft(secs);
      if (secs === 0) {
        // Auto-logout — delegate ke auth.logout() agar backend di-notify
        // (token di-blacklist) dan React state ter-reset konsisten.
        // logout() akan navigate ke /login, tapi user demo expired
        // lebih baik di-redirect ke LandingPage dengan flag.
        logout();
        // Append demo_expired flag via query (opsional, untuk UX banner).
        // Dilakukan setelah logout karena logout sudah set window.location.
        // Best-effort: ganti tujuan redirect.
        // (Jika gagal navigate karena race, fallback ke hard redirect.)
        setTimeout(() => {
          if (window.location.pathname === '/login') {
            window.location.href = '/?demo_expired=1';
          }
        }, 100);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [isDemo, logout]);

  return { isDemo, secondsLeft };
};

export default useDemoMode;
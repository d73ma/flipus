import { useEffect, useState } from 'react';

const useDemoMode = () => {
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
        // Auto-logout
        localStorage.removeItem('token');
        localStorage.removeItem('role');
        localStorage.removeItem('tenant_id');
        localStorage.removeItem('tenant_slug');
        localStorage.removeItem('is_demo');
        localStorage.removeItem('demo_expires_at');
        window.location.href = '/?demo_expired=1';
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [isDemo]);

  return { isDemo, secondsLeft };
};

export default useDemoMode;
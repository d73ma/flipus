import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

// ===== Register Service Worker (PWA) =====
// v2.0 M1: daftar SW untuk enable install-to-homescreen + cache basic.
// FASE 5 — HANYA di production build. Di dev (Vite), SW cache-first bikin
// browser menyajikan JS lama (stale) dan HMR tidak terlihat — ini yang
// menyebabkan bug "input reset" + "404 /api/kategori/list" karena Jerry
// masih melihat bundle lama via tunnel. Matikan SW saat dev.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/service-worker.js')
      .then((reg) => {
        if (import.meta.env.DEV) {
          console.log('[PWA] Service worker registered:', reg.scope)
        }
      })
      .catch((err) => {
        // Silent fail — PWA opsional, app tetap jalan tanpa SW.
        if (import.meta.env.DEV) {
          console.warn('[PWA] Service worker registration failed:', err)
        }
      })
  })
}
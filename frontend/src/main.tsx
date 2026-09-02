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
// register() aman di localhost (SW akan handle, tidak crash dev mode).
// Wrapped dalam if ('serviceWorker' in navigator) — Safari lama & iOS tanpa HTTPS bisa skip.
if ('serviceWorker' in navigator) {
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
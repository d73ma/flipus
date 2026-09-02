/**
 * FLIPUS v2.0 M1 — Service Worker untuk PWA Bendahara Quick Input.
 *
 * Strategi: network-first untuk /api/* (penting fresh data),
 * cache-first untuk static assets (icon, font, CSS).
 *
 * Catatan: ini SW minimal. Tidak ada offline-mode berat — kalau offline total,
 * user akan dapat fallback page sederhana (lihat OFFLINE_FALLBACK_HTML).
 */

const CACHE_NAME = "flipus-v20-m1";
const STATIC_CACHE = `${CACHE_NAME}-static`;
const RUNTIME_CACHE = `${CACHE_NAME}-runtime`;

// Asset statis yang harus ada untuk app shell
const PRECACHE_URLS = [
  "/manifest.json",
  "/icons/pwa-192.svg",
  "/icons/pwa-512.svg",
  "/favicon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== RUNTIME_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Skip non-GET dan cross-origin (Fonnte, Gemini, dll)
  if (req.method !== "GET") return;
  if (url.origin !== self.location.origin) return;

  // API: network-first, fallback cache (kalau sempat online sebelumnya)
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(RUNTIME_CACHE).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((r) => r || new Response("offline", { status: 503 })))
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(RUNTIME_CACHE).then((cache) => cache.put(req, copy));
        }
        return res;
      }).catch(() => caches.match("/"));
    })
  );
});
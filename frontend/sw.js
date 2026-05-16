// Service Worker — network-only (no caching).
// Exists solely for PWA installability (manifest + SW required).
// All requests go straight to the network — no stale cache issues.
const CACHE_NAME = 'foosball-v55';

self.addEventListener('install', (event) => {
  // Delete any old caches from previous SW versions
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Network-only: never serve from cache.
  // Let the browser handle failures normally.
});

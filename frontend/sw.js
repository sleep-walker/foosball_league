// Service Worker for offline support
const CACHE_NAME = 'foosball-v29';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/css/style.css',
  '/js/api.js',
  '/js/ws.js',
  '/js/ui.js',
  '/js/app.js',
  '/js/pages/landing.js',
  '/js/pages/tournaments.js',
  '/js/pages/tournament-detail.js',
  '/js/pages/leagues.js',
  '/js/pages/players.js',
  '/js/pages/live.js',
  '/js/pages/register.js',
  '/js/pages/login.js',
  '/manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Network-first for everything — ensures fresh content during development.
  // In production, you could switch JS/CSS to cache-first for performance.
  // Only cache GET requests — POST/PATCH/etc. are not cacheable
  if (event.request.method !== 'GET') {
    event.respondWith(fetch(event.request));
    return;
  }

  // Skip caching API calls (they need fresh data)
  if (event.request.url.includes('/api/')) {
    event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});

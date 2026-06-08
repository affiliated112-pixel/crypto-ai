/* Romania Crypto Signals — service worker (PWA / offline shell). */
const CACHE = 'rcb-v1';
const ASSETS = [
  '/',
  '/index.html',
  '/assets/styles.css',
  '/assets/app.js',
  '/assets/i18n.js',
  '/assets/realtime.js',
  '/assets/sync.js',
  '/assets/rcb-logo.png',
  '/portfolio.html',
  '/time-machine.html',
  '/iq-test.html',
  '/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  // Never cache API or cross-origin (prices, news proxy, websockets) — always go to network.
  if (url.pathname.startsWith('/api/') || url.origin !== self.location.origin) return;
  // Network-first for HTML so users get fresh content; cache fallback when offline.
  if (request.headers.get('accept')?.includes('text/html')) {
    e.respondWith(
      fetch(request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(request, copy));
        return res;
      }).catch(() => caches.match(request).then((m) => m || caches.match('/index.html')))
    );
    return;
  }
  // Cache-first for static assets.
  e.respondWith(caches.match(request).then((m) => m || fetch(request)));
});

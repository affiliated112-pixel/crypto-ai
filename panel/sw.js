/* Romania Crypto Signals — service worker (PWA / offline shell + push). */
const CACHE = 'rcb-v2';
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
  '/about.html',
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
  if (url.pathname.startsWith('/api/') || url.origin !== self.location.origin) return;
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
  e.respondWith(caches.match(request).then((m) => m || fetch(request)));
});

// ── PUSH NOTIFICATIONS ────────────────────────────────────────────────────────
self.addEventListener('push', (e) => {
  let data = { title: 'Romania Crypto Signals 📡', body: 'Semnal nou detectat!', tag: 'rcb-signal' };
  try {
    if (e.data) data = { ...data, ...e.data.json() };
  } catch (_) {
    if (e.data) data.body = e.data.text();
  }
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/assets/rcb-logo.png',
      badge: '/assets/rcb-logo.png',
      tag: data.tag || 'rcb-signal',
      renotify: true,
      vibrate: [200, 100, 200],
      data: { url: data.url || '/' },
      actions: [
        { action: 'open', title: '📊 Deschide' },
        { action: 'dismiss', title: 'Închide' },
      ],
    })
  );
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  if (e.action === 'dismiss') return;
  const target = e.notification.data?.url || '/';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      const existing = list.find((c) => c.url.includes(self.location.origin));
      if (existing) { existing.focus(); existing.navigate(target); }
      else clients.openWindow(target);
    })
  );
});

// ── LOCAL SIGNAL BROADCAST (from page → SW → other tabs) ─────────────────────
self.addEventListener('message', (e) => {
  if (e.data?.type === 'SIGNAL_ALERT') {
    const { title, body, url } = e.data;
    self.registration.showNotification(title || 'Semnal nou! 📡', {
      body: body || 'Bot-ul a detectat o oportunitate',
      icon: '/assets/rcb-logo.png',
      badge: '/assets/rcb-logo.png',
      tag: 'rcb-local-signal',
      renotify: true,
      vibrate: [150, 80, 150],
      data: { url: url || '/' },
    });
  }
});

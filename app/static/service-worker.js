// Metron Service Worker — no-op (required for PWA install prompt)
// All caching is handled by Cloudflare + browser via versioned URLs.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => {
  // Purge any caches left by the previous caching SW
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
  );
  self.clients.claim();
});
self.addEventListener('fetch', () => {});

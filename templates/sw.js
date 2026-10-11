// Minimal service worker: makes the app installable. Network-first, no
// caching of API/websocket traffic so chat data is never stale.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});

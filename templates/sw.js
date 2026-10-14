// Minimal service worker: makes the app installable. It caches nothing, so
// chat data is never stale. No fetch handler on purpose: an empty one only
// routes every request through the worker and slows page loads.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

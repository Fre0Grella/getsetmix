// GetSetMix service worker.
//
// Its only job is to make the app installable so Android can register the
// Web Share Target (see /manifest.webmanifest). We deliberately do NOT cache
// anything: GetSetMix is useless without its backend, and a stale cache of
// index.html / app.js would silently ship old UI. Every request goes to the
// network as usual — this worker just claims control immediately.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

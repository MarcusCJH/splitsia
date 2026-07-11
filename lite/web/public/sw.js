// Unregister this service worker and clear all caches so deploys are always fresh.
globalThis.addEventListener('install', () => globalThis.skipWaiting());
globalThis.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => globalThis.registration.unregister())
  );
});

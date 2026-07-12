// Service worker DANTE: cache-first sugli asset statici (three.js, font, icone) per
// avvio rapido/offline parziale. Gli endpoint dinamici (/ /ws /stt /tts /health) NON
// vengono mai cachati, così la chat e la voce restano sempre live e la pagina fresca.
const CACHE = 'dante-static-v1';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => e.waitUntil((async () => {
  const keys = await caches.keys();
  await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
  await self.clients.claim();
})()));

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const u = new URL(e.request.url);
  if (!u.pathname.startsWith('/static/')) return;   // solo asset statici
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
      if (resp.ok) { const c = resp.clone(); caches.open(CACHE).then(ca => ca.put(e.request, c)); }
      return resp;
    }))
  );
});

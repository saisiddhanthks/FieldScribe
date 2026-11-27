/* FieldScribe service worker: keeps the app's screens on the device so it opens with no network.
   Patient data is never cached here; it lives in the local backend database. */
const VERSION = 'fs-shell-v3'
const SHELL = ['/', '/manifest.webmanifest', '/favicon.svg', '/icon-192.png', '/icon-512.png']

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()))
})
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()))
})
self.addEventListener('fetch', e => {
  const req = e.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/docs')) return
  // built assets have content hashes in their names: cache-first
  if (url.pathname.startsWith('/assets/')) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(VERSION).then(c => c.put(req, copy)) }
      return r
    })))
    return
  }
  // pages: network first so updates show at once, cached app shell when offline
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(r => {
      const copy = r.clone(); caches.open(VERSION).then(c => c.put('/', copy)); return r
    }).catch(() => caches.match('/')))
    return
  }
  e.respondWith(caches.match(req).then(hit => hit || fetch(req)))
})

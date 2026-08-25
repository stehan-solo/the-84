/*
 * The 84 — service worker
 *
 * Offline strategy:
 *   - Every file the app needs is precached on install, so a cold launch with
 *     no network works exactly like an online one.
 *   - Navigations and same-origin assets are served cache-first and refreshed
 *     in the background (stale-while-revalidate), which keeps home-screen
 *     launches instant. A new version is picked up on the next launch.
 *
 * User data lives in localStorage and is never touched by this file — clearing
 * these caches only discards the app shell, never habit/training/metric data.
 *
 * Bump CACHE_VERSION whenever any precached file changes.
 */

const CACHE_VERSION = 'v1';
const CACHE_NAME = `the-84-${CACHE_VERSION}`;

// Paths are relative so the app works from any deploy path (root or subfolder).
const PRECACHE_URLS = [
  './',
  './index.html',
  './manifest.json',
  './icons/favicon-32.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-512.png',
  './icons/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      // Bypass the HTTP cache so a deploy never precaches a stale copy.
      await cache.addAll(
        PRECACHE_URLS.map((url) => new Request(url, { cache: 'reload' }))
      );
    })()
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key.startsWith('the-84-') && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      );
      // Speeds up first-load control on browsers that support it.
      if (self.registration.navigationPreload) {
        await self.registration.navigationPreload.enable();
      }
      await self.clients.claim();
    })()
  );
});

// Lets the page opt into an immediate update instead of waiting for relaunch.
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});

/** Revalidate in the background; failures are expected offline and ignored. */
function revalidate(cache, request) {
  return fetch(request)
    .then((response) => {
      if (response && response.ok && response.type === 'basic') {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => undefined);
}

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Never interfere with writes or cross-origin requests.
  if (request.method !== 'GET') return;
  if (new URL(request.url).origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        const cache = await caches.open(CACHE_NAME);
        const cached = await cache.match('./index.html');
        if (cached) {
          event.waitUntil(revalidate(cache, new Request('./index.html', { cache: 'reload' })));
          return cached;
        }
        const preloaded = await event.preloadResponse;
        if (preloaded) return preloaded;
        try {
          return await fetch(request);
        } catch (err) {
          // Last resort: any cached copy of the shell.
          return (await cache.match('./')) || Response.error();
        }
      })()
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(request);
      if (cached) {
        event.waitUntil(revalidate(cache, request));
        return cached;
      }
      const response = await revalidate(cache, request);
      return response || Response.error();
    })()
  );
});

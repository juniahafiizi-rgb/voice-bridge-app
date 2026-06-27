// Minimal service worker: caches the static app shell so the UI itself
// loads instantly on repeat visits. API calls always go to the network —
// translation/audio results are never cached, since they're per-request.
const CACHE_NAME = "voice-bridge-shell-v1";
const SHELL_ASSETS = ["/", "/index.html", "/style.css", "/app.js", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls — always hit the network for real results.
  if (url.pathname.startsWith("/api/")) return;

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});

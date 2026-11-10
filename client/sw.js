/* Minimal shell cache. Offline use is out of scope for v1; this only
   speeds repeat loads of the app shell. */
const CACHE = "vots-shell-v1";
const SHELL = ["/", "/static/styles.css", "/static/app.js", "/static/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET" || e.request.url.includes("/api/")) return;
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
      return res;
    }))
  );
});

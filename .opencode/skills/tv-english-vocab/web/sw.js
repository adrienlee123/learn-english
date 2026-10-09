/* Cache-first service worker so the app works with no connection. */
const CACHE = "vocab-app-v11";
const ASSETS = [
  "./",
  "./index.html",
  "./assets/app.css",
  "./assets/app.js",
  "./assets/data.js",
  "./manifest.webmanifest",
  "./icon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) =>
        // cache: "reload" bypasses the HTTP cache; without it a fresh install
        // can capture stale assets and then serve them forever.
        Promise.all(
          ASSETS.map((url) =>
            c.add(new Request(url, { cache: "reload" })).catch(() => null)
          )
        )
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;

  // index.html references assets as "assets/app.js?v=<hash>". Strip the query
  // so fingerprinted requests still hit the bare-path cache entries and keep
  // working offline.
  const url = new URL(e.request.url);
  const bare = url.origin + url.pathname;

  e.respondWith(
    caches.match(bare, { ignoreSearch: true }).then((hit) => {
      if (hit) {
        // Refresh in the background so a redeploy is picked up next launch.
        fetch(e.request).then((res) => {
          if (res && res.ok) caches.open(CACHE).then((c) => c.put(bare, res));
        }).catch(() => {});
        return hit;
      }
      return fetch(e.request)
        .then((res) => {
          if (res && res.ok && url.origin === location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(bare, copy));
          }
          return res;
        })
        .catch(() => caches.match("./index.html", { ignoreSearch: true }));
    })
  );
});
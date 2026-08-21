const CACHE_NAME = "the-brief-v1";

const PRECACHE_URLS = [
  "/us-residential-v2/",
  "/us-residential-v2/index.html",
  "/us-residential-v2/manifest.json",
  "/us-residential-v2/assets/icons/icon-192.png",
  "/us-residential-v2/assets/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const isArticlesCsv = request.url.includes("articles.csv");

  if (isArticlesCsv) {
    // Network First: 최신 기사 우선, 실패 시 캐시된 마지막 데이터 사용
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Cache First: 오프라인에서도 마지막 데이터/셸 유지
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return response;
      });
    })
  );
});

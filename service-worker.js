const CACHE_NAME = "the-brief-ea8d593f";

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
  // 캐시 정리와 clients.claim()을 하나의 waitUntil로 묶어야
  // clients.claim()이 끝나기 전에 activate가 "완료"로 취급되는 걸 방지한다.
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      ),
      self.clients.claim(),
    ])
  );
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

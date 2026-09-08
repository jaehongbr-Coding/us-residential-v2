const CACHE_NAME = "the-brief-11e9a2ca";

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

  // articles.csv와 archive_index.json 둘 다 매일 밤 갱신된다. 나머지 요청과
  // 같은 Cache First를 타면 한 번 캐시된 뒤로는 네트워크를 다시 확인하지
  // 않아 PWA 설치 사용자에게 아카이브가 그 시점 그대로 굳는다 — index.html/
  // manifest.json/아이콘 변경 시에만 CACHE_NAME이 갱신되므로(update_sw_version.yml)
  // 데이터 파일 변경으로는 캐시가 무효화되지 않기 때문이다.
  const isNetworkFirst = request.url.includes("articles.csv") || request.url.includes("archive_index.json");

  if (isNetworkFirst) {
    // Network First: 최신 데이터 우선, 실패 시 캐시된 마지막 데이터 사용
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

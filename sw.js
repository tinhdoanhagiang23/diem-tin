/* Bộ nhớ đệm cho phép mở trang khi mạng chập chờn.
   Luôn ưu tiên bản mới trên mạng; mất mạng mới dùng bản đã lưu.
   Khi sửa giao diện nhiều, tăng số phiên bản dưới đây (v1 -> v2...). */
const BO_NHO = "hst-v3";
const TEP = ["./", "index.html", "logo.png", "manifest.webmanifest",
             "icons/icon-192.png", "icons/icon-512.png", "icons/favicon-64.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(BO_NHO).then((c) => c.addAll(TEP)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== BO_NHO).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;  // không đụng Supabase, link ngoài
  e.respondWith(
    fetch(e.request).then((res) => {
      const ban = res.clone();
      caches.open(BO_NHO).then((c) => c.put(e.request, ban));
      return res;
    }).catch(() => caches.match(e.request).then((r) => r || caches.match("index.html")))
  );
});

async function api(yol, secenek = {}) {
  const r = await fetch(yol, { credentials: "same-origin", ...secenek });
  if (r.status === 401) throw new Error("Oturum gerekli");
  const t = await r.text();
  try { return JSON.parse(t); } catch { return t; }
}

const login = document.getElementById("login");
const app = document.getElementById("app");
const hata = document.getElementById("hata");
const grid = document.getElementById("grid");
const izgara = document.getElementById("izgara");

document.getElementById("giris").onclick = async () => {
  hata.textContent = "";
  try {
    const j = await api("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("user").value,
        password: document.getElementById("pass").value,
      }),
    });
    if (!j.ok) throw new Error("Giriş başarısız");
    document.getElementById("kim").textContent = j.user || "";
    login.hidden = true;
    app.hidden = false;
    await yukle();
  } catch (e) {
    hata.textContent = e.message || "Giriş başarısız";
  }
};

document.getElementById("cikis").onclick = async () => {
  await api("/api/logout", { method: "POST" });
  location.reload();
};

izgara.onchange = yukle;

async function yukle() {
  const kameralar = await api("/api/cameras");
  const n = izgara.value === "1" ? 1 : 4;
  grid.className = n === 1 ? "grid1" : "grid4";
  grid.innerHTML = "";
  kameralar.slice(0, n).forEach((k) => {
    const cell = document.createElement("div");
    cell.className = "cell";
    const v = document.createElement("video");
    v.controls = true;
    v.muted = true;
    v.autoplay = true;
    v.playsInline = true;
    v.src = `/hls/${encodeURIComponent(k.id)}/index.m3u8`;
    const ad = document.createElement("span");
    ad.textContent = k.name || k.id;
    cell.appendChild(v);
    cell.appendChild(ad);
    grid.appendChild(cell);
    if (v.canPlayType("application/vnd.apple.mpegurl")) {
      v.play().catch(() => {});
    } else if (window.Hls) {
      const h = new Hls({
        xhrSetup: (xhr) => { xhr.withCredentials = true; },
      });
      h.loadSource(v.src);
      h.attachMedia(v);
    }
  });
}

(async () => {
  try {
    const me = await api("/api/me");
    document.getElementById("kim").textContent = me.user || "";
    login.hidden = true;
    app.hidden = false;
    await yukle();
  } catch (_) {}
})();

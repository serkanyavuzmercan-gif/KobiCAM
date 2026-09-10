"""
KobiCAM uzak izleme: FastAPI + JWT + HLS.
GUI thread dışında QThread / uvicorn.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from app_info import kaynak_kok
from app_log import get_logger
from auth_manager import AuthError, AuthManager, get_app_data_dir
from config_manager import ConfigManager, kamera_rtsp
from process_util import ffmpeg_kapat
from record_session import ffmpeg_yolu
from web_token import jeton_dogrula, jeton_olustur, jwt_gizli

_HLS: dict[str, subprocess.Popen] = {}
_HLS_SON: dict[str, float] = {}
_HLS_IDLE = 45.0
_CONFIG: ConfigManager | None = None
_AUTH: AuthManager | None = None
_GIZLI = ""
_log = get_logger("web")
_hls_kilit = threading.Lock()


def _hls_kok() -> Path:
    yol = get_app_data_dir() / "hls"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def _statik() -> Path:
    return kaynak_kok() / "web_static"


def _cookie_jeton(request) -> str:
    return (request.cookies.get("kobicam_token") or "").strip()


def _kullanici(request) -> str | None:
    baslik = request.headers.get("authorization") or ""
    jeton = ""
    if baslik.lower().startswith("bearer "):
        jeton = baslik[7:].strip()
    if not jeton:
        jeton = _cookie_jeton(request)
    return jeton_dogrula(jeton, _GIZLI) if jeton else None


def web_ortam_ayarla(config: ConfigManager | None, auth: AuthManager | None, gizli: str) -> None:
    """TestClient ve sunucu için paylaşılan durum."""
    global _CONFIG, _AUTH, _GIZLI
    _CONFIG = config
    _AUTH = auth
    _GIZLI = gizli


def _uygulama():
    from fastapi import Body, FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="KobiCAM Web", docs_url=None, redoc_url=None)
    statik = _statik()
    if statik.is_dir():
        app.mount("/static", StaticFiles(directory=str(statik)), name="static")

    @app.get("/")
    def kok():
        index = statik / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse({"ok": False, "hata": "web_static yok"}, status_code=500)

    @app.post("/api/login")
    def giris(username: str = Body(...), password: str = Body(...)):
        if _AUTH is None:
            raise HTTPException(500, "Kimlik yöneticisi yok")
        try:
            ad = _AUTH.authenticate(username, password)
        except AuthError as hata:
            raise HTTPException(401, str(hata)) from hata
        jeton = jeton_olustur(ad, _GIZLI)
        cevap = JSONResponse({"ok": True, "token": jeton, "user": ad})
        cevap.set_cookie(
            "kobicam_token",
            jeton,
            httponly=True,
            samesite="lax",
            max_age=12 * 3600,
        )
        return cevap

    @app.post("/api/logout")
    def cikis():
        cevap = JSONResponse({"ok": True})
        cevap.delete_cookie("kobicam_token")
        return cevap

    @app.get("/api/me")
    def ben(request: Request):
        ad = _kullanici(request)
        if not ad:
            raise HTTPException(401, "Oturum gerekli")
        return {"user": ad}

    @app.get("/api/cameras")
    def kameralar(request: Request):
        if not _kullanici(request):
            raise HTTPException(401, "Oturum gerekli")
        if _CONFIG is None:
            return []
        liste = []
        for kam in _CONFIG.cameras():
            if not kamera_rtsp(kam):
                continue
            liste.append(
                {
                    "id": kam.get("id"),
                    "name": kam.get("name") or kam.get("ip") or kam.get("id"),
                }
            )
        return liste

    @app.get("/hls/{kamera_id}/index.m3u8")
    def oynatma_listesi(kamera_id: str, request: Request):
        if not _kullanici(request):
            raise HTTPException(401, "Oturum gerekli")
        _hls_dokun(kamera_id)
        _hls_baslat(kamera_id)
        yol = _hls_kok() / kamera_id / "index.m3u8"
        if not yol.is_file():
            raise HTTPException(503, "Yayın hazırlanıyor, tekrar deneyin")
        return FileResponse(yol, media_type="application/vnd.apple.mpegurl")

    @app.get("/hls/{kamera_id}/{parca}")
    def parca(kamera_id: str, parca: str, request: Request):
        if not _kullanici(request):
            raise HTTPException(401, "Oturum gerekli")
        _hls_dokun(kamera_id)
        if ".." in parca or "/" in parca or "\\" in parca:
            raise HTTPException(400, "Geçersiz parça")
        yol = _hls_kok() / kamera_id / parca
        if not yol.is_file():
            raise HTTPException(404)
        mime = "video/MP2T" if parca.endswith(".ts") else "application/octet-stream"
        return FileResponse(yol, media_type=mime)

    return app


def _hls_dokun(kamera_id: str) -> None:
    _HLS_SON[kamera_id] = time.monotonic()


def _hls_atil_temizle() -> None:
    simdi = time.monotonic()
    with _hls_kilit:
        atil = [k for k, ts in list(_HLS_SON.items()) if simdi - ts > _HLS_IDLE]
    for kid in atil:
        _log.info("HLS idle kapatıldı: %s", kid)
        _hls_durdur(kid)


def _hls_baslat(kamera_id: str) -> None:
    global _HLS
    _hls_dokun(kamera_id)
    with _hls_kilit:
        mevcut = _HLS.get(kamera_id)
        if mevcut is not None and mevcut.poll() is None:
            return
    if _CONFIG is None:
        return
    maks = int(_CONFIG.get("web_max_streams") or 4)
    with _hls_kilit:
        canli = [k for k, p in _HLS.items() if p.poll() is None]
    if len(canli) >= maks and kamera_id not in canli:
        _hls_durdur(canli[0])
    kam = _CONFIG.camera_by_id(kamera_id)
    url = kamera_rtsp(kam, prefer_sub=True)
    ffmpeg = ffmpeg_yolu()
    if not url or not ffmpeg:
        return
    klasor = _hls_kok() / kamera_id
    klasor.mkdir(parents=True, exist_ok=True)
    for eski in klasor.glob("*"):
        try:
            eski.unlink()
        except OSError:
            pass
    liste = str(klasor / "index.m3u8")
    kalip = str(klasor / "seg_%03d.ts")
    komut = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        url,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-g",
        "50",
        "-c:a",
        "aac",
        "-f",
        "hls",
        "-hls_time",
        "2",
        "-hls_list_size",
        "6",
        "-hls_flags",
        "delete_segments",
        "-hls_segment_filename",
        kalip,
        liste,
    ]
    bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        proc = subprocess.Popen(
            komut,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=bayrak,
        )
    except OSError:
        _log.exception("HLS FFmpeg başlatılamadı")
        return
    with _hls_kilit:
        _HLS[kamera_id] = proc
    _hls_dokun(kamera_id)


def _hls_durdur(kamera_id: str) -> None:
    with _hls_kilit:
        proc = _HLS.pop(kamera_id, None)
        _HLS_SON.pop(kamera_id, None)
    ffmpeg_kapat(proc, nazik=False, bekle_term=2.0)


def hls_hepsini_durdur() -> None:
    with _hls_kilit:
        ids = list(_HLS)
    for kid in ids:
        _hls_durdur(kid)


class WebServerThread(QThread):
    url_hazir = pyqtSignal(str)
    hata = pyqtSignal(str)

    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._sunucu = None
        self._dur = False

    def request_stop(self) -> None:
        self._dur = True
        hls_hepsini_durdur()
        try:
            from pyngrok import ngrok

            ngrok.kill()
        except Exception:
            pass
        sunucu = self._sunucu
        if sunucu is not None:
            sunucu.should_exit = True
            if getattr(sunucu, "force_exit", None) is not None:
                sunucu.force_exit = True
        else:
            _log.warning("uvicorn henüz yok; QThread.terminate")
            self.terminate()

    def run(self) -> None:
        self._dur = False
        web_ortam_ayarla(self._config, AuthManager(), jwt_gizli(self._config))
        bind = str(self._config.get("web_bind") or "0.0.0.0")
        port = int(self._config.get("web_port") or 8765)
        from network_scanner import yerel_ipv4_adresleri

        lan = (yerel_ipv4_adresleri() or ["127.0.0.1"])[0]
        public = f"http://{lan}:{port}"
        if self._config.get("ngrok_enabled") and str(self._config.get("ngrok_authtoken") or "").strip():
            try:
                from pyngrok import ngrok

                ngrok.set_auth_token(str(self._config.get("ngrok_authtoken")).strip())
                tunel = ngrok.connect(port, "http")
                public = str(tunel.public_url)
            except Exception as hata:
                _log.exception("Ngrok")
                self.hata.emit(f"Ngrok: {hata}")
        self.url_hazir.emit(public)
        bekci = threading.Thread(target=self._hls_bekci, daemon=True)
        bekci.start()
        try:
            import uvicorn

            ayar = uvicorn.Config(
                _uygulama(),
                host=bind,
                port=port,
                log_level="error",
                access_log=False,
            )
            self._sunucu = uvicorn.Server(ayar)
            self._sunucu.run()
        except Exception as hata:
            _log.exception("Web sunucusu")
            self.hata.emit(str(hata))
        finally:
            self._dur = True
            hls_hepsini_durdur()
            self._sunucu = None

    def _hls_bekci(self) -> None:
        while not self._dur:
            time.sleep(5)
            if self._dur:
                return
            try:
                _hls_atil_temizle()
            except Exception:
                _log.exception("HLS idle temizlik")

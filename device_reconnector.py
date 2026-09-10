"""
DHCP ile değişen DVR/NVR IP'sini MAC üzerinden yeniden bulur.

GUI thread kullanılmaz; tarama 3–5 saniye ile sınırlıdır.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from app_log import get_logger
from network_scanner import mac_coz_ip, mac_normalize, tcp_port_acik, yerel_ag_hedefleri

_log = get_logger("ip_recovery")

AG_KOPUK = frozenset({"timeout", "refused", "baglanti", "kapali"})
_SURE_TAVAN = 4.0
_TCP_TIMEOUT = 0.25
_WORKERS = 80


def ip_bul_mac(
    mac_address: str,
    eski_ip: str = "",
    onvif_port: int = 80,
    rtsp_port: int = 554,
    sure: float = _SURE_TAVAN,
) -> str:
    """
    Yerel /24'te MAC ile eşleşen yeni IPv4'ü arar. Bulunamazsa boş dize.
    """
    hedef_mac = mac_normalize(mac_address)
    eski = (eski_ip or "").strip()
    if not hedef_mac:
        return ""
    portlar = []
    for p in (int(rtsp_port or 554), int(onvif_port or 80)):
        if p > 0 and p not in portlar:
            portlar.append(p)
    if not portlar:
        portlar = [554, 80]

    adaylar = [ip for ip in yerel_ag_hedefleri() if ip != eski]
    if not adaylar:
        return ""

    bitis = time.monotonic() + max(1.0, min(5.0, float(sure or _SURE_TAVAN)))
    acik: list[str] = []
    with ThreadPoolExecutor(max_workers=_WORKERS) as havuz:
        isler = {
            havuz.submit(tcp_port_acik, ip, port, _TCP_TIMEOUT): ip
            for ip in adaylar
            for port in portlar
        }
        for gelecek in as_completed(isler):
            if time.monotonic() > bitis:
                for kalan in isler:
                    kalan.cancel()
                break
            ip = isler[gelecek]
            try:
                if gelecek.result():
                    acik.append(ip)
            except Exception:
                pass

    gorulen: set[str] = set()
    for ip in acik:
        if ip in gorulen:
            continue
        gorulen.add(ip)
        if time.monotonic() > bitis + 1.0:
            break
        mac = mac_coz_ip(ip)
        if mac == hedef_mac:
            return ip
    return ""


class DeviceReconnector(QThread):
    """MAC ile yeni IP arayan arka plan işçisi."""

    bulundu = pyqtSignal(str, str)  # eski_ip, yeni_ip
    bitti = pyqtSignal(str)  # yeni_ip veya ""

    def __init__(
        self,
        mac_address: str,
        eski_ip: str = "",
        onvif_port: int = 80,
        rtsp_port: int = 554,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._mac = mac_address
        self._eski = eski_ip
        self._onvif = onvif_port
        self._rtsp = rtsp_port

    def run(self) -> None:
        yeni = ip_bul_mac(self._mac, self._eski, self._onvif, self._rtsp)
        if yeni:
            self.bulundu.emit(self._eski, yeni)
        self.bitti.emit(yeni or "")

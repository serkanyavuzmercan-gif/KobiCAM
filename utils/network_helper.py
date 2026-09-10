"""Tailscale ve yerel ağ adresi yardımcıları."""

from __future__ import annotations

import ipaddress
import socket
import subprocess
from typing import Any

_TS_ADLAR = ("tailscale", "wintun")
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _cgnat_mi(ip: str) -> bool:
    try:
        adres = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    return adres in _CGNAT


def _arayuz_tailscale_mi(ad: str) -> bool:
    k = (ad or "").lower()
    return any(parca in k for parca in _TS_ADLAR)


def _ipv4_al(oge: Any) -> str:
    aile = getattr(oge, "family", None)
    if aile not in (socket.AF_INET, getattr(socket, "AF_INET", 2)):
        return ""
    ham = str(getattr(oge, "address", "") or "").split("%", 1)[0].strip()
    if not ham or ham.startswith("127."):
        return ""
    try:
        ipaddress.IPv4Address(ham)
    except ValueError:
        return ""
    return ham


def _psutil_tara() -> str:
    try:
        import psutil
    except ImportError:
        return ""
    try:
        adresler = psutil.net_if_addrs()
    except Exception:
        return ""
    isimli: list[str] = []
    cgnat: list[str] = []
    for ad, ogeler in adresler.items():
        ts_arayuz = _arayuz_tailscale_mi(ad)
        for oge in ogeler:
            ip = _ipv4_al(oge)
            if not ip:
                continue
            if ts_arayuz:
                isimli.append(ip)
            elif _cgnat_mi(ip):
                cgnat.append(ip)
    if isimli:
        for ip in isimli:
            if _cgnat_mi(ip) or ip.startswith("100."):
                return ip
        return isimli[0]
    return cgnat[0] if cgnat else ""


def _tailscale_cli() -> str:
    try:
        tamam = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if tamam.returncode != 0:
        return ""
    for satir in (tamam.stdout or "").splitlines():
        ip = satir.strip()
        if _cgnat_mi(ip) or ip.startswith("100."):
            return ip
    return ""


def get_tailscale_ip() -> str | None:
    """Tailscale IPv4 (100.64.0.0/10) veya None."""
    for aday in (_psutil_tara, _tailscale_cli):
        try:
            ip = aday()
        except Exception:
            ip = ""
        if ip:
            return ip
    return None


def portal_url(port: int) -> str:
    """Tailscale varsa http://100.x.y.z:port, yoksa boş."""
    ip = get_tailscale_ip()
    if not ip:
        return ""
    return f"http://{ip}:{int(port)}"


def tailscale_adresi_mi(url_veya_ip: str) -> bool:
    """Portal URL veya IPv4 Tailscale CGNAT aralığında mı."""
    ham = (url_veya_ip or "").strip()
    if "://" in ham:
        from urllib.parse import urlparse

        ham = urlparse(ham).hostname or ""
    return _cgnat_mi(ham) or ham.startswith("100.")

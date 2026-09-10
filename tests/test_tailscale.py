"""Tailscale IPv4 tespiti."""

from __future__ import annotations

from utils.network_helper import (
    _cgnat_mi,
    get_tailscale_ip,
    portal_url,
    tailscale_adresi_mi,
)


def test_cgnat_aralik() -> None:
    assert _cgnat_mi("100.115.20.45")
    assert _cgnat_mi("100.64.0.1")
    assert _cgnat_mi("100.127.255.254")
    assert not _cgnat_mi("100.10.0.1")
    assert not _cgnat_mi("192.168.1.50")
    assert not _cgnat_mi("")


def test_tailscale_adresi_mi() -> None:
    assert tailscale_adresi_mi("http://100.115.20.45:8765")
    assert tailscale_adresi_mi("100.64.1.2")
    assert not tailscale_adresi_mi("http://192.168.1.12:8765")


def test_psutil_ip(monkeypatch) -> None:
    import utils.network_helper as nh

    monkeypatch.setattr(nh, "_psutil_tara", lambda: "100.115.20.45")
    monkeypatch.setattr(nh, "_tailscale_cli", lambda: "")
    assert get_tailscale_ip() == "100.115.20.45"
    assert portal_url(8765) == "http://100.115.20.45:8765"


def test_yoksa_none(monkeypatch) -> None:
    import utils.network_helper as nh

    monkeypatch.setattr(nh, "_psutil_tara", lambda: "")
    monkeypatch.setattr(nh, "_tailscale_cli", lambda: "")
    assert get_tailscale_ip() is None
    assert portal_url(8765) == ""


def test_psutil_tailscale_arayuz(monkeypatch) -> None:
    import socket
    import sys
    import types
    from types import SimpleNamespace

    fake = types.ModuleType("psutil")
    fake.net_if_addrs = lambda: {
        "Ethernet": [SimpleNamespace(family=socket.AF_INET, address="192.168.1.10")],
        "Tailscale Tunnel": [SimpleNamespace(family=socket.AF_INET, address="100.115.20.45")],
    }
    monkeypatch.setitem(sys.modules, "psutil", fake)
    from utils.network_helper import _psutil_tara

    assert _psutil_tara() == "100.115.20.45"

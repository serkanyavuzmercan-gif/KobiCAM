"""MAC normalizasyonu, ARP parse ve RTSP host güncelleme."""

from __future__ import annotations

from config_manager import ConfigManager, url_host_degistir
from network_scanner import arp_ciktisindan_mac, mac_normalize


def test_mac_normalize() -> None:
    assert mac_normalize("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert mac_normalize("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"
    assert mac_normalize("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"
    assert mac_normalize("zz:zz:zz:zz:zz:zz") == ""
    assert mac_normalize("") == ""
    assert mac_normalize(None) == ""


def test_arp_ciktisindan_mac() -> None:
    ornek = """
Interface: 192.168.1.10 --- 0x5
  Internet Address      Physical Address      Type
  192.168.1.1           11-22-33-44-55-66     dynamic
  192.168.1.64          aa-bb-cc-dd-ee-ff     dynamic
"""
    assert arp_ciktisindan_mac(ornek, "192.168.1.64") == "AA:BB:CC:DD:EE:FF"
    assert arp_ciktisindan_mac(ornek, "192.168.1.1") == "11:22:33:44:55:66"
    assert arp_ciktisindan_mac(ornek, "192.168.1.99") == ""


def test_url_host_degistir() -> None:
    rtsp = "rtsp://admin:sifre@192.168.1.64:554/Streaming/Channels/101"
    yeni = url_host_degistir(rtsp, "192.168.1.64", "192.168.1.80")
    assert "192.168.1.80" in yeni
    assert "192.168.1.64" not in yeni
    assert "admin:sifre@" in yeni
    assert yeni.endswith("/Streaming/Channels/101") or "/Streaming/Channels/101" in yeni

    xaddrs = "http://192.168.1.64:80/onvif/device_service http://192.168.1.64:8899/onvif/device_service"
    guncel = url_host_degistir(xaddrs, "192.168.1.64", "10.0.0.5")
    assert "10.0.0.5" in guncel
    assert "192.168.1.64" not in guncel


def test_guncelle_cihaz_ip(tmp_path) -> None:
    cfg = ConfigManager(tmp_path / "config.json")
    cihaz = cfg.upsert_device(
        {
            "id": "dev1",
            "ip": "192.168.1.64",
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "xaddrs": "http://192.168.1.64/onvif/device_service",
        }
    )
    cfg.upsert_camera(
        {
            "id": "cam1",
            "device_id": cihaz["id"],
            "ip": "192.168.1.64",
            "main_url": "rtsp://u:p@192.168.1.64:554/ch1",
            "sub_url": "rtsp://u:p@192.168.1.64:554/ch1sub",
        }
    )
    guncel = cfg.guncelle_cihaz_ip(cihaz["id"], "192.168.1.90")
    assert guncel is not None
    assert guncel["ip"] == "192.168.1.90"
    assert "192.168.1.90" in str(guncel.get("xaddrs") or "")
    kamera = cfg.camera_by_id("cam1")
    assert kamera is not None
    assert kamera["ip"] == "192.168.1.90"
    assert "192.168.1.90" in kamera["main_url"]
    assert "192.168.1.64" not in kamera["main_url"]

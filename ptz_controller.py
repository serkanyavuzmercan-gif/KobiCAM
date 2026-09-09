"""
ONVIF PTZ (ham SOAP, ekstra kütüphane yok).

GetCapabilities ile PTZ XAddr bulunur; ContinuousMove / Stop bas-tut için kullanılır.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

_SOAP12 = "application/soap+xml; charset=utf-8"
_SOAP11 = "text/xml; charset=utf-8"
_SOAP = _SOAP12
_ZAMAN_ASIMI = 4
_SSL = ssl._create_unverified_context()


def _zarf(govde: str, kullanici: str, sifre: str, ozetli: bool = True, soap12: bool = True) -> bytes:
    ns = (
        "http://www.w3.org/2003/05/soap-envelope"
        if soap12
        else "http://schemas.xmlsoap.org/soap/envelope/"
    )
    baslik = ""
    if kullanici:
        if ozetli:
            nonce = os.urandom(16)
            nonce_b64 = base64.b64encode(nonce).decode("ascii")
            created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            ozet = hashlib.sha1(
                nonce + created.encode("utf-8") + sifre.encode("utf-8")
            ).digest()
            ozet_b64 = base64.b64encode(ozet).decode("ascii")
            parola = (
                f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{ozet_b64}</wsse:Password>'
                f'<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>'
                f"<wsu:Created>{created}</wsu:Created>"
            )
        else:
            parola = (
                f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{escape(sifre)}</wsse:Password>'
            )
        baslik = f"""
    <s:Header>
      <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                     xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
        <wsse:UsernameToken>
          <wsse:Username>{escape(kullanici)}</wsse:Username>
          {parola}
        </wsse:UsernameToken>
      </wsse:Security>
    </s:Header>"""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="{ns}">{baslik}
  <s:Body>
    {govde}
  </s:Body>
</s:Envelope>
"""
    return xml.encode("utf-8")


def _posta_ex(
    url: str,
    govde: str,
    kullanici: str,
    sifre: str,
    soap_action: str = "",
    zaman_asimi: float = _ZAMAN_ASIMI,
) -> tuple[str, str]:
    """
    SOAP POST. Dönüş: (gövde, hata). hata boşsa yanıt kullanılabilir.

    ONVIF uçları arasında uyum farkı büyük olduğu için WS-Digest / PasswordText
    ve SOAP 1.2 / 1.1 kombinasyonları denenir. Uç noktanın var olmadığı belliyse
    (404 gibi) beklemeden çıkılır.
    """
    son = ""
    hata = "yanıt yok"
    # (soap12, ozetli) — yalnızca gerekliyse sıradaki denenir
    for adim, (soap12, ozetli) in enumerate(((True, True), (True, False), (False, True))):
        data = _zarf(govde, kullanici, sifre, ozetli=ozetli, soap12=soap12)
        istek = urllib.request.Request(url, data=data, method="POST")
        istek.add_header("Content-Type", _SOAP12 if soap12 else _SOAP11)
        if soap_action:
            istek.add_header("SOAPAction", f'"{soap_action}"')
        if kullanici:
            jeton = base64.b64encode(f"{kullanici}:{sifre}".encode("utf-8")).decode("ascii")
            istek.add_header("Authorization", f"Basic {jeton}")
        try:
            with urllib.request.urlopen(istek, timeout=zaman_asimi, context=_SSL) as yanit:
                son = yanit.read().decode("utf-8", errors="replace")
                hata = ""
        except urllib.error.HTTPError as e:
            try:
                son = e.read().decode("utf-8", errors="replace")
            except Exception:
                son = ""
            if e.code in (401, 403):
                if adim == 0:
                    hata = "auth"
                    continue
                return son, "auth"
            # 404/405: bu adreste ONVIF servisi yok, denemeye devam etmenin anlamı yok
            return son, f"http_{e.code}"
        except TimeoutError:
            return "", "timeout"
        except urllib.error.URLError as e:
            neden = str(getattr(e, "reason", e) or e)
            if "refused" in neden.lower() or "10061" in neden:
                return "", "refused"
            if "timed out" in neden.lower():
                return "", "timeout"
            return "", "baglanti"
        except OSError:
            return "", "baglanti"

        if son and ("Profiles" in son or "Uri>" in son or "XAddr" in son or "VideoSource" in son):
            return son, ""
        if son and "Fault" not in son:
            return son, ""
        if son and "Fault" in son:
            if re.search(r"NotAuthorized|NotAuthorised|FailedAuthentication", son, re.I):
                hata = "auth"
                continue
            hata = "fault"
    return son, hata


def _posta(
    url: str,
    govde: str,
    kullanici: str,
    sifre: str,
    soap_action: str = "",
    zaman_asimi: float = _ZAMAN_ASIMI,
) -> str:
    govde_xml, _hata = _posta_ex(url, govde, kullanici, sifre, soap_action, zaman_asimi)
    return govde_xml


def _cihaz_url(ip: str, xaddrs: str) -> str:
    for jeton in (xaddrs or "").split():
        j = jeton.strip()
        if j.startswith("http"):
            return j
    ip = (ip or "").strip()
    if ip:
        return f"http://{ip}/onvif/device_service"
    return ""


def _xaddrs(xml: str) -> list[str]:
    return [m.strip() for m in re.findall(r"XAddr[^>]*>([^<]+)", xml, re.I)]


def _ptz_url_sec(adresler: list[str], cihaz: str) -> str:
    for a in adresler:
        if "ptz" in a.lower():
            return a.strip()
    if cihaz:
        # Yaygın yedek yol
        from urllib.parse import urlparse

        ayr = urlparse(cihaz)
        taban = f"{ayr.scheme}://{ayr.netloc}"
        return f"{taban}/onvif/ptz_service"
    return ""


def _media_url_sec(adresler: list[str], cihaz: str) -> str:
    for a in adresler:
        al = a.lower()
        if "media2" in al:
            continue
        if "media" in al:
            return a.strip()
    for a in adresler:
        if "media" in a.lower():
            return a.strip()
    if cihaz:
        from urllib.parse import urlparse

        ayr = urlparse(cihaz)
        return f"{ayr.scheme}://{ayr.netloc}/onvif/media_service"
    return ""


def _profil_token(xml: str) -> str:
    es = re.search(r"token=\"([^\"]+)\"", xml, re.I)
    if es:
        return es.group(1)
    es = re.search(r"<[^>]*ProfileToken[^>]*>([^<]+)", xml, re.I)
    return es.group(1).strip() if es else ""


def ptz_kesfet(
    ip: str,
    kullanici: str,
    sifre: str,
    xaddrs: str = "",
) -> dict:
    """
    PTZ var mı diye bakır.

    Returns:
        {ptz: bool, ptz_url: str, ptz_token: str}
    """
    bos = {"ptz": False, "ptz_url": "", "ptz_token": ""}
    cihaz = _cihaz_url(ip, xaddrs)
    if not cihaz:
        return bos

    cap = _posta(
        cihaz,
        '<tds:GetCapabilities xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
        "<tds:Category>All</tds:Category></tds:GetCapabilities>",
        kullanici,
        sifre,
    )
    if not cap:
        return bos
    if "PTZ" not in cap and "ptz" not in cap:
        return bos

    adresler = _xaddrs(cap)
    ptz_url = _ptz_url_sec(adresler, cihaz)
    media = _media_url_sec(adresler, cihaz)
    token = ""
    if media:
        prof = _posta(
            media,
            '<trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl"/>',
            kullanici,
            sifre,
        )
        token = _profil_token(prof)
    if not token:
        # Bazı cihazlar token olmadan da ilk profili kullanır
        token = "Profile_1"

    if not ptz_url:
        return bos
    return {"ptz": True, "ptz_url": ptz_url, "ptz_token": token}


def ptz_hareket(ptz_url: str, token: str, kullanici: str, sifre: str, x: float, y: float) -> None:
    if not ptz_url or not token:
        return
    govde = f"""
    <tptz:ContinuousMove xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"
                        xmlns:tt="http://www.onvif.org/ver10/schema">
      <tptz:ProfileToken>{escape(token)}</tptz:ProfileToken>
      <tptz:Velocity>
        <tt:PanTilt x="{x:.2f}" y="{y:.2f}" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocitySpaceGeneric"/>
      </tptz:Velocity>
    </tptz:ContinuousMove>
    """
    _posta(ptz_url, govde, kullanici, sifre)


def ptz_durdur(ptz_url: str, token: str, kullanici: str, sifre: str) -> None:
    if not ptz_url or not token:
        return
    govde = f"""
    <tptz:Stop xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
      <tptz:ProfileToken>{escape(token)}</tptz:ProfileToken>
      <tptz:PanTilt>true</tptz:PanTilt>
      <tptz:Zoom>true</tptz:Zoom>
    </tptz:Stop>
    """
    _posta(ptz_url, govde, kullanici, sifre)


# Yön → (pan x, tilt y)
YONLER = {
    "left": (-0.4, 0.0),
    "right": (0.4, 0.0),
    "up": (0.0, 0.4),
    "down": (0.0, -0.4),
}

# KobiCAM VMS

Windows için yerel ağ kamera / DVR izleme yazılımı.  
Local-network camera and DVR monitoring software for Windows.

**Sürüm / Version:** 1.3.1  
**Geliştirici / Author:** Serkan Yavuz Mercan  
**İletişim / Contact:** [serkanyavuzmercan@gmail.com](mailto:serkanyavuzmercan@gmail.com)

---

## Türkçe

### İndirme

Kurulum dosyası kaynak kodun yanında [Releases](../../releases) sayfasındadır:

- **[KobiCAM-Setup-1.3.1.exe](../../releases/latest)** — Masaüstü VMS, Windows 10/11 (64-bit)
- **[KobiCAM-Server-Setup-1.0.exe](../../releases/latest)** — Server Gateway (saat yanı), Windows 10/11 (64-bit)

Kurulum sihirbazını çalıştırın. İsterseniz masaüstü kısayolu oluşturun. İlk açılışta kendi kullanıcı hesabınızı tanımlarsınız.

1.3.1 kurulum paketi YOLOv8 / PyTorch içerir (~330 MB). Drive, analitik ve web portal **varsayılan kapalıdır**; Ayarlar’dan açılır.

### Ne işe yarar?

KobiCAM, ofis veya işyerindeki **kayıt cihazı (DVR/NVR)** ve IP kameraları aynı ekranda izlemek için yazılmıştır. ONVIF ve RTSP kullanır; Hikvision, Dahua, XM/Xiongmai ve benzeri cihazlarla çalışacak şekilde tasarlanmıştır.

### Özellikler

- DVR/NVR ekleme ve kanalları otomatik okuma (ONVIF, yoksa RTSP şablonları)
- XM cihazlarda Media Port (34567) ve üretici seçimi
- Ağ tarama (F5)
- 1 / 4 / 9 / 16’lı ızgara, sürükle-bırak yerleştirme
- Canlı kayıt (MP4: görüntü kopya, ses AAC) ve anlık görüntü
- PTZ, dijital yakınlaştırma, HD/SD, canlı ses
- Tanılama (F8): bu bilgisayarın IP’si, ping, açık portlar
- Cihaz IP’si değişince **MAC ile otomatik yeniden bağlanma**
- Özel pencere çubuğu, klavye kısayolları (Yardım → Klavye kısayolları)
- **Bulut (Google Drive)** döngüsel segment senkronu (OAuth, isteğe bağlı)
- **Analitik:** tek kamerada insan sayımı (giren / çıkan / tekrar giriş), turkuaz-mor çizgi, köşe sayacı ve CSV rapor (günlük / haftalık / aylık)
- **Web / mobil portal:** aynı Wi-Fi veya Tailscale ile uzaktan; QR kod; en fazla 4 yayın

### Kullanım (kısa)

1. **Cihazlar → Cihaz Ekle** ile DVR’ın IP’sini, kendi kullanıcı adını ve şifresini girin (KobiCAM şifresi değil).
2. **Bağlan** deyince kanallar **Kameralar** listesine düşer.
3. Kamerayı ızgara hücresine sürükleyin.
4. Bağlanamazsanız **Tanıla (F8)** çalıştırın. Tarayıcıda `http://cihaz-ip` açılmıyorsa sorun ağ/kablodadır, program değildir.

Ayrıntı: uygulamada **Yardım → Nasıl çalışır? (F1)**.

### Güvenlik

Gömülü yedek `admin` hesabı yoktur. İlk kurulumda bir kez gösterilen **kurtarma kodunu** saklayın; giriş ekranından parola sıfırlanır. DVR/RTSP şifreleri `config.json` içinde AES-256-GCM (`ENC:`) ile durur; Master Key Windows Credential Manager / DPAPI’dedir. Windows kullanıcısı değişirse kamera sırları çözülemez. Web JWT süreç belleğindedir; KobiCAM kapanınca oturumlar düşer.

### Google Drive (OAuth)

Manuel kırmızı kayıt butonu değişmez. Drive, seçili kameralar için ayrı 5 dakikalık (varsayılan) MP4 segmentleri yazar ve `KobiCAM_Cloud` klasörüne yükler. 120 saatten eski Drive dosyaları silinir.

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Enable **Google Drive API**.
2. Credentials → Create credentials → **OAuth client ID** → Application type **Desktop app**.
3. Client ID ve Client secret’ı **Ayarlar → Bulut** alanlarına yapıştırın.
4. **Google’a bağlan** — tarayıcı açılır; token `%APPDATA%\KobiCAM\gdrive_token.json` dosyasına yazılır.
5. Senkronlanacak kameraları işaretleyip Drive senkronunu açın.

Kapsam: `drive.file` (yalnızca uygulamanın oluşturduğu dosyalar). Kota dolarsa kuyruk durur; durum çubuğunda görünür.

### Analitik (insan sayımı)

Tek kamera, ayrı düşük FPS FFmpeg borusu; ızgara görüntüsü kilitlenmez.

1. **Ayarlar → Analitik** ile açın ve kamerayı seçin.
2. Üst menüden **Analitik (Ctrl+Shift+A)** penceresinde kare üzerine **iki tıklama** ile sayım çizgisi çizin. Turkuaz taraf giriş, mor taraf çıkıştır; tersse çizgiyi ters yönde yeniden çizin.
3. Giren / çıkan / tekrar giriş ve kalma süresi `analytics.db` içinde tutulur. **Rapor CSV** ile günlük, haftalık ve aylık Excel çıktısı alınır.
4. Köşedeki sayaca tıklayınca kutu diğer köşeye geçer.

GPU yoksa CPU’da `yolov8n` ve varsayılan 5 fps kullanılır. Model `assets/yolov8n.pt` içindedir.

### Web / mobil portal

Yayın **KobiCAM Server Gateway** (saat yanı) üzerindedir; masaüstü VMS kapanınca kesilmez. `python server_app.py` veya `KobiCAM-Server-Setup.exe`. Giriş, KobiCAM kullanıcı adı/şifresidir. RTSP adresleri tarayıcıya gitmez. En fazla 4 kamera.

- Durum: **Ayarlar → Sunucu Bağlantı Durumu** (Aktif/Pasif, URL, QR)
- Port: **Ayarlar → Web / mobil** (varsayılan 8765)
- Farklı Wi-Fi / hücresel: PC ve telefona [Tailscale](https://tailscale.com) aynı hesap. Adres `http://100.x.y.z:8765`. DVR portlarını internete açmayın.

### Kaynak koddan çalıştırma

Python 3.10+ gerekir.

```bat
pip install -r requirements.txt
python main.py
python server_app.py
```

Not: `opencv-python` (GUI) kurulmaz; `opencv-python-headless` kullanılır.

### Kurulum paketini yeniden derleme

Gerekenler: Python, [Inno Setup 6](https://jrsoftware.org/isinfo.php). Paket büyüktür (torch / YOLO).

```bat
build_release.bat
build_server.bat
```

Çıktı: `setup\Output\KobiCAM-Setup-1.3.1.exe` ve `setup\Output\KobiCAM-Server-Setup-1.0.exe`.

### Lisans

Tüm hakları saklıdır. Serkan Yavuz Mercan.

---

## English

### Download

The Windows installer is published on the [Releases](../../releases) page (not inside the source tree):

- **[KobiCAM-Setup-1.3.1.exe](../../releases/latest)** — Desktop VMS, Windows 10/11 (64-bit)
- **[KobiCAM-Server-Setup-1.0.exe](../../releases/latest)** — Server Gateway (system tray), Windows 10/11 (64-bit)

Run the wizard. Optionally create a desktop shortcut. On first launch you create your own user account.

The 1.3.1 installer bundles YOLOv8 / PyTorch (~330 MB). Drive, analytics and the web portal are **off by default** and enabled in Settings.

### What it is

KobiCAM is a video management client for **DVR/NVR recorders** and IP cameras on a local network. It uses ONVIF and RTSP and is aimed at Hikvision, Dahua, XM/Xiongmai and similar devices.

### Features

- Add a recorder and discover channels (ONVIF, then RTSP path templates)
- XM Media Port (34567) and vendor selection
- Network scan (F5)
- 1 / 4 / 9 / 16 grid with drag-and-drop
- Live recording (MP4: video copy, audio AAC) and snapshots
- PTZ, digital zoom, HD/SD, live audio
- Diagnostics (F8): this PC’s IP, ping, open ports
- **MAC-based auto-reconnect** when a device IP changes
- Custom title bar and keyboard shortcuts (Help → Keyboard shortcuts)
- **Cloud (Google Drive)** cyclic segment sync (OAuth, optional)
- **Analytics:** people counting (in / out / re-entry), turquoise–purple line, corner counter, CSV daily/weekly/monthly reports
- **Web / mobile portal:** same Wi-Fi or remote via Tailscale; QR code; up to 4 streams

### Quick start

1. **Devices → Add Device**: enter the DVR IP and **the recorder’s** username/password (not the KobiCAM login).
2. **Connect** fills the **Cameras** list with channels.
3. Drag a camera onto a grid cell.
4. If it fails, run **Diagnose (F8)**. If `http://device-ip` does not open in a browser, the path/cable/network is the problem, not KobiCAM.

Full guide: **Help → How it works (F1)** in the app.

### Security

There is no hardcoded backup admin. At first setup you get a one-time **recovery key**; use it on the login screen to reset the password. DVR/RTSP secrets in `config.json` are AES-256-GCM (`ENC:`). The Master Key lives in Windows Credential Manager / DPAPI; a different Windows user cannot decrypt them. The web JWT is in-process only and is discarded when KobiCAM exits.

### Google Drive (OAuth)

The manual red record button is unchanged. Drive writes separate 5-minute (default) MP4 segments for selected cameras and uploads them to a `KobiCAM_Cloud` folder. Files older than 120 hours are deleted on Drive.

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → enable **Google Drive API**.
2. Credentials → Create credentials → **OAuth client ID** → Application type **Desktop app**.
3. Paste Client ID and secret under **Settings → Cloud**.
4. **Connect to Google** — a browser window opens; the token is stored at `%APPDATA%\KobiCAM\gdrive_token.json`.
5. Check cameras to sync and enable Drive sync.

Scope: `drive.file`. If quota is exceeded, the queue pauses and the status bar shows a message.

### Analytics (people counting)

One camera only, on a separate low-FPS FFmpeg pipe so the live grid does not stall.

1. Enable it under **Settings → Analytics** and pick the camera.
2. Open **Analytics (Ctrl+Shift+A)** and click twice on the preview to draw the line. Turquoise is the in side, purple is the out side; reverse the clicks if the direction is wrong.
3. In / out / re-entry and dwell are stored in `analytics.db`. **Report CSV** exports daily, weekly and monthly Excel-ready summaries.
4. Click the corner counter to move it to another corner.

On CPU, `yolov8n` at 5 fps is the default. The weights file is `assets/yolov8n.pt`.

### Web / mobile portal

The stream runs in **KobiCAM Server Gateway** (system tray); closing the desktop VMS does not stop it. `python server_app.py` or `KobiCAM-Server-Setup.exe`. Login uses the KobiCAM username/password. RTSP URLs are never sent to the browser. At most 4 cameras.

- Status: **Settings → Server connection** (Active/Idle, URL, QR)
- Port: **Settings → Web / mobile** (default 8765)
- Different Wi-Fi / cellular: [Tailscale](https://tailscale.com) on PC and phone, same account. URL `http://100.x.y.z:8765`. Do not expose DVR ports.

### Run from source

Python 3.10+ is required.

```bat
pip install -r requirements.txt
python main.py
python server_app.py
```

Note: GUI `opencv-python` is not installed; use `opencv-python-headless`.

### Rebuild the installer

Requires Python and [Inno Setup 6](https://jrsoftware.org/isinfo.php). The package is large (torch / YOLO).

```bat
build_release.bat
build_server.bat
```

Output: `setup\Output\KobiCAM-Setup-1.3.1.exe` and `setup\Output\KobiCAM-Server-Setup-1.0.exe`.

### License

All rights reserved. Serkan Yavuz Mercan.

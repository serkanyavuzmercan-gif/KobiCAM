# KobiCAM VMS

Windows için yerel ağ kamera / DVR izleme yazılımı.  
Local-network camera and DVR monitoring software for Windows.

**Sürüm / Version:** 1.1.2  
**Geliştirici / Author:** Serkan Yavuz Mercan  
**İletişim / Contact:** [serkanyavuzmercan@gmail.com](mailto:serkanyavuzmercan@gmail.com)

---

## Türkçe

### İndirme

Kurulum dosyası kaynak kodun yanında [Releases](../../releases) sayfasındadır:

- **[KobiCAM-Setup-1.1.2.exe](../../releases/latest)** — Windows 10/11 (64-bit)

Kurulum sihirbazını çalıştırın. İsterseniz masaüstü kısayolu oluşturun. İlk açılışta kendi kullanıcı hesabınızı tanımlarsınız.

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
- Özel pencere çubuğu, klavye kısayolları (Yardım → Klavye kısayolları)

### Kullanım (kısa)

1. **Cihazlar → Cihaz Ekle** ile DVR’ın IP’sini, kendi kullanıcı adını ve şifresini girin (KobiCAM şifresi değil).
2. **Bağlan** deyince kanallar **Kameralar** listesine düşer.
3. Kamerayı ızgara hücresine sürükleyin.
4. Bağlanamazsanız **Tanıla (F8)** çalıştırın. Tarayıcıda `http://cihaz-ip` açılmıyorsa sorun ağ/kablodadır, program değildir.

Ayrıntı: uygulamada **Yardım → Nasıl çalışır? (F1)**.

### Kaynak koddan çalıştırma

Python 3.10+ gerekir.

```bat
pip install -r requirements.txt
python main.py
```

### Kurulum paketini yeniden derleme

Gerekenler: Python, [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```bat
setup.bat
```

Çıktı: `setup\Output\KobiCAM-Setup-<sürüm>.exe`

### Lisans

Tüm hakları saklıdır. Serkan Yavuz Mercan.

---

## English

### Download

The Windows installer is published on the [Releases](../../releases) page (not inside the source tree):

- **[KobiCAM-Setup-1.1.2.exe](../../releases/latest)** — Windows 10/11 (64-bit)

Run the wizard. Optionally create a desktop shortcut. On first launch you create your own user account.

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
- Custom title bar and keyboard shortcuts (Help → Keyboard shortcuts)

### Quick start

1. **Devices → Add Device**: enter the DVR IP and **the recorder’s** username/password (not the KobiCAM login).
2. **Connect** fills the **Cameras** list with channels.
3. Drag a camera onto a grid cell.
4. If it fails, run **Diagnose (F8)**. If `http://device-ip` does not open in a browser, the path/cable/network is the problem, not KobiCAM.

Full guide: **Help → How it works (F1)** in the app.

### Run from source

Python 3.10+ is required.

```bat
pip install -r requirements.txt
python main.py
```

### Rebuild the installer

Requires Python and [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```bat
setup.bat
```

Output: `setup\Output\KobiCAM-Setup-<version>.exe`

### License

All rights reserved. Serkan Yavuz Mercan.

"""Kullanım kılavuzu penceresi — programın nasıl çalıştığı ve iletişim."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, APP_EMAIL, uygulama_ikonu


_STIL = """
QDialog { background-color: #1a1d23; }
QScrollArea { border: none; background-color: #1a1d23; }
QWidget#icerik { background-color: #1a1d23; }
QLabel#baslik { color: #e8edf5; font-size: 17px; font-weight: 700; }
QLabel#bolum { color: #3d9cf0; font-size: 13px; font-weight: 700; }
QLabel#metin { color: #c5cdd8; font-size: 12px; }
QLabel#iletisim { color: #c5cdd8; font-size: 12px; }
QLabel#komut { color: #c5cdd8; font-size: 12px; }
QLabel#tus {
    color: #e8edf5;
    background-color: #12151a;
    border: 1px solid #2e3440;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
}
QPushButton#primary {
    background-color: #2b7fc4;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 22px;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: #3d9cf0; }
"""

_BOLUMLER: list[tuple[str, str]] = [
    (
        "1. Giriş",
        "Program açılışta kullanıcı adı ve şifre ister. İlk kurulumda hesabınızı "
        "kendiniz oluşturursunuz ve bir kez gösterilen kurtarma kodunu not edersiniz. "
        "Gömülü yedek yönetici hesabı yoktur. DVR/kamera şifreleri diskte AES-256-GCM "
        "ile saklanır; anahtar Windows Credential Manager / DPAPI’dedir. Windows "
        "kullanıcısı değişirse bu sırlar çözülemez.",
    ),
    (
        "2. Cihaz ekleme (DVR / NVR / IP kamera)",
        "Cihazlar → Cihaz Ekle ile kayıt cihazının IP adresini, kendi kullanıcı adını "
        "ve şifresini girin. Bağlan dediğinizde program cihazdaki kameraları okur ve "
        "hepsini soldaki Kameralar listesine ekler.\n"
        "Kameralar bir DVR'a bağlıysa tek tek kameraların değil, DVR'ın IP adresini girin.\n"
        "Portları cihazın kendi Ağ Ayarı ekranından okuyabilirsiniz: HTTP Port genelde 80, "
        "RTSP portu 554, Media Port 34567'dir. Media Port 34567 gördüyseniz cihaz "
        "XM / Xiongmai tabanlıdır; Üretici kutusundan XM seçmek bağlanmayı hızlandırır. "
        "Üretici Otomatik bırakılırsa program açık portlara bakıp kendi tahmin eder.",
    ),
    (
        "3. Ağı tarama",
        "Cihazın IP adresini bilmiyorsanız Cihazlar → Ağı Tara (F5) ile bilgisayarın "
        "bağlı olduğu ağdaki kamera ve kayıt cihazları aranır. Bulunan cihaza çift "
        "tıklayıp kullanıcı adı ve şifresini girmeniz gerekir.\n"
        "Cihaz farklı bir alt ağdaysa taramada çıkmaz; bu durumda IP'yi elle girin.",
    ),
    (
        "4. Bağlanamıyorsanız",
        "Cihaza sağ tıklayıp Tanıla (F8) deyin. Rapor önce bilgisayarın IP'si ile "
        "cihazın IP'sinin aynı ağda olup olmadığını, sonra ping ve portları gösterir.\n"
        "Tüm portlar kapalı ve ping yoksa sorun şifre değildir: paket cihaza ulaşmıyordur. "
        "DVR'ın kablosu Wi-Fi'nin bağlı olduğu modemle aynı kutuya gitmeli; kameralar ayrı "
        "switch'teyse o switch'ten modeme bir uplink kablosu çekin. DVR'da DHCP açıksa IP "
        "değişmiş olabilir — Ağ Ayarı ekranını tekrar okuyun. Modemde kablosuz izolasyon "
        "(AP Isolation) varsa kapatın veya PC'yi ethernet ile bağlayın.\n"
        "Tarayıcıda http://cihaz-ip açılmıyorsa KobiCAM de bağlanamaz.\n"
        "Kameralar bulunursa ama yayın gelmezse Kanalları elle ekle ile şablon ve kanal "
        "sayısını seçebilirsiniz.",
    ),
    (
        "5. Kameraları ekrana yerleştirme",
        "Soldaki Kameralar listesinden bir kamerayı sürükleyip istediğiniz hücreye "
        "bırakın. Çift tıklamak da boş hücreye yerleştirir.\n"
        "Görünüm menüsünden 1, 4, 9 veya 16'lı ızgara seçilir. Bir hücreye çift "
        "tıklayınca o kamera tüm ekranı kaplar, tekrar çift tıklayınca geri döner.",
    ),
    (
        "6. Hücre araçları",
        "Farenizi bir kameranın üzerine getirince üstte küçük bir araç çubuğu çıkar: "
        "anlık görüntü alma, kayıt başlatma/durdurma, sesi açma, dijital yakınlaştırma, "
        "HD/SD geçişi ve cihaz destekliyorsa PTZ yön tuşları.\n"
        "Fare tekerleği ile de yakınlaştırıp sürükleyerek gezinebilirsiniz.",
    ),
    (
        "7. Kayıt ve anlık görüntü",
        "Kayıt, görüntüyü yeniden sıkıştırmadan olduğu gibi diske yazar; bu yüzden "
        "kalite kaybı olmaz ve işlemciyi yormaz. MP4 seçiliyse kamera sesi (pcm_alaw) "
        "MP4'e sığmadığı için ses AAC olarak yazılır; görüntü yine kopyadır.\n"
        "Dosyaların nereye kaydedileceğini Ayarlar’dan seçersiniz. "
        "Dosya menüsündeki Kayıt klasörünü aç ile klasöre hızlıca ulaşabilirsiniz.",
    ),
    (
        "8. Görüntü kalitesi",
        "Düşük kalite kameranın sub-stream yayınını kullanır; çok kameralı görünümde "
        "ağ ve işlemci yükünü ciddi şekilde azaltır. Yüksek kalite main-stream kullanır.\n"
        "Tek kameraya geçtiğinizde veya yakınlaştırdığınızda program otomatik olarak "
        "yüksek kaliteye geçebilir (Ayarlar'dan kapatılabilir).",
    ),
    (
        "9. Tam ekran",
        "F11 tam ekrana geçirir; menü, sol panel ve durum çubuğu gizlenir, yalnızca "
        "kameralar kalır. Esc veya tekrar F11 ile çıkılır.",
    ),
    (
        "10. Ayarlarınızı saklama",
        "Dosya → Kullanıcı ayarlarını kaydet (Ctrl+S), pencere boyutunu, sol panel "
        "genişliğini, ızgara düzenini ve hangi kameranın hangi hücrede olduğunu saklar. "
        "Program bir sonraki açılışta aynı düzenle gelir.",
    ),
    (
        "11. Klavye kısayolları",
        "Menüdeki her komutun bir kısayolu vardır ve kısayol menünün sağında yazar. "
        "Tam listeyi Yardım → Klavye kısayolları (Ctrl+F1) ile görebilirsiniz.\n"
        "Kamera komutları (Ctrl+P anlık görüntü, Ctrl+R kayıt, Ctrl+U ses gibi) seçili "
        "ızgara hücresine uygulanır; hücreyi tek tıklayarak seçersiniz.",
    ),
    (
        "12. Bulut (isteğe bağlı)",
        "Ayarlar → Bulut’ta hesabınızı bağlayın ve otomatik senkronu açın. "
        "Seçtiğiniz kameraların kayıtları buluta gider. Sistem 5 günden eski videoları "
        "kendiliğinden siler; disk dolmaz. Kırmızı kayıt düğmesi değişmez.",
    ),
    (
        "13. Analitik (insan sayımı)",
        "Tek bir kamerada insan sayısı ve içeride kalma süresi izlenir; diğer hücreler "
        "etkilenmez. Ayarlar’dan Analitik’i açın, üst menüden Analitik’e tıklayın, "
        "kare üzerine iki kez tıklayarak sayım çizgisini çizin. Giren, çıkan ve ortalama "
        "kalma süresi kaydedilir; Ayarlar’daki canlı panelde son 24 saat özeti görünür.",
    ),
    (
        "14. Uzak izleme (web / telefon)",
        "Ayarlar → Web / mobil’de «Yayını başlat» kutusunu işaretleyip Kaydet’e basın. "
        "Aynı Wi-Fi’daysanız telefon tarayıcısına bilgisayarın IP adresi ve portunu yazın. "
        "Farklı Wi-Fi veya dışarıdan izlemek için «Uzaktan / farklı Wi-Fi’dan izle» "
        "kutusunu açın, Ngrok anahtarını girin; Kaydet sonrası Portal adresindeki "
        "bağlantıyı kullanın. Giriş, KobiCAM kullanıcı adı ve şifrenizledir. "
        "Üst menü: Uzak izleme (Ctrl+Shift+W).",
    ),
]

# Yardım → Klavye kısayolları penceresinin içeriği
KISAYOLLAR: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Dosya",
        [
            ("Kullanıcı ayarlarını kaydet", "Ctrl+S"),
            ("Kayıt klasörünü aç", "Ctrl+Shift+K"),
            ("Anlık görüntü klasörünü aç", "Ctrl+Shift+G"),
            ("Çıkış", "Ctrl+Q"),
        ],
    ),
    (
        "Görünüm",
        [
            ("1'li ızgara", "Ctrl+1"),
            ("4'lü ızgara", "Ctrl+2"),
            ("9'lu ızgara", "Ctrl+3"),
            ("16'lı ızgara", "Ctrl+4"),
            ("Düşük kalite (SD)", "Ctrl+Shift+D"),
            ("Yüksek kalite (HD)", "Ctrl+Shift+H"),
            ("Tam ekran / çıkış", "F11 — Esc"),
        ],
    ),
    (
        "Cihazlar",
        [
            ("Cihaz ekle", "Ctrl+N"),
            ("Ağı tara", "F5"),
            ("Seçili cihaza bağlan", "Ctrl+B"),
            ("Kanalları elle ekle", "Ctrl+Shift+N"),
            ("Seçili cihazı tanıla", "F8"),
            ("Seçili cihazı düzenle", "F2"),
            ("Seçili cihazı sil", "Ctrl+Shift+Del"),
        ],
    ),
    (
        "Kamera listesi",
        [
            ("Manuel RTSP kamera ekle", "Ctrl+M"),
            ("Seçili kamerayı hücreye bağla", "Ctrl+Return"),
            ("Seçili kamerayı düzenle", "Shift+F2"),
            ("Seçili kamerayı sil", "Shift+Del"),
        ],
    ),
    (
        "Seçili ızgara hücresi",
        [
            ("Anlık görüntü al", "Ctrl+P"),
            ("Kaydı başlat / durdur", "Ctrl+R"),
            ("Canlı sesi aç / kapat", "Ctrl+U"),
            ("Hücre kalitesini değiştir", "Ctrl+E"),
            ("Yakınlaştırmayı sıfırla", "Ctrl+0"),
            ("Seçili hücreyi boşalt", "Ctrl+Del"),
        ],
    ),
    (
        "Ayarlar ve Yardım",
        [
            ("Ayarlar", "Ctrl+,"),
            ("Nasıl çalışır?", "F1"),
            ("Klavye kısayolları", "Ctrl+F1"),
            ("İletişim", "Shift+F1"),
        ],
    ),
    (
        "Analitik / Uzak izleme",
        [
            ("Analitik penceresi", "Ctrl+Shift+A"),
            ("Uzak izleme", "Ctrl+Shift+W"),
        ],
    ),
]


class HelpDialog(QDialog):
    """Programın nasıl kullanılacağını anlatan pencere."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Nasıl Çalışır?")
        self.setWindowIcon(uygulama_ikonu())
        self.setModal(True)
        self.resize(620, 620)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(24, 20, 24, 16)
        kok.setSpacing(12)

        baslik = QLabel("KobiCAM VMS nasıl çalışır?")
        baslik.setObjectName("baslik")
        kok.addWidget(baslik)

        icerik = QWidget()
        icerik.setObjectName("icerik")
        icerik_y = QVBoxLayout(icerik)
        icerik_y.setContentsMargins(0, 0, 12, 0)
        icerik_y.setSpacing(6)
        for bolum_basligi, metin in _BOLUMLER:
            etiket = QLabel(bolum_basligi)
            etiket.setObjectName("bolum")
            icerik_y.addWidget(etiket)
            govde = QLabel(metin)
            govde.setObjectName("metin")
            govde.setWordWrap(True)
            icerik_y.addWidget(govde)
            icerik_y.addSpacing(6)
        icerik_y.addStretch(1)

        kaydirma = QScrollArea()
        kaydirma.setWidgetResizable(True)
        kaydirma.setWidget(icerik)
        kok.addWidget(kaydirma, 1)

        iletisim = QLabel(
            "Soru, öneri ve destek için: "
            f'<a style="color:#3d9cf0; text-decoration:none;" href="mailto:{APP_EMAIL}">{APP_EMAIL}</a>'
        )
        iletisim.setObjectName("iletisim")
        iletisim.setTextFormat(Qt.TextFormat.RichText)
        iletisim.setOpenExternalLinks(True)
        iletisim.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        kok.addWidget(iletisim)

        alt = QHBoxLayout()
        alt.addStretch(1)
        kapat = QPushButton("Kapat")
        kapat.setObjectName("primary")
        kapat.setDefault(True)
        kapat.clicked.connect(self.accept)
        alt.addWidget(kapat)
        kok.addLayout(alt)


class ShortcutsDialog(QDialog):
    """Menüdeki tüm komutların klavye kısayollarını listeler."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Klavye Kısayolları")
        self.setWindowIcon(uygulama_ikonu())
        self.setModal(True)
        self.resize(460, 620)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(24, 20, 24, 16)
        kok.setSpacing(12)

        baslik = QLabel("Klavye kısayolları")
        baslik.setObjectName("baslik")
        kok.addWidget(baslik)

        icerik = QWidget()
        icerik.setObjectName("icerik")
        icerik_y = QVBoxLayout(icerik)
        icerik_y.setContentsMargins(0, 0, 12, 0)
        icerik_y.setSpacing(4)
        for grup_adi, satirlar in KISAYOLLAR:
            etiket = QLabel(grup_adi)
            etiket.setObjectName("bolum")
            icerik_y.addWidget(etiket)
            for komut, tuslar in satirlar:
                satir = QHBoxLayout()
                satir.setContentsMargins(0, 0, 0, 0)
                ad = QLabel(komut)
                ad.setObjectName("komut")
                tus = QLabel(tuslar)
                tus.setObjectName("tus")
                satir.addWidget(ad, 1)
                satir.addWidget(tus, 0, Qt.AlignmentFlag.AlignRight)
                icerik_y.addLayout(satir)
            icerik_y.addSpacing(10)
        icerik_y.addStretch(1)

        kaydirma = QScrollArea()
        kaydirma.setWidgetResizable(True)
        kaydirma.setWidget(icerik)
        kok.addWidget(kaydirma, 1)

        alt = QHBoxLayout()
        alt.addStretch(1)
        kapat = QPushButton("Kapat")
        kapat.setObjectName("primary")
        kapat.setDefault(True)
        kapat.clicked.connect(self.accept)
        alt.addWidget(kapat)
        kok.addLayout(alt)

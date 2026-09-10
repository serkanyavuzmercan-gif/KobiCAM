"""
Dinamik kamera ızgarası (1, 4, 9, 16 hücre).

Hücreler slotu doldurur; kare oranları CameraWidget içinde letterbox ile korunur.
Çift tık ile tek hücreye büyüme / eski düzene dönüş.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QGridLayout, QWidget

from ui.camera_widget import CameraWidget
from stream_worker import StreamWorker


class CameraGrid(QWidget):
    """1x1 / 2x2 / 3x3 / 4x4 düzen yöneticisi."""

    DESTEKLENEN = (1, 4, 9, 16)
    HUCRe_HAVUZU = 16

    def __init__(self, hucre_sayisi: int = 4, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hucre_sayisi = hucre_sayisi if hucre_sayisi in self.DESTEKLENEN else 4
        self._onceki_duzen = self._hucre_sayisi
        self._expanded_index: int | None = None
        self._secili = 0
        self._prefer_sub = True
        self._main_on_zoom = True

        self._yerlesim = QGridLayout(self)
        self._yerlesim.setContentsMargins(4, 4, 4, 4)
        self._yerlesim.setSpacing(4)
        self._kenarlik = 4

        self._widgets: list[CameraWidget] = []
        for i in range(self.HUCRe_HAVUZU):
            hucre = CameraWidget(self)
            hucre.double_clicked.connect(lambda idx=i: self._hucre_cift_tik(idx))
            hucre.clicked.connect(lambda idx=i: self.sec(idx))
            self._widgets.append(hucre)

        self._diz()
        self.sec(0)

    @property
    def layout_count(self) -> int:
        return self._hucre_sayisi

    @property
    def expanded_index(self) -> int | None:
        return self._expanded_index

    @property
    def selected_index(self) -> int:
        return self._secili

    def widgets(self) -> list[CameraWidget]:
        return self._widgets

    def visible_count(self) -> int:
        if self._expanded_index is not None:
            return 1
        return self._hucre_sayisi

    def set_layout_count(self, hucre_sayisi: int) -> None:
        """Izgara boyutunu değiştirir ve büyütmeyi sıfırlar."""
        if hucre_sayisi not in self.DESTEKLENEN:
            return
        self._hucre_sayisi = hucre_sayisi
        self._onceki_duzen = hucre_sayisi
        self._expanded_index = None
        if self._secili >= hucre_sayisi:
            self._secili = 0
        self._diz()
        self.sec(self._secili)
        self.akislari_uygula(self._prefer_sub, self._main_on_zoom)

    def set_tam_ekran(self, aktif: bool) -> None:
        """Tam ekranda hücre kenarlıklarını daraltır."""
        kenar = 0 if aktif else self._kenarlik
        self._yerlesim.setContentsMargins(kenar, kenar, kenar, kenar)
        self._yerlesim.setSpacing(0 if aktif else self._kenarlik)

    def sec(self, indeks: int) -> None:
        self._secili = indeks
        for i, w in enumerate(self._widgets):
            w.set_selected(i == indeks)

    def _hucre_cift_tik(self, indeks: int) -> None:
        if self._expanded_index == indeks:
            self._expanded_index = None
            self._hucre_sayisi = self._onceki_duzen
        else:
            if self._expanded_index is None:
                self._onceki_duzen = self._hucre_sayisi
            self._expanded_index = indeks
            self._secili = indeks
        self._diz()
        self.sec(self._secili)
        self.akislari_uygula(self._prefer_sub, self._main_on_zoom)

    def akislari_uygula(self, prefer_sub: bool, main_on_zoom: bool) -> None:
        """Görünür moda göre sub/main seçimini hücrelere bildirir."""
        self._prefer_sub = prefer_sub
        self._main_on_zoom = main_on_zoom
        tekli = self._expanded_index is not None or self._hucre_sayisi == 1
        for i, w in enumerate(self._widgets):
            kullan_main = False
            if main_on_zoom and tekli:
                if self._expanded_index is not None:
                    kullan_main = i == self._expanded_index
                else:
                    kullan_main = i == 0
            w.set_stream_prefs(prefer_sub and not kullan_main, main_on_zoom)

    def assign_camera(self, indeks: int, kamera: dict | None) -> None:
        if 0 <= indeks < len(self._widgets):
            self._widgets[indeks].bind_camera(
                kamera,
                use_substream=self._slot_sub_mu(indeks),
            )
            self.sec(indeks)

    def _slot_sub_mu(self, indeks: int) -> bool:
        tekli = self._expanded_index is not None or self._hucre_sayisi == 1
        if self._main_on_zoom and tekli:
            if self._expanded_index is not None:
                return not (indeks == self._expanded_index)
            return indeks != 0
        return self._prefer_sub

    def assign_to_selected_or_empty(self, kamera: dict) -> int:
        """Seçili hücre boşsa oraya, değilse ilk boş görünür slota, yoksa seçiliye bağlar."""
        gorunur = self._gorunur_indeksler()
        secili = self._secili if self._secili in gorunur else gorunur[0]
        if self._widgets[secili].camera is None:
            hedef = secili
        else:
            hedef = secili
            for i in gorunur:
                if self._widgets[i].camera is None:
                    hedef = i
                    break
        self.assign_camera(hedef, kamera)
        return hedef

    def _gorunur_indeksler(self) -> list[int]:
        if self._expanded_index is not None:
            return [self._expanded_index]
        return list(range(self._hucre_sayisi))

    def stop_all(self) -> None:
        """Tüm hücre işçilerini ve kayıtları paralel durdurup bitmelerini bekler."""
        isciler: list[StreamWorker] = []
        for w in self._widgets:
            w.stop_recording()
            w.stop_audio()
            worker = w.detach_worker()
            if worker is not None:
                worker.request_stop()
                isciler.append(worker)
        for worker in isciler:
            if worker.wait(3000):
                worker.deleteLater()
            else:
                worker.finished.connect(worker.deleteLater)

    def _diz(self) -> None:
        while self._yerlesim.count():
            self._yerlesim.takeAt(0)

        for r in range(4):
            self._yerlesim.setRowStretch(r, 0)
            self._yerlesim.setColumnStretch(r, 0)

        if self._expanded_index is not None:
            for i, w in enumerate(self._widgets):
                goster = i == self._expanded_index
                w.setVisible(goster)
                if goster:
                    self._yerlesim.addWidget(w, 0, 0)
                    w.resume_if_needed()
                elif w.camera is not None:
                    w.stop_recording()
                    w.stop_audio()
                    w.stop_stream(wait=False)
            self._yerlesim.setRowStretch(0, 1)
            self._yerlesim.setColumnStretch(0, 1)
            return

        kenar = int(self._hucre_sayisi ** 0.5)
        for i, w in enumerate(self._widgets):
            if i < self._hucre_sayisi:
                satir, sutun = divmod(i, kenar)
                self._yerlesim.addWidget(w, satir, sutun)
                w.setVisible(True)
                w.resume_if_needed()
            else:
                w.setVisible(False)
                if w.camera is not None:
                    w.stop_recording()
                    w.stop_audio()
                    w.stop_stream(wait=False)
        for r in range(kenar):
            self._yerlesim.setRowStretch(r, 1)
            self._yerlesim.setColumnStretch(r, 1)

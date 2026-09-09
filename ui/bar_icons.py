"""Küçük hücre-üstü ikonlar (ekstra dosya yok, QPainter ile çizilir)."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygon


def _tuval(boyut: int = 18) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(boyut, boyut)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pm, p


def _bitir(p: QPainter, pm: QPixmap) -> QIcon:
    p.end()
    return QIcon(pm)


def ikon_yakala() -> QIcon:
    """Ekran yakalama / anlık görüntü."""
    pm, p = _tuval()
    p.setPen(QPen(QColor("#e8edf5"), 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(2, 5, 14, 10, 2, 2)
    p.drawEllipse(6, 7, 6, 6)
    p.fillRect(8, 3, 3, 2, QColor("#e8edf5"))
    return _bitir(p, pm)


def ikon_kayit(aktif: bool = False) -> QIcon:
    pm, p = _tuval()
    renk = QColor("#e85d5d") if aktif else QColor("#e8edf5")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(renk)
    p.drawEllipse(4, 4, 10, 10)
    return _bitir(p, pm)


def ikon_hoparlor(acik: bool = True) -> QIcon:
    pm, p = _tuval()
    p.setPen(QPen(QColor("#e8edf5"), 1.3))
    p.setBrush(QColor("#e8edf5"))
    yol = QPainterPath()
    yol.moveTo(3, 7)
    yol.lineTo(7, 7)
    yol.lineTo(11, 4)
    yol.lineTo(11, 14)
    yol.lineTo(7, 11)
    yol.lineTo(3, 11)
    yol.closeSubpath()
    p.drawPath(yol)
    if acik:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(11, 6, 5, 6, -50 * 16, 100 * 16)
    else:
        p.setPen(QPen(QColor("#e85d5d"), 1.5))
        p.drawLine(4, 4, 14, 14)
    return _bitir(p, pm)


def ikon_buyutec() -> QIcon:
    pm, p = _tuval()
    p.setPen(QPen(QColor("#e8edf5"), 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(3, 3, 10, 10)
    p.drawLine(11, 11, 15, 15)
    p.drawLine(6, 8, 10, 8)
    p.drawLine(8, 6, 8, 10)
    return _bitir(p, pm)


def ikon_hd(yuksek: bool) -> QIcon:
    pm, p = _tuval()
    p.setPen(QColor("#7fd07f") if yuksek else QColor("#e8edf5"))
    p.setFont(p.font())
    font = p.font()
    font.setBold(True)
    font.setPixelSize(8)
    p.setFont(font)
    p.drawText(QRect(0, 0, 18, 18), Qt.AlignmentFlag.AlignCenter, "HD" if yuksek else "SD")
    return _bitir(p, pm)


def ikon_kucult() -> QIcon:
    pm, p = _tuval(16)
    p.setPen(QPen(QColor("#e8edf5"), 1.3))
    p.drawLine(4, 9, 12, 9)
    return _bitir(p, pm)


def ikon_buyut(tam: bool = False) -> QIcon:
    """tam=True ise 'eski boyuta dön' simgesi çizilir."""
    pm, p = _tuval(16)
    p.setPen(QPen(QColor("#e8edf5"), 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if tam:
        p.drawRect(3, 6, 7, 7)
        p.drawLine(6, 4, 13, 4)
        p.drawLine(13, 4, 13, 11)
    else:
        p.drawRect(4, 4, 9, 9)
    return _bitir(p, pm)


def ikon_kapat() -> QIcon:
    pm, p = _tuval(16)
    p.setPen(QPen(QColor("#e8edf5"), 1.4))
    p.drawLine(4, 4, 12, 12)
    p.drawLine(12, 4, 4, 12)
    return _bitir(p, pm)


def ikon_ok(yon: str) -> QIcon:
    """yon: left, right, up, down"""
    pm, p = _tuval(16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#e8edf5"))
    c = 8
    if yon == "up":
        noktalar = [QPoint(c, 3), QPoint(13, 12), QPoint(3, 12)]
    elif yon == "down":
        noktalar = [QPoint(c, 13), QPoint(13, 4), QPoint(3, 4)]
    elif yon == "left":
        noktalar = [QPoint(3, c), QPoint(12, 3), QPoint(12, 13)]
    else:
        noktalar = [QPoint(13, c), QPoint(4, 3), QPoint(4, 13)]
    p.drawPolygon(QPolygon(noktalar))
    return _bitir(p, pm)

"""Small vector icons drawn with Qt, independent of fonts and external assets."""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
APP_ICON_PATH = ASSET_DIR / "corgi.svg"


def asset_icon(filename: str) -> QIcon:
    """Load an SVG shipped with Navi for a toolbar button."""
    return QIcon(str(ASSET_DIR / filename))


def app_icon() -> QIcon:
    """Load Navi's project icon, falling back to the built-in vector mark."""
    if APP_ICON_PATH.is_file():
        icon = QIcon(str(APP_ICON_PATH))
        if not icon.isNull():
            return icon
    return make_icon("app")


def make_icon(kind: str, color: str = "#536071") -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 24, size / 24)
        pen = QPen(QColor(color), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if kind == "app":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#5268e8"))
            painter.drawRoundedRect(QRectF(1, 1, 22, 22), 6, 6)
            painter.setPen(QPen(QColor("#ffffff"), 2.2))
            path = QPainterPath(QPointF(7, 17))
            path.lineTo(7, 7)
            path.lineTo(17, 17)
            path.lineTo(17, 7)
            painter.drawPath(path)
        elif kind == "pin":
            path = QPainterPath(QPointF(8, 4))
            path.lineTo(16, 4)
            path.lineTo(15, 6)
            path.lineTo(15, 11)
            path.lineTo(18, 14)
            path.lineTo(6, 14)
            path.lineTo(9, 11)
            path.lineTo(9, 6)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(QPointF(12, 14), QPointF(12, 21))
        elif kind == "close":
            painter.drawLine(QPointF(7, 7), QPointF(17, 17))
            painter.drawLine(QPointF(17, 7), QPointF(7, 17))
        elif kind == "send":
            path = QPainterPath(QPointF(5, 5))
            path.lineTo(20, 12)
            path.lineTo(5, 19)
            path.lineTo(8, 12)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(QPointF(8, 12), QPointF(15, 12))
        else:
            painter.end()
            raise ValueError(f"Unknown icon: {kind}")
        painter.end()
        icon.addPixmap(pixmap)
    return icon

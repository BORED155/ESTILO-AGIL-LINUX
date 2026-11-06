"""Vista previa de un tema: cursores animados (se prueban al pasar el mouse) e iconos de ejemplo."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from .. import xcursor
from ..temas import CURSORES_MUESTRA, ICONOS_MUESTRA, Tema

ANCHO_CELDA = 112


def pixmap_de(imagen: xcursor.Imagen) -> QPixmap:
    qi = QImage(imagen.pixeles, imagen.ancho, imagen.alto, imagen.ancho * 4, QImage.Format_ARGB32_Premultiplied)
    return QPixmap.fromImage(qi.copy())


class CeldaCursor(QFrame):
    """Un cursor del tema: se anima si tiene varios cuadros y se vuelve el cursor real al pasar el mouse."""

    def __init__(self, titulo: str, cuadros: list[xcursor.Imagen], lado: int, parent=None):
        super().__init__(parent)
        self.setObjectName("celda")
        self.setFixedSize(ANCHO_CELDA, max(lado, 48) + 52)
        self.cuadros = [(pixmap_de(c), c) for c in cuadros]
        self.indice = 0
        self.imagen = QLabel(alignment=Qt.AlignCenter)
        self.imagen.setMinimumHeight(max(lado, 48) + 8)
        texto = QLabel(titulo, alignment=Qt.AlignCenter)
        texto.setObjectName("leyenda")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 4)
        lay.addWidget(self.imagen, 1)
        lay.addWidget(texto)
        self._mostrar()
        pm, c = self.cuadros[0]
        self.setCursor(QCursor(pm, c.x_activo, c.y_activo))
        self.setToolTip("Pase el mouse por aquí para probar este cursor")
        self.temporizador = None
        if len(self.cuadros) > 1:
            self.temporizador = QTimer(self)
            self.temporizador.timeout.connect(self._siguiente)
            self.temporizador.start(max(20, self.cuadros[0][1].retardo or 50))

    def _mostrar(self) -> None:
        self.imagen.setPixmap(self.cuadros[self.indice][0])

    def _siguiente(self) -> None:
        self.indice = (self.indice + 1) % len(self.cuadros)
        self._mostrar()
        self.temporizador.setInterval(max(20, self.cuadros[self.indice][1].retardo or 50))


class CeldaIcono(QFrame):
    def __init__(self, titulo: str, ruta, lado: int = 48, parent=None):
        super().__init__(parent)
        self.setObjectName("celda")
        self.setFixedSize(ANCHO_CELDA - 12, lado + 46)
        img = QLabel(alignment=Qt.AlignCenter)
        img.setPixmap(QIcon(str(ruta)).pixmap(QSize(lado, lado)))
        texto = QLabel(titulo, alignment=Qt.AlignCenter)
        texto.setObjectName("leyenda")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 4)
        lay.addWidget(img, 1)
        lay.addWidget(texto)
        self.setToolTip(str(ruta.name))


def _cuadricula(celdas: list[QWidget], columnas: int) -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    g.setSpacing(8)
    g.setContentsMargins(0, 0, 0, 0)
    for i, c in enumerate(celdas):
        g.addWidget(c, i // columnas, i % columnas)
    g.setColumnStretch(columnas, 1)
    return w


class PanelVista(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.tema: Tema | None = None
        self.tamano = 32
        self.oscuro = False
        self.solo = "cursores"
        self.mostrar(None)

    def poner_oscuro(self, si: bool) -> None:
        self.oscuro = si
        self.mostrar(self.tema)

    def mostrar(self, tema: Tema | None, tamano: int | None = None, solo: str | None = None) -> None:
        """`solo`: "cursores" o "iconos" para mostrar únicamente esa parte del tema."""
        self.tema = tema
        if solo:
            self.solo = solo
        if tamano:
            self.tamano = tamano
        cont = QWidget()
        if self.oscuro:
            cont.setStyleSheet("QFrame#celda { background: #2d2d2d; border-color: #555555; }"
                               "QFrame#celda:hover { border-color: #64b5f6; } QLabel#leyenda { color: #eeeeee; }")
        lay = QVBoxLayout(cont)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(10)
        if tema is None:
            vacio = QLabel("Arrastre arriba el archivo de un tema, pegue un enlace o elija un tema de la lista "
                           "para verlo aquí.")
            vacio.setWordWrap(True)
            vacio.setAlignment(Qt.AlignCenter)
            vacio.setObjectName("ayuda")
            lay.addStretch(1)
            lay.addWidget(vacio)
            lay.addStretch(2)
            self.setWidget(cont)
            return
        if getattr(tema, "tiene_fondo", False):
            self._mostrar_fondo(tema, lay)
            self.setWidget(cont)
            return
        columnas = max(1, (self.viewport().width() - 20) // (ANCHO_CELDA + 8))
        if tema.tiene_cursores and self.solo == "cursores":
            celdas = []
            for titulo, nombres in CURSORES_MUESTRA:
                ruta = tema.archivo_cursor(nombres)
                if ruta is None:
                    continue
                try:
                    imagenes = xcursor.leer(ruta)
                except (OSError, xcursor.NoEsCursor):
                    continue
                celdas.append(CeldaCursor(titulo, xcursor.cuadros(imagenes, self.tamano), self.tamano))
            t = QLabel(f"Pase el mouse sobre cada cursor para probarlo ({len(celdas)} de muestra)")
            lay.addWidget(t)
            lay.addWidget(_cuadricula(celdas, columnas) if celdas else QLabel("No se pudieron leer los cursores."))
        if tema.tiene_iconos and self.solo == "iconos":
            celdas = []
            for titulo, nombres in ICONOS_MUESTRA:
                ruta = tema.archivo_icono(nombres, 48)
                if ruta is not None:
                    celdas.append(CeldaIcono(titulo, ruta, 48))
            lay.addWidget(QLabel(f"{len(celdas)} iconos de muestra"))
            if celdas:
                lay.addWidget(_cuadricula(celdas, max(1, (self.viewport().width() - 20) // (ANCHO_CELDA - 4))))
            else:
                lay.addWidget(QLabel("Este tema solo trae algunos iconos; los demás los toma del tema "
                                     f"«{', '.join(tema.hereda) or 'hicolor'}»."))
        lay.addStretch(1)
        self.setWidget(cont)

    def _mostrar_fondo(self, fondo, lay) -> None:
        from PySide6.QtGui import QImageReader

        lector = QImageReader(str(fondo.ruta))
        lector.setAutoTransform(True)
        original = lector.size()
        ancho = max(200, self.viewport().width() - 30)
        alto = max(150, self.viewport().height() - 70)
        if original.isValid():
            escala = min(ancho / original.width(), alto / original.height(), 1.0)
            lector.setScaledSize(original * escala)
        imagen = lector.read()
        marco = QLabel(alignment=Qt.AlignCenter)
        marco.setObjectName("fondo")
        if imagen.isNull():
            marco.setText("No se pudo mostrar la imagen.")
        else:
            marco.setPixmap(QPixmap.fromImage(imagen))
        marco.setStyleSheet("QLabel#fondo { border: 6px solid #263238; border-radius: 8px; background: #263238; }")
        # que la imagen no agrande la ventana: se adapta al espacio disponible
        from PySide6.QtWidgets import QSizePolicy

        marco.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        if not imagen.isNull():
            marco.setFixedHeight(imagen.height() + 12)
            marco.setMaximumWidth(imagen.width() + 12)
        lay.addWidget(marco, 0, Qt.AlignHCenter)
        if original.isValid():
            mb = fondo.ruta.stat().st_size / 1024 / 1024 if fondo.ruta.exists() else 0
            info = QLabel(f"{original.width()} × {original.height()} px  ·  {mb:.1f} MB  ·  {fondo.ruta.name}",
                          alignment=Qt.AlignCenter)
            info.setObjectName("leyenda")
            lay.addWidget(info)
        lay.addStretch(1)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.tema is not None and (getattr(self.tema, "tiene_fondo", False) or
                                      e.oldSize().width() // (ANCHO_CELDA + 8) != e.size().width() // (ANCHO_CELDA + 8)):
            QTimer.singleShot(0, lambda: self.mostrar(self.tema))



class Interruptor(QCheckBox):
    """Casilla con forma de interruptor moderno (píldora redondeada con un círculo que se desliza)."""

    ANCHO, ALTO = 38, 20

    def __init__(self, texto: str = "", parent=None):
        super().__init__(texto, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 0.0
        self._anim = QVariantAnimation(self, duration=140)
        self._anim.valueChanged.connect(self._mover)
        self.toggled.connect(self._animar)

    def _mover(self, v) -> None:
        self._pos = float(v)
        self.update()

    def _animar(self, activo: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if activo else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:
        texto = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(self.ANCHO + 8 + texto + 4, max(self.ALTO + 4, self.fontMetrics().height() + 4))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = (self.height() - self.ALTO) / 2
        apagado, encendido = QColor("#b0bec5"), QColor("#2e7d32")
        fondo = QColor(
            int(apagado.red() + (encendido.red() - apagado.red()) * self._pos),
            int(apagado.green() + (encendido.green() - apagado.green()) * self._pos),
            int(apagado.blue() + (encendido.blue() - apagado.blue()) * self._pos))
        if not self.isEnabled():
            fondo = QColor("#e0e0e0")
        p.setPen(Qt.NoPen)
        p.setBrush(fondo)
        p.drawRoundedRect(QRectF(0, y, self.ANCHO, self.ALTO), self.ALTO / 2, self.ALTO / 2)
        margen = 3
        d = self.ALTO - 2 * margen
        x = margen + (self.ANCHO - d - 2 * margen) * self._pos
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, y + margen, d, d))
        p.setPen(self.palette().color(self.foregroundRole()))
        p.drawText(QRectF(self.ANCHO + 8, 0, self.width() - self.ANCHO - 8, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()

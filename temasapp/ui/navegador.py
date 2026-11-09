"""Navegador integrado para buscar temas: lo que se descarga en él pasa directo a la vista previa."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton, QVBoxLayout

from ..escritorio import entorno_sistema

# (sección, [(texto, dirección)])
SITIOS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Cursores", [
        ("gnome-look.org — los mejor valorados", "https://www.gnome-look.org/browse?cat=107&ord=rating"),
        ("gnome-look.org — los más nuevos", "https://www.gnome-look.org/browse?cat=107&ord=latest"),
        ("KDE Store — cursores", "https://store.kde.org/browse?cat=107&ord=rating"),
        ("GitHub — los más populares", "https://github.com/search?q=cursor+theme+linux&type=repositories&s=stars"),
    ]),
    ("Iconos", [
        ("gnome-look.org — los mejor valorados", "https://www.gnome-look.org/browse?cat=132&ord=rating"),
        ("gnome-look.org — los más nuevos", "https://www.gnome-look.org/browse?cat=132&ord=latest"),
        ("KDE Store — iconos", "https://store.kde.org/browse?cat=132&ord=rating"),
        ("GitHub — los más populares", "https://github.com/search?q=icon+theme+linux&type=repositories&s=stars"),
    ]),
    ("Fondos de pantalla", [
        ("gnome-look.org — los mejor valorados", "https://www.gnome-look.org/browse?cat=300&ord=rating"),
        ("gnome-look.org — los más nuevos", "https://www.gnome-look.org/browse?cat=300&ord=latest"),
        ("Unsplash — fotos para escritorio", "https://unsplash.com/es/fondos-de-pantalla/escritorio"),
    ]),
]

_PAGINA_TEMA = re.compile(r"/p/\d+|^https?://github\.com/[\w.-]+/[\w.-]+/?$", re.I)


def es_pagina_de_tema(url: str) -> bool:
    return bool(_PAGINA_TEMA.search(url))


def abrir_externo(url: str) -> None:
    try:
        subprocess.Popen(["xdg-open", url], env=entorno_sistema(), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        QDesktopServices.openUrl(QUrl(url))


def hay_navegador_integrado() -> bool:
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        return False
    return True


_perfil = None


def _perfil_compartido():
    """Un solo perfil para todo el programa (guarda cookies: la página no vuelve a pedir lo mismo)."""
    global _perfil
    if _perfil is None:
        from PySide6.QtWebEngineCore import QWebEngineProfile

        _perfil = QWebEngineProfile("temasapp")
    return _perfil


class Navegador(QDialog):
    def __init__(self, ventana, url: str):
        super().__init__(ventana, Qt.Window)
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView

        class Pagina(QWebEnginePage):
            def createWindow(self, _tipo):   # los enlaces «en otra pestaña» se abren aquí mismo
                return self

        self.ventana = ventana
        self.setWindowTitle("Buscar temas")
        self.resize(1200, 820)
        self.perfil = _perfil_compartido()
        self.vista = QWebEngineView(self)
        self.pagina = Pagina(self.perfil, self.vista)
        self.vista.setPage(self.pagina)
        self.perfil.downloadRequested.connect(self._descarga)

        def boton(texto, tip, funcion):
            b = QToolButton()
            b.setText(texto)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(funcion)
            return b

        self.direccion = QLineEdit()
        self.direccion.returnPressed.connect(self._ir)
        self.b_usar = QPushButton("Usar este tema en el programa")
        self.b_usar.setObjectName("aplicar")
        self.b_usar.setToolTip("Descarga el tema de esta página y lo muestra en la vista previa")
        self.b_usar.clicked.connect(self._usar)
        b_externo = QPushButton("Abrir en mi navegador")
        b_externo.clicked.connect(lambda: abrir_externo(self.vista.url().toString()))
        barra = QHBoxLayout()
        barra.addWidget(boton("◀", "Atrás", self.vista.back))
        barra.addWidget(boton("▶", "Adelante", self.vista.forward))
        barra.addWidget(boton("⟳", "Recargar", self.vista.reload))
        barra.addWidget(self.direccion, 1)
        barra.addWidget(self.b_usar)
        barra.addWidget(b_externo)
        self.ayuda = QLabel("Busque un tema que le guste, entre a su página y pulse <b>«Usar este tema en el "
                            "programa»</b> (o el botón <i>Download</i> de la página). Se mostrará en la vista previa "
                            "sin instalar nada todavía.")
        self.ayuda.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(barra)
        lay.addWidget(self.ayuda)
        lay.addWidget(self.vista, 1)
        self.vista.urlChanged.connect(self._url_cambiada)
        self.vista.titleChanged.connect(lambda t: self.setWindowTitle(f"Buscar temas — {t}"))
        self.ir(url)

    def ir(self, url: str) -> None:
        self.vista.setUrl(QUrl(url))
        self._url_cambiada(QUrl(url))

    def _ir(self) -> None:
        texto = self.direccion.text().strip()
        if texto and not re.match(r"^https?://", texto):
            texto = "https://" + texto
        self.ir(texto)

    def _url_cambiada(self, url: QUrl) -> None:
        texto = url.toString()
        self.direccion.setText(texto)
        self.b_usar.setEnabled(es_pagina_de_tema(texto))

    def _a_la_vista_previa(self) -> None:
        self.ventana.showNormal()
        self.ventana.raise_()
        self.ventana.activateWindow()

    def _usar(self) -> None:
        self.ventana.enlace.setText(self.vista.url().toString())
        self.ventana.descargar_enlace()
        self._a_la_vista_previa()

    def _descarga(self, pedido) -> None:
        if pedido.page() is not self.pagina:
            return
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

        carpeta = Path(self.ventana.trabajo) / "navegador"
        carpeta.mkdir(parents=True, exist_ok=True)
        pedido.setDownloadDirectory(str(carpeta))
        nombre = pedido.downloadFileName()
        self.ventana.statusBar().showMessage(f"Descargando {nombre}…")

        def terminado():
            if not pedido.isFinished():
                return
            if pedido.state() == QWebEngineDownloadRequest.DownloadCompleted:
                ruta = Path(pedido.downloadDirectory()) / pedido.downloadFileName()
                self.ventana.cargar(ruta)
                self._a_la_vista_previa()
            else:
                self.ventana.statusBar().showMessage(f"No se pudo descargar {nombre}.", 8000)

        pedido.isFinishedChanged.connect(terminado)
        pedido.accept()

    def liberar(self) -> None:
        """Cierra y borra la página antes que el perfil (si no, Qt avisa al salir)."""
        from shiboken6 import delete

        self.close()
        self.vista.stop()
        delete(self.pagina)

    def closeEvent(self, e) -> None:
        super().closeEvent(e)

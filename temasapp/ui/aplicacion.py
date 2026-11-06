"""Arranque de la interfaz gráfica."""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLoggingCategory, Qt, QTranslator
from PySide6.QtWidgets import QApplication


def ejecutar(argumentos: list[str]) -> int:
    QLoggingCategory.setFilterRules("qt.svg.warning=false")  # muchos temas traen SVG con detalles que Qt ignora
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # lo necesita el navegador integrado
    app = QApplication([sys.argv[0]] + argumentos)
    app.setOrganizationName("temasapp")
    app.setApplicationName("Estilo Ágil")
    app.setDesktopFileName("estilo-agil")
    traductor = QTranslator(app)
    if traductor.load("qtbase_es", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(traductor)
    from .ventana import VentanaPrincipal

    ventana = VentanaPrincipal()
    ventana.show()
    archivos = [a for a in argumentos if not a.startswith("-")]
    if archivos:
        ventana.recibir(archivos)
    return app.exec()

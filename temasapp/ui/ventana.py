"""Ventana principal."""

from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QMessageBox, QProgressBar, QPushButton, QSplitter, QTabWidget, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import __version__, archivos
from ..escritorio import (NOMBRES_ENTORNO, entorno_sistema, renombrar_clave, renombrar_tema, Escritorio, desinstalar, es_del_usuario, instalar, instalado_igual, ocultar, ocultos,
                          favoritos, marcar_favorito)
from .. import fondos as mod_fondos
from ..fondos import Fondo
from ..temas import Tema, agrupar, buscar_temas, temas_instalados
from .navegador import abrir_externo
from .vistas import Interruptor, PanelVista

TAMANOS = [24, 28, 32, 36, 40, 48, 56, 64, 72, 96]
TIPOS = ["cursores", "iconos", "fondos"]
AJUSTES = [("zoom", "Rellenar la pantalla"), ("scaled", "Ajustar sin recortar"), ("centered", "Centrar"),
           ("stretched", "Estirar"), ("wallpaper", "Mosaico"), ("spanned", "Extender a todas las pantallas")]


def _de_tipo(t, tipo: str) -> bool:
    return {"cursores": t.tiene_cursores, "iconos": t.tiene_iconos, "fondos": t.tiene_fondo}[tipo]


def _del_usuario(t) -> bool:
    return mod_fondos.es_del_usuario(t) if isinstance(t, Fondo) else es_del_usuario(t)


def _instalar(t, reemplazar: bool = False):
    return mod_fondos.instalar(t, reemplazar) if isinstance(t, Fondo) else instalar(t, reemplazar=reemplazar)


def _instalado_igual(t) -> bool:
    return mod_fondos.instalado_igual(t) if isinstance(t, Fondo) else instalado_igual(t)


def _desinstalar(t) -> bool:
    return mod_fondos.desinstalar(t) if isinstance(t, Fondo) else desinstalar(t)

ESTILO = """
QFrame#zona { border: 2px dashed #000000; border-radius: 12px; background: palette(base); }
QFrame#zona[activa="true"] { border-color: #2e7d32; background: #e8f5e9; }
QFrame#celda { border: 1px solid palette(midlight); border-radius: 8px; background: palette(base); }
QFrame#celda:hover { border-color: #1565c0; }
QLabel#leyenda { font-size: 11px; }
QLabel#ayuda { color: palette(mid); font-size: 14px; }
QPushButton#aplicar { background: #2e7d32; color: white; border-radius: 4px; padding: 6px 14px; }
QPushButton#aplicar:hover { background: #43a047; }
QToolButton#buscar { background: #1565c0; color: white; border-radius: 4px; padding: 5px 12px; }
QToolButton#buscar:hover { background: #1e88e5; }
QToolButton#buscar::menu-indicator { image: none; }
QPushButton#eliminar { background: #f4a6a6; color: black; border: 1px solid #d77a7a; border-radius: 4px;
                       padding: 6px 14px; }
QPushButton#eliminar:hover { background: #ef8f8f; }
QPushButton#eliminar:disabled { background: #eeeeee; color: #9e9e9e; border-color: #cccccc; }
QToolButton#favorito { border: 1px solid palette(mid); border-radius: 4px; padding: 4px 10px; font-size: 13px; }
QToolButton#favorito:checked { background: #e8f5e9; border-color: #43a047; color: #1b5e20; }
QToolButton#favorito:hover { border-color: #43a047; }
QLabel#estado { padding: 8px 6px; }
QTabWidget::pane { border: 1px solid #cfd8dc; border-radius: 12px; background: palette(base); top: -1px; }
QTabBar::tab { background: #eceff1; color: #37474f; border: 1px solid #cfd8dc; padding: 7px 16px;
               margin-right: 4px; border-top-left-radius: 10px; border-top-right-radius: 10px; }
QTabBar::tab:selected { background: palette(base); color: #0d47a1; font-weight: bold;
                        border-bottom-color: palette(base); }
QTabBar::tab:hover:!selected { background: #e3f2fd; }
QTreeWidget { border: none; background: transparent; outline: 0; padding: 6px 4px; show-decoration-selected: 0; }
QTreeWidget::item { padding: 3px 4px; border-radius: 6px; }
QTreeWidget::item:hover { background: #e3f2fd; }
QTreeWidget::item:selected { background: #1565c0; color: white; }
QTreeView::branch:selected, QTreeView::branch:hover { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #b0bec5; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:horizontal { background: #b0bec5; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:hover { background: #78909c; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QToolButton#descartar { background: #f4a6a6; color: black; border: 1px solid #d77a7a; border-radius: 4px;
                        padding: 5px 10px; }
QToolButton#descartar::menu-indicator { image: none; }
QPushButton#aplicar:disabled { background: #9e9e9e; color: #eeeeee; }
"""


class _Señales(QObject):
    progreso = Signal(int, int)
    listo = Signal(object)
    error = Signal(str)


class ZonaArrastre(QFrame):
    soltado = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("zona")
        self.setAcceptDrops(True)

    def _activa(self, si: bool) -> None:
        self.setProperty("activa", si)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()
            self._activa(True)

    def dragLeaveEvent(self, e) -> None:
        self._activa(False)

    def dropEvent(self, e) -> None:
        self._activa(False)
        md = e.mimeData()
        if md.hasUrls():
            elementos = [u.toLocalFile() if u.isLocalFile() else u.toString() for u in md.urls()]
        else:
            elementos = [t.strip() for t in md.text().splitlines() if t.strip()]
        if elementos:
            e.acceptProposedAction()
            self.soltado.emit(elementos)


def mostrar_en_carpeta(ruta: Path) -> None:
    """Abre la carpeta que contiene `ruta` y la deja seleccionada (Archivos/Nautilus, Dolphin, Nemo, Caja…).
    Si el administrador de archivos no lo permite, abre la carpeta sin seleccionar."""
    import subprocess

    if shutil.which("gdbus"):
        try:
            r = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1",
                                "--object-path", "/org/freedesktop/FileManager1",
                                "--method", "org.freedesktop.FileManager1.ShowItems", f"['{ruta.as_uri()}']", ""],
                               capture_output=True, timeout=10, env=entorno_sistema())
            if r.returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            pass
    abrir_externo(ruta.parent.as_uri())


class DialogoArchivos(QDialog):
    """Lista de archivos de una página con casillas: se pueden descargar todos de una vez."""

    def __init__(self, lista: list[archivos.ArchivoRemoto], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Elegir archivos para descargar")
        self.resize(560, 420)
        self.lista_archivos = lista
        explicacion = QLabel("La página tiene varios archivos. Marque los que quiere revisar: se descargan todos y "
                             "aparecen juntos en «Nuevos» para compararlos.\nLos de Windows no sirven en Linux.")
        explicacion.setWordWrap(True)
        self.casillas = QListWidget()
        for a in lista:
            item = QListWidgetItem(a.texto + ("   (para Windows)" if a.parece_windows else ""))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if (archivos.es_util(a.nombre) and not a.parece_windows)
                               else Qt.Unchecked)
            if a.parece_windows:
                item.setForeground(QColor("#9e9e9e"))
            self.casillas.addItem(item)
        self.casillas.itemChanged.connect(lambda _i: self._contar())
        self.casillas.itemClicked.connect(lambda i: None)
        b_todos = QPushButton("Marcar todos los de Linux")
        b_todos.clicked.connect(lambda: self._marcar(True))
        b_ninguno = QPushButton("Ninguno")
        b_ninguno.clicked.connect(lambda: self._marcar(False))
        self.botones = QDialogButtonBox()
        self.b_ok = self.botones.addButton("Descargar", QDialogButtonBox.AcceptRole)
        self.b_ok.setObjectName("aplicar")
        self.botones.addButton("Cancelar", QDialogButtonBox.RejectRole)
        self.botones.accepted.connect(self.accept)
        self.botones.rejected.connect(self.reject)
        fila = QHBoxLayout()
        fila.addWidget(b_todos)
        fila.addWidget(b_ninguno)
        fila.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addWidget(explicacion)
        lay.addWidget(self.casillas, 1)
        lay.addLayout(fila)
        lay.addWidget(self.botones)
        self._contar()

    def _marcar(self, si: bool) -> None:
        for i, a in enumerate(self.lista_archivos):
            linux = archivos.es_util(a.nombre) and not a.parece_windows
            self.casillas.item(i).setCheckState(Qt.Checked if (si and linux) else Qt.Unchecked)

    def _contar(self) -> None:
        n = len(self.elegidos())
        self.b_ok.setText(f"Descargar {n} archivo(s)" if n != 1 else "Descargar 1 archivo")
        self.b_ok.setEnabled(n > 0)

    def elegidos(self) -> list[archivos.ArchivoRemoto]:
        return [a for i, a in enumerate(self.lista_archivos) if self.casillas.item(i).checkState() == Qt.Checked]


class VentanaPrincipal(QMainWindow):
    def __init__(self, escritorio: Escritorio | None = None):
        super().__init__()
        self.escritorio = escritorio or Escritorio()
        self.trabajo = Path(tempfile.mkdtemp(prefix="temasapp-"))
        self.paquete: list[Tema] = []
        self.marcados: set[str] = set()     # ids de los temas nuevos marcados con la casilla
        self.ocupado = False
        self.setWindowTitle("Estilo Ágil")
        self.resize(1100, 760)
        self.setStyleSheet(ESTILO)
        self.setAcceptDrops(True)

        # --- zona de arrastre y enlace ---
        self.zona = ZonaArrastre()
        self.zona.soltado.connect(self.recibir)
        titulo = QLabel("<span style='font-size:16px'><b>Arrastre aquí el tema o la imagen</b></span><br>"
                        "<span>.zip / .tar.xz de cursores o iconos, o imágenes .jpg / .png para fondo de pantalla — "
                        "o pegue el enlace de la página (gnome-look.org, pling.com, GitHub) o de la descarga</span>")
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setWordWrap(True)
        self.enlace = QLineEdit()
        self.enlace.setPlaceholderText("https://www.gnome-look.org/p/…   o   enlace directo al .zip / .tar.xz")
        self.enlace.setClearButtonEnabled(True)
        self.enlace.returnPressed.connect(self.descargar_enlace)
        self.b_descargar = QPushButton("Descargar y ver")
        self.b_descargar.clicked.connect(self.descargar_enlace)
        self.b_abrir = QPushButton("Abrir archivo…")
        self.b_abrir.clicked.connect(self.abrir_archivo)
        self.b_buscar = QToolButton()
        self.b_buscar.setText("Buscar temas en internet  ▾")
        self.b_buscar.setObjectName("buscar")
        self.b_buscar.setPopupMode(QToolButton.InstantPopup)
        self.b_buscar.setMenu(self._menu_sitios())
        self.navegador = None
        fila = QHBoxLayout()
        fila.addWidget(self.b_buscar)
        fila.addWidget(self.enlace, 1)
        fila.addWidget(self.b_descargar)
        fila.addWidget(self.b_abrir)
        lz = QVBoxLayout(self.zona)
        lz.setContentsMargins(16, 14, 16, 14)
        lz.addWidget(titulo)
        lz.addLayout(fila)

        # --- listas: una pestaña para cursores y otra para iconos ---
        self.listas = {"cursores": QTreeWidget(), "iconos": QTreeWidget(), "fondos": QTreeWidget()}
        self.pestanas = QTabWidget()
        for tipo, titulo in (("cursores", "Cursores"), ("iconos", "Iconos"), ("fondos", "Fondos")):
            lista = self.listas[tipo]
            lista.setHeaderHidden(True)
            lista.setIndentation(16)
            lista.setAnimated(True)
            lista.setSelectionMode(QAbstractItemView.SingleSelection)
            lista.currentItemChanged.connect(lambda actual, _ant, l=lista: self._item_cambiado(l, actual))
            lista.itemChanged.connect(self._marca_cambiada)
            lista.setEditTriggers(QAbstractItemView.NoEditTriggers)   # solo se edita al renombrar
            lista.itemDoubleClicked.connect(lambda item, _c, l=lista: self._doble_clic(l, item))
            lista.itemDelegate().closeEditor.connect(lambda *_a, l=lista: QTimer.singleShot(0, self._fin_renombrar))
            lista.setContextMenuPolicy(Qt.CustomContextMenu)
            lista.customContextMenuRequested.connect(lambda pos, l=lista: self._menu_lista(l, pos))
            self.pestanas.addTab(lista, titulo)
        atajo = QShortcut(QKeySequence.Delete, self.pestanas)
        atajo.activated.connect(self.eliminar)
        self.renombrando = None      # (lista, elemento, tema) mientras se edita un nombre
        self.c_renombrar = Interruptor("Renombrar con doble clic")
        self.c_renombrar.setToolTip("Actívelo para cambiar el nombre de un tema o fondo con doble clic.\n"
                                    "Solo los que agregó usted (los del sistema no se pueden renombrar).")
        self.c_ocultos = QCheckBox("Mostrar los ocultos")
        self.c_ocultos.setToolTip("Muestra también los temas del sistema que ocultó")
        self.c_ocultos.toggled.connect(lambda _s: (self.actualizar_listas(), self._cambio_pestana()))
        # botones para los temas nuevos marcados con casilla
        self.b_instalar_marcados = QPushButton("Agregar marcados a mi equipo")
        self.b_instalar_marcados.setObjectName("aplicar")
        self.b_instalar_marcados.setToolTip("Instala los temas marcados (sin aplicarlos): pasan a «Instalados por "
                                            "usted»")
        self.b_instalar_marcados.clicked.connect(self.instalar_marcados)
        self.b_descartar = QToolButton()
        self.b_descartar.setText("Descartar  ▾")
        self.b_descartar.setObjectName("descartar")
        self.b_descartar.setPopupMode(QToolButton.InstantPopup)
        menu_descartar = QMenu(self.b_descartar)
        self.a_descartar_marcados = menu_descartar.addAction("Los marcados", lambda: self.descartar("marcados"))
        self.a_descartar_resto = menu_descartar.addAction("Los NO marcados (me quedo con los marcados)",
                                                          lambda: self.descartar("resto"))
        menu_descartar.addAction("Todos los nuevos", lambda: self.descartar("todos"))
        self.b_descartar.setMenu(menu_descartar)
        self.barra_nuevos = QWidget()
        bn = QHBoxLayout(self.barra_nuevos)
        bn.setContentsMargins(0, 2, 0, 2)
        bn.addWidget(self.b_instalar_marcados, 1)
        bn.addWidget(self.b_descartar)
        self.pestanas.currentChanged.connect(lambda _i: self._cambio_pestana())
        self.pestanas.setMinimumWidth(270)

        # --- vista previa y acciones ---
        self.lbl_tema = QLabel()
        self.b_favorito = QToolButton()
        self.b_favorito.setObjectName("favorito")
        self.b_favorito.setCheckable(True)
        self.b_favorito.clicked.connect(self.cambiar_favorito)
        self.lbl_tema.setWordWrap(True)
        self.vista = PanelVista()
        self.c_tamano = QComboBox()
        self.c_tamano.setToolTip("Tamaño del cursor en pantalla")
        self.c_tamano.currentIndexChanged.connect(self._tamano_cambiado)
        self.b_aplicar = QPushButton("Aplicar")
        self.b_aplicar.setObjectName("aplicar")
        self.b_aplicar.clicked.connect(self.aplicar)
        self.b_carpeta = QToolButton()
        self.b_carpeta.setText("📂 Abrir carpeta contenedora")
        self.b_carpeta.setObjectName("favorito")
        self.b_carpeta.clicked.connect(self.abrir_carpeta)
        self.b_eliminar = QPushButton("Eliminar")
        self.b_eliminar.setObjectName("eliminar")
        self.b_eliminar.clicked.connect(self.eliminar)
        self.b_original = QPushButton("Volver a los originales")
        self.b_original.setToolTip("Restaura el cursor y los iconos que tenía antes de usar este programa")
        self.b_original.clicked.connect(self.restaurar)
        acciones = QHBoxLayout()
        self.lbl_tamano = QLabel("Tamaño del cursor:")
        acciones.addWidget(self.lbl_tamano)
        acciones.addWidget(self.c_tamano)
        self.b_tamano = QPushButton("Usar este tamaño")
        self.b_tamano.setToolTip("Cambia solo el tamaño del cursor que está usando ahora, sin cambiar el tema")
        self.b_tamano.clicked.connect(self.aplicar_tamano)
        acciones.addWidget(self.b_tamano)
        self.lbl_ajuste = QLabel("Ajuste:")
        self.c_ajuste = QComboBox()
        for codigo, texto in AJUSTES:
            self.c_ajuste.addItem(texto, codigo)
        self.c_bloqueo = QCheckBox("También en la pantalla de bloqueo")
        self.c_bloqueo.setChecked(True)
        self.c_oscuro = QCheckBox("Fondo oscuro")
        self.c_oscuro.setToolTip("Para ver mejor los cursores e iconos claros")
        self.c_oscuro.toggled.connect(self.vista.poner_oscuro)
        acciones.addWidget(self.lbl_ajuste)
        acciones.addWidget(self.c_ajuste)
        acciones.addWidget(self.c_oscuro)
        acciones.addStretch(1)
        # segunda fila: botones (así la ventana cabe en pantallas más chicas)
        botones = QHBoxLayout()
        botones.addWidget(self.b_aplicar)
        botones.addWidget(self.c_bloqueo)
        botones.addStretch(1)
        botones.addWidget(self.b_eliminar)
        botones.addWidget(self.b_original)
        derecha = QWidget()
        ld = QVBoxLayout(derecha)
        ld.setContentsMargins(8, 0, 0, 0)
        fila_titulo = QHBoxLayout()
        fila_titulo.addWidget(self.lbl_tema, 1)
        fila_titulo.addWidget(self.b_carpeta, 0, Qt.AlignTop)
        fila_titulo.addWidget(self.b_favorito, 0, Qt.AlignTop)
        ld.addLayout(fila_titulo)
        ld.addWidget(self.vista, 1)
        ld.addLayout(acciones)
        ld.addLayout(botones)

        division = QSplitter()
        izquierda = QWidget()
        li = QVBoxLayout(izquierda)
        li.setContentsMargins(0, 0, 0, 0)
        li.addWidget(self.pestanas, 1)
        li.addWidget(self.barra_nuevos)
        li.addWidget(self.c_renombrar)
        li.addWidget(self.c_ocultos)
        division.addWidget(izquierda)
        division.addWidget(derecha)
        division.setStretchFactor(1, 1)
        division.setSizes([340, 800])

        self.lbl_actual = QLabel()
        self.lbl_actual.setObjectName("estado")
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(self.zona)
        lay.addWidget(self.lbl_actual)
        lay.addWidget(division, 1)
        self.setCentralWidget(central)

        self.barra = QProgressBar()
        self.barra.setMaximumWidth(220)
        self.barra.hide()
        self.statusBar().addPermanentWidget(self.barra)

        self._llenar_tamanos()
        self.actualizar_listas()
        self._actualizar_actual()
        self._cambio_pestana()

    # --- páginas de temas ---------------------------------------------------------
    def _menu_sitios(self) -> QMenu:
        from .navegador import SITIOS, hay_navegador_integrado

        menu = QMenu(self)
        integrado = hay_navegador_integrado()
        for seccion, sitios in SITIOS:
            menu.addSection(seccion)
            for texto, url in sitios:
                if integrado:
                    menu.addAction(texto, lambda u=url: self.abrir_pagina(u))
                else:
                    menu.addAction(texto, lambda u=url: abrir_externo(u))
        if integrado:
            menu.addSeparator()
            externo = menu.addMenu("Abrir en mi navegador")
            for seccion, sitios in SITIOS:
                externo.addSection(seccion)
                for texto, url in sitios:
                    externo.addAction(texto, lambda u=url: abrir_externo(u))
        return menu

    def abrir_pagina(self, url: str) -> None:
        from .navegador import Navegador

        if self.navegador is None:
            self.navegador = Navegador(self, url)
        else:
            self.navegador.ir(url)
        self.navegador.show()
        self.navegador.raise_()
        self.navegador.activateWindow()

    # --- utilidades de interfaz ---------------------------------------------------
    def tipo_actual(self) -> str:
        return TIPOS[max(0, self.pestanas.currentIndex())]

    def _lista_actual(self) -> QTreeWidget:
        return self.listas[self.tipo_actual()]

    def elegido(self) -> tuple[Tema | None, bool]:
        """(tema, es_nuevo): es_nuevo = viene del archivo agregado y todavía no está instalado."""
        item = self._lista_actual().currentItem()
        dato = item.data(0, Qt.UserRole) if item is not None else None
        return dato if isinstance(dato, tuple) else (None, False)

    @staticmethod
    def items_de_temas(lista: QTreeWidget) -> list[QTreeWidgetItem]:
        """Los elementos que son temas, en el orden en que se ven (también los de grupos cerrados)."""
        resultado = []

        def recorrer(item):
            for i in range(item.childCount()):
                hijo = item.child(i)
                if isinstance(hijo.data(0, Qt.UserRole), tuple):
                    resultado.append(hijo)
                recorrer(hijo)

        recorrer(lista.invisibleRootItem())
        return resultado

    def ids_en_lista(self, tipo: str | None = None) -> list[str]:
        return [i.data(0, Qt.UserRole)[0].id for i in self.items_de_temas(self.listas[tipo or self.tipo_actual()])]

    @staticmethod
    def seccion_de(item) -> str:
        """Título de la sección a la que pertenece un elemento (p. ej. «★ FAVORITOS»)."""
        while item is not None and item.parent() is not None:
            item = item.parent()
        return item.text(0).split("  (")[0] if item is not None else ""

    def elegir_tema(self, id_: str, nuevo: bool | None = None, seccion: str | None = None) -> bool:
        """Elige el tema; si aparece en varias secciones (favoritos y su sección), prefiere `seccion`."""
        lista = self._lista_actual()
        candidatos = [i for i in self.items_de_temas(lista)
                      if i.data(0, Qt.UserRole)[0].id == id_ and (nuevo is None or nuevo == i.data(0, Qt.UserRole)[1])]
        if seccion:
            candidatos.sort(key=lambda i: self.seccion_de(i) != seccion)
        if not candidatos:
            return False
        item = candidatos[0]
        p = item.parent()
        while p is not None:      # abrir el grupo donde está, para que se vea
            p.setExpanded(True)
            p = p.parent()
        lista.setCurrentItem(item)
        lista.scrollToItem(item)
        return True

    def tema_elegido(self) -> Tema | None:
        return self.elegido()[0]

    def _llenar_tamanos(self) -> None:
        actual = self.escritorio.actual().tamano
        valores = sorted(set(TAMANOS + [actual]))
        self.c_tamano.blockSignals(True)
        self.c_tamano.clear()
        for v in valores:
            self.c_tamano.addItem(f"{v} px" + ("  (actual)" if v == actual else ""), v)
        self.c_tamano.setCurrentIndex(valores.index(actual))
        self.c_tamano.blockSignals(False)

    def _actualizar_actual(self) -> None:
        a = self.escritorio.actual()
        self.lbl_actual.setText(f"Escritorio: <b>{NOMBRES_ENTORNO.get(self.escritorio.entorno)}</b>  ·  "
                                f"Cursor actual: <b>{a.cursor or '—'}</b> ({a.tamano} px)  ·  "
                                f"Iconos actuales: <b>{a.iconos or '—'}</b>  ·  "
                                f"Fondo: <b>{Path(a.fondo).name if a.fondo else '—'}</b>")
        self.b_original.setEnabled(bool(self.escritorio.anterior()))

    @staticmethod
    def _seccion(lista: QTreeWidget, texto: str, color: str = "#1565c0") -> QTreeWidgetItem:
        item = QTreeWidgetItem(lista, [texto])
        item.setFlags(Qt.ItemIsEnabled)
        fuente = item.font(0)
        fuente.setBold(True)
        item.setFont(0, fuente)
        item.setForeground(0, QColor(color))
        item.setData(0, Qt.UserRole, "seccion")
        item.setExpanded(True)
        return item

    def actualizar_listas(self, elegir: str | None = None) -> None:
        """Llena las dos pestañas por secciones (Nuevos, Favoritos, Instalados por usted, Del sistema);
        las variantes de un mismo tema quedan juntas en un grupo con flecha."""
        a = self.escritorio.actual()
        instalados = temas_instalados()
        instalados_fondos = mod_fondos.fondos_instalados()
        escondidos = ocultos()
        preferidos = favoritos()
        n_ocultos = 0
        for tipo, lista in self.listas.items():
            de_tipo = (lambda t, tipo=tipo: _de_tipo(t, tipo))
            en_uso = {"cursores": a.cursor, "iconos": a.iconos, "fondos": a.fondo}[tipo]
            orden_fav = {id_: i for i, id_ in enumerate(preferidos[tipo])}
            lista.blockSignals(True)
            lista.clear()
            a_elegir = None

            visibles = []
            for t in (instalados_fondos if tipo == "fondos" else [t for t in instalados if de_tipo(t)]):
                oculto = t.id in escondidos[tipo]
                if oculto:
                    n_ocultos += 1
                    if not self.c_ocultos.isChecked() and t.id != en_uso:
                        continue
                visibles.append(t)
            secciones = [
                ("NUEVOS — del archivo que agregó", [t for t in self.paquete if de_tipo(t)], True, "#e65100"),
                ("★ FAVORITOS", sorted((t for t in visibles if t.id in orden_fav), key=lambda t: orden_fav[t.id]),
                 False, "#2e7d32"),
                ("INSTALADOS POR USTED", [t for t in visibles if _del_usuario(t)],
                 False, "#1565c0"),
                ("DEL SISTEMA", [t for t in visibles if not _del_usuario(t)],
                 False, "#616161"),
            ]
            for titulo, temas, nuevos, color in secciones:
                if not temas:
                    continue
                seccion = self._seccion(lista, f"{titulo}  ({len(temas)})", color)
                if nuevos:   # casilla en la sección: marca o desmarca todos los nuevos
                    seccion.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                    seccion.setToolTip(0, "Marque los que le gustan y pulse «Agregar marcados a mi equipo»")
                for familia, miembros in (mod_fondos.agrupar(temas) if tipo == "fondos" else agrupar(temas)):
                    padre = seccion
                    if familia:
                        padre = QTreeWidgetItem(seccion)
                        marcas = ""
                        if any(t.id == en_uso for t in miembros) and not nuevos:
                            marcas = "   ✔ en uso"
                        padre.setText(0, f"{familia}  ({len(miembros)} variantes){marcas}")
                        padre.setData(0, Qt.UserRole, "grupo")
                        padre.setToolTip(0, "Pulse la flecha para ver las variantes")
                        padre.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable |
                                       ((Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate) if nuevos else Qt.NoItemFlags))
                        if marcas:
                            fuente = padre.font(0)
                            fuente.setBold(True)
                            padre.setFont(0, fuente)
                    for t in miembros:
                        item = self._item_tema(padre, t, nuevos, en_uso, orden_fav, escondidos[tipo], self.marcados)
                        if a_elegir is None and (
                                (elegir == "nuevo" and nuevos) or
                                (not nuevos and t.id == (elegir if elegir not in (None, "nuevo") else en_uso))):
                            a_elegir = item
                    if familia and (nuevos or len(temas) == len(miembros)):
                        padre.setExpanded(True)   # si la sección es una sola familia, se ve abierta
            lista.blockSignals(False)
            if a_elegir is None:
                items = self.items_de_temas(lista)
                a_elegir = items[0] if items else None
            if a_elegir is not None:
                p = a_elegir.parent()
                while p is not None:
                    p.setExpanded(True)
                    p = p.parent()
                lista.setCurrentItem(a_elegir)
                lista.scrollToItem(a_elegir)
        self.c_ocultos.setText(f"Mostrar los ocultos ({n_ocultos})" if n_ocultos else "Mostrar los ocultos")
        self.c_ocultos.setVisible(bool(n_ocultos) or self.c_ocultos.isChecked())
        self.marcados &= {t.id for t in self.paquete}
        self._actualizar_barra_nuevos()

    @staticmethod
    def _item_tema(padre, t: Tema, nuevo: bool, en_uso: str, orden_fav: dict, escondidos: list,
                   marcados: set | frozenset = frozenset()) -> QTreeWidgetItem:
        marcas = []
        if nuevo:
            marcas.append("sin instalar")
        if t.id in escondidos:
            marcas.append("oculto")
        if not nuevo and t.id == en_uso:
            marcas.append("✔ en uso")
        estrella = "★ " if (not nuevo and t.id in orden_fav) else ""
        item = QTreeWidgetItem(padre, [estrella + t.titulo + (f"   · {' · '.join(marcas)}" if marcas else "")])
        item.setData(0, Qt.UserRole, (t, nuevo))
        if nuevo:
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked if t.id in marcados else Qt.Unchecked)
        item.setToolTip(0, str(t.carpeta) if not nuevo else f"{t.id} — pulse «Aplicar» para instalarlo y usarlo")
        if estrella:
            item.setForeground(0, QColor("#2e7d32"))
        if not nuevo and t.id == en_uso:
            fuente = item.font(0)
            fuente.setBold(True)
            item.setFont(0, fuente)
        return item

    def _item_cambiado(self, lista: QTreeWidget, item) -> None:
        dato = item.data(0, Qt.UserRole) if item is not None else None
        if dato == "grupo" and item.childCount():
            # al elegir un grupo se abre y se muestra su primera variante (o la que está en uso)
            item.setExpanded(True)
            hijo = next((item.child(i) for i in range(item.childCount())
                         if item.child(i).font(0).bold()), item.child(0))
            QTimer.singleShot(0, lambda: lista.setCurrentItem(hijo))
            return
        self._elegido(lista)

    # --- temas nuevos marcados ---------------------------------------------------------
    # --- renombrar ---------------------------------------------------------------------
    def _doble_clic(self, lista: QTreeWidget, item) -> None:
        dato = item.data(0, Qt.UserRole)
        if not self.c_renombrar.isChecked() or not isinstance(dato, tuple):
            return
        tema, nuevo = dato
        if nuevo or not _del_usuario(tema):
            self.statusBar().showMessage("Solo se pueden renombrar los temas y fondos que agregó usted "
                                         "(no los nuevos sin instalar ni los del sistema).", 8000)
            return
        self.renombrando = (lista, item, tema)
        lista.blockSignals(True)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        item.setText(0, tema.titulo)        # sin estrella ni marcas mientras se escribe
        lista.blockSignals(False)
        lista.editItem(item, 0)

    def _fin_renombrar(self) -> None:
        if self.renombrando is None:
            return
        lista, item, tema = self.renombrando
        self.renombrando = None
        nombre = " ".join(item.text(0).split())
        tipo = self.tipo_actual()
        nuevo_id = tema.id
        if nombre and nombre != tema.titulo:
            try:
                if isinstance(tema, Fondo):
                    nuevo = mod_fondos.renombrar(tema, nombre)
                    nuevo_id = nuevo.id
                    self.escritorio.fondo_movido(tema.id, nuevo_id)
                    renombrar_clave("fondos", tema.id, nuevo_id)
                else:
                    renombrar_tema(tema, nombre)
                self.statusBar().showMessage(f"«{tema.titulo}» ahora se llama «{nombre}».", 8000)
            except Exception as e:  # noqa: BLE001 - se muestra al usuario
                QMessageBox.warning(self, "No se pudo renombrar", str(e))
        seccion = self.seccion_de(item)
        self.actualizar_listas(elegir=nuevo_id)
        self.elegir_tema(nuevo_id, False, seccion)
        self._actualizar_actual()
        self._cambio_pestana()

    def _marca_cambiada(self, item, _col=0) -> None:
        if self.renombrando is not None:
            return
        dato = item.data(0, Qt.UserRole)
        if not (isinstance(dato, tuple) and dato[1]):
            return
        if item.checkState(0) == Qt.Checked:
            self.marcados.add(dato[0].id)
        else:
            self.marcados.discard(dato[0].id)
        # el mismo tema puede estar en las dos pestañas (si trae cursores e iconos): igualar la otra
        for otra in self.listas.values():
            if otra is item.treeWidget():
                continue
            for i in self.items_de_temas(otra):
                d = i.data(0, Qt.UserRole)
                if d[1] and d[0].id == dato[0].id and i.checkState(0) != item.checkState(0):
                    otra.blockSignals(True)
                    i.setCheckState(0, item.checkState(0))
                    otra.blockSignals(False)
        self._actualizar_barra_nuevos()

    def _actualizar_barra_nuevos(self) -> None:
        tipo = self.tipo_actual()
        de_tipo = [t for t in self.paquete if _de_tipo(t, tipo)]
        n = len(self.marcados & {t.id for t in self.paquete})
        self.barra_nuevos.setVisible(bool(de_tipo))
        self.b_instalar_marcados.setText(f"Agregar marcados ({n})" if n else "Marque los que le gustan")
        self.b_instalar_marcados.setEnabled(n > 0)
        self.a_descartar_marcados.setEnabled(n > 0)
        self.a_descartar_resto.setEnabled(n > 0)

    def instalar_marcados(self) -> None:
        elegidos = [t for t in self.paquete if t.id in self.marcados]
        if not elegidos:
            return
        ya = [t for t in elegidos if _instalado_igual(t)]
        reemplazar = False
        if ya:
            r = QMessageBox.question(self, "Ya instalados",
                                     f"{len(ya)} de los marcados ya están en su equipo ("
                                     f"{', '.join(t.id for t in ya[:4])}{'…' if len(ya) > 4 else ''}).\n\n"
                                     "¿Reemplazarlos por los nuevos?", QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.Yes)
            reemplazar = r == QMessageBox.Yes
        hechos, errores = [], []
        for t in elegidos:
            try:
                _instalar(t, reemplazar=reemplazar)
                hechos.append(t)
            except FileExistsError:
                hechos.append(t)          # ya estaba y eligió no reemplazarlo
            except Exception as e:  # noqa: BLE001 - se informa al final
                errores.append(f"{t.titulo}: {e}")
        listos = {t.id for t in hechos}
        self.paquete = [t for t in self.paquete if t.id not in listos]
        self.marcados -= listos
        self.actualizar_listas(elegir=hechos[0].id if hechos else None)
        self._cambio_pestana()
        self.statusBar().showMessage(f"{len(hechos)} tema(s) agregados a su equipo: están en «Instalados por usted». "
                                     "Elija uno y pulse «Aplicar» para usarlo.", 12000)
        if errores:
            QMessageBox.warning(self, "Algunos no se pudieron agregar", "\n".join(errores))

    def descartar(self, cuales: str) -> None:
        """Quita temas de «Nuevos» (no estaban instalados: no se borra nada del equipo)."""
        antes = len(self.paquete)
        if cuales == "marcados":
            self.paquete = [t for t in self.paquete if t.id not in self.marcados]
        elif cuales == "resto":
            self.paquete = [t for t in self.paquete if t.id in self.marcados]
        else:
            self.paquete = []
        self.marcados &= {t.id for t in self.paquete}
        self.actualizar_listas(elegir="nuevo" if self.paquete else None)
        self._cambio_pestana()
        self.statusBar().showMessage(f"{antes - len(self.paquete)} tema(s) descartados de «Nuevos».", 8000)

    def _cambio_pestana(self) -> None:
        es_cursor = self.tipo_actual() == "cursores"
        self._actualizar_barra_nuevos()
        es_fondo = self.tipo_actual() == "fondos"
        self.lbl_tamano.setVisible(es_cursor)
        self.c_tamano.setVisible(es_cursor)
        self.b_tamano.setVisible(es_cursor)
        self._estado_b_tamano()
        for w in (self.lbl_ajuste, self.c_ajuste):
            w.setVisible(es_fondo)
        self.c_bloqueo.setVisible(es_fondo and self.escritorio.entorno in ("gnome", "otro"))
        self.c_oscuro.setVisible(not es_fondo)
        self._elegido(self._lista_actual())

    def _elegido(self, lista: QTreeWidget) -> None:
        if lista is not self._lista_actual():
            return
        tema, nuevo = self.elegido()
        tipo = self.tipo_actual()
        self.vista.mostrar(tema, self.c_tamano.currentData(), solo=tipo)
        if tema is None:
            self.lbl_tema.setText("")
        else:
            extra = f"<br><i>{tema.comentario}</i>" if tema.comentario else ""
            estado = "nuevo, sin instalar" if nuevo else ("instalado" if _del_usuario(tema) else "del sistema")
            self.lbl_tema.setText(f"<span style='font-size:15px'><b>{tema.titulo}</b></span>  "
                                  f"<small>({estado})</small>{extra}")
        self.b_aplicar.setText({"cursores": "Aplicar este cursor", "iconos": "Aplicar estos iconos",
                                "fondos": "Poner de fondo de pantalla"}[tipo])
        self.b_aplicar.setEnabled(tema is not None)
        es_fav = bool(tema and not nuevo and tema.id in favoritos()[tipo])
        self.b_favorito.setVisible(tema is not None)
        self.b_favorito.setChecked(es_fav)
        self.b_favorito.setText("★ En favoritos" if es_fav else "☆ Agregar a favoritos")
        self.b_favorito.setToolTip("Quitar de favoritos" if es_fav else
                                   ("Lo instala (sin aplicarlo) y lo guarda en favoritos" if nuevo else
                                    "Lo pone arriba de la lista, en Favoritos"))
        accion = self._accion_borrar(tema, nuevo)
        self.b_eliminar.setText(accion[0] if accion else "Eliminar")
        self.b_eliminar.setToolTip(accion[1] if accion else "")
        self.b_eliminar.setEnabled(accion is not None)
        self.b_carpeta.setEnabled(bool(tema and not nuevo))
        if tema is not None and nuevo:
            self.b_carpeta.setToolTip("Todavía no está guardado en su equipo: agréguelo o aplíquelo primero")
        elif tema is not None:
            self.b_carpeta.setToolTip(f"Abre la carpeta donde está guardado y lo deja señalado:\n{tema.carpeta}\n\n"
                                      "Desde ahí puede copiarlo para llevarlo a otro equipo.")

    def _accion_borrar(self, tema: Tema | None, nuevo: bool) -> tuple[str, str] | None:
        """Qué hace el botón rojo con este tema: (texto, explicación), o None si no aplica."""
        if tema is None:
            return None
        if nuevo:
            return "Quitar de la lista", "No está instalado: solo se quita de «Nuevos»"
        if _del_usuario(tema):
            return "Eliminar", "Lo manda a la papelera (se puede recuperar desde ahí)"
        if tema.id in ocultos()[self.tipo_actual()]:
            return "Volver a mostrar", "Lo vuelve a mostrar en la lista"
        return "Ocultar", ("Vino con el sistema: no se borra (lo necesitan otros programas y volvería con las "
                           "actualizaciones), solo se oculta de esta lista")

    def _menu_lista(self, lista: QTreeWidget, pos) -> None:
        item = lista.itemAt(pos)
        if item is None or not isinstance(item.data(0, Qt.UserRole), tuple):
            return
        lista.setCurrentItem(item)
        tema, nuevo = self.elegido()
        menu = QMenu(self)
        menu.addAction(self.b_aplicar.text(), self.aplicar)
        es_fav = not nuevo and tema.id in favoritos()[self.tipo_actual()]
        menu.addAction("Quitar de favoritos" if es_fav else "★ Agregar a favoritos", self.cambiar_favorito)
        accion = self._accion_borrar(tema, nuevo)
        if accion:
            menu.addAction(accion[0] + ("…" if accion[0] == "Eliminar" else ""), self.eliminar)
        if not nuevo:
            menu.addSeparator()
            menu.addAction("📂 Abrir carpeta contenedora", self.abrir_carpeta)
        menu.exec(lista.viewport().mapToGlobal(pos))

    def abrir_carpeta(self) -> None:
        """Abre el administrador de archivos en la carpeta que contiene el tema o fondo, con él señalado."""
        tema, nuevo = self.elegido()
        if tema is None or nuevo:
            return
        mostrar_en_carpeta(Path(tema.carpeta))
        self.statusBar().showMessage(f"Guardado en: {Path(tema.carpeta).parent}", 10000)

    def _tamano_cambiado(self) -> None:
        self._estado_b_tamano()
        if self.vista.tema is not None:
            self.vista.mostrar(self.vista.tema, self.c_tamano.currentData())

    def _estado_b_tamano(self) -> None:
        if hasattr(self, "b_tamano"):
            self.b_tamano.setEnabled(self.c_tamano.currentData() != self.escritorio.actual().tamano)

    def aplicar_tamano(self) -> None:
        tam = self.c_tamano.currentData()
        try:
            self.escritorio.aplicar_tamano(tam)
        except Exception as e:  # noqa: BLE001 - se muestra al usuario
            QMessageBox.critical(self, "No se pudo cambiar el tamaño", str(e))
            return
        self._llenar_tamanos()
        self._actualizar_actual()
        self._estado_b_tamano()
        self.statusBar().showMessage(f"Tamaño del cursor cambiado a {tam} px. Algunas aplicaciones abiertas lo "
                                     "toman al volver a abrirlas.", 10000)

    def _ocupado(self, si: bool, texto: str = "") -> None:
        self.ocupado = si
        for b in (self.b_descargar, self.b_abrir, self.enlace):
            b.setEnabled(not si)
        self.barra.setVisible(si)
        self.barra.setRange(0, 0)
        if texto:
            self.statusBar().showMessage(texto)

    # --- entrada de paquetes ---------------------------------------------------
    def dragEnterEvent(self, e) -> None:
        self.zona.dragEnterEvent(e)

    def dropEvent(self, e) -> None:
        self.zona.dropEvent(e)

    def recibir(self, elementos: list[str]) -> None:
        primero = elementos[0]
        if primero.startswith(("http://", "https://")):
            self.enlace.setText(primero)
            self.descargar_enlace()
        else:
            self.cargar_varios([Path(e) for e in elementos if not e.startswith(("http://", "https://"))])

    def abrir_archivo(self) -> None:
        rutas, _ = QFileDialog.getOpenFileNames(self, "Abrir paquetes de temas", str(Path.home() / "Descargas"),
                                                "Temas y fondos (*.zip *.tar *.tar.gz *.tgz *.tar.xz *.txz *.tar.bz2 "
                                                "*.jpg *.jpeg *.png *.webp *.svg *.bmp);;"
                                                "Todos los archivos (*)")
        if rutas:
            self.cargar_varios([Path(r) for r in rutas])

    def _en_segundo_plano(self, funcion, al_terminar, texto: str) -> None:
        if self.ocupado:
            return
        s = _Señales(self)
        s.listo.connect(lambda r: (self._ocupado(False), al_terminar(r)))
        s.error.connect(lambda m: (self._ocupado(False), self.statusBar().clearMessage(),
                                   QMessageBox.warning(self, "No se pudo", m)))
        s.progreso.connect(self._progreso)
        self._ocupado(True, texto)

        def correr():
            try:
                s.listo.emit(funcion(s))
            except archivos.ErrorPaquete as e:
                s.error.emit(str(e))
            except Exception as e:  # noqa: BLE001 - se muestra al usuario
                s.error.emit(f"{type(e).__name__}: {e}")

        threading.Thread(target=correr, daemon=True).start()

    def _progreso(self, recibido: int, total: int) -> None:
        if total:
            self.barra.setRange(0, 100)
            self.barra.setValue(int(recibido * 100 / total))
        self.statusBar().showMessage(f"Descargando… {recibido / 1024 / 1024:.1f} MB")

    def descargar_enlace(self) -> None:
        url = self.enlace.text().strip()
        if not url:
            self.enlace.setFocus()
            return
        self._en_segundo_plano(lambda s: archivos.archivos_del_enlace(url), self._elegir_archivo,
                               "Consultando el enlace…")

    def _elegir_archivo(self, lista: list[archivos.ArchivoRemoto]) -> None:
        lista = archivos.ordenar_para_elegir(lista)
        elegidos = lista[:1]
        if len(lista) > 1:
            dlg = DialogoArchivos(lista, self)
            if dlg.exec() != QDialog.Accepted or not dlg.elegidos():
                self.statusBar().clearMessage()
                return
            elegidos = dlg.elegidos()
        carpeta = Path(tempfile.mkdtemp(prefix="descarga-", dir=self.trabajo))

        def descargar_todos(s):
            rutas = []
            for n, a in enumerate(elegidos, 1):
                s.progreso.emit(0, 0)
                rutas.append(archivos.descargar(a, carpeta, s.progreso.emit))
            return rutas

        texto = (f"Descargando {elegidos[0].nombre}…" if len(elegidos) == 1
                 else f"Descargando {len(elegidos)} archivos…")
        self._en_segundo_plano(descargar_todos, self.cargar_varios, texto)

    def cargar(self, ruta: Path) -> None:
        self.cargar_varios([Path(ruta)])

    def cargar_varios(self, rutas: list[Path]) -> None:
        rutas = [Path(r) for r in rutas]

        def preparar(_s):
            temas, sin_temas, errores = [], [], []
            for r in rutas:
                if mod_fondos.es_imagen(r.name):
                    temas.append(Fondo(r))
                    continue
                try:
                    carpeta = archivos.preparar(r, self.trabajo)
                    encontrados = buscar_temas(carpeta, profundidad=5)
                    encontrados += mod_fondos.buscar_fondos(carpeta, excluir=[t.carpeta for t in encontrados])
                except archivos.ErrorPaquete as e:
                    errores.append(str(e))
                    continue
                (temas.extend(encontrados) if encontrados else sin_temas.append(r.name))
            return temas, sin_temas, errores

        def listo(resultado) -> None:
            temas, sin_temas, errores = resultado
            avisos = errores[:]
            if sin_temas:
                avisos.append("Sin temas para Linux en: " + ", ".join(sin_temas) +
                              ".\n(Los paquetes para Windows —.cur, .ani, .inf— no sirven en Linux.)")
            if not temas:
                QMessageBox.information(self, "Sin temas", "\n\n".join(avisos) or "No se encontraron temas.")
                self.statusBar().clearMessage()
                return
            # los nuevos se suman a los que ya estaban en «Nuevos»; si se repite un tema, queda el último
            por_id = {t.id: t for t in self.paquete}
            for t in temas:
                por_id.pop(t.id, None)
                por_id[t.id] = t
            self.paquete = list(por_id.values())
            ids_nuevos = {t.id for t in temas}
            cursores = sum(t.tiene_cursores for t in temas)
            iconos = sum(t.tiene_iconos for t in temas)
            fondos = sum(t.tiene_fondo for t in temas)
            self.pestanas.blockSignals(True)
            self.pestanas.setCurrentIndex(0 if cursores else (1 if iconos else 2))
            self.pestanas.blockSignals(False)
            self.actualizar_listas(elegir="nuevo")
            primero = next(t for t in self.paquete if t.id in ids_nuevos and _de_tipo(t, self.tipo_actual()))
            self.elegir_tema(primero.id, True)
            self._cambio_pestana()
            partes = (([f"{cursores} de cursores"] if cursores else []) + ([f"{iconos} de iconos"] if iconos else []) +
                      ([f"{fondos} fondo(s) de pantalla"] if fondos else []))
            self.statusBar().showMessage(f"{len(temas)} tema(s): {' y '.join(partes)}. Aparecen arriba, en «Nuevos»; "
                                         "elija uno para verlo y pulse «Aplicar».", 12000)
            if avisos:
                QMessageBox.information(self, "Algunos archivos no se pudieron usar", "\n\n".join(avisos))

        nombre = rutas[0].name if len(rutas) == 1 else f"{len(rutas)} archivos"
        self._en_segundo_plano(preparar, listo, f"Abriendo {nombre}…")

    # --- acciones ---------------------------------------------------------------
    def _instalar_si_hace_falta(self, tema: Tema, nuevo: bool) -> Tema | None:
        if not nuevo:
            return tema
        try:
            return _instalar(tema)
        except FileExistsError:
            r = QMessageBox.question(self, "Ya instalado",
                                     f"Ya hay un tema «{tema.id}» en su carpeta personal. ¿Reemplazarlo por este?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r != QMessageBox.Yes:
                return None
            return _instalar(tema, reemplazar=True)

    def aplicar(self) -> None:
        tema, nuevo = self.elegido()
        if tema is None:
            return
        que = {"cursores": "cursor", "iconos": "iconos", "fondos": "fondo"}[self.tipo_actual()]
        try:
            instalado = self._instalar_si_hace_falta(tema, nuevo)
            if instalado is None:
                return
            if que == "fondo":
                self.escritorio.aplicar_fondo(str(instalado.ruta), self.c_ajuste.currentData(),
                                              self.c_bloqueo.isChecked() and self.c_bloqueo.isVisible())
                msj = f"Fondo de pantalla «{instalado.titulo}» puesto."
            elif que == "cursor":
                tam = self.c_tamano.currentData()
                self.escritorio.aplicar_cursor(instalado.id, tam)
                msj = f"Cursor «{instalado.titulo}» aplicado ({tam} px)."
            else:
                self.escritorio.aplicar_iconos(instalado.id)
                msj = f"Iconos «{instalado.titulo}» aplicados."
        except Exception as e:  # noqa: BLE001 - se muestra al usuario
            QMessageBox.critical(self, "No se pudo aplicar", str(e))
            return
        self._actualizar_actual()
        if nuevo:
            self.paquete = [t for t in self.paquete if t is not tema]
        self.actualizar_listas(elegir=instalado.id)
        self._cambio_pestana()
        self.statusBar().showMessage(msj + " Algunas aplicaciones abiertas lo toman al volver a abrirlas.", 12000)

    def cambiar_favorito(self) -> None:
        tema, nuevo = self.elegido()
        if tema is None:
            return
        tipo = self.tipo_actual()
        if nuevo:   # para guardarlo hay que tenerlo instalado (no se aplica)
            try:
                tema = self._instalar_si_hace_falta(tema, True)
            except Exception as e:  # noqa: BLE001 - se muestra al usuario
                QMessageBox.critical(self, "No se pudo instalar", str(e))
                return
            if tema is None:
                self._cambio_pestana()
                return
            self.paquete = [t for t in self.paquete if t.id != tema.id]
            si = True
        else:
            si = tema.id not in favoritos()[tipo]
        seccion = self.seccion_de(self._lista_actual().currentItem())
        if seccion.startswith("★") or seccion.startswith("NUEVOS"):
            seccion = "INSTALADOS POR USTED" if _del_usuario(tema) else "DEL SISTEMA"
        marcar_favorito(tipo, tema.id, si)
        self.actualizar_listas(elegir=tema.id)
        self.elegir_tema(tema.id, False, seccion)   # se queda donde estaba (en su grupo), no salta a favoritos
        self._cambio_pestana()
        self.statusBar().showMessage(f"«{tema.titulo}» " + ("agregado a favoritos ★." if si else "quitado de favoritos."),
                                     8000)

    def eliminar(self) -> None:
        tema, nuevo = self.elegido()
        accion = self._accion_borrar(tema, nuevo)
        if accion is None:
            return
        tipo = self.tipo_actual()
        items = self.items_de_temas(self._lista_actual())
        actual = self._lista_actual().currentItem()
        pos = items.index(actual) if actual in items else -1
        siguiente = items[pos + 1].data(0, Qt.UserRole) if 0 <= pos < len(items) - 1 else None
        if nuevo:
            self.paquete = [t for t in self.paquete if t is not tema]
            mensaje = f"«{tema.titulo}» quitado de la lista."
        elif accion[0] in ("Ocultar", "Volver a mostrar"):
            a = self.escritorio.actual()
            if accion[0] == "Ocultar" and tema.id in (a.cursor, a.iconos):
                QMessageBox.information(self, "Tema en uso", "Ese tema está en uso. Aplique otro antes de ocultarlo.")
                return
            ocultar(tipo, tema.id, accion[0] == "Ocultar")
            mensaje = (f"«{tema.titulo}» oculto. Para verlo de nuevo marque «Mostrar los ocultos»."
                       if accion[0] == "Ocultar" else f"«{tema.titulo}» se muestra de nuevo.")
        else:
            a = self.escritorio.actual()
            if tema.id in (a.cursor, a.iconos):
                QMessageBox.information(self, "Tema en uso", "Ese tema está en uso. Aplique otro antes de eliminarlo.")
                return
            ambos = tema.tiene_cursores and tema.tiene_iconos
            if isinstance(tema, Fondo) and tema.id == a.fondo:
                QMessageBox.information(self, "Fondo en uso", "Es su fondo de pantalla actual. Ponga otro antes.")
                return
            texto = f"¿Eliminar «{tema.titulo}»?"
            if ambos:
                texto += "\n\nEste tema trae cursores e iconos: se eliminan los dos."
            caja = QMessageBox(QMessageBox.Question, "Eliminar tema", texto, parent=self)
            b_si = caja.addButton("Eliminar", QMessageBox.ActionRole)
            b_si.setStyleSheet("background: #f4a6a6; color: black; padding: 5px 14px;")
            b_no = caja.addButton("Cancelar", QMessageBox.ActionRole)
            caja.setDefaultButton(b_no)
            caja.setEscapeButton(b_no)
            caja.exec()
            if caja.clickedButton() is not b_si:
                return
            try:
                en_papelera = _desinstalar(tema)
                for t in ("cursores", "iconos"):
                    marcar_favorito(t, tema.id, False)
            except OSError as e:
                QMessageBox.critical(self, "No se pudo eliminar", str(e))
                return
            mensaje = f"«{tema.titulo}» eliminado" + (" (está en la papelera, por si lo quiere recuperar)."
                                                     if en_papelera else ".")
        self.actualizar_listas()
        if siguiente is not None:     # queda elegido el siguiente, para seguir limpiando rápido
            self.elegir_tema(siguiente[0].id, siguiente[1])
        self._cambio_pestana()
        self.statusBar().showMessage(mensaje, 10000)

    def restaurar(self) -> None:
        try:
            hecho = self.escritorio.restaurar()
        except Exception as e:  # noqa: BLE001
            QMessageBox.information(self, "Volver a los originales", str(e))
            return
        self._llenar_tamanos()
        self._actualizar_actual()
        self.actualizar_listas()
        self._cambio_pestana()
        self.statusBar().showMessage(f"Restaurado: {hecho}.", 10000)

    def closeEvent(self, e) -> None:
        if self.navegador is not None:
            self.navegador.liberar()
        shutil.rmtree(self.trabajo, ignore_errors=True)
        super().closeEvent(e)


def acerca() -> str:
    return f"Estilo Ágil {__version__}"

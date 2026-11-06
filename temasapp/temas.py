"""Detección de temas de cursores e iconos dentro de una carpeta."""

from __future__ import annotations

import configparser
import re
import os
from dataclasses import dataclass, field
from pathlib import Path

# (nombre en pantalla, nombres posibles del archivo en cursors/, por orden de preferencia)
CURSORES_MUESTRA: list[tuple[str, tuple[str, ...]]] = [
    ("Normal", ("left_ptr", "default", "arrow", "top_left_arrow")),
    ("Enlace", ("pointer", "hand2", "hand1", "hand", "pointing_hand")),
    ("Texto", ("text", "xterm", "ibeam")),
    ("Ocupado", ("wait", "watch")),
    ("Trabajando", ("progress", "left_ptr_watch", "half-busy")),
    ("Ayuda", ("help", "question_arrow", "left_ptr_help", "whats_this")),
    ("No permitido", ("not-allowed", "crossed_circle", "forbidden", "circle", "no-drop")),
    ("Mover", ("move", "fleur", "all-scroll", "size_all")),
    ("Agarrar", ("grabbing", "closedhand", "dnd-move", "grab", "openhand")),
    ("Precisión", ("crosshair", "cross", "tcross")),
    ("Ajustar ↔", ("ew-resize", "sb_h_double_arrow", "h_double_arrow", "size_hor", "col-resize")),
    ("Ajustar ↕", ("ns-resize", "sb_v_double_arrow", "v_double_arrow", "size_ver", "row-resize")),
    ("Ajustar ⤡", ("nwse-resize", "bd_double_arrow", "size_fdiag", "se-resize")),
    ("Ajustar ⤢", ("nesw-resize", "fd_double_arrow", "size_bdiag", "ne-resize")),
    ("Lápiz", ("pencil", "draft")),
    ("Zoom", ("zoom-in", "zoom_in")),
]

# (nombre en pantalla, nombres posibles del ícono)
ICONOS_MUESTRA: list[tuple[str, tuple[str, ...]]] = [
    ("Carpeta", ("folder", "inode-directory")),
    ("Inicio", ("user-home", "folder-home")),
    ("Escritorio", ("user-desktop", "folder-desktop")),
    ("Documentos", ("folder-documents",)),
    ("Descargas", ("folder-download", "folder-downloads")),
    ("Imágenes", ("folder-pictures", "folder-images")),
    ("Música", ("folder-music",)),
    ("Videos", ("folder-videos", "folder-video")),
    ("Papelera", ("user-trash", "user-trash-full")),
    ("Texto", ("text-x-generic", "text-plain")),
    ("PDF", ("application-pdf",)),
    ("Imagen", ("image-x-generic",)),
    ("Comprimido", ("package-x-generic", "application-x-archive", "application-zip")),
    ("Terminal", ("utilities-terminal", "org.gnome.Terminal", "terminal")),
    ("Archivos", ("system-file-manager", "org.gnome.Nautilus", "nautilus")),
    ("Navegador", ("web-browser", "firefox", "google-chrome", "brave-browser")),
    ("Ajustes", ("preferences-system", "org.gnome.Settings", "gnome-control-center")),
    ("Disco", ("drive-harddisk",)),
    ("Equipo", ("computer",)),
    ("Calculadora", ("accessories-calculator", "org.gnome.Calculator")),
]

EXTENSIONES_ICONO = (".svg", ".png", ".xpm")


@dataclass
class Tema:
    id: str                    # nombre de la carpeta (el que usa el sistema)
    carpeta: Path
    nombre: str = ""           # Name= del index.theme
    comentario: str = ""
    hereda: list[str] = field(default_factory=list)
    tiene_cursores: bool = False
    tiene_iconos: bool = False
    directorios: list[tuple[str, int, str, int, int]] = field(default_factory=list)  # (dir, tamaño, tipo, min, max)
    tiene_fondo = False        # (los fondos de pantalla son otra clase: fondos.Fondo)

    @property
    def titulo(self) -> str:
        return self.nombre or self.id

    @property
    def tipo_texto(self) -> str:
        partes = []
        if self.tiene_cursores:
            partes.append("cursores")
        if self.tiene_iconos:
            partes.append("iconos")
        return " e ".join(partes).capitalize()

    # --- cursores ---------------------------------------------------------------
    def archivo_cursor(self, nombres: tuple[str, ...]) -> Path | None:
        carpeta = self.carpeta / "cursors"
        for n in nombres:
            p = carpeta / n
            if p.is_file():          # sigue enlaces simbólicos
                return p
        return None

    # --- iconos ---------------------------------------------------------------
    def archivo_icono(self, nombres: tuple[str, ...], tamano: int = 48) -> Path | None:
        if not self.directorios:
            return None

        def puntaje(d):
            _dir, tam, tipo, minimo, maximo = d
            if tipo == "scalable" and minimo <= tamano <= maximo:
                return 0
            return 1 + abs(tam - tamano) * 2 + (1 if tam < tamano else 0)

        ordenados = sorted(self.directorios, key=puntaje)
        for n in nombres:
            for d in ordenados:
                base = self.carpeta / d[0]
                for ext in EXTENSIONES_ICONO:
                    p = base / (n + ext)
                    if p.is_file():
                        return p
        return None


def leer_index(ruta: Path) -> configparser.ConfigParser | None:
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read_string(ruta.read_text(encoding="utf-8", errors="replace"))
    except (OSError, configparser.Error):
        return None
    return cp


def _entero(v: str | None, defecto: int) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return defecto


def tema_en(carpeta: Path) -> Tema | None:
    """El tema que hay en `carpeta`, o None si no es un tema."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return None
    tema = Tema(id=carpeta.name, carpeta=carpeta)
    cursores = carpeta / "cursors"
    try:
        tema.tiene_cursores = cursores.is_dir() and any(cursores.iterdir())
    except OSError:
        tema.tiene_cursores = False
    index = carpeta / "index.theme"
    if index.is_file():
        cp = leer_index(index)
        if cp is not None and cp.has_section("Icon Theme"):
            sec = cp["Icon Theme"]
            tema.nombre = sec.get("Name", "").strip()
            tema.comentario = sec.get("Comment", "").strip()
            tema.hereda = [h.strip() for h in sec.get("Inherits", "").split(",") if h.strip()]
            dirs = [d.strip() for d in (sec.get("Directories", "") + "," + sec.get("ScaledDirectories", "")).split(",")
                    if d.strip()]
            for d in dict.fromkeys(dirs):
                info = cp[d] if cp.has_section(d) else {}
                tam = _entero(info.get("Size"), 48)
                escala = _entero(info.get("Scale"), 1)
                tipo = (info.get("Type") or "Threshold").strip().lower()
                minimo = _entero(info.get("MinSize"), tam)
                maximo = _entero(info.get("MaxSize"), tam)
                if escala != 1:
                    continue
                if (carpeta / d).is_dir():
                    tema.directorios.append((d, tam, tipo, minimo, maximo))
            tema.tiene_iconos = bool(tema.directorios)
    if not (tema.tiene_cursores or tema.tiene_iconos):
        return None
    return tema


def buscar_temas(raiz: Path, profundidad: int = 4) -> list[Tema]:
    """Todos los temas dentro de `raiz` (incluida), sin entrar en las carpetas de un tema ya encontrado."""
    raiz = Path(raiz)
    encontrados: list[Tema] = []

    def recorrer(carpeta: Path, nivel: int) -> None:
        t = tema_en(carpeta)
        if t is not None:
            encontrados.append(t)
            return
        if nivel >= profundidad:
            return
        try:
            hijos = sorted(p for p in carpeta.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return
        for h in hijos:
            recorrer(h, nivel + 1)

    recorrer(raiz, 0)
    return encontrados


def carpetas_del_sistema() -> list[Path]:
    """Carpetas donde el escritorio busca temas, de mayor a menor prioridad."""
    casa = Path.home()
    datos = Path(os.environ.get("XDG_DATA_HOME") or casa / ".local" / "share")
    rutas = [casa / ".icons", datos / "icons"]
    for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if d:
            rutas.append(Path(d) / "icons")
    rutas.append(Path("/usr/share/pixmaps"))
    vistas, unicas = set(), []
    for r in rutas:
        if r not in vistas:
            vistas.add(r)
            unicas.append(r)
    return unicas


def temas_instalados() -> list[Tema]:
    """Temas instalados (el primero gana si hay dos con el mismo nombre de carpeta)."""
    vistos: dict[str, Tema] = {}
    for base in carpetas_del_sistema():
        if not base.is_dir():
            continue
        try:
            hijos = sorted(base.iterdir())
        except OSError:
            continue
        for c in hijos:
            if c.name in vistos or c.name in ("default", "hicolor", "locolor"):
                continue
            t = tema_en(c)
            if t is not None:
                vistos[c.name] = t
    return sorted(vistos.values(), key=lambda t: t.titulo.lower())


# --- familias: agrupar las variantes de un mismo tema (Bibata-Modern-Ice, Bibata-Original-Amber…) ----------
_SEPARADORES = re.compile(r"[-_\s.]+")
_CAMEL = re.compile(r"[A-Za-z][a-z]*|[0-9]+")   # Dynamic01 → Dynamic, ZorinBlue → Zorin


def _primera_palabra(id_: str) -> str:
    partes = [p for p in _SEPARADORES.split(id_.strip()) if p]
    return partes[0] if partes else id_


def familias(temas: list[Tema]) -> dict[str, str]:
    """id del tema → nombre de su familia.

    La familia es la primera palabra del nombre (Bibata-Modern-Ice → Bibata). Si varias primeras palabras
    comparten el comienzo en «camelCase» (Zorin, ZorinBlue, ZorinGreen…), la familia es ese comienzo (Zorin)."""
    primeras = {t.id: _primera_palabra(t.id) for t in temas}
    camel = {}
    for id_, p in primeras.items():
        m = _CAMEL.match(p)
        camel[id_] = m.group(0) if m else p
    distintas: dict[str, set[str]] = {}
    for id_, c in camel.items():
        distintas.setdefault(c.lower(), set()).add(primeras[id_].lower())
    resultado = {}
    for t in temas:
        c = camel[t.id]
        nombre = c if len(distintas[c.lower()]) >= 2 else primeras[t.id]
        resultado[t.id] = nombre[:1].upper() + nombre[1:]
    return resultado


def agrupar(temas: list[Tema]) -> list[tuple[str | None, list[Tema]]]:
    """[(familia, temas)] respetando el orden: las familias con un solo tema quedan como (None, [tema])."""
    fam = familias(temas)
    grupos: dict[str, list[Tema]] = {}
    orden: list[str] = []
    for t in temas:
        clave = fam[t.id].lower()
        if clave not in grupos:
            grupos[clave] = []
            orden.append(clave)
        grupos[clave].append(t)
    resultado = []
    for clave in orden:
        miembros = grupos[clave]
        resultado.append((fam[miembros[0].id], miembros) if len(miembros) > 1 else (None, miembros))
    return resultado

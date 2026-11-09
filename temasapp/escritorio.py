"""Instalar temas en la carpeta del usuario y aplicarlos en el escritorio (GNOME, Zorin, Cinnamon, MATE, Xfce, KDE…)."""

from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .temas import Tema, tema_en

Ejecutor = Callable[[list[str]], str]   # ejecuta un comando y devuelve su salida


def entorno_sistema() -> dict[str, str]:
    """Entorno para lanzar programas del sistema. En el .deb, LD_LIBRARY_PATH apunta a las librerías del paquete y
    con ellas gsettings no carga dconf (guarda en otro lado, sin avisar) y xdg-open no abre nada."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = original
    return env


def _ejecutar(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=entorno_sistema())
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or f"{cmd[0]} falló").strip())
    return r.stdout.strip()


def carpeta_usuario() -> Path:
    datos = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return datos / "icons"


def carpetas_usuario() -> list[Path]:
    return [carpeta_usuario(), Path.home() / ".icons"]


def es_del_usuario(tema: Tema) -> bool:
    try:
        padre = tema.carpeta.parent.resolve()
    except OSError:
        return False
    return any(padre == c.resolve() for c in carpetas_usuario() if c.exists()) and tema.id != "default"


def configuracion() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "temasapp"
    base.mkdir(parents=True, exist_ok=True)
    return base


# ---------------------------------------------------------------------------------------------
def detectar_entorno() -> str:
    """gnome | cinnamon | mate | xfce | kde | lxqt | otro"""
    texto = ":".join(os.environ.get(v, "") for v in ("XDG_CURRENT_DESKTOP", "DESKTOP_SESSION",
                                                     "XDG_SESSION_DESKTOP")).lower()
    for clave, entorno in (("cinnamon", "cinnamon"), ("mate", "mate"), ("xfce", "xfce"), ("kde", "kde"),
                           ("plasma", "kde"), ("lxqt", "lxqt"), ("budgie", "gnome"), ("pantheon", "gnome"),
                           ("gnome", "gnome"), ("zorin", "gnome"), ("unity", "gnome"), ("ubuntu", "gnome"),
                           ("pop", "gnome"), ("cosmic", "gnome")):
        if clave in texto:
            return entorno
    return "otro"


NOMBRES_ENTORNO = {"gnome": "GNOME", "cinnamon": "Cinnamon", "mate": "MATE", "xfce": "Xfce", "kde": "KDE Plasma",
                   "lxqt": "LXQt", "otro": "su escritorio"}


@dataclass
class Actual:
    cursor: str = ""
    tamano: int = 24
    iconos: str = ""
    fondo: str = ""          # ruta de la imagen
    ajuste: str = "zoom"


class Escritorio:
    def __init__(self, entorno: str | None = None, ejecutor: Ejecutor | None = None):
        self.entorno = entorno or detectar_entorno()
        self.ejecutar = ejecutor or _ejecutar

    # --- lectura ---------------------------------------------------------------
    def _gs_get(self, esquema: str, clave: str) -> str:
        try:
            return self.ejecutar(["gsettings", "get", esquema, clave]).strip().strip("'")
        except (RuntimeError, OSError, subprocess.SubprocessError):
            return ""

    def _xf_get(self, prop: str) -> str:
        try:
            return self.ejecutar(["xfconf-query", "-c", "xsettings", "-p", prop])
        except (RuntimeError, OSError, subprocess.SubprocessError):
            return ""

    def actual(self) -> Actual:
        a = Actual()
        e = self.entorno
        if e in ("gnome", "otro", "cinnamon", "mate"):
            esq_int = {"cinnamon": "org.cinnamon.desktop.interface"}.get(e, "org.gnome.desktop.interface")
            if e == "mate":
                a.cursor = self._gs_get("org.mate.peripherals-mouse", "cursor-theme")
                tam = self._gs_get("org.mate.peripherals-mouse", "cursor-size")
                a.iconos = self._gs_get("org.mate.interface", "icon-theme")
            else:
                a.cursor = self._gs_get(esq_int, "cursor-theme")
                tam = self._gs_get(esq_int, "cursor-size")
                a.iconos = self._gs_get(esq_int, "icon-theme")
            a.tamano = int(tam) if tam.isdigit() else 24
        elif e == "xfce":
            a.cursor = self._xf_get("/Gtk/CursorThemeName")
            tam = self._xf_get("/Gtk/CursorThemeSize")
            a.tamano = int(tam) if tam.isdigit() else 24
            a.iconos = self._xf_get("/Net/IconThemeName")
        elif e == "kde":
            a.cursor = self._kde_leer("kcminputrc", "Mouse", "cursorTheme")
            tam = self._kde_leer("kcminputrc", "Mouse", "cursorSize")
            a.tamano = int(tam) if tam.isdigit() else 24
            a.iconos = self._kde_leer("kdeglobals", "Icons", "Theme")
        if not a.cursor:
            a.cursor = self._cursor_por_defecto()
        a.fondo, a.ajuste = self._fondo_actual()
        return a

    # --- fondo de pantalla ---------------------------------------------------------
    def _fondo_actual(self) -> tuple[str, str]:
        e = self.entorno
        if e == "mate":
            return (self._gs_get("org.mate.background", "picture-filename"),
                    self._gs_get("org.mate.background", "picture-options") or "zoom")
        esquema = "org.cinnamon.desktop.background" if e == "cinnamon" else "org.gnome.desktop.background"
        if e in ("gnome", "otro", "cinnamon"):
            uri = self._gs_get(esquema, "picture-uri")
            return _ruta_de_uri(uri), self._gs_get(esquema, "picture-options") or "zoom"
        if e == "xfce":
            for prop in self._props_xfce():
                v = self._xf_get(prop)
                if v:
                    return v, "zoom"
        return "", "zoom"

    def _props_xfce(self) -> list[str]:
        try:
            salida = self.ejecutar(["xfconf-query", "-c", "xfce4-desktop", "-l"])
        except (RuntimeError, OSError, subprocess.SubprocessError):
            return []
        return [l.strip() for l in salida.splitlines() if l.strip().endswith("/last-image")]

    def comandos_fondo(self, ruta: str, ajuste: str = "zoom", bloqueo: bool = False,
                       ruta_oscuro: str | None = None) -> list[list[str]]:
        uri = Path(ruta).as_uri() if ruta else ""
        uri_osc = Path(ruta_oscuro).as_uri() if ruta_oscuro else uri
        e = self.entorno
        if e == "mate":
            return [["gsettings", "set", "org.mate.background", "picture-filename", ruta],
                    ["gsettings", "set", "org.mate.background", "picture-options", ajuste]]
        if e == "cinnamon":
            return [["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri],
                    ["gsettings", "set", "org.cinnamon.desktop.background", "picture-options", ajuste]]
        if e == "xfce":
            estilo = {"centered": "1", "wallpaper": "2", "stretched": "3", "scaled": "4", "zoom": "5",
                      "spanned": "6"}.get(ajuste, "5")
            cmds = []
            for prop in self._props_xfce() or ["/backdrop/screen0/monitor0/workspace0/last-image"]:
                cmds.append(["xfconf-query", "-c", "xfce4-desktop", "-p", prop, "-n", "-t", "string", "-s", ruta])
                cmds.append(["xfconf-query", "-c", "xfce4-desktop", "-p", prop.replace("last-image", "image-style"),
                             "-n", "-t", "int", "-s", estilo])
            return cmds
        if e == "kde":
            return [["plasma-apply-wallpaperimage", ruta]]
        cmds = [["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
                ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri_osc],
                ["gsettings", "set", "org.gnome.desktop.background", "picture-options", ajuste]]
        if bloqueo:
            cmds += [["gsettings", "set", "org.gnome.desktop.screensaver", "picture-uri", uri],
                     ["gsettings", "set", "org.gnome.desktop.screensaver", "picture-options", ajuste]]
        return cmds

    def aplicar_fondo(self, ruta: str, ajuste: str = "zoom", bloqueo: bool = False) -> None:
        self._guardar_anterior("fondo")
        for cmd in self.comandos_fondo(ruta, ajuste, bloqueo):
            self.ejecutar(cmd)

    def _kde_leer(self, archivo: str, grupo: str, clave: str) -> str:
        for prog in ("kreadconfig6", "kreadconfig5"):
            if shutil.which(prog):
                try:
                    return self.ejecutar([prog, "--file", archivo, "--group", grupo, "--key", clave])
                except (RuntimeError, OSError, subprocess.SubprocessError):
                    pass
        return ""

    def _cursor_por_defecto(self) -> str:
        from .temas import leer_index

        idx = Path.home() / ".icons" / "default" / "index.theme"
        if idx.is_file():
            cp = leer_index(idx)
            if cp is not None and cp.has_section("Icon Theme"):
                return cp["Icon Theme"].get("Inherits", "").split(",")[0].strip()
        return ""

    # --- aplicar ---------------------------------------------------------------
    def comandos_cursor(self, nombre: str, tamano: int) -> list[list[str]]:
        e = self.entorno
        if e == "cinnamon":
            return [["gsettings", "set", "org.cinnamon.desktop.interface", "cursor-theme", nombre],
                    ["gsettings", "set", "org.cinnamon.desktop.interface", "cursor-size", str(tamano)],
                    ["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", nombre],
                    ["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(tamano)]]
        if e == "mate":
            return [["gsettings", "set", "org.mate.peripherals-mouse", "cursor-theme", nombre],
                    ["gsettings", "set", "org.mate.peripherals-mouse", "cursor-size", str(tamano)]]
        if e == "xfce":
            return [["xfconf-query", "-c", "xsettings", "-p", "/Gtk/CursorThemeName", "-n", "-t", "string",
                     "-s", nombre],
                    ["xfconf-query", "-c", "xsettings", "-p", "/Gtk/CursorThemeSize", "-n", "-t", "int",
                     "-s", str(tamano)]]
        if e == "kde":
            cmds = [["plasma-apply-cursortheme", nombre]]
            prog = "kwriteconfig6" if shutil.which("kwriteconfig6") else "kwriteconfig5"
            cmds.append([prog, "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorSize", str(tamano)])
            return cmds
        return [["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", nombre],
                ["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(tamano)]]

    def comandos_iconos(self, nombre: str) -> list[list[str]]:
        e = self.entorno
        if e == "cinnamon":
            return [["gsettings", "set", "org.cinnamon.desktop.interface", "icon-theme", nombre]]
        if e == "mate":
            return [["gsettings", "set", "org.mate.interface", "icon-theme", nombre]]
        if e == "xfce":
            return [["xfconf-query", "-c", "xsettings", "-p", "/Net/IconThemeName", "-n", "-t", "string",
                     "-s", nombre]]
        if e == "kde":
            prog = shutil.which("plasma-changeicons")
            if not prog:
                for c in ("/usr/lib/x86_64-linux-gnu/libexec/plasma-changeicons", "/usr/libexec/plasma-changeicons",
                          "/usr/lib/libexec/plasma-changeicons", "/usr/lib64/libexec/plasma-changeicons"):
                    if Path(c).exists():
                        prog = c
                        break
            return [[prog or "plasma-changeicons", nombre]]
        return [["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", nombre]]

    def aplicar_cursor(self, nombre: str, tamano: int) -> None:
        self._guardar_anterior("cursor")
        for cmd in self.comandos_cursor(nombre, tamano):
            self.ejecutar(cmd)
        self._cursor_x11_por_defecto(nombre)

    def aplicar_tamano(self, tamano: int) -> None:
        """Cambia solo el tamaño del cursor, dejando el tema que ya está en uso."""
        self._guardar_anterior("cursor")
        actual = self.actual().cursor
        for cmd in self.comandos_cursor(actual, tamano):
            if actual or "size" in " ".join(cmd).lower():
                self.ejecutar(cmd)

    def fondo_movido(self, viejo: str, nuevo: str) -> None:
        """Si el fondo (o el de bloqueo) era `viejo`, ahora apunta a `nuevo` (al renombrar el archivo)."""
        if self.entorno in ("gnome", "otro"):
            for esquema, clave in (("org.gnome.desktop.background", "picture-uri"),
                                   ("org.gnome.desktop.background", "picture-uri-dark"),
                                   ("org.gnome.desktop.screensaver", "picture-uri")):
                if _ruta_de_uri(self._gs_get(esquema, clave)) == viejo:
                    self.ejecutar(["gsettings", "set", esquema, clave, Path(nuevo).as_uri()])
        elif self.actual().fondo == viejo:
            a = self.actual()
            for cmd in self.comandos_fondo(nuevo, a.ajuste):
                self.ejecutar(cmd)
        datos = self.anterior()
        cambio = False
        for k in ("fondo", "fondo_oscuro", "bloqueo"):
            if datos.get(k) == viejo:
                datos[k] = nuevo
                cambio = True
        if cambio:
            self._archivo_anterior().write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    def aplicar_iconos(self, nombre: str) -> None:
        self._guardar_anterior("iconos")
        for cmd in self.comandos_iconos(nombre):
            self.ejecutar(cmd)

    def _cursor_x11_por_defecto(self, nombre: str) -> None:
        """Las aplicaciones antiguas (X11) usan ~/.icons/default/index.theme."""
        carpeta = Path.home() / ".icons" / "default"
        idx = carpeta / "index.theme"
        if carpeta.is_symlink():
            return
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            if idx.exists() and not (configuracion() / "default-index.theme.original").exists():
                shutil.copy2(idx, configuracion() / "default-index.theme.original")
            idx.write_text(f"[Icon Theme]\nName=Default\nComment=Cursor elegido con Temas Linux\nInherits={nombre}\n",
                           encoding="utf-8")
        except OSError:
            pass

    # --- deshacer ---------------------------------------------------------------
    def _archivo_anterior(self) -> Path:
        return configuracion() / "anterior.json"

    def _guardar_anterior(self, que: str) -> None:
        """Guarda cómo estaba el escritorio antes del primer cambio, para poder volver a eso."""
        datos = self.anterior()
        if que == "cursor" and datos.get("cursor"):
            return
        if que == "iconos" and datos.get("iconos"):
            return
        if que == "fondo" and datos.get("fondo"):
            return
        a = self.actual()
        if que == "cursor":
            datos["cursor"], datos["tamano"] = a.cursor, a.tamano
        elif que == "iconos":
            datos["iconos"] = a.iconos
        else:
            datos["fondo"], datos["ajuste"] = a.fondo, a.ajuste
            if self.entorno in ("gnome", "otro"):
                datos["fondo_oscuro"] = _ruta_de_uri(self._gs_get("org.gnome.desktop.background", "picture-uri-dark"))
                datos["bloqueo"] = _ruta_de_uri(self._gs_get("org.gnome.desktop.screensaver", "picture-uri"))
        self._archivo_anterior().write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    def anterior(self) -> dict:
        try:
            return json.loads(self._archivo_anterior().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def restaurar(self) -> str:
        datos = self.anterior()
        hechos = []
        if datos.get("cursor"):
            for cmd in self.comandos_cursor(datos["cursor"], int(datos.get("tamano") or 24)):
                self.ejecutar(cmd)
            self._cursor_x11_por_defecto(datos["cursor"])
            hechos.append(f"cursor {datos['cursor']}")
        if datos.get("iconos"):
            for cmd in self.comandos_iconos(datos["iconos"]):
                self.ejecutar(cmd)
            hechos.append(f"iconos {datos['iconos']}")
        if datos.get("fondo"):
            for cmd in self.comandos_fondo(datos["fondo"], datos.get("ajuste") or "zoom",
                                           ruta_oscuro=datos.get("fondo_oscuro") or None):
                self.ejecutar(cmd)
            if datos.get("bloqueo") and self.entorno in ("gnome", "otro"):
                self.ejecutar(["gsettings", "set", "org.gnome.desktop.screensaver", "picture-uri",
                               Path(datos["bloqueo"]).as_uri()])
            hechos.append(f"fondo {Path(datos['fondo']).name}")
        if not hechos:
            raise RuntimeError("No hay un tema anterior guardado.")
        self._archivo_anterior().unlink(missing_ok=True)
        return " y ".join(hechos)


# ---------------------------------------------------------------------------------------------
def instalar(tema: Tema, reemplazar: bool = False) -> Tema:
    """Copia el tema a ~/.local/share/icons/<id> (conservando los enlaces simbólicos de los cursores)."""
    base = carpeta_usuario()
    base.mkdir(parents=True, exist_ok=True)
    destino = base / tema.id
    if destino.resolve() == tema.carpeta.resolve():
        return tema
    if destino.exists() or destino.is_symlink():
        if not reemplazar:
            raise FileExistsError(destino)
        _borrar(destino)
    temporal = base / f".{tema.id}.instalando"
    if temporal.exists():
        _borrar(temporal)
    shutil.copytree(tema.carpeta, temporal, symlinks=True)
    temporal.rename(destino)
    if tema.tiene_iconos and shutil.which("gtk-update-icon-cache"):
        try:
            subprocess.run(["gtk-update-icon-cache", "-f", "-t", "-q", str(destino)], capture_output=True, timeout=120,
                           env=entorno_sistema())
        except (OSError, subprocess.SubprocessError):
            pass
    nuevo = tema_en(destino)
    if nuevo is None:
        raise RuntimeError("El tema no quedó bien instalado.")
    return nuevo


def _borrar(ruta: Path) -> None:
    if ruta.is_symlink() or ruta.is_file():
        ruta.unlink()
    else:
        shutil.rmtree(ruta)


def desinstalar(tema: Tema, papelera: bool = True) -> bool:
    """Quita un tema de la carpeta personal. Lo manda a la papelera si se puede (para recuperarlo);
    devuelve True si quedó en la papelera."""
    if not es_del_usuario(tema):
        raise PermissionError("Solo se pueden eliminar los temas instalados en su carpeta personal.")
    if papelera and shutil.which("gio"):
        r = subprocess.run(["gio", "trash", str(tema.carpeta)], capture_output=True, timeout=60, env=entorno_sistema())
        if r.returncode == 0 and not (tema.carpeta.exists() or tema.carpeta.is_symlink()):
            return True
    _borrar(tema.carpeta)
    return False


# --- temas ocultos (los del sistema no se borran: se ocultan de la lista) --------------------
def _archivo_ocultos() -> Path:
    return configuracion() / "ocultos.json"


def ocultos() -> dict[str, list[str]]:
    try:
        datos = json.loads(_archivo_ocultos().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    return {t: list(datos.get(t, [])) for t in ("cursores", "iconos", "fondos")}


def ocultar(tipo: str, id_: str, si: bool = True) -> None:
    datos = ocultos()
    lista = [x for x in datos[tipo] if x != id_]
    if si:
        lista.append(id_)
    datos[tipo] = sorted(lista)
    _archivo_ocultos().write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def instalado_igual(tema: Tema) -> bool:
    return (carpeta_usuario() / tema.id).exists()


# --- favoritos ------------------------------------------------------------------------------
def _archivo_favoritos() -> Path:
    return configuracion() / "favoritos.json"


def favoritos() -> dict[str, list[str]]:
    try:
        datos = json.loads(_archivo_favoritos().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    return {t: list(datos.get(t, [])) for t in ("cursores", "iconos", "fondos")}


def marcar_favorito(tipo: str, id_: str, si: bool = True) -> None:
    datos = favoritos()
    lista = [x for x in datos[tipo] if x != id_]
    if si:
        lista.append(id_)
    datos[tipo] = lista
    _archivo_favoritos().write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def _ruta_de_uri(uri: str) -> str:
    if uri.startswith("file://"):
        from urllib.parse import unquote, urlparse

        return unquote(urlparse(uri).path)
    return uri


# --- renombrar ---------------------------------------------------------------------------------
def renombrar_tema(tema: Tema, nombre: str) -> None:
    """Cambia el nombre que se muestra (Name= del index.theme). La carpeta no cambia, así que el escritorio
    lo sigue encontrando aunque esté en uso."""
    nombre = " ".join(nombre.split())
    if not nombre:
        raise ValueError("El nombre no puede quedar vacío.")
    if not es_del_usuario(tema):
        raise PermissionError("Solo se pueden renombrar los temas de su carpeta personal.")
    idx = tema.carpeta / "index.theme"
    lineas = []
    if idx.is_file():
        lineas = idx.read_text(encoding="utf-8", errors="replace").splitlines()
    if idx.is_symlink():
        idx.unlink()                       # se reemplaza por un archivo propio
    if not any(l.strip() == "[Icon Theme]" for l in lineas):
        lineas = ["[Icon Theme]", f"Name={nombre}"] + ([""] + lineas if lineas else [])
    else:
        nuevas, en_seccion, puesto = [], False, False
        for l in lineas:
            t = l.strip()
            if t.startswith("[") and t.endswith("]"):
                if en_seccion and not puesto:
                    nuevas.append(f"Name={nombre}")
                    puesto = True
                en_seccion = t == "[Icon Theme]"
            elif en_seccion and re.match(r"^Name(\[[^\]]*\])?\s*=", t):
                if not puesto:
                    nuevas.append(f"Name={nombre}")
                    puesto = True
                continue                    # se quitan los Name[xx]= traducidos para que se vea el nuevo
            nuevas.append(l)
        if en_seccion and not puesto:
            nuevas.append(f"Name={nombre}")
        lineas = nuevas
    idx.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def renombrar_clave(tipo: str, viejo: str, nuevo: str) -> None:
    """Mantiene favoritos y ocultos cuando cambia el identificador (la ruta de un fondo)."""
    for ruta, leer in ((_archivo_favoritos(), favoritos), (_archivo_ocultos(), ocultos)):
        datos = leer()
        if viejo in datos[tipo]:
            datos[tipo] = [nuevo if x == viejo else x for x in datos[tipo]]
            ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

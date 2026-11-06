"""Descarga y descompresión segura de paquetes de temas (zip, tar.gz, tar.xz, tar.bz2)."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

AGENTE = "TemasLinux/1.0 (instalador de cursores e iconos)"
MAX_DESCARGA = 600 * 1024 * 1024          # 600 MB
MAX_DESCOMPRIMIDO = 3 * 1024 * 1024 * 1024  # 3 GB
MAX_ARCHIVOS = 300_000
EXT_PAQUETE = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tbz")

Progreso = Callable[[int, int], None]   # (bytes recibidos, total o 0)


class ErrorPaquete(Exception):
    """Error con un mensaje para mostrar al usuario."""


def es_paquete(nombre: str) -> bool:
    return nombre.lower().endswith(EXT_PAQUETE)


def es_util(nombre: str) -> bool:
    """Un paquete de temas o una imagen (fondo de pantalla)."""
    from .fondos import es_imagen

    return es_paquete(nombre) or es_imagen(nombre)


# ---------------------------------------------------------------------------------------------
# Descompresión
# ---------------------------------------------------------------------------------------------
def _dentro(base: Path, destino: Path) -> bool:
    try:
        destino.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _enlace_valido(base: Path, ubicacion: Path, objetivo: str) -> bool:
    if not objetivo or os.path.isabs(objetivo):
        return False
    return _dentro(base, (ubicacion.parent / objetivo))


def extraer(origen: Path, destino: Path) -> None:
    """Descomprime `origen` en `destino` sin permitir rutas fuera de `destino`."""
    origen, destino = Path(origen), Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    nombre = origen.name.lower()
    if zipfile.is_zipfile(origen):
        _extraer_zip(origen, destino)
    elif tarfile.is_tarfile(origen):
        _extraer_tar(origen, destino)
    else:
        raise ErrorPaquete(f"«{origen.name}» no es un archivo comprimido compatible (zip, tar.gz, tar.xz, tar.bz2)."
                           + (" Los .7z y .rar no son compatibles todavía." if nombre.endswith((".7z", ".rar")) else ""))


def _extraer_zip(origen: Path, destino: Path) -> None:
    with zipfile.ZipFile(origen) as z:
        infos = z.infolist()
        if len(infos) > MAX_ARCHIVOS or sum(i.file_size for i in infos) > MAX_DESCOMPRIMIDO:
            raise ErrorPaquete("El archivo es demasiado grande para ser un tema.")
        enlaces = []
        for info in infos:
            ruta = destino / info.filename
            if info.filename.startswith(("/", "\\")) or not _dentro(destino, ruta):
                raise ErrorPaquete(f"El archivo contiene una ruta no permitida: {info.filename}")
            modo = info.external_attr >> 16
            if stat.S_ISLNK(modo):
                enlaces.append((ruta, z.read(info).decode("utf-8", "replace")))
            elif info.is_dir():
                ruta.mkdir(parents=True, exist_ok=True)
            else:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(ruta, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        for ruta, objetivo in enlaces:
            # los temas de cursores usan muchos enlaces simbólicos (alias de un mismo cursor)
            if _enlace_valido(destino, ruta, objetivo):
                ruta.parent.mkdir(parents=True, exist_ok=True)
                if not ruta.exists() and not ruta.is_symlink():
                    os.symlink(objetivo, ruta)


def _extraer_tar(origen: Path, destino: Path) -> None:
    try:
        with tarfile.open(origen) as t:
            miembros = t.getmembers()
            if len(miembros) > MAX_ARCHIVOS or sum(m.size for m in miembros) > MAX_DESCOMPRIMIDO:
                raise ErrorPaquete("El archivo es demasiado grande para ser un tema.")
            seguros = []
            for m in miembros:
                try:
                    seguros.append(tarfile.data_filter(m, str(destino)))
                except tarfile.FilterError:
                    continue   # se omite lo que apunte fuera (enlaces absolutos, rutas con ..)
            t.extractall(destino, members=[m for m in seguros if m is not None], filter="data")
    except (tarfile.TarError, EOFError, OSError) as e:
        if isinstance(e, ErrorPaquete):
            raise
        raise ErrorPaquete(f"No se pudo descomprimir «{origen.name}»: {e}") from e


def preparar(origen: Path, trabajo: Path) -> Path:
    """Descomprime un paquete (o usa una carpeta) y descomprime también los paquetes que traiga adentro.

    Devuelve la carpeta donde buscar los temas."""
    origen = Path(origen)
    if origen.is_dir():
        return origen
    destino = Path(tempfile.mkdtemp(prefix="paquete-", dir=trabajo))
    extraer(origen, destino)
    # muchos paquetes traen varios .tar.xz adentro (una variante de color en cada uno)
    for interno in sorted(destino.rglob("*")):
        if interno.is_file() and not interno.is_symlink() and es_paquete(interno.name):
            sub = interno.with_name(interno.name + ".contenido")
            try:
                extraer(interno, sub)
            except ErrorPaquete:
                continue
    return destino


# ---------------------------------------------------------------------------------------------
# Descargas
# ---------------------------------------------------------------------------------------------
@dataclass
class ArchivoRemoto:
    nombre: str
    url: str
    tamano: int = 0          # bytes, 0 si no se conoce

    @property
    def parece_windows(self) -> bool:
        n = self.nombre.lower()
        return "windows" in n or "win" in re.split(r"[-_. ]", n) or n.endswith((".exe", ".inf", ".ani", ".cur"))

    @property
    def texto(self) -> str:
        if self.tamano:
            mb = self.tamano / 1024 / 1024
            return f"{self.nombre}  ({mb:.1f} MB)" if mb >= 0.1 else f"{self.nombre}  ({self.tamano // 1024} KB)"
        return self.nombre


_PLING = re.compile(r"^https?://(?:www\.)?(?:gnome-look|pling|xfce-look|cinnamon-look|store\.kde|"
                    r"opendesktop|mate-look|enlightenment-themes|linux-apps)\.(?:org|com)/.*?/?p/(\d+)", re.I)
_GITHUB = re.compile(r"^https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/(?:releases)?(?:/.*)?)?$", re.I)


def url_segura(url: str) -> str:
    """Codifica espacios y letras con tilde de la dirección (p. ej. «1440P No Logo.jpg» → «1440P%20No%20Logo.jpg»),
    sin tocar lo que ya venía codificado."""
    partes = urllib.parse.urlsplit(url.strip())
    seguro = "/%:@!$&'()*+,;=~-._"
    return urllib.parse.urlunsplit((partes.scheme, partes.netloc.encode("idna").decode("ascii") if partes.netloc
                                    and not partes.netloc.isascii() else partes.netloc,
                                    urllib.parse.quote(partes.path, safe=seguro),
                                    urllib.parse.quote(partes.query, safe=seguro + "?"),
                                    urllib.parse.quote(partes.fragment, safe=seguro)))


def _get(url: str, limite: int = 2 * 1024 * 1024) -> bytes:
    pedido = urllib.request.Request(url_segura(url), headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(pedido, timeout=30) as r:
        return r.read(limite)


def archivos_del_enlace(url: str) -> list[ArchivoRemoto]:
    """Archivos que se pueden descargar desde el enlace pegado por el usuario."""
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        raise ErrorPaquete("El enlace debe empezar con http:// o https://")
    m = _PLING.match(url)
    if m:
        return _archivos_pling(m.group(1))
    m = _GITHUB.match(url)
    if m and not es_paquete(urllib.parse.urlparse(url).path):
        return _archivos_github(m.group(1), m.group(2))
    nombre = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name or "paquete"
    return [ArchivoRemoto(nombre, url)]


def _archivos_pling(id_: str) -> list[ArchivoRemoto]:
    ultimo = None
    for api in ("https://api.gnome-look.org", "https://api.pling.com"):
        try:
            datos = json.loads(_get(f"{api}/ocs/v1/content/data/{id_}?format=json"))
            break
        except (OSError, ValueError) as e:
            ultimo = e
    else:
        raise ErrorPaquete(f"No se pudo consultar la página del tema: {ultimo}")
    contenido = datos.get("data")
    if isinstance(contenido, list):
        contenido = contenido[0] if contenido else None
    if not contenido:
        raise ErrorPaquete("La página no tiene archivos para descargar.")
    archivos = []
    for i in range(1, 100):
        nombre = contenido.get(f"downloadname{i}")
        enlace = contenido.get(f"downloadlink{i}")
        if not nombre and not enlace:
            if i > 3 and not contenido.get(f"downloadname{i + 1}"):
                break
            continue
        if not enlace:
            continue
        try:
            tam = int(float(contenido.get(f"downloadsize{i}") or 0) * 1024)   # la API da KB
        except ValueError:
            tam = 0
        archivos.append(ArchivoRemoto(nombre or f"archivo{i}", enlace, tam))
    if not archivos:
        raise ErrorPaquete("La página no tiene archivos para descargar.")
    return archivos


def _archivos_github(dueno: str, repo: str) -> list[ArchivoRemoto]:
    try:
        datos = json.loads(_get(f"https://api.github.com/repos/{dueno}/{repo}/releases/latest"))
    except OSError as e:
        raise ErrorPaquete("Ese repositorio de GitHub no tiene versiones publicadas para descargar. "
                           "Descargue el archivo del tema y arrástrelo aquí.") from e
    archivos = [ArchivoRemoto(a["name"], a["browser_download_url"], int(a.get("size") or 0))
                for a in datos.get("assets", [])]
    if not archivos:
        raise ErrorPaquete("La última versión de ese repositorio no trae archivos para descargar.")
    return archivos


def ordenar_para_elegir(archivos: list[ArchivoRemoto]) -> list[ArchivoRemoto]:
    """Primero los paquetes para Linux, al final los de Windows y lo que no es un paquete."""
    return sorted(archivos, key=lambda a: (a.parece_windows, not es_util(a.nombre)))


def descargar(archivo: ArchivoRemoto, carpeta: Path, progreso: Progreso | None = None) -> Path:
    pedido = urllib.request.Request(url_segura(archivo.url), headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(pedido, timeout=60) as r:
            total = int(r.headers.get("Content-Length") or 0)
            if total > MAX_DESCARGA:
                raise ErrorPaquete("El archivo es demasiado grande para ser un tema.")
            nombre = archivo.nombre
            disp = r.headers.get("Content-Disposition") or ""
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disp)
            if m and not es_paquete(nombre):
                nombre = urllib.parse.unquote(m.group(1))
            nombre = re.sub(r"[\\/:*?\"<>|]", "_", Path(nombre).name) or "paquete"
            destino = Path(carpeta) / nombre
            recibido = 0
            with open(destino, "wb") as f:
                while True:
                    trozo = r.read(256 * 1024)
                    if not trozo:
                        break
                    recibido += len(trozo)
                    if recibido > MAX_DESCARGA:
                        raise ErrorPaquete("El archivo es demasiado grande para ser un tema.")
                    f.write(trozo)
                    if progreso:
                        progreso(recibido, total)
    except ErrorPaquete:
        raise
    except OSError as e:
        raise ErrorPaquete(f"No se pudo descargar el archivo: {e}") from e
    return destino

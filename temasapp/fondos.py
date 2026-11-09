"""Fondos de pantalla: detección en paquetes, instalados en el equipo, instalar y eliminar."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .escritorio import entorno_sistema

EXT_IMAGEN = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".svg", ".jxl", ".avif")
LADO_MAYOR_MIN = 1000      # una imagen más chica no se considera fondo de pantalla (iconos, miniaturas…)
LADO_MENOR_MIN = 500


def es_imagen(nombre: str | Path) -> bool:
    return str(nombre).lower().endswith(EXT_IMAGEN)


def tamano_imagen(ruta: Path) -> tuple[int, int]:
    from PySide6.QtGui import QImageReader

    t = QImageReader(str(ruta)).size()
    return (t.width(), t.height()) if t.isValid() else (0, 0)


def parece_fondo(ruta: Path) -> bool:
    ancho, alto = tamano_imagen(ruta)
    return max(ancho, alto) >= LADO_MAYOR_MIN and min(ancho, alto) >= LADO_MENOR_MIN


@dataclass
class Fondo:
    ruta: Path
    grupo: str | None = None     # carpeta que lo contiene (para agrupar las colecciones)

    tiene_cursores = False
    tiene_iconos = False
    tiene_fondo = True
    comentario = ""

    @property
    def id(self) -> str:
        return str(self.ruta)

    @property
    def carpeta(self) -> Path:
        return self.ruta

    @property
    def titulo(self) -> str:
        texto = re.sub(r"[-_]+", " ", self.ruta.stem).strip()
        return texto[:1].upper() + texto[1:] if texto else self.ruta.name

    @property
    def tipo_texto(self) -> str:
        return "Fondo de pantalla"


def _grupo(ruta: Path, raiz: Path) -> str | None:
    try:
        rel = ruta.parent.relative_to(raiz)
    except ValueError:
        return None
    partes = [p for p in rel.parts if p not in (".", "")]
    if not partes:
        return None
    nombre = re.sub(r"\.contenido$", "", partes[0])
    nombre = re.sub(r"\.(zip|tar|tar\.gz|tgz|tar\.xz|txz|tar\.bz2)$", "", nombre, flags=re.I)
    return re.sub(r"[-_]+", " ", nombre).strip() or None


def buscar_fondos(raiz: Path, excluir: list[Path] | None = None, limite: int = 2000) -> list[Fondo]:
    """Imágenes de tamaño de fondo de pantalla dentro de `raiz` (sin entrar en las carpetas de temas)."""
    raiz = Path(raiz)
    excluidas = [Path(e).resolve() for e in (excluir or [])]
    encontrados = []
    for p in sorted(raiz.rglob("*")):
        if len(encontrados) >= limite:
            break
        if not p.is_file() or not es_imagen(p.name):
            continue
        real = p.resolve()
        if any(real == e or e in real.parents for e in excluidas):
            continue
        if parece_fondo(p):
            encontrados.append(Fondo(p, _grupo(p, raiz)))
    return encontrados


# ---------------------------------------------------------------------------------------------
def carpeta_usuario() -> Path:
    datos = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return datos / "backgrounds"


def carpetas_sistema() -> list[Path]:
    rutas = []
    for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if d and Path(d, "backgrounds") not in rutas:
            rutas.append(Path(d) / "backgrounds")
    return rutas


def fondos_instalados() -> list[Fondo]:
    resultado, vistos = [], set()
    for base in [carpeta_usuario()] + carpetas_sistema():
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if len(p.relative_to(base).parts) > 3 or not p.is_file() or not es_imagen(p.name):
                continue
            real = p.resolve()
            if real in vistos:
                continue
            vistos.add(real)
            resultado.append(Fondo(p, _grupo(p, base)))
    return sorted(resultado, key=lambda f: ((f.grupo or "").lower(), f.titulo.lower()))


def es_del_usuario(fondo: Fondo) -> bool:
    base = carpeta_usuario().resolve() if carpeta_usuario().exists() else carpeta_usuario()
    try:
        fondo.ruta.resolve().relative_to(base)
        return True
    except ValueError:
        return False


def destino_de(fondo: Fondo) -> Path:
    return carpeta_usuario() / fondo.ruta.name


def instalado_igual(fondo: Fondo) -> bool:
    return destino_de(fondo).exists()


def instalar(fondo: Fondo, reemplazar: bool = False) -> Fondo:
    base = carpeta_usuario()
    base.mkdir(parents=True, exist_ok=True)
    destino = destino_de(fondo)
    if destino.exists() and destino.resolve() == fondo.ruta.resolve():
        return fondo
    if destino.exists() and not reemplazar:
        raise FileExistsError(destino)
    shutil.copy2(fondo.ruta, destino)
    return Fondo(destino)


def desinstalar(fondo: Fondo) -> bool:
    if not es_del_usuario(fondo):
        raise PermissionError("Solo se pueden eliminar los fondos de su carpeta personal.")
    if shutil.which("gio"):
        r = subprocess.run(["gio", "trash", str(fondo.ruta)], capture_output=True, timeout=60, env=entorno_sistema())
        if r.returncode == 0 and not fondo.ruta.exists():
            return True
    fondo.ruta.unlink()
    return False


def agrupar(fondos: list[Fondo]) -> list[tuple[str | None, list[Fondo]]]:
    """Por carpeta; los que están sueltos, por el comienzo del nombre (Zorin, ZorinBlue-Dark… → Zorin)."""
    from types import SimpleNamespace

    from .temas import familias

    sueltos = [f for f in fondos if f.grupo is None]
    fam = familias([SimpleNamespace(id=f.ruta.stem) for f in sueltos])
    grupos: dict[str | None, list[Fondo]] = {}
    for f in fondos:
        grupos.setdefault(f.grupo if f.grupo is not None else "·" + fam[f.ruta.stem], []).append(f)
    resultado = []
    for clave, miembros in grupos.items():
        if clave is None or len(miembros) == 1 or (clave.startswith("·") and len(miembros) < 3):
            resultado.extend((None, [m]) for m in miembros)
        else:
            nombre = clave.lstrip("·")
            resultado.append((nombre[:1].upper() + nombre[1:], miembros))
    return resultado


def renombrar(fondo: Fondo, nombre: str) -> Fondo:
    """Renombra el archivo de un fondo de la carpeta personal (conserva la extensión)."""
    nombre = " ".join(nombre.replace("/", "-").replace("\\", "-").split()).strip(". ")
    if not nombre:
        raise ValueError("El nombre no puede quedar vacío.")
    if not es_del_usuario(fondo):
        raise PermissionError("Solo se pueden renombrar los fondos de su carpeta personal.")
    destino = fondo.ruta.with_name(nombre + fondo.ruta.suffix)
    if destino == fondo.ruta:
        return fondo
    if destino.exists():
        raise FileExistsError(f"Ya hay un fondo llamado «{destino.name}».")
    fondo.ruta.rename(destino)
    return Fondo(destino, fondo.grupo)

"""Lectura de archivos de cursor en formato Xcursor (los de la carpeta cursors/ de un tema)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

MAGIA = b"Xcur"
TIPO_IMAGEN = 0xFFFD0002
MAX_LADO = 1024          # protección ante archivos dañados
MAX_IMAGENES = 2000


@dataclass
class Imagen:
    """Un cuadro de un cursor. `pixeles` son ARGB premultiplicado, 4 bytes por píxel (orden little-endian)."""

    tamano: int          # tamaño nominal (24, 32, 48…)
    ancho: int
    alto: int
    x_activo: int        # punto activo (hotspot)
    y_activo: int
    retardo: int         # milisegundos hasta el siguiente cuadro (animados)
    pixeles: bytes


class NoEsCursor(ValueError):
    pass


def leer(ruta: str | Path) -> list[Imagen]:
    return leer_bytes(Path(ruta).read_bytes())


def leer_bytes(datos: bytes) -> list[Imagen]:
    if len(datos) < 16 or datos[:4] != MAGIA:
        raise NoEsCursor("No es un archivo Xcursor")
    tam_cab, _version, n = struct.unpack_from("<III", datos, 4)
    if n > MAX_IMAGENES:
        raise NoEsCursor("Demasiadas entradas")
    imagenes = []
    for i in range(n):
        pos_toc = tam_cab + i * 12
        if pos_toc + 12 > len(datos):
            break
        tipo, _subtipo, pos = struct.unpack_from("<III", datos, pos_toc)
        if tipo != TIPO_IMAGEN or pos + 36 > len(datos):
            continue
        _cab, tipo2, tamano, _ver, ancho, alto, xh, yh, retardo = struct.unpack_from("<IIIIIIIII", datos, pos)
        if tipo2 != TIPO_IMAGEN or not (0 < ancho <= MAX_LADO and 0 < alto <= MAX_LADO):
            continue
        inicio = pos + 36
        fin = inicio + ancho * alto * 4
        if fin > len(datos):
            continue
        imagenes.append(Imagen(tamano, ancho, alto, min(xh, ancho - 1), min(yh, alto - 1), retardo,
                               datos[inicio:fin]))
    if not imagenes:
        raise NoEsCursor("El cursor no tiene imágenes")
    return imagenes


def tamanos(imagenes: list[Imagen]) -> list[int]:
    return sorted({i.tamano for i in imagenes})


def cuadros(imagenes: list[Imagen], tamano: int) -> list[Imagen]:
    """Los cuadros del tamaño nominal más cercano al pedido (varios si el cursor es animado)."""
    disponibles = tamanos(imagenes)
    elegido = min(disponibles, key=lambda t: (abs(t - tamano), -t))
    return [i for i in imagenes if i.tamano == elegido]


def escribir(imagenes: list[Imagen]) -> bytes:
    """Genera un archivo Xcursor (se usa en las pruebas)."""
    n = len(imagenes)
    cab = MAGIA + struct.pack("<III", 16, 0x10000, n)
    toc = b""
    cuerpo = b""
    pos = 16 + 12 * n
    for im in imagenes:
        toc += struct.pack("<III", TIPO_IMAGEN, im.tamano, pos)
        trozo = struct.pack("<IIIIIIIII", 36, TIPO_IMAGEN, im.tamano, 1, im.ancho, im.alto, im.x_activo,
                            im.y_activo, im.retardo) + im.pixeles
        cuerpo += trozo
        pos += len(trozo)
    return cab + toc + cuerpo

import os
from pathlib import Path

import pytest

from temasapp import xcursor


def cursor_bytes(tamanos=(24, 32), cuadros=1) -> bytes:
    imgs = []
    for t in tamanos:
        for c in range(cuadros):
            pix = bytes([0x80 + c, 0x10, 0x20, 0xFF]) * (t * t)
            imgs.append(xcursor.Imagen(t, t, t, 1, 2, 40, pix))
    return xcursor.escribir(imgs)


def crear_tema_cursores(base: Path, nombre="CursorPrueba") -> Path:
    c = base / nombre / "cursors"
    c.mkdir(parents=True)
    (c / "left_ptr").write_bytes(cursor_bytes())
    (c / "watch").write_bytes(cursor_bytes(cuadros=3))
    os.symlink("left_ptr", c / "default")
    os.symlink("left_ptr", c / "arrow")
    (base / nombre / "index.theme").write_text(f"[Icon Theme]\nName={nombre}\nComment=Prueba\nInherits=Adwaita\n")
    return base / nombre


SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><rect width="48" height="48" fill="#39f"/></svg>'


def crear_tema_iconos(base: Path, nombre="IconosPrueba") -> Path:
    raiz = base / nombre
    for d in ("places/48", "places/scalable", "mimes/16"):
        (raiz / d).mkdir(parents=True)
    (raiz / "places/48/folder.svg").write_text(SVG)
    (raiz / "places/scalable/user-home.svg").write_text(SVG)
    (raiz / "mimes/16/text-x-generic.svg").write_text(SVG)
    (raiz / "index.theme").write_text(
        f"[Icon Theme]\nName={nombre}\nInherits=hicolor\nDirectories=places/48,places/scalable,mimes/16,falta/32\n\n"
        "[places/48]\nSize=48\nContext=Places\nType=Fixed\n\n"
        "[places/scalable]\nSize=48\nMinSize=8\nMaxSize=512\nType=Scalable\n\n"
        "[mimes/16]\nSize=16\nType=Fixed\n\n[falta/32]\nSize=32\n")
    return raiz


@pytest.fixture
def casa(tmp_path, monkeypatch):
    """HOME y carpetas XDG falsas: las pruebas nunca tocan los temas reales."""
    h = tmp_path / "casa"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("XDG_DATA_HOME", str(h / ".local/share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(h / ".config"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "sistema"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: h))
    return h

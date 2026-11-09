import io
import json
import os
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest
from conftest import crear_tema_cursores, crear_tema_iconos, cursor_bytes

from temasapp import archivos, escritorio, xcursor
from temasapp.temas import buscar_temas, tema_en, temas_instalados


# --- Xcursor ---------------------------------------------------------------------------------
def test_xcursor_lee_tamanos_y_cuadros():
    imgs = xcursor.leer_bytes(cursor_bytes((24, 32, 48), cuadros=2))
    assert xcursor.tamanos(imgs) == [24, 32, 48]
    c = xcursor.cuadros(imgs, 36)
    assert len(c) == 2 and c[0].tamano == 32 and (c[0].x_activo, c[0].y_activo) == (1, 2)
    assert len(c[0].pixeles) == 32 * 32 * 4


def test_xcursor_rechaza_basura():
    with pytest.raises(xcursor.NoEsCursor):
        xcursor.leer_bytes(b"PNG nada que ver")
    dañado = cursor_bytes()[:60]   # cortado: sin imágenes completas
    with pytest.raises(xcursor.NoEsCursor):
        xcursor.leer_bytes(dañado)


# --- detección ---------------------------------------------------------------------------------
def test_detecta_cursores_e_iconos(tmp_path):
    crear_tema_cursores(tmp_path / "paquete" / "a")
    crear_tema_iconos(tmp_path / "paquete")
    temas = {t.id: t for t in buscar_temas(tmp_path / "paquete")}
    assert set(temas) == {"CursorPrueba", "IconosPrueba"}
    cur, ico = temas["CursorPrueba"], temas["IconosPrueba"]
    assert cur.tiene_cursores and not cur.tiene_iconos and cur.hereda == ["Adwaita"]
    assert cur.archivo_cursor(("no-existe", "default")).name == "default"   # enlace simbólico
    assert ico.tiene_iconos and not ico.tiene_cursores
    assert [d[0] for d in ico.directorios] == ["places/48", "places/scalable", "mimes/16"]  # 'falta/32' no existe
    assert ico.archivo_icono(("folder",)).name == "folder.svg"
    assert ico.archivo_icono(("user-home",)).parent.name == "scalable"
    assert ico.archivo_icono(("text-x-generic",)) is not None
    assert ico.archivo_icono(("inexistente",)) is None


def test_carpeta_sin_tema(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "index.theme").write_text("[Icon Theme]\nName=Vacío\n")
    assert tema_en(tmp_path / "x") is None
    assert buscar_temas(tmp_path) == []


# --- paquetes ---------------------------------------------------------------------------------
def _zip_con_enlaces(ruta: Path, extra=()):
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("Tema/index.theme", "[Icon Theme]\nName=Tema\n")
        z.writestr("Tema/cursors/left_ptr", cursor_bytes())
        enlace = zipfile.ZipInfo("Tema/cursors/default")
        enlace.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(enlace, "left_ptr")
        malo = zipfile.ZipInfo("Tema/cursors/escapa")
        malo.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(malo, "../../../../etc/passwd")
        for nombre, datos in extra:
            z.writestr(nombre, datos)


def test_zip_con_enlaces_simbolicos(tmp_path):
    _zip_con_enlaces(tmp_path / "t.zip")
    carpeta = archivos.preparar(tmp_path / "t.zip", tmp_path)
    tema = buscar_temas(carpeta)[0]
    assert (tema.carpeta / "cursors" / "default").is_symlink()
    assert tema.archivo_cursor(("default",)) is not None
    assert not (tema.carpeta / "cursors" / "escapa").exists()   # enlace que sale del paquete: se omite


def test_zip_slip_rechazado(tmp_path):
    with zipfile.ZipFile(tmp_path / "malo.zip", "w") as z:
        z.writestr("../../fuera.txt", "x")
    with pytest.raises(archivos.ErrorPaquete):
        archivos.preparar(tmp_path / "malo.zip", tmp_path)
    assert not (tmp_path.parent / "fuera.txt").exists()


def test_tar_con_paquetes_adentro(tmp_path):
    # un .tar.xz por variante, todos dentro de un .zip (como muchos paquetes de gnome-look)
    internos = []
    for nombre in ("Variante-Clara", "Variante-Oscura"):
        crear_tema_cursores(tmp_path / "src", nombre)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:xz") as t:
            t.add(tmp_path / "src" / nombre, arcname=nombre)
        internos.append((f"{nombre}.tar.xz", buf.getvalue()))
    with zipfile.ZipFile(tmp_path / "todo.zip", "w") as z:
        for n, d in internos:
            z.writestr(n, d)
        z.writestr("LEEME.txt", "hola")
    carpeta = archivos.preparar(tmp_path / "todo.zip", tmp_path)
    assert sorted(t.id for t in buscar_temas(carpeta, 5)) == ["Variante-Clara", "Variante-Oscura"]


def test_tar_enlace_absoluto_omitido(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        datos = cursor_bytes()
        info = tarfile.TarInfo("T/cursors/left_ptr")
        info.size = len(datos)
        t.addfile(info, io.BytesIO(datos))
        malo = tarfile.TarInfo("T/cursors/hand2")
        malo.type, malo.linkname = tarfile.SYMTYPE, "/etc/passwd"
        t.addfile(malo)
        bueno = tarfile.TarInfo("T/cursors/arrow")
        bueno.type, bueno.linkname = tarfile.SYMTYPE, "left_ptr"
        t.addfile(bueno)
    (tmp_path / "t.tar.gz").write_bytes(buf.getvalue())
    carpeta = archivos.preparar(tmp_path / "t.tar.gz", tmp_path)
    cursores = carpeta / "T" / "cursors"
    assert (cursores / "arrow").is_symlink() and not (cursores / "hand2").exists()


def test_archivo_no_compatible(tmp_path):
    (tmp_path / "x.rar").write_bytes(b"Rar!\x1a\x07")
    with pytest.raises(archivos.ErrorPaquete, match="rar"):
        archivos.preparar(tmp_path / "x.rar", tmp_path)


# --- enlaces ---------------------------------------------------------------------------------
def test_enlace_gnome_look(monkeypatch):
    pedidos = []

    def falso(url, limite=0):
        pedidos.append(url)
        return json.dumps({"status": "ok", "data": [{
            "downloadname1": "Tema-Windows.zip", "downloadlink1": "https://f/1", "downloadsize1": "100",
            "downloadname2": "Tema.tar.xz", "downloadlink2": "https://f/2", "downloadsize2": "2048"}]}).encode()

    monkeypatch.setattr(archivos, "_get", falso)
    lista = archivos.archivos_del_enlace("https://www.gnome-look.org/p/1197198")
    assert "1197198" in pedidos[0]
    orden = archivos.ordenar_para_elegir(lista)
    assert [a.nombre for a in orden] == ["Tema.tar.xz", "Tema-Windows.zip"]
    assert orden[0].tamano == 2048 * 1024 and orden[1].parece_windows
    assert archivos.archivos_del_enlace("https://www.pling.com/s/Gnome/p/55")[0].url == "https://f/1"


def test_enlace_directo():
    a = archivos.archivos_del_enlace("https://ejemplo.com/descargas/Mi%20Tema.tar.gz")
    assert a[0].nombre == "Mi Tema.tar.gz"
    with pytest.raises(archivos.ErrorPaquete):
        archivos.archivos_del_enlace("ftp://algo")


# --- instalar y aplicar -------------------------------------------------------------------------
class Registro:
    def __init__(self, valores=None):
        self.cmds, self.valores = [], valores or {}

    def __call__(self, cmd):
        self.cmds.append(cmd)
        if cmd[:2] == ["gsettings", "get"]:
            return f"'{self.valores.get(cmd[3], '')}'" if cmd[3] != "cursor-size" else str(self.valores.get(cmd[3], 24))
        if cmd[:2] == ["gsettings", "set"]:
            self.valores[cmd[3]] = cmd[4]
        return ""


def test_instalar_aplicar_y_restaurar(casa, tmp_path):
    origen = crear_tema_cursores(tmp_path / "paquete")
    tema = buscar_temas(origen)[0]
    instalado = escritorio.instalar(tema)
    assert instalado.carpeta == casa / ".local/share/icons/CursorPrueba"
    assert (instalado.carpeta / "cursors" / "default").is_symlink()
    with pytest.raises(FileExistsError):
        escritorio.instalar(tema)
    escritorio.instalar(tema, reemplazar=True)

    reg = Registro({"cursor-theme": "Adwaita", "cursor-size": 24, "icon-theme": "Yaru"})
    e = escritorio.Escritorio("gnome", reg)
    e.aplicar_cursor("CursorPrueba", 48)
    assert ["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", "CursorPrueba"] in reg.cmds
    assert ["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", "48"] in reg.cmds
    assert "Inherits=CursorPrueba" in (casa / ".icons/default/index.theme").read_text()
    e.aplicar_cursor("Otro", 32)          # el original guardado sigue siendo Adwaita
    assert e.anterior()["cursor"] == "Adwaita"
    assert "Adwaita" in e.restaurar()
    assert reg.valores["cursor-theme"] == "Adwaita" and reg.valores["cursor-size"] == "24"
    assert e.anterior() == {}

    assert any(t.id == "CursorPrueba" for t in temas_instalados())
    instalado = [t for t in temas_instalados() if t.id == "CursorPrueba"][0]
    assert escritorio.es_del_usuario(instalado)
    escritorio.desinstalar(instalado)
    assert not instalado.carpeta.exists()


def test_no_elimina_temas_del_sistema(casa, tmp_path):
    crear_tema_iconos(tmp_path / "sistema" / "icons", "DelSistema")
    t = [t for t in temas_instalados() if t.id == "DelSistema"][0]
    assert not escritorio.es_del_usuario(t)
    with pytest.raises(PermissionError):
        escritorio.desinstalar(t)


@pytest.mark.parametrize("entorno,esperado", [
    ("cinnamon", ["gsettings", "set", "org.cinnamon.desktop.interface", "icon-theme", "X"]),
    ("mate", ["gsettings", "set", "org.mate.interface", "icon-theme", "X"]),
    ("xfce", ["xfconf-query", "-c", "xsettings", "-p", "/Net/IconThemeName", "-n", "-t", "string", "-s", "X"]),
    ("gnome", ["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", "X"]),
])
def test_comandos_por_escritorio(entorno, esperado):
    assert escritorio.Escritorio(entorno, Registro()).comandos_iconos("X") == [esperado]


def test_detectar_entorno(monkeypatch):
    for valor, esperado in (("zorin:GNOME", "gnome"), ("X-Cinnamon", "cinnamon"), ("XFCE", "xfce"),
                            ("KDE", "kde"), ("MATE", "mate"), ("", "otro")):
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", valor)
        monkeypatch.setenv("DESKTOP_SESSION", "")
        monkeypatch.setenv("XDG_SESSION_DESKTOP", "")
        assert escritorio.detectar_entorno() == esperado


def test_paginas_de_temas():
    from temasapp.ui.navegador import SITIOS, es_pagina_de_tema

    assert es_pagina_de_tema("https://www.gnome-look.org/p/1197198")
    assert es_pagina_de_tema("https://www.pling.com/s/Gnome/p/55/")
    assert es_pagina_de_tema("https://github.com/ful1e5/Bibata_Cursor")
    assert not es_pagina_de_tema("https://www.gnome-look.org/browse?cat=107&ord=rating")
    assert [s for s, _ in SITIOS] == ["Cursores", "Iconos", "Fondos de pantalla"]
    assert all(u.startswith("https://") for _s, lista in SITIOS for _t, u in lista)


def test_url_con_espacios_y_tildes():
    u = archivos.url_segura("https://files.pling.com/api/files/download/j/abc.def/1440P No Logo G477.jpg")
    assert u == "https://files.pling.com/api/files/download/j/abc.def/1440P%20No%20Logo%20G477.jpg"
    assert archivos.url_segura("https://x.org/a%20b/Montaña.png?n=1 2") == "https://x.org/a%20b/Monta%C3%B1a.png?n=1%202"
    assert archivos.url_segura("https://x.org/ya/bien.zip") == "https://x.org/ya/bien.zip"


# --- programas del sistema desde el .deb -------------------------------------------------------
def test_entorno_sistema_quita_las_librerias_del_paquete(monkeypatch):
    monkeypatch.setattr(escritorio.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/estilo-agil/_internal")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    assert "LD_LIBRARY_PATH" not in escritorio.entorno_sistema()
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/mis/libs")
    env = escritorio.entorno_sistema()
    assert env["LD_LIBRARY_PATH"] == "/mis/libs" and "LD_LIBRARY_PATH_ORIG" not in env


def test_entorno_sistema_no_toca_nada_fuera_del_paquete(monkeypatch):
    monkeypatch.delattr(escritorio.sys, "frozen", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/mis/libs")
    assert escritorio.entorno_sistema()["LD_LIBRARY_PATH"] == "/mis/libs"

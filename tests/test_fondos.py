import os
import shutil

import pytest
from conftest import crear_tema_iconos

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QColor, QImage  # noqa: E402

from temasapp import escritorio, fondos  # noqa: E402
from test_nucleo import Registro  # noqa: E402


def imagen(ruta, ancho=1600, alto=900, color="#3366aa"):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img = QImage(ancho, alto, QImage.Format_RGB32)
    img.fill(QColor(color))
    assert img.save(str(ruta))
    return ruta


def test_buscar_fondos_en_paquete(tmp_path):
    imagen(tmp_path / "pack" / "Coleccion-Mar" / "ola.png")
    imagen(tmp_path / "pack" / "Coleccion-Mar" / "playa.jpg")
    imagen(tmp_path / "pack" / "suelto.png")
    imagen(tmp_path / "pack" / "miniatura.png", 200, 120)            # muy chica: no es fondo
    tema = crear_tema_iconos(tmp_path / "pack")
    imagen(tema / "places" / "48" / "grande.png", 1200, 1200)       # dentro de un tema: se ignora
    encontrados = fondos.buscar_fondos(tmp_path / "pack", excluir=[tema])
    assert sorted(f.ruta.name for f in encontrados) == ["ola.png", "playa.jpg", "suelto.png"]
    grupos = {g: [f.ruta.name for f in m] for g, m in fondos.agrupar(encontrados)}
    assert grupos["Coleccion Mar"] == ["ola.png", "playa.jpg"]
    assert next(f for f in encontrados if f.ruta.name == "suelto.png").grupo is None


def test_instalar_aplicar_y_restaurar_fondo(casa, tmp_path):
    original = imagen(tmp_path / "sistema" / "backgrounds" / "Original.jpg")
    nuevo = fondos.Fondo(imagen(tmp_path / "descarga" / "Montaña azul.png"))
    assert nuevo.titulo == "Montaña azul"
    instalado = fondos.instalar(nuevo)
    assert instalado.ruta == casa / ".local/share/backgrounds/Montaña azul.png"
    assert fondos.es_del_usuario(instalado)
    with pytest.raises(FileExistsError):
        fondos.instalar(nuevo)
    ids = {f.id for f in fondos.fondos_instalados()}
    assert {str(instalado.ruta), str(original)} <= ids

    reg = Registro({"picture-uri": original.as_uri(), "picture-uri-dark": original.as_uri(), "picture-options": "zoom"})
    e = escritorio.Escritorio("gnome", reg)
    assert e.actual().fondo == str(original)
    e.aplicar_fondo(str(instalado.ruta), "scaled", bloqueo=True)
    uri = instalado.ruta.as_uri()
    assert ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri] in reg.cmds
    assert ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri] in reg.cmds
    assert ["gsettings", "set", "org.gnome.desktop.screensaver", "picture-uri", uri] in reg.cmds
    assert reg.valores["picture-options"] == "scaled"
    assert "Original.jpg" in e.restaurar()
    assert reg.valores["picture-uri"] == original.as_uri() and reg.valores["picture-options"] == "zoom"

    fondos.desinstalar(instalado)
    assert not instalado.ruta.exists()
    with pytest.raises(PermissionError):
        fondos.desinstalar(fondos.Fondo(original))


def test_pestana_fondos(casa, tmp_path):
    from PySide6.QtWidgets import QApplication

    from test_interfaz import _esperar
    from temasapp.ui.ventana import VentanaPrincipal

    app = QApplication.instance() or QApplication([])
    imagen(tmp_path / "src" / "Paisajes" / "lago.png")
    imagen(tmp_path / "src" / "Paisajes" / "bosque.png")
    shutil.make_archive(str(tmp_path / "fondos"), "zip", tmp_path / "src")
    suelta = imagen(tmp_path / "foto.jpg", 1920, 1080, "#aa3300")
    reg = Registro({"cursor-theme": "x", "icon-theme": "y"})
    w = VentanaPrincipal(escritorio.Escritorio("gnome", reg))
    w.cargar_varios([tmp_path / "fondos.zip", suelta])
    _esperar(app, w)
    assert w.tipo_actual() == "fondos"
    assert sorted(t.ruta.name for t in w.paquete) == ["bosque.png", "foto.jpg", "lago.png"]
    assert w.b_aplicar.text() == "Poner de fondo de pantalla" and w.c_ajuste.isVisibleTo(w)
    assert w.elegir_tema(str(suelta), True)
    app.processEvents()
    w.c_ajuste.setCurrentIndex(w.c_ajuste.findData("centered"))
    w.aplicar()
    instalada = casa / ".local/share/backgrounds/foto.jpg"
    assert instalada.exists()
    assert reg.valores["picture-uri"] == instalada.as_uri() and reg.valores["picture-options"] == "centered"
    assert w.elegido()[0].id == str(instalada) and not w.elegido()[1]   # ahora está en «Instalados por usted»
    w.close()

import os
import time

import pytest
from conftest import crear_tema_cursores, crear_tema_iconos

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from temasapp import escritorio  # noqa: E402
from temasapp.ui.ventana import VentanaPrincipal  # noqa: E402
from test_nucleo import Registro  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _esperar(app, w):
    for _ in range(200):
        app.processEvents()
        if not w.ocupado:
            return
        time.sleep(0.02)


def test_cargar_ver_y_aplicar(app, casa, tmp_path):
    import shutil
    crear_tema_cursores(tmp_path / "src")
    crear_tema_iconos(tmp_path / "src")
    shutil.make_archive(str(tmp_path / "paquete"), "zip", tmp_path / "src")
    reg = Registro({"cursor-theme": "Adwaita", "icon-theme": "Yaru"})
    w = VentanaPrincipal(escritorio.Escritorio("gnome", reg))
    w.show()
    w.cargar(tmp_path / "paquete.zip")
    _esperar(app, w)
    assert w.pestanas.currentIndex() == 0          # pestaña Cursores
    tema, nuevo = w.elegido()
    assert tema.id == "CursorPrueba" and nuevo     # el nuevo queda elegido arriba, en «Nuevos»
    assert "IconosPrueba" in w.ids_en_lista("iconos")
    assert "CursorPrueba" not in w.ids_en_lista("iconos")   # cada tema solo en su pestaña
    assert w.b_aplicar.isEnabled() and w.b_aplicar.text() == "Aplicar este cursor"
    w.aplicar()
    assert (casa / ".local/share/icons/CursorPrueba/cursors/left_ptr").exists()
    assert reg.valores["cursor-theme"] == "CursorPrueba"
    assert w.b_original.isEnabled()
    tema, nuevo = w.elegido()
    assert tema.id == "CursorPrueba" and not nuevo  # ya instalado y en uso
    w.pestanas.setCurrentIndex(1)
    app.processEvents()
    assert w.elegido()[0].id == "IconosPrueba" and w.b_aplicar.text() == "Aplicar estos iconos"
    assert not w.c_tamano.isVisible()
    w.close()


def test_eliminar_ocultar_y_quitar(app, casa, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    crear_tema_cursores(tmp_path / "sistema" / "icons", "DelSistema")
    crear_tema_cursores(casa / ".local/share/icons", "Mio")
    reg = Registro({"cursor-theme": "OtroEnUso", "icon-theme": "Yaru"})
    w = VentanaPrincipal(escritorio.Escritorio("gnome", reg))

    def elegir(id_):
        assert w.elegir_tema(id_), id_
        app.processEvents()

    def ids():
        return w.ids_en_lista("cursores")

    # del sistema: se oculta, no se borra
    elegir("DelSistema")
    assert w.b_eliminar.text() == "Ocultar" and w.b_eliminar.isEnabled()
    w.eliminar()
    assert "DelSistema" not in ids() and (tmp_path / "sistema/icons/DelSistema").exists()
    w.c_ocultos.setChecked(True)
    assert "DelSistema" in ids()
    elegir("DelSistema")
    assert w.b_eliminar.text() == "Volver a mostrar"
    w.eliminar()
    w.c_ocultos.setChecked(False)
    assert "DelSistema" in ids()

    # de la carpeta personal: se elimina (con confirmación)
    elegir("Mio")
    assert w.b_eliminar.text() == "Eliminar"
    monkeypatch.setattr(QMessageBox, "exec", lambda self: self.buttons()[0].click() or 0)
    w.eliminar()
    assert "Mio" not in ids() and not (casa / ".local/share/icons/Mio").exists()
    w.close()


def test_favoritos(app, casa, tmp_path):
    import shutil
    crear_tema_cursores(casa / ".local/share/icons", "Uno")
    crear_tema_cursores(casa / ".local/share/icons", "Dos")
    crear_tema_cursores(tmp_path / "src", "NuevoFav")
    shutil.make_archive(str(tmp_path / "p"), "zip", tmp_path / "src")
    w = VentanaPrincipal(escritorio.Escritorio("gnome", Registro({"cursor-theme": "Uno"})))
    lista = w.listas["cursores"]

    def secciones():
        return {lista.topLevelItem(i).text(0).split("  (")[0]: lista.topLevelItem(i)
                for i in range(lista.topLevelItemCount())}

    def en_seccion(nombre):
        return [i.data(0, 0x0100)[0].id for i in w.items_de_temas(lista)
                if i.parent() is secciones()[nombre] or (i.parent() and i.parent().parent() is secciones()[nombre])]

    def elegir(id_):
        assert w.elegir_tema(id_)
        app.processEvents()

    assert "★ FAVORITOS" not in secciones()
    elegir("Dos")
    assert w.b_favorito.text() == "☆ Agregar a favoritos"
    w.cambiar_favorito()
    assert en_seccion("★ FAVORITOS") == ["Dos"] and w.elegido()[0].id == "Dos"
    assert en_seccion("INSTALADOS POR USTED") == ["Dos", "Uno"]          # sigue también en su sección
    assert w.seccion_de(lista.currentItem()) == "INSTALADOS POR USTED"     # y la selección no salta
    marcado = [i for i in w.items_de_temas(lista) if i.data(0, 0x0100)[0].id == "Dos"]
    assert len(marcado) == 2 and all(i.text(0).startswith("★ Dos") for i in marcado)
    assert w.b_favorito.isChecked() and w.b_favorito.text() == "★ En favoritos"
    assert escritorio.favoritos()["cursores"] == ["Dos"]
    # un tema nuevo: al marcarlo como favorito se instala (sin aplicarlo)
    w.cargar(tmp_path / "p.zip")
    _esperar(app, w)
    assert w.elegido() [0].id == "NuevoFav" and w.elegido()[1]
    w.cambiar_favorito()
    assert (casa / ".local/share/icons/NuevoFav").exists()
    assert en_seccion("★ FAVORITOS") == ["Dos", "NuevoFav"]
    assert w.escritorio.actual().cursor == "Uno"          # no se aplicó
    elegir("Dos")
    w.cambiar_favorito()                                 # quitar
    assert escritorio.favoritos()["cursores"] == ["NuevoFav"]
    w.close()



def test_grupos_y_varios_archivos(app, casa, tmp_path):
    import shutil
    for n in ("Bibata-Modern-Ice", "Bibata-Original-Amber", "Solo"):
        crear_tema_cursores(casa / ".local/share/icons", n)
    for n in ("ZorinBlue-Dark", "Zorin", "ZorinRed-Light"):
        crear_tema_iconos(tmp_path / "sistema" / "icons", n)
    paquetes = []
    for n in ("Variante-A", "Variante-B"):
        crear_tema_cursores(tmp_path / f"src{n}", n)
        paquetes.append(shutil.make_archive(str(tmp_path / n), "zip", tmp_path / f"src{n}"))
    w = VentanaPrincipal(escritorio.Escritorio("gnome", Registro({"cursor-theme": "Solo", "icon-theme": "x"})))
    cur = w.listas["cursores"]
    secc = {cur.topLevelItem(i).text(0).split("  (")[0]: cur.topLevelItem(i) for i in range(cur.topLevelItemCount())}
    usted = secc["INSTALADOS POR USTED"]
    grupo = next(usted.child(i) for i in range(usted.childCount()) if usted.child(i).childCount())
    assert grupo.text(0).startswith("Bibata  (2 variantes)")
    ico = w.listas["iconos"]
    sistema = ico.topLevelItem(0)
    assert sistema.text(0).startswith("DEL SISTEMA") and sistema.child(0).text(0).startswith("Zorin  (3 variantes)")
    # elegir el grupo muestra su primera variante
    cur.setCurrentItem(grupo)
    for _ in range(5):
        app.processEvents()
    assert w.elegido()[0].id.startswith("Bibata")
    # varios archivos a la vez: todos quedan en «Nuevos»
    w.cargar_varios(paquetes)
    _esperar(app, w)
    nuevos = cur.topLevelItem(0)
    assert nuevos.text(0).startswith("NUEVOS")
    assert sorted(i.data(0, 0x0100)[0].id for i in w.items_de_temas(cur) if i.data(0, 0x0100)[1]) == \
        ["Variante-A", "Variante-B"]
    assert w.elegido()[1]
    w.close()


def test_dialogo_varios_archivos(app):
    from temasapp.archivos import ArchivoRemoto
    from temasapp.ui.ventana import DialogoArchivos

    d = DialogoArchivos([ArchivoRemoto("A.tar.xz", "u1"), ArchivoRemoto("B.tar.gz", "u2"),
                         ArchivoRemoto("C-Windows.zip", "u3"), ArchivoRemoto("LEEME", "u4")])
    assert [a.nombre for a in d.elegidos()] == ["A.tar.xz", "B.tar.gz"]   # los de Linux, marcados
    assert d.b_ok.text() == "Descargar 2 archivo(s)"
    d._marcar(False)
    assert d.elegidos() == [] and not d.b_ok.isEnabled()


def test_marcar_instalar_y_descartar(app, casa, tmp_path):
    import shutil
    from PySide6.QtCore import Qt
    for n in ("Pack-Rojo", "Pack-Azul", "Pack-Verde", "Otro"):
        crear_tema_cursores(tmp_path / "src", n)
    shutil.make_archive(str(tmp_path / "p"), "zip", tmp_path / "src")
    w = VentanaPrincipal(escritorio.Escritorio("gnome", Registro({"cursor-theme": "x"})))
    w.cargar(tmp_path / "p.zip")
    _esperar(app, w)
    cur = w.listas["cursores"]
    nuevos = cur.topLevelItem(0)
    assert nuevos.text(0).startswith("NUEVOS") and nuevos.flags() & Qt.ItemIsUserCheckable
    assert not w.b_instalar_marcados.isEnabled() and w.barra_nuevos.isVisibleTo(w)
    items = {i.data(0, Qt.UserRole)[0].id: i for i in w.items_de_temas(cur)}
    grupo = items["Pack-Rojo"].parent()
    assert grupo.text(0).startswith("Pack  (3 variantes)")
    grupo.setCheckState(0, Qt.Checked)            # marcar el grupo marca sus 3 variantes
    app.processEvents()
    assert w.marcados == {"Pack-Rojo", "Pack-Azul", "Pack-Verde"}
    items["Pack-Azul"].setCheckState(0, Qt.Unchecked)
    assert w.b_instalar_marcados.text() == "Agregar marcados (2)"
    w.instalar_marcados()
    icons = casa / ".local/share/icons"
    assert (icons / "Pack-Rojo").exists() and (icons / "Pack-Verde").exists() and not (icons / "Pack-Azul").exists()
    assert sorted(t.id for t in w.paquete) == ["Otro", "Pack-Azul"]
    assert w.escritorio.actual().cursor == "x"     # no se aplicó nada
    # tirar los que quedan en «Nuevos»
    w.descartar("todos")
    assert w.paquete == [] and not w.barra_nuevos.isVisibleTo(w)
    assert {"Pack-Rojo", "Pack-Verde"} <= set(w.ids_en_lista("cursores"))
    w.close()


def test_abrir_carpeta_contenedora(app, casa, tmp_path, monkeypatch):
    from temasapp.ui import ventana as modulo
    crear_tema_cursores(casa / ".local/share/icons", "Guardado")
    abiertas = []
    monkeypatch.setattr(modulo, "mostrar_en_carpeta", lambda ruta: abiertas.append(ruta))
    w = VentanaPrincipal(escritorio.Escritorio("gnome", Registro({"cursor-theme": "Guardado"})))
    assert w.elegir_tema("Guardado")
    app.processEvents()
    assert w.b_carpeta.isEnabled()
    w.abrir_carpeta()
    assert abiertas == [casa / ".local/share/icons/Guardado"]
    w.close()


def test_usar_solo_el_tamano(app, casa):
    crear_tema_cursores(casa / ".local/share/icons", "MiCursor")
    reg = Registro({"cursor-theme": "MiCursor", "cursor-size": 24})
    w = VentanaPrincipal(escritorio.Escritorio("gnome", reg))
    assert w.b_tamano.isVisibleTo(w) and not w.b_tamano.isEnabled()      # 24 = el actual
    w.c_tamano.setCurrentIndex(w.c_tamano.findData(40))
    assert w.b_tamano.isEnabled()
    w.aplicar_tamano()
    assert reg.valores["cursor-size"] == "40" and reg.valores["cursor-theme"] == "MiCursor"
    assert w.c_tamano.currentData() == 40 and "(actual)" in w.c_tamano.currentText()
    assert not w.b_tamano.isEnabled()
    w.pestanas.setCurrentIndex(1)
    assert not w.b_tamano.isVisibleTo(w)
    w.close()


def test_renombrar_con_doble_clic(app, casa, tmp_path):
    from test_fondos import imagen
    crear_tema_cursores(casa / ".local/share/icons", "MiTema")
    crear_tema_cursores(tmp_path / "sistema" / "icons", "DelSistema")
    foto = imagen(casa / ".local/share/backgrounds" / "foto vieja.png")
    reg = Registro({"cursor-theme": "MiTema", "picture-uri": foto.as_uri(), "picture-uri-dark": foto.as_uri()})
    w = VentanaPrincipal(escritorio.Escritorio("gnome", reg))
    lista = w.listas["cursores"]

    def item_de(id_):
        return next(i for i in w.items_de_temas(lista) if i.data(0, 0x0100)[0].id == id_)

    # sin activar la opción, el doble clic no hace nada
    w._doble_clic(lista, item_de("MiTema"))
    assert w.renombrando is None
    w.c_renombrar.setChecked(True)
    w._doble_clic(lista, item_de("DelSistema"))           # del sistema: no se puede
    assert w.renombrando is None
    it = item_de("MiTema")
    w._doble_clic(lista, it)
    assert w.renombrando is not None and it.text(0) == "MiTema"
    it.setText(0, "Mi cursor favorito")
    w._fin_renombrar()
    t = item_de("MiTema").data(0, 0x0100)[0]               # la carpeta no cambia (sigue en uso)
    assert t.titulo == "Mi cursor favorito" and (casa / ".local/share/icons/MiTema").is_dir()
    assert reg.valores["cursor-theme"] == "MiTema"
    # fondo en uso: se renombra el archivo y la configuración apunta al nuevo
    w.pestanas.setCurrentIndex(2)
    lista = w.listas["fondos"]
    it = item_de(str(foto))
    w._doble_clic(lista, it)
    it.setText(0, "Atardecer")
    w._fin_renombrar()
    nueva = casa / ".local/share/backgrounds/Atardecer.png"
    assert nueva.exists() and not foto.exists()
    assert reg.valores["picture-uri"] == nueva.as_uri() and reg.valores["picture-uri-dark"] == nueva.as_uri()
    assert w.elegido()[0].id == str(nueva)
    w.close()

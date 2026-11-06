# Estilo Ágil

Programa para Linux que instala, previsualiza y aplica **cursores**, **iconos** y **fondos de pantalla**.

1. **Arrastre** el `.zip` / `.tar.xz` del tema o las imágenes, **pegue el enlace** de la página
   (gnome-look.org, pling.com, GitHub, Unsplash) o use **«Buscar temas en internet»** (navegador integrado:
   lo que descarga pasa directo a la vista previa).
2. **Vista previa**: los cursores se animan y se prueban al pasar el mouse; los iconos con ejemplos; los fondos
   en grande con su resolución.
3. **Aplicar**: el tema se copia a su carpeta personal (sin clave de administrador) y se activa. Tamaño del cursor,
   ajuste del fondo y pantalla de bloqueo.
4. Secciones Nuevos / Favoritos / Instalados por usted / Del sistema, variantes agrupadas, casillas para agregar
   varios, renombrar, abrir carpeta contenedora y **Volver a los originales**.

Escritorios: GNOME (Zorin, Ubuntu, Pop!_OS, Budgie), Cinnamon, MATE, Xfce y KDE Plasma.

## Instalar

Descargue el `.deb` de la página **Releases** y ábralo con doble clic (o `sudo apt install ./estilo-agil_*.deb`).

## Desarrollo

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/temasapp
.venv/bin/python -m pytest -q
.venv/bin/python empaquetar/construir_deb.py     # instalador .deb en dist/
```

"""Genera las variantes de la Bitácora desde la fuente única bitacora-obra.html.

- bitacora-obra-demo.html : activa MODO_DEMO (para el artifact demo de claude.ai).
- Bitacora de Obra.html   : un solo archivo autocontenido (logos incrustados en base64) para
                            abrir desde disco o enviar por correo; sin claude.ai arranca en modo local.

Ejecutar después de cada cambio a la Bitácora:  python generar_demo.py
"""
import base64
import pathlib

AQUI = pathlib.Path(__file__).resolve().parent
fuente = (AQUI / 'bitacora-obra.html').read_text(encoding='utf-8')
marca = 'var MODO_DEMO = false;'
if fuente.count(marca) != 1:
    raise SystemExit('No se encontró exactamente una vez la marca MODO_DEMO en la fuente.')
demo = fuente.replace(marca, 'var MODO_DEMO = true;').replace('<title>Bitácora de Obra</title>', '<title>Bitácora de Obra (demo)</title>', 1)
(AQUI / 'bitacora-obra-demo.html').write_text(demo, encoding='utf-8')
print('OK: bitacora-obra-demo.html generado')

local = fuente
for logo in ('logo-dgc-color.png', 'logo-dgc-blanco.png'):
    ref = 'src="assets/' + logo + '"'
    if ref not in local:
        raise SystemExit('No se encontró la referencia a ' + logo + ' en la fuente.')
    b64 = base64.b64encode((AQUI / 'assets' / logo).read_bytes()).decode('ascii')
    local = local.replace(ref, 'src="data:image/png;base64,' + b64 + '"')
(AQUI / 'Bitacora de Obra.html').write_text(local, encoding='utf-8')
print('OK: Bitacora de Obra.html generado (autocontenido)')

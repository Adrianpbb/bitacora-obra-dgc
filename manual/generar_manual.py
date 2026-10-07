"""Genera 'Manual de procedimientos - Bitacora de Obra.docx' (Word, editable).

Uso:  python generar_manual.py
Los nombres de pestañas y botones son los de la pantalla (frontend/bitacora-obra.html, v10.15).
Si cambia la pantalla, se cambia aquí y se vuelve a generar.
"""
import pathlib
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.shared import Cm, Pt, RGBColor
from PIL import Image
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'bizagi'))
import generar_bpmn as bz
from bpmn_lib import X0

AQUI = pathlib.Path(__file__).resolve().parent
LOGO = AQUI.parent / 'frontend' / 'assets' / 'logo-dgc-color.png'
VERSION = 'v10.17 · 2026-10-07'
AZUL = RGBColor(0x1F, 0x3A, 0x5F)

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.59), Cm(27.94)       # carta
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)

st = doc.styles['Normal']
st.font.name = 'Calibri'
st.font.size = Pt(10.5)
st.element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
st.paragraph_format.space_after = Pt(4)
for nombre, tam in (('Heading 1', 17), ('Heading 2', 13), ('Heading 3', 11)):
    h = doc.styles[nombre]
    h.font.name = 'Calibri'
    h.font.size = Pt(tam)
    h.font.bold = True
    h.font.color.rgb = AZUL
    h.element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    h.paragraph_format.space_before = Pt(14 if nombre == 'Heading 1' else 10)
    h.paragraph_format.space_after = Pt(4)
    h.paragraph_format.keep_with_next = True


def sombrear(celda, hexcolor):
    tcPr = celda._tc.get_or_add_tcPr()
    sh = OxmlElement('w:shd')
    sh.set(qn('w:val'), 'clear'); sh.set(qn('w:color'), 'auto'); sh.set(qn('w:fill'), hexcolor)
    tcPr.append(sh)


def h1(t): doc.add_heading(t, level=1)
def h2(t): doc.add_heading(t, level=2)
def h3(t): doc.add_heading(t, level=3)


def p(texto, negrita=False, cursiva=False, color=None, tam=None, centro=False):
    par = doc.add_paragraph()
    r = par.add_run(texto)
    r.bold, r.italic = negrita, cursiva
    if color: r.font.color.rgb = color
    if tam: r.font.size = Pt(tam)
    if centro: par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return par


def rico(partes, estilo=None, sangria=None):
    """partes: lista de str o (str, 'b') para negrita."""
    par = doc.add_paragraph(style=estilo) if estilo else doc.add_paragraph()
    for x in partes:
        if isinstance(x, tuple):
            r = par.add_run(x[0]); r.bold = True
        else:
            par.add_run(x)
    if sangria is not None:
        par.paragraph_format.left_indent = Cm(sangria)
    return par


def pasos(lista):
    """Pasos numerados a mano (la numeración automática de Word continúa entre listas)."""
    for i, t in enumerate(lista, 1):
        par = doc.add_paragraph()
        par.paragraph_format.left_indent = Cm(0.9)
        par.paragraph_format.first_line_indent = Cm(-0.6)
        par.paragraph_format.space_after = Pt(2)
        r = par.add_run('%d.  ' % i); r.bold = True; r.font.color.rgb = AZUL
        # permite **negrita** simple con asteriscos dobles
        partes = t.split('**')
        for j, tr in enumerate(partes):
            rr = par.add_run(tr); rr.bold = (j % 2 == 1)


def viñetas(lista):
    for t in lista:
        par = doc.add_paragraph(style='List Bullet')
        par.paragraph_format.space_after = Pt(1)
        partes = t.split('**')
        for j, tr in enumerate(partes):
            rr = par.add_run(tr); rr.bold = (j % 2 == 1)


def nota(texto, titulo='Importante'):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    sombrear(c, 'FFF6DB')
    par = c.paragraphs[0]
    r = par.add_run(titulo + ': '); r.bold = True
    par.add_run(texto)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def tabla(cabeceras, filas, anchos=None):
    t = doc.add_table(rows=1, cols=len(cabeceras))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, c in enumerate(cabeceras):
        cel = t.rows[0].cells[i]
        sombrear(cel, '1F3A5F')
        r = cel.paragraphs[0].add_run(c); r.bold = True; r.font.color.rgb = RGBColor(255, 255, 255)
    for fila in filas:
        cel = t.add_row().cells
        for i, v in enumerate(fila):
            partes = str(v).split('**')
            for j, tr in enumerate(partes):
                rr = cel[i].paragraphs[0].add_run(tr); rr.bold = (j % 2 == 1)
    if anchos:
        for row in t.rows:
            for i, w in enumerate(anchos):
                row.cells[i].width = Cm(w)
    for row in t.rows:
        for cel in row.cells:
            for par in cel.paragraphs:
                par.paragraph_format.space_after = Pt(1)
                for r in par.runs:
                    r.font.size = Pt(9.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t



# ---------------- diagramas (hoja horizontal, partidos en dos mitades legibles)
BIZ = AQUI.parent / 'bizagi'
TMP = AQUI / '_tmp'


def _mejor_corte(proc):
    """Columna x (px del SVG) donde partir el diagrama sin cortar elementos y con pocas flechas cruzadas."""
    proc.to_svg()
    W = proc.width + 20
    cajas = []
    for n in proc.nodes:
        mar = 58 if n.kind in ('start', 'end', 'xor', 'and') else 8
        cajas.append((n.x - mar, n.r + mar))
    mejor = None
    for x in range(int(W * 0.36), int(W * 0.64), 4):
        if any(a < x < b for a, b in cajas):
            continue
        cruces = 0
        for f in proc.flows:
            for (x1, y1), (x2, y2) in zip(f.pts, f.pts[1:]):
                if abs(y1 - y2) < 1 and min(x1, x2) < x < max(x1, x2):
                    cruces += 1
        costo = (cruces, abs(x - W / 2))
        if mejor is None or costo < mejor[0]:
            mejor = (costo, x)
    return mejor[1], W


def _seccion(horizontal):
    s = doc.add_section(WD_SECTION.NEW_PAGE)
    if horizontal:
        s.orientation = WD_ORIENT.LANDSCAPE
        s.page_width, s.page_height = Cm(27.94), Cm(21.59)
        s.left_margin = s.right_margin = Cm(1.5)
        s.top_margin, s.bottom_margin = Cm(1.8), Cm(1.6)
    else:
        s.orientation = WD_ORIENT.PORTRAIT
        s.page_width, s.page_height = Cm(21.59), Cm(27.94)
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin, s.bottom_margin = Cm(2.2), Cm(2.0)


def diagrama(archivo, fn, titulo, texto):
    proc = fn()
    x, W = _mejor_corte(proc)
    img = Image.open(BIZ / (archivo + '.png')).convert('RGB')
    k = img.width / W
    TMP.mkdir(exist_ok=True)
    izq = img.crop((0, 0, int(x * k), img.height))
    franja = img.crop((0, 0, int(X0 * k), img.height))
    cola = img.crop((int(x * k), 0, img.width, img.height))
    der = Image.new('RGB', (franja.width + cola.width, img.height), 'white')
    der.paste(franja, (0, 0))
    der.paste(cola, (franja.width, 0))
    piezas = []
    for nombre, im in (('a', izq), ('b', der)):
        ruta = TMP / ('%s_%s.png' % (archivo, nombre))
        im.save(ruta)
        piezas.append((ruta, im))
    ancho_max, alto_max = 24.9, 15.2
    anchos = [min(ancho_max, alto_max * im.width / im.height) for _, im in piezas]
    altos = [anchos[i] * piezas[i][1].height / piezas[i][1].width for i in range(2)]
    juntas = altos[0] + altos[1] + 3.6 <= 18.0
    if not juntas and altos[0] + altos[1] <= 16.0:        # diagramas bajos: las dos mitades caben en una hoja, algo más angostas
        anchos = [min(22.0, a_) for a_ in anchos]
        juntas = True
    _seccion(True)
    h2(titulo)
    p(texto, cursiva=True, tam=9.5)
    for i, (ruta, im) in enumerate(piezas):
        if i == 1 and not juntas:
            doc.add_page_break()
        doc.add_picture(str(ruta), width=Cm(anchos[i]))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        pie = 'Parte %d de 2%s' % (i + 1, ' · el diagrama continúa más abajo' if (i == 0 and juntas) else (' · el diagrama continúa en la página siguiente' if i == 0 else ' · fin del diagrama'))
        p(pie, tam=8.5, color=RGBColor(0x55, 0x65, 0x7A), centro=True)
    _seccion(False)


# ---------------- encabezado / pie
hp = sec.header.paragraphs[0]
hp.text = 'Bitácora de Obra · Manual de procedimientos'
hp.runs[0].font.size = Pt(8.5); hp.runs[0].font.color.rgb = RGBColor(0x55, 0x65, 0x7A)
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr = fp.add_run('Dirección General de Concesiones · División de Construcción · ' + VERSION + ' · Página ')
fr.font.size = Pt(8.5); fr.font.color.rgb = RGBColor(0x55, 0x65, 0x7A)
for tipo, txt in (('begin', None), (None, 'PAGE'), ('end', None)):
    r = fp.add_run(); r.font.size = Pt(8.5)
    if tipo:
        e = OxmlElement('w:fldChar'); e.set(qn('w:fldCharType'), tipo); r._r.append(e)
    else:
        e = OxmlElement('w:instrText'); e.set(qn('xml:space'), 'preserve'); e.text = txt; r._r.append(e)

# ---------------- portada
if LOGO.exists():
    doc.add_picture(str(LOGO), width=Cm(5.2))
p('')
p('Bitácora de Obra', negrita=True, color=AZUL, tam=30)
p('Manual de procedimientos', color=AZUL, tam=18)
p('')
p('Dirección General de Concesiones · División de Construcción · Ministerio de Obras Públicas', tam=11)
p('Versión de la herramienta: ' + VERSION, tam=10, color=RGBColor(0x55, 0x65, 0x7A))
p('')
p('Para quién es: Inspectores Fiscales (IF) y asesorías (AIF), Validadores / Jefes de Departamento, '
  'Administradores del sistema y Gabinete. Cada capítulo explica, paso a paso, qué hace cada perfil, e incluye '
  'los diagramas del flujo de trabajo (BPMN) del proceso que se describe.')
nota('Los nombres de pestañas y botones son los que verás en pantalla. Los diagramas de flujo van en hojas horizontales; '
     'cada uno se divide en dos partes para que se lea bien impreso.', 'Cómo leer este manual')
doc.add_page_break()

# ---------------- 1
h1('1. Qué es y cómo se usa')
p('La Bitácora de Obra permite que cada Inspector Fiscal informe, por contrato, el avance físico, las fechas de los hitos '
  'y las problemáticas de terreno. Lo que informa el IF no es oficial hasta que su jefatura lo aprueba; solo los datos aprobados '
  'aparecen en el dashboard de Gabinete.')
h2('1.1 Perfiles')
tabla(['Perfil', 'Qué hace', 'Pestañas que ve'], [
    ['**IF / AIF**', 'Reporta avance, fechas de hitos y problemáticas de sus contratos (normalmente dos: uno como titular y otro como suplente).',
     'Mis contratos · Cargar avance · Modificar hitos · Mis solicitudes · Problemáticas · Resueltas'],
    ['**Validador / Jefe de Depto.**', 'Revisa las solicitudes de los IF y las aprueba o rechaza. Publica alertas a Gabinete.',
     'Contratos · Bandeja de aprobaciones · Historial · Problemáticas · Resueltas'],
    ['**Administrador**', 'Carga contratos y subsectores, define hitos y pesos, asigna perfiles y contratos. Además hace lo del Validador.',
     'Las del Validador + Gestión de permisos · Configuración · Registro de cambios'],
    ['**Gabinete**', 'Solo consulta. No aprueba ni edita nada. Ve únicamente datos aprobados.', 'Dashboard ejecutivo'],
], [3.6, 7.6, 5.4])
h2('1.2 Ideas que conviene tener claras')
viñetas([
    '**Dato oficial:** el último valor aprobado. Todo lo que ven el semáforo, el radar y Gabinete sale de ahí.',
    '**Solicitud:** cada cambio que propone un IF (un avance o una fecha). Pasa por estados: Borrador → En revisión → Aprobada o Rechazada (o Eliminada si el IF la cancela).',
    '**Contrato, sector y subsector:** cada contrato se divide en sectores (según el tipo: aeródromos, estaciones, cárceles, hospitales…). El avance y los hitos se informan por sector.',
    '**Hitos principales:** Ingeniería → Inicio Físico → PSP (Puesta en Servicio Provisoria) → PSD (Puesta en Servicio Definitiva). El radar de cada contrato los muestra en ese orden.',
    '**Semáforo del contrato:** Rojo si hay una alerta extrema publicada o un hito atrasado; Ámbar si hay desvío de fechas o una alerta de riesgo alto; Verde en los demás casos.',
    '**Peso:** porcentaje que cada contrato aporta al avance global y cada sector al avance de su contrato. Lo define el Administrador.',
])
h2('1.3 Visión general del flujo')
p('El Administrador deja listos los contratos, sectores y perfiles. El IF reporta; el sistema registra la solicitud y avisa al Validador; '
  'el Validador aprueba o rechaza; lo aprobado se vuelve dato oficial y queda disponible para Gabinete. Si se rechaza, el IF ve el motivo '
  'y puede reportar de nuevo. Las problemáticas no requieren aprobación: el Validador solo decide si publica una alerta a Gabinete.')
diagrama('05_mapa_general', bz.mapa, 'Diagrama general: Bitácora de Obra',
         'Quién hace qué, cómo se aprueba la información y qué ve Gabinete. Los capítulos siguientes detallan cada proceso.')

# ---------------- 2
h1('2. Cómo ingresar')
h2('2.1 Entrar a la Bitácora')
pasos([
    'Abre el enlace institucional de la **Bitácora de Obra** con Chrome o Edge.',
    'Ingresa con tu cuenta institucional. La herramienta reconoce tu **perfil** y los **contratos** que el Administrador te asignó, y te lleva directo a tus pestañas.',
    'Arriba a la derecha ves tu nombre y tu perfil. Si tienes más de un contrato, aparece el selector de **contrato activo**.',
    'Para salir, presiona **Cerrar sesión**.',
])
nota('Si ingresas y la herramienta dice que no tienes perfil, pide al Administrador que te lo asigne (ver 6.4). Sin perfil asignado no se puede entrar.')
h2('2.2 Qué ve y qué puede hacer cada persona')
tabla(['Perfil', 'Ve', 'Puede hacer'], [
    ['IF / AIF', 'Solo los contratos que tiene asignados (titular y suplente).', 'Proponer avances, fechas de hitos y problemáticas; seguir sus solicitudes.'],
    ['Validador / Jefe de Depto.', 'Los contratos de su alcance y las solicitudes de sus IF.', 'Aprobar o rechazar; publicar alertas a Gabinete.'],
    ['Administrador', 'Todo, incluido el registro de cambios.', 'Cargar contratos, sectores, hitos y pesos; asignar perfiles.'],
    ['Gabinete', 'Solo datos aprobados.', 'Consultar. No aprueba ni edita.'],
], [3.6, 6.4, 6.6])
h2('2.3 Avisos por correo')
p('La Bitácora tiene una campanita 🔔 con los avisos dentro de la herramienta. Además, al enviar una solicitud o al decidirla, el botón '
  '**Avisar por correo** abre tu Outlook con el mensaje ya redactado (contrato, sector, hito, valores y comentario); tú lo revisas y lo envías. '
  'El destinatario es el correo del aprobador del contrato (al enviar) o el del IF autor (al decidir).')

# ---------------- 3 IF
h1('3. Procedimientos del Inspector Fiscal / AIF')
h2('3.1 Revisar mis contratos')
pasos([
    'Entra a la pestaña **Mis contratos**. Cada tarjeta muestra el avance físico vigente, el semáforo y el radar Ingeniería → Inicio Físico → PSP → PSD.',
    'Cada contrato lleva la etiqueta **Titular** o **Suplente**. Si tienes más de uno, aparece un selector de **contrato activo**: él define sobre cuál trabajan "Cargar avance" y "Modificar hitos".',
    'Usa **Ver desglose del cronograma** para ver las fechas de cada hito y **Bitácora histórica** para ver los cambios aprobados.',
])
h2('3.2 Cargar un avance')
pasos([
    'Entra a **Cargar avance** y verifica el contrato activo.',
    'Elige el **sector**. La pantalla muestra el avance vigente y, al costado, el historial de avances aprobados.',
    'Indica la **fecha del reporte** y el **% propuesto** (número entero entre 0 y 100; puedes usar la barra deslizante).',
    'Escribe las **observaciones o notas de terreno** si corresponde.',
    'Presiona **Enviar a revisión**. Si aún no está listo, **Guardar borrador**.',
    'En la ventana de confirmación puedes usar **Avisar por correo al aprobador**: se abre tu Outlook con el mensaje ya redactado y tú lo envías. La herramienta no envía correos por sí sola.',
])
nota('Mientras un sector tenga una solicitud en revisión no se puede enviar otra sobre el mismo dato. Espera la decisión o cancélala (3.4).')
diagrama('01_avance_fisico', bz.avance, 'Diagrama: reporte y aprobación de avance físico',
         'Desde que el IF ingresa el avance hasta que el dato queda oficial y visible para Gabinete, o es rechazado con comentario.')
h2('3.3 Modificar la fecha de un hito')
pasos([
    'Entra a **Modificar hitos**. Verás la carta Gantt por sector con la línea de hoy. Los símbolos son: rombo = fecha contractual, cuadrado = fecha programada vigente, círculo = fecha real.',
    'El color indica el estado del hito: cumplido, en plazo, con desvío o atrasado. En el Gantt solo aparecen datos aprobados.',
    'Haz clic en el hito que cambió. Se abre la ventana **Modificar hito**.',
    'Elige una de las dos opciones: **nueva fecha programada** (la justificación es obligatoria) o **fecha real de cumplimiento** (no puede ser una fecha futura).',
    'Envía la solicitud. Como en el avance, puedes **Avisar por correo al aprobador**.',
])
diagrama('02_modificacion_hitos', bz.hitos, 'Diagrama: modificación de fechas de hitos desde el Gantt',
         'Cómo una nueva fecha programada o una fecha real llega a ser oficial: validación, aprobación, actualización del hito, desvío y semáforo.')
h2('3.4 Seguir mis solicitudes')
pasos([
    'Entra a **Mis solicitudes**: ahí están todas, con su estado y los días que llevan en revisión.',
    'Una solicitud **Rechazada** muestra el comentario del revisor. Corrige y crea una nueva solicitud.',
    'Una solicitud **En revisión** se puede cancelar: presiona cancelar y confirma con **Sí, cancelar**. Queda como Eliminada (no se borra).',
    'La campanita 🔔 de la barra superior avisa de las solicitudes rechazadas, aprobadas y pendientes. **Marcar todo como leído** limpia el contador.',
])
h2('3.5 Registrar una problemática')
pasos([
    'Entra a **Problemáticas** y presiona **+ Nueva problemática / riesgo**. (También puedes usar el bloque "¿Hay un problema en terreno?" de Cargar avance, con el botón **Registrar problemática**.)',
    'Completa: sector, título, descripción, impacto, **nivel de riesgo** (Extremo, Alto, Medio o Bajo), **actores relevantes**, fecha de vencimiento y ayuda requerida.',
    'Arma el **checklist de acciones para subsanar**: escribe cada acción y presiona **+ Agregar acción** (o Enter).',
    'Presiona **Crear tarjeta**. La ficha queda en la columna **Detectado**.',
])
h2('3.6 Gestionar y escalar')
pasos([
    'Mueve la tarjeta entre las columnas **Detectado → En gestión → Escalado** arrastrándola. Al escalar, indica a quién: Jefe de División, Directora, Jurídica u Otro.',
    'Abre la ficha con **Ver detalle** para marcar acciones como hechas, agregar **notas** a la bitácora de la ficha o usar **✎ Editar checklist** (luego **Guardar checklist**).',
    'El autor o la jefatura del contrato pueden cambiar el resto de la ficha con **✎ Editar**.',
])
h2('3.7 Resolver una problemática')
pasos([
    'En la ficha presiona **Marcar como resuelta**.',
    'Escribe **cómo y por qué se resolvió** (obligatorio, mínimo 5 caracteres). Queda con fecha y autor.',
    'La ficha pasa a la pestaña **Resueltas**, donde se puede abrir con **Ver ficha** para revisar todo lo ocurrido: descripción, riesgo, actores, checklist, notas y motivo de resolución.',
    'Si el problema vuelve, **Reabrir** la ficha; la resolución anterior se conserva.',
])
diagrama('03_problematicas_y_alertas', bz.problematicas, 'Diagrama: gestión de problemáticas y alertas',
         'Ciclo de una problemática (Detectado → En gestión → Escalado → Resuelto) y, en paralelo, la decisión del Validador de publicar una alerta.')

# ---------------- 4 Validador
h1('4. Procedimientos del Validador / Jefe de Departamento')
h2('4.1 Revisar la bandeja')
pasos([
    'Entra a **Bandeja de aprobaciones**. El número rojo de la pestaña indica cuántas solicitudes esperan decisión.',
    'Cada tarjeta muestra en letra grande **Contrato**, **Sector** y **Hito a modificar** (o el avance), luego el **valor actual → propuesto** y la justificación o notas del IF.',
    'Verifica quién propuso, cuántos días lleva en revisión y la marca **✓ verificado** de autoría.',
])
h2('4.2 Aprobar')
pasos([
    'Presiona **Aprobar**. El dato propuesto pasa a ser oficial y se guarda el cambio (anterior → nuevo) en el historial.',
    'La ventana de confirmación ofrece **Avisar por correo al IF**: se abre Outlook con el mensaje listo; tú lo envías.',
])
h2('4.3 Rechazar')
pasos([
    'Presiona **Rechazar** y escribe el **comentario** (obligatorio, mínimo 5 caracteres): el IF lo leerá en su campanita y en Mis solicitudes.',
    'Confirma con **Confirmar rechazo**. Puedes avisar por correo al IF; el correo lleva el comentario.',
])
nota('No se puede aprobar ni rechazar una solicitud que tú mismo enviaste: el botón no aparece. Debe revisarla otra persona.')
h2('4.4 Alertas a Gabinete')
pasos([
    'En **Problemáticas**, abre la ficha que corresponda a un riesgo relevante.',
    'Presiona **Publicar** para mostrarla como alerta en el dashboard de Gabinete; si la ficha cambió, **Actualizar**; para quitarla, **Retirar**.',
    'Una alerta de riesgo **Extremo** pone el contrato en rojo; una de riesgo **Alto**, en ámbar.',
])
h2('4.5 Historial')
p('La pestaña **Historial** lista los cambios ya revisados (quién propuso, quién aprobó y el antes → después). Sirve para consultas y respaldo.')

# ---------------- 5 Gabinete
h1('5. Gabinete: dashboard ejecutivo')
pasos([
    'Entra al **Dashboard ejecutivo**. Solo verás datos aprobados; no hay botones para editar ni aprobar.',
    'Arriba: **Semáforo** (cuántos contratos hay en rojo, ámbar y verde), **avance global**, **hitos atrasados** y alertas. Al hacer clic en un color del semáforo se filtran los contratos de ese color.',
    'Cada contrato muestra su avance, su radar de hitos y, con **Ver desglose del cronograma**, las fechas de cada hito.',
    'Abajo, la tabla **Últimas aprobaciones**: avances aprobados y hitos modificados (contrato, sector, hito, fecha anterior → nueva y fecha de aprobación). Usa **Ver más** para ver más filas.',
])

# ---------------- 6 Administrador
h1('6. Procedimientos del Administrador del sistema')
h2('6.1 Cargar contratos por Excel')
pasos([
    'Entra a **Configuración** y presiona **Descargar plantilla (.xlsx)** (o **.csv**).',
    'Completa una fila por contrato con las columnas **COD_DEAF**, **NOMBRE_CONTRATO**, **TIPO_UNIDAD**, **IF_TITULAR**, **IF_SUPLENTE** y **CORREO_APROBADOR**. También se aceptan CORREO_IF_TITULAR y CORREO_IF_SUPLENTE (basta con el nombre o el correo del titular).',
    'Presiona **Subir Excel / CSV** y elige el archivo.',
    'Revisa la **vista previa**: cuántos contratos son nuevos, cuántos se actualizan y cuántos no cambian. Si hay errores, se listan por fila y **no se importa nada** hasta corregirlos.',
    'Confirma la importación. Los contratos existentes se actualizan por **COD_DEAF**; nunca se borran.',
])
nota('Límites del archivo: 2 MB, 500 filas con datos y 30 columnas. Se lee solo la primera hoja. Una celda que empieza con = + - @ se rechaza.')
h2('6.2 Sectores y subsectores')
pasos([
    'En **Configuración → Unidades y subsectores** aparece cada contrato con la lista de sus subsectores, uno por uno.',
    'Para agregar uno, presiona **+ Agregar subsector**. Cada fila se edita directamente (nombre y activo).',
    'Un subsector no se borra: se desactiva. Los nombres no pueden repetirse dentro de un contrato.',
    'También se puede cargar por Excel (plantilla con **COD_DEAF**, **SUBSECTOR**, **ACTIVO**) con el mismo procedimiento de vista previa y confirmación.',
])
h2('6.3 Línea base de hitos y pesos')
pasos([
    'En **Configuración**, presiona **+ Agregar hito** para cargar la línea base: tipo (Ingeniería, Inicio Físico, PSP o PSD), sector y **fecha contractual**.',
    'Define los **pesos** (%) de cada contrato en el avance global y de cada sector dentro de su contrato. La suma debe ser 100; **Repartir en partes iguales** ayuda a partir. Luego **Guardar pesos**.',
    'Con todos los pesos definidos el avance se calcula ponderado; si falta alguno, se usa el promedio simple y la tarjeta lo indica.',
])
h2('6.4 Asignar perfiles y contratos')
pasos([
    'Entra a **Gestión de permisos** y busca a la persona.',
    'Asigna su **perfil** (IF/AIF, Validador, Administrador o Gabinete) y su **correo**.',
    'Para un IF, presiona **Editar contratos…**: busca por nombre o COD_DEAF, filtra con **Todos / Asignados / Sin asignar**, marca los contratos y elige **Titular** o **Suplente** en cada uno. Se recomienda un máximo de dos contratos por IF; con más aparece una advertencia.',
    'Guarda. Sin perfil asignado, una persona no puede usar la herramienta.',
    'Atajo: **Revisar asignaciones por correo** asigna a cada IF los contratos donde aparece su correo. Primero muestra qué agregaría; conserva lo que ya tenía.',
    'Completa también el **correo del aprobador de cada contrato**: es el destinatario del botón "Avisar por correo".',
])
diagrama('04_carga_y_permisos_admin', bz.administracion, 'Diagrama: carga de contratos, subsectores y permisos',
         'Plantilla, validación y vista previa de la carga por Excel; luego la asignación de perfiles y contratos.')
h2('6.5 Registro de cambios')
p('Para dar apoyo, el Administrador puede usar el selector **Ver como** (barra superior) y ver la herramienta con otro perfil. Es solo una vista: '
  'lo que hagas queda registrado con tu cuenta y el sistema sigue aplicando tus permisos reales.')
p('La pestaña **Registro de cambios** muestra quién modificó qué, cuándo y el antes → después (contratos, sectores, hitos, permisos, pesos, solicitudes, alertas y problemáticas). '
  'Se filtra por qué, quién, texto y fechas, y se exporta con **Exportar CSV**. Una fila alterada se marca "⚠ alterado".')
doc.add_page_break()

# ---------------- 7 reglas
h1('7. Reglas que aplica el sistema')
tabla(['Regla', 'Qué significa'], [
    ['Nadie aprueba lo propio', 'La solicitud que enviaste solo la puede revisar otra persona.'],
    ['Rechazo con comentario', 'Al rechazar hay que escribir un comentario de al menos 5 caracteres.'],
    ['Una solicitud activa por dato', 'No se puede enviar otra mientras la anterior sobre el mismo avance u hito está en revisión.'],
    ['Fecha programada con justificación', 'Cambiar la fecha programada de un hito exige explicar el motivo.'],
    ['Fecha real no futura', 'La fecha real de cumplimiento no puede ser posterior a hoy.'],
    ['Avance entre 0 y 100', 'Número entero.'],
    ['Resolver con motivo', 'Una problemática no se marca resuelta sin explicar cómo o por qué (mín. 5 caracteres).'],
    ['Nada se borra', 'Lo "eliminado" queda marcado, no se destruye; los cambios se conservan en el historial y en el registro de cambios.'],
    ['Gabinete solo lee', 'Ve únicamente datos aprobados y no puede editar ni aprobar.'],
    ['Cada IF ve sus contratos', 'Un IF ve y trabaja solo los contratos que el Administrador le asignó.'],
], [5.0, 11.6])

# ---------------- 8 problemas frecuentes
h1('8. Problemas frecuentes')
tabla(['Situación', 'Qué hacer'], [
    ['No puedo entrar / dice que no tengo perfil', 'Pide al Administrador que te asigne un perfil y tus contratos en Gestión de permisos.'],
    ['No veo el botón Aprobar', 'Verifica que tu perfil sea Validador o Administrador y que la solicitud no sea tuya.'],
    ['No me deja enviar: ya hay una solicitud para ese dato', 'Espera la decisión o cancela la solicitud pendiente desde Mis solicitudes.'],
    ['Mi hito no aparece en el Gantt o no cambió', 'El Gantt muestra datos aprobados: el cambio se ve cuando el Validador lo aprueba.'],
    ['El botón "Avisar por correo" no envía nada', 'Solo abre Outlook con el mensaje redactado. Revisa el destinatario y envíalo tú.'],
    ['Falta el correo del aprobador', 'Pide al Administrador que lo complete para ese contrato (Gestión de permisos o carga por Excel).'],
    ['El Excel muestra errores', 'Corrige las filas indicadas en la vista previa y vuelve a subirlo. Hasta entonces no se importa nada.'],
], [6.0, 10.6])

# ---------------- glosario
h1('9. Glosario')
tabla(['Término', 'Significado'], [
    ['IF / AIF', 'Inspector Fiscal / Asesoría de Inspección Fiscal.'],
    ['COD_DEAF', 'Código único de cada contrato.'],
    ['PSP / PSD', 'Puesta en Servicio Provisoria / Definitiva.'],
    ['Sector / subsector', 'Cada parte en que se divide un contrato (aeródromo, estación, cárcel, hospital, etc.). En pantalla también aparece como unidad.'],
    ['Línea base', 'Fechas contractuales de los hitos; la referencia contra la cual se mide el desvío.'],
    ['Desvío', 'Diferencia en días entre la fecha programada (o real) y la contractual.'],
    ['Dato oficial', 'Valor aprobado por la jefatura; es el que ve Gabinete.'],
    ['Radar', 'Línea de los cuatro hitos principales de un contrato con su estado.'],
], [4.0, 12.6])

salida = AQUI / 'Manual de procedimientos - Bitacora de Obra.docx'
doc.save(str(salida))
print('OK', salida.name)

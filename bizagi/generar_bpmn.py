"""Genera los diagramas BPMN (Bizagi) de la Bitácora de Obra.

Uso:  python generar_bpmn.py
Salida: 01_..05_*.bpmn (importar en Bizagi Modeler) y su .svg (revisión/impresión).
Las reglas de cada flujo salen de DISENO_BITACORA_OBRA.md (secciones 9-11) y backend/validar.py.
"""
import pathlib
from bpmn_lib import Process, COL_W

AQUI = pathlib.Path(__file__).resolve().parent
IF, VAL, SIS, GAB, ADM = 'IF / AIF', 'Validador / Jefe de Depto.', 'Sistema', 'Gabinete', 'Administrador'


def r(p, id):
    return p.byid(id).r


# ---------------------------------------------------------------- 01 avance físico
def avance():
    p = Process('Avance', 'Reporte y aprobación de avance físico', [IF, VAL, SIS, GAB],
                'El IF/AIF propone un avance (%); el Validador lo aprueba o rechaza; solo lo aprobado pasa a ser dato oficial '
                'y lo ve Gabinete. Estados: BORRADOR, PENDIENTE_APROBACION, APROBADO, RECHAZADO, ELIMINADO.')
    p.add('S', 'start', 'Hay que reportar el avance', IF, 0)
    p.add('T1', 'user', 'Ingresar sector, avance % y fecha de reporte', IF, 1,
          doc='Cargar información > Cargar avance. El IF elige el contrato activo (titular o suplente) y el sector. El avance es un entero entre 0 y 100; la fecha de reporte es obligatoria.')
    p.add('T2', 'service', 'Validar datos (0–100, fecha, sin solicitud activa)', SIS, 2,
          doc='Reglas: avance entero 0–100; fecha de reporte obligatoria; una sola solicitud activa por dato (sector).')
    p.add('G1', 'xor', '¿Datos válidos?', SIS, 3)
    p.add('T3', 'user', 'Corregir datos', IF, 3)
    p.add('T4', 'user', 'Enviar a aprobación', IF, 4,
          doc='La solicitud pasa de BORRADOR a PENDIENTE_APROBACION. Opcional: botón "Avisar por correo al aprobador" (mailto: se abre en Outlook; el navegador no envía el correo). Mientras está pendiente el IF puede cancelarla (estado ELIMINADO).')
    p.add('T5', 'service', 'Registrar solicitud y recibo de auditoría', SIS, 5,
          doc='Se guarda la solicitud con su recibo de auditoría (hash SHA-256) y queda en la bandeja del Validador del contrato.')
    p.add('T6', 'user', 'Revisar: valor actual → propuesto', VAL, 6,
          doc='Bandeja de aprobaciones. Se muestra Contrato / Sector / valor actual → propuesto y la diferencia en puntos porcentuales. Nadie aprueba una solicitud que envió él mismo.')
    p.add('G2', 'xor', '¿Decisión?', VAL, 7)
    p.add('T7', 'service', 'Publicar dato oficial y guardar historial', SIS, 8,
          doc='El valor aprobado pasa a oficial (colección oficial) y se guarda el historial anterior → nuevo con fecha de aprobación y revisor.')
    p.add('T8', 'user', 'Consultar avance y semáforo del contrato', GAB, 9,
          doc='Gabinete es solo lectura: ve únicamente datos APROBADOS (dashboard, radar, últimas aprobaciones).')
    p.add('E1', 'end', 'Avance oficial visible', GAB, 10)
    p.add('T9', 'user', 'Escribir comentario del rechazo (mín. 5 caracteres)', VAL, 8,
          doc='El rechazo exige comentario de al menos 5 caracteres. Después se ofrece "Avisar por correo al IF" (mailto:) con el comentario.')
    p.add('T10', 'service', 'Marcar RECHAZADO y avisar al IF', SIS, 9,
          doc='La solicitud queda RECHAZADA y el IF la ve en la campanita de notificaciones con el comentario del revisor.')
    p.add('E2', 'end', 'Rechazada: el IF ve el motivo y puede reenviar', IF, 10)
    p.note('N1', 'Opcional: "Avisar por correo al aprobador" (mailto:). El IF puede cancelar mientras esté pendiente (ELIMINADO).', IF, 6.2, 'T4')
    p.note('N2', 'Regla: nadie aprueba lo propio. Solo el Validador del contrato ve la solicitud.', GAB, 6, 'T6')

    p.flow('S', 'T1'); p.flow('T1', 'T2'); p.flow('T2', 'G1')
    p.flow('G1', 'T3', 'No', mode='v')
    p.flow('T3', 'T1', via=[], ports=('l', 'r'))
    p.flow('G1', 'T4', 'Sí', mode='hv')
    p.flow('T4', 'T5'); p.flow('T5', 'T6'); p.flow('T6', 'G2')
    p.flow('G2', 'T7', 'Aprobar', mode='vh')
    p.flow('G2', 'T9', 'Rechazar', mode='h')
    p.flow('T7', 'T8', mx=r(p, 'T7') + 14)
    p.flow('T8', 'E1', mode='h')
    p.flow('T9', 'T10', mx=r(p, 'T9') + 34)
    p.flow('T10', 'E2')
    return p


# ---------------------------------------------------------------- 02 hitos
def hitos():
    p = Process('Hitos', 'Modificación de fechas de hitos desde el Gantt', [IF, VAL, SIS, GAB],
                'El IF/AIF propone una nueva fecha programada (con justificación) o la fecha real de cumplimiento de un hito '
                '(Ingeniería, Inicio Físico, PSP, PSD) desde la carta Gantt; el Validador aprueba o rechaza.')
    p.add('S', 'start', 'Cambia la fecha de un hito', IF, 0)
    p.add('T1', 'user', 'Abrir Modificar hitos (Gantt) y hacer clic en el hito', IF, 1,
          doc='Cargar información > Modificar hitos. El Gantt muestra solo datos oficiales: fecha contractual (rombo), programada vigente (cuadrado), real (círculo), línea de hoy y color por estado (cumplido, en plazo, con desvío, atrasado).')
    p.add('T2', 'user', 'Indicar nueva fecha programada o fecha real', IF, 2,
          doc='Popup del hito: nueva fecha programada (justificación obligatoria) o fecha real de cumplimiento (no puede ser futura).')
    p.add('T3', 'service', 'Validar fecha, justificación y solicitud única', SIS, 3,
          doc='Reglas: fecha_programada exige justificación; fecha_real no puede ser futura; una sola solicitud activa por hito.')
    p.add('G1', 'xor', '¿Datos válidos?', SIS, 4)
    p.add('T4', 'user', 'Corregir datos', IF, 4)
    p.add('T5', 'user', 'Enviar a aprobación', IF, 5,
          doc='Pasa a PENDIENTE_APROBACION. Opcional: "Avisar por correo al aprobador" (mailto:, el correo del aprobador se define por contrato).')
    p.add('T6', 'service', 'Registrar solicitud y recibo de auditoría', SIS, 6)
    p.add('T7', 'user', 'Revisar: Contrato / Sector / Hito, fecha vigente → propuesta', VAL, 7,
          doc='La tarjeta muestra con letra grande Contrato, Sector y Hito a modificar; luego la fecha vigente, la propuesta y la justificación.')
    p.add('G2', 'xor', '¿Decisión?', VAL, 8)
    p.add('T8', 'service', 'Actualizar hito oficial; recalcular desvío y semáforo', SIS, 9,
          doc='Se guarda la fecha oficial y el historial (fecha anterior → nueva). El "antes" de un hito sin fecha vigente previa es la fecha contractual. Se recalculan desvío vs. contrato, semáforo y radar.')
    p.add('T9', 'user', 'Ver en "Últimas aprobaciones" y en el radar', GAB, 10)
    p.add('E1', 'end', 'Hito actualizado y visible', GAB, 11)
    p.add('T10', 'user', 'Escribir comentario del rechazo (mín. 5 caracteres)', VAL, 9)
    p.add('T11', 'service', 'Marcar RECHAZADO y avisar al IF', SIS, 10)
    p.add('E2', 'end', 'Rechazada: el IF ve el motivo en la campanita', IF, 11)
    p.note('N1', 'Después de decidir se ofrece "Avisar por correo al IF" (mailto:); el rechazo lleva el comentario.', GAB, 7, 'T7')

    p.flow('S', 'T1'); p.flow('T1', 'T2'); p.flow('T2', 'T3'); p.flow('T3', 'G1')
    p.flow('G1', 'T4', 'No', mode='v')
    p.flow('T4', 'T2', via=[], ports=('l', 'r'))
    p.flow('G1', 'T5', 'Sí', mode='hv')
    p.flow('T5', 'T6'); p.flow('T6', 'T7'); p.flow('T7', 'G2')
    p.flow('G2', 'T8', 'Aprobar', mode='vh')
    p.flow('G2', 'T10', 'Rechazar', mode='h')
    p.flow('T8', 'T9', mx=r(p, 'T8') + 14)
    p.flow('T9', 'E1', mode='h')
    p.flow('T10', 'T11', mx=r(p, 'T10') + 34)
    p.flow('T11', 'E2')
    return p


# ---------------------------------------------------------------- 03 problemáticas
def problematicas():
    p = Process('Problem', 'Gestión de problemáticas y alertas', [IF, VAL, SIS, GAB],
                'Problemáticas de terreno: Detectado → En gestión → Escalado → Resuelto. No pasan por aprobación; el Validador '
                'decide si publica una alerta a Gabinete según el riesgo de la ficha.')
    p.add('S', 'start', '¿Hay un problema en terreno?', IF, 0)
    p.add('T1', 'user', 'Registrar problemática (riesgo, stakeholders, checklist)', IF, 1,
          doc='Título, descripción, nivel de riesgo (Extremo, Alto, Medio, Bajo), stakeholders, checklist de subsanación y fecha de vencimiento.')
    p.add('T2', 'service', 'Guardar ficha en estado Detectado', SIS, 2)
    p.add('P1', 'and', '', SIS, 3)
    p.add('T3', 'user', 'Gestionar: checklist y notas; escalar si hace falta', IF, 4,
          doc='Estados: Detectado → En gestión → Escalado. Escalamiento a Jefe de División, Directora, Jurídica u Otro. Cada nota queda en la bitácora de la ficha. El checklist se puede editar.')
    p.add('G1', 'xor', '¿Se resolvió?', IF, 5)
    p.add('T4', 'user', 'Marcar como resuelta con el motivo (mín. 5 caracteres)', IF, 6,
          doc='El motivo "cómo / por qué se resolvió" es obligatorio y queda con fecha y autor (id).')
    p.add('T5', 'service', 'Registrar resolución y pasar a Resueltas', SIS, 7,
          doc='Se guarda texto, autor y fecha de la resolución. Si la ficha se reabre, la resolución anterior se conserva.')
    p.add('E1', 'end', 'Problemática resuelta (ficha consultable)', IF, 8)
    p.add('T6', 'user', 'Evaluar riesgo y, si corresponde, publicar alerta', VAL, 4,
          doc='Publicar o retirar la alerta a Gabinete es decisión del Validador/Jefe de Depto.')
    p.add('T7', 'user', 'Ver alerta (extrema → rojo; alta → ámbar)', GAB, 5,
          doc='Una alerta extrema publicada pone el contrato en rojo; una de riesgo alto, en ámbar. Se ve en el dashboard de Gabinete.')
    p.add('E2', 'end', 'Alerta visible en el dashboard', GAB, 6)

    p.flow('S', 'T1'); p.flow('T1', 'T2'); p.flow('T2', 'P1')
    p.flow('P1', 'T3', mode='vh')
    p.flow('P1', 'T6', mode='hvh')
    p.flow('T3', 'G1', mode='h')
    p.flow('G1', 'T3', 'No: seguir gestionando', mode='looptop')
    p.flow('G1', 'T4', 'Sí')
    p.flow('T4', 'T5'); p.flow('T5', 'E1')
    p.flow('T6', 'T7'); p.flow('T7', 'E2', mode='h')
    p.note('N1', 'La ficha reabierta conserva la resolución anterior. Las resueltas se consultan en la pestaña Resueltas.', VAL, 7.2, 'T5')
    return p


# ---------------------------------------------------------------- 04 administración
def administracion():
    p = Process('Admin', 'Carga de contratos, subsectores y permisos', [ADM, SIS],
                'El Administrador carga contratos y subsectores por Excel/CSV (con plantilla), revisa la vista previa y confirma; '
                'luego asigna perfiles y contratos en Gestión de permisos.')
    p.add('S', 'start', 'Cargar contratos o subsectores', ADM, 0)
    p.add('T1', 'user', 'Descargar plantilla (.xlsx o .csv)', ADM, 1,
          doc='Contratos: COD_DEAF, NOMBRE_CONTRATO, TIPO_UNIDAD, IF_TITULAR, IF_SUPLENTE, CORREO_APROBADOR (también acepta correos del IF). Subsectores: COD_DEAF, SUBSECTOR, ACTIVO.')
    p.add('T2', 'user', 'Completar plantilla', ADM, 2)
    p.add('T3', 'user', 'Subir archivo', ADM, 3)
    p.add('T4', 'service', 'Validar archivo (tamaño, filas, COD_DEAF, correos)', SIS, 4,
          doc='Máx. 2 MB, 500 filas, 30 columnas; COD_DEAF único y válido; correos válidos; ninguna celda empieza con = + - @. Lee solo la primera hoja y no evalúa fórmulas ni macros.')
    p.add('G1', 'xor', '¿Hay errores?', SIS, 5)
    p.add('T5', 'user', 'Corregir según errores por fila (no se importó nada)', ADM, 5,
          doc='Si hay un solo error no se importa nada; la vista previa lista los errores por fila.')
    p.add('T6', 'service', 'Mostrar vista previa: nuevos / por actualizar / sin cambios', SIS, 6)
    p.add('T7', 'user', 'Confirmar importación', ADM, 7)
    p.add('T8', 'service', 'Importar: crear nuevos y actualizar por COD_DEAF', SIS, 8,
          doc='Importación atómica. Nunca se borra: el COD_DEAF existente se actualiza sin tocar "activo".')
    p.add('T9', 'user', 'Asignar perfil, contratos y rol Titular/Suplente', ADM, 9,
          doc='Gestión de permisos: perfil (IF/AIF, Validador, Administrador, Gabinete), contratos con multiselección, rol Titular/Suplente por contrato y correo de la persona. Un IF suele tener máx. 2 contratos.')
    p.add('T10', 'service', 'Guardar permiso (solo ids) y auditar', SIS, 10,
          doc='Solo se guarda el id de la persona, nunca su nombre. Sin perfil asignado, una persona no puede entrar.')
    p.add('E1', 'end', 'Contratos, subsectores y permisos listos', ADM, 11)
    p.note('N1', 'Subsectores: vista contrato por contrato, editable por fila; alta y desactivación (borrado lógico).', SIS, 1.6, 'T2')

    p.flow('S', 'T1'); p.flow('T1', 'T2'); p.flow('T2', 'T3')
    p.flow('T3', 'T4'); p.flow('T4', 'G1')
    p.flow('G1', 'T5', 'Sí', mode='v')
    p.flow('T5', 'T3', via=[], ports=('l', 'r'))
    p.flow('G1', 'T6', 'No', mode='h')
    p.flow('T6', 'T7'); p.flow('T7', 'T8'); p.flow('T8', 'T9'); p.flow('T9', 'T10')
    p.flow('T10', 'E1')
    return p


# ---------------------------------------------------------------- 05 mapa general
def mapa():
    p = Process('Mapa', 'Bitácora de Obra: mapa general del flujo', [ADM, IF, VAL, SIS, GAB],
                'Vista de una página: quién hace qué, cómo se aprueba la información y qué ve Gabinete.')
    p.add('S', 'start', 'Inicio del piloto', ADM, 0)
    p.add('T1', 'user', 'Cargar contratos y subsectores; asignar perfiles', ADM, 1,
          doc='Detalle en el proceso 04.')
    p.add('T2', 'user', 'Reportar avance, fechas de hitos o problemáticas', IF, 2,
          doc='Detalle en los procesos 01 (avance), 02 (hitos) y 03 (problemáticas).')
    p.add('T3', 'service', 'Registrar solicitud pendiente y avisar al Validador', SIS, 3)
    p.add('T4', 'user', 'Revisar y decidir', VAL, 4)
    p.add('G1', 'xor', '¿Aprueba?', VAL, 5)
    p.add('T5', 'service', 'Publicar dato oficial, historial y semáforo', SIS, 6)
    p.add('T6', 'user', 'Consultar dashboard: contratos, semáforo, radar, últimas aprobaciones', GAB, 7)
    p.add('E1', 'end', 'Información ejecutiva al día', GAB, 8)
    p.add('T7', 'user', 'Comentar el rechazo (mín. 5 caracteres)', VAL, 6)
    p.add('T8', 'service', 'Avisar al IF (campanita; correo opcional)', SIS, 7)
    p.add('E2', 'end', 'El IF corrige y vuelve a reportar', IF, 8)
    p.note('N1', 'Las problemáticas no requieren aprobación: el Validador solo decide si publica una alerta a Gabinete.', IF, 4.6, 'T2')

    p.flow('S', 'T1'); p.flow('T1', 'T2')
    p.flow('T2', 'T3'); p.flow('T3', 'T4'); p.flow('T4', 'G1')
    p.flow('G1', 'T5', 'Sí', mode='vh')
    p.flow('G1', 'T7', 'No', mode='h')
    p.flow('T5', 'T6', mx=r(p, 'T5') + 14)
    p.flow('T6', 'E1', mode='h')
    p.flow('T7', 'T8', mx=r(p, 'T7') + 34)
    p.flow('T8', 'E2')
    return p


if __name__ == '__main__':
    for nombre, fn in [('01_avance_fisico', avance), ('02_modificacion_hitos', hitos),
                       ('03_problematicas_y_alertas', problematicas), ('04_carga_y_permisos_admin', administracion),
                       ('05_mapa_general', mapa)]:
        proc = fn()
        (AQUI / (nombre + '.bpmn')).write_text(proc.to_bpmn(), encoding='utf-8')
        (AQUI / (nombre + '.svg')).write_text(proc.to_svg(), encoding='utf-8')
        print('OK', nombre)

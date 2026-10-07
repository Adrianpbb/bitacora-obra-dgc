# Bitácora de Obra — Diseño y bitácora de avance

**Actualizado al: 2026-10-02** (v10: sección 11)

**Desde 2026-10-02 se trabaja y entrega como HTML local** (`frontend\Bitacora de Obra.html`,
ver sección 10): la red MOP bloquea claude.ai y el usuario no puede abrir los artifacts.
Artifact HTML (Claude Artifacts, congelado en la v8): `https://claude.ai/artifact/8EUtQPjnVGvCYNYMnRkJfg`
Dirección General de Concesiones (DGC) — División de Construcción.

Este documento se va actualizando a medida que avanza el proyecto. Vive junto al resto de
material de Construcción en `Documents\PMO\Monday\Construccion\`, que ya contiene por separado
la **Planilla Hitos Construcción** (Excel + Gantt, `scripts\build_v8.py` etc., ver más abajo
cómo se relacionan ambos sistemas).

## 1. Objetivo

Herramienta para que los **Inspectores Fiscales (IF)** de contratos de Concesiones —
Construcción reporten, por contrato:

1. **Hitos**: PSP, Informe de avance, Fase de construcción, Ingeniería.
2. **Avance de obra**: % físico, historizado (se guarda cada reporte, el front muestra el
   vigente).
3. **Problemáticas y riesgos**: conflictos territoriales, riesgos de contrato, con
   escalamiento a Jefe de División / Directora / Jurídica.

## 2. Contexto organizacional

**Reunión martes 29-09-2026** con tres jefaturas (jefes de Departamento de Obras
Viales, Edificación Pública y Hospitales, respectivamente):

- Se presentó la necesidad de Monday.com para gestión de contratos, usando como referencia
  lo ya hecho en Operaciones (`DDLPMonday.py`, "Monday Vibes").
- Se presentó el prototipo (este Artifact) para capturar hitos (conectado a Monday a futuro),
  avances y problemáticas. Se planteó la necesidad de infraestructura SQL para sostenerlo.
- Recepción positiva de los tres.

**Acuerdos:**
- **Con la jefatura piloto**: piloto con dos contratos de muestra — **Red Aeroportuaria Austral** y
  **Teleférico Bicentenario** — trabajando directo con sus IF. (Ya existen carpetas de estos
  dos contratos en la carpeta de pilotos dentro de `Documents\PMO\Monday\Construccion\`, usadas por la Planilla
  Hitos Construcción — ver sección 6.)
- **Con la jefatura de Hospitales**: envío a todos los IF de Hospitales; se releva la necesidad de normalizar
  la información entre inspectores. Buena disposición, interés en medir otras necesidades.
- **Con la jefatura de desarrollo**: integrar esfuerzos con el desarrollo de su equipo (GitHub);
  sumar también a otra persona del equipo.

Correo de resumen enviado al Jefe de División de Construcción el 30-09-2026.

## 3. Por qué Claude Artifact (y no una app propia todavía)

No está confirmado si el hosting de la web de DGC soporta backend o es solo estático — eso
determina si conviene esperar el espacio en el SQL Server institucional (el mismo que se
pidió para [[controversias-dgc-access]] / Defensa Judicial) o si basta con algo más liviano
(SQLite en el propio servidor, o un interino tipo Microsoft Forms + SharePoint). **Mientras
se resuelve, se sigue iterando en HTML/Claude Artifact**, aunque la capa de datos (`db`
capability del Artifact) no sea portable fuera de claude.ai — es decir, el diseño visual y la
lógica de formularios SÍ son reusables si se migra, pero la persistencia no.

**Ojo con la distinción:** el espacio en SQL Server institucional ya fue solicitado
explícitamente para Controversias DGC/Defensa Judicial (2026-09-28). Para la Bitácora de Obra
el bloqueo es la pregunta de capacidad del hosting DGC, que AÚN no se ha confirmado — no son
exactamente el mismo pendiente, aunque la misma infraestructura SQL, una vez otorgada, podría
servir a ambos.

## 4. Modelo de datos (colección `db` del Artifact) — vigente desde 2026-10-01 (v8); cambios de la v10 en la sección 11.2

```
contratos (nombre, unidadLabel, inspectorNombre, activo)        [lee: Lector · escribe: Editor]
unidades (contratoId, nombre, activo)                           [lee: Lector · escribe: Editor]
hitos (contratoId, unidadId, nombre, tipo, fechaContractual,
       isDeleted)  ← línea base                                 [lee: Lector · escribe: Editor]
oficial/  ← lo ÚNICO que ve Gabinete                            [lee: Lector · escribe: Editor]
   avance-<unidad>   (valor, fechaReporte, aprobadoTs, solicitudId, revisorId)
   hito-<hito>       (fechaVigente, fechaReal, aprobadoTs, revisorId)
   hist-<solicitud>  (campo, ref, valorAnterior, valorNuevo, nota, autorId, revisorId, aprobadoTs)
   alerta-<problem.> (titulo, nivelRiesgo, escalamiento[], estado, publicadoTs, isDeleted)
solicitudes (tipo: avance|fecha_programada|fecha_real, contratoId, unidadId|hitoId,
             valorPropuesto, valorVigente, fechaReporte, nota, estado, isDeleted,
             autorId, creadoTs, enviadoTs, revisorId, revisadoTs,
             comentarioRevision, historial[])                   [lee/escribe: Colaborador]
problematicas (... como v7 + isDeleted, autorId)                [lee/escribe: Colaborador]
permisos/<cuenta> (rol, contratos[], activo)                    [lee: Colaborador · escribe: Editor]
audit/<cuenta>/eventos/<recibo>                                 [escribe: esa cuenta · lee: Editor]
config/auditoria (problematicas[] previas a la auditoría)       [escribe: Editor]
```

Colecciones legadas que quedan en la base sin usarse (nada se borra): `avances`,
`hitoSeguimiento` (migradas a `oficial` el 2026-10-01) y `credenciales` (vacía; la clave por
contrato se retiró, lectura bloqueada a no-Editores).

- **Ingreso = cuenta institucional + perfil asignado** (ver sección 9). Ya no hay clave por
  contrato.
- Una `problematica` puede ser de una unidad específica o de "todo el contrato"
  (`unidadId: null`).

## 5. Historial de iteraciones

**2026-09-28** — v1: maqueta inicial con pestañas Resumen/Reportar/Sectores, PIN por sector,
db capability con reglas de acceso verificadas.

**2026-09-29** — Rediseño grande a partir de feedback:
- Login movido al primer momento de abrir (antes estaba dentro de "Reportar").
- Modelo generalizado Contrato→Unidad (antes "Sector" fijo).
- Login pasó de ser por Unidad a ser por **Contrato** (1 IF = 1 contrato completo).
- Se agregó Hitos (PSP/Informe/Fase/Ingeniería) con fecha contractual fija + desvío.
- Problemáticas: checklist de subsanación, bitácora de notas por tarjeta, stakeholders como
  tags, fecha de vencimiento, drag & drop entre columnas, pestaña "Resueltas" separada del
  kanban activo.
- **Detalle curioso**: en un momento, al publicar, el sistema detectó que una versión más
  nueva había sido guardada directamente desde dentro de la página (edición in-place) con un
  rediseño más elaborado (appbar oscuro, timeline de avances, nivel de riesgo) — se fusionó
  sobre esa versión en vez de sobrescribirla. Esa es la base de la v6.

**2026-10-01** — v7: auditoría y blindaje de seguridad (detalle en la sección 8). Desde esta
versión el código fuente vive en esta carpeta (`frontend\bitacora-obra.html`) y se publica
desde aquí; ya no depende de una copia temporal de la sesión.

**2026-10-01** — v8: perfiles (IF/AIF, Validador, Administrador, Gabinete), flujo de
aprobación, datos oficiales, radar de hitos críticos, paleta institucional con logo DGC 2026 y
artifact demo aparte. Se retiró la clave por contrato. Detalle en la sección 9. Desde esta
versión la carpeta es un repositorio **git** (un commit por hito).

**2026-10-02** — v10: pantalla del IF (Gantt, avisos, correo), Gabinete, cargas por Excel, semáforo y banner (sección 11).

**2026-10-02** — v9: **modo local**. Decisión del usuario: "trabajémoslo siempre en HTML, porque
no me abren los artefactos en claude.ai". El mismo HTML, abierto desde disco, funciona sin
claude.ai guardando en el navegador; se genera además un archivo único autocontenido. Detalle
en la sección 10.

## 6. Relación con otros sistemas de Construcción (para no confundirlos)

- **Monday workspace `16733064`** (ver [[monday-construccion]]): destino final de Hitos/
  Avance/Problemáticas una vez resuelto el tema de licencias Monday. Carpeta por contrato,
  3 tableros de ejemplo. Brief para Sidekick ya armado. La Bitácora de Obra (Artifact) nace
  de esta necesidad pero hoy vive independiente, con sincronía pendiente.
- **Planilla Hitos Construcción** (ver [[planilla-hitos-construccion]]): sistema Excel + Gantt
  paralelo, ya en v8, con pestaña de sectores editable por IF. Scripts en
  `Documents\PMO\Monday\Construccion\scripts\` (`build_v8.py`, `build_pilotos.py`, `gantt.py`).
  Las carpetas de los dos contratos piloto (Red Aeroportuaria Austral, Teléferico Bicentenario)
  ya existen en la carpeta de pilotos dentro de `Documents\PMO\Monday\Construccion\`. **Esto es un sistema distinto
  de la Bitácora de Obra** — ambos abordan Construcción pero con formatos distintos (Excel/
  Gantt vs. Artifact web); falta decidir si convergen o conviven.

## 7. Pendiente / próximos pasos

- [ ] **(2026-10-02, v10) Decisiones abiertas del dueño del proyecto**: ver la lista de la sección 11.6
      (regla del semáforo, correo por contrato o por persona, lector de Excel propio, línea base por Excel, etc.).
- [x] **(2026-10-02, v10) Carga de contratos y subsectores sin ir uno por uno**: resuelto con Excel/CSV (sección 11.3).
- [x] **(2026-10-02, v10) Trabajar los hitos desde una vista tipo Monday**: resuelto con la carta Gantt del IF (sección 11.1). El Monday real sigue pendiente.
- [ ] **(2026-10-02) Definir el camino multiusuario sin claude.ai.** El modo local es para una
      sola persona en un solo navegador. Opción intermedia: servir el `backend\` (SQLite) desde un
      PC o servidor de la red DGC. La definitiva sigue siendo SQL Server con el DBA (ver abajo).

- [ ] **Dar acceso a las personas del piloto** (menú Compartir del artifact): Validadores y
      Administradores como **Editor**, IF/AIF como **Colaborador**, Gabinete como **Lector**. Luego
      asignar perfil y contratos en "Gestión de permisos" (sin perfil, un Colaborador no entra).
- [ ] Cargar la línea base real de hitos (Ingeniería, Inicio Físico, PSP, PSD) de los contratos
      piloto en Configuración: hoy los datos son de ejemplo (2026-10-01).
- [ ] Compartir el demo (https://claude.ai/artifact/7T3Q5quQzyy9p5fudSUGem) con quienes lo vayan a
      ver como **Colaborador**, para presentar al Jefe de División y jefaturas.
- [ ] Revisar `backend\schema_sqlserver.sql` con el DBA antes de ejecutarlo (no se ha corrido
      contra SQL Server; el mismo modelo sí está probado en SQLite). **Desde la v10 hay que revisar además**: columnas nuevas
      (CodDeaf, InspectorSuplente, CorreoAprobador, RolContrato, ResolucionTexto/PorId), tablas nuevas
      (ProblematicaResolucionPrevia, LecturaNotificacion), índices únicos (UX_Contrato_CodDeaf, UX_Unidad_Contrato_Nombre; la
      unicidad sin distinguir mayúsculas depende de la intercalación `_CI_` de la base) y la política `PoliticaPropia`.
- [ ] En el backend definitivo: identidad con AD/Entra ID (SSO), cookie de sesión HttpOnly +
      Secure + SameSite, y Content-Security-Policy con nonce.
- [ ] Confirmar si el hosting web de DGC soporta backend o es solo estático.
- [ ] Definir si la Bitácora de Obra (Artifact) y la Planilla Hitos Construcción (Excel/Gantt)
      convergen en un solo sistema o siguen caminos paralelos para los dos contratos piloto.
- [ ] Sincronía de Hitos con Monday (botón de espejo) — en pausa, evaluar `mcp` capability del
      Artifact cuando se resuelva el tema de licencias.
- [ ] Trabajar con los IF reales de Red Aeroportuaria Austral y Teleférico Bicentenario
      (piloto acordado con la jefatura piloto).

## 8. Seguridad — auditoría y blindaje (2026-10-01)

> **Nota v8 (2026-10-01):** la clave por contrato descrita en esta sección se **retiró** al pasar
> a cuentas individuales con perfil (sección 9). Siguen vigentes: escape de XSS por defecto,
> normalización de todo dato leído, recibos de auditoría, reglas del servidor, aislamiento del
> flujo normal y la preparación SQL parametrizada.

### 8.1 Hallazgos sobre la v6

| # | Severidad | Hallazgo | Estado |
|---|---|---|---|
| 1 | Crítico | PINs en texto plano legibles por cualquiera que abriera el artifact | Corregido: hash PBKDF2-SHA256 600.000 it.; PINs viejos borrados |
| 2 | Crítico | El login era solo visual: el servidor no sabía del PIN | Mitigado (ver límites 8.3) |
| 3 | Crítico | XSS almacenado en 4 vectores (`fmtDate` devolvía texto crudo; `avancePct`, `fechaProgramada` y estado PSP sin escapar) | Corregido |
| 4 | Alto | Fecha contractual "fija" solo en pantalla; cualquier colaborador podía cambiarla | Corregido: `hitos` solo admin en el servidor |
| 5 | Alto | `reportadoPor`/`timestamp` falsificables desde el navegador | Mitigado: autoría desde la sesión + recibos verificables |
| 6 | Alto | Se descargaban todos los contratos, incluso antes del login | Corregido en el flujo normal (ver límites 8.3) |
| 7 | Medio | Sin validación de tipos al leer (un dato mal formado botaba el tablero) | Corregido |
| 8 | Medio | Lookups con claves del usuario (`constructor`, `__proto__`) y sin límites de largo | Corregido |

### 8.2 Qué se implementó

**Autenticación.** Login con contrato + clave (6 a 64 caracteres imprimibles). La clave se
guarda como hash PBKDF2-SHA256 con sal aleatoria de 16 bytes y 600.000 iteraciones (Web
Crypto, nada hecho a mano); se compara en tiempo constante; nunca queda en el DOM ni viaja en
claro. Bloqueo progresivo tras 5 intentos (30 s, 60 s… hasta 5 min). Las claves se asignan en
Administración y no se pueden volver a leer, solo reemplazar. **El formato es idéntico al del
backend**: verificado con un hash generado en Chrome y comprobado en Python.

**Control de acceso (reglas del servidor, 8 reglas).** Datos legibles solo por Colaboradores o
superior; `contratos`, `unidades`, `hitos` (línea base), `credenciales` y `config`: escribe solo
el nivel central; el IF escribe `hitoSeguimiento`, `avances` y `problematicas`.

**Trazabilidad.** La autoría (`reportadoPor`, `autorId`) sale de la sesión, nunca del
formulario. Cada avance, problemática y nota deja antes un **recibo** en
`audit/<cuenta>/eventos` con el SHA-256 de su contenido. Esa carpeta solo la puede escribir la
propia cuenta (lo impone el servidor), así que el nivel central ve en cada registro:
"✓ verificado", "⚠ alterado" (cambió después de registrarse), "⚠ sin respaldo" (la cuenta que
figura como autora no lo registró) o "previo a auditoría" (lista `config/auditoria`, que solo
escribe el admin).

**Prevención de XSS.** Toda la interfaz se dibuja con una plantilla que escapa cada valor por
defecto (`& < > " ' \` =`); solo se marcan como HTML de confianza los íconos fijos del archivo.
Cada documento leído pasa por un normalizador: tipos, listas cerradas, fechas reales, largos
máximos, y se eliminan caracteres de control e invisibles de dirección de texto ("Trojan
Source"). Sin `innerHTML` con datos crudos ni handlers inline.

**Aislamiento.** Antes del login solo se cargan nombres de contratos. Tras el login, el IF se
suscribe únicamente a los documentos de su contrato (`where contratoId == …`), y todo lo que no
sea de su contrato se descarta igual al recibirlo. Al cerrar sesión se cortan las suscripciones
y se vacía la memoria y la pantalla.

**Preparación para SQL.** Carpeta `backend\`: `validar.py` (las mismas reglas que el
frontend), `auth_clave.py` (hash, bloqueo, tokens de sesión que se guardan solo como SHA-256),
`repositorio.py` (todas las consultas parametrizadas con `?`, ninguna armada con texto, el
contrato siempre sale de la sesión del servidor) y los esquemas `schema_sqlite.sql` y
`schema_sqlserver.sql`. El de SQL Server agrega seguridad por filas (RLS) por contrato, rol de
aplicación con mínimo privilegio, y Avance/Notas/Auditoría de solo anexar.

### 8.3 Límites que la plataforma de Artifacts no permite superar (honestidad técnica)

- Las reglas del servidor distinguen por **nivel de acceso** (Lector/Colaborador/Editor), no
  por contrato. Por eso, mientras viva en el artifact, **cualquier Colaborador con conocimientos
  técnicos puede leer los datos de otros contratos y saltarse la pantalla de login** usando las
  herramientas de desarrollador del navegador. Lo que sí no puede hacer es tocar la línea base,
  las claves, la configuración ni los recibos de otros, y cualquier dato que fabrique a nombre
  de otra cuenta queda marcado "sin respaldo".
- No existe un reloj de servidor para los documentos: los `ts` los pone el navegador (la fecha
  de auditoría confiable llega con el backend: `DEFAULT SYSUTCDATETIME()`).
- Los hashes de las claves son legibles por los Colaboradores → rotar claves al ir a producción.
- Mitigación operativa: **compartir el artifact solo con las personas del piloto** (menú
  Compartir), sin enlace público ni acceso general.

### 8.4 Verificación (2026-10-01)

- `pruebas\test_backend.py`: **17/17 OK** (inyección SQL, aislamiento entre contratos, bloqueo
  de login, auditoría del servidor, solo anexar, validación).
- `pruebas\test_frontend.py` (Chrome headless + base simulada con las mismas reglas): **39/39
  OK** (XSS en todas las vistas, consultas filtradas por contrato, login con hash, recibos y
  estados de verificación, clave asignada en el navegador verificada por Python, limpieza al
  cerrar sesión). El arrastre de tarjetas se probó con eventos sintéticos (el simulador de
  mouse de Playwright no arrastra en headless).
- Servidor real (artifact publicado v7): 5 escrituras de ataque como Colaborador **rechazadas**
  (línea base de hitos, clave de un contrato, lista de legado, recibo a nombre de otra cuenta,
  inspector de un contrato); la escritura legítima de seguimiento pasó; un recibo ajeno es
  invisible para un Colaborador y visible para el nivel central.

### 8.5 Migración de datos aplicada (2026-10-01, lote atómico de 23 escrituras)

PIN en texto plano eliminado de los 3 contratos; hitos separados en línea base +
`hitoSeguimiento`; `contratoId` y `ts` agregados a avances y problemáticas; "qué se necesita
para subsanar" convertido a checklist; los 5 avances y 4 problemáticas existentes (incluidos
los creados desde la página el 28 y 29-09) quedaron marcados como "previos a auditoría". No se
perdió ningún registro.

### 8.6 Estructura de la carpeta

```
Bitacora de Obra\
  DISENO_BITACORA_OBRA.md      ← este documento
  frontend\bitacora-obra.html  ← fuente del artifact (se publica desde aquí)
  backend\                     ← validar.py, auth_sesion.py, repositorio.py, schema_*.sql
  pruebas\                     ← test_backend.py, test_frontend.py
```

## 9. v8 — Perfiles, flujo de aprobación y vista ejecutiva (2026-10-01)

Decisiones del usuario (2026-10-01): construirlo **en el artifact actual** (HTML + JS, sin
React por ahora), **cuenta institucional + perfil asignado** (se retira la clave por contrato),
y **selector de rol solo para el nivel central**, más un **artifact demo** con datos ficticios.

- Artifact real: https://claude.ai/artifact/8EUtQPjnVGvCYNYMnRkJfg (v9 publicada)
- Demo: https://claude.ai/artifact/7T3Q5quQzyy9p5fudSUGem (datos ficticios, selector libre)

### 9.1 Perfiles y qué impone el servidor

| Perfil | Nivel en "Compartir" | Qué hace | Impuesto por el servidor |
|---|---|---|---|
| IF / AIF | Colaborador | Carga avance %, fechas y problemáticas; "Mis solicitudes"; cancela lo no revisado | No puede escribir datos oficiales, permisos ni configuración |
| Jefe de Depto. / Validador | Editor | Bandeja de aprobaciones (actual vs. propuesto), aprueba / rechaza con comentario, publica alertas | Solo un Editor escribe `oficial` |
| Administrador | Editor | Gestión de permisos (buscador del directorio + contratos por persona), configuración, línea base | Solo un Editor escribe `permisos`, `contratos`, `unidades`, `hitos` |
| Gabinete / DG | Lector | Dashboard ejecutivo de solo lectura | Un Lector **solo puede leer** `contratos`, `unidades`, `hitos` y `oficial`: nada operativo |

Se resuelven en la aplicación (la plataforma no distingue contratos): el alcance por contrato
de IF y Validador, la regla "nadie revisa lo propio" y el rechazo con comentario. En el backend
SQL las tres quedan además impuestas por la base (RLS, CHECKs y triggers).

### 9.2 Flujo de aprobación

`BORRADOR → PENDIENTE_APROBACION → APROBADO | RECHAZADO`, o `ELIMINADO` (eliminación lógica,
`isDeleted: true`) mientras no haya sido revisada. Aplica a **avance %**, **fecha programada**
y **fecha real de cumplimiento**. Cada solicitud guarda el valor vigente al proponer, su
historial de estados y los días en revisión (se calculan al vuelo). Reprogramar exige
justificación; la fecha real no puede ser futura; no se permiten dos propuestas activas para el
mismo dato. Al aprobar se escriben `oficial/avance-*` o `oficial/hito-*` y una entrada de
historial `oficial/hist-*`; eso es lo que ve Gabinete. Problemáticas escaladas, con riesgo
extremo o que requieren a Directora/Jurídica aparecen en la bandeja para **publicarse** como
alerta a Gabinete (o retirarse, de forma lógica).

### 9.3 Radar y semáforo (solo con datos oficiales)

Etapas: Ingeniería → Inicio Físico → PSP → PSD. Una etapa está **cumplida** cuando todos sus
hitos tienen fecha real aprobada (✓ + fecha). La **crítica** es la primera no cumplida: muestra
días restantes o días de atraso, y el desvío contra la fecha contractual. Las siguientes se
ven atenuadas. Clic en el radar → desglose del cronograma. Semáforo: **Rojo** si hay un hito
atrasado, una alerta extrema publicada o un desvío > 30 días; **Ámbar** si hay desvío o
alertas; **Verde** en otro caso.

### 9.4 Selector "Ver como" y demo

En la Bitácora real solo los Editores ven el selector; el servidor sigue aplicando su permiso
real, las acciones quedan con su cuenta y no pueden aprobar lo que enviaron ellos mismos. El
demo se genera desde la misma fuente (`frontend\generar_demo.py` cambia `MODO_DEMO`), tiene su
propia base con 49 documentos ficticios y permite cambiar libremente de perfil. Antes de
publicar el demo tras un cambio: `python frontend\generar_demo.py`.

### 9.5 Migración de datos reales (2026-10-01)

Solo se agregaron documentos, sin borrar ni modificar nada: los 5 avances legados pasaron a
`oficial/avance-<unidad>` (vigente) + `oficial/hist-legado-*` (historial, marcados como
"previo al flujo de aprobación"); los 5 `hitoSeguimiento` pasaron a `oficial/hito-*` (el h5
quedó cumplido el 2026-09-30). `credenciales` estaba vacía.

### 9.6 Verificación (2026-10-01)

- `pruebas\test_frontend.py` (Chrome headless): **52/52 OK** en 5 escenarios: IF, Validador,
  Gabinete, Administrador y cuenta sin perfil (XSS, alcance por contrato, radar, flujo
  completo, bandeja, permisos, eliminación lógica, Gabinete solo oficial).
- `pruebas\test_backend.py`: **23/23 OK** (flujo, nadie se aprueba a sí mismo ni en la app ni
  en la base, rechazo con comentario, nada se borra físicamente, Gabinete solo oficial,
  inyección SQL, aislamiento).
- Servidor real: un Colaborador **no** puede escribir `oficial` ni autoasignarse un perfil
  en `permisos`, y **sí** lee los datos oficiales.
- No probado: el esquema SQL Server (no hay servidor disponible) y la vista de Lector contra el
  servidor real (la herramienta de verificación solo simula Colaborador y Editor; está cubierta
  por las pruebas del navegador).

### 9.7 Límites (mientras viva en el artifact)

- Un Colaborador con conocimientos técnicos puede leer datos operativos de otros contratos
  (la plataforma no filtra por contrato); no puede tocar datos oficiales, permisos ni
  configuración. El aislamiento real llega con el backend (RLS).
- Validadores y Administradores son Editores del artifact: técnicamente podrían publicar
  versiones de la página. Darle ese nivel solo a personas de confianza.
- No hay reloj de servidor para los documentos: las fechas las pone el navegador (en el
  backend: `DEFAULT SYSUTCDATETIME()`).

### 9.8 Estructura y versiones

```
Bitacora de Obra\   (repositorio git)
  DISENO_BITACORA_OBRA.md
  frontend\bitacora-obra.html        ← fuente única (MODO_DEMO = false)
  frontend\bitacora-obra-demo.html   ← generado por generar_demo.py
  frontend\assets\logo-dgc-*.png     ← logo DGC 2026 optimizado para web
  backend\  validar.py · auth_sesion.py · repositorio.py · schema_sqlite.sql · schema_sqlserver.sql
  pruebas\  test_frontend.py · test_backend.py
```

Commits del 2026-10-01: `58db169` v7 blindada · `0f72edc` frontend v8 · `b524651` publicación
real + demo · `e3c0ac8` backend v8.
Commit del 2026-10-01: `1416c89` docs v8.

## 10. v9 — Modo local: HTML que abre sin claude.ai (2026-10-02)

**Motivo.** La red institucional MOP bloquea claude.ai (ya se había visto el 2026-09-28: solo
abría con wifi externo). Decisión del usuario del 2026-10-02: trabajar y entregar siempre en HTML.
El artifact real **no se republicó** con estos cambios y queda congelado en la v8.

### 10.1 Cómo funciona
- La página revisa si existe `window.claude`. **Sin claude.ai** activa `MODO_LOCAL`:
  - fuerza el modo demo: selector "Ver como" con los 4 perfiles y sin el control de "no
    aprobar lo propio", porque hay un único usuario (`u_local`, "Usuario local");
  - el banner avisa que los datos quedan solo en ese navegador y ese computador.
- **Almacén local** (`crearStoreLocal`, sección 3b del HTML).
  - Imita la API del `db` del artifact: collection/doc, where `==`/`in`, orderBy, limit, get,
    onSnapshot, set, update. Así el resto del código no cambió.
  - Guarda en `localStorage`, clave `bitacora-obra-dgc-v1`. Se sincroniza entre pestañas
    abiertas con el evento `storage`.
  - `delete` se rechaza; se mantiene la eliminación lógica.
- **Primer arranque.** Se cargan los `DATOS_EJEMPLO`: los mismos 49 documentos ficticios del
  demo (3 contratos).
- **"Restablecer datos de ejemplo"** (botón del appbar). Se confirma con dos clics en menos de
  5 s y vuelve a la semilla.
- Con claude.ai disponible, el mismo archivo sigue funcionando como antes (runtime `db` + `user`).

### 10.2 Archivos que se entregan
- `frontend\Bitacora de Obra.html` es el **entregable**: un solo archivo autocontenido, con los
  logos incrustados en base64 (unos 40 KB). Se puede copiar, mandar por correo o abrir desde
  cualquier carpeta.
- `python frontend\generar_demo.py` lo genera junto con `bitacora-obra-demo.html`. La fuente
  sigue siendo `frontend\bitacora-obra.html`, que usa `assets\` como ruta relativa.

### 10.3 Límites (honestidad técnica)
- **Monousuario.** Lo que cargue una persona no lo ve otra. No sirve todavía para el piloto con
  los IF: para eso falta un servidor (pendiente en la sección 7).
- **Los datos viven en el perfil del navegador.** Borrar los datos de navegación los elimina.
  Chrome y Edge no comparten estos datos entre sí.
- Para `file://`, Chrome comparte un solo `localStorage` entre todos los HTML locales. Por eso
  la clave lleva un nombre propio de la Bitácora.

### 10.4 Verificación (2026-10-02)
- **Frontend: 61/61.** Incluye el escenario F nuevo, que abre el HTML sin runtime y comprueba:
  - arranque en modo local con los datos de ejemplo;
  - envío de una solicitud;
  - que los datos persisten al recargar;
  - aprobación como Validador;
  - que Gabinete ve el nuevo promedio oficial (68 % y 55 % → 62 %);
  - que "Restablecer" vuelve a 55 %;
  - sin XSS ni errores de JS.
- **Backend: 23/23.**
- **Archivo autocontenido:** abierto desde otra carpeta carga el logo y no da errores de consola.

## 11. v10 — Pantalla del IF, Gantt, avisos, cargas por Excel y semáforo (2026-10-02)

Encargo del dueño del proyecto, hecho en el orden 1→7 con un commit por punto (`v10.1` … `v10.6`, más el cierre).
Fuente única `frontend\bitacora-obra.html`; después de cada cambio `python frontend\generar_demo.py`.

### 11.1 Qué cambió, por punto

1. **Banner y ancho.** Banner en dos zonas (marca y título a la izquierda; "Ver como", usuario y botones a la
   derecha) con logo de 64 px y pestañas separadas debajo. El contenido y el banner comparten el ancho máximo de
   1.600 px con 32 px de gutter (16 px en teléfono). Tarjetas con `auto-fill`.
2. **Pantalla del IF.**
   - *Titular / Suplente* por contrato (`permisos/<uid>.rolesContrato`): etiqueta en tarjetas y en el selector; con más de un
     contrato aparece el selector de **contrato activo** (rige "Cargar avance" y el Gantt). Más de 2 contratos por IF
     solo genera una advertencia en Gestión de permisos.
   - *Cargar información* quedó en dos pestañas: **Cargar avance** (formulario + historial de avances aprobados en
     línea de tiempo + bloque "¿Hay un problema en terreno?") y **Modificar hitos**.
   - *Modificar hitos* es una **carta Gantt** (por sector: Ingeniería → Inicio Físico → PSP → PSD) con F. contractual (rombo),
     F. programada vigente (cuadrado), F. real (círculo), línea de hoy y colores por estado (cumplido, en plazo, con desvío, atrasado).
     Usa solo datos oficiales. Un clic en el hito abre el popup (nueva fecha programada con justificación obligatoria, o fecha real
     no futura) y crea la solicitud. Se retiró el formulario suelto de hitos.
   - *Notificaciones*: campanita con contador (rechazadas con el comentario del revisor, aprobadas, pendientes). Lo leído se
     guarda como `notificaciones/<uid>.leidoTs` (solo un número, sin nombres).
   - *Correo*: al enviar una solicitud aparece "Avisar por correo al aprobador" (`mailto:` con contrato, sector, hito o avance,
     valor actual → propuesto y justificación; se codifica con `encodeURIComponent` y el cuerpo se limita a 1.500 caracteres).
     El navegador **no envía** correos: abre el programa de correo (Outlook).
   - *Problemáticas resueltas*: el motivo "Cómo / por qué se resolvió" es obligatorio (mín. 5 caracteres) y queda con fecha y
     autor (id). En Resueltas hay una **ficha completa** (descripción, riesgo, stakeholders, checklist, toda la bitácora y el motivo).
     Al reabrir, la resolución anterior se conserva (`resolucionesPrevias`).
3. **Validador.** Cada solicitud muestra **Contrato / Sector / Hito a modificar** con letra grande, luego valor actual → propuesto y la
   justificación. Tras aprobar o rechazar se ofrece "Avisar por correo al IF" (`mailto:` al IF autor; el rechazo lleva el comentario).
4. **Gabinete.** Sigue de solo lectura, sin bandeja ni botones de aprobación (hay prueba). Nueva tabla **Últimas aprobaciones**
   (solo `oficial/hist-*`): avances aprobados y hitos modificados con contrato, sector, hito, anterior → nuevo y fecha de
   aprobación; de la más reciente a la más antigua, 10 por vez ("Ver más") y filtro. Para que el "antes" de un hito sin fecha vigente
   previa sea claro, ahora es la fecha contractual (frontend y backend).
5. **Administrador.**
   - Contrato con `codDeaf` (único), IF titular, IF suplente y correo del aprobador.
   - **Carga por Excel/CSV** de contratos (COD_DEAF, NOMBRE_CONTRATO, TIPO_UNIDAD, IF_TITULAR, IF_SUPLENTE, CORREO_APROBADOR) y de
     subsectores (COD_DEAF, SUBSECTOR, ACTIVO), con plantilla descargable (.xlsx y .csv), validación completa y vista previa con
     errores por fila. Si hay un error no se importa nada. El COD_DEAF existente actualiza (sin tocar "activo" ni el código guardado); nunca se borra.
   - **Unidades y subsectores**: vista contrato por contrato, cada subsector editable en su fila; alta y desactivación (borrado
     lógico); nombres únicos por contrato.
   - En **Gestión de permisos**: rol Titular/Suplente por contrato, correo de la persona y una tabla "Correo del aprobador de cada contrato".
6. **Dashboard.** El semáforo pasó de "2/0/1" a tres cifras con color y etiqueta ("2 contratos en rojo"), una leyenda de cómo se
   calcula y filtro por color al hacer clic (también en Gabinete).

### 11.2 Cambios al modelo de datos

```
contratos     + codDeaf, inspectorSuplente, correoAprobador   (inspectorNombre = IF titular, referencial)
permisos/<u>  + rolesContrato {contratoId: titular|suplente}, correo
problematicas + resolucion {texto, autorId, fecha, ts}, resolucionesPrevias[]
notificaciones/<uid> (nuevo)  leidoTs
```

Backend (`backend\`): `Contrato.CodDeaf / InspectorSuplente / CorreoAprobador`, `UsuarioContrato.RolContrato`, `Usuario.Email` (correo
de la persona), `Problematica.ResolucionTexto / ResolucionPorId` con CHECK (no se resuelve sin motivo), tablas `ProblematicaResolucionPrevia`
(solo anexar) y `LecturaNotificacion`, índices únicos de COD_DEAF y de nombre de subsector por contrato. `repositorio.py`:
`guardar_permiso(..., roles_contrato, email)`, `listar_contratos`, `mover_problematica(..., motivo)`, `listar_resoluciones_previas`,
`listar_avisos`, `marcar_avisos_leidos`, `importar_contratos` e `importar_unidades` (atómicos: `ErrorCarga` con los errores por fila).
`validar.py`: `correo`, `cod_deaf`, `sin_formula`. Historial oficial con desempate por `Id`.

### 11.3 Decisiones

- **Excel sin librería externa.** Se escribió un lector/escritor `.xlsx` mínimo (ZIP + XML) que usa `DecompressionStream` del navegador. Motivo:
  funciona desde `file://` y sin internet (SheetJS desde cdnjs no funciona sin red; incrustarlo agregaría ~1 MB a un HTML de ~290 KB), y no hay
  dependencias que auditar. Además ofrece CSV (UTF-8, separador `;` o `,`, con BOM) como alternativa. Lee solo la primera hoja, no
  evalúa fórmulas ni macros (cada celda se toma como texto y pasa por la validación; una celda que empieza con `= + - @` se rechaza).
  Límites: 2 MB, 500 filas con datos, 30 columnas.
- **Correo del aprobador por contrato** (`contratos.correoAprobador`), no por persona: así lo leen todos los IF sin tocar `permisos`. Se edita
  en Gestión de permisos y también viene en el Excel de contratos. El correo de **la persona** (`permisos.correo`) solo se usa para avisar al IF autor.
- **Los validadores** ahora leen `permisos` (solo de los IF de su alcance) para obtener ese correo.
- **Semáforo: la lógica no cambió**; la leyenda describe lo que hace de verdad (ver 11.6).
- Un IF con más de 2 contratos no se bloquea (advertencia). En modo demo/local los roles Titular/Suplente son fijos (`ROLES_CONTRATO_DEMO`).
- Pruebas: la ruta de Chrome es configurable con la variable `CHROME` (por defecto la de Windows, o `/opt/pw-browsers/...` en la nube).

### 11.4 Límites (honestidad técnica)

- **Importación en el artifact no es atómica**: el navegador escribe fila por fila; la validación sí es "todo o nada" antes de escribir, y
  si una escritura falla a mitad de camino se informa cuántas filas quedaron (volver a subir deja las ya cargadas como "sin cambios").
  El backend sí es atómico (transacción).
- **Los correos de las personas** (`permisos.correo`) son legibles por cualquier Colaborador del artifact (la plataforma filtra por nivel, no
  por contrato) y el correo del aprobador, por Gabinete. Mismo límite de la sección 9.7.
- `notificaciones/<uid>` no puede impedir que otro Colaborador escriba el aviso leído de otra cuenta (límite de la plataforma); en el backend
  la política `PoliticaPropia` lo impide.
- El `mailto:` depende del programa de correo del equipo y de su límite de largo; no queda registro de que el correo se envió.
- Lectura de `.xlsx` requiere `DecompressionStream` (Chrome/Edge actuales, Firefox 113+, Safari 16.4+); si no existe, se indica usar el CSV.
- La unicidad de nombres en SQLite solo pliega ASCII a nivel de base; la validación de la aplicación sí compara con `casefold()`.
  En SQL Server depende de la intercalación (ver pendiente del DBA).
- Los problemáticas ya resueltas antes de la v10 no tienen motivo: la ficha dice "Sin motivo registrado". En el backend el CHECK exige motivo,
  así que al migrar datos antiguos hay que cargar un texto (por ejemplo "Resuelta antes de registrar el motivo").

### 11.5 Verificación (2026-10-02)

- `pruebas\test_frontend.py`: **164/164** (Chrome headless). Partió en 61. Nuevo: banner y ancho (1.920 px y 390 px), Gantt y popup, avance con
  historial, correos `mailto:` (destino, contenido y codificación), notificaciones, resolución de problemáticas con ficha, Titular/Suplente
  y selector de contrato, jerarquía del validador y correo al IF, tabla de Gabinete (orden, límite, filtros, sin botones),
  permisos con rol por contrato y correos, cargas por Excel/CSV (plantilla leída con `openpyxl`, archivos generados por `openpyxl` con
  compresión y cadenas compartidas, errores por fila, fórmula, correos inválidos, CSV con `;`, archivos corruptos o muy grandes,
  subsectores), semáforo con filtro y el entregable abierto desde otra carpeta (logo incrustado, sin errores de consola).
- `pruebas\test_backend.py`: **40/40** (SQLite). Partió en 23. Nuevo: Titular/Suplente, correos, motivo de resolución (aplicación y base),
  resoluciones previas, avisos leídos, cargas masivas atómicas, COD_DEAF único, nombres de subsector únicos.
- `Bitacora de Obra.html` (autocontenido, ~290 KB; antes ~200 KB) abre desde otra carpeta con el logo y sin errores de JavaScript.
- **No verificado**: SQL Server (`schema_sqlserver.sql`, no se ejecutó nada); archivos `.xlsx` guardados por **Excel de escritorio** y
  Outlook real (solo `openpyxl` y el CSV); Firefox y Safari; el artifact publicado (sigue congelado en la v8).

### 11.6 Decisiones que quedan para el dueño del proyecto

1. **Semáforo.** La lógica actual: *rojo* = hito atrasado, alerta extrema publicada **o desvío de fechas de más de 30 días**; *ámbar* = desvío de
   fechas (hasta 30 días) **o cualquier alerta publicada** que no sea extrema; *verde* = ninguna. Tu descripción omitía el desvío > 30 días y
   hablaba de "alerta de riesgo alto" para el ámbar. Dejé la leyenda fiel a la lógica. ¿Cambiamos la lógica o la leyenda?
2. **Correo del aprobador**: hoy es uno por contrato. ¿Prefieres uno por persona (varios aprobadores por contrato)?
3. **Formato del COD_DEAF**: acepto letras, números y `. _ - /` hasta 40 caracteres. Confírmalo con códigos reales.
4. **Lector de Excel propio vs. SheetJS**: si prefieres la librería estándar (más compatible con archivos raros), se puede incrustar a costa de ~1 MB.
5. **Línea base de hitos por Excel**: no estaba en el encargo; hoy los hitos de línea base se cargan uno por uno en Configuración.
6. **Gantt de solo lectura** para Validador/Gabinete: hoy solo el IF lo ve (con edición); los demás tienen el desglose de cronograma de cada tarjeta.
7. **Importación atómica** en el artifact no es posible; solo en el backend. ¿Basta con el aviso actual?
8. **Datos antiguos sin motivo de resolución** al migrar al backend (ver 11.4).

### 11.7 Ampliación v10.8 — Pesos del avance (2026-10-02)

Pedido del dueño del proyecto: una interfaz de configuración para fijar el peso de cada contrato según sus sectores y subsectores.
Decisiones tomadas con él: **jerarquía contrato → sectores/subsectores** (las unidades que ya existen; sin nivel de partidas por ahora) y
**pesos en porcentaje que suma 100**.

- **Dónde:** Configuración → "Peso de cada contrato en el avance global" (suma 100% entre los contratos activos) y, en cada contrato de
  "Unidades y subsectores", la columna **Peso (%)** (suma 100% entre sus subsectores activos). La suma se muestra en vivo
  ("Suma: 90% · faltan 10%"); hay "Repartir en partes iguales" y "Guardar pesos". No se guarda si no suma exactamente 100%,
  si falta algún peso o si no es un número entre 0 y 100 con hasta 2 decimales (acepta coma). Un subsector desactivado conserva su peso pero no cuenta.
- **Cálculo (frontend `promedioAvance`, backend `promedio_ponderado`, misma regla):**
  - avance de un contrato = promedio de sus subsectores activos **ponderado por peso**;
  - avance global = promedio de los contratos **ponderado por el peso del contrato**;
  - si a algún elemento del conjunto le falta el peso, se usa **promedio simple** y la tarjeta lo dice ("promedio simple" / "ponderado por peso");
  - un subsector sin reporte aprobado **no cuenta como 0**: se re-normalizan los pesos entre los que sí tienen dato (igual que antes con el promedio simple).
- **Modelo:** `contratos.peso`, `unidades.peso` (número 0–100 o ausente). Backend: `Contrato.Peso`, `Unidad.Peso` (CHECK 0–100),
  `guardar_pesos_unidades`, `guardar_pesos_contratos` (todo o nada), `avance_contrato`, `avance_global`.
- **El demo** trae pesos de ejemplo (por eso, por ejemplo, la Red Aeroportuaria de ejemplo pasa de 55% a 60%).
- **Verificación:** frontend 181/181, backend 49/49.
- **Límites / decisiones abiertas:** (a) no hay nivel de *partidas*: si se necesita, el modelo pasa a árbol (contrato → sector → subsector → partida) y el
  avance se carga en el nivel más bajo; (b) los pesos no se cargan por Excel (solo desde la pantalla); (c) un subsector nuevo sin peso hace que el
  contrato vuelva al promedio simple hasta que se vuelvan a cuadrar los pesos; (d) "sin reporte = no cuenta" puede subestimar o sobrestimar el
  avance si hay unidades pesadas sin primer reporte (la alternativa es contarlas como 0%).

### 11.8 Ampliaciones v10.9 – v10.12 (2026-10-02)

Nuevas ideas del dueño del proyecto, trabajadas con commit por bloque y registradas en `CHANGELOG.md` (archivo nuevo, se actualiza en cada commit).

- **Registro de cambios auditable (v10.9).** Pestaña del administrador. Cada modificación de datos queda anotada en `audit/<cuenta>/cambios/<id>`
  (ruta que solo puede escribir la propia cuenta; igual que los recibos) con: hora, id del autor (nunca nombre), perfil, acción, entidad, contrato, detalle,
  el **antes → después** de cada campo y una **huella SHA-256** del contenido. La vista permite filtrar (qué, quién, texto, fechas), exportar a CSV (neutraliza `= + - @`)
  y marca "⚠ alterado" cualquier fila cuyo contenido ya no coincide con su huella; una anotación escrita a nombre de otra cuenta no se muestra.
  Se anota *después* de guardar el cambio; si el registro falla se avisa. Backend: la tabla `Auditoria` (solo anexar, fecha de la base) guarda antes → después
  en contratos, subsectores, hitos y permisos, y `listar_auditoria` (solo ADMIN) la expone con filtros.
  Límites: el artifact no puede impedir que una cuenta borre sus propias anotaciones (la plataforma no lo permite); el backend sí (triggers).
  La huella detecta ediciones, no borrados; el backend (`Auditoria`) sí es de solo anexar.
- **Ficha de problemáticas (v10.10).** "Actores relevantes" (antes Stakeholders; el campo guardado sigue llamándose `stakeholders`). Checklist con "+ Agregar acción" (una por línea,
  numeradas, quitables). Botón **Editar** para el autor o una jefatura del contrato: deja `edicion {autorId, ts}`, una nota automática en la bitácora, un recibo
  con huella (`problematica-<id>-editar`; la verificación de autoría usa ese recibo si la ficha fue editada) y la anotación en el Registro de cambios.
- **Dashboard (v10.11).** Semáforo a la izquierda y las tres cifras como tarjetas compactas a la derecha. Gantt y línea base de hitos muestran el peso de cada sector.
  *Duda pendiente*: no quedó claro si "agregar los pesos para los sectores" en Hitos pedía algo más que mostrarlos (el peso se edita en Configuración → Unidades y subsectores).
- **Permisos y correos (v10.12).** Ver `CHANGELOG.md` v10.12. Decisión: la asignación por correo es **explícita** (botón con vista previa), no automática al ingresar, para que cada
  cambio de acceso quede auditado y no dependa de que el correo de la cuenta coincida. El correo de la persona lo escribe el administrador (o lo trae el directorio).
  Pendiente: cargar *personas* por Excel (hoy se agregan una a una desde el directorio, porque `permisos/<uid>` se identifica por la cuenta, no por el correo).

### 11.9 v10.13 – v10.14: checklist editable y modo celular (2026-10-02)

- **Checklist de fichas ya creadas** (v10.13): "Editar checklist" en el detalle de cada ficha, para cualquier persona del contrato (antes solo autor o jefatura
  podían editar, y en el modo local las fichas de ejemplo eran de otra persona, por eso no aparecía el botón). Nota automática en la bitácora y Registro de cambios.
- **Modo celular** (v10.14). Criterio: *nada cortado ni escondido a la derecha*. Se verifica con un script que, para cada perfil y pestaña (y las ventanas
  emergentes), detecta scroll horizontal de página, elementos fuera de pantalla, contenido que exige deslizar, texto cortado, campos cuyo valor no cabe y
  placeholders cortados (`pruebas/test_frontend.py`, escenario H, `JS_RECORTES`). Decisiones: tablas → tarjetas por regla automática (`ajustarTablas`:
  si no cabe o un campo queda apretado; con histéresis para no oscilar); Gantt en lista en celular (`renderGanttLista`); banner no fijo en celular;
  pestañas en varias líneas en todo tamaño. Límite: verificado en Chromium (escritorio y emulación de ancho); no probado en un teléfono físico ni en Safari/iOS.


## 12. Diagramas de proceso para Bizagi (2026-10-07)

Pedido del dueño del proyecto para mostrar el flujo de trabajo a la consultora (que evalúa implementar la Bitácora en su
sistema, tras no poder montar servidor web ni motor SQL propios). Carpeta `bizagi\` (ver su `LEEME_BIZAGI.md`):
cinco diagramas BPMN 2.0 con carriles por perfil más un carril Sistema, generados por `generar_bpmn.py` a partir de las reglas
de las secciones 9–11. Bizagi Modeler no abre su formato propio (`.bpm`) desde fuera, por eso se entrega BPMN estándar
(Archivo → Importar) y, de respaldo, SVG/PNG. Verificado: XML bien formado, sin referencias rotas y cada elemento en su carril;
la importación real en Bizagi **no se pudo probar** (no está instalado en el equipo de desarrollo).

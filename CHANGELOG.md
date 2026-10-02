# Registro de cambios — Bitácora de Obra DGC

Aquí queda cada cambio y actualización del proyecto (herramienta, backend, pruebas y documentación), del más reciente al más antiguo.
**Se actualiza en cada commit.** El detalle técnico y las decisiones están en `DISENO_BITACORA_OBRA.md`; el registro crudo es `git log`.

> No confundir con el **Registro de cambios dentro de la herramienta** (pestaña del administrador): ese guarda quién modificó qué datos,
> y cuándo, mientras se usa la Bitácora. Este archivo guarda cómo evoluciona el **programa**.

Formato de cada entrada: versión · fecha · commit — qué cambió · pruebas.

---

## v10.12 · 2026-10-02 — Gestión de permisos para muchos contratos y cargas por correo
- **Gestión de permisos sin botones sueltos**: cada persona muestra un resumen ("12 contratos · 1 titular · 11 suplente" + los primeros nombres) y el botón **"Editar contratos…"**, que abre una ventana con **búsqueda** por nombre o COD_DEAF, filtros *Todos / Asignados / Sin asignar*, **"Marcar los visibles"**, **"Quitar los visibles"**, **"Quitar todos"**, contador y selector Titular/Suplente por contrato. Probado con 82 contratos.
- **Cargas con base en correos electrónicos**: el Excel/CSV de contratos acepta `CORREO_IF_TITULAR` y `CORREO_IF_SUPLENTE` (basta el nombre o el correo del titular). La tabla de Configuración también los muestra y edita.
- **Asignar contratos por correo** (Gestión de permisos): el sistema asigna a cada IF los contratos donde aparece su correo (titular o suplente), muestra primero qué agregaría, conserva lo que ya tenía y avisa de los correos de IF que aún no tienen persona. Cada cambio queda en el Registro de cambios.
- El directorio completa el correo de la persona cuando lo trae.
- Backend: `Contrato.CorreoIfTitular/CorreoIfSuplente`, `importar_contratos` con esos correos, `sincronizar_asignaciones_por_correo` (solo ADMIN, idempotente, auditada).
- Pruebas: frontend 239/239 · backend 58/58.

## v10.11 · 2026-10-02 — Dashboard más compacto y pesos visibles en Hitos
- **Tarjetas del dashboard**: "Avance global", "Hitos atrasados" y "Alertas escaladas / En revisión" dejan de estirarse a la altura de la tarjeta del semáforo. Ahora el semáforo (con su leyenda) va a la izquierda y las tres cifras son tarjetas compactas apiladas a la derecha; en teléfono quedan una bajo otra.
- **Hitos (Gantt)**: cada sector muestra su **peso** ("peso 70%") o "sin peso"; el peso se define en Configuración → Unidades y subsectores. En la línea base de hitos (Configuración) el selector de sector también muestra el peso.
- Pruebas: frontend 218/218 · backend 54/54.

## v10.10 · 2026-10-02 — Ficha de problemáticas: actores relevantes, checklist y edición
- "Stakeholders" pasa a llamarse **"Actores relevantes"** (formulario, tarjeta y ficha; el dato guardado sigue siendo el mismo).
- **Checklist de acciones para subsanar**: en vez de un cuadro "una tarea por línea", cada acción aparece en su línea numerada, con botón **"+ Agregar acción"** (o Enter) y botón × para quitarla. Lo escrito sin agregar se agrega al guardar.
- **Botón "✎ Editar"** en cada ficha (autor o jefatura del contrato): permite cambiar unidad, título, descripción, impacto, actores, checklist (renombrar, marcar hecha, quitar, agregar), riesgo, vencimiento y ayuda requerida.
- Cada edición deja: quién y cuándo editó (solo el id), una nota automática en la bitácora de la ficha, un recibo con huella (la verificación de autoría sigue funcionando) y una anotación en el Registro de cambios con el antes → después.
- Pruebas: frontend 216/216 · backend 54/54.

## v10.9 · 2026-10-02 — Registro de cambios auditable (dentro de la herramienta) y CHANGELOG
- **Pestaña "Registro de cambios"** (administrador): quién modificó qué, cuándo y el **antes → después** de cada campo; filtros por qué, quién, texto y fechas; "Ver más"; exportación a CSV (neutraliza fórmulas de Excel).
- Se anotan contratos, subsectores, hitos de línea base, permisos, pesos, cargas masivas, solicitudes (enviar, cancelar, aprobar, rechazar), alertas a Gabinete y problemáticas (crear, mover, resolver, tareas, notas, eliminar).
- Cada anotación se guarda en `audit/<cuenta>/cambios` (ruta que solo escribe la propia cuenta), con id de usuario (nunca nombre) y una **huella SHA-256**: una fila alterada se marca "⚠ alterado"; una anotación a nombre de otra cuenta no se muestra.
- Backend: la tabla `Auditoria` (solo anexar, fecha de la base) ahora guarda el antes → después en contratos, subsectores, hitos y permisos; nuevo `listar_auditoria` (solo ADMIN, con filtros).
- Nuevo `CHANGELOG.md` (este archivo), con el historial retroactivo.
- Pruebas: frontend 200/200 · backend 54/54.

## v10.8 · 2026-10-02 · `cf54a60` — Pesos del avance
- Pesos en porcentaje (suma 100) de cada contrato en el avance global y de cada sector/subsector dentro de su contrato; vista de configuración con suma en vivo, "Repartir en partes iguales" y validación.
- El avance se calcula ponderado cuando todos tienen peso (si no, promedio simple, indicado en la tarjeta); los sin reporte no cuentan como 0.
- Backend: `Peso` en contrato y unidad (CHECK 0–100), `guardar_pesos_*`, `avance_contrato`, `avance_global`. Demo con pesos de ejemplo.
- Pruebas: frontend 181/181 · backend 49/49.

## v10.7 · 2026-10-02 · `3b3d4c4` — Cierre de la v10
- Prueba permanente del entregable `Bitacora de Obra.html` abierto desde otra carpeta (logo incrustado, sin errores).
- Gantt y selector de contrato legibles en teléfono. Documento de diseño: sección 11.
- Pruebas: frontend 164/164 · backend 40/40.

## v10.6 · 2026-10-02 · `65491aa` — Dashboard: semáforo
- La tarjeta "Semáforo" muestra tres cifras con color y etiqueta ("2 contratos en rojo"), leyenda de cálculo y filtro por color (Contratos y Gabinete).

## v10.5 · 2026-10-02 · `9406241` — Administrador: COD_DEAF, cargas por Excel/CSV y subsectores
- Contrato con `codDeaf` único, IF titular/suplente y correo del aprobador.
- Carga masiva de contratos y de subsectores desde `.xlsx` o `.csv` sin servidor ni librerías externas, con plantillas, validación y vista previa con errores por fila (todo o nada).
- Subsectores en vista por contrato (alta y desactivación lógica). Backend: `importar_contratos` / `importar_unidades` atómicos, índices únicos.

## v10.4 · 2026-10-02 · `3d8b7e2` — Gabinete: últimas aprobaciones
- Tabla "Últimas aprobaciones" (solo datos oficiales), con "Ver más" y filtros. La fecha anterior de un hito sin fecha vigente es la contractual.

## v10.3 · 2026-10-02 · `fb1c4f7` — Validador
- Solicitudes con Contrato / Sector / Hito a modificar en grande; "Avisar por correo al IF" (`mailto:`) tras aprobar o rechazar.

## v10.2 · 2026-10-02 · `18936c3` — Pantalla del IF
- Titular/Suplente por contrato y selector de contrato activo; "Cargar avance" con historial; "Modificar hitos" con carta Gantt y popup de edición.
- Campanita de notificaciones con `leidoTs` por usuario; `mailto:` al aprobador; motivo obligatorio al resolver una problemática y ficha completa en Resueltas.

## v10.1 · 2026-10-02 · `18ee9c3` — Banner y ancho de pantalla
- Banner en dos zonas con logo de 64 px; contenido hasta 1.600 px; usable en teléfono. Ruta de Chrome de las pruebas configurable (`CHROME`).

## v9 · 2026-10-02 · `0a27fb0` — Modo local
- La herramienta abre desde disco sin claude.ai (datos en el navegador, con datos de ejemplo). Archivo único `Bitacora de Obra.html`.

## v8 · 2026-10-01
- Perfiles (IF/AIF, Validador, Administrador, Gabinete), flujo de aprobación, datos oficiales, radar de hitos críticos, logo DGC 2026 y demo.

## v7 · 2026-10-01
- Auditoría y blindaje de seguridad (XSS, hashes, recibos de auditoría, backend SQL parametrizado).

## v1–v6 · 2026-09-28 a 2026-09-29
- Maqueta inicial, modelo contrato → unidad, hitos, problemáticas con tablero y bitácora. Ver `DISENO_BITACORA_OBRA.md`, sección 5.

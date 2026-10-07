# Diagramas de proceso (BPMN 2.0 para Bizagi Modeler)

Generados el 2026-10-07 a partir de `DISENO_BITACORA_OBRA.md` (secciones 9–11) y `backend/validar.py`.
Cada diagrama tiene carriles por perfil (IF/AIF, Validador/Jefe de Depto., Administrador, Gabinete) y un carril
**Sistema** para los pasos automáticos. Las tareas con ☺ son manuales; las con ⚙ las hace el sistema. El detalle de
cada paso está en la *documentación* del elemento (en Bizagi: propiedades → Descripción).

| Archivo | Proceso |
|---|---|
| `01_avance_fisico` | El IF propone un avance %; el Validador aprueba o rechaza; Gabinete ve solo lo aprobado |
| `02_modificacion_hitos` | Nueva fecha programada o fecha real desde el Gantt, con aprobación |
| `03_problematicas_y_alertas` | Detectado → En gestión → Escalado → Resuelto; alerta a Gabinete |
| `04_carga_y_permisos_admin` | Carga de contratos/subsectores por Excel y asignación de permisos |
| `05_mapa_general` | Vista de una página de todo el flujo |

## Cómo abrirlos en Bizagi Modeler
1. **Archivo → Importar → BPMN** (o *Abrir*) y elegir el `.bpmn`.
2. Si el orden de las flechas se ve distinto, ajustar a mano: el modelo (elementos, carriles y conexiones) es correcto.
3. Cada `.png` y `.svg` es el mismo diagrama ya dibujado, por si no hay Bizagi a mano o no importa bien.

## Regenerar
`python generar_bpmn.py` (crea `.bpmn` y `.svg`) y `python renderizar_png.py` (crea `.png`; usa el Chrome del sistema).
Si cambia el flujo en `DISENO_BITACORA_OBRA.md`, hay que cambiarlo también en `generar_bpmn.py`.

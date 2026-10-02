/* =====================================================================
   Bitácora de Obra — esquema SQL Server (espacio institucional)
   Actualizado al: 2026-10-02 (v10: titular/suplente, correos, motivo de resolución, avisos leídos)

   NO EJECUTAR sin revisión del DBA: crea un esquema, roles y políticas de
   seguridad por filas. Se ejecuta con sqlcmd o SSMS (usa separadores GO).
   No fue probado contra SQL Server; el mismo modelo sí está probado en SQLite
   (pruebas/test_backend.py, 23 pruebas).

   Seguridad en capas:
   1. Identidad: SSO institucional (AD / Entra ID). Sin contraseñas propias.
   2. Rol de aplicación con mínimo privilegio (sin DDL, sin sysadmin).
   3. Seguridad por filas (RLS), según el contexto que fija la aplicación:
        usuario_id, rol  (EXEC sp_set_session_context ...; ver repositorio.py)
      - Datos operativos (solicitudes, problemáticas): IF/VALIDADOR solo sus
        contratos asignados; ADMIN todos; GABINETE ninguno.
      - Datos oficiales: lectura para GABINETE y ADMIN (todos) e IF/VALIDADOR
        (sus contratos); escritura solo VALIDADOR (sus contratos) y ADMIN.
   4. La propia base impide: borrar (solo eliminación lógica), aprobarse a sí
      mismo, rechazar sin comentario, editar historiales y auditoría.
   ===================================================================== */

CREATE SCHEMA bitacora;
GO

-- ---------------------------------------------------------------- identidad y permisos
CREATE TABLE bitacora.Usuario (
  Id     NVARCHAR(128) NOT NULL PRIMARY KEY,     -- identificador del SSO (objectId / UPN)
  Nombre NVARCHAR(150) NOT NULL,
  Email  NVARCHAR(254) NULL,
  Activo BIT NOT NULL DEFAULT 1
);
CREATE TABLE bitacora.Permiso (
  UsuarioId      NVARCHAR(128) NOT NULL PRIMARY KEY REFERENCES bitacora.Usuario(Id),
  Rol            VARCHAR(10)   NOT NULL CHECK (Rol IN ('IF', 'VALIDADOR', 'ADMIN', 'GABINETE')),
  Activo         BIT           NOT NULL DEFAULT 1,
  ActualizadoPor NVARCHAR(128) NOT NULL REFERENCES bitacora.Usuario(Id),
  ActualizadoEn  DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE bitacora.Contrato (
  Id              NVARCHAR(64)  NOT NULL PRIMARY KEY,
  Nombre          NVARCHAR(150) NOT NULL CHECK (LEN(Nombre) >= 1),
  UnidadLabel     NVARCHAR(50)  NOT NULL DEFAULT N'',
  CodDeaf         NVARCHAR(40)  NULL,                   -- código DEAF del contrato (único)
  InspectorNombre NVARCHAR(150) NOT NULL DEFAULT N'',   -- IF titular (referencial)
  InspectorSuplente NVARCHAR(150) NOT NULL DEFAULT N'', -- IF suplente (referencial)
  CorreoAprobador NVARCHAR(254) NOT NULL DEFAULT N'',   -- a esta dirección se abre el aviso (mailto:)
  Activo          BIT           NOT NULL DEFAULT 1,
  CreadoEn        DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE bitacora.UsuarioContrato (
  UsuarioId  NVARCHAR(128) NOT NULL REFERENCES bitacora.Usuario(Id),
  ContratoId NVARCHAR(64)  NOT NULL REFERENCES bitacora.Contrato(Id),
  RolContrato VARCHAR(10)  NOT NULL DEFAULT 'titular' CHECK (RolContrato IN ('titular', 'suplente')),  -- un IF suele tener 2
  Activo     BIT           NOT NULL DEFAULT 1,
  PRIMARY KEY (UsuarioId, ContratoId)
);
CREATE TABLE bitacora.Sesion (
  TokenHash CHAR(64)      NOT NULL PRIMARY KEY,  -- SHA-256 del token; el token nunca se guarda
  UsuarioId NVARCHAR(128) NOT NULL REFERENCES bitacora.Usuario(Id),
  Rol       VARCHAR(10)   NOT NULL CHECK (Rol IN ('IF', 'VALIDADOR', 'ADMIN', 'GABINETE')),
  CreadaEn  DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME(),
  ExpiraEn  DATETIME2(3)  NOT NULL,
  Revocada  BIT           NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------- estructura y línea base
CREATE TABLE bitacora.Unidad (
  Id         NVARCHAR(64)  NOT NULL PRIMARY KEY,
  ContratoId NVARCHAR(64)  NOT NULL REFERENCES bitacora.Contrato(Id),
  Nombre     NVARCHAR(150) NOT NULL CHECK (LEN(Nombre) >= 1),
  Activo     BIT           NOT NULL DEFAULT 1
);
CREATE TABLE bitacora.Hito (
  Id               NVARCHAR(64)  NOT NULL PRIMARY KEY,
  ContratoId       NVARCHAR(64)  NOT NULL REFERENCES bitacora.Contrato(Id),
  UnidadId         NVARCHAR(64)  NOT NULL REFERENCES bitacora.Unidad(Id),
  Nombre           NVARCHAR(150) NOT NULL DEFAULT N'',
  Tipo             NVARCHAR(30)  NOT NULL CHECK (Tipo IN (N'Ingeniería', N'Inicio Físico', N'PSP', N'PSD', N'Informe de avance', N'Fase de construcción')),
  FechaContractual DATE          NOT NULL,
  IsDeleted        BIT           NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------- flujo de aprobación
CREATE TABLE bitacora.Solicitud (
  Id                 NVARCHAR(64)   NOT NULL PRIMARY KEY,
  ContratoId         NVARCHAR(64)   NOT NULL REFERENCES bitacora.Contrato(Id),
  Tipo               VARCHAR(20)    NOT NULL CHECK (Tipo IN ('avance', 'fecha_programada', 'fecha_real')),
  UnidadId           NVARCHAR(64)   NULL REFERENCES bitacora.Unidad(Id),
  HitoId             NVARCHAR(64)   NULL REFERENCES bitacora.Hito(Id),
  ValorAvance        TINYINT        NULL CHECK (ValorAvance BETWEEN 0 AND 100),
  ValorFecha         DATE           NULL,
  VigenteAvance      TINYINT        NULL,
  VigenteFecha       DATE           NULL,
  FechaReporte       DATE           NOT NULL,
  Nota               NVARCHAR(4000) NOT NULL DEFAULT N'',
  Estado             VARCHAR(22)    NOT NULL CHECK (Estado IN ('BORRADOR', 'PENDIENTE_APROBACION', 'APROBADO', 'RECHAZADO', 'ELIMINADO')),
  IsDeleted          BIT            NOT NULL DEFAULT 0,
  AutorId            NVARCHAR(128)  NOT NULL REFERENCES bitacora.Usuario(Id),
  CreadoEn           DATETIME2(3)   NOT NULL DEFAULT SYSUTCDATETIME(),
  EnviadoEn          DATETIME2(3)   NULL,
  RevisorId          NVARCHAR(128)  NULL REFERENCES bitacora.Usuario(Id),
  RevisadoEn         DATETIME2(3)   NULL,
  ComentarioRevision NVARCHAR(2000) NOT NULL DEFAULT N'',
  CONSTRAINT CK_Solicitud_Valor CHECK ((Tipo = 'avance' AND UnidadId IS NOT NULL AND ValorAvance IS NOT NULL AND HitoId IS NULL)
                                    OR (Tipo <> 'avance' AND HitoId IS NOT NULL AND ValorFecha IS NOT NULL AND UnidadId IS NULL)),
  CONSTRAINT CK_Solicitud_NoAutoaprobar CHECK (RevisorId IS NULL OR RevisorId <> AutorId),
  CONSTRAINT CK_Solicitud_RechazoConComentario CHECK (Estado <> 'RECHAZADO' OR LEN(LTRIM(RTRIM(ComentarioRevision))) >= 5),
  CONSTRAINT CK_Solicitud_Eliminado CHECK ((Estado = 'ELIMINADO' AND IsDeleted = 1) OR (Estado <> 'ELIMINADO' AND IsDeleted = 0))
);
CREATE TABLE bitacora.SolicitudHistorial (                 -- solo anexar
  Id          BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  SolicitudId NVARCHAR(64)   NOT NULL REFERENCES bitacora.Solicitud(Id),
  ContratoId  NVARCHAR(64)   NOT NULL REFERENCES bitacora.Contrato(Id),
  Estado      VARCHAR(22)    NOT NULL,
  ActorId     NVARCHAR(128)  NOT NULL REFERENCES bitacora.Usuario(Id),
  Comentario  NVARCHAR(2000) NOT NULL DEFAULT N'',
  OcurridoEn  DATETIME2(3)   NOT NULL DEFAULT SYSUTCDATETIME()
);

-- ---------------------------------------------------------------- datos oficiales
CREATE TABLE bitacora.AvanceOficial (
  UnidadId     NVARCHAR(64)  NOT NULL PRIMARY KEY REFERENCES bitacora.Unidad(Id),
  ContratoId   NVARCHAR(64)  NOT NULL REFERENCES bitacora.Contrato(Id),
  Valor        TINYINT       NOT NULL CHECK (Valor BETWEEN 0 AND 100),
  FechaReporte DATE          NOT NULL,
  SolicitudId  NVARCHAR(64)  NULL REFERENCES bitacora.Solicitud(Id),
  RevisorId    NVARCHAR(128) NULL REFERENCES bitacora.Usuario(Id),
  AprobadoEn   DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE bitacora.HitoOficial (
  HitoId       NVARCHAR(64)  NOT NULL PRIMARY KEY REFERENCES bitacora.Hito(Id),
  ContratoId   NVARCHAR(64)  NOT NULL REFERENCES bitacora.Contrato(Id),
  FechaVigente DATE          NULL,
  FechaReal    DATE          NULL,
  RevisorId    NVARCHAR(128) NULL REFERENCES bitacora.Usuario(Id),
  AprobadoEn   DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE bitacora.HistorialOficial (                   -- solo anexar
  Id            BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  ContratoId    NVARCHAR(64)   NOT NULL REFERENCES bitacora.Contrato(Id),
  SolicitudId   NVARCHAR(64)   NULL REFERENCES bitacora.Solicitud(Id),
  Campo         VARCHAR(20)    NOT NULL CHECK (Campo IN ('avance', 'fecha_programada', 'fecha_real')),
  Ref           NVARCHAR(64)   NOT NULL,
  ValorAnterior NVARCHAR(20)   NULL,
  ValorNuevo    NVARCHAR(20)   NOT NULL,
  FechaReporte  DATE           NULL,
  Nota          NVARCHAR(4000) NOT NULL DEFAULT N'',
  AutorId       NVARCHAR(128)  NULL REFERENCES bitacora.Usuario(Id),
  RevisorId     NVARCHAR(128)  NULL REFERENCES bitacora.Usuario(Id),
  Migrado       BIT            NOT NULL DEFAULT 0,
  AprobadoEn    DATETIME2(3)   NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE bitacora.AlertaGabinete (
  ProblematicaId NVARCHAR(64)  NOT NULL PRIMARY KEY,
  ContratoId     NVARCHAR(64)  NOT NULL REFERENCES bitacora.Contrato(Id),
  Titulo         NVARCHAR(200) NOT NULL,
  NivelRiesgo    VARCHAR(8)    NULL CHECK (NivelRiesgo IN ('Extremo', 'Alto', 'Medio', 'Bajo')),
  Estado         VARCHAR(12)   NOT NULL CHECK (Estado IN ('detectado', 'en_gestion', 'escalado', 'resuelto')),
  Escalamiento   NVARCHAR(200) NOT NULL DEFAULT N'',
  RevisorId      NVARCHAR(128) NOT NULL REFERENCES bitacora.Usuario(Id),
  PublicadoEn    DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME(),
  IsDeleted      BIT           NOT NULL DEFAULT 0,
  RetiradoEn     DATETIME2(3)  NULL
);

-- ---------------------------------------------------------------- problemáticas
CREATE TABLE bitacora.Problematica (
  Id               NVARCHAR(64)   NOT NULL PRIMARY KEY,
  ContratoId       NVARCHAR(64)   NOT NULL REFERENCES bitacora.Contrato(Id),
  UnidadId         NVARCHAR(64)   NULL REFERENCES bitacora.Unidad(Id),
  Titulo           NVARCHAR(200)  NOT NULL CHECK (LEN(Titulo) >= 1),
  Descripcion      NVARCHAR(4000) NOT NULL CHECK (LEN(Descripcion) >= 1),
  Impacto          NVARCHAR(4000) NOT NULL DEFAULT N'',
  NivelRiesgo      VARCHAR(8)     NULL CHECK (NivelRiesgo IN ('Extremo', 'Alto', 'Medio', 'Bajo')),
  Estado           VARCHAR(12)    NOT NULL DEFAULT 'detectado' CHECK (Estado IN ('detectado', 'en_gestion', 'escalado', 'resuelto')),
  FechaVencimiento DATE           NULL,
  AutorId          NVARCHAR(128)  NOT NULL REFERENCES bitacora.Usuario(Id),
  CreadoEn         DATETIME2(3)   NOT NULL DEFAULT SYSUTCDATETIME(),
  ResueltaEn       DATETIME2(3)   NULL,
  ResolucionTexto  NVARCHAR(4000) NULL,                    -- cómo / por qué se resolvió
  ResolucionPorId  NVARCHAR(128)  NULL REFERENCES bitacora.Usuario(Id),
  IsDeleted        BIT            NOT NULL DEFAULT 0,
  CONSTRAINT CK_Problematica_ResueltaConMotivo            -- no se resuelve sin motivo
    CHECK (Estado <> 'resuelto' OR LEN(LTRIM(RTRIM(ISNULL(ResolucionTexto, N'')))) >= 5)
);
CREATE TABLE bitacora.ProblematicaResolucionPrevia (        -- solo anexar: resoluciones de una problemática reabierta
  Id             BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  ProblematicaId NVARCHAR(64)   NOT NULL REFERENCES bitacora.Problematica(Id),
  ContratoId     NVARCHAR(64)   NOT NULL REFERENCES bitacora.Contrato(Id),
  Texto          NVARCHAR(4000) NOT NULL,
  AutorId        NVARCHAR(128)  NULL REFERENCES bitacora.Usuario(Id),
  ResueltaEn     DATETIME2(3)   NULL
);
CREATE TABLE bitacora.LecturaNotificacion (                 -- avisos del IF: lo anterior a LeidoEn ya fue leído
  UsuarioId NVARCHAR(128) NOT NULL PRIMARY KEY REFERENCES bitacora.Usuario(Id),
  LeidoEn   DATETIME2(3)  NOT NULL
);
CREATE TABLE bitacora.ProblematicaStakeholder (
  ProblematicaId NVARCHAR(64) NOT NULL REFERENCES bitacora.Problematica(Id),
  ContratoId     NVARCHAR(64) NOT NULL REFERENCES bitacora.Contrato(Id),
  Nombre         NVARCHAR(80) NOT NULL,
  PRIMARY KEY (ProblematicaId, Nombre)
);
CREATE TABLE bitacora.ProblematicaEscalamiento (
  ProblematicaId NVARCHAR(64) NOT NULL REFERENCES bitacora.Problematica(Id),
  ContratoId     NVARCHAR(64) NOT NULL REFERENCES bitacora.Contrato(Id),
  Instancia      NVARCHAR(40) NOT NULL CHECK (Instancia IN (N'Jefe de División', N'Directora', N'Jurídica', N'Otro')),
  PRIMARY KEY (ProblematicaId, Instancia)
);
CREATE TABLE bitacora.ProblematicaTarea (
  Id             NVARCHAR(64)  NOT NULL PRIMARY KEY,
  ProblematicaId NVARCHAR(64)  NOT NULL REFERENCES bitacora.Problematica(Id),
  ContratoId     NVARCHAR(64)  NOT NULL REFERENCES bitacora.Contrato(Id),
  Texto          NVARCHAR(300) NOT NULL CHECK (LEN(Texto) >= 1),
  Hecho          BIT           NOT NULL DEFAULT 0,
  Orden          INT           NOT NULL
);
CREATE TABLE bitacora.ProblematicaNota (                   -- solo anexar
  Id             NVARCHAR(64)   NOT NULL PRIMARY KEY,
  ProblematicaId NVARCHAR(64)   NOT NULL REFERENCES bitacora.Problematica(Id),
  ContratoId     NVARCHAR(64)   NOT NULL REFERENCES bitacora.Contrato(Id),
  Texto          NVARCHAR(2000) NOT NULL CHECK (LEN(Texto) >= 1),
  AutorId        NVARCHAR(128)  NOT NULL REFERENCES bitacora.Usuario(Id),
  CreadoEn       DATETIME2(3)   NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE bitacora.Auditoria (                          -- solo anexar
  Id         BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  OcurridoEn DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME(),
  ContratoId NVARCHAR(64)  NULL,
  ActorId    NVARCHAR(128) NOT NULL,
  Rol        VARCHAR(10)   NOT NULL,
  Accion     VARCHAR(30)   NOT NULL,
  Entidad    VARCHAR(40)   NOT NULL,
  EntidadId  NVARCHAR(64)  NULL,
  Detalle    NVARCHAR(500) NOT NULL DEFAULT N''
);

-- Únicos sin distinguir mayúsculas SOLO si la intercalación (collation) de la base es _CI_; el DBA debe confirmarlo.
CREATE UNIQUE INDEX UX_Contrato_CodDeaf ON bitacora.Contrato(CodDeaf) WHERE CodDeaf IS NOT NULL;
CREATE UNIQUE INDEX UX_Unidad_Contrato_Nombre ON bitacora.Unidad(ContratoId, Nombre);
CREATE INDEX IX_UsuarioContrato_Contrato ON bitacora.UsuarioContrato(ContratoId) INCLUDE (Activo);
CREATE INDEX IX_Solicitud_Contrato       ON bitacora.Solicitud(ContratoId, Estado);
CREATE INDEX IX_HistOf_Contrato          ON bitacora.HistorialOficial(ContratoId, AprobadoEn DESC);
CREATE INDEX IX_Problematica_Contrato    ON bitacora.Problematica(ContratoId, Estado);
GO

/* ---------- Seguridad por filas (RLS) ---------- */
CREATE FUNCTION bitacora.fn_Asignado (@ContratoId NVARCHAR(64))
RETURNS TABLE WITH SCHEMABINDING AS RETURN
  SELECT 1 AS Ok FROM bitacora.UsuarioContrato uc
  WHERE uc.UsuarioId = CAST(SESSION_CONTEXT(N'usuario_id') AS NVARCHAR(128)) AND uc.ContratoId = @ContratoId AND uc.Activo = 1;
GO
-- Datos operativos: ADMIN todos; IF/VALIDADOR sus contratos; GABINETE nada.
CREATE FUNCTION bitacora.fn_Operativo (@ContratoId NVARCHAR(64))
RETURNS TABLE WITH SCHEMABINDING AS RETURN
  SELECT 1 AS Ok
  WHERE CAST(SESSION_CONTEXT(N'rol') AS VARCHAR(10)) = 'ADMIN'
     OR (CAST(SESSION_CONTEXT(N'rol') AS VARCHAR(10)) IN ('IF', 'VALIDADOR') AND EXISTS (SELECT 1 FROM bitacora.fn_Asignado(@ContratoId)));
GO
-- Lectura oficial: ADMIN y GABINETE todos; IF/VALIDADOR sus contratos.
CREATE FUNCTION bitacora.fn_LecturaOficial (@ContratoId NVARCHAR(64))
RETURNS TABLE WITH SCHEMABINDING AS RETURN
  SELECT 1 AS Ok
  WHERE CAST(SESSION_CONTEXT(N'rol') AS VARCHAR(10)) IN ('ADMIN', 'GABINETE')
     OR (CAST(SESSION_CONTEXT(N'rol') AS VARCHAR(10)) IN ('IF', 'VALIDADOR') AND EXISTS (SELECT 1 FROM bitacora.fn_Asignado(@ContratoId)));
GO
-- Escritura oficial: ADMIN todos; VALIDADOR sus contratos. Nadie más.
CREATE FUNCTION bitacora.fn_EscrituraOficial (@ContratoId NVARCHAR(64))
RETURNS TABLE WITH SCHEMABINDING AS RETURN
  SELECT 1 AS Ok
  WHERE CAST(SESSION_CONTEXT(N'rol') AS VARCHAR(10)) = 'ADMIN'
     OR (CAST(SESSION_CONTEXT(N'rol') AS VARCHAR(10)) = 'VALIDADOR' AND EXISTS (SELECT 1 FROM bitacora.fn_Asignado(@ContratoId)));
GO
-- Cada cuenta solo ve y escribe lo suyo (avisos leídos).
CREATE FUNCTION bitacora.fn_Propio (@UsuarioId NVARCHAR(128))
RETURNS TABLE WITH SCHEMABINDING AS RETURN
  SELECT 1 AS Ok WHERE @UsuarioId = CAST(SESSION_CONTEXT(N'usuario_id') AS NVARCHAR(128));
GO
-- Solo ADMIN (permisos, asignaciones, línea base).
CREATE FUNCTION bitacora.fn_SoloAdmin (@Cualquiera NVARCHAR(128))
RETURNS TABLE WITH SCHEMABINDING AS RETURN
  SELECT 1 AS Ok WHERE CAST(SESSION_CONTEXT(N'rol') AS VARCHAR(10)) = 'ADMIN';
GO

CREATE SECURITY POLICY bitacora.PoliticaOperativa
  ADD FILTER PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.Solicitud,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.Solicitud AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.Solicitud AFTER UPDATE,
  ADD FILTER PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.SolicitudHistorial,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.SolicitudHistorial AFTER INSERT,
  ADD FILTER PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.Problematica,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.Problematica AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.Problematica AFTER UPDATE,
  ADD FILTER PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaStakeholder,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaStakeholder AFTER INSERT,
  ADD FILTER PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaEscalamiento,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaEscalamiento AFTER INSERT,
  ADD FILTER PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaTarea,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaTarea AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaTarea AFTER UPDATE,
  ADD FILTER PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaNota,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaNota AFTER INSERT,
  ADD FILTER PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaResolucionPrevia,
  ADD BLOCK  PREDICATE bitacora.fn_Operativo(ContratoId) ON bitacora.ProblematicaResolucionPrevia AFTER INSERT
  WITH (STATE = ON);
GO
CREATE SECURITY POLICY bitacora.PoliticaPropia
  ADD FILTER PREDICATE bitacora.fn_Propio(UsuarioId) ON bitacora.LecturaNotificacion,
  ADD BLOCK  PREDICATE bitacora.fn_Propio(UsuarioId) ON bitacora.LecturaNotificacion AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_Propio(UsuarioId) ON bitacora.LecturaNotificacion AFTER UPDATE
  WITH (STATE = ON);
GO
CREATE SECURITY POLICY bitacora.PoliticaOficial
  ADD FILTER PREDICATE bitacora.fn_LecturaOficial(ContratoId)   ON bitacora.Unidad,
  ADD FILTER PREDICATE bitacora.fn_LecturaOficial(ContratoId)   ON bitacora.Hito,
  ADD FILTER PREDICATE bitacora.fn_LecturaOficial(ContratoId)   ON bitacora.AvanceOficial,
  ADD BLOCK  PREDICATE bitacora.fn_EscrituraOficial(ContratoId) ON bitacora.AvanceOficial AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_EscrituraOficial(ContratoId) ON bitacora.AvanceOficial AFTER UPDATE,
  ADD FILTER PREDICATE bitacora.fn_LecturaOficial(ContratoId)   ON bitacora.HitoOficial,
  ADD BLOCK  PREDICATE bitacora.fn_EscrituraOficial(ContratoId) ON bitacora.HitoOficial AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_EscrituraOficial(ContratoId) ON bitacora.HitoOficial AFTER UPDATE,
  ADD FILTER PREDICATE bitacora.fn_LecturaOficial(ContratoId)   ON bitacora.HistorialOficial,
  ADD BLOCK  PREDICATE bitacora.fn_EscrituraOficial(ContratoId) ON bitacora.HistorialOficial AFTER INSERT,
  ADD FILTER PREDICATE bitacora.fn_LecturaOficial(ContratoId)   ON bitacora.AlertaGabinete,
  ADD BLOCK  PREDICATE bitacora.fn_EscrituraOficial(ContratoId) ON bitacora.AlertaGabinete AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_EscrituraOficial(ContratoId) ON bitacora.AlertaGabinete AFTER UPDATE,
  ADD BLOCK  PREDICATE bitacora.fn_SoloAdmin(UsuarioId)          ON bitacora.Permiso AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_SoloAdmin(UsuarioId)          ON bitacora.Permiso AFTER UPDATE,
  ADD BLOCK  PREDICATE bitacora.fn_SoloAdmin(UsuarioId)          ON bitacora.UsuarioContrato AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_SoloAdmin(UsuarioId)          ON bitacora.UsuarioContrato AFTER UPDATE,
  ADD BLOCK  PREDICATE bitacora.fn_SoloAdmin(ContratoId)         ON bitacora.Hito AFTER INSERT,
  ADD BLOCK  PREDICATE bitacora.fn_SoloAdmin(ContratoId)         ON bitacora.Hito AFTER UPDATE
  WITH (STATE = ON);
GO

/* ---------- Rol de aplicación: mínimo privilegio ----------
   La aplicación se conecta con una cuenta de servicio dedicada (AD), miembro SOLO
   de este rol. Nunca sysadmin ni db_owner. Ninguna tabla admite DELETE. */
CREATE ROLE bitacora_app;
GRANT SELECT                 ON bitacora.Usuario                  TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.Permiso                  TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.UsuarioContrato          TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.Sesion                   TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.Contrato                 TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.Unidad                   TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.Hito                     TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.Solicitud                TO bitacora_app;
GRANT SELECT, INSERT         ON bitacora.SolicitudHistorial       TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.AvanceOficial            TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.HitoOficial              TO bitacora_app;
GRANT SELECT, INSERT         ON bitacora.HistorialOficial         TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.AlertaGabinete           TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.Problematica             TO bitacora_app;
GRANT SELECT, INSERT         ON bitacora.ProblematicaStakeholder  TO bitacora_app;
GRANT SELECT, INSERT         ON bitacora.ProblematicaEscalamiento TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.ProblematicaTarea        TO bitacora_app;
GRANT SELECT, INSERT         ON bitacora.ProblematicaNota         TO bitacora_app;
GRANT SELECT, INSERT         ON bitacora.ProblematicaResolucionPrevia TO bitacora_app;
GRANT SELECT, INSERT, UPDATE ON bitacora.LecturaNotificacion      TO bitacora_app;
GRANT INSERT                 ON bitacora.Auditoria                TO bitacora_app;
DENY  DELETE ON SCHEMA::bitacora TO bitacora_app;                 -- nada se borra físicamente
DENY  UPDATE ON bitacora.SolicitudHistorial TO bitacora_app;      -- historiales y auditoría: solo anexar
DENY  UPDATE ON bitacora.HistorialOficial   TO bitacora_app;
DENY  UPDATE ON bitacora.ProblematicaNota   TO bitacora_app;
DENY  UPDATE ON bitacora.ProblematicaResolucionPrevia TO bitacora_app;
DENY  UPDATE ON bitacora.Auditoria          TO bitacora_app;
GO

/* Usuario de base de datos de la aplicación (ajustar al login que entregue el DBA):
   CREATE USER [DOMINIO\svc_bitacora] FROM LOGIN [DOMINIO\svc_bitacora] WITH DEFAULT_SCHEMA = bitacora;
   ALTER ROLE bitacora_app ADD MEMBER [DOMINIO\svc_bitacora];
   DEFAULT_SCHEMA = bitacora es necesario: repositorio.py usa nombres de tabla sin prefijo.
   Con connection pooling, sp_reset_connection limpia el contexto de sesión al reutilizar
   la conexión: el usuario y rol de una petición nunca se heredan a otra. */

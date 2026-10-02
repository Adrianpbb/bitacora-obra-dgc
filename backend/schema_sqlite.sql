-- Bitácora de Obra — esquema SQLite (opción liviana si el hosting DGC corre backend propio)
-- Actualizado al: 2026-10-02 (v10: titular/suplente, correos, motivo de resolución, avisos leídos)
--
-- SQLite no tiene seguridad por filas: el alcance por contrato lo impone repositorio.py
-- (toda consulta filtra por los contratos asignados a la sesión). La base, por su parte,
-- garantiza por sí misma:
--   * Nada se borra físicamente (triggers BEFORE DELETE): eliminación lógica con IsDeleted.
--   * Nadie aprueba ni rechaza su propia solicitud (CHECK RevisorId <> AutorId).
--   * No hay rechazo sin comentario (CHECK sobre ComentarioRevision).
--   * Historiales y auditoría son de solo anexar.
--   * Las fechas de auditoría las pone la base (DEFAULT), nunca el cliente.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- identidad y permisos
CREATE TABLE IF NOT EXISTS Usuario (
  Id     TEXT PRIMARY KEY CHECK (length(Id) BETWEEN 1 AND 128),   -- identificador del SSO (AD/Entra ID)
  Nombre TEXT NOT NULL CHECK (length(Nombre) BETWEEN 1 AND 150),
  Email  TEXT NULL CHECK (Email IS NULL OR length(Email) <= 254),
  Activo INTEGER NOT NULL DEFAULT 1 CHECK (Activo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS Permiso (
  UsuarioId      TEXT PRIMARY KEY REFERENCES Usuario(Id),
  Rol            TEXT NOT NULL CHECK (Rol IN ('IF', 'VALIDADOR', 'ADMIN', 'GABINETE')),
  Activo         INTEGER NOT NULL DEFAULT 1 CHECK (Activo IN (0, 1)),
  ActualizadoPor TEXT NOT NULL REFERENCES Usuario(Id),
  ActualizadoEn  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS Contrato (
  Id              TEXT PRIMARY KEY CHECK (length(Id) BETWEEN 1 AND 64),
  Nombre          TEXT NOT NULL CHECK (length(Nombre) BETWEEN 1 AND 150),
  UnidadLabel     TEXT NOT NULL DEFAULT '' CHECK (length(UnidadLabel) <= 50),
  CodDeaf         TEXT NULL CHECK (CodDeaf IS NULL OR (length(CodDeaf) BETWEEN 1 AND 40 AND CodDeaf NOT GLOB '*[^A-Za-z0-9._/-]*')),
  InspectorNombre TEXT NOT NULL DEFAULT '' CHECK (length(InspectorNombre) <= 150),                 -- IF titular (referencial)
  InspectorSuplente TEXT NOT NULL DEFAULT '' CHECK (length(InspectorSuplente) <= 150),             -- IF suplente (referencial)
  CorreoAprobador TEXT NOT NULL DEFAULT '' CHECK (length(CorreoAprobador) <= 254),     -- a esta dirección se abre el aviso (mailto:)
  Activo          INTEGER NOT NULL DEFAULT 1 CHECK (Activo IN (0, 1)),
  CreadoEn        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS UsuarioContrato (            -- contratos asignados (IF y VALIDADOR)
  UsuarioId  TEXT NOT NULL REFERENCES Usuario(Id),
  ContratoId TEXT NOT NULL REFERENCES Contrato(Id),
  RolContrato TEXT NOT NULL DEFAULT 'titular' CHECK (RolContrato IN ('titular', 'suplente')),   -- un IF suele tener 2: titular y suplente
  Activo     INTEGER NOT NULL DEFAULT 1 CHECK (Activo IN (0, 1)),
  PRIMARY KEY (UsuarioId, ContratoId)
);

CREATE TABLE IF NOT EXISTS Sesion (
  TokenHash TEXT PRIMARY KEY CHECK (length(TokenHash) = 64),       -- SHA-256 del token
  UsuarioId TEXT NOT NULL REFERENCES Usuario(Id),
  Rol       TEXT NOT NULL CHECK (Rol IN ('IF', 'VALIDADOR', 'ADMIN', 'GABINETE')),
  CreadaEn  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ExpiraEn  TEXT NOT NULL,
  Revocada  INTEGER NOT NULL DEFAULT 0 CHECK (Revocada IN (0, 1))
);

-- ---------------------------------------------------------------- estructura y línea base
CREATE TABLE IF NOT EXISTS Unidad (
  Id         TEXT PRIMARY KEY CHECK (length(Id) BETWEEN 1 AND 64),
  ContratoId TEXT NOT NULL REFERENCES Contrato(Id),
  Nombre     TEXT NOT NULL CHECK (length(Nombre) BETWEEN 1 AND 150),
  Activo     INTEGER NOT NULL DEFAULT 1 CHECK (Activo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS Hito (
  Id               TEXT PRIMARY KEY CHECK (length(Id) BETWEEN 1 AND 64),
  ContratoId       TEXT NOT NULL REFERENCES Contrato(Id),
  UnidadId         TEXT NOT NULL REFERENCES Unidad(Id),
  Nombre           TEXT NOT NULL DEFAULT '' CHECK (length(Nombre) <= 150),
  Tipo             TEXT NOT NULL CHECK (Tipo IN ('Ingeniería', 'Inicio Físico', 'PSP', 'PSD', 'Informe de avance', 'Fase de construcción')),
  FechaContractual TEXT NOT NULL CHECK (FechaContractual GLOB '[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]'),
  IsDeleted        INTEGER NOT NULL DEFAULT 0 CHECK (IsDeleted IN (0, 1))
);

-- ---------------------------------------------------------------- flujo de aprobación
CREATE TABLE IF NOT EXISTS Solicitud (
  Id                 TEXT PRIMARY KEY CHECK (length(Id) BETWEEN 1 AND 64),
  ContratoId         TEXT NOT NULL REFERENCES Contrato(Id),
  Tipo               TEXT NOT NULL CHECK (Tipo IN ('avance', 'fecha_programada', 'fecha_real')),
  UnidadId           TEXT NULL REFERENCES Unidad(Id),
  HitoId             TEXT NULL REFERENCES Hito(Id),
  ValorAvance        INTEGER NULL CHECK (ValorAvance IS NULL OR ValorAvance BETWEEN 0 AND 100),
  ValorFecha         TEXT NULL CHECK (ValorFecha IS NULL OR ValorFecha GLOB '[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]'),
  VigenteAvance      INTEGER NULL,
  VigenteFecha       TEXT NULL,
  FechaReporte       TEXT NOT NULL CHECK (FechaReporte GLOB '[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]'),
  Nota               TEXT NOT NULL DEFAULT '' CHECK (length(Nota) <= 4000),
  Estado             TEXT NOT NULL CHECK (Estado IN ('BORRADOR', 'PENDIENTE_APROBACION', 'APROBADO', 'RECHAZADO', 'ELIMINADO')),
  IsDeleted          INTEGER NOT NULL DEFAULT 0 CHECK (IsDeleted IN (0, 1)),
  AutorId            TEXT NOT NULL REFERENCES Usuario(Id),
  CreadoEn           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  EnviadoEn          TEXT NULL,
  RevisorId          TEXT NULL REFERENCES Usuario(Id),
  RevisadoEn         TEXT NULL,
  ComentarioRevision TEXT NOT NULL DEFAULT '' CHECK (length(ComentarioRevision) <= 2000),
  CHECK ((Tipo = 'avance' AND UnidadId IS NOT NULL AND ValorAvance IS NOT NULL AND HitoId IS NULL)
      OR (Tipo <> 'avance' AND HitoId IS NOT NULL AND ValorFecha IS NOT NULL AND UnidadId IS NULL)),
  CHECK (RevisorId IS NULL OR RevisorId <> AutorId),                         -- nadie se aprueba a sí mismo
  CHECK (Estado <> 'RECHAZADO' OR length(trim(ComentarioRevision)) >= 5),    -- rechazo con comentario
  CHECK ((Estado = 'ELIMINADO') = (IsDeleted = 1))
);

CREATE TABLE IF NOT EXISTS SolicitudHistorial (          -- solo anexar
  Id          INTEGER PRIMARY KEY AUTOINCREMENT,
  SolicitudId TEXT NOT NULL REFERENCES Solicitud(Id),
  ContratoId  TEXT NOT NULL REFERENCES Contrato(Id),
  Estado      TEXT NOT NULL CHECK (Estado IN ('BORRADOR', 'PENDIENTE_APROBACION', 'APROBADO', 'RECHAZADO', 'ELIMINADO')),
  ActorId     TEXT NOT NULL REFERENCES Usuario(Id),
  Comentario  TEXT NOT NULL DEFAULT '',
  OcurridoEn  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ---------------------------------------------------------------- datos oficiales (lo único que ve Gabinete)
CREATE TABLE IF NOT EXISTS AvanceOficial (
  UnidadId     TEXT PRIMARY KEY REFERENCES Unidad(Id),
  ContratoId   TEXT NOT NULL REFERENCES Contrato(Id),
  Valor        INTEGER NOT NULL CHECK (Valor BETWEEN 0 AND 100),
  FechaReporte TEXT NOT NULL,
  SolicitudId  TEXT NULL REFERENCES Solicitud(Id),
  RevisorId    TEXT NULL REFERENCES Usuario(Id),
  AprobadoEn   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS HitoOficial (
  HitoId       TEXT PRIMARY KEY REFERENCES Hito(Id),
  ContratoId   TEXT NOT NULL REFERENCES Contrato(Id),
  FechaVigente TEXT NULL,
  FechaReal    TEXT NULL,
  RevisorId    TEXT NULL REFERENCES Usuario(Id),
  AprobadoEn   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS HistorialOficial (            -- solo anexar
  Id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ContratoId    TEXT NOT NULL REFERENCES Contrato(Id),
  SolicitudId   TEXT NULL REFERENCES Solicitud(Id),
  Campo         TEXT NOT NULL CHECK (Campo IN ('avance', 'fecha_programada', 'fecha_real')),
  Ref           TEXT NOT NULL,
  ValorAnterior TEXT NULL,
  ValorNuevo    TEXT NOT NULL,
  FechaReporte  TEXT NULL,
  Nota          TEXT NOT NULL DEFAULT '',
  AutorId       TEXT NULL REFERENCES Usuario(Id),
  RevisorId     TEXT NULL REFERENCES Usuario(Id),
  Migrado       INTEGER NOT NULL DEFAULT 0 CHECK (Migrado IN (0, 1)),
  AprobadoEn    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS AlertaGabinete (
  ProblematicaId TEXT PRIMARY KEY,
  ContratoId     TEXT NOT NULL REFERENCES Contrato(Id),
  Titulo         TEXT NOT NULL CHECK (length(Titulo) BETWEEN 1 AND 200),
  NivelRiesgo    TEXT NULL CHECK (NivelRiesgo IS NULL OR NivelRiesgo IN ('Extremo', 'Alto', 'Medio', 'Bajo')),
  Estado         TEXT NOT NULL CHECK (Estado IN ('detectado', 'en_gestion', 'escalado', 'resuelto')),
  Escalamiento   TEXT NOT NULL DEFAULT '',          -- instancias separadas por "|"
  RevisorId      TEXT NOT NULL REFERENCES Usuario(Id),
  PublicadoEn    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  IsDeleted      INTEGER NOT NULL DEFAULT 0 CHECK (IsDeleted IN (0, 1)),
  RetiradoEn     TEXT NULL
);

-- ---------------------------------------------------------------- problemáticas
CREATE TABLE IF NOT EXISTS Problematica (
  Id               TEXT PRIMARY KEY CHECK (length(Id) BETWEEN 1 AND 64),
  ContratoId       TEXT NOT NULL REFERENCES Contrato(Id),
  UnidadId         TEXT NULL REFERENCES Unidad(Id),
  Titulo           TEXT NOT NULL CHECK (length(Titulo) BETWEEN 1 AND 200),
  Descripcion      TEXT NOT NULL CHECK (length(Descripcion) BETWEEN 1 AND 4000),
  Impacto          TEXT NOT NULL DEFAULT '' CHECK (length(Impacto) <= 4000),
  NivelRiesgo      TEXT NULL CHECK (NivelRiesgo IS NULL OR NivelRiesgo IN ('Extremo', 'Alto', 'Medio', 'Bajo')),
  Estado           TEXT NOT NULL DEFAULT 'detectado' CHECK (Estado IN ('detectado', 'en_gestion', 'escalado', 'resuelto')),
  FechaVencimiento TEXT NULL CHECK (FechaVencimiento IS NULL OR FechaVencimiento GLOB '[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]'),
  AutorId          TEXT NOT NULL REFERENCES Usuario(Id),
  CreadoEn         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ResueltaEn       TEXT NULL,
  ResolucionTexto  TEXT NULL CHECK (ResolucionTexto IS NULL OR length(ResolucionTexto) <= 4000),   -- cómo / por qué se resolvió
  ResolucionPorId  TEXT NULL REFERENCES Usuario(Id),
  IsDeleted        INTEGER NOT NULL DEFAULT 0 CHECK (IsDeleted IN (0, 1)),
  CHECK (Estado <> 'resuelto' OR length(trim(COALESCE(ResolucionTexto, ''))) >= 5)               -- no se resuelve sin motivo
);

CREATE TABLE IF NOT EXISTS ProblematicaResolucionPrevia (   -- solo anexar: resoluciones de una problemática reabierta
  Id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ProblematicaId TEXT NOT NULL REFERENCES Problematica(Id),
  ContratoId     TEXT NOT NULL REFERENCES Contrato(Id),
  Texto          TEXT NOT NULL,
  AutorId        TEXT NULL REFERENCES Usuario(Id),
  ResueltaEn     TEXT NULL
);

CREATE TABLE IF NOT EXISTS LecturaNotificacion (        -- avisos del IF: lo anterior a LeidoEn ya fue leído
  UsuarioId TEXT PRIMARY KEY REFERENCES Usuario(Id),
  LeidoEn   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ProblematicaStakeholder (
  ProblematicaId TEXT NOT NULL REFERENCES Problematica(Id),
  ContratoId     TEXT NOT NULL REFERENCES Contrato(Id),
  Nombre         TEXT NOT NULL CHECK (length(Nombre) BETWEEN 1 AND 80),
  PRIMARY KEY (ProblematicaId, Nombre)
);

CREATE TABLE IF NOT EXISTS ProblematicaEscalamiento (
  ProblematicaId TEXT NOT NULL REFERENCES Problematica(Id),
  ContratoId     TEXT NOT NULL REFERENCES Contrato(Id),
  Instancia      TEXT NOT NULL CHECK (Instancia IN ('Jefe de División', 'Directora', 'Jurídica', 'Otro')),
  PRIMARY KEY (ProblematicaId, Instancia)
);

CREATE TABLE IF NOT EXISTS ProblematicaTarea (
  Id             TEXT PRIMARY KEY CHECK (length(Id) BETWEEN 1 AND 64),
  ProblematicaId TEXT NOT NULL REFERENCES Problematica(Id),
  ContratoId     TEXT NOT NULL REFERENCES Contrato(Id),
  Texto          TEXT NOT NULL CHECK (length(Texto) BETWEEN 1 AND 300),
  Hecho          INTEGER NOT NULL DEFAULT 0 CHECK (Hecho IN (0, 1)),
  Orden          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ProblematicaNota (            -- solo anexar
  Id             TEXT PRIMARY KEY CHECK (length(Id) BETWEEN 1 AND 64),
  ProblematicaId TEXT NOT NULL REFERENCES Problematica(Id),
  ContratoId     TEXT NOT NULL REFERENCES Contrato(Id),
  Texto          TEXT NOT NULL CHECK (length(Texto) BETWEEN 1 AND 2000),
  AutorId        TEXT NOT NULL REFERENCES Usuario(Id),
  CreadoEn       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS Auditoria (                   -- solo anexar
  Id         INTEGER PRIMARY KEY AUTOINCREMENT,
  OcurridoEn TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ContratoId TEXT NULL,
  ActorId    TEXT NOT NULL,
  Rol        TEXT NOT NULL,
  Accion     TEXT NOT NULL,
  Entidad    TEXT NOT NULL,
  EntidadId  TEXT NULL,
  Detalle    TEXT NOT NULL DEFAULT ''
);

-- ---------------------------------------------------------------- nada se borra físicamente
CREATE TRIGGER IF NOT EXISTS Solicitud_NoBorrar BEFORE DELETE ON Solicitud BEGIN SELECT RAISE(ABORT, 'Eliminación lógica: usa Estado ELIMINADO'); END;
CREATE TRIGGER IF NOT EXISTS Problematica_NoBorrar BEFORE DELETE ON Problematica BEGIN SELECT RAISE(ABORT, 'Eliminación lógica: usa IsDeleted'); END;
CREATE TRIGGER IF NOT EXISTS Hito_NoBorrar BEFORE DELETE ON Hito BEGIN SELECT RAISE(ABORT, 'Eliminación lógica: usa IsDeleted'); END;
CREATE TRIGGER IF NOT EXISTS Alerta_NoBorrar BEFORE DELETE ON AlertaGabinete BEGIN SELECT RAISE(ABORT, 'Eliminación lógica: usa IsDeleted'); END;
CREATE TRIGGER IF NOT EXISTS Contrato_NoBorrar BEFORE DELETE ON Contrato BEGIN SELECT RAISE(ABORT, 'Desactiva el contrato (Activo = 0)'); END;
CREATE TRIGGER IF NOT EXISTS Unidad_NoBorrar BEFORE DELETE ON Unidad BEGIN SELECT RAISE(ABORT, 'Desactiva la unidad (Activo = 0)'); END;
CREATE TRIGGER IF NOT EXISTS UsuarioContrato_NoBorrar BEFORE DELETE ON UsuarioContrato BEGIN SELECT RAISE(ABORT, 'Desactiva la asignación (Activo = 0)'); END;
-- solo anexar
CREATE TRIGGER IF NOT EXISTS SolHist_NoEditar BEFORE UPDATE ON SolicitudHistorial BEGIN SELECT RAISE(ABORT, 'Historial de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS SolHist_NoBorrar BEFORE DELETE ON SolicitudHistorial BEGIN SELECT RAISE(ABORT, 'Historial de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS HistOf_NoEditar BEFORE UPDATE ON HistorialOficial BEGIN SELECT RAISE(ABORT, 'Historial de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS HistOf_NoBorrar BEFORE DELETE ON HistorialOficial BEGIN SELECT RAISE(ABORT, 'Historial de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS Nota_NoEditar BEFORE UPDATE ON ProblematicaNota BEGIN SELECT RAISE(ABORT, 'Notas de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS Nota_NoBorrar BEFORE DELETE ON ProblematicaNota BEGIN SELECT RAISE(ABORT, 'Notas de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS ResPrev_NoEditar BEFORE UPDATE ON ProblematicaResolucionPrevia BEGIN SELECT RAISE(ABORT, 'Historial de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS ResPrev_NoBorrar BEFORE DELETE ON ProblematicaResolucionPrevia BEGIN SELECT RAISE(ABORT, 'Historial de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS Auditoria_NoEditar BEFORE UPDATE ON Auditoria BEGIN SELECT RAISE(ABORT, 'Auditoría de solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS Auditoria_NoBorrar BEFORE DELETE ON Auditoria BEGIN SELECT RAISE(ABORT, 'Auditoría de solo anexar'); END;

CREATE UNIQUE INDEX IF NOT EXISTS UX_Contrato_CodDeaf ON Contrato(CodDeaf COLLATE NOCASE) WHERE CodDeaf IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS UX_Unidad_Contrato_Nombre ON Unidad(ContratoId, Nombre COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS IX_UsuarioContrato_Contrato ON UsuarioContrato(ContratoId);
CREATE INDEX IF NOT EXISTS IX_Unidad_Contrato          ON Unidad(ContratoId);
CREATE INDEX IF NOT EXISTS IX_Hito_Contrato            ON Hito(ContratoId);
CREATE INDEX IF NOT EXISTS IX_Solicitud_Contrato       ON Solicitud(ContratoId, Estado);
CREATE INDEX IF NOT EXISTS IX_HistOf_Contrato          ON HistorialOficial(ContratoId, AprobadoEn);
CREATE INDEX IF NOT EXISTS IX_Problematica_Contrato    ON Problematica(ContratoId, Estado);

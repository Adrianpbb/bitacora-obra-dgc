"""Capa de acceso a datos de la Bitácora de Obra (SQLite o SQL Server) — v8, 2026-10-01.

Garantías de este módulo:
1. Sin inyección SQL: todo valor viaja como parámetro `?` (paramstyle "qmark", común a
   sqlite3 y pyodbc). Todo el SQL es texto literal de este archivo; nada se arma
   concatenando datos.
2. Alcance por perfil, decidido en el servidor:
   - IF y VALIDADOR: solo los contratos asignados en UsuarioContrato (subconsulta
     parametrizada por el id de la sesión; el contrato que mande el cliente se ignora).
   - ADMIN: todos los contratos.
   - GABINETE: solo lectura de datos oficiales (AvanceOficial, HitoOficial,
     HistorialOficial, AlertaGabinete); cualquier dato operativo le está vedado.
3. Flujo de aprobación: BORRADOR -> PENDIENTE_APROBACION -> APROBADO / RECHAZADO, o
   ELIMINADO (lógico). Nadie revisa su propia solicitud; rechazar exige comentario.
   Solo una aprobación escribe en las tablas oficiales.
4. Nada se borra físicamente; autoría y fechas las pone el servidor.

La identidad la entrega el SSO institucional (AD / Entra ID): llamar a abrir_sesion()
solo después de validarla. En SQL Server, el usuario de base de datos de la aplicación
debe tener DEFAULT_SCHEMA = bitacora (lo configura schema_sqlserver.sql).
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import auth_sesion as auth
import validar as v


@dataclass(frozen=True)
class Sesion:
    usuario_id: str
    rol: str        # IF | VALIDADOR | ADMIN | GABINETE
    nombre: str


class AccesoDenegado(PermissionError):
    pass


class NoEncontrado(LookupError):
    pass


def _nuevo_id():
    return uuid.uuid4().hex


def _ahora():
    return datetime.now(timezone.utc)


# Filtro de alcance: contratos asignados y activos del usuario de la sesión.
_ASIGNADOS = 'SELECT ContratoId FROM UsuarioContrato WHERE UsuarioId = ? AND Activo = 1'

# Lecturas: (nombre, por_usuario) -> SQL literal. Las variantes "por usuario" reciben el id de la sesión.
_LECTURAS = {
    ('contratos', False): 'SELECT Id, Nombre, UnidadLabel, InspectorNombre, CorreoAprobador, Activo FROM Contrato ORDER BY Nombre',
    ('contratos', True): 'SELECT c.Id, c.Nombre, c.UnidadLabel, c.InspectorNombre, c.CorreoAprobador, c.Activo, '
                         '(SELECT uc.RolContrato FROM UsuarioContrato uc WHERE uc.UsuarioId = ? AND uc.ContratoId = c.Id AND uc.Activo = 1) AS RolContrato '
                         'FROM Contrato c WHERE c.Id IN (' + _ASIGNADOS + ') ORDER BY c.Nombre',
    ('unidades', False): 'SELECT Id, ContratoId, Nombre, Activo FROM Unidad ORDER BY Nombre',
    ('unidades', True): 'SELECT Id, ContratoId, Nombre, Activo FROM Unidad WHERE ContratoId IN (' + _ASIGNADOS + ') ORDER BY Nombre',
    ('hitos', False): 'SELECT h.Id, h.ContratoId, h.UnidadId, h.Nombre, h.Tipo, h.FechaContractual, o.FechaVigente, o.FechaReal '
                      'FROM Hito h LEFT JOIN HitoOficial o ON o.HitoId = h.Id WHERE h.IsDeleted = 0 ORDER BY h.FechaContractual',
    ('hitos', True): 'SELECT h.Id, h.ContratoId, h.UnidadId, h.Nombre, h.Tipo, h.FechaContractual, o.FechaVigente, o.FechaReal '
                     'FROM Hito h LEFT JOIN HitoOficial o ON o.HitoId = h.Id WHERE h.IsDeleted = 0 '
                     'AND h.ContratoId IN (' + _ASIGNADOS + ') ORDER BY h.FechaContractual',
    ('avances', False): 'SELECT UnidadId, ContratoId, Valor, FechaReporte, AprobadoEn FROM AvanceOficial',
    ('avances', True): 'SELECT UnidadId, ContratoId, Valor, FechaReporte, AprobadoEn FROM AvanceOficial '
                       'WHERE ContratoId IN (' + _ASIGNADOS + ')',
    ('alertas', False): 'SELECT ProblematicaId, ContratoId, Titulo, NivelRiesgo, Estado, Escalamiento, PublicadoEn '
                        'FROM AlertaGabinete WHERE IsDeleted = 0 ORDER BY PublicadoEn DESC',
    ('alertas', True): 'SELECT ProblematicaId, ContratoId, Titulo, NivelRiesgo, Estado, Escalamiento, PublicadoEn '
                       'FROM AlertaGabinete WHERE IsDeleted = 0 AND ContratoId IN (' + _ASIGNADOS + ') ORDER BY PublicadoEn DESC',
    ('solicitudes', False): 'SELECT Id, ContratoId, Tipo, UnidadId, HitoId, ValorAvance, ValorFecha, VigenteAvance, VigenteFecha, '
                            'FechaReporte, Nota, Estado, AutorId, CreadoEn, EnviadoEn, RevisorId, RevisadoEn, ComentarioRevision '
                            'FROM Solicitud ORDER BY CreadoEn DESC',
    ('solicitudes', True): 'SELECT Id, ContratoId, Tipo, UnidadId, HitoId, ValorAvance, ValorFecha, VigenteAvance, VigenteFecha, '
                           'FechaReporte, Nota, Estado, AutorId, CreadoEn, EnviadoEn, RevisorId, RevisadoEn, ComentarioRevision '
                           'FROM Solicitud WHERE ContratoId IN (' + _ASIGNADOS + ') ORDER BY CreadoEn DESC',
    ('problematicas', False): 'SELECT Id, ContratoId, UnidadId, Titulo, Descripcion, Impacto, NivelRiesgo, Estado, '
                              'FechaVencimiento, AutorId, CreadoEn, ResueltaEn, ResolucionTexto, ResolucionPorId FROM Problematica WHERE IsDeleted = 0 ORDER BY CreadoEn DESC',
    ('problematicas', True): 'SELECT Id, ContratoId, UnidadId, Titulo, Descripcion, Impacto, NivelRiesgo, Estado, '
                             'FechaVencimiento, AutorId, CreadoEn, ResueltaEn, ResolucionTexto, ResolucionPorId FROM Problematica WHERE IsDeleted = 0 '
                             'AND ContratoId IN (' + _ASIGNADOS + ') ORDER BY CreadoEn DESC',
}

_HISTORIAL = {
    ('sqlite', False): 'SELECT ContratoId, Campo, Ref, ValorAnterior, ValorNuevo, FechaReporte, Nota, AutorId, RevisorId, Migrado, AprobadoEn '
                       'FROM HistorialOficial ORDER BY AprobadoEn DESC LIMIT ?',
    ('sqlite', True): 'SELECT ContratoId, Campo, Ref, ValorAnterior, ValorNuevo, FechaReporte, Nota, AutorId, RevisorId, Migrado, AprobadoEn '
                      'FROM HistorialOficial WHERE ContratoId IN (' + _ASIGNADOS + ') ORDER BY AprobadoEn DESC LIMIT ?',
    ('sqlserver', False): 'SELECT TOP (?) ContratoId, Campo, Ref, ValorAnterior, ValorNuevo, FechaReporte, Nota, AutorId, RevisorId, Migrado, '
                          'AprobadoEn FROM HistorialOficial ORDER BY AprobadoEn DESC',
    ('sqlserver', True): 'SELECT TOP (?) ContratoId, Campo, Ref, ValorAnterior, ValorNuevo, FechaReporte, Nota, AutorId, RevisorId, Migrado, '
                         'AprobadoEn FROM HistorialOficial WHERE ContratoId IN (' + _ASIGNADOS + ') ORDER BY AprobadoEn DESC',
}

# Búsqueda de una entidad dentro del alcance: (entidad, por_usuario) -> SQL literal.
_UNA = {
    ('unidad', False): 'SELECT ContratoId FROM Unidad WHERE Id = ? AND Activo = 1',
    ('unidad', True): 'SELECT ContratoId FROM Unidad WHERE Id = ? AND Activo = 1 AND ContratoId IN (' + _ASIGNADOS + ')',
    ('hito', False): 'SELECT ContratoId, FechaContractual FROM Hito WHERE Id = ? AND IsDeleted = 0',
    ('hito', True): 'SELECT ContratoId, FechaContractual FROM Hito WHERE Id = ? AND IsDeleted = 0 AND ContratoId IN (' + _ASIGNADOS + ')',
    ('solicitud', False): 'SELECT ContratoId, Tipo, UnidadId, HitoId, ValorAvance, ValorFecha, FechaReporte, Nota, Estado, AutorId '
                          'FROM Solicitud WHERE Id = ?',
    ('solicitud', True): 'SELECT ContratoId, Tipo, UnidadId, HitoId, ValorAvance, ValorFecha, FechaReporte, Nota, Estado, AutorId '
                         'FROM Solicitud WHERE Id = ? AND ContratoId IN (' + _ASIGNADOS + ')',
    ('problematica', False): 'SELECT ContratoId, UnidadId, Titulo, NivelRiesgo, Estado, AutorId, ResolucionTexto, ResolucionPorId, ResueltaEn FROM Problematica WHERE Id = ? AND IsDeleted = 0',
    ('problematica', True): 'SELECT ContratoId, UnidadId, Titulo, NivelRiesgo, Estado, AutorId, ResolucionTexto, ResolucionPorId, ResueltaEn FROM Problematica '
                            'WHERE Id = ? AND IsDeleted = 0 AND ContratoId IN (' + _ASIGNADOS + ')',
    ('tarea', False): 'SELECT ContratoId FROM ProblematicaTarea WHERE Id = ?',
    ('tarea', True): 'SELECT ContratoId FROM ProblematicaTarea WHERE Id = ? AND ContratoId IN (' + _ASIGNADOS + ')',
}


class Repositorio:
    def __init__(self, conn, dialecto='sqlite'):
        if dialecto not in ('sqlite', 'sqlserver'):
            raise ValueError('dialecto debe ser sqlite o sqlserver')
        self.conn = conn
        self.dialecto = dialecto

    # ------------------------------------------------------------ utilidades
    def _ts(self, dt):
        dt = dt.astimezone(timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ') if self.dialecto == 'sqlite' else dt.replace(tzinfo=None)

    def _parse_ts(self, valor):
        if isinstance(valor, datetime):
            return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
        return datetime.strptime(valor, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)

    def _cursor(self, sesion=None):
        cur = self.conn.cursor()
        if self.dialecto == 'sqlserver' and sesion is not None:
            # Contexto que leen las políticas de seguridad por filas (RLS).
            cur.execute("EXEC sp_set_session_context @key = N'usuario_id', @value = ?", (sesion.usuario_id,))
            cur.execute("EXEC sp_set_session_context @key = N'rol', @value = ?", (sesion.rol,))
        return cur

    @staticmethod
    def _filas(cur):
        nombres = [d[0] for d in cur.description]
        return [dict(zip(nombres, f)) for f in cur.fetchall()]

    @staticmethod
    def _por_usuario(sesion, oficial):
        """False = sin filtro (todos los contratos); True = solo contratos asignados."""
        if sesion.rol == 'ADMIN':
            return False
        if sesion.rol == 'GABINETE':
            if oficial:
                return False
            raise AccesoDenegado('Gabinete solo accede a datos oficiales')
        if sesion.rol in ('IF', 'VALIDADOR'):
            return True
        raise AccesoDenegado('perfil desconocido')

    def _leer(self, sesion, nombre, oficial):
        por_usuario = self._por_usuario(sesion, oficial)
        cur = self._cursor(sesion)
        cur.execute(_LECTURAS[(nombre, por_usuario)], (sesion.usuario_id,) if por_usuario else ())
        return self._filas(cur)

    def _una(self, cur, sesion, entidad, entidad_id):
        por_usuario = self._por_usuario(sesion, oficial=False)
        params = (entidad_id, sesion.usuario_id) if por_usuario else (entidad_id,)
        cur.execute(_UNA[(entidad, por_usuario)], params)
        fila = cur.fetchone()
        if fila is None:
            raise NoEncontrado(entidad)   # mismo error si no existe o está fuera del alcance
        nombres = [d[0] for d in cur.description]
        return dict(zip(nombres, fila))

    @staticmethod
    def _exigir(sesion, *roles):
        if sesion.rol not in roles:
            raise AccesoDenegado('requiere perfil ' + ' o '.join(roles))

    def _auditar(self, cur, sesion, accion, entidad, entidad_id, contrato_id, detalle=''):
        cur.execute('INSERT INTO Auditoria (ContratoId, ActorId, Rol, Accion, Entidad, EntidadId, Detalle) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (contrato_id, sesion.usuario_id, sesion.rol, accion, entidad, entidad_id, detalle[:500]))

    def _historial(self, cur, sesion, solicitud_id, contrato_id, estado, comentario=''):
        cur.execute('INSERT INTO SolicitudHistorial (SolicitudId, ContratoId, Estado, ActorId, Comentario) VALUES (?, ?, ?, ?, ?)',
                    (solicitud_id, contrato_id, estado, sesion.usuario_id, comentario))

    # ------------------------------------------------------------ identidad y permisos
    def abrir_sesion(self, usuario_id):
        """Llamar SOLO después de validar la identidad con el SSO institucional."""
        usuario_id = v.ident(usuario_id, 'usuario')
        cur = self.conn.cursor()
        cur.execute('SELECT u.Nombre, p.Rol FROM Usuario u JOIN Permiso p ON p.UsuarioId = u.Id '
                    'WHERE u.Id = ? AND u.Activo = 1 AND p.Activo = 1', (usuario_id,))
        fila = cur.fetchone()
        if fila is None:
            raise AccesoDenegado('la cuenta no tiene un perfil activo')
        sesion = Sesion(usuario_id, fila[1], fila[0])
        token, token_hash = auth.nuevo_token()
        cur.execute('INSERT INTO Sesion (TokenHash, UsuarioId, Rol, ExpiraEn) VALUES (?, ?, ?, ?)',
                    (token_hash, usuario_id, sesion.rol, self._ts(_ahora() + timedelta(hours=auth.HORAS_SESION))))
        self._auditar(cur, sesion, 'ingreso', 'Sesion', None, None)
        self.conn.commit()
        return token, sesion

    def sesion_desde_token(self, token):
        if not isinstance(token, str) or not 20 <= len(token) <= 100:
            raise AccesoDenegado('token inválido')
        cur = self.conn.cursor()
        cur.execute('SELECT s.UsuarioId, s.Rol, s.ExpiraEn, s.Revocada, u.Nombre, p.Activo FROM Sesion s '
                    'JOIN Usuario u ON u.Id = s.UsuarioId JOIN Permiso p ON p.UsuarioId = s.UsuarioId WHERE s.TokenHash = ?',
                    (auth.hash_token(token),))
        fila = cur.fetchone()
        if fila is None or fila[3] or not fila[5] or self._parse_ts(fila[2]) <= _ahora():
            raise AccesoDenegado('sesión inválida o expirada')
        return Sesion(fila[0], fila[1], fila[4])

    def logout(self, token):
        cur = self.conn.cursor()
        cur.execute('UPDATE Sesion SET Revocada = 1 WHERE TokenHash = ?', (auth.hash_token(token),))
        self.conn.commit()

    def guardar_usuario(self, sesion, usuario_id, nombre, email=None):
        """En producción los usuarios se sincronizan desde AD/Entra ID."""
        self._exigir(sesion, 'ADMIN')
        usuario_id = v.ident(usuario_id, 'usuario')
        nombre = v.texto(nombre, v.LIM['inspector'], requerido=True, campo='nombre')
        email = v.texto(email, 254) or None
        cur = self._cursor(sesion)
        cur.execute('UPDATE Usuario SET Nombre = ?, Email = ?, Activo = 1 WHERE Id = ?', (nombre, email, usuario_id))
        if cur.rowcount == 0:
            cur.execute('INSERT INTO Usuario (Id, Nombre, Email) VALUES (?, ?, ?)', (usuario_id, nombre, email))
        self._auditar(cur, sesion, 'guardar', 'Usuario', usuario_id, None)
        self.conn.commit()

    def guardar_permiso(self, sesion, usuario_id, rol, contratos, activo=True, roles_contrato=None, email=None):
        """roles_contrato: {contrato_id: 'titular' | 'suplente'} (solo IF; por omisión 'titular').
        email: correo de la persona, para los avisos (mailto:); None = no cambiarlo."""
        self._exigir(sesion, 'ADMIN')
        usuario_id = v.ident(usuario_id, 'usuario')
        rol = v.opcion(rol, v.ROLES, 'perfil')
        ids = [v.ident(c, 'contrato') for c in (contratos or [])] if rol in ('IF', 'VALIDADOR') else []
        roles_contrato = roles_contrato or {}
        por_contrato = {cid: v.opcion(roles_contrato.get(cid, 'titular'), v.ROLES_CONTRATO, 'rol en el contrato') for cid in ids}
        if email is not None:
            email = v.correo(email, campo='correo de la persona') or None
        if rol in ('IF', 'VALIDADOR') and activo and not ids:
            raise v.ErrorValidacion('Asigna al menos un contrato a este perfil.')
        cur = self._cursor(sesion)
        ahora = self._ts(_ahora())
        cur.execute('UPDATE Permiso SET Rol = ?, Activo = ?, ActualizadoPor = ?, ActualizadoEn = ? WHERE UsuarioId = ?',
                    (rol, 1 if activo else 0, sesion.usuario_id, ahora, usuario_id))
        if cur.rowcount == 0:
            cur.execute('INSERT INTO Permiso (UsuarioId, Rol, Activo, ActualizadoPor) VALUES (?, ?, ?, ?)',
                        (usuario_id, rol, 1 if activo else 0, sesion.usuario_id))
        # Las asignaciones nunca se borran: se desactivan todas y se reactivan las elegidas.
        cur.execute('UPDATE UsuarioContrato SET Activo = 0 WHERE UsuarioId = ?', (usuario_id,))
        for cid in ids:
            rc = por_contrato[cid] if rol == 'IF' else 'titular'
            cur.execute('UPDATE UsuarioContrato SET Activo = 1, RolContrato = ? WHERE UsuarioId = ? AND ContratoId = ?', (rc, usuario_id, cid))
            if cur.rowcount == 0:
                cur.execute('INSERT INTO UsuarioContrato (UsuarioId, ContratoId, RolContrato) VALUES (?, ?, ?)', (usuario_id, cid, rc))
        if email is not None:
            cur.execute('UPDATE Usuario SET Email = ? WHERE Id = ?', (email, usuario_id))
        self._auditar(cur, sesion, 'permiso', 'Permiso', usuario_id, None, rol + ': ' + ','.join(c + '=' + por_contrato[c] for c in ids))
        self.conn.commit()

    # ------------------------------------------------------------ estructura (ADMIN)
    def guardar_contrato(self, sesion, datos, contrato_id=None):
        self._exigir(sesion, 'ADMIN')
        fila = (v.texto(datos.get('nombre'), v.LIM['nombre'], requerido=True, campo='nombre'),
                v.texto(datos.get('unidadLabel'), v.LIM['label']),
                v.texto(datos.get('inspectorNombre'), v.LIM['inspector']),
                v.correo(datos.get('correoAprobador'), campo='correo del aprobador'),
                0 if datos.get('activo') is False else 1)
        cur = self._cursor(sesion)
        if contrato_id is None:
            contrato_id = _nuevo_id()
            cur.execute('INSERT INTO Contrato (Nombre, UnidadLabel, InspectorNombre, CorreoAprobador, Activo, Id) VALUES (?, ?, ?, ?, ?, ?)', fila + (contrato_id,))
        else:
            cur.execute('UPDATE Contrato SET Nombre = ?, UnidadLabel = ?, InspectorNombre = ?, CorreoAprobador = ?, Activo = ? WHERE Id = ?',
                        fila + (v.ident(contrato_id, 'contrato'),))
        self._auditar(cur, sesion, 'guardar', 'Contrato', contrato_id, contrato_id)
        self.conn.commit()
        return contrato_id

    def guardar_unidad(self, sesion, datos, unidad_id=None):
        self._exigir(sesion, 'ADMIN')
        contrato_id = v.ident(datos.get('contratoId'), 'contrato')
        nombre = v.texto(datos.get('nombre'), v.LIM['nombre'], requerido=True, campo='nombre')
        activo = 0 if datos.get('activo') is False else 1
        cur = self._cursor(sesion)
        if unidad_id is None:
            unidad_id = _nuevo_id()
            cur.execute('INSERT INTO Unidad (Id, ContratoId, Nombre, Activo) VALUES (?, ?, ?, ?)', (unidad_id, contrato_id, nombre, activo))
        else:
            cur.execute('UPDATE Unidad SET ContratoId = ?, Nombre = ?, Activo = ? WHERE Id = ?',
                        (contrato_id, nombre, activo, v.ident(unidad_id, 'unidad')))
        self._auditar(cur, sesion, 'guardar', 'Unidad', unidad_id, contrato_id)
        self.conn.commit()
        return unidad_id

    def guardar_hito_base(self, sesion, datos, hito_id=None):
        self._exigir(sesion, 'ADMIN')
        cur = self._cursor(sesion)
        unidad_id = v.ident(datos.get('unidadId'), 'unidad')
        contrato_id = self._una(cur, sesion, 'unidad', unidad_id)['ContratoId']
        fila = (contrato_id, unidad_id, v.texto(datos.get('nombre'), v.LIM['nombre']),
                v.opcion(datos.get('tipo'), v.HITO_TIPOS, 'tipo'),
                v.fecha(datos.get('fechaContractual'), requerido=True, campo='fecha contractual'))
        if hito_id is None:
            hito_id = _nuevo_id()
            cur.execute('INSERT INTO Hito (ContratoId, UnidadId, Nombre, Tipo, FechaContractual, Id) VALUES (?, ?, ?, ?, ?, ?)', fila + (hito_id,))
        else:
            cur.execute('UPDATE Hito SET ContratoId = ?, UnidadId = ?, Nombre = ?, Tipo = ?, FechaContractual = ? WHERE Id = ?',
                        fila + (v.ident(hito_id, 'hito'),))
        self._auditar(cur, sesion, 'guardar', 'Hito', hito_id, contrato_id)
        self.conn.commit()
        return hito_id

    def eliminar_hito(self, sesion, hito_id):
        self._exigir(sesion, 'ADMIN')
        cur = self._cursor(sesion)
        hito_id = v.ident(hito_id, 'hito')
        contrato_id = self._una(cur, sesion, 'hito', hito_id)['ContratoId']
        cur.execute('UPDATE Hito SET IsDeleted = 1 WHERE Id = ?', (hito_id,))
        self._auditar(cur, sesion, 'eliminar', 'Hito', hito_id, contrato_id)
        self.conn.commit()

    # ------------------------------------------------------------ lecturas
    def listar_contratos(self, sesion):
        """Contratos del alcance; para IF y VALIDADOR trae además su RolContrato (titular/suplente)."""
        por_usuario = self._por_usuario(sesion, oficial=True)
        cur = self._cursor(sesion)
        cur.execute(_LECTURAS[('contratos', por_usuario)], (sesion.usuario_id, sesion.usuario_id) if por_usuario else ())
        return self._filas(cur)

    def listar_unidades(self, sesion):
        return self._leer(sesion, 'unidades', oficial=True)

    def listar_hitos(self, sesion):
        return self._leer(sesion, 'hitos', oficial=True)

    def listar_avances_oficiales(self, sesion):
        return self._leer(sesion, 'avances', oficial=True)

    def listar_alertas(self, sesion):
        return self._leer(sesion, 'alertas', oficial=True)

    def listar_historial_oficial(self, sesion, limite=200):
        por_usuario = self._por_usuario(sesion, oficial=True)
        limite = v.entero(limite, 1, 1000, 'límite')
        cur = self._cursor(sesion)
        if not por_usuario:
            params = (limite,)
        elif self.dialecto == 'sqlserver':
            params = (limite, sesion.usuario_id)    # TOP (?) va antes del WHERE
        else:
            params = (sesion.usuario_id, limite)    # LIMIT ? va al final
        cur.execute(_HISTORIAL[(self.dialecto, por_usuario)], params)
        return self._filas(cur)

    def listar_solicitudes(self, sesion):
        return self._leer(sesion, 'solicitudes', oficial=False)

    def listar_problematicas(self, sesion):
        return self._leer(sesion, 'problematicas', oficial=False)

    # ------------------------------------------------------------ flujo de aprobación
    def proponer(self, sesion, datos, enviar=True):
        self._exigir(sesion, 'IF', 'VALIDADOR', 'ADMIN')
        tipo = v.opcion(datos.get('tipo'), v.SOL_TIPOS, 'tipo')
        cur = self._cursor(sesion)
        nota = v.texto(datos.get('nota'), v.LIM['texto'], multilinea=True)
        unidad_id = hito_id = valor_avance = valor_fecha = vig_avance = vig_fecha = None
        if tipo == 'avance':
            unidad_id = v.ident(datos.get('unidadId'), 'unidad')
            contrato_id = self._una(cur, sesion, 'unidad', unidad_id)['ContratoId']
            valor_avance = v.entero(datos.get('valor'), 0, 100, 'avance')
            fecha_reporte = v.fecha(datos.get('fechaReporte'), requerido=True, campo='fecha del reporte')
            cur.execute('SELECT Valor FROM AvanceOficial WHERE UnidadId = ?', (unidad_id,))
            fila = cur.fetchone()
            vig_avance = fila[0] if fila else None
            cur.execute("SELECT 1 FROM Solicitud WHERE Tipo = 'avance' AND UnidadId = ? AND "
                        "(Estado = 'PENDIENTE_APROBACION' OR (Estado = 'BORRADOR' AND AutorId = ?))", (unidad_id, sesion.usuario_id))
        else:
            hito_id = v.ident(datos.get('hitoId'), 'hito')
            contrato_id = self._una(cur, sesion, 'hito', hito_id)['ContratoId']
            valor_fecha = v.fecha(datos.get('valor'), requerido=True)
            if tipo == 'fecha_real' and date.fromisoformat(valor_fecha) > date.today():
                raise v.ErrorValidacion('La fecha real de cumplimiento no puede ser futura.')
            if tipo == 'fecha_programada' and not nota:
                raise v.ErrorValidacion('Justifica el cambio de fecha.')
            fecha_reporte = date.today().isoformat()
            cur.execute('SELECT FechaVigente, FechaReal FROM HitoOficial WHERE HitoId = ?', (hito_id,))
            fila = cur.fetchone()
            vig_fecha = (fila[0] if tipo == 'fecha_programada' else fila[1]) if fila else None
            cur.execute("SELECT 1 FROM Solicitud WHERE Tipo = ? AND HitoId = ? AND "
                        "(Estado = 'PENDIENTE_APROBACION' OR (Estado = 'BORRADOR' AND AutorId = ?))", (tipo, hito_id, sesion.usuario_id))
        if cur.fetchone() is not None:
            raise v.ErrorValidacion('Ya hay una solicitud activa para ese dato.')
        estado = 'PENDIENTE_APROBACION' if enviar else 'BORRADOR'
        solicitud_id = _nuevo_id()
        cur.execute('INSERT INTO Solicitud (Id, ContratoId, Tipo, UnidadId, HitoId, ValorAvance, ValorFecha, VigenteAvance, VigenteFecha, '
                    'FechaReporte, Nota, Estado, AutorId, EnviadoEn) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (solicitud_id, contrato_id, tipo, unidad_id, hito_id, valor_avance, valor_fecha, vig_avance, vig_fecha,
                     fecha_reporte, nota, estado, sesion.usuario_id, self._ts(_ahora()) if enviar else None))
        self._historial(cur, sesion, solicitud_id, contrato_id, estado)
        self._auditar(cur, sesion, 'proponer', 'Solicitud', solicitud_id, contrato_id, tipo)
        self.conn.commit()
        return solicitud_id

    def enviar(self, sesion, solicitud_id):
        cur = self._cursor(sesion)
        solicitud_id = v.ident(solicitud_id, 'solicitud')
        s = self._una(cur, sesion, 'solicitud', solicitud_id)
        if s['AutorId'] != sesion.usuario_id or s['Estado'] != 'BORRADOR':
            raise AccesoDenegado('solo puedes enviar tus propios borradores')
        cur.execute("UPDATE Solicitud SET Estado = 'PENDIENTE_APROBACION', EnviadoEn = ? WHERE Id = ? AND Estado = 'BORRADOR'",
                    (self._ts(_ahora()), solicitud_id))
        self._historial(cur, sesion, solicitud_id, s['ContratoId'], 'PENDIENTE_APROBACION')
        self._auditar(cur, sesion, 'enviar', 'Solicitud', solicitud_id, s['ContratoId'])
        self.conn.commit()

    def cancelar(self, sesion, solicitud_id):
        cur = self._cursor(sesion)
        solicitud_id = v.ident(solicitud_id, 'solicitud')
        s = self._una(cur, sesion, 'solicitud', solicitud_id)
        if s['AutorId'] != sesion.usuario_id:
            raise AccesoDenegado('solo quien envió la solicitud puede cancelarla')
        if s['Estado'] not in ('BORRADOR', 'PENDIENTE_APROBACION'):
            raise v.ErrorValidacion('La solicitud ya fue revisada; no se puede cancelar.')
        cur.execute("UPDATE Solicitud SET Estado = 'ELIMINADO', IsDeleted = 1 WHERE Id = ?", (solicitud_id,))
        self._historial(cur, sesion, solicitud_id, s['ContratoId'], 'ELIMINADO')
        self._auditar(cur, sesion, 'cancelar', 'Solicitud', solicitud_id, s['ContratoId'])
        self.conn.commit()

    def _pendiente_para_revisar(self, cur, sesion, solicitud_id):
        self._exigir(sesion, 'VALIDADOR', 'ADMIN')
        s = self._una(cur, sesion, 'solicitud', solicitud_id)
        if s['Estado'] != 'PENDIENTE_APROBACION':
            raise v.ErrorValidacion('La solicitud ya no está pendiente.')
        if s['AutorId'] == sesion.usuario_id:
            raise AccesoDenegado('nadie puede revisar una solicitud propia')
        return s

    def aprobar(self, sesion, solicitud_id):
        cur = self._cursor(sesion)
        solicitud_id = v.ident(solicitud_id, 'solicitud')
        s = self._pendiente_para_revisar(cur, sesion, solicitud_id)
        ahora = self._ts(_ahora())
        cid = s['ContratoId']
        if s['Tipo'] == 'avance':
            cur.execute('SELECT Valor FROM AvanceOficial WHERE UnidadId = ?', (s['UnidadId'],))
            fila = cur.fetchone()
            anterior, nuevo, ref = (str(fila[0]) if fila else None), str(s['ValorAvance']), s['UnidadId']
            cur.execute('UPDATE AvanceOficial SET Valor = ?, FechaReporte = ?, SolicitudId = ?, RevisorId = ?, AprobadoEn = ? WHERE UnidadId = ?',
                        (s['ValorAvance'], s['FechaReporte'], solicitud_id, sesion.usuario_id, ahora, ref))
            if cur.rowcount == 0:
                cur.execute('INSERT INTO AvanceOficial (UnidadId, ContratoId, Valor, FechaReporte, SolicitudId, RevisorId) VALUES (?, ?, ?, ?, ?, ?)',
                            (ref, cid, s['ValorAvance'], s['FechaReporte'], solicitud_id, sesion.usuario_id))
        else:
            ref, nuevo = s['HitoId'], s['ValorFecha']
            cur.execute('SELECT FechaVigente, FechaReal FROM HitoOficial WHERE HitoId = ?', (ref,))
            fila = cur.fetchone()
            vigente, real = (fila[0], fila[1]) if fila else (None, None)
            anterior = vigente if s['Tipo'] == 'fecha_programada' else real
            if s['Tipo'] == 'fecha_programada':
                vigente = nuevo
            else:
                real = nuevo
            cur.execute('UPDATE HitoOficial SET FechaVigente = ?, FechaReal = ?, RevisorId = ?, AprobadoEn = ? WHERE HitoId = ?',
                        (vigente, real, sesion.usuario_id, ahora, ref))
            if cur.rowcount == 0:
                cur.execute('INSERT INTO HitoOficial (HitoId, ContratoId, FechaVigente, FechaReal, RevisorId) VALUES (?, ?, ?, ?, ?)',
                            (ref, cid, vigente, real, sesion.usuario_id))
        cur.execute('INSERT INTO HistorialOficial (ContratoId, SolicitudId, Campo, Ref, ValorAnterior, ValorNuevo, FechaReporte, Nota, AutorId, RevisorId) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (cid, solicitud_id, s['Tipo'], ref, anterior, nuevo, s['FechaReporte'], s['Nota'], s['AutorId'], sesion.usuario_id))
        cur.execute("UPDATE Solicitud SET Estado = 'APROBADO', RevisorId = ?, RevisadoEn = ? WHERE Id = ?", (sesion.usuario_id, ahora, solicitud_id))
        self._historial(cur, sesion, solicitud_id, cid, 'APROBADO')
        self._auditar(cur, sesion, 'aprobar', 'Solicitud', solicitud_id, cid)
        self.conn.commit()

    def rechazar(self, sesion, solicitud_id, comentario):
        cur = self._cursor(sesion)
        solicitud_id = v.ident(solicitud_id, 'solicitud')
        comentario = v.texto(comentario, v.LIM['motivo'], multilinea=True)
        if len(comentario) < 5:
            raise v.ErrorValidacion('El comentario es obligatorio para rechazar (mínimo 5 caracteres).')
        s = self._pendiente_para_revisar(cur, sesion, solicitud_id)
        cur.execute("UPDATE Solicitud SET Estado = 'RECHAZADO', RevisorId = ?, RevisadoEn = ?, ComentarioRevision = ? WHERE Id = ?",
                    (sesion.usuario_id, self._ts(_ahora()), comentario, solicitud_id))
        self._historial(cur, sesion, solicitud_id, s['ContratoId'], 'RECHAZADO', comentario)
        self._auditar(cur, sesion, 'rechazar', 'Solicitud', solicitud_id, s['ContratoId'])
        self.conn.commit()

    def publicar_alerta(self, sesion, problematica_id):
        self._exigir(sesion, 'VALIDADOR', 'ADMIN')
        cur = self._cursor(sesion)
        problematica_id = v.ident(problematica_id, 'problemática')
        p = self._una(cur, sesion, 'problematica', problematica_id)
        cur.execute('SELECT Instancia FROM ProblematicaEscalamiento WHERE ProblematicaId = ? ORDER BY Instancia', (problematica_id,))
        escal = '|'.join(f[0] for f in cur.fetchall())
        fila = (p['ContratoId'], p['Titulo'], p['NivelRiesgo'], p['Estado'], escal, sesion.usuario_id, self._ts(_ahora()))
        cur.execute('UPDATE AlertaGabinete SET ContratoId = ?, Titulo = ?, NivelRiesgo = ?, Estado = ?, Escalamiento = ?, RevisorId = ?, '
                    'PublicadoEn = ?, IsDeleted = 0, RetiradoEn = NULL WHERE ProblematicaId = ?', fila + (problematica_id,))
        if cur.rowcount == 0:
            cur.execute('INSERT INTO AlertaGabinete (ContratoId, Titulo, NivelRiesgo, Estado, Escalamiento, RevisorId, PublicadoEn, ProblematicaId) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)', fila + (problematica_id,))
        self._auditar(cur, sesion, 'publicar', 'AlertaGabinete', problematica_id, p['ContratoId'])
        self.conn.commit()

    def retirar_alerta(self, sesion, problematica_id):
        self._exigir(sesion, 'VALIDADOR', 'ADMIN')
        cur = self._cursor(sesion)
        problematica_id = v.ident(problematica_id, 'problemática')
        por_usuario = self._por_usuario(sesion, oficial=False)
        if por_usuario:
            cur.execute('UPDATE AlertaGabinete SET IsDeleted = 1, RetiradoEn = ? WHERE ProblematicaId = ? AND ContratoId IN (' + _ASIGNADOS + ')',
                        (self._ts(_ahora()), problematica_id, sesion.usuario_id))
        else:
            cur.execute('UPDATE AlertaGabinete SET IsDeleted = 1, RetiradoEn = ? WHERE ProblematicaId = ?', (self._ts(_ahora()), problematica_id))
        if cur.rowcount == 0:
            self.conn.rollback()
            raise NoEncontrado('alerta')
        self._auditar(cur, sesion, 'retirar', 'AlertaGabinete', problematica_id, None)
        self.conn.commit()

    # ------------------------------------------------------------ problemáticas
    def crear_problematica(self, sesion, datos):
        self._exigir(sesion, 'IF', 'VALIDADOR', 'ADMIN')
        cur = self._cursor(sesion)
        unidad_id = datos.get('unidadId') or None
        if unidad_id is not None:
            unidad_id = v.ident(unidad_id, 'unidad')
            contrato_id = self._una(cur, sesion, 'unidad', unidad_id)['ContratoId']
        else:
            contrato_id = v.ident(datos.get('contratoId'), 'contrato')
            if self._por_usuario(sesion, oficial=False):
                cur.execute('SELECT 1 FROM UsuarioContrato WHERE UsuarioId = ? AND ContratoId = ? AND Activo = 1', (sesion.usuario_id, contrato_id))
            else:
                cur.execute('SELECT 1 FROM Contrato WHERE Id = ? AND Activo = 1', (contrato_id,))
            if cur.fetchone() is None:
                raise NoEncontrado('contrato')
        problematica_id = _nuevo_id()
        cur.execute('INSERT INTO Problematica (Id, ContratoId, UnidadId, Titulo, Descripcion, Impacto, NivelRiesgo, FechaVencimiento, AutorId) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (problematica_id, contrato_id, unidad_id,
                     v.texto(datos.get('titulo'), v.LIM['titulo'], requerido=True, campo='título'),
                     v.texto(datos.get('descripcion'), v.LIM['texto'], multilinea=True, requerido=True, campo='descripción'),
                     v.texto(datos.get('impacto'), v.LIM['texto'], multilinea=True),
                     v.opcion(datos.get('nivelRiesgo'), v.RIESGOS, 'nivel de riesgo', requerido=False),
                     v.fecha(datos.get('fechaVencimiento'), campo='fecha de vencimiento'),
                     sesion.usuario_id))
        for nombre in v.lista_textos(datos.get('stakeholders'), v.LIM['tags'], v.LIM['tag'], campo='stakeholders'):
            cur.execute('INSERT INTO ProblematicaStakeholder (ProblematicaId, ContratoId, Nombre) VALUES (?, ?, ?)', (problematica_id, contrato_id, nombre))
        for inst in v.lista_textos(datos.get('escalamiento'), 4, 40, v.ESCALAMIENTOS, campo='escalamiento'):
            cur.execute('INSERT INTO ProblematicaEscalamiento (ProblematicaId, ContratoId, Instancia) VALUES (?, ?, ?)', (problematica_id, contrato_id, inst))
        for orden, texto in enumerate(v.lista_textos(datos.get('checklist'), v.LIM['checklist'], v.LIM['tarea'], campo='checklist')):
            cur.execute('INSERT INTO ProblematicaTarea (Id, ProblematicaId, ContratoId, Texto, Orden) VALUES (?, ?, ?, ?, ?)',
                        (_nuevo_id(), problematica_id, contrato_id, texto, orden))
        self._auditar(cur, sesion, 'crear', 'Problematica', problematica_id, contrato_id)
        self.conn.commit()
        return problematica_id

    def mover_problematica(self, sesion, problematica_id, estado, motivo=None):
        """Resolver exige el motivo (cómo / por qué se resolvió, mín. 5 caracteres); queda con su autor y fecha.
        Al reabrir, la resolución anterior se conserva (solo anexar)."""
        self._exigir(sesion, 'IF', 'VALIDADOR', 'ADMIN')
        cur = self._cursor(sesion)
        problematica_id = v.ident(problematica_id, 'problemática')
        estado = v.opcion(estado, v.PB_ESTADOS, 'estado')
        p = self._una(cur, sesion, 'problematica', problematica_id)
        ahora = self._ts(_ahora())
        if estado == 'resuelto':
            motivo = v.texto(motivo, v.LIM['texto'], multilinea=True, requerido=True, campo='motivo de la resolución')
            if len(motivo) < 5:
                raise v.ErrorValidacion('motivo de la resolución: mínimo 5 caracteres')
            cur.execute('UPDATE Problematica SET Estado = ?, ResueltaEn = ?, ResolucionTexto = ?, ResolucionPorId = ? WHERE Id = ?',
                        (estado, ahora, motivo, sesion.usuario_id, problematica_id))
        else:
            if p['Estado'] == 'resuelto' and p['ResolucionTexto']:
                cur.execute('INSERT INTO ProblematicaResolucionPrevia (ProblematicaId, ContratoId, Texto, AutorId, ResueltaEn) VALUES (?, ?, ?, ?, ?)',
                            (problematica_id, p['ContratoId'], p['ResolucionTexto'], p['ResolucionPorId'], p['ResueltaEn']))
            cur.execute('UPDATE Problematica SET Estado = ?, ResueltaEn = NULL, ResolucionTexto = NULL, ResolucionPorId = NULL WHERE Id = ?',
                        (estado, problematica_id))
        self._auditar(cur, sesion, 'mover', 'Problematica', problematica_id, p['ContratoId'], estado)
        self.conn.commit()

    def listar_resoluciones_previas(self, sesion, problematica_id):
        cur = self._cursor(sesion)
        problematica_id = v.ident(problematica_id, 'problemática')
        self._una(cur, sesion, 'problematica', problematica_id)     # exige que esté en tu alcance
        cur.execute('SELECT Texto, AutorId, ResueltaEn FROM ProblematicaResolucionPrevia WHERE ProblematicaId = ? ORDER BY Id', (problematica_id,))
        return self._filas(cur)

    # ------------------------------------------------------------ avisos del IF
    def listar_avisos(self, sesion):
        """Solicitudes propias resueltas o en revisión, con la marca de lectura del usuario."""
        self._exigir(sesion, 'IF')
        cur = self._cursor(sesion)
        cur.execute('SELECT Id, ContratoId, Tipo, Estado, RevisadoEn, EnviadoEn, ComentarioRevision FROM Solicitud '
                    "WHERE AutorId = ? AND Estado IN ('PENDIENTE_APROBACION', 'APROBADO', 'RECHAZADO') ORDER BY COALESCE(RevisadoEn, EnviadoEn) DESC",
                    (sesion.usuario_id,))
        avisos = self._filas(cur)
        cur.execute('SELECT LeidoEn FROM LecturaNotificacion WHERE UsuarioId = ?', (sesion.usuario_id,))
        fila = cur.fetchone()
        return avisos, (fila[0] if fila else None)

    def marcar_avisos_leidos(self, sesion):
        self._exigir(sesion, 'IF')
        cur = self._cursor(sesion)
        ahora = self._ts(_ahora())
        cur.execute('UPDATE LecturaNotificacion SET LeidoEn = ? WHERE UsuarioId = ?', (ahora, sesion.usuario_id))
        if cur.rowcount == 0:
            cur.execute('INSERT INTO LecturaNotificacion (UsuarioId, LeidoEn) VALUES (?, ?)', (sesion.usuario_id, ahora))
        self.conn.commit()

    def alternar_tarea(self, sesion, tarea_id, hecho):
        self._exigir(sesion, 'IF', 'VALIDADOR', 'ADMIN')
        cur = self._cursor(sesion)
        tarea_id = v.ident(tarea_id, 'tarea')
        t = self._una(cur, sesion, 'tarea', tarea_id)
        cur.execute('UPDATE ProblematicaTarea SET Hecho = ? WHERE Id = ?', (1 if hecho is True else 0, tarea_id))
        self._auditar(cur, sesion, 'tarea', 'ProblematicaTarea', tarea_id, t['ContratoId'])
        self.conn.commit()

    def agregar_nota(self, sesion, problematica_id, texto):
        self._exigir(sesion, 'IF', 'VALIDADOR', 'ADMIN')
        cur = self._cursor(sesion)
        problematica_id = v.ident(problematica_id, 'problemática')
        p = self._una(cur, sesion, 'problematica', problematica_id)
        nota_id = _nuevo_id()
        cur.execute('INSERT INTO ProblematicaNota (Id, ProblematicaId, ContratoId, Texto, AutorId) VALUES (?, ?, ?, ?, ?)',
                    (nota_id, problematica_id, p['ContratoId'], v.texto(texto, v.LIM['nota'], multilinea=True, requerido=True, campo='nota'),
                     sesion.usuario_id))
        self._auditar(cur, sesion, 'nota', 'Problematica', problematica_id, p['ContratoId'])
        self.conn.commit()
        return nota_id

    def eliminar_problematica(self, sesion, problematica_id):
        self._exigir(sesion, 'IF', 'VALIDADOR', 'ADMIN')
        cur = self._cursor(sesion)
        problematica_id = v.ident(problematica_id, 'problemática')
        p = self._una(cur, sesion, 'problematica', problematica_id)
        if p['AutorId'] != sesion.usuario_id and sesion.rol == 'IF':
            raise AccesoDenegado('solo quien la creó o una jefatura puede eliminarla')
        cur.execute('UPDATE Problematica SET IsDeleted = 1 WHERE Id = ?', (problematica_id,))
        self._auditar(cur, sesion, 'eliminar', 'Problematica', problematica_id, p['ContratoId'])
        self.conn.commit()

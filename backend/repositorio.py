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


class ErrorCarga(v.ErrorValidacion):
    """Carga masiva rechazada: `errores` es una lista de (número de fila, mensaje). No se guardó nada."""
    def __init__(self, errores):
        super().__init__('; '.join(f'fila {n}: {m}' for n, m in errores))
        self.errores = errores


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
    ('contratos', False): 'SELECT Id, Nombre, CodDeaf, Peso, UnidadLabel, InspectorNombre, InspectorSuplente, CorreoAprobador, Activo FROM Contrato ORDER BY Nombre',
    ('contratos', True): 'SELECT c.Id, c.Nombre, c.CodDeaf, c.Peso, c.UnidadLabel, c.InspectorNombre, c.InspectorSuplente, c.CorreoAprobador, c.Activo, '
                         '(SELECT uc.RolContrato FROM UsuarioContrato uc WHERE uc.UsuarioId = ? AND uc.ContratoId = c.Id AND uc.Activo = 1) AS RolContrato '
                         'FROM Contrato c WHERE c.Id IN (' + _ASIGNADOS + ') ORDER BY c.Nombre',
    ('unidades', False): 'SELECT Id, ContratoId, Nombre, Peso, Activo FROM Unidad ORDER BY Nombre',
    ('unidades', True): 'SELECT Id, ContratoId, Nombre, Peso, Activo FROM Unidad WHERE ContratoId IN (' + _ASIGNADOS + ') ORDER BY Nombre',
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
                       'FROM HistorialOficial ORDER BY AprobadoEn DESC, Id DESC LIMIT ?',
    ('sqlite', True): 'SELECT ContratoId, Campo, Ref, ValorAnterior, ValorNuevo, FechaReporte, Nota, AutorId, RevisorId, Migrado, AprobadoEn '
                      'FROM HistorialOficial WHERE ContratoId IN (' + _ASIGNADOS + ') ORDER BY AprobadoEn DESC, Id DESC LIMIT ?',
    ('sqlserver', False): 'SELECT TOP (?) ContratoId, Campo, Ref, ValorAnterior, ValorNuevo, FechaReporte, Nota, AutorId, RevisorId, Migrado, '
                          'AprobadoEn FROM HistorialOficial ORDER BY AprobadoEn DESC, Id DESC',
    ('sqlserver', True): 'SELECT TOP (?) ContratoId, Campo, Ref, ValorAnterior, ValorNuevo, FechaReporte, Nota, AutorId, RevisorId, Migrado, '
                         'AprobadoEn FROM HistorialOficial WHERE ContratoId IN (' + _ASIGNADOS + ') ORDER BY AprobadoEn DESC, Id DESC',
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


def promedio_ponderado(items, todos_pesos):
    """Misma regla que el frontend (bitacora-obra.html, promedioAvance).
    items: [(valor, peso|None)] de los elementos CON dato; todos_pesos: pesos (o None) de TODOS los elementos del conjunto.
    Si todos tienen peso se pondera (re-normalizando entre los que tienen dato); si falta alguno, promedio simple.
    Los elementos sin dato no cuentan como 0. Devuelve (porcentaje entero | None, ponderado: bool)."""
    ponderable = bool(todos_pesos) and all(p is not None for p in todos_pesos)
    if not items:
        return None, ponderable
    suma = sum(p for _, p in items) if ponderable else 0
    if ponderable and suma > 0:
        return _redondear(sum(v * p for v, p in items) / suma), True
    return _redondear(sum(v for v, _ in items) / len(items)), False


def _redondear(x):
    return int(x + 0.5)      # como Math.round de JavaScript (mitades hacia arriba)


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
        cod = v.cod_deaf(datos.get('codDeaf'), requerido=False)
        fila = (v.texto(datos.get('nombre'), v.LIM['nombre'], requerido=True, campo='nombre'),
                cod,
                v.texto(datos.get('unidadLabel'), v.LIM['label']),
                v.texto(datos.get('inspectorNombre'), v.LIM['inspector']),
                v.texto(datos.get('inspectorSuplente'), v.LIM['inspector']),
                v.correo(datos.get('correoAprobador'), campo='correo del aprobador'),
                0 if datos.get('activo') is False else 1)
        cur = self._cursor(sesion)
        if cod is not None:
            cur.execute('SELECT Id FROM Contrato WHERE UPPER(CodDeaf) = UPPER(?)', (cod,))
            otro = cur.fetchone()
            if otro is not None and otro[0] != contrato_id:
                raise v.ErrorValidacion('COD_DEAF: ya existe otro contrato con ese código')
        if contrato_id is None:
            contrato_id = _nuevo_id()
            cur.execute('INSERT INTO Contrato (Nombre, CodDeaf, UnidadLabel, InspectorNombre, InspectorSuplente, CorreoAprobador, Activo, Id) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)', fila + (contrato_id,))
        else:
            cur.execute('UPDATE Contrato SET Nombre = ?, CodDeaf = ?, UnidadLabel = ?, InspectorNombre = ?, InspectorSuplente = ?, '
                        'CorreoAprobador = ?, Activo = ? WHERE Id = ?', fila + (v.ident(contrato_id, 'contrato'),))
        self._auditar(cur, sesion, 'guardar', 'Contrato', contrato_id, contrato_id)
        self.conn.commit()
        return contrato_id

    def importar_contratos(self, sesion, filas):
        """Carga masiva (Excel/CSV): filas = lista de dicts con codDeaf, nombre, unidadLabel, inspectorNombre,
        inspectorSuplente, correoAprobador. Todo o nada: si alguna fila falla se lanza ErrorCarga con
        todos los errores y no se guarda nada. Existe el COD_DEAF -> actualiza (sin tocar Activo); si no, crea.
        Nada se borra. Devuelve {'creados', 'actualizados', 'iguales'}."""
        self._exigir(sesion, 'ADMIN')
        if not isinstance(filas, (list, tuple)) or not filas:
            raise v.ErrorValidacion('la carga no tiene filas')
        if len(filas) > 500:
            raise v.ErrorValidacion('la carga supera las 500 filas')
        errores, vistos, limpias = [], {}, []
        for n, f in enumerate(filas, start=1):
            e0 = len(errores)
            d = {}
            for campo, fn in (('codDeaf', lambda x: v.cod_deaf(x)),
                              ('nombre', lambda x: v.sin_formula(v.texto(x, v.LIM['nombre'], requerido=True, campo='nombre'), 'nombre')),
                              ('unidadLabel', lambda x: v.sin_formula(v.texto(x, v.LIM['label'], requerido=True, campo='tipo de unidad'), 'tipo de unidad')),
                              ('inspectorNombre', lambda x: v.sin_formula(v.texto(x, v.LIM['inspector'], requerido=True, campo='IF titular'), 'IF titular')),
                              ('inspectorSuplente', lambda x: v.sin_formula(v.texto(x, v.LIM['inspector'], campo='IF suplente'), 'IF suplente')),
                              ('correoAprobador', lambda x: v.correo(x, requerido=True, campo='correo del aprobador'))):
                try:
                    d[campo] = fn(f.get(campo) if isinstance(f, dict) else None)
                except v.ErrorValidacion as e:
                    errores.append((n, str(e)))
            if len(errores) == e0:
                clave = d['codDeaf'].upper()
                if clave in vistos:
                    errores.append((n, f'COD_DEAF repetido en la carga (fila {vistos[clave]})'))
                else:
                    vistos[clave] = n
                    limpias.append((n, d))
        if errores:
            raise ErrorCarga(errores)
        cur = self._cursor(sesion)
        r = {'creados': 0, 'actualizados': 0, 'iguales': 0}
        try:
            for n, d in limpias:
                cur.execute('SELECT Id, Nombre, UnidadLabel, InspectorNombre, InspectorSuplente, CorreoAprobador FROM Contrato WHERE UPPER(CodDeaf) = UPPER(?)', (d['codDeaf'],))
                filas_db = cur.fetchall()
                if len(filas_db) > 1:
                    raise ErrorCarga([(n, 'COD_DEAF repetido en la base')])
                nuevos = (d['nombre'], d['unidadLabel'], d['inspectorNombre'], d['inspectorSuplente'], d['correoAprobador'])
                if not filas_db:
                    cid = _nuevo_id()
                    cur.execute('INSERT INTO Contrato (Id, CodDeaf, Nombre, UnidadLabel, InspectorNombre, InspectorSuplente, CorreoAprobador) VALUES (?, ?, ?, ?, ?, ?, ?)',
                                (cid, d['codDeaf'], d['nombre'], d['unidadLabel'], d['inspectorNombre'], d['inspectorSuplente'], d['correoAprobador']))
                    r['creados'] += 1
                elif tuple(filas_db[0][1:]) == nuevos:
                    r['iguales'] += 1
                    cid = filas_db[0][0]
                else:
                    cid = filas_db[0][0]
                    cur.execute('UPDATE Contrato SET Nombre = ?, UnidadLabel = ?, InspectorNombre = ?, InspectorSuplente = ?, CorreoAprobador = ? WHERE Id = ?',
                                (d['nombre'], d['unidadLabel'], d['inspectorNombre'], d['inspectorSuplente'], d['correoAprobador'], cid))   # el COD_DEAF guardado no se toca
                    r['actualizados'] += 1
            self._auditar(cur, sesion, 'importar', 'Contrato', None, None, f"{r['creados']} creados, {r['actualizados']} actualizados")
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()
        return r

    def guardar_unidad(self, sesion, datos, unidad_id=None):
        self._exigir(sesion, 'ADMIN')
        contrato_id = v.ident(datos.get('contratoId'), 'contrato')
        nombre = v.texto(datos.get('nombre'), v.LIM['nombre'], requerido=True, campo='nombre')
        activo = 0 if datos.get('activo') is False else 1
        cur = self._cursor(sesion)
        cur.execute('SELECT Id, Nombre FROM Unidad WHERE ContratoId = ?', (contrato_id,))
        # Comparación sin distinguir mayúsculas ni acentos de mayúscula (casefold): UPPER/NOCASE de SQLite solo pliega ASCII.
        if any(fila[0] != unidad_id and fila[1].casefold() == nombre.casefold() for fila in cur.fetchall()):
            raise v.ErrorValidacion('subsector: ese contrato ya tiene uno con ese nombre')
        if unidad_id is None:
            unidad_id = _nuevo_id()
            cur.execute('INSERT INTO Unidad (Id, ContratoId, Nombre, Activo) VALUES (?, ?, ?, ?)', (unidad_id, contrato_id, nombre, activo))
        else:
            cur.execute('UPDATE Unidad SET ContratoId = ?, Nombre = ?, Activo = ? WHERE Id = ?',
                        (contrato_id, nombre, activo, v.ident(unidad_id, 'unidad')))
        self._auditar(cur, sesion, 'guardar', 'Unidad', unidad_id, contrato_id)
        self.conn.commit()
        return unidad_id

    def importar_unidades(self, sesion, filas):
        """Carga masiva de subsectores: filas = dicts con codDeaf (del contrato), nombre y activo (bool).
        Todo o nada. Si el subsector ya existe en ese contrato (mismo nombre) solo se actualiza Activo; nunca se borra."""
        self._exigir(sesion, 'ADMIN')
        if not isinstance(filas, (list, tuple)) or not filas:
            raise v.ErrorValidacion('la carga no tiene filas')
        if len(filas) > 500:
            raise v.ErrorValidacion('la carga supera las 500 filas')
        cur = self._cursor(sesion)
        errores, vistos, limpias = [], {}, []
        for n, f in enumerate(filas, start=1):
            try:
                if not isinstance(f, dict):
                    raise v.ErrorValidacion('fila inválida')
                cod = v.cod_deaf(f.get('codDeaf'))
                nombre = v.sin_formula(v.texto(f.get('nombre'), v.LIM['nombre'], requerido=True, campo='subsector'), 'subsector')
                if not isinstance(f.get('activo'), bool):
                    raise v.ErrorValidacion('activo: debe ser verdadero o falso')
                cur.execute('SELECT Id FROM Contrato WHERE UPPER(CodDeaf) = UPPER(?)', (cod,))
                cs = cur.fetchall()
                if not cs:
                    raise v.ErrorValidacion('COD_DEAF: el contrato no existe (cárgalo primero)')
                if len(cs) > 1:
                    raise v.ErrorValidacion('COD_DEAF repetido en la base')
                clave = (cs[0][0], nombre.casefold())
                if clave in vistos:
                    raise v.ErrorValidacion(f'subsector repetido en la carga (fila {vistos[clave]})')
                vistos[clave] = n
                limpias.append((cs[0][0], nombre, f['activo']))
            except v.ErrorValidacion as e:
                errores.append((n, str(e)))
        if errores:
            raise ErrorCarga(errores)
        r = {'creados': 0, 'actualizados': 0, 'iguales': 0}
        try:
            for contrato_id, nombre, activo in limpias:
                cur.execute('SELECT Id, Activo, Nombre FROM Unidad WHERE ContratoId = ?', (contrato_id,))
                u = next((fila for fila in cur.fetchall() if fila[2].casefold() == nombre.casefold()), None)
                if u is None:
                    cur.execute('INSERT INTO Unidad (Id, ContratoId, Nombre, Activo) VALUES (?, ?, ?, ?)', (_nuevo_id(), contrato_id, nombre, 1 if activo else 0))
                    r['creados'] += 1
                elif bool(u[1]) == activo:
                    r['iguales'] += 1
                else:
                    cur.execute('UPDATE Unidad SET Activo = ? WHERE Id = ?', (1 if activo else 0, u[0]))
                    r['actualizados'] += 1
            self._auditar(cur, sesion, 'importar', 'Unidad', None, None, f"{r['creados']} creados, {r['actualizados']} actualizados")
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()
        return r

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

    def avance_contrato(self, sesion, contrato_id):
        """Avance oficial del contrato: promedio de sus unidades activas, ponderado por Peso cuando todas lo tienen."""
        contrato_id = v.ident(contrato_id, 'contrato')
        unidades = [u for u in self.listar_unidades(sesion) if u['ContratoId'] == contrato_id and u['Activo']]
        valores = {a['UnidadId']: a['Valor'] for a in self.listar_avances_oficiales(sesion) if a['ContratoId'] == contrato_id}
        con_dato = [(valores[u['Id']], u['Peso']) for u in unidades if u['Id'] in valores]
        pct, ponderado = promedio_ponderado(con_dato, [u['Peso'] for u in unidades])
        return {'pct': pct, 'ponderado': ponderado, 'reportadas': len(con_dato), 'total': len(unidades)}

    def avance_global(self, sesion):
        """Promedio de los contratos activos del alcance, ponderado por el Peso del contrato cuando todos lo tienen."""
        contratos = [c for c in self.listar_contratos(sesion) if c['Activo']]
        parciales = [(c, self.avance_contrato(sesion, c['Id'])['pct']) for c in contratos]
        con_dato = [(pct, c['Peso']) for c, pct in parciales if pct is not None]
        pct, ponderado = promedio_ponderado(con_dato, [c['Peso'] for c in contratos])
        return {'pct': pct, 'ponderado': ponderado}

    def guardar_pesos_unidades(self, sesion, contrato_id, pesos):
        """pesos: {unidad_id: porcentaje}. Deben estar TODAS las unidades activas del contrato y sumar exactamente 100.
        Las unidades desactivadas conservan su peso pero no cuentan. Todo o nada."""
        self._exigir(sesion, 'ADMIN')
        contrato_id = v.ident(contrato_id, 'contrato')
        cur = self._cursor(sesion)
        cur.execute('SELECT Id FROM Unidad WHERE ContratoId = ? AND Activo = 1', (contrato_id,))
        activas = [f[0] for f in cur.fetchall()]
        if not activas:
            raise NoEncontrado('unidades activas del contrato')
        self._guardar_pesos(cur, sesion, 'Unidad', activas, pesos, contrato_id)

    def guardar_pesos_contratos(self, sesion, pesos):
        """pesos: {contrato_id: porcentaje} para TODOS los contratos activos; suman exactamente 100."""
        self._exigir(sesion, 'ADMIN')
        cur = self._cursor(sesion)
        cur.execute('SELECT Id FROM Contrato WHERE Activo = 1')
        activos = [f[0] for f in cur.fetchall()]
        if not activos:
            raise NoEncontrado('contratos activos')
        self._guardar_pesos(cur, sesion, 'Contrato', activos, pesos, None)

    def _guardar_pesos(self, cur, sesion, tabla, ids, pesos, contrato_id):
        if not isinstance(pesos, dict) or set(pesos) != set(ids):
            raise v.ErrorValidacion('pesos: deben indicarse exactamente todos los elementos activos')
        centavos, limpios = 0, {}
        for k in ids:
            n = pesos[k]
            if isinstance(n, bool) or not isinstance(n, (int, float, str)):
                raise v.ErrorValidacion('peso: debe ser un número')
            try:
                n = float(str(n).replace(',', '.'))
            except ValueError:
                raise v.ErrorValidacion('peso: debe ser un número')
            if not 0 <= n <= 100 or round(n * 100) != n * 100 and abs(round(n * 100) - n * 100) > 1e-6:
                raise v.ErrorValidacion('peso: entre 0 y 100, con hasta 2 decimales')
            limpios[k] = round(n, 2)
            centavos += round(n * 100)
        if centavos != 10000:
            raise v.ErrorValidacion(f'pesos: suman {centavos / 100:g}%, deben sumar exactamente 100%')
        for k, n in limpios.items():
            cur.execute(f'UPDATE {tabla} SET Peso = ? WHERE Id = ?', (n, k))      # el nombre de tabla es una constante interna
        self._auditar(cur, sesion, 'pesos', tabla, contrato_id, contrato_id, f'{len(limpios)} pesos')
        self.conn.commit()

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
            if anterior is None and s['Tipo'] == 'fecha_programada':
                # Sin fecha vigente previa, lo que se reprograma es la fecha contractual (Gabinete ve un "antes" claro).
                cur.execute('SELECT FechaContractual FROM Hito WHERE Id = ?', (ref,))
                anterior = cur.fetchone()[0]
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

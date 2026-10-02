"""Pruebas del backend v8 (SQLite en memoria): perfiles, flujo de aprobación y seguridad.

Ejecutar:  python test_backend.py
"""
import pathlib
import sqlite3
import sys
import unittest
from datetime import date, timedelta

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'backend'))

import repositorio as r   # noqa: E402
import validar as v       # noqa: E402

HOY = date.today()


def d(dias):
    return (HOY + timedelta(days=dias)).isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript((AQUI.parent / 'backend' / 'schema_sqlite.sql').read_text(encoding='utf-8'))
        self.repo = r.Repositorio(self.conn, 'sqlite')
        # Arranque: el primer administrador se crea directo en la base (en producción, desde AD).
        self.conn.execute("INSERT INTO Usuario (Id, Nombre) VALUES ('u_admin', 'Admin Central')")
        self.conn.execute("INSERT INTO Permiso (UsuarioId, Rol, ActualizadoPor) VALUES ('u_admin', 'ADMIN', 'u_admin')")
        self.conn.commit()
        _, self.admin = self.repo.abrir_sesion('u_admin')
        self.c1 = self.repo.guardar_contrato(self.admin, {'nombre': 'Red Aeroportuaria Austral'})
        self.c2 = self.repo.guardar_contrato(self.admin, {'nombre': 'Teleférico Bicentenario'})
        self.u1 = self.repo.guardar_unidad(self.admin, {'contratoId': self.c1, 'nombre': 'Aeródromo Norte'})
        self.u2 = self.repo.guardar_unidad(self.admin, {'contratoId': self.c2, 'nombre': 'Estación Base'})
        self.h1 = self.repo.guardar_hito_base(self.admin, {'unidadId': self.u1, 'tipo': 'PSP', 'fechaContractual': d(60)})
        for uid, nombre, rol, cs in [('u_if', 'Inés Fiscal', 'IF', [self.c1]), ('u_val', 'Valentina Jefa', 'VALIDADOR', [self.c1]),
                                     ('u_val2', 'Otro Jefe', 'VALIDADOR', [self.c2]), ('u_gab', 'Gabinete DG', 'GABINETE', [])]:
            self.repo.guardar_usuario(self.admin, uid, nombre)
            self.repo.guardar_permiso(self.admin, uid, rol, cs)
        self.tok_if, self.inf = self.repo.abrir_sesion('u_if')
        _, self.val = self.repo.abrir_sesion('u_val')
        _, self.val2 = self.repo.abrir_sesion('u_val2')
        _, self.gab = self.repo.abrir_sesion('u_gab')

    def tearDown(self):
        self.conn.close()

    def proponer_avance(self, valor=70, sesion=None):
        return self.repo.proponer(sesion or self.inf, {'tipo': 'avance', 'unidadId': self.u1, 'valor': valor, 'fechaReporte': d(0), 'nota': 'n'})

    def estado(self, sid):
        return self.conn.execute('SELECT Estado, IsDeleted FROM Solicitud WHERE Id = ?', (sid,)).fetchone()


class TestIdentidad(Base):
    def test_cuenta_sin_perfil_no_entra(self):
        self.repo.guardar_usuario(self.admin, 'u_nuevo', 'Persona Nueva')
        with self.assertRaises(r.AccesoDenegado):
            self.repo.abrir_sesion('u_nuevo')

    def test_token_se_guarda_solo_como_hash_y_logout_lo_revoca(self):
        self.assertEqual(self.repo.sesion_desde_token(self.tok_if).rol, 'IF')
        self.assertIsNone(self.conn.execute('SELECT 1 FROM Sesion WHERE TokenHash = ?', (self.tok_if,)).fetchone())
        self.repo.logout(self.tok_if)
        with self.assertRaises(r.AccesoDenegado):
            self.repo.sesion_desde_token(self.tok_if)

    def test_permiso_desactivado_corta_la_sesion(self):
        self.repo.guardar_permiso(self.admin, 'u_if', 'IF', [self.c1], activo=False)
        with self.assertRaises(r.AccesoDenegado):
            self.repo.sesion_desde_token(self.tok_if)

    def test_solo_admin_gestiona_permisos(self):
        with self.assertRaises(r.AccesoDenegado):
            self.repo.guardar_permiso(self.val, 'u_if', 'VALIDADOR', [self.c1])
        with self.assertRaises(v.ErrorValidacion):
            self.repo.guardar_permiso(self.admin, 'u_if', 'IF', [])


class TestFlujo(Base):
    def test_propuesta_queda_pendiente_con_vigente_y_trazabilidad(self):
        sid = self.proponer_avance()
        fila = self.conn.execute('SELECT Estado, ValorAvance, AutorId, EnviadoEn FROM Solicitud WHERE Id = ?', (sid,)).fetchone()
        self.assertEqual(fila[:3], ('PENDIENTE_APROBACION', 70, 'u_if'))
        self.assertIsNotNone(fila[3])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM SolicitudHistorial WHERE SolicitudId = ?', (sid,)).fetchone()[0], 1)

    def test_no_dos_propuestas_activas_para_el_mismo_dato(self):
        self.proponer_avance()
        with self.assertRaises(v.ErrorValidacion):
            self.proponer_avance(80)

    def test_reglas_de_fechas(self):
        with self.assertRaises(v.ErrorValidacion):
            self.repo.proponer(self.inf, {'tipo': 'fecha_programada', 'hitoId': self.h1, 'valor': d(90)})
        with self.assertRaises(v.ErrorValidacion):
            self.repo.proponer(self.inf, {'tipo': 'fecha_real', 'hitoId': self.h1, 'valor': d(5)})
        self.repo.proponer(self.inf, {'tipo': 'fecha_programada', 'hitoId': self.h1, 'valor': d(90), 'nota': 'Permisos'})

    def test_aprobar_publica_el_dato_oficial(self):
        sid = self.proponer_avance()
        self.repo.aprobar(self.val, sid)
        self.assertEqual(self.estado(sid)[0], 'APROBADO')
        oficial = self.repo.listar_avances_oficiales(self.gab)
        self.assertEqual([(a['UnidadId'], a['Valor']) for a in oficial], [(self.u1, 70)])
        hist = self.repo.listar_historial_oficial(self.gab)
        self.assertEqual((hist[0]['ValorAnterior'], hist[0]['ValorNuevo'], hist[0]['RevisorId']), (None, '70', 'u_val'))

    def test_aprobar_fechas_actualiza_hito_oficial(self):
        sp = self.repo.proponer(self.inf, {'tipo': 'fecha_programada', 'hitoId': self.h1, 'valor': d(90), 'nota': 'Permisos'})
        self.repo.aprobar(self.val, sp)
        sr = self.repo.proponer(self.inf, {'tipo': 'fecha_real', 'hitoId': self.h1, 'valor': d(-1)})
        self.repo.aprobar(self.val, sr)
        hito = self.repo.listar_hitos(self.gab)[0]
        self.assertEqual((hito['FechaVigente'], hito['FechaReal']), (d(90), d(-1)))

    def test_nadie_aprueba_lo_propio_ni_en_la_app_ni_en_la_base(self):
        sid = self.proponer_avance(sesion=self.val)
        with self.assertRaises(r.AccesoDenegado):
            self.repo.aprobar(self.val, sid)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE Solicitud SET Estado = 'APROBADO', RevisorId = AutorId WHERE Id = ?", (sid,))

    def test_rechazo_exige_comentario_en_la_app_y_en_la_base(self):
        sid = self.proponer_avance()
        with self.assertRaises(v.ErrorValidacion):
            self.repo.rechazar(self.val, sid, '  ')
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE Solicitud SET Estado = 'RECHAZADO', RevisorId = 'u_val', ComentarioRevision = '' WHERE Id = ?", (sid,))
        self.repo.rechazar(self.val, sid, 'Falta respaldo fotográfico')
        self.assertEqual(self.estado(sid)[0], 'RECHAZADO')

    def test_borrador_enviar_y_cancelar(self):
        sid = self.repo.proponer(self.inf, {'tipo': 'avance', 'unidadId': self.u1, 'valor': 50, 'fechaReporte': d(0)}, enviar=False)
        self.assertEqual(self.estado(sid)[0], 'BORRADOR')
        self.repo.enviar(self.inf, sid)
        self.repo.cancelar(self.inf, sid)
        self.assertEqual(self.estado(sid), ('ELIMINADO', 1))

    def test_no_se_cancela_lo_ya_revisado_ni_lo_ajeno(self):
        sid = self.proponer_avance()
        with self.assertRaises(r.AccesoDenegado):
            self.repo.cancelar(self.val, sid)
        self.repo.aprobar(self.val, sid)
        with self.assertRaises(v.ErrorValidacion):
            self.repo.cancelar(self.inf, sid)

    def test_validador_de_otro_contrato_no_ve_ni_aprueba(self):
        sid = self.proponer_avance()
        self.assertEqual(self.repo.listar_solicitudes(self.val2), [])
        with self.assertRaises(r.NoEncontrado):
            self.repo.aprobar(self.val2, sid)

    def test_if_no_puede_aprobar(self):
        sid = self.proponer_avance(sesion=self.val)
        with self.assertRaises(r.AccesoDenegado):
            self.repo.aprobar(self.inf, sid)


class TestGabineteYAislamiento(Base):
    def test_gabinete_solo_lee_datos_oficiales(self):
        self.proponer_avance(99)
        with self.assertRaises(r.AccesoDenegado):
            self.repo.listar_solicitudes(self.gab)
        with self.assertRaises(r.AccesoDenegado):
            self.repo.listar_problematicas(self.gab)
        self.assertEqual(self.repo.listar_avances_oficiales(self.gab), [])   # la propuesta pendiente no es oficial
        with self.assertRaises(r.AccesoDenegado):
            self.proponer_avance(sesion=self.gab)

    def test_if_solo_opera_en_sus_contratos(self):
        with self.assertRaises(r.NoEncontrado):
            self.repo.proponer(self.inf, {'tipo': 'avance', 'unidadId': self.u2, 'valor': 10, 'fechaReporte': d(0)})
        self.assertEqual({u['ContratoId'] for u in self.repo.listar_unidades(self.inf)}, {self.c1})
        with self.assertRaises(r.NoEncontrado):
            self.repo.crear_problematica(self.inf, {'contratoId': self.c2, 'titulo': 't', 'descripcion': 'd'})

    def test_alertas_para_gabinete(self):
        pid = self.repo.crear_problematica(self.inf, {'unidadId': self.u1, 'titulo': 'Toma de terreno', 'descripcion': 'd',
                                                      'nivelRiesgo': 'Extremo', 'escalamiento': ['Directora']})
        with self.assertRaises(r.AccesoDenegado):
            self.repo.publicar_alerta(self.inf, pid)
        self.repo.publicar_alerta(self.val, pid)
        self.assertEqual([a['Titulo'] for a in self.repo.listar_alertas(self.gab)], ['Toma de terreno'])
        self.repo.retirar_alerta(self.val, pid)
        self.assertEqual(self.repo.listar_alertas(self.gab), [])
        self.assertEqual(self.conn.execute('SELECT IsDeleted FROM AlertaGabinete WHERE ProblematicaId = ?', (pid,)).fetchone()[0], 1)


class TestIntegridad(Base):
    def test_nada_se_borra_fisicamente(self):
        sid = self.proponer_avance()
        pid = self.repo.crear_problematica(self.inf, {'unidadId': self.u1, 'titulo': 't', 'descripcion': 'd'})
        for sql, param in [('DELETE FROM Solicitud WHERE Id = ?', sid), ('DELETE FROM Problematica WHERE Id = ?', pid),
                           ('DELETE FROM Hito WHERE Id = ?', self.h1), ('DELETE FROM Contrato WHERE Id = ?', self.c1)]:
            with self.assertRaises(sqlite3.DatabaseError):
                self.conn.execute(sql, (param,))
        for tabla in ('SolicitudHistorial', 'Auditoria'):
            with self.assertRaises(sqlite3.DatabaseError):
                self.conn.execute(f'DELETE FROM {tabla}')

    def test_eliminaciones_son_logicas(self):
        self.repo.eliminar_hito(self.admin, self.h1)
        self.assertEqual(self.repo.listar_hitos(self.admin), [])
        self.assertEqual(self.conn.execute('SELECT IsDeleted FROM Hito WHERE Id = ?', (self.h1,)).fetchone()[0], 1)

    def test_inyeccion_sql_se_guarda_como_texto(self):
        carga = "x'); DROP TABLE Solicitud; --"
        self.repo.proponer(self.inf, {'tipo': 'avance', 'unidadId': self.u1, 'valor': 10, 'fechaReporte': d(0), 'nota': carga})
        self.assertEqual(self.repo.listar_solicitudes(self.inf)[0]['Nota'], carga)
        with self.assertRaises(v.ErrorValidacion):
            self.repo.proponer(self.inf, {'tipo': 'avance', 'unidadId': "u1' OR '1'='1", 'valor': 10, 'fechaReporte': d(0)})

    def test_autoria_y_fechas_las_pone_el_servidor(self):
        sid = self.repo.proponer(self.inf, {'tipo': 'avance', 'unidadId': self.u1, 'valor': 10, 'fechaReporte': d(0),
                                            'autorId': 'u_admin', 'creadoEn': '1999-01-01', 'estado': 'APROBADO'})
        fila = self.conn.execute('SELECT AutorId, CreadoEn, Estado FROM Solicitud WHERE Id = ?', (sid,)).fetchone()
        self.assertEqual((fila[0], fila[2]), ('u_if', 'PENDIENTE_APROBACION'))
        self.assertFalse(fila[1].startswith('1999'))

    def test_validacion_de_entradas(self):
        for valor in (150, -1, '10; DROP', True):
            with self.assertRaises(v.ErrorValidacion):
                self.repo.proponer(self.inf, {'tipo': 'avance', 'unidadId': self.u1, 'valor': valor, 'fechaReporte': d(0)})
        self.assertEqual(v.texto('a‮b\x00c﻿', 10), 'abc')


class TestV10(Base):
    """v10 (2026-10-02): titular/suplente, correos, motivo de resolución y avisos leídos."""

    def crear_problematica(self):
        return self.repo.crear_problematica(self.inf, {'unidadId': self.u1, 'titulo': 'Toma de terreno', 'descripcion': 'Ocupan el acceso'})

    def test_if_con_dos_contratos_titular_y_suplente(self):
        self.repo.guardar_permiso(self.admin, 'u_if', 'IF', [self.c1, self.c2], roles_contrato={self.c1: 'titular', self.c2: 'suplente'})
        roles = {c['Id']: c['RolContrato'] for c in self.repo.listar_contratos(self.inf)}
        self.assertEqual(roles, {self.c1: 'titular', self.c2: 'suplente'})
        with self.assertRaises(v.ErrorValidacion):
            self.repo.guardar_permiso(self.admin, 'u_if', 'IF', [self.c1], roles_contrato={self.c1: 'jefe'})
        # la base también lo impone
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE UsuarioContrato SET RolContrato = 'otro' WHERE UsuarioId = 'u_if'")

    def test_alcance_de_contratos_listados(self):
        self.assertEqual([c['Id'] for c in self.repo.listar_contratos(self.inf)], [self.c1])
        self.assertEqual(len(self.repo.listar_contratos(self.admin)), 2)
        self.assertEqual(len(self.repo.listar_contratos(self.gab)), 2)

    def test_correos_se_validan_y_se_guardan(self):
        for malo in ('sin-arroba', 'a@b', 'a b@x.cl', '<script>@x.cl'):
            with self.assertRaises(v.ErrorValidacion):
                self.repo.guardar_contrato(self.admin, {'nombre': 'X', 'correoAprobador': malo})
        self.repo.guardar_contrato(self.admin, {'nombre': 'Red Aeroportuaria Austral', 'correoAprobador': 'jefe.depto@example.org'}, self.c1)
        self.assertEqual(self.repo.listar_contratos(self.inf)[0]['CorreoAprobador'], 'jefe.depto@example.org')
        self.repo.guardar_permiso(self.admin, 'u_if', 'IF', [self.c1], email='if.titular@example.org')
        self.assertEqual(self.conn.execute("SELECT Email FROM Usuario WHERE Id = 'u_if'").fetchone()[0], 'if.titular@example.org')
        with self.assertRaises(v.ErrorValidacion):
            self.repo.guardar_permiso(self.admin, 'u_if', 'IF', [self.c1], email='no-es-correo')

    def test_resolver_exige_motivo_y_queda_con_autor(self):
        pid = self.crear_problematica()
        for motivo in (None, '', '   ', 'ok'):
            with self.assertRaises(v.ErrorValidacion):
                self.repo.mover_problematica(self.inf, pid, 'resuelto', motivo)
        self.repo.mover_problematica(self.inf, pid, 'resuelto', 'Se acordó plan de acceso con la comunidad')
        f = self.repo.listar_problematicas(self.inf)[0]
        self.assertEqual((f['Estado'], f['ResolucionTexto'], f['ResolucionPorId']), ('resuelto', 'Se acordó plan de acceso con la comunidad', 'u_if'))
        self.assertIsNotNone(f['ResueltaEn'])

    def test_historial_oficial_de_fecha_programada_parte_de_la_contractual(self):
        sid = self.repo.proponer(self.inf, {'tipo': 'fecha_programada', 'hitoId': self.h1, 'valor': d(90), 'nota': 'Permisos'})
        self.repo.aprobar(self.val, sid)
        h = self.repo.listar_historial_oficial(self.gab)[0]
        self.assertEqual((h['Campo'], h['ValorAnterior'], h['ValorNuevo']), ('fecha_programada', d(60), d(90)))
        sid = self.repo.proponer(self.inf, {'tipo': 'fecha_programada', 'hitoId': self.h1, 'valor': d(100), 'nota': 'Otra vez'})
        self.repo.aprobar(self.val, sid)
        self.assertEqual(self.repo.listar_historial_oficial(self.gab)[0]['ValorAnterior'], d(90))

    def test_la_base_impide_resolver_sin_motivo(self):
        pid = self.crear_problematica()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE Problematica SET Estado = 'resuelto' WHERE Id = ?", (pid,))

    def test_reabrir_conserva_la_resolucion_anterior(self):
        pid = self.crear_problematica()
        self.repo.mover_problematica(self.inf, pid, 'resuelto', 'Primera solución acordada')
        self.repo.mover_problematica(self.inf, pid, 'detectado')
        f = self.repo.listar_problematicas(self.inf)[0]
        self.assertEqual((f['Estado'], f['ResolucionTexto']), ('detectado', None))
        previas = self.repo.listar_resoluciones_previas(self.inf, pid)
        self.assertEqual([x['Texto'] for x in previas], ['Primera solución acordada'])
        with self.assertRaises(sqlite3.IntegrityError):           # solo anexar
            self.conn.execute('UPDATE ProblematicaResolucionPrevia SET Texto = ?', ('x',))
        with self.assertRaises(r.NoEncontrado):                    # y solo dentro del alcance
            self.repo.listar_resoluciones_previas(self.val2, pid)

    def test_avisos_del_if_y_marca_de_lectura(self):
        sid = self.proponer_avance(70)
        self.repo.rechazar(self.val, sid, 'Falta respaldo fotográfico')
        avisos, leido = self.repo.listar_avisos(self.inf)
        self.assertEqual([(a['Estado'], a['ComentarioRevision']) for a in avisos], [('RECHAZADO', 'Falta respaldo fotográfico')])
        self.assertIsNone(leido)
        self.repo.marcar_avisos_leidos(self.inf)
        self.repo.marcar_avisos_leidos(self.inf)                   # idempotente
        self.assertIsNotNone(self.repo.listar_avisos(self.inf)[1])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM LecturaNotificacion').fetchone()[0], 1)
        with self.assertRaises(r.AccesoDenegado):
            self.repo.listar_avisos(self.val)


class TestCargasMasivas(Base):
    """Carga de contratos y subsectores (v10, 2026-10-02): COD_DEAF, todo o nada, nada se borra."""

    def fila(self, **kw):
        base = {'codDeaf': 'DEAF-100', 'nombre': 'Contrato Nuevo', 'unidadLabel': 'Sector', 'inspectorNombre': 'IF Titular',
                'inspectorSuplente': '', 'correoAprobador': 'jefe@example.org'}
        base.update(kw)
        return base

    def test_crea_y_actualiza_por_cod_deaf_sin_borrar(self):
        self.repo.guardar_contrato(self.admin, {'nombre': 'Red Aeroportuaria Austral', 'codDeaf': 'DEAF-001'}, self.c1)
        r1 = self.repo.importar_contratos(self.admin, [self.fila(), self.fila(codDeaf='deaf-001', nombre='Red Austral II')])
        self.assertEqual(r1, {'creados': 1, 'actualizados': 1, 'iguales': 0})
        nombres = {c['CodDeaf']: c['Nombre'] for c in self.repo.listar_contratos(self.admin)}
        self.assertEqual(nombres['DEAF-100'], 'Contrato Nuevo')
        self.assertEqual(nombres['DEAF-001'], 'Red Austral II')
        self.assertEqual(len(self.repo.listar_contratos(self.admin)), 3)          # el c2 sigue ahí
        self.assertEqual(self.repo.importar_contratos(self.admin, [self.fila()])['iguales'], 1)

    def test_actualizar_no_cambia_el_estado_activo(self):
        self.repo.guardar_contrato(self.admin, {'nombre': 'X', 'codDeaf': 'DEAF-200', 'activo': False})
        self.repo.importar_contratos(self.admin, [self.fila(codDeaf='DEAF-200')])
        self.assertEqual(self.conn.execute("SELECT Activo FROM Contrato WHERE CodDeaf = 'DEAF-200'").fetchone()[0], 0)

    def test_todo_o_nada_con_errores_por_fila(self):
        malas = [self.fila(), self.fila(codDeaf=''), self.fila(correoAprobador='malo'), self.fila(nombre='=1+1', codDeaf='DEAF-300'),
                 self.fila(codDeaf='DEAF-100'), self.fila(codDeaf='X Y', nombre='a')]
        with self.assertRaises(r.ErrorCarga) as cm:
            self.repo.importar_contratos(self.admin, malas)
        self.assertEqual([n for n, _ in cm.exception.errores], [2, 3, 4, 5, 6])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM Contrato WHERE CodDeaf IS NOT NULL").fetchone()[0], 0)   # nada se guardó

    def test_cod_deaf_es_unico_tambien_en_la_base(self):
        self.repo.guardar_contrato(self.admin, {'nombre': 'A', 'codDeaf': 'DEAF-1'})
        with self.assertRaises(v.ErrorValidacion):
            self.repo.guardar_contrato(self.admin, {'nombre': 'B', 'codDeaf': 'deaf-1'})
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO Contrato (Id, Nombre, CodDeaf) VALUES ('zz', 'C', 'DEAF-1')")

    def test_solo_admin_importa(self):
        for ses in (self.val, self.inf, self.gab):
            with self.assertRaises(r.AccesoDenegado):
                self.repo.importar_contratos(ses, [self.fila()])
            with self.assertRaises(r.AccesoDenegado):
                self.repo.importar_unidades(ses, [{'codDeaf': 'X', 'nombre': 'Y', 'activo': True}])

    def test_inyeccion_en_carga_se_guarda_como_texto(self):
        carga = "x'); DROP TABLE Contrato; --"
        self.repo.importar_contratos(self.admin, [self.fila(nombre=carga)])
        self.assertEqual(self.conn.execute("SELECT Nombre FROM Contrato WHERE CodDeaf = 'DEAF-100'").fetchone()[0], carga)

    def test_subsectores_crea_reactiva_y_no_borra(self):
        self.repo.guardar_contrato(self.admin, {'nombre': 'Red Aeroportuaria Austral', 'codDeaf': 'DEAF-001'}, self.c1)
        r1 = self.repo.importar_unidades(self.admin, [{'codDeaf': 'DEAF-001', 'nombre': 'Aeródromo Sur', 'activo': True},
                                                      {'codDeaf': 'deaf-001', 'nombre': 'aeródromo norte', 'activo': False}])
        self.assertEqual(r1, {'creados': 1, 'actualizados': 1, 'iguales': 0})
        estados = {u['Nombre']: u['Activo'] for u in self.repo.listar_unidades(self.admin) if u['ContratoId'] == self.c1}
        self.assertEqual(estados, {'Aeródromo Norte': 0, 'Aeródromo Sur': 1})

    def test_subsectores_todo_o_nada(self):
        self.repo.guardar_contrato(self.admin, {'nombre': 'Red Aeroportuaria Austral', 'codDeaf': 'DEAF-001'}, self.c1)
        with self.assertRaises(r.ErrorCarga) as cm:
            self.repo.importar_unidades(self.admin, [{'codDeaf': 'DEAF-001', 'nombre': 'Bueno', 'activo': True},
                                                     {'codDeaf': 'NOEXISTE', 'nombre': 'Fantasma', 'activo': True},
                                                     {'codDeaf': 'DEAF-001', 'nombre': 'bueno', 'activo': True},
                                                     {'codDeaf': 'DEAF-001', 'nombre': 'X', 'activo': 'si'}])
        self.assertEqual([n for n, _ in cm.exception.errores], [2, 3, 4])
        self.assertEqual(len([u for u in self.repo.listar_unidades(self.admin) if u['Nombre'] == 'Bueno']), 0)

    def test_subsector_repetido_en_un_contrato_se_rechaza_pero_no_entre_contratos(self):
        with self.assertRaises(v.ErrorValidacion):
            self.repo.guardar_unidad(self.admin, {'contratoId': self.c1, 'nombre': 'aeródromo norte'})
        with self.assertRaises(v.ErrorValidacion):
            self.repo.guardar_unidad(self.admin, {'contratoId': self.c1, 'nombre': 'AERÓDROMO NORTE'})     # acentos en mayúscula
        self.repo.guardar_unidad(self.admin, {'contratoId': self.c2, 'nombre': 'Aeródromo Norte'})
        self.repo.guardar_unidad(self.admin, {'contratoId': self.c1, 'nombre': 'Norte'})
        with self.assertRaises(sqlite3.IntegrityError):                                                    # y la base lo impone (ASCII)
            self.conn.execute("INSERT INTO Unidad (Id, ContratoId, Nombre) VALUES ('zz', ?, 'NORTE')", (self.c1,))
        # renombrar su propia fila no cuenta como duplicado
        self.repo.guardar_unidad(self.admin, {'contratoId': self.c1, 'nombre': 'Aeródromo Norte', 'activo': False}, self.u1)


class TestPesos(Base):
    """Pesos del avance (v10.8, 2026-10-02): contrato -> unidades, en porcentaje que suma 100."""

    def setUp(self):
        super().setUp()
        self.u1b = self.repo.guardar_unidad(self.admin, {'contratoId': self.c1, 'nombre': 'Aeródromo Segundo'})
        self.repo.guardar_permiso(self.admin, 'u_val', 'VALIDADOR', [self.c1])
        for uid, valor in ((self.u1, 62), (self.u1b, 40), (self.u2, 20)):
            self.conn.execute("INSERT INTO AvanceOficial (UnidadId, ContratoId, Valor, FechaReporte) "
                              "SELECT ?, ContratoId, ?, '2026-09-01' FROM Unidad WHERE Id = ?", (uid, valor, uid))
        self.conn.commit()

    def test_sin_pesos_es_promedio_simple(self):
        a = self.repo.avance_contrato(self.admin, self.c1)
        self.assertEqual((a['pct'], a['ponderado'], a['reportadas'], a['total']), (51, False, 2, 2))

    def test_con_pesos_se_pondera(self):
        self.repo.guardar_pesos_unidades(self.admin, self.c1, {self.u1: 70, self.u1b: '30'})
        a = self.repo.avance_contrato(self.admin, self.c1)
        self.assertEqual((a['pct'], a['ponderado']), (55, True))              # 0,7*62 + 0,3*40 = 55,4

    def test_sin_dato_no_cuenta_como_cero_y_se_renormaliza(self):
        self.repo.guardar_pesos_unidades(self.admin, self.c1, {self.u1: 70, self.u1b: 30})
        self.conn.execute('DELETE FROM AvanceOficial WHERE UnidadId = ?', (self.u1b,))
        a = self.repo.avance_contrato(self.admin, self.c1)
        self.assertEqual((a['pct'], a['reportadas'], a['total']), (62, 1, 2))

    def test_falta_un_peso_vuelve_al_promedio_simple(self):
        self.repo.guardar_pesos_unidades(self.admin, self.c1, {self.u1: 70, self.u1b: 30})
        nueva = self.repo.guardar_unidad(self.admin, {'contratoId': self.c1, 'nombre': 'Nueva sin peso'})
        self.assertFalse(self.repo.avance_contrato(self.admin, self.c1)['ponderado'])
        self.repo.guardar_unidad(self.admin, {'contratoId': self.c1, 'nombre': 'Nueva sin peso', 'activo': False}, nueva)
        self.assertTrue(self.repo.avance_contrato(self.admin, self.c1)['ponderado'])      # desactivada: no cuenta

    def test_los_pesos_deben_sumar_100_y_estar_todos(self):
        for malo in ({self.u1: 60, self.u1b: 30}, {self.u1: 70}, {self.u1: 70, self.u1b: 40}, {self.u1: -10, self.u1b: 110},
                     {self.u1: 'abc', self.u1b: 30}, {self.u1: 33.333, self.u1b: 66.667}, {self.u1: True, self.u1b: 99}):
            with self.assertRaises(v.ErrorValidacion):
                self.repo.guardar_pesos_unidades(self.admin, self.c1, malo)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM Unidad WHERE Peso IS NOT NULL').fetchone()[0], 0)   # nada se guardó
        self.repo.guardar_pesos_unidades(self.admin, self.c1, {self.u1: '33,33', self.u1b: '66,67'})

    def test_la_base_impide_pesos_fuera_de_rango(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('UPDATE Unidad SET Peso = 101 WHERE Id = ?', (self.u1,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('UPDATE Contrato SET Peso = -1 WHERE Id = ?', (self.c1,))

    def test_global_ponderado_por_contrato(self):
        self.repo.guardar_pesos_unidades(self.admin, self.c1, {self.u1: 70, self.u1b: 30})
        self.repo.guardar_pesos_unidades(self.admin, self.c2, {self.u2: 100})
        self.assertEqual(self.repo.avance_global(self.admin), {'pct': 38, 'ponderado': False})      # sin peso de contrato: (55 + 20) / 2
        self.repo.guardar_pesos_contratos(self.admin, {self.c1: 75, self.c2: 25})
        self.assertEqual(self.repo.avance_global(self.admin), {'pct': 46, 'ponderado': True})      # 0,75*55 + 0,25*20
        with self.assertRaises(v.ErrorValidacion):
            self.repo.guardar_pesos_contratos(self.admin, {self.c1: 75, self.c2: 20})

    def test_solo_admin_configura_pesos(self):
        for ses in (self.val, self.inf, self.gab):
            with self.assertRaises(r.AccesoDenegado):
                self.repo.guardar_pesos_unidades(ses, self.c1, {self.u1: 50, self.u1b: 50})
            with self.assertRaises(r.AccesoDenegado):
                self.repo.guardar_pesos_contratos(ses, {self.c1: 50, self.c2: 50})

    def test_gabinete_y_validador_leen_el_avance_ponderado(self):
        self.repo.guardar_pesos_unidades(self.admin, self.c1, {self.u1: 70, self.u1b: 30})
        self.assertEqual(self.repo.avance_contrato(self.gab, self.c1)['pct'], 55)
        self.assertEqual(self.repo.avance_contrato(self.val, self.c1)['pct'], 55)


class TestRegistroDeCambios(Base):
    """Registro de modificaciones auditable (v10.9, 2026-10-02): toda operación que cambia datos deja su anotación."""

    def ultima(self):
        return self.conn.execute('SELECT ActorId, Rol, Accion, Entidad, EntidadId, ContratoId, Detalle, OcurridoEn FROM Auditoria ORDER BY Id DESC LIMIT 1').fetchone()

    def total(self):
        return self.conn.execute('SELECT COUNT(*) FROM Auditoria').fetchone()[0]

    def test_toda_operacion_que_modifica_datos_deja_anotacion_con_su_autor(self):
        repo, admin, inf, val = self.repo, self.admin, self.inf, self.val
        pid = {}

        def repartir(ids):
            base = int(10000 / len(ids)) / 100
            pesos = {i: base for i in ids}
            pesos[ids[-1]] = round(100 - base * (len(ids) - 1), 2)
            return pesos

        pasos = [
            ('Contrato', admin, lambda: repo.guardar_contrato(admin, {'nombre': 'Nuevo', 'codDeaf': 'N-1'})),
            ('Unidad', admin, lambda: repo.guardar_unidad(admin, {'contratoId': self.c1, 'nombre': 'Otra unidad'})),
            ('Hito', admin, lambda: repo.guardar_hito_base(admin, {'unidadId': self.u1, 'tipo': 'PSD', 'fechaContractual': d(90)})),
            ('Hito', admin, lambda: repo.eliminar_hito(admin, self.h1)),
            ('Usuario', admin, lambda: repo.guardar_usuario(admin, 'u_x', 'Persona X', 'x@example.org')),
            ('Permiso', admin, lambda: repo.guardar_permiso(admin, 'u_x', 'IF', [self.c1], roles_contrato={self.c1: 'suplente'}, email='x@example.org')),
            ('Contrato', admin, lambda: repo.importar_contratos(admin, [{'codDeaf': 'N-2', 'nombre': 'Dos', 'unidadLabel': 'Sector', 'inspectorNombre': 'IF', 'correoAprobador': 'a@example.org'}])),
            ('Unidad', admin, lambda: repo.importar_unidades(admin, [{'codDeaf': 'N-2', 'nombre': 'Sub', 'activo': True}])),
            ('Unidad', admin, lambda: repo.guardar_pesos_unidades(admin, self.c1, repartir([u['Id'] for u in repo.listar_unidades(admin) if u['ContratoId'] == self.c1 and u['Activo']]))),
            ('Contrato', admin, lambda: repo.guardar_pesos_contratos(admin, repartir([c['Id'] for c in repo.listar_contratos(admin) if c['Activo']]))),
            ('Solicitud', inf, lambda: pid.update(s=repo.proponer(inf, {'tipo': 'avance', 'unidadId': self.u1, 'valor': 70, 'fechaReporte': d(0), 'nota': 'n'}, enviar=False))),
            ('Solicitud', inf, lambda: repo.enviar(inf, pid['s'])),
            ('Solicitud', inf, lambda: repo.cancelar(inf, pid['s'])),
            ('Solicitud', inf, lambda: pid.update(s=self.proponer_avance(60))),
            ('Solicitud', val, lambda: repo.aprobar(val, pid['s'])),
            ('Solicitud', inf, lambda: pid.update(s=self.proponer_avance(65))),
            ('Solicitud', val, lambda: repo.rechazar(val, pid['s'], 'Falta respaldo')),
            ('Problematica', inf, lambda: pid.update(p=repo.crear_problematica(inf, {'unidadId': self.u1, 'titulo': 'T', 'descripcion': 'D', 'nivelRiesgo': 'Extremo', 'checklist': ['a']}))),
            ('Problematica', inf, lambda: repo.mover_problematica(inf, pid['p'], 'escalado')),
            ('ProblematicaTarea', inf, lambda: repo.alternar_tarea(inf, self.conn.execute('SELECT Id FROM ProblematicaTarea').fetchone()[0], True)),
            ('Problematica', inf, lambda: repo.agregar_nota(inf, pid['p'], 'una nota')),
            ('AlertaGabinete', val, lambda: repo.publicar_alerta(val, pid['p'])),
            ('AlertaGabinete', val, lambda: repo.retirar_alerta(val, pid['p'])),
            ('Problematica', inf, lambda: repo.eliminar_problematica(inf, pid['p'])),
        ]
        for entidad, ses, accion in pasos:
            antes = self.total()
            accion()
            self.assertGreater(self.total(), antes, f'sin anotación en el paso de {entidad}')
            ult = self.ultima()
            self.assertEqual((ult[0], ult[1]), (ses.usuario_id, ses.rol), f'autor incorrecto en {entidad}')
            self.assertTrue(ult[7].startswith(str(HOY.year)), 'la fecha la pone la base')

    def test_el_registro_guarda_el_antes_y_el_despues(self):
        self.repo.guardar_contrato(self.admin, {'nombre': 'Red Aeroportuaria Austral', 'codDeaf': 'D-1'}, self.c1)
        self.repo.guardar_contrato(self.admin, {'nombre': 'Red Austral II', 'codDeaf': 'D-1'}, self.c1)
        ult = self.ultima()
        self.assertEqual((ult[2], ult[3]), ('editar', 'Contrato'))
        self.assertIn('Nombre: Red Aeroportuaria Austral -> Red Austral II', ult[6])
        self.assertNotIn('COD_DEAF', ult[6])                                       # lo que no cambió no se anota
        self.repo.guardar_permiso(self.admin, 'u_if', 'VALIDADOR', [self.c1])
        self.assertIn('Perfil: IF -> VALIDADOR', self.ultima()[6])

    def test_solo_admin_lee_el_registro_y_se_puede_filtrar(self):
        self.proponer_avance(70)
        for ses in (self.inf, self.val, self.gab):
            with self.assertRaises(r.AccesoDenegado):
                self.repo.listar_auditoria(ses)
        todo = self.repo.listar_auditoria(self.admin)
        self.assertTrue(todo and todo[0]['Id'] > todo[-1]['Id'])                   # más reciente primero
        sol = self.repo.listar_auditoria(self.admin, entidad='Solicitud')
        self.assertTrue(sol and all(f['Entidad'] == 'Solicitud' for f in sol))
        self.assertTrue(all(f['ActorId'] == 'u_if' for f in self.repo.listar_auditoria(self.admin, entidad='Solicitud', actor_id='u_if')))
        self.assertEqual(self.repo.listar_auditoria(self.admin, desde='2099-01-01'), [])
        self.assertTrue(self.repo.listar_auditoria(self.admin, desde=d(-1), hasta=d(0)))
        self.assertLessEqual(len(self.repo.listar_auditoria(self.admin, limite=2)), 2)
        with self.assertRaises(v.ErrorValidacion):
            self.repo.listar_auditoria(self.admin, entidad="x' OR '1'='1" * 50, limite=0)

    def test_el_registro_es_de_solo_anexar(self):
        self.proponer_avance(70)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE Auditoria SET Detalle = 'manipulado'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('DELETE FROM Auditoria')

    def test_las_operaciones_rechazadas_no_dejan_anotacion_falsa(self):
        antes = self.total()
        with self.assertRaises(v.ErrorValidacion):
            self.repo.guardar_contrato(self.admin, {'nombre': 'X', 'correoAprobador': 'malo'})
        with self.assertRaises(r.AccesoDenegado):
            self.repo.guardar_contrato(self.inf, {'nombre': 'X'})
        self.assertEqual(self.total(), antes)


if __name__ == '__main__':
    unittest.main(verbosity=2)

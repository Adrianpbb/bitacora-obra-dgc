"""Validación y normalización de entradas de la Bitácora de Obra.

Espejo de las reglas del frontend (bitacora-obra.html, sección 2): mismo recorte
de caracteres de control, mismos largos máximos, mismas listas cerradas. Si cambias
una regla aquí, cámbiala también allá, o los hashes de auditoría dejarán de calzar.
"""
import re
from datetime import date

LIM = dict(nombre=150, titulo=200, texto=4000, nota=2000, label=50, tag=80, tags=20,
           checklist=30, tarea=300, inspector=150, motivo=2000, correo=254, cod_deaf=40)

HITO_TIPOS = ('Ingeniería', 'Inicio Físico', 'PSP', 'PSD', 'Informe de avance', 'Fase de construcción')
RIESGOS = ('Extremo', 'Alto', 'Medio', 'Bajo')
PB_ESTADOS = ('detectado', 'en_gestion', 'escalado', 'resuelto')
ESCALAMIENTOS = ('Jefe de División', 'Directora', 'Jurídica', 'Otro')
SOL_TIPOS = ('avance', 'fecha_programada', 'fecha_real')
SOL_ESTADOS = ('BORRADOR', 'PENDIENTE_APROBACION', 'APROBADO', 'RECHAZADO', 'ELIMINADO')
ROLES = ('IF', 'VALIDADOR', 'ADMIN', 'GABINETE')
ROLES_CONTRATO = ('titular', 'suplente')

_CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
# Caracteres invisibles de control bidireccional/BOM: permiten disfrazar texto ("Trojan Source").
_INVISIBLES = re.compile('[‪-‮⁦-⁩‎‏؜﻿]')
_ID = re.compile(r'^[A-Za-z0-9_\-.~:@+]{1,200}$')
_FECHA = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_COD_DEAF = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}$')
_CORREO = re.compile(r'^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$')


class ErrorValidacion(ValueError):
    pass


def texto(v, maximo, multilinea=False, requerido=False, campo='campo'):
    if v is None:
        v = ''
    if not isinstance(v, str):
        raise ErrorValidacion(f'{campo}: debe ser texto')
    s = _INVISIBLES.sub('', _CTRL.sub('', v))
    s = re.sub(r'\r\n?', '\n', s) if multilinea else re.sub(r'[\r\n\t]+', ' ', s)
    s = s.strip()[:maximo]
    if requerido and not s:
        raise ErrorValidacion(f'{campo}: es obligatorio')
    return s


def correo(v, requerido=False, campo='correo'):
    """Correo electrónico (mismo patrón que cleanEmail del frontend). Vacío = sin correo."""
    s = texto(v, LIM['correo'], campo=campo)
    if not s:
        if requerido:
            raise ErrorValidacion(f'{campo}: es obligatorio')
        return ''
    if len(s) > LIM['correo'] or not _CORREO.match(s):
        raise ErrorValidacion(f'{campo}: formato de correo inválido')
    return s


def cod_deaf(v, requerido=True, campo='COD_DEAF'):
    s = texto(v, 100, campo=campo)
    if not s:
        if requerido:
            raise ErrorValidacion(f'{campo}: es obligatorio')
        return None
    if not _COD_DEAF.match(s):
        raise ErrorValidacion(f'{campo}: solo admite letras, números y . _ - /')
    return s


def sin_formula(s, campo='campo'):
    """Texto que no empieza con = + - @ (higiene frente a fórmulas si el dato se exporta a Excel)."""
    if s and s[0] in '=+-@':
        raise ErrorValidacion(f'{campo}: no puede comenzar con = + - @')
    return s


def fecha(v, requerido=False, campo='fecha'):
    if v in (None, ''):
        if requerido:
            raise ErrorValidacion(f'{campo}: es obligatoria')
        return None
    if not isinstance(v, str) or not _FECHA.match(v):
        raise ErrorValidacion(f'{campo}: formato esperado AAAA-MM-DD')
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ErrorValidacion(f'{campo}: fecha inexistente')
    if not 1990 <= d.year <= 2100:
        raise ErrorValidacion(f'{campo}: fuera de rango')
    return v


def entero(v, minimo, maximo, campo='número'):
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        raise ErrorValidacion(f'{campo}: debe ser un número entero')
    if isinstance(v, str):
        if not re.fullmatch(r'-?\d+', v.strip()):
            raise ErrorValidacion(f'{campo}: debe ser un número entero')
        v = int(v.strip())
    if not minimo <= v <= maximo:
        raise ErrorValidacion(f'{campo}: debe estar entre {minimo} y {maximo}')
    return v


def opcion(v, permitidas, campo='opción', requerido=True):
    if v in (None, '') and not requerido:
        return None
    if v not in permitidas:
        raise ErrorValidacion(f'{campo}: valor no permitido')
    return v


def lista_textos(v, max_items, max_largo, permitidas=None, campo='lista'):
    if v is None:
        return []
    if not isinstance(v, (list, tuple)):
        raise ErrorValidacion(f'{campo}: debe ser una lista')
    out = []
    for item in v:
        if not isinstance(item, str):
            continue
        s = texto(item, max_largo)
        if not s or s in out:
            continue
        if permitidas is not None and s not in permitidas:
            raise ErrorValidacion(f'{campo}: valor no permitido "{s}"')
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def ident(v, campo='id'):
    if not isinstance(v, str) or not _ID.match(v) or v in ('.', '..'):
        raise ErrorValidacion(f'{campo}: identificador inválido')
    return v

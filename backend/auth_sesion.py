"""Tokens de sesión de la Bitácora de Obra.

La identidad de cada persona la entrega el inicio de sesión institucional (AD /
Entra ID, SSO): este backend NO maneja contraseñas ni claves por contrato (se
retiraron el 2026-10-01). Una vez validada la identidad, repositorio.abrir_sesion()
emite un token aleatorio; en la base solo se guarda su SHA-256, nunca el token.
El token viaja al navegador en una cookie HttpOnly + Secure + SameSite=Strict.
"""
import hashlib
import secrets

HORAS_SESION = 8


def nuevo_token():
    """Devuelve (token_para_el_cliente, hash_para_guardar)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

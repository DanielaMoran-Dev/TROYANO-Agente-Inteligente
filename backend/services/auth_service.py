"""
Auth Service — bcrypt password hashing for users and doctors.

Usa bcrypt directamente (no passlib) para evitar incompatibilidades con
la última versión de bcrypt en Python 3.12+.
"""

import bcrypt

_ROUNDS = 12  # factor de coste recomendado para bcrypt


def hash_password(plain: str) -> str:
    """
    Hashea un password con bcrypt. Devuelve el hash como str UTF-8,
    listo para guardarse en MongoDB.
    """
    if not plain:
        raise ValueError("El password no puede estar vacío.")
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    """
    Verifica un password en plano contra un hash existente.
    Devuelve False en vez de lanzar si el hash está corrupto.
    """
    if not plain or not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False

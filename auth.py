"""
Acceso de administrador para la aplicación de torneos.

Hay una única cuenta, "Administrador", con permiso para hacer sorteos y
gestionar torneos. Quien no se identifica entra como invitado y solo puede
consultar.

Seguridad:
- La contraseña nunca se guarda: se almacena un hash PBKDF2-HMAC-SHA256 con
  sal aleatoria y 600.000 iteraciones, y se compara en tiempo constante.
- Tras 5 contraseñas incorrectas seguidas el acceso de administrador queda
  bloqueado 5 minutos. El contador se guarda en la base de datos, así que
  cerrar y abrir el navegador no lo reinicia.
- Contraseña mínima de 8 caracteres.

Línea de comandos (por ejemplo, si olvidas la contraseña; hay que tener acceso
a la máquina donde corre la aplicación):

    python auth.py --establecer-password
"""

import argparse
import getpass
import hashlib
import hmac
import math
import secrets
import time
from typing import NamedTuple, Optional

import torneo as db

USUARIO_ADMIN = "Administrador"
ALGORITMO = "pbkdf2_sha256"
ITERACIONES = 600_000
MIN_LONGITUD = 8
MAX_LONGITUD = 256
MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 300


class Resultado(NamedTuple):
    ok: bool
    mensaje: str = ""


# ---------------------------------------------------------------------------
# Hash de contraseña
# ---------------------------------------------------------------------------

def _hash(password: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sal, ITERACIONES)
    return f"{ALGORITMO}${ITERACIONES}${sal.hex()}${derivada.hex()}"


def _comprobar(password: str, almacenado: str) -> bool:
    try:
        algoritmo, iteraciones, sal, esperado = almacenado.split("$")
        if algoritmo != ALGORITMO:
            return False
        derivada = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(sal), int(iteraciones))
        return hmac.compare_digest(derivada.hex(), esperado)
    except (ValueError, AttributeError):
        return False


def _validar_nueva(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_LONGITUD:
        raise ValueError(f"La contraseña debe tener al menos {MIN_LONGITUD} caracteres.")
    if len(password) > MAX_LONGITUD:
        raise ValueError(f"La contraseña no puede superar los {MAX_LONGITUD} caracteres.")
    if not password.strip():
        raise ValueError("La contraseña no puede estar formada solo por espacios.")


# ---------------------------------------------------------------------------
# Acceso a la configuración guardada
# ---------------------------------------------------------------------------

def _leer(con, clave: str, defecto: Optional[str] = None) -> Optional[str]:
    fila = con.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila else defecto


def _guardar(con, clave: str, valor: str) -> None:
    con.execute(
        "INSERT INTO config (clave, valor) VALUES (?, ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, valor))


def _reiniciar_intentos(con) -> None:
    _guardar(con, "intentos_fallidos", "0")
    _guardar(con, "bloqueado_hasta", "0")


def _mensaje_bloqueo(segundos: float) -> str:
    minutos = max(1, math.ceil(segundos / 60))
    unidad = "minuto" if minutos == 1 else "minutos"
    return f"Demasiados intentos fallidos. Inténtalo de nuevo en {minutos} {unidad}."


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def hay_admin() -> bool:
    with db._conexion() as con:
        return _leer(con, "admin_hash") is not None


def crear_admin(password: str) -> None:
    """Define la contraseña del administrador la primera vez. Falla si ya existe."""
    _validar_nueva(password)
    with db._conexion() as con:
        con.execute("BEGIN IMMEDIATE")
        if _leer(con, "admin_hash") is not None:
            raise ValueError("Ya existe un administrador configurado.")
        _guardar(con, "admin_hash", _hash(password))
        _reiniciar_intentos(con)


def verificar_admin(password: str, ahora: Optional[float] = None) -> Resultado:
    """Comprueba la contraseña aplicando el límite de intentos."""
    ahora = time.time() if ahora is None else ahora
    with db._conexion() as con:
        con.execute("BEGIN IMMEDIATE")  # evita que dos sesiones se salten el contador
        almacenado = _leer(con, "admin_hash")
        if almacenado is None:
            return Resultado(False, "Todavía no hay un administrador configurado.")

        bloqueado_hasta = float(_leer(con, "bloqueado_hasta", "0"))
        if bloqueado_hasta > ahora:
            return Resultado(False, _mensaje_bloqueo(bloqueado_hasta - ahora))
        if bloqueado_hasta:  # el bloqueo ya terminó: se empieza de cero
            _reiniciar_intentos(con)

        if _comprobar(password or "", almacenado):
            _reiniciar_intentos(con)
            return Resultado(True)

        intentos = int(_leer(con, "intentos_fallidos", "0")) + 1
        if intentos >= MAX_INTENTOS:
            _guardar(con, "intentos_fallidos", "0")
            _guardar(con, "bloqueado_hasta", str(ahora + BLOQUEO_SEGUNDOS))
            return Resultado(False, _mensaje_bloqueo(BLOQUEO_SEGUNDOS))
        _guardar(con, "intentos_fallidos", str(intentos))
        restantes = MAX_INTENTOS - intentos
        return Resultado(False, f"Contraseña incorrecta. Te quedan {restantes} "
                                f"intento{'s' if restantes != 1 else ''}.")


def cambiar_password(actual: str, nueva: str, ahora: Optional[float] = None) -> Resultado:
    """Cambia la contraseña comprobando antes la actual (con el mismo límite de intentos)."""
    try:
        _validar_nueva(nueva)
    except ValueError as e:
        return Resultado(False, str(e))
    comprobacion = verificar_admin(actual, ahora)
    if not comprobacion.ok:
        return comprobacion
    with db._conexion() as con:
        _guardar(con, "admin_hash", _hash(nueva))
    return Resultado(True)


def establecer_password(nueva: str) -> None:
    """Fija la contraseña sin pedir la anterior y quita cualquier bloqueo (uso por línea de comandos)."""
    _validar_nueva(nueva)
    with db._conexion() as con:
        con.execute("BEGIN IMMEDIATE")
        _guardar(con, "admin_hash", _hash(nueva))
        _reiniciar_intentos(con)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestión de la contraseña del administrador")
    parser.add_argument("--establecer-password", action="store_true",
                        help="Crea o restablece la contraseña del administrador")
    args = parser.parse_args()
    if not args.establecer_password:
        parser.print_help()
        return
    nueva = getpass.getpass("Nueva contraseña de administrador: ")
    if nueva != getpass.getpass("Repite la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden.")
    try:
        establecer_password(nueva)
    except ValueError as e:
        raise SystemExit(str(e))
    print("Contraseña de administrador guardada.")


if __name__ == "__main__":
    main()

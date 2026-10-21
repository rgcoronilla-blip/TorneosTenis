"""Pruebas de auth.py: hash, alta, verificación, bloqueo por intentos y cambio de contraseña."""
import os
import sqlite3
import tempfile

import auth
import torneo as db

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "auth.db")
auth.ITERACIONES = 1000  # solo para que los tests vayan rápido; el hash guarda sus iteraciones
T0 = 1_000_000.0


def falla(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    raise SystemExit(f"debería haber fallado: {fn.__name__}{a}")


# 1) Sin administrador configurado
assert auth.hay_admin() is False
r = auth.verificar_admin("lo-que-sea", T0)
assert not r.ok and "no hay un administrador" in r.mensaje.lower()
print("OK 1: sin administrador no se puede entrar")

# 2) Alta: validaciones y guardado seguro
for mala in ["", "corta", "1234567", " " * 10, "x" * 300]:
    falla(auth.crear_admin, mala)
assert auth.hay_admin() is False
auth.crear_admin("Clave-segura-1")
assert auth.hay_admin() is True
falla(auth.crear_admin, "Otra-clave-2")            # no se puede crear dos veces
raw = sqlite3.connect(db.DB_PATH).execute("SELECT valor FROM config WHERE clave='admin_hash'").fetchone()[0]
partes = raw.split("$")
assert partes[0] == "pbkdf2_sha256" and partes[1] == "1000" and len(partes[2]) == 32 and len(partes[3]) == 64
assert "Clave-segura-1" not in raw
volcado = "".join(str(f) for f in sqlite3.connect(db.DB_PATH).execute("SELECT * FROM config"))
assert "Clave-segura-1" not in volcado
assert auth.verificar_admin("Clave-segura-1", T0).ok   # el segundo alta fallido no cambió la contraseña
print("OK 2: alta validada, solo se guarda el hash con sal")

# 3) Dos hashes de la misma contraseña son distintos (sal aleatoria)
assert auth._hash("misma-clave-9") != auth._hash("misma-clave-9")
assert auth._comprobar("misma-clave-9", auth._hash("misma-clave-9"))
assert not auth._comprobar("otra-clave-99", auth._hash("misma-clave-9"))
for basura in ["", "x", "a$b$c$d", "pbkdf2_sha256$no-numero$00$00", None]:
    assert auth._comprobar("lo-que-sea", basura) is False
print("OK 3: sal aleatoria y hash corrupto rechazado sin romper")

# 4) Contraseña incorrecta: cuenta atrás y bloqueo al 5.º fallo
for esperados in (4, 3, 2, 1):
    r = auth.verificar_admin("mal", T0)
    assert not r.ok and f"{esperados} intento" in r.mensaje, r
r = auth.verificar_admin("mal", T0)                     # 5.º fallo
assert not r.ok and "5 minutos" in r.mensaje, r
# durante el bloqueo ni siquiera la contraseña correcta entra
r = auth.verificar_admin("Clave-segura-1", T0 + 60)
assert not r.ok and "4 minutos" in r.mensaje, r
r = auth.verificar_admin("Clave-segura-1", T0 + auth.BLOQUEO_SEGUNDOS - 1)
assert not r.ok and "1 minuto" in r.mensaje and "minutos" not in r.mensaje, r
print("OK 4: bloqueo tras 5 fallos, incluso con la contraseña correcta")

# 5) Al acabar el bloqueo se puede entrar y el contador vuelve a cero
t1 = T0 + auth.BLOQUEO_SEGUNDOS + 1
assert auth.verificar_admin("mal", t1).mensaje.endswith("Te quedan 4 intentos.")   # empieza de cero
assert auth.verificar_admin("Clave-segura-1", t1).ok
assert auth.verificar_admin("mal", t1).mensaje.endswith("Te quedan 4 intentos.")   # el éxito reinició el contador
auth.verificar_admin("Clave-segura-1", t1)
print("OK 5: el bloqueo caduca y un acceso correcto reinicia el contador")

# 6) El bloqueo persiste en la base de datos (sobrevive a otra sesión/conexión)
for _ in range(auth.MAX_INTENTOS):
    auth.verificar_admin("mal", t1)
assert not auth.verificar_admin("Clave-segura-1", t1 + 5).ok
print("OK 6: el bloqueo está en la base de datos")

# 7) Cambio de contraseña
t2 = t1 + 10_000
assert not auth.cambiar_password("incorrecta", "Nueva-clave-77", t2).ok
assert auth.verificar_admin("Clave-segura-1", t2).ok                        # sigue la antigua
r = auth.cambiar_password("Clave-segura-1", "corta", t2)
assert not r.ok and "al menos 8" in r.mensaje
assert auth.verificar_admin("Clave-segura-1", t2).ok
assert auth.cambiar_password("Clave-segura-1", "Nueva-clave-77", t2).ok
assert not auth.verificar_admin("Clave-segura-1", t2).ok
assert auth.verificar_admin("Nueva-clave-77", t2).ok
# cambiar la contraseña también está limitado por intentos
t3 = t2 + 10_000
for _ in range(auth.MAX_INTENTOS):
    auth.cambiar_password("mal", "Otra-nueva-88", t3)
r = auth.cambiar_password("Nueva-clave-77", "Otra-nueva-88", t3 + 1)
assert not r.ok and "Demasiados" in r.mensaje
assert not auth.verificar_admin("Otra-nueva-88", t3 + auth.BLOQUEO_SEGUNDOS + 1).ok
print("OK 7: cambio de contraseña (con límite de intentos)")

# 8) Restablecimiento por línea de comandos: nueva contraseña y desbloqueo
for _ in range(auth.MAX_INTENTOS):
    auth.verificar_admin("mal", t3)
assert not auth.verificar_admin("Nueva-clave-77", t3).ok
falla(auth.establecer_password, "corta")
auth.establecer_password("Restablecida-55")
assert auth.verificar_admin("Restablecida-55", t3).ok
assert not auth.verificar_admin("Nueva-clave-77", t3).ok
print("OK 8: restablecer contraseña quita el bloqueo")

# 9) Los datos de torneos no se ven afectados por la tabla de configuración
assert db.buscar_torneos() == []
print("TODO OK AUTH")

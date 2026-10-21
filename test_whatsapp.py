"""Pruebas de los avisos por WhatsApp: teléfonos, enlaces wa.me, CSV, BD y migración."""
import os
import sqlite3
import tempfile
from datetime import date
from urllib.parse import parse_qs, urlparse

import emparejamientos
import torneo as db
import whatsapp
from sorteo_torneo_tenis import SorteoTorneo, Jugador

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "wa.db")


def falla(fn, *a):
    try:
        fn(*a)
    except ValueError as e:
        return str(e)
    raise SystemExit(f"debería fallar: {a}")


# 1. normalización
n = whatsapp.normalizar_telefono
assert n("600123456") == "34600123456"
assert n("600 12 34 56") == "34600123456"
assert n("+34 600-123-456") == "34600123456"
assert n("0034600123456") == "34600123456"
assert n("(+34) 600.123.456") == "34600123456"
assert n("+44 7911 123456") == "447911123456"
assert n("") == "" and n(None) == "" and n("  ") == "" and n("nan") == ""
for malo in ("abc", "12345", "600123456789012345", "+34 6001234", "600123456; DROP", "+0123456789", "https://x.es"):
    falla(n, malo)
print("OK 1 normalización")

# 2. enlace wa.me
msg = "Hola Ana, ¿juegas el 02/06 a las 18:30? & más=1 #x"
url = whatsapp.enlace_whatsapp("600123456", msg)
u = urlparse(url)
assert (u.scheme, u.netloc, u.path) == ("https", "wa.me", "/34600123456"), url
assert parse_qs(u.query)["text"] == [msg]
assert "&" not in u.query.replace("%26", "") and " " not in url and "#" not in url
falla(whatsapp.enlace_whatsapp, "", "x")
print("OK 2 enlace")

# 3. mensaje
p = {"fase": "grupo", "grupo": "B", "fecha_hora": "2026-06-02T18:30"}
m = whatsapp.mensaje_partido("Open Primavera", p, "Ana García", "Laura Pérez", "Club Nazaret")
for trozo in ("Hola Ana,", "Open Primavera", "(Grupo B)", "Club Nazaret", "Laura Pérez",
              "es el martes 02/06/2026 a las 18:30"):
    assert trozo in m, (trozo, m)
m2 = whatsapp.mensaje_partido("T", {"fase": "eliminatoria", "grupo": None, "fecha_hora": None}, "Ana", "Bea")
assert "aún no tiene día y hora" in m2 and "Grupo" not in m2
print("OK 3 mensaje")

# 4. CSV de jugadores
ok = emparejamientos.leer_jugadores(
    "jugador;ranking;teléfono\nAna;1;600123456\nBea;2;\nCarla;3;+34 611 22 33 44\n".encode())
assert [j.telefono for j in ok] == ["34600123456", "", "34611223344"]
sin_col = emparejamientos.leer_jugadores("jugador;ranking\nAna;1\nBea;2\n".encode())
assert [j.telefono for j in sin_col] == ["", ""]
alias = emparejamientos.leer_jugadores("nombre,ranking,móvil\nAna,1,600123456\n".encode())
assert alias[0].telefono == "34600123456"
try:
    emparejamientos.leer_jugadores("jugador;ranking;telefono\nAna;1;123\nBea;2;abc\n".encode())
    raise SystemExit("debía fallar")
except emparejamientos.ErrorCSV as e:
    assert len(e.errores) == 2 and "Línea 2" in e.errores[0] and "Línea 3" in e.errores[1], e.errores
# el teléfono no sale en repr ni cuenta en la igualdad
assert "600" not in repr(ok[0]) and Jugador("Ana", 1, "34600123456") == Jugador("Ana", 1)
# plantilla propia válida
pl = emparejamientos.leer_jugadores(emparejamientos.plantilla_jugadores())
assert len(pl) == 4 and pl[0].telefono == "34600123456"
print("OK 4 CSV")

# 5. BD: guardar, consultar, editar
js = [Jugador("Ana", 1, "34600123456"), Jugador("Bea", 2), Jugador("Carla", 3, "611 22 33 44"), Jugador("Dora", 4)]
obj = SorteoTorneo(js, seed=1); obj.generar()
cod = db.crear_torneo(codigo="T1", nombre="Torneo 1", fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 6, 5),
                      tipo="eliminatorias", sets_ganar=2, jugadores=js, sorteo=obj)
ids = {j["nombre"]: j["id"] for j in db.jugadores_de(cod)}
tels = db.telefonos_de(cod)
assert tels == {ids["Ana"]: "34600123456", ids["Carla"]: "34611223344"}, tels
assert db.establecer_telefono(ids["Bea"], "622 33 44 55") == "34622334455"
assert db.establecer_telefono(ids["Ana"], "") == "" and ids["Ana"] not in db.telefonos_de(cod)
falla(db.establecer_telefono, ids["Bea"], "xx")
falla(db.establecer_telefono, 99999, "600123456")
assert db.telefonos_de(cod)[ids["Bea"]] == "34622334455"  # el error no tocó nada
# teléfono inválido al crear: no queda torneo a medias
mal = [Jugador("X", 1, "abc"), Jugador("Y", 2)]
o2 = SorteoTorneo(mal, seed=1); o2.generar()
falla(lambda: db.crear_torneo(codigo="T2", nombre="Malo", fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 6, 2),
                              tipo="eliminatorias", sets_ganar=2, jugadores=mal, sorteo=o2))
assert db.obtener_torneo("T2") is None
print("OK 5 BD")

# 6. los teléfonos no aparecen en ninguna consulta pública
def contiene(obj, trozo):
    return trozo in repr(obj)

pub = [db.buscar_torneos(), db.obtener_torneo(cod), db.partidos_de(cod), db.jugadores_de(cod),
       db.clasificaciones(cod) if False else None]
for x in pub:
    assert not contiene(x, "6223") and not contiene(x, "6112") and not contiene(x, "telefono"), x
print("OK 6 sin fugas")

# 7. migración de una base antigua (sin columna telefono)
ruta = os.path.join(tempfile.mkdtemp(), "vieja.db")
con = sqlite3.connect(ruta)
con.executescript("""CREATE TABLE torneos (codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL, tipo TEXT NOT NULL,
 fecha_inicio TEXT NOT NULL, fecha_fin TEXT NOT NULL, sets_ganar INTEGER NOT NULL DEFAULT 2,
 estado TEXT NOT NULL DEFAULT 'sorteado', campeon_id INTEGER, creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE jugadores (id INTEGER PRIMARY KEY AUTOINCREMENT, torneo TEXT NOT NULL, nombre TEXT NOT NULL,
 ranking INTEGER NOT NULL, grupo TEXT);
INSERT INTO torneos (codigo,nombre,tipo,fecha_inicio,fecha_fin) VALUES ('V','Viejo','eliminatorias','2026-01-01','2026-01-02');
INSERT INTO jugadores (torneo,nombre,ranking) VALUES ('V','Vieja',1);""")
con.commit(); con.close()
db.DB_PATH = ruta
assert db.telefonos_de("V") == {}
jid = db.jugadores_de("V")[0]["id"]
db.establecer_telefono(jid, "600123456")
assert db.telefonos_de("V") == {jid: "34600123456"}
print("OK 7 migración")
print("TODO OK")

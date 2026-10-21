"""Pruebas del tablón de anuncios (general, de torneo y del ranking continuo)."""
import os
import sqlite3
import tempfile
from datetime import date, timedelta

import anuncios as an
import estilo
import torneo as db
from sorteo_torneo_tenis import Jugador, SorteoTorneo

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "an.db")


def falla(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    raise SystemExit(f"debería fallar: {fn.__name__}{a}{k}")


def torneo(cod, visible=True):
    js = [Jugador("A", 1), Jugador("B", 2)]
    o = SorteoTorneo(js, seed=1); o.generar()
    db.crear_torneo(codigo=cod, nombre=f"Torneo {cod}", fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 6, 2),
                    tipo="eliminatorias", sets_ganar=2, jugadores=js, sorteo=o, visible=visible)


torneo("T1"); torneo("T2", visible=False)
hoy = date(2026, 10, 19)

# 1. alta en los tres ámbitos y listados
g = an.crear_anuncio("general", "  Cierre   por obras ", "El club cierra el lunes.\nGracias.")
t1 = an.crear_anuncio("torneo", "Sorteo hecho", "Ya está el cuadro.", torneo="T1")
r = an.crear_anuncio("ranking", "Ventana 2 abierta", "Hasta el viernes.")
assert [a["ambito"] for a in an.listar_anuncios(hoy=hoy)] == ["ranking", "torneo", "general"]   # más reciente primero
assert [a["id"] for a in an.listar_anuncios(ambito="torneo", torneo="T1", hoy=hoy)] == [t1]
assert [a["id"] for a in an.listar_anuncios(ambito="ranking", hoy=hoy)] == [r]
assert [a["id"] for a in an.listar_anuncios(ambito="general", hoy=hoy)] == [g]
assert an.listar_anuncios(ambito="torneo", torneo="T2", hoy=hoy) == []
x = an.listar_anuncios(ambito="general", hoy=hoy)[0]
assert x["titulo"] == "Cierre por obras" and x["torneo"] is None and x["torneo_nombre"] is None
assert an.listar_anuncios(ambito="torneo", hoy=hoy)[0]["torneo_nombre"] == "Torneo T1"
print("OK 1 alta y listado por ámbito")

# 2. validaciones
falla(an.crear_anuncio, "otro", "T", "x")
falla(an.crear_anuncio, "general", "", "x")
falla(an.crear_anuncio, "general", "   ", "x")
falla(an.crear_anuncio, "general", "T", "   ")
falla(an.crear_anuncio, "general", "T" * 121, "x")
falla(an.crear_anuncio, "general", "T", "x" * 2001)
falla(an.crear_anuncio, "torneo", "T", "x")                                   # sin torneo
falla(an.crear_anuncio, "torneo", "T", "x", torneo="NOEXISTE")
falla(an.crear_anuncio, "general", "T", "x", caduca="2026-12-31")             # debe ser una fecha
assert an.crear_anuncio("general", "T", "x", torneo="T1") and an.listar_anuncios(ambito="general", hoy=hoy)[0]["torneo"] is None
for a in an.listar_anuncios(hoy=hoy):
    if a["titulo"] == "T":
        an.eliminar_anuncio(a["id"])
print("OK 2 validaciones")

# 3. fijados primero
an.fijar_anuncio(g, True)
assert an.listar_anuncios(hoy=hoy)[0]["id"] == g
an.fijar_anuncio(g, False)
assert an.listar_anuncios(hoy=hoy)[0]["id"] == r
falla(an.fijar_anuncio, 9999, True)
print("OK 3 fijar")

# 4. editar y eliminar
an.editar_anuncio(t1, "Cuadro publicado", "Texto nuevo", fijado=True, caduca=hoy + timedelta(days=3))
e = an.listar_anuncios(ambito="torneo", torneo="T1", hoy=hoy)[0]
assert (e["titulo"], e["texto"], e["fijado"], e["caduca"], e["torneo"]) == ("Cuadro publicado", "Texto nuevo", 1, "2026-10-22", "T1")
falla(an.editar_anuncio, t1, "", "x")
falla(an.editar_anuncio, 9999, "T", "x")
an.eliminar_anuncio(r)
falla(an.eliminar_anuncio, r)
assert r not in [a["id"] for a in an.listar_anuncios(hoy=hoy)]
print("OK 4 editar y eliminar")

# 5. caducidad: los invitados no ven los caducados; el administrador sí, marcados
c = an.crear_anuncio("general", "Caducado", "Ya pasó", caduca=hoy - timedelta(days=1))
hoy_mismo = an.crear_anuncio("general", "Caduca hoy", "Aún vale", caduca=hoy)
inv = [a["id"] for a in an.listar_anuncios(hoy=hoy)]
adm = {a["id"]: a for a in an.listar_anuncios(incluir_ocultos=True, hoy=hoy)}
assert c not in inv and hoy_mismo in inv
assert c in adm and adm[c]["caducado"] == 1 and adm[hoy_mismo]["caducado"] == 0
print("OK 5 caducidad")

# 6. torneos ocultos: sus anuncios no los ve un invitado
o = an.crear_anuncio("torneo", "Prueba interna", "No público", torneo="T2")
assert o not in [a["id"] for a in an.listar_anuncios(hoy=hoy)]
assert an.listar_anuncios(ambito="torneo", torneo="T2", hoy=hoy) == []
assert o in [a["id"] for a in an.listar_anuncios(incluir_ocultos=True, hoy=hoy)]
db.establecer_visibilidad("T2", True)
assert o in [a["id"] for a in an.listar_anuncios(hoy=hoy)]
db.establecer_visibilidad("T2", False)
print("OK 6 torneos ocultos")

# 7. HTML seguro
malo = {"ambito": "torneo", "torneo_nombre": "<b>T</b>", "titulo": "<script>alert(1)</script>", "fijado": 1,
        "texto": 'Línea 1\n<img src=x onerror="alert(1)">\nLínea 3', "creado": "2026-10-19 10:00:00", "caduca": None,
        "caducado": 0, "id": 1}
h = estilo.anuncios_html([malo])
assert "<script>" not in h and "<img" not in h and "<b>T</b>" not in h and "\n" not in h
assert "Línea 1<br>" in h and "&lt;script&gt;" in h and "19/10/2026" in h and "📌" in h
assert estilo.anuncios_html([]) == ""
print("OK 7 HTML escapado")

# 8. los anuncios de un torneo desaparecen con él (ON DELETE CASCADE) y la base antigua se migra
with db._conexion() as con:
    con.execute("DELETE FROM torneos WHERE codigo = 'T1'")
assert an.listar_anuncios(ambito="torneo", torneo="T1", incluir_ocultos=True, hoy=hoy) == []
ruta = os.path.join(tempfile.mkdtemp(), "vieja.db")
con = sqlite3.connect(ruta)
con.executescript("CREATE TABLE torneos (codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL, tipo TEXT NOT NULL, "
                  "fecha_inicio TEXT NOT NULL, fecha_fin TEXT NOT NULL);")
con.commit(); con.close()
db.DB_PATH = ruta
assert an.listar_anuncios(hoy=hoy) == [] and an.crear_anuncio("general", "Nuevo", "En base antigua")
print("OK 8 cascada y base antigua")
print("TODO OK ANUNCIOS")

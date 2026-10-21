"""Pruebas de la programación de partidos (día y hora prevista) y de la migración de bases antiguas."""
import os
import random
import sqlite3
import tempfile
from datetime import date, datetime, timezone

import torneo as db
from sorteo_torneo_tenis import FaseDeGruposYEliminatorias, Jugador, SorteoTorneo

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "prog.db")
random.seed(5)


def falla(fn, *a):
    try:
        fn(*a)
    except ValueError as e:
        return str(e)
    raise SystemExit(f"debería haber fallado: {fn.__name__}{a}")


def crear(codigo, tipo, n, sg=2):
    js = [Jugador(f"J{i}", i) for i in range(1, n + 1)]
    obj = SorteoTorneo(js, seed=n) if tipo == "eliminatorias" else FaseDeGruposYEliminatorias(js)
    obj.generar()
    return db.crear_torneo(codigo=codigo, nombre=f"Torneo {codigo}", fecha_inicio=date(2026, 6, 1),
                           fecha_fin=date(2026, 6, 5), tipo=tipo, sets_ganar=sg, jugadores=js, sorteo=obj)


def partido(codigo, ronda, posicion, fase="eliminatoria", grupo=None):
    return next(p for p in db.partidos_de(codigo)
                if p["fase"] == fase and p["ronda"] == ronda and p["posicion"] == posicion and p["grupo"] == grupo)


def jugar_todo(codigo, sg=2):
    while True:
        jugables = [p for p in db.partidos_de(codigo)
                    if p["estado"] == "pendiente" and p["jugador1"] and p["jugador2"]
                    and "BYE" not in (p["origen1"], p["origen2"])]
        if not jugables:
            return
        p = random.choice(jugables)
        db.registrar_resultado(p["id"], sg, random.randrange(sg))


# 1) Fijar, cambiar y quitar --------------------------------------------------------------------------------
crear("PRG-1", "eliminatorias", 8)
assert all(p["fecha_hora"] is None for p in db.partidos_de("PRG-1"))        # al crear no hay nada programado
m = partido("PRG-1", 1, 1)
db.programar_partido(m["id"], datetime(2026, 6, 2, 18, 30, 45, 123))         # se guarda al minuto
assert partido("PRG-1", 1, 1)["fecha_hora"] == "2026-06-02T18:30"
assert sum(1 for p in db.partidos_de("PRG-1") if p["fecha_hora"]) == 1
db.programar_partido(m["id"], datetime(2026, 6, 3, 9, 5))
assert partido("PRG-1", 1, 1)["fecha_hora"] == "2026-06-03T09:05"
db.programar_partido(m["id"], None)
assert partido("PRG-1", 1, 1)["fecha_hora"] is None
db.programar_partido(m["id"], None)                                          # quitar de nuevo no da error
print("OK 1: fijar, cambiar y quitar el día y la hora")

# 2) Validaciones --------------------------------------------------------------------------------------------------
for malo in (date(2026, 6, 2), "2026-06-02T18:30", "2026-06-02", 20260602, datetime(2026, 6, 2, tzinfo=timezone.utc)):
    falla(db.programar_partido, m["id"], malo)
assert "2000 y 2100" in falla(db.programar_partido, m["id"], datetime(1999, 12, 31, 10, 0))
assert "2000 y 2100" in falla(db.programar_partido, m["id"], datetime(2101, 1, 1, 10, 0))
assert "no existe" in falla(db.programar_partido, 999999, datetime(2026, 6, 2, 10, 0))
assert partido("PRG-1", 1, 1)["fecha_hora"] is None                          # los intentos fallidos no cambian nada
crear("PRG-BYE", "eliminatorias", 5)                                           # 8 plazas: 3 byes
byes = [p for p in db.partidos_de("PRG-BYE") if p["estado"] == "bye"]
assert byes
assert "BYE" in falla(db.programar_partido, byes[0]["id"], datetime(2026, 6, 2, 10, 0))
assert byes[0]["fecha_hora"] is None
print("OK 2: validaciones (tipo, zona horaria, rango de años, partido inexistente, BYE)")

# 3) Se puede programar antes de conocer a los jugadores, y no se pierde al avanzar el torneo ------------------------------
final = partido("PRG-1", 3, 1)
assert final["jugador1"] is None and final["jugador2"] is None
db.programar_partido(final["id"], datetime(2026, 6, 5, 20, 0))
semi = partido("PRG-1", 2, 1)
db.programar_partido(semi["id"], datetime(2026, 6, 4, 19, 0))
r1 = partido("PRG-1", 1, 1)
db.programar_partido(r1["id"], datetime(2026, 6, 2, 18, 30))
db.registrar_resultado(r1["id"], 2, 0)                                        # jugar, corregir y anular no tocan el horario
db.registrar_resultado(r1["id"], 0, 2)
assert partido("PRG-1", 1, 1)["fecha_hora"] == "2026-06-02T18:30"
db.anular_resultado(r1["id"])
assert partido("PRG-1", 1, 1)["fecha_hora"] == "2026-06-02T18:30"
jugar_todo("PRG-1")
t = db.obtener_torneo("PRG-1")
assert t["estado"] == "finalizado"
assert partido("PRG-1", 3, 1)["fecha_hora"] == "2026-06-05T20:00" and partido("PRG-1", 2, 1)["fecha_hora"] == "2026-06-04T19:00"
db.programar_partido(r1["id"], datetime(2026, 6, 2, 17, 0))                  # un partido ya jugado se puede corregir
assert partido("PRG-1", 1, 1)["fecha_hora"] == "2026-06-02T17:00"
print("OK 3: se programa sin jugadores conocidos y el horario sobrevive a resultados y anulaciones")

# 4) Torneo con grupos: partidos de grupo y casillas del cuadro --------------------------------------------------------------
crear("PRG-G", "grupos", 8)
gp = next(p for p in db.partidos_de("PRG-G") if p["fase"] == "grupo" and p["grupo"] == "B")
ep = partido("PRG-G", 1, 1)
assert ep["origen1"].startswith("1º Grupo") and ep["jugador1"] is None
db.programar_partido(gp["id"], datetime(2026, 6, 1, 10, 0))
db.programar_partido(ep["id"], datetime(2026, 6, 4, 12, 0))
jugar_todo("PRG-G")
assert db.obtener_torneo("PRG-G")["estado"] == "finalizado"
assert next(p for p in db.partidos_de("PRG-G") if p["id"] == gp["id"])["fecha_hora"] == "2026-06-01T10:00"
assert partido("PRG-G", 1, 1)["fecha_hora"] == "2026-06-04T12:00"
print("OK 4: torneo con grupos")

# 5) Una base creada con la versión anterior (sin la columna) se actualiza sin perder datos ---------------------------------------
crear("PRG-OLD", "grupos", 8)
jugar = [p for p in db.partidos_de("PRG-OLD") if p["fase"] == "grupo"][:3]
for p in jugar:
    db.registrar_resultado(p["id"], 2, 1, "6-4 3-6 7-5")
antes = [{k: v for k, v in p.items() if k != "fecha_hora"} for p in db.partidos_de("PRG-OLD")]
con = sqlite3.connect(db.DB_PATH)
con.execute("ALTER TABLE partidos DROP COLUMN fecha_hora")                    # deja la tabla como en la versión anterior
con.commit()
assert "fecha_hora" not in {r[1] for r in con.execute("PRAGMA table_info(partidos)")}
con.close()
despues = db.partidos_de("PRG-OLD")                                            # al abrirla se migra
assert all(p["fecha_hora"] is None for p in despues)
assert [{k: v for k, v in p.items() if k != "fecha_hora"} for p in despues] == antes
assert db.obtener_torneo("PRG-OLD")["estado"] == "en curso"
assert sorted(t["codigo"] for t in db.buscar_torneos()) == ["PRG-1", "PRG-BYE", "PRG-G", "PRG-OLD"]
nuevo = next(p for p in despues if p["estado"] == "pendiente" and p["fase"] == "grupo")
db.programar_partido(nuevo["id"], datetime(2026, 6, 3, 11, 15))
db.registrar_resultado(nuevo["id"], 2, 0)
assert next(p for p in db.partidos_de("PRG-OLD") if p["id"] == nuevo["id"])["fecha_hora"] == "2026-06-03T11:15"
for _ in range(3):                                                             # abrir varias veces no vuelve a migrar ni falla
    db.partidos_de("PRG-OLD")
print("OK 5: migración de una base antigua con datos (resultados y torneos intactos)")

# 6) Una base nueva ya trae la columna ----------------------------------------------------------------------------------------------
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "nueva.db")
db.buscar_torneos()
con = sqlite3.connect(db.DB_PATH)
assert "fecha_hora" in {r[1] for r in con.execute("PRAGMA table_info(partidos)")}
con.close()
print("TODO OK PROGRAMACION")

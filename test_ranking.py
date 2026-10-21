"""Pruebas del ranking continuo (ventanas 1-3 y ventana Reto)."""
import os
import tempfile

import ranking as rk
import torneo as db

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "rk.db")


def falla(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    raise SystemExit(f"debería fallar: {fn.__name__}{a}{k}")


def orden():
    return [j["nombre"] for j in rk.jugadores()]


def idj(nombre):
    return next(j["id"] for j in rk.jugadores() if j["nombre"] == nombre)


def pj(ventana, nombre):
    return next(p for p in rk.partidos_de_ventana(ventana) if nombre in (p["nombre_alto"], p["nombre_bajo"]))


# 1. emparejamientos puros
assert rk.emparejar_ventana(8, 1) == [(1, 2), (3, 4), (5, 6), (7, 8)]
assert rk.emparejar_ventana(7, 1) == [(1, 2), (3, 4), (5, 6)]
assert rk.emparejar_ventana(13, 3) == [(1, 4), (2, 5), (3, 6), (7, 10), (8, 11), (9, 12)]
assert rk.emparejar_ventana(12, 5) == [(1, 6), (2, 7), (3, 8), (4, 9), (5, 10)]
assert rk.emparejar_ventana(4, 5) == [] and rk.emparejar_ventana(1, 1) == []
for n in range(2, 40):
    for g in (1, 3, 5):
        ps = [x for par in rk.emparejar_ventana(n, g) for x in par]
        assert len(ps) == len(set(ps)), (n, g)          # nadie juega dos veces
        assert all(b - a == g and b <= n for a, b in rk.emparejar_ventana(n, g))
print("OK 1 emparejamientos")

# 2. carga inicial y altas
falla(rk.cargar_jugadores_iniciales, ["A", "a"])
falla(rk.cargar_jugadores_iniciales, ["A", ""])
nombres = [f"J{i}" for i in range(1, 13)]
assert rk.cargar_jugadores_iniciales(nombres) == 12 and orden() == nombres
falla(rk.cargar_jugadores_iniciales, ["X"])           # ya hay jugadores
falla(rk.anadir_jugador, "j3")                          # repetido sin distinguir mayúsculas
rk.anadir_jugador("  Nuevo   Jugador ")
assert orden()[-1] == "Nuevo Jugador" and rk.jugadores()[-1]["posicion"] == 13
print("OK 2 altas")

# 3. ventana 1: abrir, jugar, reglas de posición
assert rk.siguiente_ventana() == (1, "v1")
v1 = rk.abrir_ventana()
falla(rk.abrir_ventana)                                  # ya hay una abierta
ps = rk.partidos_de_ventana(v1)
assert [(p["pos_alto"], p["pos_bajo"]) for p in ps] == [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)]
falla(rk.cerrar_ventana)                                 # pendientes
p12 = pj(v1, "J1")
rk.registrar_resultado(p12["id"], idj("J1"), "6-2 6-3")  # gana el de arriba: nada cambia
assert orden()[:2] == ["J1", "J2"]
falla(rk.registrar_resultado, p12["id"], idj("J2"))      # ya tiene resultado
p34 = pj(v1, "J3")
rk.registrar_resultado(p34["id"], idj("J4"), "7-5 6-4")  # gana el de abajo: sube
assert orden()[2:4] == ["J4", "J3"]
falla(rk.registrar_resultado, pj(v1, "J5")["id"], idj("J9"))   # ganador ajeno
rk.registrar_resultado(pj(v1, "J5")["id"], incomparecencia_de=idj("J5"))  # J5 no se presenta: gana J6
assert orden()[4:6] == ["J6", "J5"] and pj(v1, "J5")["walkover"] == 1
rk.registrar_resultado(pj(v1, "J7")["id"], incomparecencia_de=idj("J8"))  # no se presenta el de abajo: nada
assert orden()[6:8] == ["J7", "J8"]
falla(rk.registrar_resultado, pj(v1, "J9")["id"], None, "", idj("J1"))   # el ausente no juega
rk.registrar_resultado(pj(v1, "J9")["id"], idj("J10"))
rk.registrar_resultado(pj(v1, "J11")["id"], idj("J11"))
assert orden() == ["J1", "J2", "J4", "J3", "J6", "J5", "J7", "J8", "J10", "J9", "J11", "J12", "Nuevo Jugador"]
print("OK 3 ventana 1")

# 4. anular
p = pj(v1, "J11")
rk.anular_resultado(p["id"])                             # sin movimiento: vuelve a pendiente
assert pj(v1, "J11")["estado"] == "pendiente"
rk.registrar_resultado(p["id"], idj("J12"))              # ahora gana J12 y sube
assert orden()[10:12] == ["J12", "J11"]
rk.anular_resultado(p["id"])
assert orden()[10:12] == ["J11", "J12"]
rk.registrar_resultado(p["id"], idj("J11"))
rk.cerrar_ventana()
falla(rk.anular_resultado, p["id"])                      # ventana cerrada
falla(rk.registrar_resultado, pj(v1, "J1")["id"], idj("J1"))
print("OK 4 anular y cerrar")

# 5. ventana 2: usa las posiciones tras la ventana 1
assert rk.siguiente_ventana() == (1, "v2")
v2 = rk.abrir_ventana()
base = orden()
ps = rk.partidos_de_ventana(v2)
assert [(p["pos_alto"], p["pos_bajo"]) for p in ps] == [(1, 4), (2, 5), (3, 6), (7, 10), (8, 11), (9, 12)]
assert ps[0]["nombre_alto"] == base[0] and ps[0]["nombre_bajo"] == base[3]
rk.registrar_resultado(ps[0]["id"], idj(base[3]))        # el 4º gana al 1º: intercambio 1<->4
nuevo = base[:]; nuevo[0], nuevo[3] = base[3], base[0]
assert orden() == nuevo
for p in rk.partidos_de_ventana(v2):
    if p["estado"] == "pendiente":
        rk.registrar_resultado(p["id"], p["jugador_alto"])
rk.cerrar_ventana()
print("OK 5 ventana 2")

# 6. ventana 3
assert rk.siguiente_ventana() == (1, "v3")
v3 = rk.abrir_ventana()
assert [(p["pos_alto"], p["pos_bajo"]) for p in rk.partidos_de_ventana(v3)] == [(1, 6), (2, 7), (3, 8), (4, 9), (5, 10)]
for p in rk.partidos_de_ventana(v3):
    rk.registrar_resultado(p["id"], p["jugador_alto"])
rk.cerrar_ventana()
print("OK 6 ventana 3")

# 7. ventana Reto
assert rk.siguiente_ventana() == (1, "reto")
falla(rk.crear_reto, idj("J1"), idj("J2"))                # sin ventana abierta
vr = rk.abrir_ventana()
assert rk.partidos_de_ventana(vr) == []
o = orden()
a, b = idj(o[9]), idj(o[2])                               # retador 10º, retado 3º: 7 puestos
rid = rk.crear_reto(a, b)
falla(rk.crear_reto, a, idj(o[0]))                        # el retador ya tiene reto
falla(rk.crear_reto, idj(o[11]), b)                       # el retado ya tiene reto
falla(rk.crear_reto, idj(o[11]), idj(o[3]))               # 8 puestos
falla(rk.crear_reto, idj(o[3]), idj(o[11]))               # retar hacia abajo
falla(rk.crear_reto, idj(o[3]), idj(o[3]))
r2 = rk.crear_reto(idj(o[5]), idj(o[4]))                  # 1 puesto
rk.quitar_reto(r2)
assert len(rk.partidos_de_ventana(vr)) == 1
falla(rk.cerrar_ventana)                                  # reto pendiente
rk.registrar_resultado(rid, a, "6-4 6-4")                 # el retador gana: toma la posición del retado
o2 = orden()
assert o2[2] == o[9] and o2[9] == o[2], (o, o2)
falla(rk.quitar_reto, rid)                                # ya jugado
h = rk.historial()
assert h[0]["id"] == rid and h[0]["subio"] and h[0]["tipo"] == "reto"
rk.cerrar_ventana()
assert rk.siguiente_ventana() == (2, "v1")
print("OK 7 ventana reto")

# 8. anular con jugadores movidos
v = rk.abrir_ventana()
o = orden()
p1 = pj(v, o[1])                                          # (1,2) -> gana el 2º
rk.registrar_resultado(p1["id"], p1["jugador_bajo"])
rk.anular_resultado(p1["id"])
assert orden() == o
rk.registrar_resultado(p1["id"], p1["jugador_bajo"])
print("OK 8 anular restaura")

# 9. bajas
falla(rk.dar_de_baja, idj(orden()[0]))                    # ventana abierta
for p in rk.partidos_de_ventana(v):
    if p["estado"] == "pendiente":
        rk.registrar_resultado(p["id"], p["jugador_alto"])
rk.cerrar_ventana()
o = orden()
rk.dar_de_baja(idj(o[3]))
assert orden() == o[:3] + o[4:] and [j["posicion"] for j in rk.jugadores()] == list(range(1, len(o)))
falla(rk.dar_de_baja, 99999)
rk.anadir_jugador(o[3])                                   # reactivación al final, con su historial
assert orden()[-1] == o[3] and len(orden()) == len(o)
print("OK 9 bajas y reactivación")

# 10. teléfonos y programación de partidos
import sqlite3
from datetime import datetime
import whatsapp
o = rk.jugadores()
a_id, b_id = o[0]["id"], o[1]["id"]
assert rk.telefonos() == {}
assert rk.establecer_telefono(a_id, "600 123 456") == "34600123456"
assert rk.establecer_telefono(b_id, "+34 611 22 33 44") == "34611223344"
falla(rk.establecer_telefono, a_id, "abc")
falla(rk.establecer_telefono, 99999, "600123456")
assert rk.telefonos() == {a_id: "34600123456", b_id: "34611223344"}
rk.establecer_telefono(b_id, "")
assert rk.telefonos() == {a_id: "34600123456"}
nid = rk.anadir_jugador("Con Teléfono", "622 33 44 55")
assert rk.telefonos()[nid] == "34622334455"
falla(rk.anadir_jugador, "Otro", "xx")
assert "Otro" not in orden()                               # el error no deja la alta a medias
# los teléfonos no salen en las consultas públicas
for x in (rk.jugadores(), rk.historial(), [p for v in rk.ventanas() for p in rk.partidos_de_ventana(v["id"])]):
    assert "34600123456" not in repr(x) and "telefono" not in repr(x)
# carga inicial con teléfonos en una base nueva
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "rk2.db")
rk.cargar_jugadores_iniciales(["A", "B", "C"], ["600111222", "", "+34 633 44 55 66"])
ids = {j["nombre"]: j["id"] for j in rk.jugadores()}
assert rk.telefonos() == {ids["A"]: "34600111222", ids["C"]: "34633445566"}
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "rk3.db")
falla(rk.cargar_jugadores_iniciales, ["A", "B"], ["600111222"])     # un teléfono por jugador
falla(rk.cargar_jugadores_iniciales, ["A", "B"], ["600111222", "mal"])
assert rk.jugadores() == []
rk.cargar_jugadores_iniciales([f"J{i}" for i in range(1, 7)])
v = rk.abrir_ventana()
p = rk.partidos_de_ventana(v)[0]
assert p["fecha_hora"] is None
rk.programar_partido(p["id"], datetime(2026, 6, 2, 18, 30, 45))
assert rk.partidos_de_ventana(v)[0]["fecha_hora"] == "2026-06-02T18:30"
rk.programar_partido(p["id"], None)
assert rk.partidos_de_ventana(v)[0]["fecha_hora"] is None
falla(rk.programar_partido, p["id"], "mañana")
falla(rk.programar_partido, 9999, datetime(2026, 6, 2, 18, 0))
rk.programar_partido(p["id"], datetime(2026, 6, 3, 10, 0))
m = whatsapp.mensaje_ranking("Ventana 1", rk.partidos_de_ventana(v)[0], "Ana García", "Bea López", "Club Nazaret")
for trozo in ("Hola Ana,", "Ranking continuo (Ventana 1)", "Club Nazaret", "Bea López", "es el miércoles 03/06/2026 a las 10:00"):
    assert trozo in m, (trozo, m)
assert "aún no tiene día y hora" in whatsapp.mensaje_ranking("Ventana Reto", {"fecha_hora": None}, "Ana", "Bea")
rk.registrar_resultado(p["id"], p["jugador_alto"])
falla(rk.programar_partido, p["id"], datetime(2026, 6, 4, 10, 0))   # ya jugado
for q in rk.partidos_de_ventana(v):
    if q["estado"] == "pendiente":
        rk.registrar_resultado(q["id"], q["jugador_alto"])
rk.cerrar_ventana()
falla(rk.programar_partido, p["id"], datetime(2026, 6, 4, 10, 0))   # ventana cerrada
print("OK 10 teléfonos y fechas previstas")

# 11. migración de una base con el ranking de la versión anterior
ruta = os.path.join(tempfile.mkdtemp(), "vieja.db")
con = sqlite3.connect(ruta)
con.executescript("""CREATE TABLE ranking_jugadores (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
 posicion INTEGER, activo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE ranking_ventanas (id INTEGER PRIMARY KEY AUTOINCREMENT, ciclo INTEGER NOT NULL, tipo TEXT NOT NULL,
 estado TEXT NOT NULL DEFAULT 'abierta', creada TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, cerrada TEXT);
CREATE TABLE ranking_partidos (id INTEGER PRIMARY KEY AUTOINCREMENT, ventana INTEGER NOT NULL, jugador_alto INTEGER NOT NULL,
 jugador_bajo INTEGER NOT NULL, pos_alto INTEGER NOT NULL, pos_bajo INTEGER NOT NULL, ganador INTEGER, marcador TEXT,
 walkover INTEGER NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT 'pendiente', jugado TEXT);
INSERT INTO ranking_jugadores (nombre, posicion) VALUES ('Vieja', 1), ('Vieja2', 2);
INSERT INTO ranking_ventanas (ciclo, tipo) VALUES (1, 'v1');
INSERT INTO ranking_partidos (ventana, jugador_alto, jugador_bajo, pos_alto, pos_bajo) VALUES (1, 1, 2, 1, 2);""")
con.commit(); con.close()
db.DB_PATH = ruta
assert rk.telefonos() == {} and rk.partidos_de_ventana(1)[0]["fecha_hora"] is None
rk.programar_partido(1, datetime(2026, 6, 2, 9, 0))
rk.establecer_telefono(1, "600123456")
assert rk.telefonos() == {1: "34600123456"} and rk.partidos_de_ventana(1)[0]["fecha_hora"] == "2026-06-02T09:00"
print("OK 11 migración del ranking")

# 12. buscador de partidos
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "rk4.db")
rk.cargar_jugadores_iniciales(["Ana García", "Beatriz Núñez", "Carlos Pérez", "Dolores Ruiz", "Elena Pérez", "José Luis Ortega"])
vb = rk.abrir_ventana()
todos = rk.partidos_de_ventana(vb)                       # 1-2, 3-4, 5-6
assert len(todos) == 3
def nombres_de(ps): return [(p["nombre_alto"], p["nombre_bajo"]) for p in ps]
assert rk.filtrar_partidos(todos, "") == todos and rk.filtrar_partidos(todos, "   ") == todos
assert nombres_de(rk.filtrar_partidos(todos, "garcia")) == [("Ana García", "Beatriz Núñez")]   # sin acentos
assert nombres_de(rk.filtrar_partidos(todos, "GARCÍA")) == [("Ana García", "Beatriz Núñez")]    # mayúsculas
assert nombres_de(rk.filtrar_partidos(todos, "nunez")) == [("Ana García", "Beatriz Núñez")]     # juega el de abajo
assert len(rk.filtrar_partidos(todos, "perez")) == 2                                              # dos partidos
assert nombres_de(rk.filtrar_partidos(todos, "jose  luis")) == [("Elena Pérez", "José Luis Ortega")]
assert len(rk.filtrar_partidos(todos, "ez")) == 3                                                 # parte del nombre
assert nombres_de(rk.filtrar_partidos(todos, "carlos ruiz")) == []                                # palabras de jugadores distintos
assert rk.filtrar_partidos(todos, "zzz") == [] and rk.filtrar_partidos([], "ana") == []
assert rk.filtrar_partidos(todos, None) == todos
print("OK 12 buscador de partidos")

# 13. evolución de un jugador a lo largo de las ventanas
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "rk5.db")
rk.cargar_jugadores_iniciales([f"J{i}" for i in range(1, 9)])
J = {j["nombre"]: j["id"] for j in rk.jugadores()}
assert rk.evolucion_jugador(J["J4"]) == []                  # sin ventanas todavía
falla(rk.evolucion_jugador, 99999)
w1 = rk.abrir_ventana()                                      # 1-2, 3-4, 5-6, 7-8
assert [(p["etiqueta"], p["posicion"]) for p in rk.evolucion_jugador(J["J4"])] == [("Inicio", 4), ("C1 V1 (en curso)", 4)]
for p in rk.partidos_de_ventana(w1):
    rk.registrar_resultado(p["id"], p["jugador_bajo"])       # ganan todos los de abajo: J2, J4, J6, J8 suben
ev = rk.evolucion_jugador(J["J4"])
assert ev == [{"etiqueta": "Inicio", "posicion": 4, "en_curso": False},
              {"etiqueta": "C1 V1 (en curso)", "posicion": 3, "en_curso": True}], ev
rk.cerrar_ventana()
ev = rk.evolucion_jugador(J["J4"])
assert [(p["etiqueta"], p["posicion"]) for p in ev] == [("Inicio", 4), ("C1 V1", 3)] and not any(p["en_curso"] for p in ev)
w2 = rk.abrir_ventana()                                      # salto 3: usa las posiciones nuevas
orden_antes = orden()
p = rk.partidos_de_ventana(w2)[0]                            # 1º vs 4º
rk.registrar_resultado(p["id"], p["jugador_bajo"])           # el 4º gana: intercambio
cur = next(j["posicion"] for j in rk.jugadores() if j["id"] == p["jugador_bajo"])
assert cur == 1
ev = rk.evolucion_jugador(p["jugador_bajo"])
assert ev[-1] == {"etiqueta": "C1 V2 (en curso)", "posicion": 1, "en_curso": True} and ev[-2]["etiqueta"] == "C1 V1"
for q in rk.partidos_de_ventana(w2):
    if q["estado"] == "pendiente":
        rk.registrar_resultado(q["id"], q["jugador_alto"])
rk.cerrar_ventana()
for _ in range(2):
    rk.abrir_ventana()
    for q in rk.partidos_de_ventana(rk.ventana_abierta()["id"]):
        rk.registrar_resultado(q["id"], q["jugador_alto"])
    rk.cerrar_ventana()
ev = rk.evolucion_jugador(J["J1"])
assert [p["etiqueta"] for p in ev] == ["Inicio", "C1 V1", "C1 V2", "C1 V3", "C1 Reto"], ev
rk.abrir_ventana()
assert rk.evolucion_jugador(J["J1"])[-1]["etiqueta"] == "C2 V1 (en curso)"
for q in rk.partidos_de_ventana(rk.ventana_abierta()["id"]):
    rk.registrar_resultado(q["id"], q["jugador_alto"])
rk.cerrar_ventana()
# un jugador que entra después empieza su gráfica cuando ya está en el ranking
nuevo = rk.anadir_jugador("Recién llegado")
assert rk.evolucion_jugador(nuevo) == []
rk.abrir_ventana()
for q in rk.partidos_de_ventana(rk.ventana_abierta()["id"]):
    rk.registrar_resultado(q["id"], q["jugador_alto"])
rk.cerrar_ventana()
ev = rk.evolucion_jugador(nuevo)
assert [p["etiqueta"] for p in ev] == ["Inicio", "C2 V2"] and ev[0]["posicion"] == 9
# una baja entre ventanas desplaza a los demás: la gráfica lo refleja en la siguiente ventana
antes = {j["nombre"]: j["posicion"] for j in rk.jugadores()}
rk.dar_de_baja(J["J2"])
rk.abrir_ventana()
despues = rk.evolucion_jugador(J["J8"])
assert despues[-1]["en_curso"] and despues[-1]["posicion"] == next(j["posicion"] for j in rk.jugadores() if j["nombre"] == "J8")
# un jugador dado de baja ya no tiene gráfica
falla(rk.evolucion_jugador, J["J2"])
print("OK 13 evolución del puesto por ventana")
print("TODO OK RANKING")

import os, random, tempfile
from datetime import date
import torneo as db
from sorteo_torneo_tenis import Jugador, SorteoTorneo, FaseDeGruposYEliminatorias

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
random.seed(1)

def jugar_todo(codigo, sg):
    """Juega al azar todos los partidos jugables hasta que no quede ninguno."""
    n = 0
    while True:
        jugables = [p for p in db.partidos_de(codigo)
                    if p["estado"] == "pendiente" and p["jugador1"] and p["jugador2"]
                    and "BYE" not in (p["origen1"], p["origen2"])]
        if not jugables:
            return n
        p = random.choice(jugables)
        perd = random.randrange(sg)
        s = (sg, perd) if random.random() < .5 else (perd, sg)
        db.registrar_resultado(p["id"], *s, "6-4 6-3")
        n += 1

def crear(tipo, n, sg=2, cod=None):
    js = [Jugador(f"J{i}", i) for i in range(1, n + 1)]
    obj = SorteoTorneo(js, seed=n) if tipo == "eliminatorias" else FaseDeGruposYEliminatorias(js)
    obj.generar()
    cod = cod or f"{tipo[:3].upper()}-{n}"
    return db.crear_torneo(codigo=cod, nombre=f"Torneo {tipo} {n}", fecha_inicio=date(2026, 5, 1),
                           fecha_fin=date(2026, 5, 10), tipo=tipo, sets_ganar=sg, jugadores=js, sorteo=obj)

# 1) Torneos completos de ambos tipos
for tipo, tams in (("eliminatorias", [2,3,4,5,7,8,9,12,16,17,23,33]),
                   ("grupos", [3,4,6,7,8,9,10,11,12,13,16,17,23,29])):
    for n in tams:
        for sg in (1, 2, 3):
            cod = crear(tipo, n, sg, f"{tipo[:3].upper()}-{n}-{sg}")
            jugados = jugar_todo(cod, sg)
            t = db.obtener_torneo(cod)
            assert t["estado"] == "finalizado" and t["campeon"], (tipo, n, t)
            if tipo == "eliminatorias":
                assert jugados == n - 1, (n, jugados)
            else:
                cl = db.clasificaciones(cod)
                assert all(c["completo"] for c in cl.values())
                g = len(cl)
                grupos_partidos = sum(len(c["tabla"]) * (len(c["tabla"]) - 1) // 2 for c in cl.values())
                tams = [len(c["tabla"]) for c in cl.values()]
                assert all(x in (3, 4) for x in tams) and sum(tams) == n and tams.count(3) <= 3
                cons = sum(x - 2 for x in tams)          # 3º de cada grupo y 4º de los de 4
                esperado_elim = (2 * g - 1) + (cons - 1 if cons >= 2 else 0)
                assert jugados == grupos_partidos + esperado_elim, (n, jugados, grupos_partidos, esperado_elim)
print("OK 1: torneos completos de ambos tipos (1, 2 y 3 sets)")

# 2) Placeholders se resuelven por grupo y byes esperan al clasificado
cod = crear("grupos", 12, 2, "GRP-BYE")   # 3 grupos -> 6 clasificados por cuadro -> 2 byes
ps = db.partidos_de(cod)
elim1 = [p for p in ps if p["fase"] == "eliminatoria" and p["ronda"] == 1 and p["cuadro"] == "principal"]
assert all(p["jugador1"] is None and p["jugador2"] is None for p in elim1)
assert all(p["estado"] == "pendiente" for p in elim1)
# juego solo el grupo A
for p in [p for p in ps if p["fase"] == "grupo" and p["grupo"] == "A"]:
    db.registrar_resultado(p["id"], 2, 0)
ps = db.partidos_de(cod)
elim1 = [p for p in ps if p["fase"] == "eliminatoria" and p["ronda"] == 1 and p["cuadro"] == "principal"]
bye_A = [p for p in elim1 if p["origen1"] == "1º Grupo A"][0]
assert bye_A["estado"] == "bye" and bye_A["nombre_ganador"] == bye_A["nombre1"]
# ... y el ganador del bye ya está en semifinales
semi = [p for p in ps if p["fase"] == "eliminatoria" and p["ronda"] == 2 and p["cuadro"] == "principal"]
assert bye_A["nombre1"] in (semi[0]["nombre1"], semi[0]["nombre2"])
bye_A3 = [p for p in ps if p["cuadro"] == "consolacion" and p["ronda"] == 1 and p["origen1"] == "3º Grupo A"][0]
assert bye_A3["estado"] == "bye" and bye_A3["nombre_ganador"] == bye_A3["nombre1"]
# anular un partido del grupo A lo deshace
pid = [p for p in ps if p["fase"] == "grupo" and p["grupo"] == "A"][0]["id"]
db.anular_resultado(pid)
ps = db.partidos_de(cod)
bye_A = [p for p in ps if p["fase"] == "eliminatoria" and p["origen1"] == "1º Grupo A"][0]
assert bye_A["estado"] == "pendiente" and bye_A["jugador1"] is None
semi = [p for p in ps if p["fase"] == "eliminatoria" and p["ronda"] == 2]
assert all(p["jugador1"] is None and p["jugador2"] is None for p in semi)
print("OK 2: clasificados y byes se resuelven/deshacen por grupo")

# 3) Bloqueos
cod = crear("eliminatorias", 8, 2, "ELI-BLOQ")
ps = [p for p in db.partidos_de(cod) if p["ronda"] == 1]
for p in ps:
    db.registrar_resultado(p["id"], 2, 0)
r2 = [p for p in db.partidos_de(cod) if p["ronda"] == 2][0]
assert r2["jugador1"] and r2["jugador2"]
# cambiar ganador de R1 antes de jugar R2 propaga el cambio
p0 = ps[0]
db.registrar_resultado(p0["id"], 0, 2)
r2n = [p for p in db.partidos_de(cod) if p["ronda"] == 2][0]
assert r2n["nombre1"] == p0["nombre2"], (r2n, p0)
db.registrar_resultado(r2n["id"], 2, 1)
for fn in (lambda: db.registrar_resultado(p0["id"], 2, 0), lambda: db.anular_resultado(p0["id"])):
    try: fn(); raise SystemExit("debería bloquear")
    except ValueError as e: pass
db.anular_resultado(r2n["id"])           # anular R2 desbloquea R1
db.registrar_resultado(p0["id"], 2, 0)
print("OK 3: avance al editar y bloqueos")

cod = crear("grupos", 8, 2, "GRP-BLOQ")
ps = db.partidos_de(cod)
for p in [p for p in ps if p["fase"] == "grupo"]:
    db.registrar_resultado(p["id"], 2, 0)
sf = [p for p in db.partidos_de(cod) if p["fase"] == "eliminatoria" and p["ronda"] == 1 and p["cuadro"] == "principal"][0]
db.registrar_resultado(sf["id"], 2, 0)
g1 = [p for p in db.partidos_de(cod) if p["fase"] == "grupo"][0]
try: db.registrar_resultado(g1["id"], 0, 2); raise SystemExit("debería bloquear")
except ValueError: pass
print("OK 3b: grupos bloqueados tras iniciar eliminatorias")

# 4) Validaciones de resultado
cod = crear("eliminatorias", 4, 2, "ELI-VAL")
p = db.partidos_de(cod)[0]
for s in [(1, 1), (2, 2), (3, 0), (0, 0), (1, 0)]:
    try: db.registrar_resultado(p["id"], *s); raise SystemExit(f"{s} debería fallar")
    except ValueError: pass
r2 = [p for p in db.partidos_de(cod) if p["ronda"] == 2][0]
try: db.registrar_resultado(r2["id"], 2, 0); raise SystemExit("faltan jugadores")
except ValueError: pass
cod = crear("eliminatorias", 5, 2, "ELI-BYE")
byep = [p for p in db.partidos_de(cod) if p["estado"] == "bye"][0]
try: db.registrar_resultado(byep["id"], 2, 0); raise SystemExit("bye no se juega")
except ValueError: pass
print("OK 4: validaciones de resultado")

# 5) Desempate triple circular (A>B, B>C, C>A y todos ganan a D)
js = [Jugador("A", 1), Jugador("B", 2), Jugador("C", 3), Jugador("D", 4)]
obj = FaseDeGruposYEliminatorias(js); obj.generar()
cod = db.crear_torneo(codigo="TRI", nombre="tri", fecha_inicio=date(2026,1,1), fecha_fin=date(2026,1,2),
                      tipo="grupos", sets_ganar=2, jugadores=js, sorteo=obj)
res = {("A","B"): (2,0), ("B","C"): (2,1), ("C","A"): (2,0), ("A","D"): (2,0), ("B","D"): (2,0), ("C","D"): (2,0)}
for p in [p for p in db.partidos_de(cod) if p["fase"] == "grupo"]:
    k = (p["nombre1"], p["nombre2"]); kr = (p["nombre2"], p["nombre1"])
    if k in res: db.registrar_resultado(p["id"], *res[k])
    else:
        a, b = res[kr]; db.registrar_resultado(p["id"], b, a)
tabla = db.clasificaciones(cod)["A"]["tabla"]
assert [f["PG"] for f in tabla] == [2, 2, 2, 0]
assert [f["nombre"] for f in tabla] == ["C", "A", "B", "D"], [f["nombre"] for f in tabla]   # mini-liga: C=+1, A=0, B=-1
print("OK 5: desempate triple ejecutado")

# 6) Código y búsquedas
try: crear("eliminatorias", 4, 2, "ELI-VAL"); raise SystemExit("duplicado")
except ValueError: pass
for kw in [dict(codigo="mal código"), dict(nombre="  "), dict(fecha_fin=date(2026,4,1))]:
    base = dict(codigo="NUEVO", nombre="x", fecha_inicio=date(2026,5,1), fecha_fin=date(2026,5,2),
                tipo="eliminatorias", sets_ganar=2, jugadores=[Jugador("a",1),Jugador("b",2)],
                sorteo=None)
    base.update(kw)
    js = base["jugadores"]; o = SorteoTorneo(js); o.generar(); base["sorteo"] = o
    try: db.crear_torneo(**base); raise SystemExit(f"debería fallar {kw}")
    except ValueError: pass
print("OK 6a: validaciones de alta")

cod_a = crear("eliminatorias", 4, 2, "LIGA-2025")
with db._conexion() as con:
    con.execute("UPDATE torneos SET nombre='Open Jerez 100%', fecha_inicio='2025-03-01', fecha_fin='2025-03-05' WHERE codigo=?", (cod_a,))
assert [t["codigo"] for t in db.buscar_torneos(codigo="liga")] == ["LIGA-2025"]
assert [t["codigo"] for t in db.buscar_torneos(nombre="jerez")] == ["LIGA-2025"]
assert [t["codigo"] for t in db.buscar_torneos(nombre="100%")] == ["LIGA-2025"]
assert [t["codigo"] for t in db.buscar_torneos(nombre="%")] == ["LIGA-2025"]   # '%' se trata como texto, no comodín
assert [t["codigo"] for t in db.buscar_torneos(inicio=(date(2025,1,1), date(2025,12,31)))] == ["LIGA-2025"]
assert db.buscar_torneos(inicio=(date(2026,1,1), None), codigo="LIGA") == []
assert [t["codigo"] for t in db.buscar_torneos(fin=(None, date(2025,3,5)))] == ["LIGA-2025"]
assert db.buscar_torneos(fin=(date(2025,3,6), None), codigo="LIGA") == []
assert db.sugerir_codigo(2026) == "TEN-2026-001"
crear("eliminatorias", 4, 2, "TEN-2026-001")
assert db.sugerir_codigo(2026) == "TEN-2026-002"
print("OK 6b: búsquedas por código, nombre y fechas")
print("TODO OK")

# 7) Otros grupos siguen anotando mientras A y B ya juegan eliminatorias
cod = crear("grupos", 16, 2, "GRP-4G")
ps = db.partidos_de(cod)
for p in [p for p in ps if p["fase"] == "grupo" and p["grupo"] in "AB"]:
    db.registrar_resultado(p["id"], 2, 0)
ps = db.partidos_de(cod)
cruce = [p for p in ps if p["fase"] == "eliminatoria" and p["ronda"] == 1 and p["jugador1"] and p["jugador2"]
         and p["cuadro"] == "principal"]
assert len(cruce) == 1 and {cruce[0]["origen1"], cruce[0]["origen2"]} == {"1º Grupo A", "2º Grupo B"}
cons = [p for p in ps if p["fase"] == "eliminatoria" and p["ronda"] == 1 and p["jugador1"] and p["jugador2"]
        and p["cuadro"] == "consolacion"]
assert len(cons) == 1 and {cons[0]["origen1"], cons[0]["origen2"]} == {"3º Grupo A", "4º Grupo B"}
db.registrar_resultado(cruce[0]["id"], 2, 1)
grupo_c = [p for p in ps if p["fase"] == "grupo" and p["grupo"] == "C"]
db.registrar_resultado(grupo_c[0]["id"], 2, 0)                      # primera anotación en C: permitido
ga = [p for p in ps if p["fase"] == "grupo" and p["grupo"] == "A"][0]
gb = [p for p in ps if p["fase"] == "grupo" and p["grupo"] == "B"][0]
for pid in (ga["id"], gb["id"]):                                     # A y B ya tienen jugadores en eliminatorias
    try: db.anular_resultado(pid); raise SystemExit("debería bloquear")
    except ValueError: pass
db.anular_resultado(grupo_c[0]["id"])                                # C sí se puede editar
print("OK 7: bloqueo por grupo")


# 8) Cuadro principal y cuadro de consolación ------------------------------------------------------------------
def falla(fn, *a):
    try: fn(*a)
    except ValueError as e: return str(e)
    raise SystemExit("debería fallar")

for n in (0, 1, 2, 5):                                       # grupos de 4 o de 3: 1, 2 y 5 no son posibles
    js = [Jugador(f"X{i}", i) for i in range(1, n + 1)]
    try: FaseDeGruposYEliminatorias(js).generar(); raise SystemExit(f"{n} no debería valer")
    except ValueError: pass
from sorteo_torneo_tenis import calcular_tamanos_grupos
assert calcular_tamanos_grupos(10) == [4, 3, 3] and calcular_tamanos_grupos(11) == [4, 4, 3]
assert calcular_tamanos_grupos(9) == [3, 3, 3] and calcular_tamanos_grupos(3) == [3] and calcular_tamanos_grupos(6) == [3, 3]
js = [Jugador(f"X{i}", i) for i in range(1, 6)]
ok = FaseDeGruposYEliminatorias([Jugador(f"Y{i}", i) for i in range(1, 9)]); ok.generar()
assert "5 jugadores" in falla(lambda: db.crear_torneo(codigo="M5", nombre="m", fecha_inicio=date(2026,1,1),
        fecha_fin=date(2026,1,2), tipo="grupos", sets_ganar=2, jugadores=js, sorteo=ok))

cod = crear("grupos", 8, 2, "CONS")                          # 2 grupos: 4 clasificados por cuadro
ps = db.partidos_de(cod)
for cuadro in ("principal", "consolacion"):
    r1 = [p for p in ps if p["cuadro"] == cuadro and p["ronda"] == 1]
    assert len(r1) == 2 and len([p for p in ps if p["cuadro"] == cuadro]) == 3
    assert all(p["jugador1"] is None and p["jugador2"] is None for p in r1)
assert {p["origen1"][0] + p["origen2"][0] for p in ps if p["cuadro"] == "principal" and p["ronda"] == 1} == {"12"}
assert {p["origen1"][0] + p["origen2"][0] for p in ps if p["cuadro"] == "consolacion" and p["ronda"] == 1} == {"34"}
assert all(p["cuadro"] is None for p in ps if p["fase"] == "grupo")
# todavía no se pueden jugar (no hay jugadores hasta acabar el grupo)
assert "jugadores" in falla(db.registrar_resultado, next(p for p in ps if p["cuadro"] == "consolacion")["id"], 2, 0)

# se juegan los grupos con resultados que fijan el orden: Jn gana a Jm si n < m
for p in [p for p in ps if p["fase"] == "grupo"]:
    ganador1 = int(p["nombre1"][1:]) < int(p["nombre2"][1:])
    db.registrar_resultado(p["id"], *((2, 0) if ganador1 else (0, 2)))
ps = db.partidos_de(cod)
tablas = db.clasificaciones(cod)
por_pos = {(l, f["pos"]): f["nombre"] for l, c in tablas.items() for f in c["tabla"]}
for cuadro, posiciones in (("principal", (1, 2)), ("consolacion", (3, 4))):
    en_cuadro = {p[f"nombre{k}"] for p in ps if p["cuadro"] == cuadro and p["ronda"] == 1 for k in (1, 2)}
    assert en_cuadro == {por_pos[(l, pos)] for l in "AB" for pos in posiciones}, (cuadro, en_cuadro)
    for p in ps:                                              # nadie repite rival de grupo en primera ronda
        if p["cuadro"] == cuadro and p["ronda"] == 1:
            g = {x["nombre"]: l for l, c in tablas.items() for x in c["tabla"]}
            assert g[p["nombre1"]] != g[p["nombre2"]]

# jugar la consolación entera no termina el torneo ni da campeón
for p in sorted([p for p in ps if p["cuadro"] == "consolacion"], key=lambda p: (p["ronda"], p["posicion"])):
    p = next(x for x in db.partidos_de(cod) if x["id"] == p["id"])
    db.registrar_resultado(p["id"], 2, 0)
t = db.obtener_torneo(cod)
assert t["estado"] == "en curso" and t["campeon"] is None, t
# jugar el principal: el campeón sale del principal y entonces finaliza
final_cons = next(p for p in db.partidos_de(cod) if p["cuadro"] == "consolacion" and p["ronda"] == 2)
for p in sorted([p for p in db.partidos_de(cod) if p["cuadro"] == "principal"], key=lambda p: (p["ronda"], p["posicion"])):
    db.registrar_resultado(p["id"], 2, 1)
t = db.obtener_torneo(cod)
fp = next(p for p in db.partidos_de(cod) if p["cuadro"] == "principal" and p["ronda"] == 2)
assert t["estado"] == "finalizado" and t["campeon"] == fp["nombre_ganador"], t
assert t["campeon"] != final_cons["nombre_ganador"]
# bloqueo dentro de cada cuadro: no se toca una semifinal de consolación con la final jugada
semi_c = next(p for p in db.partidos_de(cod) if p["cuadro"] == "consolacion" and p["ronda"] == 1)
assert "siguiente ronda" in falla(db.anular_resultado, semi_c["id"])
# el mismo resultado de la final principal no bloquea la consolación (cuadros independientes)
db.anular_resultado(final_cons["id"])
assert db.obtener_torneo(cod)["estado"] == "en curso"
assert db.obtener_torneo(cod)["campeon"]                      # el campeón no depende de la consolación
db.anular_resultado(semi_c["id"])                             # ahora sí se puede
db.registrar_resultado(semi_c["id"], 2, 0)
print("OK 8: cuadro principal y consolación (clasificados, cruces, campeón, estado, bloqueos)")

# 9) Una base antigua (sin columna cuadro) se migra: sus eliminatorias son el cuadro principal ------------------
import sqlite3
cod = crear("grupos", 8, 2, "VIEJO")
with db._conexion() as con:
    con.execute("DELETE FROM partidos WHERE torneo = 'VIEJO' AND cuadro = 'consolacion'")
    con.commit()
con = sqlite3.connect(db.DB_PATH)
con.execute("ALTER TABLE partidos DROP COLUMN cuadro")
con.commit(); con.close()
viejo = db.partidos_de("VIEJO")
assert all(p["cuadro"] == "principal" for p in viejo if p["fase"] == "eliminatoria") and viejo
for p in [p for p in viejo if p["fase"] == "grupo"]:
    db.registrar_resultado(p["id"], 2, 0)
jugar_todo("VIEJO", 2)
assert db.obtener_torneo("VIEJO")["estado"] == "finalizado"      # sin consolación termina con el principal
print("OK 9: migración de una base sin cuadro de consolación")


# 10) Grupos de 3: solo el 3º pasa a consolación --------------------------------------------------------------
cod = crear("grupos", 10, 2, "G433")                         # grupos de 4, 3 y 3
ps = db.partidos_de(cod)
tam = {l: len({x for p in ps if p["grupo"] == l for x in (p["jugador1"], p["jugador2"])}) for l in "ABC"}
assert tam == {"A": 4, "B": 3, "C": 3}
cons = [p for p in ps if p["cuadro"] == "consolacion"]
etiquetas = {o for p in cons if p["ronda"] == 1 for o in (p["origen1"], p["origen2"]) if o and o != "BYE"}
assert etiquetas == {"3º Grupo A", "3º Grupo B", "3º Grupo C", "4º Grupo A"}, etiquetas
assert len(cons) == 3                                         # 4 jugadores: semifinales y final
for p in [p for p in ps if p["fase"] == "grupo"]:
    db.registrar_resultado(p["id"], *((2, 0) if int(p["nombre1"][1:]) < int(p["nombre2"][1:]) else (0, 2)))
tablas = db.clasificaciones(cod)
terceros = {tablas[l]["tabla"][2]["nombre"] for l in "ABC"} | {tablas["A"]["tabla"][3]["nombre"]}
ps = db.partidos_de(cod)
jug_cons = {p[f"nombre{k}"] for p in ps if p["cuadro"] == "consolacion" and p["ronda"] == 1 for k in (1, 2)} - {None}
assert jug_cons == terceros, (jug_cons, terceros)
prim = {p[f"nombre{k}"] for p in ps if p["cuadro"] == "principal" and p["ronda"] == 1 for k in (1, 2)} - {None}
assert prim == {tablas[l]["tabla"][i]["nombre"] for l in "ABC" for i in (0, 1)}
jugar_todo(cod, 2)
assert db.obtener_torneo(cod)["estado"] == "finalizado"

# un único grupo de 3: solo cuadro principal (final 1º-2º), sin consolación
cod = crear("grupos", 3, 2, "SOLO3")
ps = db.partidos_de(cod)
assert {p["cuadro"] for p in ps if p["fase"] == "eliminatoria"} == {"principal"} and len([p for p in ps if p["fase"] == "eliminatoria"]) == 1
jugar_todo(cod, 2)
assert db.obtener_torneo(cod)["estado"] == "finalizado"
print("OK 10: grupos de 3 (solo el 3º a consolación) y grupo único de 3")


# 11) Puntos (2 ganador, 1 perdedor), partidos no jugados (0 y 0) y desempate por puntos ------------------------
cod = crear("grupos", 4, 2, "PUNTOS")
ps = {frozenset((p["nombre1"], p["nombre2"])): p for p in db.partidos_de(cod) if p["fase"] == "grupo"}
def jugar(a, b, sa, sb):
    p = ps[frozenset((a, b))]
    db.registrar_resultado(p["id"], *((sa, sb) if p["nombre1"] == a else (sb, sa)))
jugar("J1", "J2", 2, 0); jugar("J1", "J3", 2, 0)
assert "Pts" in db.clasificaciones(cod)["A"]["tabla"][0]
f = {x["nombre"]: x for x in db.clasificaciones(cod)["A"]["tabla"]}
assert (f["J1"]["Pts"], f["J2"]["Pts"], f["J3"]["Pts"], f["J4"]["Pts"]) == (4, 1, 1, 0)
nj = ps[frozenset(("J1", "J4"))]
db.marcar_no_jugado(nj["id"])
f = {x["nombre"]: x for x in db.clasificaciones(cod)["A"]["tabla"]}
assert f["J1"]["Pts"] == 4 and f["J4"]["Pts"] == 0 and f["J1"]["PJ"] == 2 and f["J1"]["NJ"] == 1 and f["J4"]["NJ"] == 1
p = next(x for x in db.partidos_de(cod) if x["id"] == nj["id"])
assert p["sin_jugar"] == 1 and p["ganador"] is None and p["estado"] == "jugado"
jugar("J3", "J2", 2, 0); jugar("J4", "J2", 2, 0); jugar("J4", "J3", 2, 1)
cl = db.clasificaciones(cod)["A"]
assert cl["completo"]                                          # un partido no jugado no bloquea el grupo
f = {x["nombre"]: x for x in cl["tabla"]}
assert (f["J1"]["Pts"], f["J2"]["Pts"], f["J3"]["Pts"], f["J4"]["Pts"]) == (4, 3, 4, 4)
assert [x["nombre"] for x in cl["tabla"]] == ["J1", "J4", "J3", "J2"], [x["nombre"] for x in cl["tabla"]]
ps2 = db.partidos_de(cod)
prin = [p for p in ps2 if p["cuadro"] == "principal"][0]
assert {prin["nombre1"], prin["nombre2"]} == {"J1", "J4"}      # pasan los dos primeros por puntos
assert db.obtener_torneo(cod)["estado"] == "en curso"
# un partido no jugado se puede cambiar por un resultado, o deshacer
db.registrar_resultado(nj["id"], 2, 0)
assert next(x for x in db.partidos_de(cod) if x["id"] == nj["id"])["sin_jugar"] == 0
db.marcar_no_jugado(nj["id"])
db.anular_resultado(nj["id"])
q = next(x for x in db.partidos_de(cod) if x["id"] == nj["id"])
assert q["estado"] == "pendiente" and q["sin_jugar"] == 0
assert not db.clasificaciones(cod)["A"]["completo"]
db.marcar_no_jugado(nj["id"])
# no se puede marcar en eliminatorias, ni cuando el grupo ya está bloqueado por jugar eliminatorias
assert "fase de grupos" in falla(db.marcar_no_jugado, prin["id"])
assert "no existe" in falla(db.marcar_no_jugado, 999999)
db.registrar_resultado(prin["id"], 2, 0)
assert "eliminatorias" in falla(db.marcar_no_jugado, nj["id"])
print("OK 11: puntos 2/1, partidos no jugados (0 puntos), desempate por puntos")


# 12) Sorteo de grupos por bombos --------------------------------------------------------------------------------
from sorteo_torneo_tenis import formar_bombos, calcular_tamanos_grupos
for n in (4, 8, 12, 16, 20, 6, 7, 9, 10, 11, 13, 17, 29):
    for semilla in range(5):
        js = [Jugador(f"J{i}", i) for i in range(1, n + 1)]
        random.shuffle(js)
        o = FaseDeGruposYEliminatorias(js, por_bombos=True, seed=semilla); o.generar()
        tams = calcular_tamanos_grupos(n)
        assert [len(g) for g in o.grupos] == tams
        assert sorted(j.nombre for g in o.grupos for j in g) == sorted(j.nombre for j in js)
        # bombos ordenados por ranking: ningún jugador de un bombo es peor que uno de un bombo posterior
        for b1, b2 in zip(o.bombos, o.bombos[1:]):
            assert max(j.ranking for j in b1) < min(j.ranking for j in b2)
        assert [len(b) for b in o.bombos][:3] == [len(tams)] * min(3, len(o.bombos))
        # cada grupo, como mucho un jugador de cada bombo; los grupos de 4 tienen uno de los cuatro bombos
        for g in o.grupos:
            ids = {j.nombre for j in g}
            en = [len(ids & {j.nombre for j in b}) for b in o.bombos]
            assert max(en) == 1 and sum(en) == len(g), (n, en)
            if len(g) == 4:
                assert en == [1, 1, 1, 1]
# misma semilla, mismo sorteo; sin bombos, la serpentina de siempre (el 1 y el 2 nunca juntos)
js = [Jugador(f"J{i}", i) for i in range(1, 17)]
a = FaseDeGruposYEliminatorias(js, por_bombos=True, seed=7); a.generar()
b = FaseDeGruposYEliminatorias(js, por_bombos=True, seed=7); b.generar()
assert [[j.nombre for j in g] for g in a.grupos] == [[j.nombre for j in g] for g in b.grupos]
assert a.bombos and not FaseDeGruposYEliminatorias(js).bombos
# y se puede crear el torneo con ese sorteo
cod = db.crear_torneo(codigo="BOMBOS", nombre="b", fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 2),
                      tipo="grupos", sets_ganar=2, jugadores=js, sorteo=a)
jugar_todo(cod, 2)
assert db.obtener_torneo(cod)["estado"] == "finalizado"
print("OK 12: sorteo de grupos por bombos")


# 13) Torneos no visibles para los invitados ---------------------------------------------------------------------
import sqlite3
cod = crear("eliminatorias", 4, 2, "PRUEBA-1")
assert db.obtener_torneo(cod)["visible"] == 1                              # por defecto, visible
js = [Jugador(f"V{i}", i) for i in range(1, 5)]
o = SorteoTorneo(js, seed=1); o.generar()
db.crear_torneo(codigo="OCULTO-1", nombre="Solo pruebas", fecha_inicio=date(2026, 5, 1), fecha_fin=date(2026, 5, 2),
                tipo="eliminatorias", sets_ganar=2, jugadores=js, sorteo=o, visible=False)
assert "OCULTO-1" not in [x["codigo"] for x in db.buscar_torneos()]                    # invitado: no aparece
assert "OCULTO-1" not in [x["codigo"] for x in db.buscar_torneos(codigo="OCULTO")]
assert db.buscar_torneos(nombre="pruebas") == []
assert db.obtener_torneo("OCULTO-1") is None                                           # ni por código
assert [x["codigo"] for x in db.buscar_torneos(codigo="OCULTO", incluir_ocultos=True)] == ["OCULTO-1"]
assert db.obtener_torneo("OCULTO-1", incluir_ocultos=True)["visible"] == 0
# el administrador puede seguir usándolo con normalidad
p = next(x for x in db.partidos_de("OCULTO-1") if x["ronda"] == 1)
db.registrar_resultado(p["id"], 2, 0)
db.establecer_visibilidad("OCULTO-1", True)
assert "OCULTO-1" in [x["codigo"] for x in db.buscar_torneos()] and db.obtener_torneo("OCULTO-1")
db.establecer_visibilidad("OCULTO-1", False)
assert db.obtener_torneo("OCULTO-1") is None
assert "no existe" in falla(db.establecer_visibilidad, "NOPE", False)
# una base antigua sin la columna se migra y todo queda visible
con = sqlite3.connect(db.DB_PATH); con.execute("ALTER TABLE torneos DROP COLUMN visible"); con.commit(); con.close()
assert db.obtener_torneo("OCULTO-1")["visible"] == 1
print("OK 13: torneos no visibles para invitados")


# 14) Juegos: se anotan con el resultado y desempatan después de los sets ------------------------------------------
cod = crear("grupos", 4, 2, "JUEGOS")
ps = {frozenset((p["nombre1"], p["nombre2"])): p for p in db.partidos_de(cod) if p["fase"] == "grupo"}
def jugar_j(a, b, ja, jb, sa=2, sb=0):
    p = ps[frozenset((a, b))]
    if p["nombre1"] == a: db.registrar_resultado(p["id"], sa, sb, "", ja, jb)
    else: db.registrar_resultado(p["id"], sb, sa, "", jb, ja)
p0 = next(iter(ps.values()))
assert "dos jugadores" in falla(db.registrar_resultado, p0["id"], 2, 0, "", 12, None)
assert "0 y 99" in falla(db.registrar_resultado, p0["id"], 2, 0, "", -1, 5)
assert "0 y 99" in falla(db.registrar_resultado, p0["id"], 2, 0, "", 100, 5)
assert db.partidos_de(cod)[0]["estado"] == "pendiente"
# J1>J2 12-6, J2>J3 12-9, J3>J1 12-10 (todos 2-0 en sets): empatan a puntos y a sets; decide la diferencia de juegos
jugar_j("J1", "J2", 12, 6); jugar_j("J2", "J3", 12, 9); jugar_j("J3", "J1", 12, 10)
for x in ("J1", "J2", "J3"): jugar_j(x, "J4", 12, 0)
cl = db.clasificaciones(cod)["A"]["tabla"]
f = {x["nombre"]: x for x in cl}
assert (f["J1"]["JF"], f["J1"]["JC"], f["J1"]["DJ"]) == (34, 18, 16) and f["J4"]["DJ"] == -36
assert [x["nombre"] for x in cl] == ["J1", "J3", "J2", "J4"], [x["nombre"] for x in cl]   # mini-liga: +4, -1, -3
# los juegos se ven en el partido, se pueden corregir y anular
q = next(x for x in db.partidos_de(cod) if x["id"] == ps[frozenset(("J1", "J2"))]["id"])
assert {q["juegos1"], q["juegos2"]} == {12, 6}
db.registrar_resultado(q["id"], 2, 0, "", *( (6, 12) if q["nombre1"] == "J2" else (12, 6) ))
db.anular_resultado(q["id"])
q = next(x for x in db.partidos_de(cod) if x["id"] == q["id"])
assert q["juegos1"] is None and q["juegos2"] is None
# la misma clasificación sin juegos (como antes) sigue funcionando: cuentan 0
cod2 = crear("grupos", 4, 2, "SINJ")
for p in [p for p in db.partidos_de(cod2) if p["fase"] == "grupo"]:
    db.registrar_resultado(p["id"], 2, 0)
assert all(x["JF"] == 0 and x["DJ"] == 0 for x in db.clasificaciones(cod2)["A"]["tabla"])
# base antigua sin columnas de juegos
con = sqlite3.connect(db.DB_PATH); con.execute("ALTER TABLE partidos DROP COLUMN juegos1"); con.execute("ALTER TABLE partidos DROP COLUMN juegos2"); con.commit(); con.close()
assert all(p["juegos1"] is None for p in db.partidos_de(cod2))
print("OK 14: juegos anotados y desempate por diferencia de juegos")


# 15) El enfrentamiento directo NO influye en el desempate ----------------------------------------------------------
cod = crear("grupos", 4, 2, "H2H")
ps = {frozenset((p["nombre1"], p["nombre2"])): p for p in db.partidos_de(cod) if p["fase"] == "grupo"}
def res(a, b, sa, sb):
    p = ps[frozenset((a, b))]
    db.registrar_resultado(p["id"], *((sa, sb) if p["nombre1"] == a else (sb, sa)))
res("J1", "J2", 2, 1); res("J1", "J4", 2, 1); res("J3", "J1", 2, 0)
res("J2", "J3", 2, 0); res("J2", "J4", 2, 0); res("J4", "J3", 2, 0)
cl = db.clasificaciones(cod)["A"]["tabla"]
f = {x["nombre"]: x for x in cl}
assert f["J1"]["Pts"] == f["J2"]["Pts"] == 5 and f["J1"]["DS"] == 0 and f["J2"]["DS"] == 3
# J1 ganó a J2 en el cara a cara, pero J2 tiene mejor diferencia de sets: J2 va primero
assert [x["nombre"] for x in cl] == ["J2", "J1", "J4", "J3"], [x["nombre"] for x in cl]
print("OK 15: el cara a cara no cuenta en el desempate")

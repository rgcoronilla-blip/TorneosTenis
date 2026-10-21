"""Pruebas de emparejamientos.py: formatos de CSV, errores, y torneos completos creados desde CSV."""
import os
import random
import tempfile
from datetime import date

import emparejamientos as em
import torneo as db
from emparejamientos import ErrorCSV
from sorteo_torneo_tenis import SIN_RANKING, Jugador, etiqueta_jugador

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "emp.db")
random.seed(3)


def errores_de(fn, datos):
    try:
        fn(datos)
    except ErrorCSV as e:
        return e.errores
    raise SystemExit(f"debería haber fallado: {datos!r}")


def hay(errores, *trozos):
    return any(all(t in e for t in trozos) for e in errores)


def nombres(cuadro):
    return [("BYE" if x == "BYE" else x.nombre) for x in cuadro]


# 1) ELIMINATORIAS: formato válido y variantes de fichero ---------------------------------
base = em.leer_eliminatorias(em.plantilla("eliminatorias"))        # UTF-8 con BOM, separador «;»
assert nombres(base.cuadro) == ["Ana García", "BYE", "Elena Torres", "Sofía Marín",
                                "Laura Pérez", "BYE", "Marta Ruiz", "Paula Ortiz"]
assert base.draw_size == 8 and base.byes == 2 and len(base.jugadores) == 6 and base.manual
assert [j.ranking for j in base.jugadores] == [1, 4, 6, 2, 3, 7]
assert base.nombre_rondas() == ["Cuartos de final", "Semifinales", "Final"]

csv_comas = "jugador1,jugador2\nAna García,Elena Torres\nMarta Ruiz,Paula Ortiz\n"
for datos in (csv_comas, csv_comas.encode("utf-8"), csv_comas.encode("cp1252"), csv_comas.encode("utf-8-sig"),
              csv_comas.replace(",", ";"), csv_comas.replace(",", "\t"), csv_comas.replace("\n", "\r\n")):
    o = em.leer_eliminatorias(datos)
    assert nombres(o.cuadro) == ["Ana García", "Elena Torres", "Marta Ruiz", "Paula Ortiz"], datos
    assert all(j.ranking == SIN_RANKING for j in o.jugadores)            # sin columnas de ranking

o = em.leer_eliminatorias("  JUGADOR_1 ; Jugador 2 ;Ranking 1\n\nAna   García ; bye ;3\n;;\nbye;Elena Torres;\n")
assert nombres(o.cuadro) == ["Ana García", "BYE", "BYE", "Elena Torres"]
assert [j.ranking for j in o.jugadores] == [3, SIN_RANKING]               # ranking2 ausente, ranking1 vacío
assert str(o.jugadores[1]) == "Elena Torres" and str(o.jugadores[0]) == "Ana García (#3)"
assert etiqueta_jugador("X", SIN_RANKING) == "X" and etiqueta_jugador("X", 5) == "X (#5)"
print("OK 1: eliminatorias — formato, separadores, codificaciones y cabeceras flexibles")

# 2) ELIMINATORIAS: errores ------------------------------------------------------------------
E = em.leer_eliminatorias
assert hay(errores_de(E, ""), "vacío")
assert hay(errores_de(E, "jugador1;jugador2\n"), "ningún partido")
assert hay(errores_de(E, "jugador1;ranking\nA;1\n"), "Faltan las columnas", "jugador2")
assert hay(errores_de(E, "a;b\nx;y\n"), "Faltan las columnas", "jugador1, jugador2")
tres = "jugador1;jugador2\nA;B\nC;D\nE;F\n"
assert hay(errores_de(E, tres), "tiene 3", "Añade 1 fila", "hasta llegar a 4")
seis = "jugador1;jugador2\n" + "".join(f"P{i};Q{i}\n" for i in range(6))
assert hay(errores_de(E, seis), "tiene 6", "Añade 2 fila", "8")
assert hay(errores_de(E, "jugador1;jugador2\nBYE;bye\nA;B\n"), "Línea 2", "BYE contra BYE")
assert hay(errores_de(E, "jugador1;jugador2\nA;\nB;C\n"), "Línea 2", "falta «jugador2»", "BYE")
assert hay(errores_de(E, "jugador1;jugador2\nA;B\nC;a\n"), "Línea 3", "«a» ya aparece en la línea 2")
assert hay(errores_de(E, "jugador1;jugador2\nA;A\n"), "Línea 2", "ya aparece")
assert hay(errores_de(E, "jugador1;jugador2\nA;BYE\n"), "al menos 2 jugadores")
for malo in ("abc", "0", "-3", "2.5", "1e3", "٣"):
    assert hay(errores_de(E, f"jugador1;jugador2;ranking1\nA;B;{malo}\n"), "Línea 2", "ranking1"), malo
assert hay(errores_de(E, "jugador1;jugador2\n" + "x" * 101 + ";B\n"), "100 caracteres")
# todos los errores a la vez, con su número de línea
varios = errores_de(E, "jugador1;jugador2;ranking1\nBYE;BYE;\nA;;x\nB;C;1\n")
assert len(varios) >= 4 and hay(varios, "Línea 2") and hay(varios, "Línea 3", "falta") and hay(varios, "Línea 3", "ranking1")
assert hay(varios, "tiene 3")
# ficheros que no son un CSV
assert hay(errores_de(E, b"PK\x03\x04\x00\x00\x00\x08\x00"), "no parece un CSV")
assert hay(errores_de(E, b"x" * (em.MAX_BYTES + 1)), "demasiado grande")
filas = "jugador1;jugador2\n" + "".join(f"A{i};B{i}\n" for i in range(em.MAX_FILAS + 1))
assert hay(errores_de(E, filas), "demasiadas filas")
txt = em.resumen_errores(ErrorCSV([f"error {i}" for i in range(40)]))
assert txt.count("\n- ") == em.MAX_ERRORES_MOSTRADOS and "25 error(es) más" in txt
print("OK 2: eliminatorias — errores claros, con línea, todos a la vez")

# 3) GRUPOS: formato válido -----------------------------------------------------------------------
g = em.leer_grupos(em.plantilla("grupos"))
assert [[j.nombre for j in grp] for grp in g.grupos] == [
    ["Ana García", "Elena Torres", "Cristina Vidal", "Lucía Navarro"],
    ["Laura Pérez", "Marta Ruiz", "Sofía Marín", "Paula Ortiz"]]
assert g.draw_size == 4 and g.nombre_rondas() == ["Semifinales", "Final"] and g.manual
from sorteo_torneo_tenis import generar_cuadro_clasificados
assert g.cuadro == generar_cuadro_clasificados(2, 1, 2)[0]
assert g.cuadro_consolacion == generar_cuadro_clasificados(2, 3, 4)[0]
assert g.generar()[0] is g.grupos

mezcla = ("Grupo ; Nombre\n grupo b ;Luis\nA;Pedro\nA;Ana\nB;Eva\nb;Rosa\na;Juan\n"
          "Grupo A;Mar\nB;Sol\n")            # grupo en minúsculas/«Grupo X», columna «nombre», desordenado
o = em.leer_grupos(mezcla)
assert [[j.nombre for j in grp] for grp in o.grupos] == [["Pedro", "Ana", "Juan", "Mar"], ["Luis", "Eva", "Rosa", "Sol"]]
assert all(j.ranking == SIN_RANKING for j in o.jugadores)
tres_grupos = "grupo;jugador\n" + "".join(f"{l};{l}{i}\n" for l in "ABC" for i in range(4))
o3 = em.leer_grupos(tres_grupos)
assert len(o3.grupos) == 3 and o3.draw_size == 8 and sum(1 for x in o3.cuadro if x == "BYE") == 2
assert sum(1 for x in o3.cuadro_consolacion if x == "BYE") == 2 and "3º Grupo A" in o3.cuadro_consolacion
print("OK 3: grupos — formato, etiquetas de grupo flexibles, cuadro de eliminatorias derivado")

# 4) GRUPOS: errores ----------------------------------------------------------------------------------
Gp = em.leer_grupos
assert hay(errores_de(Gp, "grupo;jugador\n"), "ningún jugador")
assert hay(errores_de(Gp, "grupo;nombre\nA;x\n"), "El grupo A tiene 1 jugador")
assert hay(errores_de(Gp, "jugador;ranking\nx;1\n"), "Faltan las columnas", "grupo")
dos = "grupo;jugador\n" + "".join(f"A;a{i}\n" for i in range(2))
assert hay(errores_de(Gp, dos), "grupo A tiene 2", "3 o 4")
tres = "grupo;jugador\n" + "".join(f"A;a{i}\n" for i in range(3))
assert Gp(tres).draw_size == 2 and not Gp(tres).cuadro_consolacion    # un grupo de 3 vale; sin consolación
cinco = "grupo;jugador\n" + "".join(f"A;a{i}\n" for i in range(5))
assert hay(errores_de(Gp, cinco), "grupo A tiene 5", "3 o 4")
saltado = "grupo;jugador\n" + "".join(f"{l};{l}{i}\n" for l in "AC" for i in range(4))
assert hay(errores_de(Gp, saltado), "sin saltarse ninguna letra", "A, C")
sin_a = "grupo;jugador\n" + "".join(f"B;b{i}\n" for i in range(4))
assert hay(errores_de(Gp, sin_a), "sin saltarse ninguna letra")
assert hay(errores_de(Gp, "grupo;jugador\nAA;x\nA;y\n"), "Línea 2", "«AA»", "no es un grupo válido")
assert hay(errores_de(Gp, "grupo;jugador\n1;x\n"), "«1»", "no es un grupo válido")
assert hay(errores_de(Gp, "grupo;jugador\nA;\n"), "Línea 2", "falta el nombre")
dup = "grupo;jugador\nA;Ana\nA;b\nA;c\nA;f\nB;ANA\nB;d\nB;e\nB;g\n"
assert hay(errores_de(Gp, dup), "Línea 6", "«ANA» ya aparece en la línea 2")
assert hay(errores_de(Gp, "grupo;jugador;ranking\nA;x;0\n"), "Línea 2", "ranking")
print("OK 4: grupos — errores claros")

# 5) Plantillas y ficheros de ejemplo se leen bien ---------------------------------------------------------
for tipo in ("eliminatorias", "grupos"):
    assert em.cargar(tipo, em.plantilla(tipo)).manual
    assert em.nombre_plantilla(tipo).endswith(".csv") and tipo in em.AYUDA
    ejemplo = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"ejemplo_emparejamientos_{tipo}.csv")
    if os.path.exists(ejemplo):
        assert em.cargar(tipo, open(ejemplo, "rb").read()).manual
try:
    em.cargar("liga", "x")
    raise SystemExit("tipo desconocido")
except ValueError:
    pass
print("OK 5: plantillas y ejemplos")


# 6) Integración: crear el torneo desde el CSV y jugarlo entero ------------------------------------------------
def jugar_todo(codigo, sg=2):
    n = 0
    while True:
        jugables = [p for p in db.partidos_de(codigo)
                    if p["estado"] == "pendiente" and p["jugador1"] and p["jugador2"]
                    and "BYE" not in (p["origen1"], p["origen2"])]
        if not jugables:
            return n
        p = random.choice(jugables)
        s = (sg, random.randrange(sg)) if random.random() < .5 else (random.randrange(sg), sg)
        db.registrar_resultado(p["id"], *s)
        n += 1


def alta(codigo, tipo, obj, sg=2):
    return db.crear_torneo(codigo=codigo, nombre=f"Desde CSV {tipo}", fecha_inicio=date(2026, 6, 1),
                           fecha_fin=date(2026, 6, 5), tipo=tipo, sets_ganar=sg, jugadores=obj.jugadores, sorteo=obj)


# eliminatorias con byes en posiciones concretas (incluido BYE como jugador1)
obj = em.leer_eliminatorias("jugador1;jugador2;ranking1;ranking2\nBYE;Ana;;1\nBea;Cris;;\nDora;BYE;;\nEva;Flor;2;\n")
alta("CSV-ELI", "eliminatorias", obj)
r1 = [p for p in db.partidos_de("CSV-ELI") if p["ronda"] == 1]
assert [(p["nombre1"], p["nombre2"], p["estado"], p["nombre_ganador"]) for p in r1] == [
    (None, "Ana", "bye", "Ana"), ("Bea", "Cris", "pendiente", None),
    ("Dora", None, "bye", "Dora"), ("Eva", "Flor", "pendiente", None)]
assert r1[0]["ranking2"] == 1 and r1[1]["ranking1"] == SIN_RANKING
semi = [p for p in db.partidos_de("CSV-ELI") if p["ronda"] == 2]
assert semi[0]["nombre1"] == "Ana" and semi[1]["nombre1"] == "Dora"       # los byes ya avanzaron
jugados = jugar_todo("CSV-ELI")
t = db.obtener_torneo("CSV-ELI")
assert t["estado"] == "finalizado" and t["campeon"] and jugados == len(obj.jugadores) - 1
print("OK 6a: torneo de eliminatorias creado desde CSV y jugado hasta el campeón")

# todas las plantillas y varios tamaños de grupos, con sets 1/2/3
for sg in (1, 2, 3):
    alta(f"CSV-GRP-{sg}", "grupos", em.leer_grupos(em.plantilla("grupos")), sg)
    jugar_todo(f"CSV-GRP-{sg}", sg)
    t = db.obtener_torneo(f"CSV-GRP-{sg}")
    assert t["estado"] == "finalizado" and t["campeon"], t
    alta(f"CSV-ELI-{sg}", "eliminatorias", em.leer_eliminatorias(em.plantilla("eliminatorias")), sg)
    jugar_todo(f"CSV-ELI-{sg}", sg)
    assert db.obtener_torneo(f"CSV-ELI-{sg}")["estado"] == "finalizado"
# grupos mixtos 4+3+3
mixto = "grupo;jugador;ranking\n" + "".join(f"{l};{l}{i};{i + 1}\n" for l, n in (("A", 4), ("B", 3), ("C", 3)) for i in range(n))
alta("CSV-GRP-MIX", "grupos", em.leer_grupos(mixto))
jugar_todo("CSV-GRP-MIX")
assert db.obtener_torneo("CSV-GRP-MIX")["estado"] == "finalizado"
# 3 grupos de 4 (cuadros con byes) y comprobación de los dos cuadros
tres_g = "grupo;jugador;ranking\n" + "".join(f"{l};{l}{i};{i + 1}\n" for l in "ABC" for i in range(4))
alta("CSV-GRP-3G", "grupos", em.leer_grupos(tres_g))
jugar_todo("CSV-GRP-3G")
assert db.obtener_torneo("CSV-GRP-3G")["estado"] == "finalizado"
cl = db.clasificaciones("CSV-GRP-3G")
assert {k: len(v["tabla"]) for k, v in cl.items()} == {"A": 4, "B": 4, "C": 4} and all(v["completo"] for v in cl.values())
ps = db.partidos_de("CSV-GRP-3G")
assert {p["cuadro"] for p in ps if p["fase"] == "eliminatoria"} == {"principal", "consolacion"}
print("OK 6b: torneos con grupos de 4 creados desde CSV y jugados hasta el final (principal y consolación)")

# 7) Sin ranking: en un desempate total gana quien sí lo tiene ----------------------------------------------------------
obj = em.leer_grupos("grupo;jugador;ranking\nA;A;\nA;B;\nA;C;5\nA;D;1\n")
alta("CSV-RANK", "grupos", obj)
# A>B, B>C, C>A en circular (todos 2-0) y todos ganan a D: A, B y C empatan en todo salvo el ranking
res = {("A", "B"): (2, 0), ("B", "C"): (2, 0), ("C", "A"): (2, 0),
       ("A", "D"): (2, 0), ("B", "D"): (2, 0), ("C", "D"): (2, 0)}
for p in [p for p in db.partidos_de("CSV-RANK") if p["fase"] == "grupo"]:
    k = (p["nombre1"], p["nombre2"])
    if k in res:
        db.registrar_resultado(p["id"], *res[k])
    else:
        a, b = res[(p["nombre2"], p["nombre1"])]
        db.registrar_resultado(p["id"], b, a)
tabla = db.clasificaciones("CSV-RANK")["A"]["tabla"]
assert [f["PG"] for f in tabla] == [2, 2, 2, 0] and tabla[0]["nombre"] == "C" and tabla[3]["nombre"] == "D"
print("OK 7: sin ranking cuenta el último en los desempates")

# 8) Validaciones de alta que siguen valiendo con cuadros manuales
for tipo, obj in (("grupos", em.leer_eliminatorias(em.plantilla("eliminatorias"))),
                  ("eliminatorias", em.leer_grupos(em.plantilla("grupos")))):
    try:
        alta(f"MAL-{tipo}", tipo, obj)
        raise SystemExit("el tipo no corresponde al cuadro")
    except ValueError as e:
        assert "no corresponde" in str(e)
print("TODO OK EMPAREJAMIENTOS")

# 9) CSV de jugadores para el sorteo (jugador;ranking) ----------------------------------------------------------
js = em.leer_jugadores(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ejemplo_jugadores_sorteo.csv"), "rb").read())
assert [(j.nombre, j.ranking) for j in js][:2] == [("Ana García", 1), ("Elena Torres", 4)] and len(js) == 8
assert [j.nombre for j in em.leer_jugadores("nombre,ranking\nA,1\nB,2\n")] == ["A", "B"]          # alias y separador «,»
assert [j.ranking for j in em.leer_jugadores("Jugador ; Ranking\r\nA;3\r\n\r\nB;1\r\n".encode("cp1252"))] == [3, 1]
assert hay(errores_de(em.leer_jugadores, "jugador\nA\n"), "Faltan las columnas", "ranking")
assert hay(errores_de(em.leer_jugadores, "jugador;ranking\nA;\n"), "Línea 2", "falta el ranking")
assert hay(errores_de(em.leer_jugadores, "jugador;ranking\nA;x\nA;2\n"), "Línea 2", "ranking")
assert hay(errores_de(em.leer_jugadores, "jugador;ranking\nA;x\nA;2\n"), "Línea 3", "ya aparece")
assert hay(errores_de(em.leer_jugadores, "jugador;ranking\n"), "ningún jugador")
assert em.leer_jugadores(em.plantilla_jugadores())
print("OK 9: CSV de jugadores del sorteo")

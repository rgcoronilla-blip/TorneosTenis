"""Pruebas del cuadro visual (HTML)."""
import os
import random
import tempfile
from datetime import date, datetime

import torneo as db
import cuadro_visual as cv
from sorteo_torneo_tenis import FaseDeGruposYEliminatorias, Jugador, SorteoTorneo

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "cv.db")
random.seed(2)

# 1) Eliminatorias de 5 jugadores (con byes): una tarjeta por partido, columnas = rondas
js = [Jugador(f"J{i}", i) for i in range(1, 6)]
o = SorteoTorneo(js, seed=1); o.generar()
db.crear_torneo(codigo="V1", nombre="v", fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 2),
                tipo="eliminatorias", sets_ganar=2, jugadores=js, sorteo=o)
ps = [p for p in db.partidos_de("V1") if p["fase"] == "eliminatoria"]
h = cv.html_cuadro(ps)
assert "\n" not in h and "\r" not in h                           # una sola línea (Markdown de Streamlit)
assert h.count('class="cv-col"') == 3 and h.count('class="cv-m"') == len(ps) == 7
assert h.count(">BYE<") == 3 and "Cuartos de final" in h and "Semifinales" in h and "Final" in h
assert "Ganador Semifinal 1" in h or "Ganador Cuartos 1" in h      # casillas por determinar abreviadas
assert 'class="cv-f w"' not in h                                   # aún no hay ganadores
assert cv.html_cuadro([]) == ""

# 2) Resultados: ganador resaltado, marcador y juegos
p = next(x for x in ps if x["jugador1"] and x["jugador2"] and "BYE" not in (x["origen1"], x["origen2"]))
db.registrar_resultado(p["id"], 2, 1, "6-4 3-6 7-5", 14, 11)
db.programar_partido(next(x for x in ps if x["ronda"] == 3)["id"], datetime(2026, 1, 2, 19, 30))
ps = [x for x in db.partidos_de("V1") if x["fase"] == "eliminatoria"]
h = cv.html_cuadro(ps)
assert h.count('class="cv-f w"') >= 1 and 'class="cv-f l"' in h
assert "Juegos 14-11" in h and "6-4 3-6 7-5" in h
assert "📅" in h and "19:30" in h and "02/01" in h
h2 = cv.html_cuadro(ps, campeon="J1", etiqueta_campeon="Campeón")
assert (chr(34)+"cv-camp"+chr(34)) in h2 and "J1" in h2 and h2.count('class="cv-col"') == 4
assert (chr(34)+"cv-camp"+chr(34)) not in h

# 3) Todo lo que viene de la base de datos se escapa (sin inyección de HTML)
malo = [dict(p) for p in ps]
malo[0]["nombre1"] = '<script>alert(1)</script>'
malo[0]["jugador1"] = 999
malo[0]["marcador"] = '"><img src=x onerror=alert(2)>'
malo[0]["estado"] = "jugado"
malo[0]["sets1"], malo[0]["sets2"], malo[0]["ganador"] = 2, 0, 999
hm = cv.html_cuadro(malo, campeon="<b>x</b>")
assert "<script>" not in hm and "&lt;script&gt;" in hm
assert "<img" not in hm and "<b>x</b>" not in hm and "&lt;b&gt;x&lt;/b&gt;" in hm

# 4) Torneo de grupos: los dos cuadros y casillas de grupo ("1º Grupo A")
js = [Jugador(f"G{i}", i) for i in range(1, 9)]
o = FaseDeGruposYEliminatorias(js, por_bombos=True, seed=1); o.generar()
db.crear_torneo(codigo="V2", nombre="v", fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 2),
                tipo="grupos", sets_ganar=2, jugadores=js, sorteo=o)
ps = db.partidos_de("V2")
for c, txt in (("principal", "1º Grupo A"), ("consolacion", "3º Grupo A")):
    h = cv.html_cuadro([p for p in ps if p["fase"] == "eliminatoria" and p["cuadro"] == c])
    assert txt in h and h.count('class="cv-col"') == 2 and "Semifinales" in h

# 5) Página suelta
pg = cv.pagina_html(h, "t")
assert pg.startswith("<!doctype html>") and "<title>t</title>" in pg
print("TODO OK CUADRO VISUAL")

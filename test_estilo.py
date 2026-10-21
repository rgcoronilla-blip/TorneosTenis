"""Pruebas de las piezas HTML de estilo (escape, estructura, una sola línea)."""
import base64
import os
import tempfile

import estilo
from sorteo_torneo_tenis import Jugador, SIN_RANKING

MALO = '<script>alert(1)</script>'

# cabecera: escapa nombre y subtítulo, incrusta el escudo como data URI
png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
d = tempfile.mkdtemp(); ruta = os.path.join(d, "escudo_club.png"); open(ruta, "wb").write(png)
h = estilo.cabecera_html(MALO, '"><b>x</b>', ruta)
assert "\n" not in h and "<script>" not in h and "&lt;script&gt;" in h and "<b>x</b>" not in h
assert 'src="data:image/png;base64,' in h
assert "<img" not in estilo.cabecera_html("Club", "Sub", None)
assert "<img" not in estilo.cabecera_html("Club", "Sub", os.path.join(d, "no_existe.png"))

# clasificación
def fila(pos, nombre, pts, nj=0, ranking=5):
    return {"pos": pos, "nombre": nombre, "ranking": ranking, "Pts": pts, "PJ": 3, "PG": 2, "PP": 1, "NJ": nj,
            "SF": 5, "SC": 3, "DS": 2, "JF": 40, "JC": 38, "DJ": 2}
tabla = [fila(1, "A", 5), fila(2, MALO, 5), fila(3, "C", 4, ranking=SIN_RANKING), fila(4, "D", 3)]
h = estilo.clasificacion_html(tabla, completo=True)
assert "\n" not in h and "<script>" not in h and "&lt;script&gt;" in h
assert h.count('class="zp"') == 2 and h.count('class="zc"') == 2
assert h.count("Principal</span>") == 2 and h.count("Consolación</span>") == 2
assert "<th>NJ</th>" not in h and "+2" in h and "5-3" in h and "40-38" in h
assert "#999999" not in h
assert "<th>NJ</th>" in estilo.clasificacion_html([fila(1, "A", 0, nj=1)], True)
p = estilo.clasificacion_html(tabla, completo=False)
assert "Principal</span>" not in p and "Consolación</span>" not in p       # sin etiquetas hasta completar el grupo
assert "Consolación</span>" not in estilo.clasificacion_html(tabla, True, hay_consolacion=False)

# tarjetas
g = estilo.grupos_html([[Jugador("Ana", 1), Jugador(MALO, SIN_RANKING)], [Jugador("Bea", 2)]])
assert "Grupo A" in g and "Grupo B" in g and "<script>" not in g and "#999999" not in g and "\n" not in g
b = estilo.bombos_html([[Jugador("Ana", 1)], [Jugador("Bea", 2)]])
assert "Bombo 1" in b and "Bombo 2" in b

# lista de torneos
ts = [{"codigo": "T-1", "nombre": MALO, "tipo": "grupos", "fecha_inicio": "2026-06-01", "fecha_fin": "2026-06-09",
       "num_jugadores": 8, "estado": "en curso", "campeon": None, "visible": 0},
      {"codigo": "T-2", "nombre": "Open", "tipo": "eliminatorias", "fecha_inicio": "2026-06-01",
       "fecha_fin": "2026-06-09", "num_jugadores": 4, "estado": "finalizado", "campeon": "<i>Z</i>", "visible": 1}]
fmt = lambda iso: iso[8:10] + "/" + iso[5:7] + "/" + iso[:4]
h = estilo.torneos_html(ts, {"grupos": "Grupos", "eliminatorias": "Elim"}, fmt, admin=True)
assert "<script>" not in h and "<i>Z</i>" not in h and "&lt;i&gt;Z&lt;/i&gt;" in h and "\n" not in h
assert "t-estado en-curso" in h and "t-estado finalizado" in h and "01/06/2026" in h and "<th>Visible</th>" in h and "🔒" in h
ha = estilo.torneos_html(ts, {}, fmt, admin=False)
assert "<th>Visible</th>" not in ha and "🔒" not in ha
assert estilo.css_global().startswith("<style>") and "\n" not in estilo.css_global()
print("TODO OK ESTILO")

# --- gráfica de evolución del ranking ------------------------------------------------------
P = [{"etiqueta": "Inicio", "posicion": 9, "en_curso": False}, {"etiqueta": "C1 V1", "posicion": 8, "en_curso": False},
     {"etiqueta": "C1 V2", "posicion": 5, "en_curso": False},
     {"etiqueta": "C1 V3 (en curso)", "posicion": 6, "en_curso": True}]
assert estilo.evolucion_html([], "A") == "" and estilo.evolucion_html(P[:1], "A") == ""
h = estilo.evolucion_html(P, 'Ana <b>"X"</b>')
assert h.startswith("<svg") and h.endswith("</svg>") and "\n" not in h
assert "<b>" not in h and "&lt;b&gt;" in h                                        # nombre escapado
assert h.count("<title>") == 4 and "C1 V2: puesto 5" in h                          # un tooltip por punto
assert h.count("<line") >= 3 + 3 and 'stroke-dasharray="5 4"' in h                  # tramo en curso discontinuo
assert ">Ahora<" in h and ">Inicio<" in h and "↑ mejor puesto" in h
assert h.count('stroke-dasharray="5 4"') == 1
# eje invertido: el mejor puesto (5º) queda más arriba (menor y) que el peor (9º)
import re
cy = {int(p): float(c) for c, p in re.findall(r'<circle cx="[\d.]+" cy="([\d.]+)" r="4.5"[^>]*/><title>[^<]*: puesto (\d+)</title>', h)}
assert cy[5] < cy[6] < cy[8] < cy[9], cy
# muchas ventanas: no se saturan las etiquetas del eje horizontal
muchos = [{"etiqueta": f"C{i} V1", "posicion": 1 + i % 5, "en_curso": False} for i in range(1, 31)]
hm = estilo.evolucion_html(muchos, "M")
assert hm.count("font-size=\"11\" text-anchor=\"middle\"") <= 12
# plano: un jugador que no se mueve se dibuja sin dividir por cero
plano = [{"etiqueta": f"V{i}", "posicion": 3, "en_curso": False} for i in range(3)]
assert "<svg" in estilo.evolucion_html(plano, "P")
t = estilo.evolucion_tabla_html(P)
assert "⬆️ +1" in t and "⬆️ +3" in t and "⬇️ -1" in t and "—" in t and "\n" not in t
print("OK gráfica de evolución")

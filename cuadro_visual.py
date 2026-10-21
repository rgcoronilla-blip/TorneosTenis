"""
Cuadro de eliminatorias dibujado como un árbol (HTML + CSS), con conectores entre rondas.

`html_cuadro(partidos)` recibe los partidos de UN cuadro (los de `torneo.partidos_de` con
fase 'eliminatoria' y el mismo `cuadro`) y devuelve un fragmento HTML autocontenido (con su
`<style>`) para mostrar con `st.markdown(..., unsafe_allow_html=True)`.

- El HTML se devuelve en una sola línea, sin saltos ni sangrías, para que el intérprete de
  Markdown de Streamlit no lo trate como bloque de código ni lo corte en las líneas en blanco.
- Todo texto que viene de la base de datos (nombres, marcadores…) se escapa.
- Los colores usan transparencias y `inherit`, así que se ven bien en tema claro y oscuro.
"""

import html
import re
from datetime import datetime
from typing import Dict, List, Optional

from sorteo_torneo_tenis import SIN_RANKING, nombres_de_rondas

ACENTO = "#2e7d32"       # verde pista; color del ganador
ANCHO_TARJETA = 236      # px por columna (incluye el hueco de los conectores)
_DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

CSS = f"""
.cv-solo{{overflow:visible;padding:2px 0}}
.cv-solo .cv-m{{max-width:440px}}
.cv{{--cv-acento:{ACENTO};--cv-linea:rgba(128,128,128,.55);--cv-fondo:rgba(128,128,128,.10);
--cv-borde:rgba(128,128,128,.38);--cv-suave:rgba(128,128,128,.95);display:flex;align-items:stretch;
overflow-x:auto;padding:6px 2px 14px;font-size:14px;line-height:1.25;color:inherit}}
.cv *{{box-sizing:border-box}}
.cv-col{{display:flex;flex-direction:column;flex:0 0 {ANCHO_TARJETA}px;min-width:{ANCHO_TARJETA}px}}
.cv-h{{text-align:center;font-weight:700;font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;
color:var(--cv-suave);padding:0 0 8px}}
.cv-slots{{display:flex;flex-direction:column;flex:1}}
.cv-slot{{position:relative;flex:1;display:flex;align-items:center;padding:6px 20px;min-height:78px}}
.cv-m{{position:relative;z-index:1;width:100%;border:1px solid var(--cv-borde);border-radius:9px;
background:var(--cv-fondo);overflow:hidden}}
.cv-f{{display:flex;align-items:center;gap:6px;padding:6px 8px;border-left:3px solid transparent}}
.cv-f+.cv-f{{border-top:1px solid var(--cv-borde)}}
.cv-f.w{{border-left-color:var(--cv-acento);background:rgba(46,125,50,.16);font-weight:700}}
.cv-f.l{{opacity:.6}}
.cv-f.t{{color:var(--cv-suave);font-style:italic}}
.cv-f.b{{color:var(--cv-suave);font-size:12px;letter-spacing:.08em}}
.cv-rk{{font-size:11px;color:var(--cv-suave);min-width:24px;font-weight:400;font-style:normal}}
.cv-n{{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cv-s{{min-width:16px;text-align:right;font-variant-numeric:tabular-nums;font-weight:700}}
.cv-meta{{font-size:11px;color:var(--cv-suave);padding:3px 8px;border-top:1px solid var(--cv-borde);
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cv-slot.r::after{{content:"";position:absolute;right:0;top:50%;width:20px;border-top:2px solid var(--cv-linea)}}
.cv-slot.l::before{{content:"";position:absolute;left:0;top:50%;width:20px;border-top:2px solid var(--cv-linea)}}
.cv-v{{position:absolute;right:0;width:0;height:50%;border-right:2px solid var(--cv-linea)}}
.cv-slot.up .cv-v{{top:50%}}
.cv-slot.dn .cv-v{{top:0}}
.cv-camp{{width:100%;text-align:center;padding:12px 8px;border-radius:9px;border:2px solid var(--cv-acento);
background:rgba(46,125,50,.16);font-weight:700}}
.cv-camp small{{display:block;font-weight:400;color:var(--cv-suave);font-size:11px;margin-bottom:2px}}
"""


_ABREVIATURAS = {"octavos": "Octavos", "cuartos": "Cuartos", "semifinales": "Semifinal", "final": "Final"}


def _corto(origen: Optional[str]) -> str:
    """«Ganador Cuartos de final #2» -> «Ganador Cuartos 2» (cabe en la tarjeta)."""
    if not origen:
        return "Por determinar"
    m = re.fullmatch(r"Ganador (.+) #(\d+)", origen)
    if not m:
        return origen
    ronda = m.group(1)
    primera = ronda.split()[0].lower()
    return f"Ganador {_ABREVIATURAS.get(primera, ronda.split()[0])} {m.group(2)}"


def _esc(texto) -> str:
    return html.escape(str(texto), quote=True)


def _fecha(valor: Optional[str]) -> str:
    if not valor:
        return ""
    try:
        d = datetime.fromisoformat(valor)
    except ValueError:
        return ""
    return f"📅 {_DIAS[d.weekday()]} {d:%d/%m %H:%M}"


def _fila(p: Dict, k: int, gana: Optional[int], con_bye: bool, jugado: bool) -> str:
    """Una fila de jugador (k = 1 ó 2) de la tarjeta del partido."""
    jugador = p[f"jugador{k}"]
    origen = p[f"origen{k}"]
    if origen == "BYE":
        return '<div class="cv-f b"><span class="cv-rk"></span><span class="cv-n">BYE</span></div>'
    if jugador is None:
        return (f'<div class="cv-f t"><span class="cv-rk"></span>'
                f'<span class="cv-n" title="{_esc(origen or "Por determinar")}">{_esc(_corto(origen))}</span></div>')
    ranking = p[f"ranking{k}"]
    rk = f"#{ranking}" if ranking is not None and ranking != SIN_RANKING else ""
    clase = ""
    if jugado and gana is not None:
        clase = " w" if gana == jugador else " l"
    sets = p[f"sets{k}"] if jugado and not con_bye else None
    marcador = f'<span class="cv-s">{sets}</span>' if sets is not None else ""
    nombre = _esc(p[f"nombre{k}"])
    return (f'<div class="cv-f{clase}"><span class="cv-rk">{rk}</span>'
            f'<span class="cv-n" title="{nombre}">{nombre}</span>{marcador}</div>')


def _tarjeta(p: Dict, con_meta: bool = True) -> str:
    con_bye = "BYE" in (p["origen1"], p["origen2"])
    jugado = p["estado"] == "jugado"
    gana = p["ganador"] if (jugado or p["estado"] == "bye") else None
    filas = _fila(p, 1, gana, con_bye, jugado) + _fila(p, 2, gana, con_bye, jugado)
    meta = ""
    if con_meta and not con_bye:
        if jugado:
            partes = []
            if p.get("juegos1") is not None:
                partes.append(f"Juegos {p['juegos1']}-{p['juegos2']}")
            if p.get("marcador"):
                partes.append(p["marcador"])
            meta = " · ".join(partes)
        else:
            meta = _fecha(p.get("fecha_hora"))
    if meta:
        meta = f'<div class="cv-meta">{_esc(meta)}</div>'
    return f'<div class="cv-m">{filas}{meta}</div>'


def tarjeta_html(p: Dict, con_meta: bool = True) -> str:
    """Un solo partido con el mismo aspecto que en el cuadro (sin `<style>`: lo pone `estilo.inyectar`)."""
    return f'<div class="cv cv-solo">{_tarjeta(p, con_meta)}</div>'


def html_cuadro(partidos: List[Dict], campeon: Optional[str] = None,
                etiqueta_campeon: str = "Campeón") -> str:
    """
    HTML del cuadro de un único cuadro de eliminatorias.
    `campeon` (nombre) añade una columna final con el ganador cuando ya se conoce.
    """
    if not partidos:
        return ""
    rondas = sorted({p["ronda"] for p in partidos})
    nombres = nombres_de_rondas(2 ** len(rondas))
    ultima = rondas[-1]
    con_campeon = bool(campeon)

    columnas = []
    for r in rondas:
        delaronda = sorted((p for p in partidos if p["ronda"] == r), key=lambda p: p["posicion"])
        slots = []
        for p in delaronda:
            clases = ["cv-slot"]
            v = ""
            if r != ultima:
                clases.append("r")
                clases.append("up" if p["posicion"] % 2 == 1 else "dn")
                v = '<span class="cv-v"></span>'
            elif con_campeon:
                clases.append("r")
            if r != rondas[0]:
                clases.append("l")
            slots.append(f'<div class="{" ".join(clases)}">{_tarjeta(p)}{v}</div>')
        columnas.append(f'<div class="cv-col"><div class="cv-h">{_esc(nombres[r - 1])}</div>'
                        f'<div class="cv-slots">{"".join(slots)}</div></div>')
    if con_campeon:
        columnas.append(
            f'<div class="cv-col"><div class="cv-h">&nbsp;</div><div class="cv-slots">'
            f'<div class="cv-slot l"><div class="cv-camp"><small>🏆 {_esc(etiqueta_campeon)}</small>'
            f'{_esc(campeon)}</div></div></div></div>')
    return f'<style>{CSS}</style><div class="cv">{"".join(columnas)}</div>'.replace("\n", "")


def pagina_html(cuerpo: str, titulo: str = "Cuadro") -> str:
    """Página HTML completa (para abrir el cuadro suelto en un navegador o hacer una captura)."""
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"<title>{_esc(titulo)}</title><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>:root{color-scheme:light dark}body{margin:0;padding:20px 16px;font-family:system-ui,sans-serif;"
        "background:#fff;color:#1f2933}@media (prefers-color-scheme:dark){body{background:#0e1117;color:#fafafa}}"
        f"</style></head><body>{cuerpo}</body></html>"
    )


def partidos_desde_cuadro(cuadro: list, draw_size: int) -> List[Dict]:
    """
    Partidos "de mentira" a partir de un cuadro sorteado (lista de Jugador / «1º Grupo A» / «BYE»),
    para dibujar el cuadro completo antes de guardarlo. Quien pasa por un BYE avanza solo.
    """
    nombres = nombres_de_rondas(draw_size)
    contador = [0]

    def competidor(valor):
        if valor is None or valor == "BYE":
            return {"jugador": None, "origen": "BYE", "nombre": None, "ranking": None}
        if hasattr(valor, "nombre"):
            contador[0] += 1
            return {"jugador": contador[0], "origen": None, "nombre": valor.nombre, "ranking": valor.ranking}
        return {"jugador": None, "origen": str(valor), "nombre": None, "ranking": None}

    def partido(r, pos, a, b):
        return {"ronda": r, "posicion": pos, "estado": "pendiente", "ganador": None, "fecha_hora": None,
                "marcador": None, "sets1": None, "sets2": None, "juegos1": None, "juegos2": None,
                "jugador1": a["jugador"], "origen1": a["origen"], "nombre1": a["nombre"], "ranking1": a["ranking"],
                "jugador2": b["jugador"], "origen2": b["origen"], "nombre2": b["nombre"], "ranking2": b["ranking"]}

    actual = [competidor(v) for v in cuadro]
    partidos: List[Dict] = []
    ronda = 1
    while len(actual) > 1:
        siguiente = []
        for pos in range(1, len(actual) // 2 + 1):
            a, b = actual[2 * pos - 2], actual[2 * pos - 1]
            partidos.append(partido(ronda, pos, a, b))
            if a["origen"] == "BYE" and b["origen"] != "BYE":
                siguiente.append(dict(b))
            elif b["origen"] == "BYE" and a["origen"] != "BYE":
                siguiente.append(dict(a))
            else:
                siguiente.append({"jugador": None, "nombre": None, "ranking": None,
                                  "origen": f"Ganador {nombres[ronda - 1]} #{pos}"})
        actual = siguiente
        ronda += 1
    return partidos


def html_cuadro_sorteo(cuadro: list, draw_size: int) -> str:
    """Cuadro completo de un sorteo todavía sin guardar."""
    return html_cuadro(partidos_desde_cuadro(cuadro, draw_size))

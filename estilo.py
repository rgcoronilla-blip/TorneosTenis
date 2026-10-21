"""
Estilo visual común de la interfaz: CSS global y piezas HTML (cabecera del club, tablas de
clasificación y de torneos, tarjetas de grupos y bombos). Se pinta con
`st.markdown(..., unsafe_allow_html=True)`.

Reglas:
- Todo texto que viene de la base de datos se escapa con `html.escape`.
- Cada pieza se devuelve en una sola línea (el Markdown de Streamlit rompe el HTML con líneas en
  blanco y trata las líneas con sangría como código).
- Los colores usan transparencias y `inherit`: valen para tema claro y oscuro.
"""

import base64
import html
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from sorteo_torneo_tenis import SIN_RANKING

import cuadro_visual

VERDE = cuadro_visual.ACENTO
VERDE_OSCURO = "#1b5e20"
AMBAR = "#b7791f"

CSS_GLOBAL = f"""
.block-container{{padding-top:1.4rem;max-width:1240px}}
[data-testid="stMetric"]{{background:rgba(128,128,128,.08);border:1px solid rgba(128,128,128,.28);
border-radius:12px;padding:10px 14px}}
[data-testid="stMetricLabel"]{{opacity:.75}}
[data-testid="stVerticalBlockBorderWrapper"]{{border-radius:12px}}
[data-testid="stExpander"]{{border-radius:12px}}
.stTabs [data-baseweb="tab"]{{font-weight:600}}
.stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{{border-radius:999px;font-weight:600}}
.sp-franja{{margin:0 0 16px;padding:10px 14px 12px;border:1px solid rgba(128,128,128,.28);border-radius:14px;
background:rgba(128,128,128,.06)}}
.sp-tit{{font-size:.72rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;opacity:.65;margin:0 0 8px}}
.sp-logos{{display:flex;flex-wrap:wrap;gap:10px;justify-content:center}}
.sp-logo{{box-sizing:border-box;display:flex;align-items:center;justify-content:center;background:#fff;border-radius:10px;
padding:6px 12px;height:72px;border:1px solid rgba(128,128,128,.25);text-decoration:none;min-width:0}}
.sp-c1 .sp-logo{{flex:0 0 100%}}
.sp-c2 .sp-logo{{flex:0 0 calc((100% - 10px) / 2)}}
.sp-c3 .sp-logo{{flex:0 0 calc((100% - 20px) / 3)}}
.sp-logo img{{max-height:58px;max-width:100%;width:auto;height:auto;object-fit:contain;display:block}}
a.sp-logo:hover{{box-shadow:0 2px 8px rgba(0,0,0,.2)}}
.rk-pos{{font-weight:800;width:44px}}
.rk-top1{{background:rgba(212,175,55,.18)}}.rk-top2{{background:rgba(160,160,160,.18)}}.rk-top3{{background:rgba(176,112,60,.16)}}
.rk-vs{{opacity:.6;font-size:12px}}
.rk-gan{{font-weight:800;color:#2e7d32}}
.an-card{{margin:0 0 10px;padding:12px 16px;border:1px solid rgba(128,128,128,.28);border-radius:14px;
background:rgba(128,128,128,.06)}}
.an-fijado{{border-color:rgba(46,125,50,.6);background:rgba(46,125,50,.09)}}
.an-cad{{opacity:.6}}
.an-cab{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:4px}}
.an-tit{{font-weight:800;font-size:1.05rem}}
.an-etq{{display:inline-block;padding:1px 9px;border-radius:999px;font-size:11.5px;font-weight:700;
background:rgba(128,128,128,.2)}}
.an-fecha{{opacity:.65;font-size:12.5px;margin-left:auto}}
.an-txt{{line-height:1.5;word-break:break-word}}
.t-banner{{display:flex;align-items:center;gap:16px;padding:16px 22px;border-radius:16px;margin:0 0 16px;
color:#fff;background:linear-gradient(135deg,{VERDE_OSCURO},{VERDE} 62%,#4c9a50)}}
.t-banner img{{height:76px;width:auto;border-radius:10px;background:rgba(255,255,255,.14);padding:4px}}
.t-banner-t{{font-size:1.55rem;font-weight:800;letter-spacing:-.01em;line-height:1.15}}
.t-banner-s{{margin-top:3px;opacity:.88;font-size:.92rem}}
.t-chip{{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:700;
white-space:nowrap;border:1px solid rgba(128,128,128,.4)}}
.t-chip.p{{background:rgba(46,125,50,.18);border-color:rgba(46,125,50,.55)}}
.t-chip.c{{background:rgba(183,121,31,.2);border-color:rgba(183,121,31,.6)}}
.t-chip.g{{background:rgba(128,128,128,.16)}}
.t-scroll{{overflow-x:auto;margin:4px 0 10px}}
.t-tabla{{width:100%;border-collapse:separate;border-spacing:0;font-size:14px;
border:1px solid rgba(128,128,128,.34);border-radius:12px;overflow:hidden}}
.t-tabla th{{background:rgba(128,128,128,.14);font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;
padding:8px 10px;text-align:center;white-space:nowrap}}
.t-tabla td{{padding:8px 10px;text-align:center;border-top:1px solid rgba(128,128,128,.22);
font-variant-numeric:tabular-nums;white-space:nowrap}}
.t-tabla .izq{{text-align:left}}
.t-tabla td.pts{{font-weight:800}}
.t-tabla td.pos{{font-weight:700;color:rgba(128,128,128,.95);border-left:4px solid transparent}}
.t-tabla tr.zp td.pos{{border-left-color:{VERDE}}}
.t-tabla tr.zp{{background:rgba(46,125,50,.09)}}
.t-tabla tr.zc td.pos{{border-left-color:{AMBAR}}}
.t-tabla tr.zc{{background:rgba(183,121,31,.08)}}
.t-tabla td .rk{{font-size:11px;color:rgba(128,128,128,.95);margin-right:6px}}
.t-leyenda{{font-size:12px;color:rgba(128,128,128,.95);margin:0 0 8px}}
.t-leyenda i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin:0 4px 0 10px;vertical-align:-1px}}
.t-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:12px;margin:6px 0 14px}}
.t-card{{border:1px solid rgba(128,128,128,.34);border-radius:12px;overflow:hidden;background:rgba(128,128,128,.07)}}
.t-card-h{{padding:7px 12px;font-weight:800;font-size:12.5px;letter-spacing:.05em;text-transform:uppercase;
background:linear-gradient(135deg,{VERDE_OSCURO},{VERDE});color:#fff}}
.t-card-h.b{{background:linear-gradient(135deg,#3b3f45,#5a6068)}}
.t-card-i{{display:flex;gap:6px;align-items:center;padding:6px 12px;border-top:1px solid rgba(128,128,128,.2);font-size:14px}}
.t-card-i:first-of-type{{border-top:none}}
.t-card-i .rk{{font-size:11px;color:rgba(128,128,128,.95);min-width:26px}}
.t-card-i .n{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.t-estado{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:700}}
.t-estado.sorteado{{background:rgba(128,128,128,.2)}}
.t-estado.en-curso{{background:rgba(183,121,31,.22)}}
.t-estado.finalizado{{background:rgba(46,125,50,.22)}}
""" + cuadro_visual.CSS


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


def _una_linea(texto: str) -> str:
    return texto.replace("\n", "")


def css_global() -> str:
    return _una_linea(f"<style>{CSS_GLOBAL}</style>")


def inyectar(st) -> None:
    """Pone el CSS global (una vez por ejecución de la página)."""
    st.markdown(css_global(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Cabecera del club
# ---------------------------------------------------------------------------

def imagen_data_uri(ruta: Optional[Path]) -> Optional[str]:
    """La imagen como `data:` URI (para incrustarla en el HTML), o None si no se puede leer."""
    if ruta is None:
        return None
    try:
        datos = Path(ruta).read_bytes()
    except OSError:
        return None
    tipo = mimetypes.guess_type(str(ruta))[0] or "image/png"
    if not tipo.startswith("image/"):
        return None
    return f"data:{tipo};base64,{base64.b64encode(datos).decode('ascii')}"


def cabecera_html(nombre: str, subtitulo: str, escudo: Optional[Path] = None) -> str:
    uri = imagen_data_uri(escudo)
    img = f'<img src="{_esc(uri)}" alt="Escudo de {_esc(nombre)}">' if uri else ""
    return _una_linea(
        f'<div class="t-banner">{img}<div><div class="t-banner-t">{_esc(nombre)}</div>'
        f'<div class="t-banner-s">{_esc(subtitulo)}</div></div></div>')


def columnas_patrocinadores(n: int) -> int:
    """Logos por fila: el banner se reparte entre ellos y nunca hay más de tres juntos (4 → 2+2)."""
    return 1 if n <= 1 else 2 if n in (2, 4) else 3


def patrocinadores_html(patrocinadores: List[Dict]) -> str:
    """Franja de patrocinadores del torneo ("" si no hay). Solo se enlazan URL http(s)."""
    if not patrocinadores:
        return ""
    logos = []
    for p in patrocinadores:
        mime = p["mime"] if str(p.get("mime", "")).startswith("image/") else "image/png"
        uri = f"data:{mime};base64,{base64.b64encode(p['imagen']).decode('ascii')}"
        img = f'<img src="{uri}" alt="{_esc(p["nombre"])}" title="{_esc(p["nombre"])}">'
        url = (p.get("url") or "").strip()
        if url.lower().startswith(("http://", "https://")):
            logos.append(f'<a class="sp-logo" href="{_esc(url)}" target="_blank" '
                         f'rel="noopener noreferrer sponsored">{img}</a>')
        else:
            logos.append(f'<span class="sp-logo">{img}</span>')
    return _una_linea(f'<div class="sp-franja"><div class="sp-tit">Patrocinadores</div>'
                      f'<div class="sp-logos sp-c{columnas_patrocinadores(len(logos))}">{"".join(logos)}</div></div>')


# ---------------------------------------------------------------------------
# Clasificación de un grupo
# ---------------------------------------------------------------------------

def _signo(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def clasificacion_html(tabla: List[Dict], completo: bool, hay_consolacion: bool = True) -> str:
    """
    Tabla de un grupo. Las dos primeras posiciones (verde) van al cuadro principal y las demás
    (ámbar) a la consolación; la etiqueta de destino sale cuando el grupo está completo.
    """
    con_nj = any(f["NJ"] for f in tabla)
    cab = ('<tr><th>#</th><th class="izq">Jugador</th><th>Pts</th><th>PJ</th><th>PG</th><th>PP</th>'
           + ("<th>NJ</th>" if con_nj else "")
           + "<th>Sets</th><th>DS</th><th>Juegos</th><th>DJ</th></tr>")
    filas = []
    for f in tabla:
        principal = f["pos"] <= 2
        chip = ""
        if completo:
            if principal:
                chip = ' <span class="t-chip p">Principal</span>'
            elif hay_consolacion:
                chip = ' <span class="t-chip c">Consolación</span>'
        rk = f'<span class="rk">#{f["ranking"]}</span>' if f["ranking"] not in (None, SIN_RANKING) else ""
        filas.append(
            f'<tr class="{"zp" if principal else "zc"}"><td class="pos">{f["pos"]}</td>'
            f'<td class="izq">{rk}<b>{_esc(f["nombre"])}</b>{chip}</td>'
            f'<td class="pts">{f["Pts"]}</td><td>{f["PJ"]}</td><td>{f["PG"]}</td><td>{f["PP"]}</td>'
            + (f'<td>{f["NJ"]}</td>' if con_nj else "")
            + f'<td>{f["SF"]}-{f["SC"]}</td><td>{_signo(f["DS"])}</td>'
            f'<td>{f["JF"]}-{f["JC"]}</td><td>{_signo(f["DJ"])}</td></tr>')
    leyenda = ('<div class="t-leyenda"><i style="background:' + VERDE + '"></i>Cuadro principal'
               + ('<i style="background:' + AMBAR + '"></i>Cuadro consolación' if hay_consolacion else "")
               + "</div>")
    return _una_linea(f'{leyenda}<div class="t-scroll"><table class="t-tabla"><thead>{cab}</thead>'
                      f'<tbody>{"".join(filas)}</tbody></table></div>')


# ---------------------------------------------------------------------------
# Tarjetas de grupos y de bombos (vista previa del sorteo)
# ---------------------------------------------------------------------------

def _tarjetas(titulos: List[str], listas: List[list], clase_cabecera: str = "") -> str:
    tarjetas = []
    for titulo, jugadores in zip(titulos, listas):
        items = []
        for j in jugadores:
            rk = f'<span class="rk">#{j.ranking}</span>' if j.ranking != SIN_RANKING else '<span class="rk"></span>'
            items.append(f'<div class="t-card-i">{rk}<span class="n" title="{_esc(j.nombre)}">{_esc(j.nombre)}</span></div>')
        tarjetas.append(f'<div class="t-card"><div class="t-card-h {clase_cabecera}">{_esc(titulo)}</div>{"".join(items)}</div>')
    return _una_linea(f'<div class="t-grid">{"".join(tarjetas)}</div>')


def grupos_html(grupos: List[list]) -> str:
    letras = [chr(65 + i) for i in range(len(grupos))]
    return _tarjetas([f"Grupo {l}" for l in letras], grupos)


def bombos_html(bombos: List[list]) -> str:
    return _tarjetas([f"Bombo {i}" for i in range(1, len(bombos) + 1)], bombos, "b")


# ---------------------------------------------------------------------------
# Lista de torneos
# ---------------------------------------------------------------------------

def torneos_html(torneos: List[Dict], tipos: Dict[str, str], fmt_fecha: Callable[[str], str],
                 admin: bool = False) -> str:
    cab = ('<tr><th class="izq">Código</th><th class="izq">Nombre</th><th class="izq">Tipo</th><th>Inicio</th>'
           '<th>Fin</th><th>Jugadores</th><th>Estado</th><th class="izq">Campeón</th>'
           + ("<th>Visible</th>" if admin else "") + "</tr>")
    filas = []
    for t in torneos:
        estado = str(t["estado"])
        clase = estado.replace(" ", "-")
        oculto = admin and not t.get("visible", 1)
        filas.append(
            f'<tr><td class="izq"><b>{_esc(t["codigo"])}</b></td>'
            f'<td class="izq">{_esc(t["nombre"])}{" 🔒" if oculto else ""}</td>'
            f'<td class="izq">{_esc(tipos.get(t["tipo"], t["tipo"]))}</td>'
            f'<td>{_esc(fmt_fecha(t["fecha_inicio"]))}</td><td>{_esc(fmt_fecha(t["fecha_fin"]))}</td>'
            f'<td>{t["num_jugadores"]}</td>'
            f'<td><span class="t-estado {_esc(clase)}">{_esc(estado.capitalize())}</span></td>'
            f'<td class="izq">{"🏆 " + _esc(t["campeon"]) if t.get("campeon") else "—"}</td>'
            + (f'<td>{"🔒 No" if oculto else "Sí"}</td>' if admin else "") + "</tr>")
    return _una_linea(f'<div class="t-scroll"><table class="t-tabla"><thead>{cab}</thead>'
                      f'<tbody>{"".join(filas)}</tbody></table></div>')


# ---------------------------------------------------------------------------
# Ranking continuo
# ---------------------------------------------------------------------------

def ranking_html(jugadores: List[Dict]) -> str:
    """Clasificación del ranking continuo (ya ordenada por posición)."""
    medallas = {1: "🥇", 2: "🥈", 3: "🥉"}
    filas = []
    for j in jugadores:
        pos = j["posicion"]
        clase = f' class="rk-top{pos}"' if pos in medallas else ""
        filas.append(f'<tr{clase}><td class="rk-pos">{pos}</td><td class="izq">{medallas.get(pos, "")} '
                     f'{_esc(j["nombre"])}</td></tr>')
    if not filas:
        return ""
    return _una_linea('<div class="t-scroll"><table class="t-tabla"><thead><tr><th>Puesto</th>'
                      f'<th class="izq">Jugador</th></tr></thead><tbody>{"".join(filas)}</tbody></table></div>')


def _resultado_rk(p: Dict) -> str:
    if p["estado"] != "jugado":
        return "Pendiente"
    texto = f'<span class="rk-gan">{_esc(p["nombre_ganador"])}</span>'
    if p.get("walkover"):
        texto += " (incomparecencia)"
    elif p.get("marcador"):
        texto += f' · {_esc(p["marcador"])}'
    return texto


_DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _fecha_prevista(iso) -> str:
    if not iso:
        return "Por confirmar"
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return "Por confirmar"
    return f"{_DIAS_CORTOS[d.weekday()]} {d:%d/%m/%Y} · {d:%H:%M}"


def partidos_ranking_html(partidos: List[Dict]) -> str:
    """Partidos de una ventana: el mejor situado a la izquierda, con su día y hora previstos."""
    if not partidos:
        return ""
    filas = [f'<tr><td class="izq">{p["pos_alto"]}º <b>{_esc(p["nombre_alto"])}</b></td>'
             f'<td class="rk-vs">vs</td>'
             f'<td class="izq">{p["pos_bajo"]}º <b>{_esc(p["nombre_bajo"])}</b></td>'
             f'<td class="izq">{_esc(_fecha_prevista(p.get("fecha_hora")))}</td>'
             f'<td class="izq">{_resultado_rk(p)}</td></tr>' for p in partidos]
    return _una_linea('<div class="t-scroll"><table class="t-tabla"><thead><tr><th class="izq">Mejor situado</th>'
                      '<th></th><th class="izq">Peor situado</th><th class="izq">Fecha prevista</th>'
                      '<th class="izq">Resultado</th></tr></thead>'
                      f'<tbody>{"".join(filas)}</tbody></table></div>')


def historial_ranking_html(items: List[Dict], nombres_ventana: Dict[str, str]) -> str:
    if not items:
        return ""
    filas = []
    for p in items:
        cambio = "⬆️ intercambio de puestos" if p["subio"] else "sin cambios"
        filas.append(f'<tr><td class="izq">{_esc(nombres_ventana.get(p["tipo"], p["tipo"]))} · ciclo {p["ciclo"]}</td>'
                     f'<td class="izq">{_esc(p["nombre_alto"])} <span class="rk-vs">vs</span> {_esc(p["nombre_bajo"])}</td>'
                     f'<td class="izq">{_resultado_rk(p)}</td><td class="izq">{cambio}</td></tr>')
    return _una_linea('<div class="t-scroll"><table class="t-tabla"><thead><tr><th class="izq">Ventana</th>'
                      '<th class="izq">Partido</th><th class="izq">Resultado</th><th class="izq">Efecto</th></tr></thead>'
                      f'<tbody>{"".join(filas)}</tbody></table></div>')


# ---------------------------------------------------------------------------
# Tablón de anuncios
# ---------------------------------------------------------------------------

def anuncios_html(anuncios: List[Dict]) -> str:
    """Tarjetas de anuncios (el texto se escapa y los saltos de línea se respetan)."""
    nombres = {"general": "General", "torneo": "Torneo", "ranking": "Ranking continuo"}
    tarjetas = []
    for a in anuncios:
        etiqueta = nombres.get(a["ambito"], a["ambito"])
        if a["ambito"] == "torneo" and a.get("torneo_nombre"):
            etiqueta += f": {a['torneo_nombre']}"
        try:
            fecha = datetime.fromisoformat(str(a["creado"])).strftime("%d/%m/%Y")
        except ValueError:
            fecha = ""
        clases = "an-card" + (" an-fijado" if a.get("fijado") else "") + (" an-cad" if a.get("caducado") else "")
        extra = ""
        if a.get("caduca"):
            try:
                extra = f' · {"caducó" if a.get("caducado") else "caduca"} el {datetime.fromisoformat(a["caduca"]):%d/%m/%Y}'
            except ValueError:
                pass
        texto = _esc(a["texto"]).replace("\n", "<br>")
        tarjetas.append(
            f'<div class="{clases}"><div class="an-cab">{"📌 " if a.get("fijado") else ""}'
            f'<span class="an-tit">{_esc(a["titulo"])}</span><span class="an-etq">{_esc(etiqueta)}</span>'
            f'<span class="an-fecha">{_esc(fecha)}{_esc(extra)}</span></div><div class="an-txt">{texto}</div></div>')
    return _una_linea("".join(tarjetas))


# ---------------------------------------------------------------------------
# Ranking continuo: evolución de un jugador
# ---------------------------------------------------------------------------

_COLOR_EVOLUCION = "#3f9b45"  # verde del club algo más claro: se lee bien en tema claro y oscuro


def evolucion_html(puntos: List[Dict], nombre: str) -> str:
    """
    Gráfica de líneas (SVG) con el puesto de un jugador en cada ventana. El eje vertical va invertido:
    el puesto 1 queda arriba. Necesita al menos dos puntos; si no, devuelve "".
    """
    if len(puntos) < 2:
        return ""
    W, H, ml, mr, mt, mb = 720, 290, 46, 30, 26, 56
    pos = [p["posicion"] for p in puntos]
    lo = max(1, min(pos) - 2)
    hi = max(max(pos) + 2, lo + 4)
    n = len(puntos)

    def x(i):
        return ml + (W - ml - mr) * (i / (n - 1))

    def y(p):
        return mt + (H - mt - mb) * ((p - lo) / (hi - lo))

    paso = max(1, -(-(hi - lo) // 5))
    ticks = list(range(lo, hi + 1, paso))
    if ticks[-1] != hi and hi - ticks[-1] >= paso:
        ticks.append(hi)
    cada = max(1, -(-n // 10))
    partes = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;color:inherit" role="img" '
              f'aria-label="Evolución de puestos de {_esc(nombre)}: '
              + "; ".join(f"{_esc(p['etiqueta'])} puesto {p['posicion']}" for p in puntos) + '">']
    partes.append(f'<text x="{ml}" y="12" font-size="11" fill="currentColor" opacity=".6">↑ mejor puesto</text>')
    for t in ticks:
        partes.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="currentColor" opacity=".13"/>'
                      f'<text x="{ml - 8}" y="{y(t) + 4:.1f}" font-size="11" text-anchor="end" fill="currentColor" '
                      f'opacity=".7">{t}º</text>')
    for i, p in enumerate(puntos):
        if i % cada == 0 or i == n - 1:
            et = "Ahora" if p.get("en_curso") else p["etiqueta"]
            partes.append(f'<text x="{x(i):.1f}" y="{H - mb + 20}" font-size="11" text-anchor="middle" '
                          f'fill="currentColor" opacity=".7">{_esc(et)}</text>')
    # tramos: el último es discontinuo si es la ventana en curso
    for i in range(n - 1):
        seco = ' stroke-dasharray="5 4"' if puntos[i + 1].get("en_curso") else ""
        partes.append(f'<line x1="{x(i):.1f}" y1="{y(pos[i]):.1f}" x2="{x(i + 1):.1f}" y2="{y(pos[i + 1]):.1f}" '
                      f'stroke="{_COLOR_EVOLUCION}" stroke-width="2" stroke-linecap="round"{seco}/>')
    mejor = min(pos)
    etiquetados = {0, n - 1, pos.index(mejor)}
    for i, p in enumerate(puntos):
        hueco = ' fill="none" stroke-width="2"' if p.get("en_curso") else ""
        relleno = "" if p.get("en_curso") else f' fill="{_COLOR_EVOLUCION}"'
        partes.append(
            f'<g><circle cx="{x(i):.1f}" cy="{y(p["posicion"]):.1f}" r="14" fill="transparent"/>'
            f'<circle cx="{x(i):.1f}" cy="{y(p["posicion"]):.1f}" r="4.5" stroke="{_COLOR_EVOLUCION}"{relleno}{hueco}/>'
            f'<title>{_esc(p["etiqueta"])}: puesto {p["posicion"]}</title></g>')
        if i in etiquetados:
            partes.append(f'<text x="{x(i):.1f}" y="{y(p["posicion"]) - 10:.1f}" font-size="12" font-weight="700" '
                          f'text-anchor="middle" fill="currentColor">{p["posicion"]}º</text>')
    partes.append("</svg>")
    return _una_linea("".join(partes))


def evolucion_tabla_html(puntos: List[Dict]) -> str:
    """Los mismos datos de la gráfica en forma de tabla (con el cambio respecto al punto anterior)."""
    filas = []
    for i, p in enumerate(puntos):
        if i == 0:
            cambio = "—"
        else:
            d = puntos[i - 1]["posicion"] - p["posicion"]
            cambio = f"⬆️ +{d}" if d > 0 else (f"⬇️ {d}" if d < 0 else "＝ igual")
        filas.append(f'<tr><td class="izq">{_esc(p["etiqueta"])}</td><td>{p["posicion"]}º</td><td>{cambio}</td></tr>')
    return _una_linea('<div class="t-scroll"><table class="t-tabla"><thead><tr><th class="izq">Momento</th><th>Puesto</th>'
                      f'<th>Cambio</th></tr></thead><tbody>{"".join(filas)}</tbody></table></div>')

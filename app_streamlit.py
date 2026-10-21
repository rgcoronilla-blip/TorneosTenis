"""
Interfaz gráfica (Streamlit) para sortear, gestionar y consultar torneos de tenis.

Acceso:
  - Administrador (con contraseña): hace sorteos y gestiona torneos.
  - Invitado (por defecto, sin contraseña): solo consulta torneos y resultados.

Secciones del administrador:
  1. Nuevo torneo      -> sorteo según ranking o emparejamientos cargados desde un CSV (sin sorteo),
                          y alta del torneo (código, nombre, fechas).
  2. Gestionar torneo  -> anotar resultados y fijar el día y la hora previstos de cada partido;
                          los ganadores avanzan solos de ronda y,
                          en fase de grupos, los clasificados pasan solos al cuadro.
  3. Consultar torneos -> búsqueda por código, nombre y fechas de inicio/fin.
Secciones del invitado:
  1. Consultar torneos -> la misma búsqueda.
  2. Ver torneo        -> grupos, cuadro y resultados en solo lectura.

Ejecutar con:
    pip install -r requirements.txt
    streamlit run app_streamlit.py
"""

from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import cuadro_visual
import anuncios
import emparejamientos
import estilo
import ranking as rk
import torneo as db
import whatsapp
from whatsapp import normalizar_telefono
from sorteo_torneo_tenis import (
    FaseDeGruposYEliminatorias,
    Jugador,
    SorteoTorneo,
    calcular_tamanos_grupos,
    etiqueta_jugador,
    nombres_de_rondas,
    plan_eliminatorias,
)

st.set_page_config(page_title="Torneos de Tenis", page_icon="🎾", layout="wide")

SECCIONES_ADMIN = ["Nuevo torneo", "Gestionar torneo", "Consultar torneos", "Ranking continuo", "Tablón de anuncios"]
SECCIONES_INVITADO = ["Consultar torneos", "Ver torneo", "Ranking continuo", "Tablón de anuncios"]

CLUB_NOMBRE = "Club Nazaret"
CLUB_LOCALIDAD = "Jerez de la Frontera"
# El escudo se carga de un fichero de imagen que se guarda junto a este archivo.
CARPETA_APP = Path(__file__).resolve().parent
EXTENSIONES_ESCUDO = (".png", ".jpg", ".jpeg", ".webp")
TIPOS = {"eliminatorias": "Eliminatorias directas", "grupos": "Fase de grupos + eliminatorias"}
MODOS = {"sorteo": "Sorteo según el ranking", "csv": "Emparejamientos desde un CSV (sin sorteo)"}
FORMATOS_SETS = {"Al mejor de 3 sets": 2, "Al mejor de 5 sets": 3, "Un solo set": 1}

JUGADORES_EJEMPLO = pd.DataFrame(
    [
        {"nombre": "Carlos Alcaraz", "ranking": 1},
        {"nombre": "Jannik Sinner", "ranking": 2},
        {"nombre": "Novak Djokovic", "ranking": 3},
        {"nombre": "Alexander Zverev", "ranking": 4},
        {"nombre": "Daniil Medvedev", "ranking": 5},
        {"nombre": "Andrey Rublev", "ranking": 6},
        {"nombre": "Casper Ruud", "ranking": 7},
        {"nombre": "Hubert Hurkacz", "ranking": 8},
        {"nombre": "Grigor Dimitrov", "ranking": 9},
        {"nombre": "Stefanos Tsitsipas", "ranking": 10},
        {"nombre": "Taylor Fritz", "ranking": 11},
        {"nombre": "Tommy Paul", "ranking": 12},
    ]
)
JUGADORES_EJEMPLO["telefono"] = ""  # opcional, para los avisos por WhatsApp


def init_estado():
    ss = st.session_state
    ss.setdefault("rol", "invitado")  # se entra como invitado hasta identificarse
    ss.setdefault("seccion", SECCIONES_INVITADO[0])
    ss.setdefault("jugadores_base", JUGADORES_EJEMPLO.copy())
    ss.setdefault("editor_version", 0)
    ss.setdefault("pendiente", None)  # sorteo realizado pero aún sin guardar como torneo
    ss.setdefault("torneo_activo", None)
    ss.setdefault("csv_firma", None)


def es_admin() -> bool:
    return st.session_state.get("rol") == "admin"


def secciones() -> list:
    return SECCIONES_ADMIN if es_admin() else SECCIONES_INVITADO


def exigir_admin():
    """Corta la ejecución si quien llega a una pantalla de administración no lo es."""
    if not es_admin():
        st.error("Esta sección es solo para el administrador.")
        st.stop()


def ruta_escudo():
    """Ruta de escudo_club.(png|jpg|jpeg|webp) junto a la app, o None si no está."""
    for extension in EXTENSIONES_ESCUDO:
        ruta = CARPETA_APP / f"escudo_club{extension}"
        if ruta.is_file():
            return ruta
    return None


def cabecera_club():
    """Parte superior del panel: banner con el escudo y el nombre del club (visible para todos)."""
    ruta = ruta_escudo()
    st.markdown(estilo.cabecera_html(CLUB_NOMBRE, f"{CLUB_LOCALIDAD} · Torneos de tenis", ruta),
                unsafe_allow_html=True)
    if ruta is None and es_admin():
        st.caption("Para mostrar el escudo, guarda la imagen como «escudo_club.png» (o .jpg / .webp) "
                   "en la misma carpeta que app_streamlit.py.")


def fmt_fecha(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def fmt_fecha_hora(iso: str) -> str:
    """«2026-06-02T18:30» -> «mar 02/06/2026 · 18:30»."""
    d = datetime.fromisoformat(iso)
    return f"{DIAS_SEMANA[d.weekday()]} {d:%d/%m/%Y} · {d:%H:%M}"


def mostrar_flash():
    flash = st.session_state.pop("flash", None)
    if flash:
        nivel, mensaje = flash
        {"success": st.success, "warning": st.warning}.get(nivel, st.error)(mensaje)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def cargar_ejemplo():
    if not es_admin():
        return
    ss = st.session_state
    ss.jugadores_base = JUGADORES_EJEMPLO.copy()
    ss.editor_version += 1
    ss.pendiente = None


def crear_torneo_cb():
    ss = st.session_state
    if not es_admin():
        ss.flash = ("error", "Acción reservada al administrador.")
        return
    pend = ss.pendiente
    if not pend:
        return
    try:
        codigo = db.crear_torneo(
            codigo=ss.nuevo_codigo,
            nombre=ss.nuevo_nombre,
            fecha_inicio=ss.nuevo_inicio,
            fecha_fin=ss.nuevo_fin,
            tipo=pend["tipo"],
            sets_ganar=FORMATOS_SETS[ss.nuevo_formato],
            jugadores=pend["jugadores"],
            sorteo=pend["obj"],
            visible=bool(ss.get("nuevo_visible", True)),
        )
    except ValueError as e:
        ss.flash = ("error", str(e))
        return
    ss.flash = ("success", f"Torneo {codigo} generado. Ya puedes anotar los resultados.")
    ss.pendiente = None
    ss.torneo_activo = codigo
    ss.seccion = "Gestionar torneo"


def cambiar_visibilidad(codigo: str, visible: bool):
    ss = st.session_state
    if not es_admin():
        ss.flash = ("error", "Acción reservada al administrador.")
        return
    try:
        db.establecer_visibilidad(codigo, visible)
    except ValueError as e:
        ss.flash = ("error", str(e))
        return
    ss.flash = ("success", "El torneo ya es visible para los invitados." if visible
                else "El torneo queda oculto: los invitados no pueden consultarlo.")


def abrir_torneo(codigo: str):
    st.session_state.torneo_activo = codigo
    st.session_state.seccion = "Gestionar torneo" if es_admin() else "Ver torneo"


def cerrar_sesion():
    ss = st.session_state
    ss.rol = "invitado"
    ss.seccion = SECCIONES_INVITADO[0]
    ss.pendiente = None  # un sorteo sin guardar no debe quedar a la vista del invitado
    ss.pop("flash", None)


# ---------------------------------------------------------------------------
# Componentes de dibujo
# ---------------------------------------------------------------------------

def render_bracket(cuadro, draw_size, rondas):
    """Cuadro completo del sorteo (todavía sin guardar), dibujado como árbol."""
    st.markdown(cuadro_visual.html_cuadro_sorteo(cuadro, draw_size), unsafe_allow_html=True)
    st.caption("Estructura del torneo: " + " → ".join(rondas))


def texto_bracket(cuadro, draw_size):
    return "\n".join(
        f"Partido {i // 2 + 1}: "
        f"{('BYE' if cuadro[i] in (None, 'BYE') else cuadro[i])} vs "
        f"{('BYE' if cuadro[i + 1] in (None, 'BYE') else cuadro[i + 1])}"
        for i in range(0, draw_size, 2)
    )


def render_sorteo(tipo, obj):
    """Vista previa del sorteo realizado (todavía sin guardar)."""
    if tipo == "eliminatorias":
        c1, c2, c3 = st.columns(3)
        c1.metric("Plazas del cuadro", obj.draw_size)
        if getattr(obj, "manual", False):
            c2.metric("Jugadores", len(obj.jugadores))
        else:
            c2.metric("Cabezas de serie", obj.num_seeds)
        c3.metric("Byes", obj.byes)
        render_bracket(obj.cuadro, obj.draw_size, obj.nombre_rondas())
        texto = texto_bracket(obj.cuadro, obj.draw_size)
    else:
        letras = [chr(65 + i) for i in range(len(obj.grupos))]
        c1, c2, c3 = st.columns(3)
        c1.metric("Nº de grupos", len(obj.grupos))
        c2.metric("Plazas cuadro principal", obj.draw_size)
        c3.metric("Plazas consolación", obj.draw_size_consolacion or "—")
        if getattr(obj, "bombos", None):
            st.markdown("**Bombos** (por ranking; cada grupo lleva un jugador de cada bombo)")
            st.markdown(estilo.bombos_html(obj.bombos), unsafe_allow_html=True)
        st.markdown("**Fase de grupos**")
        st.markdown(estilo.grupos_html(obj.grupos), unsafe_allow_html=True)
        st.divider()
        st.markdown("**Cuadro principal** (clasifican el 1º y 2º de cada grupo)")
        render_bracket(obj.cuadro, obj.draw_size, obj.nombre_rondas())
        if obj.cuadro_consolacion:
            st.markdown("**Cuadro consolación** (el 3º de cada grupo y el 4º de los grupos de 4)")
            render_bracket(obj.cuadro_consolacion, obj.draw_size_consolacion, obj.nombre_rondas_consolacion())
        else:
            st.caption("Con un solo grupo de 3 jugadores no hay cuadro de consolación.")
        texto = (
            "\n\n".join(
                f"Grupo {letra}:\n" + "\n".join(f"  - {j}" for j in grupo)
                for letra, grupo in zip(letras, obj.grupos)
            )
            + "\n\nCUADRO PRINCIPAL (1º y 2º de cada grupo)\n"
            + texto_bracket(obj.cuadro, obj.draw_size)
            + ("\n\nCUADRO CONSOLACIÓN (3º de cada grupo y 4º de los grupos de 4)\n"
               + texto_bracket(obj.cuadro_consolacion, obj.draw_size_consolacion)
               if obj.cuadro_consolacion else "")
        )
    st.download_button("⬇️ Descargar sorteo (.txt)", texto, file_name="sorteo_torneo.txt")


# ---------------------------------------------------------------------------
# Sección 1: Nuevo torneo
# ---------------------------------------------------------------------------

def _bloque_sorteo(tipo):
    """Jugadores con su ranking y sorteo automático del cuadro."""
    ss = st.session_state
    with st.expander("Cargar jugadores desde un CSV (columnas: jugador;ranking)"):
        st.markdown(emparejamientos.AYUDA_JUGADORES)
        st.download_button("⬇️ Descargar plantilla CSV", emparejamientos.plantilla_jugadores(),
                           file_name="plantilla_jugadores.csv", mime="text/csv")
        archivo = st.file_uploader("Fichero CSV", type="csv")
        if archivo is not None:
            firma = (archivo.name, archivo.size)
            if ss.csv_firma != firma:  # se procesa una sola vez por fichero
                try:
                    cargados = emparejamientos.leer_jugadores(archivo.getvalue())
                except emparejamientos.ErrorCSV as e:
                    st.error("No se han podido cargar los jugadores:\n\n" + emparejamientos.resumen_errores(e))
                else:
                    ss.jugadores_base = pd.DataFrame(
                        {"nombre": [j.nombre for j in cargados], "ranking": [j.ranking for j in cargados],
                         "telefono": [j.telefono for j in cargados]})
                    ss.editor_version += 1
                    ss.pendiente = None
                    ss.csv_firma = firma
                    ss.flash = ("success", f"{len(cargados)} jugadores cargados desde el CSV.")
                    st.rerun()
        st.button("↺ Volver a la lista de ejemplo", on_click=cargar_ejemplo)

    df_edit = st.data_editor(
        ss.jugadores_base,
        num_rows="dynamic",
        column_config={
            "nombre": st.column_config.TextColumn("Jugador", required=True),
            "ranking": st.column_config.NumberColumn("Ranking", min_value=1, step=1, required=True),
            "telefono": st.column_config.TextColumn(
                "Teléfono (opcional)", help="Para avisar por WhatsApp. Solo lo ve el administrador."),
        },
        key=f"editor_{ss.editor_version}",
    )
    df = df_edit.dropna(subset=["nombre", "ranking"])
    df = df[df["nombre"].astype(str).str.strip() != ""]
    n = len(df)

    if n >= 2 and tipo == "eliminatorias":
        draw_size, seeds, byes = plan_eliminatorias(n)
        st.caption(f"Con {n} jugadores → cuadro de {draw_size} plazas, {seeds} cabezas de serie, {byes} byes.")
    elif n >= 1 and tipo == "grupos":
        try:
            tamanos = calcular_tamanos_grupos(n)
            st.caption(f"Con {n} jugadores → {len(tamanos)} grupo(s) de {', '.join(str(t) for t in tamanos)} "
                       f"jugadores.")
        except ValueError as err:
            st.warning(str(err))

    semilla = None
    por_bombos = False
    if tipo == "grupos":
        por_bombos = st.checkbox(
            "Formar bombos por ranking (cada grupo lleva un jugador de cada bombo)", value=False,
            help="Se forman 4 bombos ordenados por ranking: el primero con los mejores jugadores, el segundo "
                 "con los siguientes, etc. Cada grupo se forma sacando un jugador de cada bombo. Sin esta "
                 "opción los grupos se reparten en serpiente (1-2-3-4 / 4-3-2-1…).")
    if tipo == "eliminatorias" or por_bombos:
        usar_semilla = st.checkbox("Semilla fija (sorteo reproducible)", value=False)
        if usar_semilla:
            semilla = int(st.number_input("Semilla", min_value=0, value=42, step=1))

    if st.button("🎲 Realizar sorteo", type="primary"):
        minimo = 3 if tipo == "grupos" else 2
        if n < minimo:
            st.error(f"Se necesitan al menos {minimo} jugadores para este tipo de campeonato.")
        elif tipo == "grupos" and n == 5:
            st.error("Con 5 jugadores no se pueden formar grupos de 4 ni de 3.")
        elif df["nombre"].astype(str).str.strip().duplicated().any():
            st.error("Hay nombres de jugador repetidos; corrígelos antes de sortear.")
        else:
            try:
                jugadores = [Jugador(str(r.nombre).strip(), int(r.ranking),
                                     normalizar_telefono(getattr(r, "telefono", "")))
                             for r in df.itertuples()]
            except ValueError as err:
                st.error(f"{err} Corrígelo en la tabla de jugadores antes de sortear.")
                return
            if tipo == "eliminatorias":
                obj = SorteoTorneo(jugadores, seed=semilla)
            else:
                obj = FaseDeGruposYEliminatorias(jugadores, por_bombos=por_bombos, seed=semilla)
            obj.generar()
            ss.pendiente = {"tipo": tipo, "jugadores": jugadores, "obj": obj, "origen": "sorteo"}


def _bloque_csv(tipo):
    """Emparejamientos ya decididos, cargados desde un CSV con el formato del tipo de campeonato."""
    ss = st.session_state
    st.markdown(emparejamientos.AYUDA[tipo])
    st.download_button("⬇️ Descargar plantilla CSV", emparejamientos.plantilla(tipo),
                       file_name=emparejamientos.nombre_plantilla(tipo), mime="text/csv")
    archivo = st.file_uploader("Fichero de emparejamientos (CSV)", type="csv", key=f"emparejamientos_{tipo}")
    if st.button("📥 Cargar emparejamientos", type="primary"):
        if archivo is None:
            st.error("Selecciona primero un fichero CSV.")
            return
        try:
            obj = emparejamientos.cargar(tipo, archivo.getvalue())
        except emparejamientos.ErrorCSV as e:
            ss.pendiente = None  # no se deja a la vista un cuadro anterior que no corresponde a este fichero
            st.error("No se han podido cargar los emparejamientos:\n\n" + emparejamientos.resumen_errores(e))
            return
        obj.generar()
        ss.pendiente = {"tipo": tipo, "jugadores": obj.jugadores, "obj": obj, "origen": "csv"}


def pagina_nuevo():
    exigir_admin()
    ss = st.session_state
    st.header("Nuevo torneo")
    mostrar_flash()

    st.subheader("1. Tipo de campeonato y origen del cuadro")
    tipo = st.radio(
        "Tipo de campeonato",
        options=list(TIPOS),
        format_func=TIPOS.get,
        horizontal=True,
    )
    if tipo == "eliminatorias":
        st.caption("Partidos de eliminatoria: el perdedor queda eliminado del torneo.")
    else:
        st.caption(
            "Grupos de 4 jugadores (o de 3 si no se puede formar con grupos de 4). Al terminar los grupos "
            "se juegan dos cuadros de eliminatorias: el principal (1º y 2º de cada grupo) y el de "
            "consolación (3º de cada grupo y 4º de los grupos de 4)."
        )

    modo = st.radio("Cómo quieres crear el cuadro", options=list(MODOS), format_func=MODOS.get, horizontal=True)
    if modo == "sorteo":
        _bloque_sorteo(tipo)
    else:
        _bloque_csv(tipo)

    pend = ss.pendiente
    if pend:
        st.divider()
        titulo = "Emparejamientos cargados" if pend.get("origen") == "csv" else "Resultado del sorteo"
        st.subheader(f"2. {titulo} — {TIPOS[pend['tipo']]}")
        render_sorteo(pend["tipo"], pend["obj"])

        st.divider()
        st.subheader("3. Generar el torneo")
        st.caption("Guarda el torneo con todos sus partidos para poder anotar los resultados.")
        c1, c2 = st.columns([1, 2])
        c1.text_input("Código", value=db.sugerir_codigo(date.today().year), key="nuevo_codigo",
                      help="Letras, números, guiones y guiones bajos. Debe ser único.")
        c2.text_input("Nombre del torneo", key="nuevo_nombre", placeholder="Ej.: Open de Jerez 2026")
        d1, d2, d3 = st.columns(3)
        d1.date_input("Fecha de inicio", value=date.today(), key="nuevo_inicio", format="DD/MM/YYYY")
        d2.date_input("Fecha de fin", value=date.today(), key="nuevo_fin", format="DD/MM/YYYY")
        d3.selectbox("Formato de partido", list(FORMATOS_SETS), key="nuevo_formato")
        st.checkbox("Visible para los invitados", value=True, key="nuevo_visible",
                    help="Desmárcalo para hacer pruebas: los invitados no verán el torneo hasta que lo "
                         "hagas visible en «Gestionar torneo».")
        st.button("✅ Generar torneo", type="primary", on_click=crear_torneo_cb)


# ---------------------------------------------------------------------------
# Sección 2: Gestionar torneo
# ---------------------------------------------------------------------------

def lado(p, k):
    nombre = p[f"nombre{k}"]
    if nombre:
        texto = etiqueta_jugador(nombre, p[f"ranking{k}"])
        return f"**{texto}**" if p["ganador"] == p[f"jugador{k}"] and p["estado"] == "jugado" else texto
    origen = p[f"origen{k}"]
    return f"*{origen}*" if origen else "*por determinar*"


def formulario_resultado(p, sets_ganar):
    ss = st.session_state
    pid = p["id"]
    jugado = p["estado"] == "jugado"
    with st.expander("Editar resultado" if jugado else "Anotar resultado", expanded=not jugado):
        with st.form(f"form_{pid}"):
            a, b, c = st.columns([1, 1, 3])
            s1 = a.number_input(f"Sets {p['nombre1']}", min_value=0, max_value=sets_ganar,
                                value=int(p["sets1"] or 0), step=1, key=f"s1_{pid}")
            s2 = b.number_input(f"Sets {p['nombre2']}", min_value=0, max_value=sets_ganar,
                                value=int(p["sets2"] or 0), step=1, key=f"s2_{pid}")
            marcador = c.text_input("Marcador (opcional)", value=p["marcador"] or "",
                                    placeholder="6-4 3-6 7-5", key=f"m_{pid}")
            d, e = st.columns(2)
            j1 = d.number_input(f"Juegos totales {p['nombre1']}", min_value=0, max_value=99,
                                value=int(p["juegos1"] or 0), step=1, key=f"j1_{pid}",
                                help="Suma de los juegos ganados en todos los sets.")
            j2 = e.number_input(f"Juegos totales {p['nombre2']}", min_value=0, max_value=99,
                                value=int(p["juegos2"] or 0), step=1, key=f"j2_{pid}",
                                help="Suma de los juegos ganados en todos los sets.")
            g, h, i = st.columns(3)
            guardar = g.form_submit_button("Guardar resultado", type="primary")
            anular = h.form_submit_button("Anular resultado") if jugado else False
            sin_jugar = (i.form_submit_button("No se jugó (0 puntos)")
                         if p["fase"] == "grupo" and not p["sin_jugar"] else False)
    if guardar or anular or sin_jugar:
        if not es_admin():
            st.error("Acción reservada al administrador.")
            return
        try:
            if guardar:
                db.registrar_resultado(pid, s1, s2, marcador, j1, j2)
            elif sin_jugar:
                db.marcar_no_jugado(pid)
            else:
                db.anular_resultado(pid)
        except ValueError as e:
            st.error(str(e))
        else:
            ss.flash = ("success", "Resultado guardado." if guardar else
                        "Partido marcado como no jugado: 0 puntos para ambos jugadores." if sin_jugar
                        else "Resultado anulado.")
            st.rerun()


def formulario_horario(p, t):
    """Día y hora previstos del partido (solo administrador)."""
    ss = st.session_state
    pid = p["id"]
    actual = datetime.fromisoformat(p["fecha_hora"]) if p["fecha_hora"] else None
    inicio, fin = date.fromisoformat(t["fecha_inicio"]), date.fromisoformat(t["fecha_fin"])
    dia_defecto = actual.date() if actual else min(max(date.today(), inicio), fin)
    hora_defecto = actual.time() if actual else time(10, 0)
    with st.expander("Cambiar día y hora" if actual else "Programar día y hora"):
        with st.form(f"form_horario_{pid}"):
            a, b = st.columns(2)
            dia = a.date_input("Día", value=dia_defecto, key=f"dia_{pid}", format="DD/MM/YYYY")
            hora = b.time_input("Hora", value=hora_defecto, step=900, key=f"hora_{pid}")
            g, h = st.columns(2)
            guardar = g.form_submit_button("Guardar día y hora", type="primary")
            quitar = h.form_submit_button("Quitar programación") if actual else False
    if guardar or quitar:
        if not es_admin():
            st.error("Acción reservada al administrador.")
            return
        try:
            db.programar_partido(pid, datetime.combine(dia, hora) if guardar else None)
        except ValueError as e:
            st.error(str(e))
            return
        if guardar and not (inicio <= dia <= fin):
            ss.flash = ("warning", f"Día y hora guardados, pero el {dia:%d/%m/%Y} queda fuera de las fechas "
                                   f"del torneo ({inicio:%d/%m/%Y} – {fin:%d/%m/%Y}).")
        else:
            ss.flash = ("success", "Día y hora guardados." if guardar else "Programación quitada.")
        st.rerun()


def avisos_whatsapp(p, t, telefonos):
    """Enlaces wa.me para avisar a cada jugador de su partido (solo administrador)."""
    if not es_admin() or p["estado"] != "pendiente" or p["jugador1"] is None or p["jugador2"] is None:
        return
    lados = ((p["jugador1"], p["nombre1"], p["nombre2"]), (p["jugador2"], p["nombre2"], p["nombre1"]))
    columnas = st.columns(2)
    for col, (jid, nombre, rival) in zip(columnas, lados):
        tel = telefonos.get(jid)
        if not tel:
            col.caption(f"📵 {nombre}: sin teléfono")
            continue
        texto = whatsapp.mensaje_partido(t["nombre"], p, nombre, rival, CLUB_NOMBRE)
        col.link_button(f"📲 Avisar a {nombre}", whatsapp.enlace_whatsapp(tel, texto),
                        help="Abre WhatsApp con el mensaje ya escrito; tú pulsas «Enviar».")


def render_partido(p, t, editable=True, telefonos=None):
    with st.container(border=True):
        st.markdown(cuadro_visual.tarjeta_html(p, con_meta=False), unsafe_allow_html=True)
        if p["estado"] == "bye":
            st.caption(f"BYE: pasa directamente {p['nombre_ganador']}.")
            return
        if "BYE" in (p["origen1"], p["origen2"]):
            st.caption("BYE: pasará directamente cuando se conozca al clasificado.")
            return
        # día y hora previstos: los ven todos los usuarios
        if p["fecha_hora"]:
            st.caption(f"📅 Previsto: {fmt_fecha_hora(p['fecha_hora'])}")
        elif p["estado"] == "pendiente":
            st.caption("📅 Día y hora por confirmar.")
        if p["jugador1"] is None or p["jugador2"] is None:
            st.caption("Pendiente: aún no se conocen los dos jugadores.")
        else:
            if p["estado"] == "jugado" and p["sin_jugar"]:
                st.markdown("⛔ **Partido no jugado** — 0 puntos para ambos jugadores.")
            elif p["estado"] == "jugado":
                resultado = f"{p['sets1']}-{p['sets2']} en sets"
                if p["juegos1"] is not None:
                    resultado += f", {p['juegos1']}-{p['juegos2']} en juegos"
                if p["marcador"]:
                    resultado += f" ({p['marcador']})"
                puntos = " · 2 puntos para el ganador y 1 para el perdedor" if p["fase"] == "grupo" else ""
                st.markdown(f"✅ Ganador: **{p['nombre_ganador']}** — {resultado}{puntos}")
            elif not editable:
                st.caption("Pendiente de jugar.")
            if editable:
                formulario_resultado(p, t["sets_ganar"])
        if editable:
            formulario_horario(p, t)
            if telefonos is not None:
                avisos_whatsapp(p, t, telefonos)


def vista_grupos(codigo, t, partidos, editable=True, telefonos=None):
    clasif = db.clasificaciones(codigo)
    letras = sorted(clasif)
    hay_cons = any(p["cuadro"] == "consolacion" for p in partidos)
    st.caption(
        "Puntos: 2 por partido ganado, 1 por partido perdido y 0 si el partido no se juega. "
        "Clasificación: puntos; en caso de empate, diferencia de sets, diferencia de juegos y ranking "
        "(no se tiene en cuenta quién ganó el enfrentamiento directo). "
        "PJ=jugados, PG=ganados, PP=perdidos, NJ=no jugados, SF/SC=sets a favor/en contra, "
        "DS=diferencia de sets, JF/JC=juegos a favor/en contra, DJ=diferencia de juegos."
    )
    for tab, letra in zip(st.tabs([f"Grupo {l}" for l in letras]), letras):
        with tab:
            info = clasif[letra]
            st.markdown(estilo.clasificacion_html(info["tabla"], info["completo"], hay_cons),
                        unsafe_allow_html=True)
            if info["completo"]:
                st.success("Grupo completado: el 1º y el 2º ya están en el cuadro principal y "
                           + ("el 3º y el 4º en el de consolación." if len(info["tabla"]) == 4
                              else "el 3º en el de consolación."))
            delgrupo = [p for p in partidos if p["fase"] == "grupo" and p["grupo"] == letra]
            for jornada in sorted({p["ronda"] for p in delgrupo}):
                st.markdown(f"**Jornada {jornada}**")
                for p in (x for x in delgrupo if x["ronda"] == jornada):
                    render_partido(p, t, editable, telefonos)


def vista_eliminatorias(t, partidos, editable=True, cuadro="principal", telefonos=None):
    elim = [p for p in partidos if p["fase"] == "eliminatoria" and (p["cuadro"] or "principal") == cuadro]
    rondas = sorted({p["ronda"] for p in elim})
    nombres = nombres_de_rondas(2 ** len(rondas))
    final = next((p for p in elim if p["ronda"] == rondas[-1]), None)
    ganador = final["nombre_ganador"] if final and final["estado"] == "jugado" else None
    with st.expander("🎾 Ver el cuadro completo", expanded=True):
        st.markdown(
            cuadro_visual.html_cuadro(elim, campeon=ganador,
                                      etiqueta_campeon="Campeón" if cuadro == "principal" else "Ganador consolación"),
            unsafe_allow_html=True)
    st.markdown("**Partidos por ronda**" + (" — anota aquí los resultados" if editable else ""))
    for tab, r in zip(st.tabs([nombres[r - 1] for r in rondas]), rondas):
        with tab:
            for p in (x for x in elim if x["ronda"] == r):
                render_partido(p, t, editable, telefonos)


def panel_telefonos(codigo):
    """Alta y corrección de los teléfonos de los jugadores (solo administrador)."""
    if not es_admin():
        return
    jugadores = db.jugadores_de(codigo)
    actuales = db.telefonos_de(codigo)
    sin = sum(1 for j in jugadores if j["id"] not in actuales)
    with st.expander(f"📱 Teléfonos para avisos por WhatsApp ({len(actuales)}/{len(jugadores)} informados)"):
        st.caption("Solo los ve el administrador. Guárdalos únicamente si el jugador ha dado su consentimiento "
                   "para recibir avisos del club. Formato: 600 123 456 o +34 600 123 456."
                   + (f" Faltan {sin}." if sin else ""))
        with st.form(f"form_telefonos_{codigo}"):
            for j in jugadores:
                st.text_input(j["nombre"], value=actuales.get(j["id"], ""), key=f"tel_{codigo}_{j['id']}")
            guardar = st.form_submit_button("Guardar teléfonos", type="primary")
    if guardar:
        if not es_admin():
            st.error("Acción reservada al administrador.")
            return
        ss = st.session_state
        errores, hechos = [], 0
        for j in jugadores:
            nuevo = ss.get(f"tel_{codigo}_{j['id']}", "")
            try:
                if whatsapp.normalizar_telefono(nuevo) != actuales.get(j["id"], ""):
                    db.establecer_telefono(j["id"], nuevo)
                    hechos += 1
            except ValueError as e:
                errores.append(f"{j['nombre']}: {e}")
        if errores:
            ss.flash = ("error", "No se han guardado algunos teléfonos:\n\n" + "\n\n".join(errores))
        else:
            ss.flash = ("success", f"Teléfonos guardados ({hechos} cambio(s)).")
        st.rerun()


def panel_patrocinadores(codigo):
    """Alta, orden y baja de los patrocinadores del torneo (solo administrador)."""
    if not es_admin():
        return
    ss = st.session_state
    lista = db.patrocinadores_de(codigo)
    with st.expander(f"🤝 Patrocinadores del torneo ({len(lista)}/{db.MAX_PATROCINADORES})"):
        st.caption("Aparecen en un banner en la parte superior del torneo para todos los usuarios. "
                   "Logotipo en PNG, JPG, GIF o WEBP (máx. 800 KB); la web es opcional y debe empezar por https://.")
        for i, p in enumerate(lista):
            c1, c2, c3, c4 = st.columns([5, 1, 1, 1])
            c1.markdown(f"**{p['nombre']}**" + (f" · {p['url']}" if p["url"] else ""))
            if c2.button("⬆️", key=f"sp_up_{p['id']}", disabled=i == 0, help="Subir"):
                _accion_patrocinador(db.mover_patrocinador, p["id"], -1)
            if c3.button("⬇️", key=f"sp_dn_{p['id']}", disabled=i == len(lista) - 1, help="Bajar"):
                _accion_patrocinador(db.mover_patrocinador, p["id"], 1)
            if c4.button("🗑️", key=f"sp_del_{p['id']}", help="Quitar"):
                _accion_patrocinador(db.eliminar_patrocinador, p["id"])
        with st.form(f"form_patrocinador_{codigo}", clear_on_submit=True):
            nombre = st.text_input("Nombre del patrocinador", key=f"sp_nombre_{codigo}", max_chars=80)
            web = st.text_input("Web (opcional)", key=f"sp_url_{codigo}", placeholder="https://…")
            logo = st.file_uploader("Logotipo", type=["png", "jpg", "jpeg", "gif", "webp"], key=f"sp_logo_{codigo}")
            enviar = st.form_submit_button("Añadir patrocinador", type="primary")
    if enviar:
        if not es_admin():
            st.error("Acción reservada al administrador.")
            return
        try:
            db.anadir_patrocinador(codigo, nombre, logo.getvalue() if logo is not None else b"", web)
        except ValueError as e:
            ss.flash = ("error", str(e))
        else:
            ss.flash = ("success", f"Patrocinador «{nombre.strip()}» añadido.")
        st.rerun()


def _accion_patrocinador(fn, *args):
    ss = st.session_state
    if not es_admin():
        ss.flash = ("error", "Acción reservada al administrador.")
    else:
        try:
            fn(*args)
        except ValueError as e:
            ss.flash = ("error", str(e))
    st.rerun()


def pagina_gestionar(editable=True):
    """Detalle del torneo. Con editable=False (invitado) es solo lectura."""
    editable = editable and es_admin()  # nunca se muestran formularios a quien no es admin
    ss = st.session_state
    st.header("Gestionar torneo" if editable else "Resultados del torneo")
    mostrar_flash()

    torneos = db.buscar_torneos(incluir_ocultos=es_admin())
    if not torneos:
        st.info("Todavía no hay torneos. Crea uno en la sección «Nuevo torneo»."
                if editable else "Todavía no hay torneos.")
        return
    nombres = {t["codigo"]: t["nombre"] + ("" if t["visible"] else " 🔒 (no visible)") for t in torneos}
    codigos = list(nombres)
    activo = ss.torneo_activo if ss.torneo_activo in nombres else codigos[0]
    codigo = st.selectbox("Torneo", codigos, index=codigos.index(activo),
                          format_func=lambda c: f"{c} — {nombres[c]}")
    ss.torneo_activo = codigo

    t = db.obtener_torneo(codigo, incluir_ocultos=es_admin())
    if t is None:
        st.info("Este torneo no está disponible.")
        return
    partidos = db.partidos_de(codigo)

    banner = estilo.patrocinadores_html(db.patrocinadores_de(codigo))
    if banner:
        st.markdown(banner, unsafe_allow_html=True)
    st.subheader(t["nombre"])
    mostrar_anuncios("torneo", codigo, "📌 Anuncios del torneo")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Código", t["codigo"])
    c2.metric("Inicio", fmt_fecha(t["fecha_inicio"]))
    c3.metric("Fin", fmt_fecha(t["fecha_fin"]))
    c4.metric("Estado", t["estado"].capitalize())
    st.caption(
        f"{TIPOS[t['tipo']]} · {t['num_jugadores']} jugadores · "
        f"gana quien llegue a {t['sets_ganar']} set(s)"
    )
    if t["campeon"]:
        st.success(f"🏆 Campeón: {t['campeon']}")
    if editable:
        if t["visible"]:
            st.button("🔒 Ocultar a los invitados", on_click=cambiar_visibilidad, args=(codigo, False),
                      help="Los invitados dejarán de ver este torneo (útil para pruebas).")
        else:
            st.warning("🔒 Este torneo no es visible para los invitados.")
            st.button("👁️ Hacer visible para los invitados", on_click=cambiar_visibilidad,
                      args=(codigo, True), type="primary")

    # Los teléfonos solo se consultan para el administrador: los invitados nunca los reciben.
    telefonos = db.telefonos_de(codigo) if editable and es_admin() else None
    if telefonos is not None:
        panel_patrocinadores(codigo)
        panel_telefonos(codigo)

    if t["tipo"] == "grupos":
        hay_consolacion = any(p["cuadro"] == "consolacion" for p in partidos)
        titulos = ["Fase de grupos", "Cuadro principal"] + (["Cuadro consolación"] if hay_consolacion else [])
        pestanas = st.tabs(titulos)
        with pestanas[0]:
            vista_grupos(codigo, t, partidos, editable, telefonos)
        with pestanas[1]:
            vista_eliminatorias(t, partidos, editable, "principal", telefonos)
        if hay_consolacion:
            with pestanas[2]:
                vista_eliminatorias(t, partidos, editable, "consolacion", telefonos)
    else:
        vista_eliminatorias(t, partidos, editable, telefonos=telefonos)


# ---------------------------------------------------------------------------
# Sección 3: Consultar torneos
# ---------------------------------------------------------------------------

def _rango(valor):
    if isinstance(valor, (tuple, list)) and len(valor) == 2:
        return valor[0], valor[1]
    return None


def pagina_consultar():
    st.header("Consultar torneos")
    mostrar_flash()
    if not es_admin():
        st.caption("Estás como invitado: puedes consultar los torneos y sus resultados.")

    c1, c2 = st.columns(2)
    codigo = c1.text_input("Código (o parte)")
    nombre = c2.text_input("Nombre (o parte)")

    anio = date.today().year
    rango_defecto = (date(anio, 1, 1), date(anio, 12, 31))
    f1, f2 = st.columns(2)
    usar_ini = f1.checkbox("Filtrar por fecha de inicio")
    rango_ini = f1.date_input("Inicio entre", value=rango_defecto, key="f_ini",
                              disabled=not usar_ini, format="DD/MM/YYYY")
    usar_fin = f2.checkbox("Filtrar por fecha de fin")
    rango_fin = f2.date_input("Fin entre", value=rango_defecto, key="f_fin",
                              disabled=not usar_fin, format="DD/MM/YYYY")

    resultados = db.buscar_torneos(
        codigo=codigo,
        nombre=nombre,
        inicio=_rango(rango_ini) if usar_ini else None,
        fin=_rango(rango_fin) if usar_fin else None,
        incluir_ocultos=es_admin(),
    )
    st.caption(f"{len(resultados)} torneo(s) encontrado(s).")
    if not resultados:
        return

    st.markdown(estilo.torneos_html(resultados, TIPOS, fmt_fecha, admin=es_admin()), unsafe_allow_html=True)

    nombres = {t["codigo"]: t["nombre"] + ("" if t["visible"] else " 🔒") for t in resultados}
    elegido = st.selectbox("Abrir torneo", list(nombres), format_func=lambda c: f"{c} — {nombres[c]}")
    st.button("Abrir en «Gestionar torneo»" if es_admin() else "Ver resultados del torneo",
              on_click=abrir_torneo, args=(elegido,))


# ---------------------------------------------------------------------------
# Acceso (barra lateral)
# ---------------------------------------------------------------------------

def _entrar_como_admin():
    st.session_state.rol = "admin"
    st.session_state.seccion = SECCIONES_ADMIN[0]
    st.rerun()


def sidebar_acceso():
    with st.sidebar:
        st.title("🎾 Torneos de tenis")
        if es_admin():
            st.success(f"Sesión: {auth.USUARIO_ADMIN}")
            st.button("Cerrar sesión", on_click=cerrar_sesion)
            with st.expander("Cambiar contraseña"):
                with st.form("form_cambiar_password", clear_on_submit=True):
                    actual = st.text_input("Contraseña actual", type="password")
                    nueva = st.text_input("Nueva contraseña", type="password")
                    repetida = st.text_input("Repite la nueva contraseña", type="password")
                    cambiar = st.form_submit_button("Cambiar contraseña")
                if cambiar:
                    if nueva != repetida:
                        st.error("Las contraseñas nuevas no coinciden.")
                    else:
                        r = auth.cambiar_password(actual, nueva)
                        if r.ok:
                            st.success("Contraseña cambiada.")
                        else:
                            st.error(r.mensaje)
        else:
            st.info("Sesión: Invitado (solo consulta)")
            if not auth.hay_admin():
                with st.expander("Configurar administrador", expanded=True):
                    st.caption(
                        f"Todavía no hay administrador. Define la contraseña de «{auth.USUARIO_ADMIN}» "
                        f"(mínimo {auth.MIN_LONGITUD} caracteres)."
                    )
                    with st.form("form_alta_admin"):
                        nueva = st.text_input("Contraseña", type="password")
                        repetida = st.text_input("Repite la contraseña", type="password")
                        crear = st.form_submit_button("Crear administrador y entrar")
                    if crear:
                        if nueva != repetida:
                            st.error("Las contraseñas no coinciden.")
                        else:
                            try:
                                auth.crear_admin(nueva)
                            except ValueError as e:
                                st.error(str(e))
                            else:
                                _entrar_como_admin()
            else:
                with st.expander("Acceso de administrador"):
                    with st.form("form_login", clear_on_submit=True):
                        st.text_input("Usuario", value=auth.USUARIO_ADMIN, disabled=True)
                        password = st.text_input("Contraseña", type="password")
                        entrar = st.form_submit_button("Entrar")
                    if entrar:
                        r = auth.verificar_admin(password)
                        if r.ok:
                            _entrar_como_admin()
                        else:
                            st.error(r.mensaje)

        st.radio("Sección", secciones(), key="seccion")
        if es_admin():
            st.caption(f"Base de datos: {db.DB_PATH}")


# ---------------------------------------------------------------------------
# Sección 4: Ranking continuo
# ---------------------------------------------------------------------------

def _accion_ranking(fn, *args, ok="Hecho.", **kwargs):
    """Ejecuta una acción de administrador sobre el ranking y deja el aviso para el siguiente repintado."""
    ss = st.session_state
    if not es_admin():
        ss.flash = ("error", "Acción reservada al administrador.")
    else:
        try:
            fn(*args, **kwargs)
            ss.flash = ("success", ok)
        except ValueError as e:
            ss.flash = ("error", str(e))
    st.rerun()


def formulario_ranking_partido(p):
    """Resultado de un partido del ranking (solo administrador)."""
    pid = p["id"]
    jugado = p["estado"] == "jugado"
    with st.expander("Editar resultado" if jugado else "Anotar resultado", expanded=not jugado):
        if jugado:
            if st.button("Anular resultado", key=f"rk_anular_{pid}"):
                _accion_ranking(rk.anular_resultado, pid, ok="Resultado anulado.")
            return
        with st.form(f"form_rk_{pid}"):
            ganador = st.radio("Ganador", [p["jugador_alto"], p["jugador_bajo"]], horizontal=True,
                               format_func=lambda j: p["nombre_alto"] if j == p["jugador_alto"] else p["nombre_bajo"],
                               key=f"rk_g_{pid}")
            marcador = st.text_input("Marcador (opcional)", placeholder="6-4 3-6 7-5", key=f"rk_m_{pid}")
            a, b, c = st.columns(3)
            guardar = a.form_submit_button("Guardar resultado", type="primary")
            falta_alto = b.form_submit_button(f"No se presentó {p['nombre_alto']}")
            falta_bajo = c.form_submit_button(f"No se presentó {p['nombre_bajo']}")
    if guardar or falta_alto or falta_bajo:
        if falta_alto or falta_bajo:
            _accion_ranking(rk.registrar_resultado, pid, None, marcador,
                            p["jugador_alto"] if falta_alto else p["jugador_bajo"],
                            ok="Resultado anotado por incomparecencia.")
        else:
            _accion_ranking(rk.registrar_resultado, pid, ganador, marcador, ok="Resultado anotado.")


def formulario_horario_ranking(p):
    """Día y hora previstos de un partido pendiente del ranking (solo administrador)."""
    pid = p["id"]
    actual = datetime.fromisoformat(p["fecha_hora"]) if p["fecha_hora"] else None
    with st.expander("Cambiar día y hora" if actual else "Programar día y hora"):
        with st.form(f"form_rk_horario_{pid}"):
            x, y = st.columns(2)
            dia = x.date_input("Día", value=actual.date() if actual else date.today(), key=f"rk_dia_{pid}",
                               format="DD/MM/YYYY")
            hora = y.time_input("Hora", value=actual.time() if actual else time(10, 0), step=900,
                                key=f"rk_hora_{pid}")
            g, h = st.columns(2)
            guardar = g.form_submit_button("Guardar día y hora", type="primary")
            quitar = h.form_submit_button("Quitar programación") if actual else False
    if guardar or quitar:
        _accion_ranking(rk.programar_partido, pid, datetime.combine(dia, hora) if guardar else None,
                        ok="Día y hora guardados." if guardar else "Programación quitada.")


def avisos_whatsapp_ranking(p, ventana, telefonos):
    """Enlaces wa.me para avisar a los dos jugadores de un partido pendiente (solo administrador)."""
    if not es_admin() or p["estado"] != "pendiente":
        return
    lados = ((p["jugador_alto"], p["nombre_alto"], p["nombre_bajo"]),
             (p["jugador_bajo"], p["nombre_bajo"], p["nombre_alto"]))
    for col, (jid, nombre, rival) in zip(st.columns(2), lados):
        tel = telefonos.get(jid)
        if not tel:
            col.caption(f"📵 {nombre}: sin teléfono")
            continue
        texto = whatsapp.mensaje_ranking(ventana, p, nombre, rival, CLUB_NOMBRE)
        col.link_button(f"📲 Avisar a {nombre}", whatsapp.enlace_whatsapp(tel, texto),
                        help="Abre WhatsApp con el mensaje ya escrito; tú pulsas «Enviar».")


def panel_telefonos_ranking(js, telefonos):
    """Teléfonos de los jugadores del ranking (solo administrador)."""
    with st.expander(f"📱 Teléfonos para avisos por WhatsApp ({len(telefonos)}/{len(js)} informados)"):
        st.caption("Solo los ve el administrador. Guárdalos únicamente si el jugador ha dado su consentimiento "
                   "para recibir avisos del club. Formato: 600 123 456 o +34 600 123 456.")
        with st.form("form_rk_telefonos"):
            for j in js:
                st.text_input(f"{j['posicion']}º {j['nombre']}", value=telefonos.get(j["id"], ""),
                              key=f"rk_tel_{j['id']}")
            guardar = st.form_submit_button("Guardar teléfonos", type="primary")
    if guardar:
        if not es_admin():
            st.error("Acción reservada al administrador.")
            return
        ss = st.session_state
        errores, hechos = [], 0
        for j in js:
            nuevo = ss.get(f"rk_tel_{j['id']}", "")
            try:
                if whatsapp.normalizar_telefono(nuevo) != telefonos.get(j["id"], ""):
                    rk.establecer_telefono(j["id"], nuevo)
                    hechos += 1
            except ValueError as e:
                errores.append(f"{j['nombre']}: {e}")
        ss.flash = (("error", "No se han guardado algunos teléfonos:\n\n" + "\n\n".join(errores)) if errores
                    else ("success", f"Teléfonos guardados ({hechos} cambio(s))."))
        st.rerun()


def formulario_reto(jugadores):
    """Alta de un reto en la ventana Reto (solo administrador)."""
    por_id = {j["id"]: j for j in jugadores}
    st.markdown(f"**Nuevo reto** — se puede retar hasta {rk.MAX_RETO} posiciones por encima.")
    retador = st.selectbox("Retador", list(por_id), format_func=lambda i: f"{por_id[i]['posicion']}º {por_id[i]['nombre']}",
                           key="rk_retador")
    pos = por_id[retador]["posicion"]
    posibles = [j["id"] for j in jugadores if 1 <= pos - j["posicion"] <= rk.MAX_RETO]
    if not posibles:
        st.info("Este jugador no tiene a nadie por encima a quien retar.")
        return
    retado = st.selectbox("Retado", posibles, format_func=lambda i: f"{por_id[i]['posicion']}º {por_id[i]['nombre']}",
                          key="rk_retado")
    if st.button("Crear reto", type="primary", key="rk_crear_reto"):
        _accion_ranking(rk.crear_reto, retador, retado, ok="Reto creado.")


def _bloque_carga_ranking():
    st.info("El ranking está vacío. Carga la clasificación inicial: un jugador por línea, del primero al último.")
    texto = st.text_area("Jugadores (uno por línea, en orden de clasificación)", key="rk_carga_texto", height=200)
    archivo = st.file_uploader("…o un CSV (columnas jugador;ranking y, opcional, telefono)", type="csv", key="rk_carga_csv")
    if st.button("Cargar clasificación inicial", type="primary", key="rk_cargar"):
        if not es_admin():
            st.error("Acción reservada al administrador.")
            return
        try:
            if archivo is not None:
                cargados = sorted(emparejamientos.leer_jugadores(archivo.getvalue()), key=lambda j: j.ranking)
                nombres = [j.nombre for j in cargados]
                tels = [j.telefono for j in cargados]
            else:
                nombres = [l for l in (texto or "").splitlines() if l.strip()]
                tels = None
            n = rk.cargar_jugadores_iniciales(nombres, tels)
        except emparejamientos.ErrorCSV as e:
            st.error("No se ha podido leer el CSV:\n\n" + emparejamientos.resumen_errores(e))
            return
        except ValueError as e:
            st.error(str(e))
            return
        st.session_state.flash = ("success", f"Ranking creado con {n} jugadores.")
        st.rerun()


def pagina_ranking():
    admin = es_admin()
    st.header("Ranking continuo")
    mostrar_flash()
    mostrar_anuncios("ranking", None, "📌 Anuncios del ranking")
    js = rk.jugadores()
    if not js:
        if admin:
            _bloque_carga_ranking()
        else:
            st.info("Todavía no hay ranking.")
        return

    abierta = rk.ventana_abierta()
    ciclo_sig, tipo_sig = rk.siguiente_ventana()
    tels = rk.telefonos() if admin else {}  # los teléfonos solo se consultan para el administrador
    c1, c2, c3 = st.columns(3)
    c1.metric("Jugadores", len(js))
    c2.metric("Ventana abierta", rk.NOMBRES[abierta["tipo"]] if abierta else "Ninguna")
    c3.metric("Ciclo", abierta["ciclo"] if abierta else ciclo_sig)

    titulos = ["Clasificación", "Ventana actual", "Historial"] + (["Jugadores"] if admin else [])
    tabs = st.tabs(titulos)

    with tabs[0]:
        st.markdown(estilo.ranking_html(js), unsafe_allow_html=True)
        st.markdown("**📈 Evolución de un jugador**")
        elegido = st.selectbox("Jugador", [j["id"] for j in js], key="rk_evo",
                               format_func=lambda i: next(f"{j['posicion']}º {j['nombre']}" for j in js if j["id"] == i))
        puntos = rk.evolucion_jugador(elegido)
        nombre_ev = next(j["nombre"] for j in js if j["id"] == elegido)
        grafica = estilo.evolucion_html(puntos, nombre_ev)
        if grafica:
            st.markdown(grafica, unsafe_allow_html=True)
            posiciones = [p["posicion"] for p in puntos]
            st.caption(f"Mejor puesto: {min(posiciones)}º · Peor puesto: {max(posiciones)}º · "
                       f"Variación desde el inicio: {posiciones[0] - posiciones[-1]:+d} puestos. "
                       "El eje vertical va del mejor puesto (arriba) al peor; el punto hueco es la ventana en curso.")
            with st.expander("Ver los datos en tabla"):
                st.markdown(estilo.evolucion_tabla_html(puntos), unsafe_allow_html=True)
        else:
            st.info("Todavía no hay suficientes ventanas para dibujar la evolución de este jugador.")
        st.caption("Reglas: si gana el jugador peor situado, toma la posición del perdedor (y este la suya); "
                   "si gana el mejor situado, nadie se mueve. Ventana 1: contra el de 1 puesto por encima; "
                   "ventana 2: 3 puestos; ventana 3: 5 puestos; ventana Reto: retos voluntarios hasta 7 puestos por encima.")

    with tabs[1]:
        if abierta is None:
            st.info(f"No hay ninguna ventana abierta. La próxima es la **{rk.NOMBRES[tipo_sig]}** (ciclo {ciclo_sig}).")
            if admin and st.button(f"Abrir {rk.NOMBRES[tipo_sig]}", type="primary", key="rk_abrir"):
                _accion_ranking(rk.abrir_ventana, ok=f"{rk.NOMBRES[tipo_sig]} abierta.")
        else:
            st.subheader(f"{rk.NOMBRES[abierta['tipo']]} · ciclo {abierta['ciclo']}")
            partidos = rk.partidos_de_ventana(abierta["id"])
            pendientes = sum(1 for p in partidos if p["estado"] == "pendiente")
            if abierta["tipo"] == "reto":
                st.caption("Los jugadores pueden retar a cualquiera hasta 7 puestos por encima; "
                           "un jugador solo puede estar en un reto por ventana.")
            visibles = partidos
            if partidos:
                buscar = st.text_input("🔎 Buscar jugador", key="rk_buscar", max_chars=60,
                                       placeholder="Escribe parte del nombre (sin importar mayúsculas ni acentos)")
                visibles = rk.filtrar_partidos(partidos, buscar)
                if buscar.strip():
                    st.caption(f"{len(visibles)} de {len(partidos)} partidos.")
                if visibles:
                    st.markdown(estilo.partidos_ranking_html(visibles), unsafe_allow_html=True)
                else:
                    st.warning(f"Ningún partido de esta ventana incluye a «{buscar.strip()}».")
            else:
                st.info("Esta ventana no tiene partidos todavía." if abierta["tipo"] == "reto"
                        else "Con los jugadores actuales esta ventana no tiene partidos.")
            if admin:
                for p in visibles:
                    with st.container(border=True):
                        st.markdown(f"{p['pos_alto']}º **{p['nombre_alto']}** vs {p['pos_bajo']}º **{p['nombre_bajo']}**")
                        formulario_ranking_partido(p)
                        if p["estado"] == "pendiente":
                            formulario_horario_ranking(p)
                            avisos_whatsapp_ranking(p, rk.NOMBRES[abierta["tipo"]], tels)
                        if abierta["tipo"] == "reto" and p["estado"] == "pendiente":
                            if st.button("Quitar reto", key=f"rk_quitar_{p['id']}"):
                                _accion_ranking(rk.quitar_reto, p["id"], ok="Reto quitado.")
                if abierta["tipo"] == "reto":
                    formulario_reto(js)
                st.divider()
                if st.button("Cerrar ventana", type="primary", key="rk_cerrar", disabled=pendientes > 0,
                             help="Se puede cerrar cuando no quedan partidos pendientes."):
                    _accion_ranking(rk.cerrar_ventana, ok="Ventana cerrada.")

    with tabs[2]:
        items = rk.historial(40)
        if items:
            st.markdown(estilo.historial_ranking_html(items, rk.NOMBRES), unsafe_allow_html=True)
        else:
            st.info("Todavía no se ha jugado ningún partido.")

    if admin:
        with tabs[3]:
            with st.form("form_rk_alta", clear_on_submit=True):
                nuevo = st.text_input("Nuevo jugador (se añade al final del ranking)", key="rk_nuevo", max_chars=100)
                nuevo_tel = st.text_input("Teléfono (opcional)", key="rk_nuevo_tel", max_chars=30)
                alta = st.form_submit_button("Añadir jugador", type="primary")
            if alta:
                _accion_ranking(rk.anadir_jugador, nuevo, nuevo_tel, ok="Jugador añadido al final del ranking.")
            panel_telefonos_ranking(js, tels)
            st.markdown("**Dar de baja** (los de abajo suben un puesto; solo sin ventana abierta)")
            baja = st.selectbox("Jugador", [j["id"] for j in js], key="rk_baja",
                                format_func=lambda i: next(f"{j['posicion']}º {j['nombre']}" for j in js if j["id"] == i))
            if st.button("Dar de baja", key="rk_dar_baja"):
                _accion_ranking(rk.dar_de_baja, baja, ok="Jugador dado de baja.")


# ---------------------------------------------------------------------------
# Sección 5: Tablón de anuncios
# ---------------------------------------------------------------------------

def mostrar_anuncios(ambito, torneo=None, titulo="📌 Anuncios"):
    """Anuncios de un torneo o del ranking, en la parte superior de su página (todos los usuarios)."""
    lista = anuncios.listar_anuncios(ambito=ambito, torneo=torneo, incluir_ocultos=es_admin(), limite=20)
    if lista:
        with st.expander(f"{titulo} ({len(lista)})", expanded=True):
            st.markdown(estilo.anuncios_html(lista), unsafe_allow_html=True)


def formulario_anuncio(torneos, anuncio=None):
    """Alta (anuncio=None) o edición de un anuncio (solo administrador)."""
    nuevo = anuncio is None
    k = "nuevo" if nuevo else str(anuncio["id"])
    with st.form(f"form_anuncio_{k}", clear_on_submit=nuevo):
        if nuevo:
            ambito = st.radio("Dónde se publica", list(anuncios.AMBITOS), horizontal=True,
                              format_func=lambda x: anuncios.NOMBRES_AMBITO[x], key=f"an_ambito_{k}")
            torneo = st.selectbox("Torneo (solo si el anuncio es de un torneo)", [t["codigo"] for t in torneos],
                                  format_func=lambda c: next(f"{t['codigo']} — {t['nombre']}" for t in torneos if t["codigo"] == c),
                                  key=f"an_torneo_{k}") if torneos else None
        titulo = st.text_input("Título", value="" if nuevo else anuncio["titulo"], max_chars=anuncios.MAX_TITULO,
                               key=f"an_titulo_{k}")
        texto = st.text_area("Texto", value="" if nuevo else anuncio["texto"], max_chars=anuncios.MAX_TEXTO,
                             key=f"an_texto_{k}")
        fijado = st.checkbox("📌 Fijar arriba", value=False if nuevo else bool(anuncio["fijado"]), key=f"an_fijado_{k}")
        con_caducidad = st.checkbox("Con fecha de caducidad (deja de verse ese día)",
                                    value=False if nuevo else bool(anuncio["caduca"]), key=f"an_concad_{k}")
        caduca = st.date_input("Caduca el", value=(date.fromisoformat(anuncio["caduca"]) if (not nuevo and anuncio["caduca"])
                                                    else date.today()), format="DD/MM/YYYY", key=f"an_caduca_{k}")
        enviar = st.form_submit_button("Publicar anuncio" if nuevo else "Guardar cambios", type="primary")
    if enviar:
        fecha = caduca if con_caducidad else None
        if nuevo:
            _accion_ranking(anuncios.crear_anuncio, ambito, titulo, texto, torneo if ambito == "torneo" else None,
                            fijado, fecha, ok="Anuncio publicado.")
        else:
            _accion_ranking(anuncios.editar_anuncio, anuncio["id"], titulo, texto, fijado, fecha,
                            ok="Anuncio actualizado.")


def pagina_anuncios():
    admin = es_admin()
    st.header("Tablón de anuncios")
    mostrar_flash()
    torneos = db.buscar_torneos(incluir_ocultos=admin)
    if admin:
        with st.expander("➕ Nuevo anuncio"):
            formulario_anuncio(torneos)

    opciones = ["todos", "general", "ranking"] + [t["codigo"] for t in torneos]
    nombres = {"todos": "Todos", "general": "General", "ranking": "Ranking continuo",
               **{t["codigo"]: f"Torneo {t['codigo']} — {t['nombre']}" for t in torneos}}
    filtro = st.selectbox("Mostrar", opciones, format_func=lambda o: nombres[o], key="an_filtro")
    if filtro == "todos":
        lista = anuncios.listar_anuncios(incluir_ocultos=admin)
    elif filtro in ("general", "ranking"):
        lista = anuncios.listar_anuncios(ambito=filtro, incluir_ocultos=admin)
    else:
        lista = anuncios.listar_anuncios(ambito="torneo", torneo=filtro, incluir_ocultos=admin)
    if not lista:
        st.info("No hay anuncios.")
        return
    if not admin:
        st.markdown(estilo.anuncios_html(lista), unsafe_allow_html=True)
        return
    for an in lista:
        with st.container(border=True):
            st.markdown(estilo.anuncios_html([an]), unsafe_allow_html=True)
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("Quitar fijado" if an["fijado"] else "📌 Fijar", key=f"an_fijar_{an['id']}"):
                _accion_ranking(anuncios.fijar_anuncio, an["id"], not an["fijado"],
                                ok="Anuncio desfijado." if an["fijado"] else "Anuncio fijado.")
            if c2.button("🗑️ Eliminar", key=f"an_del_{an['id']}"):
                _accion_ranking(anuncios.eliminar_anuncio, an["id"], ok="Anuncio eliminado.")
            with st.expander("Editar"):
                formulario_anuncio(torneos, an)


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

init_estado()
estilo.inyectar(st)
if st.session_state.seccion not in secciones():  # p. ej. tras iniciar o cerrar sesión
    st.session_state.seccion = secciones()[0]
sidebar_acceso()
cabecera_club()

_seccion = st.session_state.seccion
if _seccion == "Nuevo torneo":
    exigir_admin()
    pagina_nuevo()
elif _seccion == "Gestionar torneo":
    exigir_admin()
    pagina_gestionar(editable=True)
elif _seccion == "Ver torneo":
    pagina_gestionar(editable=False)
elif _seccion == "Ranking continuo":
    pagina_ranking()
elif _seccion == "Tablón de anuncios":
    pagina_anuncios()
else:
    pagina_consultar()

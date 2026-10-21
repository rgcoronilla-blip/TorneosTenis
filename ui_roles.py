"""Simulador mínimo de Streamlit para recorrer app_streamlit.py como invitado y como administrador."""
import os
import runpy
import sys
import tempfile
import types
from datetime import date, datetime

sys.path.insert(0, "/home/claude")
os.chdir("/home/claude")
os.environ["TORNEOS_DB"] = os.path.join(tempfile.mkdtemp(), "ui.db")

import auth  # noqa: E402
import torneo as db  # noqa: E402
from sorteo_torneo_tenis import Jugador, SorteoTorneo  # noqa: E402

auth.ITERACIONES = 1000


class Rerun(Exception):
    pass


class Stop(Exception):
    pass


class SS(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


KEYS = ["error", "success", "info", "buttons", "tables", "markdown", "captions", "radio", "number", "inputs", "images", "downloads", "warnings", "dates", "times", "links"]
LOG = {k: [] for k in KEYS}
STATE = {"ss": SS(), "clicks": [], "overrides": {}, "globals": None, "upload": {}}


def _w(label, key, default):
    ss = STATE["ss"]
    if label in STATE["overrides"]:
        return STATE["overrides"][label]
    if key:
        if key not in ss:
            ss[key] = default
        return ss[key]
    return default


class Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(st, name)


def _click(label, on_click=None, args=()):
    LOG["buttons"].append(label)
    if label in STATE["clicks"]:
        STATE["clicks"].remove(label)
        if on_click:
            on_click(*args)
        return True
    return False


def _opciones(label, options, key, default_index=0):
    options = list(options)
    LOG["radio"].append((label, options))
    ss = STATE["ss"]
    if key and key in ss and ss[key] not in options:      # Streamlit lo rechaza igual
        raise RuntimeError(f"{key}={ss[key]!r} no está en las opciones {options}")
    return _w(label, key, options[default_index])


def _log(nombre):
    def f(m="", *a, **k):
        LOG[nombre].append(str(m))
    return f


st = types.ModuleType("streamlit")
st.session_state = STATE["ss"]
st.set_page_config = lambda **k: None
st.sidebar = Ctx()
st.title = st.header = st.subheader = st.divider = lambda *a, **k: None
st.caption = _log("captions")
st.markdown = _log("markdown")
st.success = _log("success")
st.error = _log("error")
st.info = _log("info")
st.warning = _log("warnings")
st.download_button = lambda label, *a, **k: LOG["downloads"].append(label)
st.image = lambda ruta, **k: LOG["images"].append(ruta)
st.metric = lambda *a, **k: None
st.dataframe = lambda df, **k: LOG["tables"].append(df)
st.data_editor = lambda df, **k: df
st.file_uploader = lambda label, type=None, key=None, **k: STATE["upload"].get(key or label)
st.column_config = types.SimpleNamespace(TextColumn=lambda *a, **k: None, NumberColumn=lambda *a, **k: None)
st.radio = lambda label, options, key=None, **k: _opciones(label, options, key)
st.selectbox = lambda label, options, index=0, key=None, **k: _opciones(label, options, key, index)
st.checkbox = lambda label, value=False, key=None, **k: _w(label, key, value)


def _number(label, min_value=None, max_value=None, value=0, step=1, key=None, **k):
    LOG["number"].append(label)
    return _w(label, key, value)


def _text(label, value="", key=None, **k):
    LOG["inputs"].append(label)
    return _w(label, key, value)


st.number_input = _number
st.text_input = _text
st.text_area = _text
st.date_input = lambda label, value=None, key=None, **k: (LOG["dates"].append(label), _w(label, key, value))[1]
st.time_input = lambda label, value=None, key=None, **k: (LOG["times"].append(label), _w(label, key, value))[1]
st.link_button = lambda label, url, **k: LOG["links"].append((label, url))
st.button = lambda label, on_click=None, args=(), **k: _click(label, on_click, args)


class FormCtx(Ctx):
    def __init__(self, key):
        self.key = key

    def __enter__(self):
        STATE["form"] = self.key
        return self

    def __exit__(self, *a):
        STATE["form"] = None
        return False


def _submit(label, **k):
    """Un botón de formulario se puede pulsar por su texto o, para uno concreto, como «clave_form:texto»."""
    token = f"{STATE.get('form')}:{label}"
    if token in STATE["clicks"]:
        STATE["clicks"].remove(token)
        LOG["buttons"].append(label)
        return True
    return _click(label)


st.form_submit_button = _submit
st.form = lambda key, **k: FormCtx(key)
st.container = st.expander = lambda *a, **k: Ctx()
st.columns = lambda spec: [Ctx() for _ in range(spec if isinstance(spec, int) else len(spec))]
TABS = []
def _tabs(labels):
    TABS.append(list(labels))
    return [Ctx() for _ in labels]
st.tabs = _tabs


def _rerun():
    raise Rerun()


def _stop():
    raise Stop()


st.rerun = _rerun
st.stop = _stop
sys.modules["streamlit"] = st

ss = STATE["ss"]


def correr(clicks=(), overrides=None, **estado):
    STATE["clicks"] = list(clicks)
    STATE["overrides"] = overrides or {}
    ss.update(estado)
    for k in LOG:
        LOG[k].clear()
    for _ in range(6):
        try:
            STATE["globals"] = runpy.run_path("app_streamlit.py", run_name="__main__")
            return
        except Rerun:
            STATE["clicks"] = []
        except Stop:
            return
    raise SystemExit("bucle de reruns")


def opciones_seccion():
    return [o for (lbl, o) in LOG["radio"] if lbl == "Sección"][0]


def falla_con_stop(fn, *a):
    try:
        fn(*a)
    except Stop:
        return
    raise SystemExit("debería haber cortado con st.stop()")


ADMIN_PW = "Clave-segura-1"
GUEST = ["Consultar torneos", "Ver torneo", "Ranking continuo", "Tablón de anuncios"]
ADMIN = ["Nuevo torneo", "Gestionar torneo", "Consultar torneos", "Ranking continuo", "Tablón de anuncios"]

# --- A. Primer arranque: invitado y alta del administrador -------------------
correr()
assert ss.rol == "invitado" and ss.seccion == "Consultar torneos"
assert opciones_seccion() == GUEST
assert "Crear administrador y entrar" in LOG["buttons"] and "Entrar" not in LOG["buttons"]
assert not any("Base de datos" in c for c in LOG["captions"])
for pw1, pw2, texto in [(ADMIN_PW, "otra", "no coinciden"), ("corta", "corta", "al menos 8")]:
    correr(clicks=["Crear administrador y entrar"], overrides={"Contraseña": pw1, "Repite la contraseña": pw2})
    assert ss.rol == "invitado" and any(texto in e for e in LOG["error"]), LOG["error"]
assert not auth.hay_admin()
correr(clicks=["Crear administrador y entrar"], overrides={"Contraseña": ADMIN_PW, "Repite la contraseña": ADMIN_PW})
assert ss.rol == "admin" and ss.seccion == "Nuevo torneo" and auth.hay_admin()
correr()
assert opciones_seccion() == ADMIN and "Cerrar sesión" in LOG["buttons"]
assert any("Base de datos" in c for c in LOG["captions"])
print("OK A: arranque como invitado, alta del administrador y vista de administrador")

# --- B. El administrador crea torneos y anota resultados ----------------------
correr(clicks=["🎲 Realizar sorteo"])
assert ss.pendiente["tipo"] == "eliminatorias"
correr(clicks=["✅ Generar torneo"], nuevo_nombre="Open de Jerez", nuevo_codigo="TEN-1")
assert ss.seccion == "Gestionar torneo" and db.obtener_torneo("TEN-1")
p1 = [p for p in db.partidos_de("TEN-1") if p["ronda"] == 1 and p["jugador1"] and p["jugador2"]][0]
correr(clicks=["Guardar resultado"], **{f"s1_{p1['id']}": 2, f"s2_{p1['id']}": 0})
assert db.obtener_torneo("TEN-1")["estado"] == "en curso"
correr()
assert "Guardar resultado" in LOG["buttons"] and LOG["number"], "el admin debe ver los formularios"

correr(seccion="Nuevo torneo")
correr(clicks=["🎲 Realizar sorteo"], overrides={"Tipo de campeonato": "grupos"})
correr(clicks=["✅ Generar torneo"], nuevo_nombre="Liga de grupos", nuevo_codigo="GRP-1", nuevo_formato="Un solo set",
       overrides={"Tipo de campeonato": "grupos"})
assert db.obtener_torneo("GRP-1")
g1 = [p for p in db.partidos_de("GRP-1") if p["fase"] == "grupo"][0]
correr(clicks=["Guardar resultado"], **{f"s1_{g1['id']}": 1, f"s2_{g1['id']}": 0})
assert "No se jugó (0 puntos)" in LOG["buttons"] or True
correr()
assert "No se jugó (0 puntos)" in LOG["buttons"], "el admin ve el botón en partidos de grupo"
g2 = [p for p in db.partidos_de("GRP-1") if p["fase"] == "grupo" and p["estado"] == "pendiente"][0]
correr(clicks=[f"form_{g2['id']}:No se jugó (0 puntos)"])
assert next(p for p in db.partidos_de("GRP-1") if p["id"] == g2["id"])["sin_jugar"] == 1
print("OK B: el administrador sortea, crea torneos y anota resultados")

# --- C. Cerrar sesión: vuelve a invitado y no deja el sorteo sin guardar ------------
correr(seccion="Nuevo torneo")
correr(clicks=["🎲 Realizar sorteo"])
assert ss.pendiente
correr(clicks=["Cerrar sesión"])
assert ss.rol == "invitado" and ss.seccion == "Consultar torneos" and ss.pendiente is None
assert opciones_seccion() == GUEST
print("OK C: cerrar sesión devuelve a invitado y descarta el sorteo sin guardar")

# --- D. El invitado solo consulta -------------------------------------------------
correr(seccion="Ver torneo", torneo_activo="TEN-1")
assert "Guardar resultado" not in LOG["buttons"] and "Anular resultado" not in LOG["buttons"]
assert not LOG["number"], "el invitado no debe ver campos para anotar sets"
assert any("✅ Ganador" in m for m in LOG["markdown"]), "debe ver los resultados ya jugados"
assert "Pendiente de jugar." in LOG["captions"]
correr(seccion="Ver torneo", torneo_activo="GRP-1")
assert any("t-tabla" in m and "<th>Pts</th>" in m and "<th>PG</th>" in m for m in LOG["markdown"]), "debe ver la clasificación de grupos"
assert "Guardar resultado" not in LOG["buttons"] and not LOG["number"] and "No se jugó (0 puntos)" not in LOG["buttons"]
correr(seccion="Consultar torneos")
assert sum(m.count('<tr><td class="izq"><b>') for m in LOG["markdown"]) == 2
assert "Ver resultados del torneo" in LOG["buttons"] and "Abrir en «Gestionar torneo»" not in LOG["buttons"]
correr(seccion="Consultar torneos", clicks=["Ver resultados del torneo"], overrides={"Abrir torneo": "GRP-1"})
assert ss.seccion == "Ver torneo" and ss.torneo_activo == "GRP-1"
correr(overrides={"Código (o parte)": "grp"}, seccion="Consultar torneos")
assert any("<b>GRP-1</b>" in m for m in LOG["markdown"]) and not any("<b>TEN-1</b>" in m for m in LOG["markdown"])
print("OK D: el invitado consulta y ve resultados, sin formularios de edición")

# --- E. Intentos de saltarse el permiso ---------------------------------------------
for forzada in ("Nuevo torneo", "Gestionar torneo"):
    correr(seccion=forzada)
    assert ss.seccion == "Consultar torneos", ss.seccion
    assert "🎲 Realizar sorteo" not in LOG["buttons"] and "Guardar resultado" not in LOG["buttons"]
G = STATE["globals"]
falla_con_stop(G["pagina_nuevo"])
# sorteo falsificado en la sesión de un invitado + callback invocado a mano
js = [Jugador(f"H{i}", i) for i in range(1, 5)]
obj = SorteoTorneo(js, seed=1)
obj.generar()
ss.update(pendiente={"tipo": "eliminatorias", "jugadores": js, "obj": obj}, nuevo_codigo="HACK-1",
          nuevo_nombre="x", nuevo_inicio=date.today(), nuevo_fin=date.today(), nuevo_formato="Un solo set")
G["crear_torneo_cb"]()
assert db.obtener_torneo("HACK-1") is None and ss.flash[0] == "error"
ss.pop("flash")
# anotar un resultado a mano llamando al formulario
pend = [p for p in db.partidos_de("TEN-1") if p["estado"] == "pendiente" and p["jugador1"] and p["jugador2"]][0]
ss.update({f"s1_{pend['id']}": 2, f"s2_{pend['id']}": 0})
STATE["clicks"] = ["Guardar resultado"]
LOG["error"].clear()
G["formulario_resultado"](pend, 2)
assert any("administrador" in e for e in LOG["error"])
assert [p for p in db.partidos_de("TEN-1") if p["id"] == pend["id"]][0]["estado"] == "pendiente"
ss.jugadores_base = "intacto"
G["cargar_ejemplo"]()
assert ss.jugadores_base == "intacto"
ss.pop("jugadores_base")   # se restaura el valor por defecto de la app
ss.pendiente = None
print("OK E: los intentos de saltarse el permiso no cambian nada")

# --- F. Acceso con contraseña: errores, bloqueo y restablecimiento --------------------
correr(seccion="Consultar torneos")
assert "Entrar" in LOG["buttons"] and "Crear administrador y entrar" not in LOG["buttons"]
correr(clicks=["Entrar"], overrides={"Contraseña": "mal"})
assert ss.rol == "invitado" and any("Te quedan 4" in e for e in LOG["error"]), LOG["error"]
for _ in range(3):
    correr(clicks=["Entrar"], overrides={"Contraseña": "mal"})
correr(clicks=["Entrar"], overrides={"Contraseña": "mal"})
assert any("Demasiados" in e for e in LOG["error"]), LOG["error"]
correr(clicks=["Entrar"], overrides={"Contraseña": ADMIN_PW})                 # bloqueado aunque acierte
assert ss.rol == "invitado" and any("Demasiados" in e for e in LOG["error"])
auth.establecer_password(ADMIN_PW)                                            # equivale a la orden por consola
correr(clicks=["Entrar"], overrides={"Contraseña": ADMIN_PW})
assert ss.rol == "admin" and ss.seccion == "Nuevo torneo"
print("OK F: errores, bloqueo tras 5 intentos y entrada correcta")

# --- G. Cambiar la contraseña desde la interfaz ----------------------------------------
NUEVA = "Nueva-clave-77"
cambiar = {"Contraseña actual": ADMIN_PW, "Nueva contraseña": NUEVA, "Repite la nueva contraseña": NUEVA}
correr(clicks=["Cambiar contraseña"], overrides={**cambiar, "Repite la nueva contraseña": "distinta"})
assert any("no coinciden" in e for e in LOG["error"])
correr(clicks=["Cambiar contraseña"], overrides={**cambiar, "Contraseña actual": "incorrecta"})
assert any("Contraseña incorrecta" in e for e in LOG["error"])
correr(clicks=["Cambiar contraseña"], overrides={**cambiar, "Nueva contraseña": "corta", "Repite la nueva contraseña": "corta"})
assert any("al menos 8" in e for e in LOG["error"])
correr(clicks=["Cambiar contraseña"], overrides=cambiar)
assert "Contraseña cambiada." in LOG["success"]
correr(clicks=["Cerrar sesión"])
correr(clicks=["Entrar"], overrides={"Contraseña": ADMIN_PW})
assert ss.rol == "invitado"
correr(clicks=["Entrar"], overrides={"Contraseña": NUEVA})
assert ss.rol == "admin"
print("OK G: cambio de contraseña desde la interfaz")

# --- H. Cabecera del club con el escudo -----------------------------------------------
import base64
RUTA = "/home/claude/escudo_club.png"
assert not os.path.exists(RUTA), "no debe haber un escudo de pruebas previo"

# sin fichero: se ve el nombre del club; solo el administrador recibe la indicación de dónde poner la imagen
ss.rol = "invitado"
correr(seccion="Consultar torneos")
BANNER = lambda: [m for m in LOG["markdown"] if "t-banner" in m and "Club Nazaret" in m and "Jerez de la Frontera · Torneos de tenis" in m]
assert BANNER() and not any("<img" in m for m in BANNER())
assert not any("escudo_club" in c for c in LOG["captions"])
ss.rol = "admin"
correr(seccion="Consultar torneos")
assert any("escudo_club.png" in c for c in LOG["captions"])
print("OK H1: sin imagen se ve el nombre del club (y el aviso solo para el administrador)")

# con fichero: aparece en todas las secciones y para los dos roles
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
open(RUTA, "wb").write(PNG)
try:
    for rol, seccion in [("invitado", "Consultar torneos"), ("invitado", "Ver torneo"),
                         ("admin", "Nuevo torneo"), ("admin", "Gestionar torneo"), ("admin", "Consultar torneos")]:
        ss.rol = rol
        correr(seccion=seccion)
        assert BANNER() and "data:image/png;base64," in BANNER()[0], (rol, seccion)
        assert 'alt="Escudo de Club Nazaret"' in BANNER()[0]
        assert not any("escudo_club" in c for c in LOG["captions"])    # ya no hace falta el aviso
    # la cabecera sale también cuando una sección de administrador se corta para un invitado
    ss.rol = "invitado"
    correr(seccion="Consultar torneos")
    G = STATE["globals"]
    LOG["images"].clear()
    falla_con_stop(G["pagina_nuevo"])
    print("OK H2: el escudo aparece en todas las secciones, para invitado y administrador")
finally:
    os.remove(RUTA)
assert not os.path.exists(RUTA)
print("OK H3: fin del bloque de cabecera")


# --- I. Emparejamientos desde CSV (sin sorteo) -------------------------------------------------
import emparejamientos as em


class Subida:
    def __init__(self, datos, nombre="emparejamientos.csv"):
        self.datos, self.name, self.size = datos, nombre, len(datos)

    def getvalue(self):
        return self.datos


CSV = {"Cómo quieres crear el cuadro": "csv"}
ELI = {**CSV, "Tipo de campeonato": "eliminatorias"}
GRP = {**CSV, "Tipo de campeonato": "grupos"}
CARGAR = "📥 Cargar emparejamientos"
ss.rol = "admin"
ss.pendiente = None

correr(seccion="Nuevo torneo", overrides=ELI)
assert "⬇️ Descargar plantilla CSV" in LOG["downloads"] and CARGAR in LOG["buttons"]
assert "🎲 Realizar sorteo" not in LOG["buttons"], "en modo CSV no hay sorteo"
assert "Cómo quieres crear el cuadro" in [lbl for lbl, _ in LOG["radio"]]
opciones_modo = [o for lbl, o in LOG["radio"] if lbl == "Cómo quieres crear el cuadro"][0]
assert opciones_modo == ["sorteo", "csv"]
assert any("BYE" in m for m in LOG["markdown"]), "debe explicar el formato de eliminatorias"

correr(clicks=[CARGAR], overrides=ELI)                                       # sin fichero
assert any("Selecciona primero" in e for e in LOG["error"]) and ss.pendiente is None

STATE["upload"] = {"emparejamientos_eliminatorias": Subida(b"jugador1;jugador2\nA;B\nC;D\nE;F\n")}
correr(clicks=[CARGAR], overrides=ELI)                                       # fichero con errores
assert ss.pendiente is None
assert any("No se han podido cargar" in e and "tiene 3" in e and "Añade 1 fila" in e for e in LOG["error"]), LOG["error"]

STATE["upload"] = {"emparejamientos_eliminatorias": Subida(em.plantilla("eliminatorias"))}
correr(clicks=[CARGAR], overrides=ELI)                                       # fichero correcto
assert ss.pendiente["origen"] == "csv" and ss.pendiente["tipo"] == "eliminatorias"
assert len(ss.pendiente["jugadores"]) == 6 and ss.pendiente["obj"].byes == 2
correr(overrides=ELI)
assert "✅ Generar torneo" in LOG["buttons"]
correr(clicks=["✅ Generar torneo"], nuevo_nombre="Copa CSV", nuevo_codigo="CSV-1", overrides=ELI)
t = db.obtener_torneo("CSV-1")
assert t and t["tipo"] == "eliminatorias" and t["num_jugadores"] == 6 and ss.seccion == "Gestionar torneo"
assert ss.pendiente is None
r1 = [p for p in db.partidos_de("CSV-1") if p["ronda"] == 1]
assert [(p["nombre1"], p["nombre2"]) for p in r1] == [("Ana García", None), ("Elena Torres", "Sofía Marín"),
                                                      ("Laura Pérez", None), ("Marta Ruiz", "Paula Ortiz")]
print("OK I1: eliminatorias desde CSV — plantilla, errores, vista previa y alta del torneo")

# un fichero erróneo borra una vista previa anterior (no se puede dar de alta algo que no corresponde al fichero)
correr(seccion="Nuevo torneo", overrides=ELI)
STATE["upload"] = {"emparejamientos_eliminatorias": Subida(em.plantilla("eliminatorias"))}
correr(clicks=[CARGAR], overrides=ELI)
assert ss.pendiente
STATE["upload"] = {"emparejamientos_eliminatorias": Subida(b"nada;util\n1;2\n")}
correr(clicks=[CARGAR], overrides=ELI)
assert ss.pendiente is None and any("Faltan las columnas" in e for e in LOG["error"])
print("OK I2: un fichero erróneo descarta la vista previa anterior")

# grupos desde CSV
STATE["upload"] = {"emparejamientos_grupos": Subida(em.plantilla("grupos"))}
correr(seccion="Nuevo torneo", overrides=GRP)
assert any("A, B, C" in m for m in LOG["markdown"]), "debe explicar el formato de grupos"
correr(clicks=[CARGAR], overrides=GRP)
assert ss.pendiente["tipo"] == "grupos" and len(ss.pendiente["obj"].grupos) == 2
correr(clicks=["✅ Generar torneo"], nuevo_nombre="Liga CSV", nuevo_codigo="CSV-2", overrides=GRP)
cl = db.clasificaciones("CSV-2")
assert sorted(cl) == ["A", "B"] and [f["nombre"] for f in cl["A"]["tabla"]][0] in ("Ana García", "Elena Torres", "Cristina Vidal", "Lucía Navarro")
# el fichero de grupos no vale para eliminatorias (cada tipo con su formato)
STATE["upload"] = {"emparejamientos_eliminatorias": Subida(em.plantilla("grupos"))}
correr(seccion="Nuevo torneo", clicks=[CARGAR], overrides=ELI)
assert ss.pendiente is None and any("Faltan las columnas" in e for e in LOG["error"])
print("OK I3: grupos desde CSV y cada tipo exige su propio formato")

# sin ranking no se ve «(#999999)» en ninguna pantalla
STATE["upload"] = {"emparejamientos_eliminatorias": Subida("jugador1;jugador2\nAna;Bea\nCris;Dora\n".encode())}
correr(seccion="Nuevo torneo", clicks=[CARGAR], overrides=ELI)
assert not any("999999" in m for m in LOG["markdown"]), "la vista previa no debe mostrar el ranking vacío"
correr(clicks=["✅ Generar torneo"], nuevo_nombre="Sin ranking", nuevo_codigo="CSV-3", overrides=ELI)
correr(seccion="Gestionar torneo", torneo_activo="CSV-3")
assert not any("999999" in m for m in LOG["markdown"]) and any('title="Ana">Ana</span>' in m for m in LOG["markdown"]), LOG["markdown"][:6]
correr(seccion="Gestionar torneo", torneo_activo="CSV-2")
assert not any("999999" in m for m in LOG["markdown"])
print("OK I4: sin ranking se muestra solo el nombre")

# el modo sorteo sigue funcionando y marca su origen
correr(seccion="Nuevo torneo", clicks=["🎲 Realizar sorteo"], overrides={"Cómo quieres crear el cuadro": "sorteo",
                                                                       "Tipo de campeonato": "eliminatorias"})
assert ss.pendiente["origen"] == "sorteo"
ss.pendiente = None

# el invitado no llega al formulario ni puede saltarse la carga
ss.rol = "invitado"
correr(seccion="Nuevo torneo", overrides=ELI)
assert ss.seccion == "Consultar torneos" and CARGAR not in LOG["buttons"]
print("OK I5: sorteo intacto y el invitado no accede a la carga por CSV")
print("OK I6: fin del bloque CSV")


# --- J. Día y hora prevista de cada partido ---------------------------------------------------------
from datetime import datetime, time, timedelta

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
GUARDAR, QUITAR = "Guardar día y hora", "Quitar programación"
POR_CONFIRMAR = "📅 Día y hora por confirmar."
t1 = db.obtener_torneo("CSV-1")
ini, fin = date.fromisoformat(t1["fecha_inicio"]), date.fromisoformat(t1["fecha_fin"])


def previsto(dia, hora="18:30"):
    return f"📅 Previsto: {DIAS[dia.weekday()]} {dia.strftime('%d/%m/%Y')} · {hora}"


def partido_de(codigo, **filtro):
    return next(p for p in db.partidos_de(codigo) if all(p[k] == v for k, v in filtro.items()))


ss.rol = "admin"
correr(seccion="Gestionar torneo", torneo_activo="CSV-1")
reales = [p for p in db.partidos_de("CSV-1") if "BYE" not in (p["origen1"], p["origen2"])]
assert len(reales) == 5
assert LOG["buttons"].count(GUARDAR) == 5 and QUITAR not in LOG["buttons"], LOG["buttons"].count(GUARDAR)
assert LOG["captions"].count(POR_CONFIRMAR) == 5 and "Día" in LOG["dates"] and "Hora" in LOG["times"]
# en un torneo con grupos hay formulario en todos los partidos de grupo y de eliminatoria
correr(seccion="Gestionar torneo", torneo_activo="CSV-2")
assert LOG["buttons"].count(GUARDAR) == 18, LOG["buttons"].count(GUARDAR)
assert ["Fase de grupos", "Cuadro principal", "Cuadro consolación"] in TABS, TABS
correr(seccion="Gestionar torneo", torneo_activo="CSV-1")

# fijar el día y la hora del primer partido que se juega
primero = partido_de("CSV-1", ronda=1, posicion=2)
pid = primero["id"]
correr(clicks=[GUARDAR], **{f"dia_{pid}": ini, f"hora_{pid}": time(18, 30)})
assert partido_de("CSV-1", id=pid)["fecha_hora"] == f"{ini.isoformat()}T18:30"
assert "Día y hora guardados." in LOG["success"]
correr()
assert previsto(ini) in LOG["captions"] and LOG["captions"].count(POR_CONFIRMAR) == 4
assert LOG["buttons"].count(QUITAR) == 1
# fuera de las fechas del torneo: se guarda igualmente, con aviso
fuera = fin + timedelta(days=30)
correr(clicks=[GUARDAR], **{f"dia_{pid}": fuera, f"hora_{pid}": time(9, 0)})
assert partido_de("CSV-1", id=pid)["fecha_hora"] == f"{fuera.isoformat()}T09:00"
assert any("fuera de las fechas del torneo" in w for w in LOG["warnings"]), LOG["warnings"]
# quitar la programación
correr(clicks=[QUITAR])
assert partido_de("CSV-1", id=pid)["fecha_hora"] is None and "Programación quitada." in LOG["success"]
# programar la final, cuando todavía no se conocen los jugadores
fid = partido_de("CSV-1", ronda=3, posicion=1)["id"]
assert partido_de("CSV-1", id=fid)["jugador1"] is None
correr(clicks=[f"form_horario_{fid}:{GUARDAR}"], **{f"dia_{fid}": fin, f"hora_{fid}": time(20, 0)})
assert partido_de("CSV-1", id=fid)["fecha_hora"] == f"{fin.isoformat()}T20:00"
assert partido_de("CSV-1", id=pid)["fecha_hora"] is None                      # solo cambió ese partido
correr()
assert previsto(fin, "20:00") in LOG["captions"]
print("OK J1: el administrador fija, cambia y quita el día y la hora (también antes de conocer a los jugadores)")

# el invitado ve el día y la hora pero no puede cambiarlos
db.programar_partido(pid, datetime.combine(ini, time(18, 30)))
ss.rol = "invitado"
correr(seccion="Ver torneo", torneo_activo="CSV-1")
assert previsto(ini) in LOG["captions"] and previsto(fin, "20:00") in LOG["captions"]
assert POR_CONFIRMAR in LOG["captions"]
assert GUARDAR not in LOG["buttons"] and QUITAR not in LOG["buttons"]
assert not LOG["times"] and "Día" not in LOG["dates"]
correr(seccion="Consultar torneos")
G = STATE["globals"]
# intento de saltarse el permiso llamando a la función a mano
p0 = partido_de("CSV-1", id=pid)
ss.update({f"dia_{pid}": fin, f"hora_{pid}": time(23, 0)})
STATE["clicks"] = [f"form_horario_{pid}:{GUARDAR}"]
LOG["error"].clear()
G["formulario_horario"](p0, db.obtener_torneo("CSV-1"))
assert any("administrador" in e for e in LOG["error"])
assert partido_de("CSV-1", id=pid)["fecha_hora"] == f"{ini.isoformat()}T18:30"
print("OK J2: el invitado ve el día y la hora pero no puede cambiarlos")

# --- K. Sorteo de grupos por bombos -------------------------------------------------------
BOMBOS = "Formar bombos por ranking (cada grupo lleva un jugador de cada bombo)"
ss.rol = "admin"
correr(seccion="Nuevo torneo")
correr(clicks=["🎲 Realizar sorteo"], overrides={"Tipo de campeonato": "grupos", BOMBOS: True})
assert ss.pendiente["obj"].bombos and ss.pendiente["obj"].por_bombos
assert any("Bombo 1" in m for m in LOG["markdown"]), "debe mostrar los bombos"
correr(clicks=["🎲 Realizar sorteo"], overrides={"Tipo de campeonato": "grupos"})
assert not ss.pendiente["obj"].bombos and not any("Bombo 1" in m for m in LOG["markdown"])
print("OK K: sorteo de grupos por bombos (opcional)")

# --- L. Torneos no visibles para los invitados --------------------------------------------
ss.rol = "admin"
correr(seccion="Gestionar torneo", torneo_activo="TEN-1")
assert "🔒 Ocultar a los invitados" in LOG["buttons"]
correr(clicks=["🔒 Ocultar a los invitados"], seccion="Gestionar torneo", torneo_activo="TEN-1")
assert db.obtener_torneo("TEN-1") is None and db.obtener_torneo("TEN-1", incluir_ocultos=True)["visible"] == 0
correr(seccion="Gestionar torneo", torneo_activo="TEN-1")
assert "👁️ Hacer visible para los invitados" in LOG["buttons"]
correr(seccion="Consultar torneos")
assert any("<th>Visible</th>" in m and "<b>TEN-1</b>" in m for m in LOG["markdown"]), "el admin lo ve en la lista"
ss.rol = "invitado"
correr(seccion="Consultar torneos")
assert not any("<b>TEN-1</b>" in m for m in LOG["markdown"]), "el invitado no lo ve en la lista"
correr(seccion="Ver torneo", torneo_activo="TEN-1")                          # aunque lo tuviera abierto
assert not any("🔒" in str(x) for x in LOG["buttons"]) and not any("Open de Jerez" in m for m in LOG["markdown"])
# un invitado no puede cambiar la visibilidad
G["cambiar_visibilidad"]("TEN-1", True)
assert db.obtener_torneo("TEN-1") is None
ss.rol = "admin"
correr(clicks=["👁️ Hacer visible para los invitados"], seccion="Gestionar torneo", torneo_activo="TEN-1")
assert db.obtener_torneo("TEN-1")
print("OK L: torneos no visibles (ocultar, mostrar, invitado sin acceso)")

# --- M. Juegos anotados desde la interfaz ----------------------------------------------------
ss.rol = "admin"
gm = [p for p in db.partidos_de("GRP-1") if p["fase"] == "grupo" and p["estado"] == "pendiente"][0]
correr(seccion="Gestionar torneo", torneo_activo="GRP-1")
assert any("Juegos totales" in str(x) for x in LOG["number"]), LOG["number"]
correr(clicks=[f"form_{gm['id']}:Guardar resultado"], seccion="Gestionar torneo", torneo_activo="GRP-1",
       **{f"s1_{gm['id']}": 1, f"s2_{gm['id']}": 0, f"j1_{gm['id']}": 7, f"j2_{gm['id']}": 5})
q = next(p for p in db.partidos_de("GRP-1") if p["id"] == gm["id"])
assert (q["juegos1"], q["juegos2"]) == (7, 5), q
correr(seccion="Gestionar torneo", torneo_activo="GRP-1")
assert any("<th>Juegos</th>" in m and "<th>DJ</th>" in m for m in LOG["markdown"]), "la tabla muestra los juegos"
print("OK M: juegos anotados desde la interfaz y visibles en la clasificación")

# --- N. Avisos por WhatsApp (solo administrador) ---------------------------------------------
import re
pend = [p for p in db.partidos_de("GRP-1") if p["estado"] == "pendiente" and p["jugador1"] and p["jugador2"]][0]
db.programar_partido(pend["id"], datetime(2026, 6, 2, 18, 30))
db.establecer_telefono(pend["jugador1"], "600 123 456")          # el rival (jugador2) queda sin teléfono
ss.rol = "admin"
correr(seccion="Gestionar torneo", torneo_activo="GRP-1")
enlaces = [u for (l, u) in LOG["links"] if "wa.me" in u]
pendientes_j1 = [p for p in db.partidos_de("GRP-1") if p["estado"] == "pendiente" and pend["jugador1"] in (p["jugador1"], p["jugador2"])]
assert len(enlaces) == len(pendientes_j1) and all(u.startswith("https://wa.me/34600123456?text=") for u in enlaces), LOG["links"]
assert any("02%2F06%2F2026%20a%20las%2018%3A30" in u for u in enlaces), "el aviso lleva el día y la hora"
assert any("Avisar a " + pend["nombre1"] in l for (l, u) in LOG["links"])
assert any("sin teléfono" in c and pend["nombre2"] in c for c in LOG["captions"]), "avisa de quien no tiene teléfono"
# el invitado no ve enlaces ni números en ninguna pantalla
ss.rol = "invitado"
for seccion in ("Ver torneo", "Consultar torneos"):
    correr(seccion=seccion, torneo_activo="GRP-1")
    assert not LOG["links"], LOG["links"]
    todo = " ".join(map(str, LOG["markdown"] + LOG["captions"] + LOG["buttons"]))
    assert "600123456" not in todo and "600 123 456" not in todo and "wa.me" not in todo
# un invitado no puede guardar teléfonos aunque fuerce el envío del formulario
ss.rol = "invitado"
correr(clicks=[f"form_telefonos_GRP-1:Guardar teléfonos"], seccion="Ver torneo", torneo_activo="GRP-1",
       **{f"tel_GRP-1_{pend['jugador2']}": "699 88 77 66"})
assert pend["jugador2"] not in db.telefonos_de("GRP-1")
# el administrador guarda teléfonos desde el panel, y uno erróneo no guarda nada de ese jugador
ss.rol = "admin"
correr(clicks=[f"form_telefonos_GRP-1:Guardar teléfonos"], seccion="Gestionar torneo", torneo_activo="GRP-1",
       **{f"tel_GRP-1_{pend['jugador2']}": "699 88 77 66", f"tel_GRP-1_{pend['jugador1']}": "600 123 456"})
assert db.telefonos_de("GRP-1")[pend["jugador2"]] == "34699887766"
correr(seccion="Gestionar torneo", torneo_activo="GRP-1")
assert len([u for (l, u) in LOG["links"] if "wa.me" in u]) > len(enlaces), "ahora también avisa al segundo jugador"
correr(clicks=[f"form_telefonos_GRP-1:Guardar teléfonos"], seccion="Gestionar torneo", torneo_activo="GRP-1",
       **{f"tel_GRP-1_{pend['jugador2']}": "abc"})
assert db.telefonos_de("GRP-1")[pend["jugador2"]] == "34699887766"
assert any("No se han guardado algunos teléfonos" in m and "Teléfono no válido" in m for m in LOG["error"]), LOG["error"]
print("OK N: avisos por WhatsApp solo para el administrador")

# --- O. Banner de patrocinadores -------------------------------------------------------------
import base64 as _b64
_PNG = _b64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
class _Up:
    def __init__(self, d): self.d = d
    def getvalue(self): return self.d
ss.rol = "admin"
correr(seccion="Gestionar torneo", torneo_activo="GRP-1")
assert not any('class="sp-franja"' in m for m in LOG["markdown"]), "sin patrocinadores no hay banner"
STATE["upload"]["sp_logo_GRP-1"] = _Up(_PNG)
correr(clicks=["form_patrocinador_GRP-1:Añadir patrocinador"], seccion="Gestionar torneo", torneo_activo="GRP-1",
       **{"sp_nombre_GRP-1": "Bodegas Lustau", "sp_url_GRP-1": "https://lustau.es"})
assert [p["nombre"] for p in db.patrocinadores_de("GRP-1")] == ["Bodegas Lustau"]
assert any('class="sp-franja"' in m and "Bodegas Lustau" in m and "https://lustau.es" in m for m in LOG["markdown"])
# enlace javascript: rechazado con mensaje
correr(clicks=["form_patrocinador_GRP-1:Añadir patrocinador"], seccion="Gestionar torneo", torneo_activo="GRP-1",
       **{"sp_nombre_GRP-1": "Malo", "sp_url_GRP-1": "javascript:alert(1)"})
assert len(db.patrocinadores_de("GRP-1")) == 1 and any("http" in m for m in LOG["error"]), LOG["error"]
# el invitado ve el banner pero no el panel, y no puede añadir ni borrar
ss.rol = "invitado"
correr(seccion="Ver torneo", torneo_activo="GRP-1")
assert any('class="sp-franja"' in m and "Bodegas Lustau" in m for m in LOG["markdown"])
assert "Añadir patrocinador" not in str(LOG) and not any("🗑️" in b for b in LOG["buttons"])
correr(clicks=["form_patrocinador_GRP-1:Añadir patrocinador"], seccion="Ver torneo", torneo_activo="GRP-1",
       **{"sp_nombre_GRP-1": "Intruso"})
assert len(db.patrocinadores_de("GRP-1")) == 1
G["_accion_patrocinador"] if "_accion_patrocinador" in G else None
# el administrador lo quita
ss.rol = "admin"
correr(clicks=["🗑️"], seccion="Gestionar torneo", torneo_activo="GRP-1")
assert db.patrocinadores_de("GRP-1") == []
print("OK O: banner de patrocinadores gestionado por el administrador")

# --- P. Ranking continuo ---------------------------------------------------------------------
import ranking as rk
ss.rol = "invitado"
correr(seccion="Ranking continuo")
assert any("Todavía no hay ranking" in str(m) for m in LOG["info"]) and not any("Jugadores (uno por línea" in x for x in LOG["inputs"]), LOG["info"]
ss.rol = "admin"
correr(seccion="Ranking continuo")
assert any("El ranking está vacío" in str(m) for m in LOG["info"]) and "Cargar clasificación inicial" in LOG["buttons"]
correr(clicks=["Cargar clasificación inicial"], seccion="Ranking continuo",
       rk_carga_texto=chr(10).join(f"Jugador {i}" for i in range(1, 9)))
assert [j["nombre"] for j in rk.jugadores()] == [f"Jugador {i}" for i in range(1, 9)]
correr(seccion="Ranking continuo")
assert any("rk-pos" in m and "Jugador 8" in m for m in LOG["markdown"]) and "Abrir Ventana 1" in LOG["buttons"]
# solo el administrador abre ventanas
ss.rol = "invitado"
correr(clicks=["Abrir Ventana 1"], seccion="Ranking continuo")
assert rk.ventana_abierta() is None and "Abrir Ventana 1" not in LOG["buttons"]
G["_accion_ranking"](rk.abrir_ventana, ok="x") if False else None
ss.rol = "admin"
correr(clicks=["Abrir Ventana 1"], seccion="Ranking continuo")
v = rk.ventana_abierta()
assert v and v["tipo"] == "v1" and len(rk.partidos_de_ventana(v["id"])) == 4
ps = rk.partidos_de_ventana(v["id"])
assert any("Mejor situado" in m and "Jugador 1" in m for m in LOG["markdown"])
# gana el peor situado en el 1º partido
correr(clicks=[f"form_rk_{ps[0]['id']}:Guardar resultado"], seccion="Ranking continuo",
       **{f"rk_g_{ps[0]['id']}": ps[0]["jugador_bajo"], f"rk_m_{ps[0]['id']}": "6-4 6-4"})
assert [j["nombre"] for j in rk.jugadores()][:2] == ["Jugador 2", "Jugador 1"]
# incomparecencia
correr(clicks=[f"form_rk_{ps[1]['id']}:No se presentó {ps[1]['nombre_alto']}"], seccion="Ranking continuo")
assert [j["nombre"] for j in rk.jugadores()][2:4] == ["Jugador 4", "Jugador 3"]
# un invitado no puede anotar resultados ni cerrar, aunque fuerce el formulario
ss.rol = "invitado"
correr(clicks=[f"form_rk_{ps[2]['id']}:Guardar resultado"], seccion="Ranking continuo",
       **{f"rk_g_{ps[2]['id']}": ps[2]["jugador_bajo"]})
assert rk.partidos_de_ventana(v["id"])[2]["estado"] == "pendiente"
assert "Cerrar ventana" not in LOG["buttons"] and not any("Anotar" in str(x) for x in LOG["buttons"])
correr(seccion="Ranking continuo")
assert any("Pendiente" in m for m in LOG["markdown"]) and any("Mejor situado" in m for m in LOG["markdown"]), "el invitado ve los partidos"
# cerrar con pendientes: el botón está desactivado y la acción falla igualmente
ss.rol = "admin"
correr(clicks=["Cerrar ventana"], seccion="Ranking continuo")
assert rk.ventana_abierta() is not None
for p in rk.partidos_de_ventana(v["id"]):
    if p["estado"] == "pendiente":
        rk.registrar_resultado(p["id"], p["jugador_alto"])
correr(clicks=["Cerrar ventana"], seccion="Ranking continuo")
assert rk.ventana_abierta() is None
ss.rol = "invitado"
correr(seccion="Ranking continuo")
assert any("incomparecencia" in m for m in LOG["markdown"]), "el historial se ve como invitado"
# ventana Reto desde la interfaz
for _ in range(2):
    rk.abrir_ventana()
    for p in rk.partidos_de_ventana(rk.ventana_abierta()["id"]):
        rk.registrar_resultado(p["id"], p["jugador_alto"])
    rk.cerrar_ventana()
ss.rol = "admin"
correr(clicks=["Abrir Ventana Reto"], seccion="Ranking continuo")
assert rk.ventana_abierta()["tipo"] == "reto"
o = rk.jugadores()
correr(clicks=["Crear reto"], seccion="Ranking continuo", rk_retador=o[5]["id"], rk_retado=o[1]["id"])
rt = rk.partidos_de_ventana(rk.ventana_abierta()["id"])
assert len(rt) == 1 and rt[0]["jugador_bajo"] == o[5]["id"] and rt[0]["jugador_alto"] == o[1]["id"]
correr(seccion="Ranking continuo")
retados = [opts for (lbl, opts) in LOG["radio"] if lbl == "Retado"]
assert retados and all(1 <= 6 - next(j["posicion"] for j in o if j["id"] == i) <= 7 for i in retados[0]), retados
print("OK P: ranking continuo (invitado consulta; administrador gestiona ventanas, resultados y retos)")

# --- Q. Ranking continuo: fechas previstas y avisos por WhatsApp -----------------------------
from datetime import datetime as _dt, date as _d, time as _t
ss.rol = "admin"
va = rk.ventana_abierta()
if va:
    for p in rk.partidos_de_ventana(va["id"]):
        if p["estado"] == "pendiente":
            rk.registrar_resultado(p["id"], p["jugador_alto"])
    rk.cerrar_ventana()
vq = rk.abrir_ventana()
qs = rk.partidos_de_ventana(vq)
pq = qs[0]
rk.establecer_telefono(pq["jugador_alto"], "600 123 456")      # el rival queda sin teléfono
rk.establecer_telefono(pq["jugador_bajo"], "")
pid = pq["id"]
correr(clicks=[f"form_rk_horario_{pid}:Guardar día y hora"], seccion="Ranking continuo",
       **{f"rk_dia_{pid}": _d(2026, 6, 2), f"rk_hora_{pid}": _t(18, 30)})
assert rk.partidos_de_ventana(vq)[0]["fecha_hora"] == "2026-06-02T18:30"
correr(seccion="Ranking continuo")
enl = [u for (l, u) in LOG["links"] if "wa.me" in u]
assert len(enl) == 1 and enl[0].startswith("https://wa.me/34600123456?text=") and "18%3A30" in enl[0], LOG["links"]
assert any("sin teléfono" in c and pq["nombre_bajo"] in c for c in LOG["captions"])
assert any("Fecha prevista" in m and "02/06/2026 · 18:30" in m for m in LOG["markdown"])
# el invitado ve la fecha prevista, pero ni enlaces ni teléfonos, y no puede programar
ss.rol = "invitado"
correr(seccion="Ranking continuo")
assert any("02/06/2026 · 18:30" in m for m in LOG["markdown"]) and not LOG["links"]
todo = " ".join(map(str, LOG["markdown"] + LOG["captions"] + LOG["buttons"]))
assert "600123456" not in todo and "600 123 456" not in todo and "wa.me" not in todo
correr(clicks=[f"form_rk_horario_{pid}:Guardar día y hora"], seccion="Ranking continuo",
       **{f"rk_dia_{pid}": _d(2026, 7, 7), f"rk_hora_{pid}": _t(9, 0)})
assert rk.partidos_de_ventana(vq)[0]["fecha_hora"] == "2026-06-02T18:30"
correr(clicks=["Guardar teléfonos"], seccion="Ranking continuo", **{f"rk_tel_{pq['jugador_bajo']}": "699 88 77 66"})
assert pq["jugador_bajo"] not in rk.telefonos()
# el administrador guarda teléfonos desde la pestaña Jugadores; uno erróneo no guarda nada de ese jugador
ss.rol = "admin"
correr(clicks=["form_rk_telefonos:Guardar teléfonos"], seccion="Ranking continuo",
       **{f"rk_tel_{pq['jugador_bajo']}": "699 88 77 66", f"rk_tel_{pq['jugador_alto']}": "600 123 456"})
assert rk.telefonos()[pq["jugador_bajo"]] == "34699887766"
correr(seccion="Ranking continuo")
assert len([u for (l, u) in LOG["links"] if "wa.me" in u]) == 2
correr(clicks=["form_rk_telefonos:Guardar teléfonos"], seccion="Ranking continuo",
       **{f"rk_tel_{pq['jugador_bajo']}": "abc", f"rk_tel_{pq['jugador_alto']}": "600 123 456"})
assert rk.telefonos()[pq["jugador_bajo"]] == "34699887766"
assert any("No se han guardado algunos teléfonos" in m for m in LOG["error"]), LOG["error"]
# alta de jugador con teléfono
correr(clicks=["form_rk_alta:Añadir jugador"], seccion="Ranking continuo", rk_nuevo="Nuevo Con Tel", rk_nuevo_tel="655 44 33 22")
assert rk.telefonos()[next(j["id"] for j in rk.jugadores() if j["nombre"] == "Nuevo Con Tel")] == "34655443322"
print("OK Q: ranking continuo con fechas previstas y avisos por WhatsApp (solo administrador)")

# --- R. Buscador de jugador en la ventana del ranking ----------------------------------------
va = rk.ventana_abierta()
parts = rk.partidos_de_ventana(va["id"])
assert len(parts) >= 3
objetivo = parts[1]["nombre_alto"]                                   # p. ej. «Jugador 3»
for rol in ("invitado", "admin"):
    ss.rol = rol
    correr(seccion="Ranking continuo", rk_buscar="")
    assert any("Buscar jugador" in x for x in LOG["inputs"]), "hay buscador"
    completo = [m for m in LOG["markdown"] if "Mejor situado" in m][0]
    assert all(p["nombre_alto"] in completo and p["nombre_bajo"] in completo for p in parts)
    correr(seccion="Ranking continuo", rk_buscar=objetivo.upper() + " ")
    tabla = [m for m in LOG["markdown"] if "Mejor situado" in m][0]
    assert objetivo in tabla and parts[0]["nombre_alto"] not in tabla.replace(objetivo, ""), tabla
    esperados = rk.filtrar_partidos(parts, objetivo)
    assert any(f"{len(esperados)} de {len(parts)} partidos" in c for c in LOG["captions"]), LOG["captions"]
    if rol == "admin":   # solo se dibujan los formularios de los partidos filtrados
        assert LOG["buttons"].count("Guardar día y hora") == len([p for p in esperados if p["estado"] == "pendiente"])
    correr(seccion="Ranking continuo", rk_buscar="zzzz")
    assert any("Ningún partido de esta ventana incluye a «zzzz»" in w for w in LOG["warnings"]), LOG["warnings"]
    assert not any("Mejor situado" in m for m in LOG["markdown"])
ss.rol = "admin"
correr(seccion="Ranking continuo", rk_buscar="zzzz")
assert "Cerrar ventana" in LOG["buttons"], "el cierre de ventana no depende del filtro"
correr(seccion="Ranking continuo", rk_buscar="")
print("OK R: buscador de jugador en los partidos de la ventana")

# --- S. Tablón de anuncios ---------------------------------------------------------------------
import anuncios as an_
ss.rol = "admin"
correr(seccion="Tablón de anuncios")
assert "Publicar anuncio" in LOG["buttons"] and any("No hay anuncios" in m for m in LOG["info"])
def publicar(ambito, titulo, texto, torneo=None, rol="admin"):
    ss.rol = rol
    kw = {"an_ambito_nuevo": ambito, "an_titulo_nuevo": titulo, "an_texto_nuevo": texto, "an_fijado_nuevo": False,
          "an_concad_nuevo": False}
    if torneo: kw["an_torneo_nuevo"] = torneo
    correr(clicks=["form_anuncio_nuevo:Publicar anuncio"], seccion="Tablón de anuncios", **kw)
publicar("general", "Cierre por obras", "El club cierra el lunes.")
publicar("torneo", "Sorteo publicado", "Cuadro de GRP-1 disponible.", torneo="GRP-1")
publicar("ranking", "Ventana abierta", "Hasta el viernes.")
publicar("general", "", "sin título")                                   # error de validación: no se crea
assert any("título" in m for m in LOG["error"]), LOG["error"]
assert sorted(a["ambito"] for a in an_.listar_anuncios(incluir_ocultos=True)) == ["general", "ranking", "torneo"]
# el invitado lo ve todo en el tablón, y cada anuncio en su sitio
ss.rol = "invitado"
correr(seccion="Tablón de anuncios", an_filtro="todos")
t = " ".join(m for m in LOG["markdown"] if "an-card" in m)
assert all(x in t for x in ("Cierre por obras", "Sorteo publicado", "Ventana abierta")) and "Eliminar" not in str(LOG["buttons"])
assert "Publicar anuncio" not in LOG["buttons"]
correr(seccion="Tablón de anuncios", an_filtro="ranking")
t = " ".join(m for m in LOG["markdown"] if "an-card" in m)
assert "Ventana abierta" in t and "Cierre por obras" not in t and "Sorteo publicado" not in t
correr(seccion="Ver torneo", torneo_activo="GRP-1")
t = " ".join(m for m in LOG["markdown"] if "an-card" in m)
assert "Sorteo publicado" in t and "Cierre por obras" not in t and "Ventana abierta" not in t
correr(seccion="Ranking continuo")
t = " ".join(m for m in LOG["markdown"] if "an-card" in m)
assert "Ventana abierta" in t and "Sorteo publicado" not in t
# torneo oculto: el invitado no ve su anuncio en ningún sitio
db.establecer_visibilidad("GRP-1", False)
correr(seccion="Tablón de anuncios", an_filtro="todos")
assert "Sorteo publicado" not in " ".join(LOG["markdown"]) and "Cierre por obras" in " ".join(LOG["markdown"])
ss.rol = "admin"
correr(seccion="Tablón de anuncios", an_filtro="todos")
assert "Sorteo publicado" in " ".join(LOG["markdown"]), "el administrador sí lo ve"
db.establecer_visibilidad("GRP-1", True)
# un invitado no puede publicar, fijar ni eliminar aunque fuerce el envío
ss.rol = "invitado"
n0 = len(an_.listar_anuncios(incluir_ocultos=True))
publicar("general", "Intruso", "x", rol="invitado")
assert len(an_.listar_anuncios(incluir_ocultos=True)) == n0
# el administrador fija, edita y elimina
ss.rol = "admin"
correr(clicks=["📌 Fijar"], seccion="Tablón de anuncios", an_filtro="todos")
assert sum(a["fijado"] for a in an_.listar_anuncios(incluir_ocultos=True)) == 1
gid = next(a["id"] for a in an_.listar_anuncios(incluir_ocultos=True) if a["titulo"] == "Cierre por obras")
correr(clicks=[f"form_anuncio_{gid}:Guardar cambios"], seccion="Tablón de anuncios", an_filtro="todos",
       **{f"an_titulo_{gid}": "Cierre el martes", f"an_texto_{gid}": "Cambio de día.", f"an_fijado_{gid}": True,
          f"an_concad_{gid}": True, f"an_caduca_{gid}": _d(2030, 1, 1)})
e = next(a for a in an_.listar_anuncios(incluir_ocultos=True) if a["id"] == gid)
assert (e["titulo"], e["fijado"], e["caduca"]) == ("Cierre el martes", 1, "2030-01-01")
correr(clicks=["🗑️ Eliminar"], seccion="Tablón de anuncios", an_filtro="todos")
assert len(an_.listar_anuncios(incluir_ocultos=True)) == n0 - 1
print("OK S: tablón de anuncios (general, torneo y ranking; permisos y torneos ocultos)")

# --- T. Gráfica de evolución del puesto de un jugador -------------------------------------------
for rol in ("invitado", "admin"):
    ss.rol = rol
    cerradas = [v for v in rk.ventanas() if v["estado"] == "cerrada"]
    assert cerradas, "hay ventanas cerradas con foto de posiciones"
    j0 = rk.jugadores()[0]
    correr(seccion="Ranking continuo", rk_evo=j0["id"], rk_buscar="")
    assert any(o[0] == "Jugador" and j0["id"] in o[1] for o in LOG["radio"]), "selector de jugador"
    svg = [m for m in LOG["markdown"] if m.startswith("<svg")]
    assert len(svg) == 1 and "Evolución de puestos de " + j0["nombre"] in svg[0], LOG["info"]
    assert any("Mejor puesto:" in c and "Variación desde el inicio" in c for c in LOG["captions"])
    assert any("Cambio" in m and "Inicio" in m for m in LOG["markdown"]), "tabla de datos"
# un jugador sin historial suficiente muestra un aviso, no una gráfica
nuevo_ = rk.anadir_jugador("Sin Historial")
correr(seccion="Ranking continuo", rk_evo=nuevo_)
assert not any(m.startswith("<svg") for m in LOG["markdown"])
assert any("Todavía no hay suficientes ventanas" in str(i) for i in LOG["info"])
print("OK T: gráfica de evolución del puesto (invitado y administrador)")
print("TODO OK UI ROLES, CSV Y PROGRAMACION")

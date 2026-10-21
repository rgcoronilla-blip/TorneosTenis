"""
Persistencia y gestión de torneos de tenis (SQLite).

Una vez hecho el sorteo (ver sorteo_torneo_tenis.py), `crear_torneo` guarda el
torneo con todos sus partidos para poder anotar resultados. A partir de ahí:

- `registrar_resultado` / `anular_resultado` anotan los marcadores (en sets).
- `programar_partido` fija (o quita) el día y la hora previstos de cada partido.
- Los ganadores avanzan solos a la siguiente ronda y los BYE se resuelven solos.
- En torneos con fase de grupos (de 4 jugadores, o de 3), cuando un grupo
  termina se calcula su clasificación y sus jugadores ocupan automáticamente
  su hueco: 1º y 2º en el cuadro principal; el 3º (y el 4º si el grupo es de 4) en el de consolación.
  El campeón es el ganador del cuadro principal.
- `buscar_torneos` permite consultar por código, nombre y fechas de inicio/fin.

Puntos en la fase de grupos: 2 el ganador, 1 el perdedor y 0 para ambos si el
partido no se juega (`marcar_no_jugado`).

Criterios de clasificación de un grupo (en este orden):
  1. Puntos.
  2. Diferencia de sets.
  3. Diferencia de juegos.
  4. Ranking previo al torneo (el mejor).
El resultado del enfrentamiento directo entre empatados no se tiene en cuenta.

La base de datos es un fichero `torneos.db` junto al código (se puede cambiar
con la variable de entorno TORNEOS_DB).
"""

import math
import os
import re
import sqlite3
import string
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from sorteo_torneo_tenis import Jugador, nombres_de_rondas
from whatsapp import normalizar_telefono

PUNTOS_VICTORIA = 2   # fase de grupos: el ganador suma 2 puntos, el perdedor 1 y un partido no jugado, 0
PUNTOS_DERROTA = 1

DB_PATH = os.environ.get("TORNEOS_DB") or str(Path(__file__).with_name("torneos.db"))

ESQUEMA = """
CREATE TABLE IF NOT EXISTS torneos (
    codigo       TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    tipo         TEXT NOT NULL CHECK (tipo IN ('eliminatorias', 'grupos')),
    fecha_inicio TEXT NOT NULL,
    fecha_fin    TEXT NOT NULL,
    sets_ganar   INTEGER NOT NULL DEFAULT 2,
    estado       TEXT NOT NULL DEFAULT 'sorteado',
    campeon_id   INTEGER,
    visible      INTEGER NOT NULL DEFAULT 1,
    creado       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS jugadores (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    torneo  TEXT NOT NULL REFERENCES torneos(codigo) ON DELETE CASCADE,
    nombre  TEXT NOT NULL,
    ranking INTEGER NOT NULL,
    grupo   TEXT,
    telefono TEXT
);
CREATE TABLE IF NOT EXISTS partidos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    torneo    TEXT NOT NULL REFERENCES torneos(codigo) ON DELETE CASCADE,
    fase      TEXT NOT NULL CHECK (fase IN ('grupo', 'eliminatoria')),
    grupo     TEXT,
    ronda     INTEGER NOT NULL,
    posicion  INTEGER NOT NULL,
    jugador1  INTEGER REFERENCES jugadores(id),
    jugador2  INTEGER REFERENCES jugadores(id),
    origen1   TEXT,
    origen2   TEXT,
    sets1     INTEGER,
    sets2     INTEGER,
    juegos1   INTEGER,
    juegos2   INTEGER,
    marcador  TEXT,
    ganador   INTEGER REFERENCES jugadores(id),
    fecha_hora TEXT,
    cuadro    TEXT,
    sin_jugar INTEGER NOT NULL DEFAULT 0,
    estado    TEXT NOT NULL DEFAULT 'pendiente'
              CHECK (estado IN ('pendiente', 'jugado', 'bye'))
);
CREATE TABLE IF NOT EXISTS patrocinadores (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    torneo  TEXT NOT NULL REFERENCES torneos(codigo) ON DELETE CASCADE,
    nombre  TEXT NOT NULL,
    url     TEXT,
    mime    TEXT NOT NULL,
    imagen  BLOB NOT NULL,
    orden   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_patrocinadores_torneo ON patrocinadores(torneo, orden);
CREATE TABLE IF NOT EXISTS ranking_jugadores (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    posicion INTEGER,
    activo   INTEGER NOT NULL DEFAULT 1,
    telefono TEXT
);
CREATE TABLE IF NOT EXISTS ranking_ventanas (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ciclo   INTEGER NOT NULL,
    tipo    TEXT NOT NULL CHECK (tipo IN ('v1', 'v2', 'v3', 'reto')),
    estado  TEXT NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta', 'cerrada')),
    creada  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cerrada TEXT
);
CREATE TABLE IF NOT EXISTS ranking_partidos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ventana      INTEGER NOT NULL REFERENCES ranking_ventanas(id),
    jugador_alto INTEGER NOT NULL REFERENCES ranking_jugadores(id),
    jugador_bajo INTEGER NOT NULL REFERENCES ranking_jugadores(id),
    pos_alto     INTEGER NOT NULL,
    pos_bajo     INTEGER NOT NULL,
    ganador      INTEGER REFERENCES ranking_jugadores(id),
    marcador     TEXT,
    walkover     INTEGER NOT NULL DEFAULT 0,
    estado       TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'jugado')),
    jugado       TEXT,
    fecha_hora   TEXT
);
CREATE TABLE IF NOT EXISTS ranking_posiciones (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ventana  INTEGER NOT NULL REFERENCES ranking_ventanas(id),
    momento  TEXT NOT NULL CHECK (momento IN ('abrir', 'cerrar')),
    jugador  INTEGER NOT NULL REFERENCES ranking_jugadores(id),
    posicion INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ranking_posiciones ON ranking_posiciones(jugador, ventana);
CREATE TABLE IF NOT EXISTS ranking_movimientos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    partido     INTEGER NOT NULL REFERENCES ranking_partidos(id) ON DELETE CASCADE,
    jugador     INTEGER NOT NULL REFERENCES ranking_jugadores(id),
    pos_antes   INTEGER NOT NULL,
    pos_despues INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS anuncios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ambito     TEXT NOT NULL CHECK (ambito IN ('general', 'torneo', 'ranking')),
    torneo     TEXT REFERENCES torneos(codigo) ON DELETE CASCADE,
    titulo     TEXT NOT NULL,
    texto      TEXT NOT NULL,
    fijado     INTEGER NOT NULL DEFAULT 0,
    caduca     TEXT,
    creado     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((ambito = 'torneo' AND torneo IS NOT NULL) OR (ambito <> 'torneo' AND torneo IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_anuncios ON anuncios(ambito, torneo);
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_partidos_torneo ON partidos(torneo, fase, ronda, posicion);
CREATE INDEX IF NOT EXISTS idx_jugadores_torneo ON jugadores(torneo);
"""


def _migrar(con):
    """Actualiza bases creadas con versiones anteriores (sin tocar sus datos)."""
    if "visible" not in {fila["name"] for fila in con.execute("PRAGMA table_info(torneos)")}:
        try:
            con.execute("ALTER TABLE torneos ADD COLUMN visible INTEGER NOT NULL DEFAULT 1")
        except sqlite3.OperationalError:
            if "visible" not in {f["name"] for f in con.execute("PRAGMA table_info(torneos)")}:
                raise
    if "telefono" not in {f["name"] for f in con.execute("PRAGMA table_info(jugadores)")}:
        try:
            con.execute("ALTER TABLE jugadores ADD COLUMN telefono TEXT")
        except sqlite3.OperationalError:
            if "telefono" not in {f["name"] for f in con.execute("PRAGMA table_info(jugadores)")}:
                raise
    for tabla, col, tipo in (("ranking_jugadores", "telefono", "TEXT"), ("ranking_partidos", "fecha_hora", "TEXT")):
        if col not in {f["name"] for f in con.execute(f"PRAGMA table_info({tabla})")}:
            try:
                con.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
            except sqlite3.OperationalError:  # otra sesión la añadió justo ahora
                if col not in {f["name"] for f in con.execute(f"PRAGMA table_info({tabla})")}:
                    raise
    columnas = {fila["name"] for fila in con.execute("PRAGMA table_info(partidos)")}
    for col in ("juegos1", "juegos2"):
        if col not in columnas:
            try:
                con.execute(f"ALTER TABLE partidos ADD COLUMN {col} INTEGER")
            except sqlite3.OperationalError:
                if col not in {f["name"] for f in con.execute("PRAGMA table_info(partidos)")}:
                    raise
    if "sin_jugar" not in columnas:
        try:
            con.execute("ALTER TABLE partidos ADD COLUMN sin_jugar INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            if "sin_jugar" not in {f["name"] for f in con.execute("PRAGMA table_info(partidos)")}:
                raise
    if "cuadro" not in columnas:
        try:
            con.execute("ALTER TABLE partidos ADD COLUMN cuadro TEXT")
        except sqlite3.OperationalError:
            if "cuadro" not in {f["name"] for f in con.execute("PRAGMA table_info(partidos)")}:
                raise
        # Las eliminatorias de versiones anteriores eran el único cuadro: el principal.
        con.execute("UPDATE partidos SET cuadro = 'principal' WHERE fase = 'eliminatoria' AND cuadro IS NULL")
    if "fecha_hora" not in columnas:
        try:
            con.execute("ALTER TABLE partidos ADD COLUMN fecha_hora TEXT")
        except sqlite3.OperationalError:  # otra sesión la añadió justo ahora
            if "fecha_hora" not in {f["name"] for f in con.execute("PRAGMA table_info(partidos)")}:
                raise


@contextmanager
def _conexion():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    _migrar(con)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _iso(d) -> str:
    if isinstance(d, date):
        return d.isoformat()
    try:
        return date.fromisoformat(str(d)).isoformat()
    except ValueError:
        raise ValueError(f"Fecha no válida: {d!r}")


# ---------------------------------------------------------------------------
# Creación del torneo a partir del sorteo
# ---------------------------------------------------------------------------

def sugerir_codigo(anio: int) -> str:
    """Siguiente código libre con formato TEN-<año>-<nnn>."""
    prefijo = f"TEN-{anio}-"
    with _conexion() as con:
        filas = con.execute("SELECT codigo FROM torneos WHERE codigo LIKE ?", (prefijo + "%",)).fetchall()
    numeros = [int(f["codigo"][len(prefijo):]) for f in filas if f["codigo"][len(prefijo):].isdigit()]
    return f"{prefijo}{max(numeros, default=0) + 1:03d}"


def _slot(valor, ids):
    """Convierte un hueco del cuadro en (id_jugador, origen)."""
    if isinstance(valor, Jugador):
        return ids[valor.nombre], None
    if valor is None or valor == "BYE":
        return None, "BYE"
    return None, str(valor)  # marcador tipo "1º Grupo A"


def _calendario_todos_contra_todos(ids: List[int]) -> List[List[tuple]]:
    """Jornadas de una liguilla (método del círculo)."""
    lista = list(ids)
    if len(lista) % 2:
        lista.append(None)
    n = len(lista)
    jornadas = []
    for _ in range(n - 1):
        pares = []
        for i in range(n // 2):
            a, b = lista[i], lista[n - 1 - i]
            if a is not None and b is not None:
                pares.append((a, b))
        jornadas.append(pares)
        lista = [lista[0]] + [lista[-1]] + lista[1:-1]
    return jornadas


CUADROS = ("principal", "consolacion")


def _crear_eliminatorias(con, codigo, cuadro, draw_size, ids, nombre_cuadro="principal"):
    rondas = int(math.log2(draw_size))
    nombres = nombres_de_rondas(draw_size)
    insertar = (
        "INSERT INTO partidos (torneo, fase, cuadro, ronda, posicion, jugador1, jugador2, origen1, origen2) "
        "VALUES (?, 'eliminatoria', '" + nombre_cuadro + "', ?, ?, ?, ?, ?, ?)"
    )
    for p in range(1, draw_size // 2 + 1):
        j1, o1 = _slot(cuadro[2 * p - 2], ids)
        j2, o2 = _slot(cuadro[2 * p - 1], ids)
        con.execute(insertar, (codigo, 1, p, j1, j2, o1, o2))
    for r in range(2, rondas + 1):
        for p in range(1, draw_size // (2 ** r) + 1):
            o1 = f"Ganador {nombres[r - 2]} #{2 * p - 1}"
            o2 = f"Ganador {nombres[r - 2]} #{2 * p}"
            con.execute(insertar, (codigo, r, p, None, None, o1, o2))


def crear_torneo(*, codigo: str, nombre: str, fecha_inicio, fecha_fin, tipo: str,
                 sets_ganar: int, jugadores: List[Jugador], sorteo, visible: bool = True) -> str:
    """
    Guarda el torneo sorteado con todos sus partidos y devuelve su código. Con `visible=False`
    el torneo queda oculto a los invitados (por ejemplo para hacer pruebas).
    `sorteo` es el objeto ya generado (SorteoTorneo o FaseDeGruposYEliminatorias).
    """
    codigo = (codigo or "").strip().upper()
    nombre = (nombre or "").strip()
    if not re.fullmatch(r"[A-Z0-9_-]+", codigo):
        raise ValueError("El código solo puede contener letras, números, guiones y guiones bajos.")
    if not nombre:
        raise ValueError("El nombre del torneo es obligatorio.")
    f_ini, f_fin = _iso(fecha_inicio), _iso(fecha_fin)
    if f_fin < f_ini:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")
    if tipo not in ("eliminatorias", "grupos"):
        raise ValueError(f"Tipo de campeonato desconocido: {tipo}")
    if sets_ganar not in (1, 2, 3):
        raise ValueError("Los sets necesarios para ganar deben ser 1, 2 o 3.")
    if (tipo == "grupos") != hasattr(sorteo, "grupos"):
        raise ValueError("El sorteo no corresponde al tipo de campeonato indicado.")
    minimo = 3 if tipo == "grupos" else 2
    if len(jugadores) < minimo:
        raise ValueError(f"Se necesitan al menos {minimo} jugadores para este tipo de campeonato.")
    if tipo == "grupos" and len(jugadores) == 5:
        raise ValueError("Con 5 jugadores no se pueden formar grupos de 4 ni de 3.")
    nombres_j = [j.nombre.strip() for j in jugadores]
    if any(not n for n in nombres_j) or len(set(nombres_j)) != len(nombres_j):
        raise ValueError("Los nombres de jugador deben ser únicos y no estar vacíos.")
    if tipo == "grupos":
        if not hasattr(sorteo, "cuadro_consolacion"):
            raise ValueError("El sorteo no incluye el cuadro de consolación.")
        if any(len(g) not in (3, 4) for g in sorteo.grupos):
            raise ValueError("Todos los grupos deben ser de 4 jugadores (o de 3).")

    with _conexion() as con:
        if con.execute("SELECT 1 FROM torneos WHERE UPPER(codigo) = ?", (codigo,)).fetchone():
            raise ValueError(f"Ya existe un torneo con el código {codigo}.")
        con.execute(
            "INSERT INTO torneos (codigo, nombre, tipo, fecha_inicio, fecha_fin, sets_ganar, visible) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (codigo, nombre, tipo, f_ini, f_fin, sets_ganar, 1 if visible else 0),
        )
        ids = {}
        for j in jugadores:
            cur = con.execute(
                "INSERT INTO jugadores (torneo, nombre, ranking, telefono) VALUES (?, ?, ?, ?)",
                (codigo, j.nombre.strip(), j.ranking,
                 normalizar_telefono(getattr(j, "telefono", "")) or None),
            )
            ids[j.nombre] = cur.lastrowid

        if tipo == "grupos":
            letras = string.ascii_uppercase
            for letra, grupo in zip(letras, sorteo.grupos):
                ids_grupo = [ids[j.nombre] for j in grupo]
                con.executemany("UPDATE jugadores SET grupo = ? WHERE id = ?",
                                [(letra, i) for i in ids_grupo])
                for jornada, pares in enumerate(_calendario_todos_contra_todos(ids_grupo), 1):
                    for pos, (a, b) in enumerate(pares, 1):
                        con.execute(
                            "INSERT INTO partidos (torneo, fase, grupo, ronda, posicion, jugador1, jugador2) "
                            "VALUES (?, 'grupo', ?, ?, ?, ?, ?)",
                            (codigo, letra, jornada, pos, a, b),
                        )
        _crear_eliminatorias(con, codigo, sorteo.cuadro, sorteo.draw_size, ids, "principal")
        if tipo == "grupos" and sorteo.cuadro_consolacion:     # con un solo grupo de 3 no hay consolación
            _crear_eliminatorias(con, codigo, sorteo.cuadro_consolacion,
                                 len(sorteo.cuadro_consolacion), ids, "consolacion")
        _recalcular(con, codigo)
    return codigo


# ---------------------------------------------------------------------------
# Clasificación de grupos
# ---------------------------------------------------------------------------

def _tabla_grupo(con, codigo, letra):
    """Devuelve (tabla ordenada, grupo_completo)."""
    jugs = con.execute("SELECT id, nombre, ranking FROM jugadores WHERE torneo = ? AND grupo = ?",
                       (codigo, letra)).fetchall()
    partidos = con.execute("SELECT * FROM partidos WHERE torneo = ? AND fase = 'grupo' AND grupo = ?",
                           (codigo, letra)).fetchall()
    filas = {j["id"]: {"id": j["id"], "nombre": j["nombre"], "ranking": j["ranking"],
                       "PJ": 0, "PG": 0, "PP": 0, "NJ": 0, "SF": 0, "SC": 0, "JF": 0, "JC": 0} for j in jugs}
    # Un partido "no jugado" cuenta como resuelto (el grupo puede completarse) pero da 0 puntos a ambos.
    jugados = [p for p in partidos if p["estado"] == "jugado" and not p["sin_jugar"]]
    for p in partidos:
        if p["estado"] == "jugado" and p["sin_jugar"]:
            filas[p["jugador1"]]["NJ"] += 1
            filas[p["jugador2"]]["NJ"] += 1
    for p in jugados:
        a, b = filas[p["jugador1"]], filas[p["jugador2"]]
        a["PJ"] += 1
        b["PJ"] += 1
        a["SF"] += p["sets1"]
        a["SC"] += p["sets2"]
        b["SF"] += p["sets2"]
        b["SC"] += p["sets1"]
        a["JF"] += p["juegos1"] or 0          # partidos anotados sin juegos cuentan 0
        a["JC"] += p["juegos2"] or 0
        b["JF"] += p["juegos2"] or 0
        b["JC"] += p["juegos1"] or 0
        ganador, perdedor = (a, b) if p["ganador"] == p["jugador1"] else (b, a)
        ganador["PG"] += 1
        perdedor["PP"] += 1
    for f in filas.values():
        f["DS"] = f["SF"] - f["SC"]
        f["DJ"] = f["JF"] - f["JC"]
        f["Pts"] = PUNTOS_VICTORIA * f["PG"] + PUNTOS_DERROTA * f["PP"]

    # Orden: puntos, diferencia de sets, diferencia de juegos y ranking previo.
    # El resultado del partido entre empatados no influye en el desempate.
    tabla = sorted(filas.values(), key=lambda f: (-f["Pts"], -f["DS"], -f["DJ"], f["ranking"]))
    for pos, f in enumerate(tabla, 1):
        f["pos"] = pos
    completo = bool(partidos) and all(p["estado"] == "jugado" for p in partidos)
    return tabla, completo


def clasificaciones(codigo: str) -> Dict[str, dict]:
    """{letra: {"tabla": [...], "completo": bool}} para cada grupo del torneo."""
    with _conexion() as con:
        letras = [r[0] for r in con.execute(
            "SELECT DISTINCT grupo FROM jugadores WHERE torneo = ? AND grupo IS NOT NULL ORDER BY grupo",
            (codigo,))]
        resultado = {}
        for letra in letras:
            tabla, completo = _tabla_grupo(con, codigo, letra)
            resultado[letra] = {"tabla": tabla, "completo": completo}
        return resultado


# ---------------------------------------------------------------------------
# Avance automático: clasificados de grupo, byes y ganadores
# ---------------------------------------------------------------------------

def _recalcular(con, codigo):
    """Recalcula todo lo derivado (huecos de los cuadros, byes, campeón, estado)."""
    t = con.execute("SELECT * FROM torneos WHERE codigo = ?", (codigo,)).fetchone()
    todos = [dict(r) for r in con.execute(
        "SELECT * FROM partidos WHERE torneo = ? AND fase = 'eliminatoria' ORDER BY ronda, posicion",
        (codigo,))]
    if not todos:
        return

    mapa = {}
    if t["tipo"] == "grupos":
        letras = [r[0] for r in con.execute(
            "SELECT DISTINCT grupo FROM jugadores WHERE torneo = ? AND grupo IS NOT NULL", (codigo,))]
        for letra in letras:
            tabla, completo = _tabla_grupo(con, codigo, letra)
            if completo:
                for fila in tabla:
                    mapa[f"{fila['pos']}º Grupo {letra}"] = fila["id"]

    finales = {}
    for cuadro in {p["cuadro"] or "principal" for p in todos}:
        partidos = [p for p in todos if (p["cuadro"] or "principal") == cuadro]
        por_clave = {(p["ronda"], p["posicion"]): p for p in partidos}
        max_ronda = max(p["ronda"] for p in partidos)

        for p in partidos:
            if p["ronda"] == 1:
                for k in (1, 2):
                    origen = p[f"origen{k}"]
                    if origen and "º Grupo " in origen:
                        p[f"jugador{k}"] = mapa.get(origen)

        for r in range(1, max_ronda + 1):
            for p in (x for x in partidos if x["ronda"] == r):
                if p["origen1"] == "BYE" or p["origen2"] == "BYE":
                    otro = p["jugador2"] if p["origen1"] == "BYE" else p["jugador1"]
                    p["ganador"] = otro
                    p["estado"] = "bye" if otro else "pendiente"
                    p["sets1"] = p["sets2"] = p["marcador"] = p["juegos1"] = p["juegos2"] = None
                elif p["estado"] == "jugado" and p["ganador"] not in (p["jugador1"], p["jugador2"]):
                    p["ganador"] = p["sets1"] = p["sets2"] = p["marcador"] = p["juegos1"] = p["juegos2"] = None
                    p["estado"] = "pendiente"
                if r < max_ronda:
                    siguiente = por_clave[(r + 1, (p["posicion"] + 1) // 2)]
                    siguiente["jugador1" if p["posicion"] % 2 == 1 else "jugador2"] = p["ganador"]
        finales[cuadro] = por_clave[(max_ronda, 1)]

    for p in todos:
        con.execute(
            "UPDATE partidos SET jugador1=?, jugador2=?, sets1=?, sets2=?, juegos1=?, juegos2=?, marcador=?, "
            "ganador=?, estado=? "
            "WHERE id=?",
            (p["jugador1"], p["jugador2"], p["sets1"], p["sets2"], p["juegos1"], p["juegos2"], p["marcador"],
             p["ganador"], p["estado"], p["id"]),
        )

    # El campeón es el ganador del cuadro principal; el torneo termina cuando
    # han terminado todos sus cuadros (principal y, si existe, consolación).
    final = finales["principal"]
    campeon = final["ganador"] if final["estado"] == "jugado" else None
    completo = all(f["estado"] == "jugado" for f in finales.values())
    jugados = con.execute("SELECT COUNT(*) FROM partidos WHERE torneo = ? AND estado = 'jugado'",
                          (codigo,)).fetchone()[0]
    estado = "finalizado" if completo else ("en curso" if jugados else "sorteado")
    con.execute("UPDATE torneos SET estado = ?, campeon_id = ? WHERE codigo = ?", (estado, campeon, codigo))


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------

def _verificar_modificable(con, p):
    if p["fase"] == "grupo":
        # Solo afecta si alguien de este grupo ya ha jugado una eliminatoria
        # (los demás grupos pueden seguir anotando resultados con normalidad).
        if con.execute(
            "SELECT 1 FROM partidos m JOIN jugadores j ON j.id IN (m.jugador1, m.jugador2) "
            "WHERE m.torneo = ? AND m.fase = 'eliminatoria' AND m.estado = 'jugado' "
            "AND j.grupo = ? LIMIT 1", (p["torneo"], p["grupo"])).fetchone():
            raise ValueError("No se puede modificar un resultado de este grupo porque algún jugador "
                             "del grupo ya ha disputado partidos de eliminatorias.")
    else:
        siguiente = con.execute(
            "SELECT estado FROM partidos WHERE torneo = ? AND fase = 'eliminatoria' "
            "AND cuadro IS ? AND ronda = ? AND posicion = ?",
            (p["torneo"], p["cuadro"], p["ronda"] + 1, (p["posicion"] + 1) // 2)
        ).fetchone()
        if siguiente and siguiente["estado"] == "jugado":
            raise ValueError("No se puede modificar este resultado porque el partido de la "
                             "siguiente ronda ya tiene resultado. Anula primero ese resultado.")


def registrar_resultado(partido_id: int, sets1: int, sets2: int, marcador: str = "",
                        juegos1: Optional[int] = None, juegos2: Optional[int] = None) -> None:
    """
    Anota el resultado: sets ganados por cada jugador (gana quien llega a `sets_ganar`) y,
    opcionalmente, el total de juegos ganados por cada uno (desempatan la clasificación de
    grupo después de la diferencia de sets). Si se da uno de los juegos hay que dar los dos.
    """
    with _conexion() as con:
        p = con.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)).fetchone()
        if p is None:
            raise ValueError("El partido no existe.")
        if p["origen1"] == "BYE" or p["origen2"] == "BYE":
            raise ValueError("Un partido con BYE no se juega: el jugador pasa automáticamente.")
        if p["jugador1"] is None or p["jugador2"] is None:
            raise ValueError("Todavía no se conocen los dos jugadores de este partido.")
        sg = con.execute("SELECT sets_ganar FROM torneos WHERE codigo = ?", (p["torneo"],)).fetchone()[0]
        sets1, sets2 = int(sets1), int(sets2)
        valido = (sets1 == sg and 0 <= sets2 < sg) or (sets2 == sg and 0 <= sets1 < sg)
        if not valido:
            raise ValueError(f"Resultado no válido: gana quien llegue a {sg} set(s) y el otro "
                             f"debe tener menos.")
        if (juegos1 is None) != (juegos2 is None):
            raise ValueError("Indica los juegos de los dos jugadores.")
        if juegos1 is not None:
            juegos1, juegos2 = int(juegos1), int(juegos2)
            if not (0 <= juegos1 <= 99 and 0 <= juegos2 <= 99):
                raise ValueError("Los juegos de cada jugador deben estar entre 0 y 99.")
        _verificar_modificable(con, p)
        ganador = p["jugador1"] if sets1 > sets2 else p["jugador2"]
        con.execute(
            "UPDATE partidos SET sets1=?, sets2=?, juegos1=?, juegos2=?, marcador=?, ganador=?, "
            "estado='jugado', sin_jugar=0 "
            "WHERE id=?",
            (sets1, sets2, juegos1, juegos2, (marcador or "").strip() or None, ganador, partido_id),
        )
        _recalcular(con, p["torneo"])


def marcar_no_jugado(partido_id: int) -> None:
    """
    Indica que un partido de la fase de grupos no se juega: ambos jugadores suman 0 puntos
    en él y el partido deja de estar pendiente. Se puede deshacer con `anular_resultado`
    o anotando después un resultado.
    """
    with _conexion() as con:
        p = con.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)).fetchone()
        if p is None:
            raise ValueError("El partido no existe.")
        if p["fase"] != "grupo":
            raise ValueError("Solo los partidos de la fase de grupos pueden quedar sin jugar: "
                             "en las eliminatorias alguien tiene que ganar.")
        _verificar_modificable(con, p)
        con.execute("UPDATE partidos SET sets1=NULL, sets2=NULL, juegos1=NULL, juegos2=NULL, marcador=NULL, ganador=NULL, "
                    "estado='jugado', sin_jugar=1 WHERE id=?", (partido_id,))
        _recalcular(con, p["torneo"])


def programar_partido(partido_id: int, fecha_hora: Optional[datetime]) -> None:
    """
    Fija el día y la hora previstos de un partido, o los quita si `fecha_hora` es None.
    La hora es la local del club (sin zona horaria) y se guarda al minuto. Se puede programar
    un partido aunque todavía no se conozcan sus jugadores; los partidos con BYE no se programan
    porque no se juegan.
    """
    if fecha_hora is None:
        valor = None
    else:
        if not isinstance(fecha_hora, datetime):
            raise ValueError("Indica el día y la hora del partido.")
        if fecha_hora.tzinfo is not None:
            raise ValueError("La hora debe indicarse sin zona horaria (hora local del club).")
        if not 2000 <= fecha_hora.year <= 2100:
            raise ValueError("El año del partido debe estar entre 2000 y 2100.")
        valor = fecha_hora.strftime("%Y-%m-%dT%H:%M")
    with _conexion() as con:
        p = con.execute("SELECT origen1, origen2 FROM partidos WHERE id = ?", (partido_id,)).fetchone()
        if p is None:
            raise ValueError("El partido no existe.")
        if "BYE" in (p["origen1"], p["origen2"]):
            raise ValueError("Un partido con BYE no se juega, así que no se puede programar.")
        con.execute("UPDATE partidos SET fecha_hora = ? WHERE id = ?", (valor, partido_id))


def anular_resultado(partido_id: int) -> None:
    with _conexion() as con:
        p = con.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)).fetchone()
        if p is None:
            raise ValueError("El partido no existe.")
        if p["estado"] != "jugado":
            raise ValueError("Este partido no tiene resultado que anular.")
        _verificar_modificable(con, p)
        con.execute("UPDATE partidos SET sets1=NULL, sets2=NULL, juegos1=NULL, juegos2=NULL, marcador=NULL, ganador=NULL, "
                    "estado='pendiente', sin_jugar=0 WHERE id=?", (partido_id,))
        _recalcular(con, p["torneo"])


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def establecer_visibilidad(codigo: str, visible: bool) -> None:
    """Muestra u oculta un torneo a los invitados (el administrador siempre lo ve)."""
    with _conexion() as con:
        cur = con.execute("UPDATE torneos SET visible = ? WHERE codigo = ?", (1 if visible else 0, codigo))
        if cur.rowcount == 0:
            raise ValueError("El torneo no existe.")


def buscar_torneos(codigo: str = "", nombre: str = "", inicio: Optional[tuple] = None,
                   fin: Optional[tuple] = None, incluir_ocultos: bool = False) -> List[dict]:
    """
    Busca torneos. `codigo` y `nombre` son búsquedas parciales (sin distinguir
    mayúsculas). `inicio` y `fin` son rangos opcionales (desde, hasta) sobre la
    fecha de inicio y la de fin del torneo; cualquiera de los extremos puede ser None.
    Los torneos no visibles solo se devuelven con `incluir_ocultos=True` (administrador).
    """
    sql = ("SELECT t.*, "
           "(SELECT COUNT(*) FROM jugadores j WHERE j.torneo = t.codigo) AS num_jugadores, "
           "(SELECT nombre FROM jugadores j WHERE j.id = t.campeon_id) AS campeon "
           "FROM torneos t WHERE 1 = 1")
    params: list = []
    if not incluir_ocultos:
        sql += " AND t.visible = 1"
    if codigo and codigo.strip():
        sql += " AND t.codigo LIKE ? ESCAPE '\\'"
        params.append(f"%{_escapar_like(codigo.strip())}%")
    if nombre and nombre.strip():
        sql += " AND t.nombre LIKE ? ESCAPE '\\'"
        params.append(f"%{_escapar_like(nombre.strip())}%")
    for columna, rango in (("fecha_inicio", inicio), ("fecha_fin", fin)):
        if rango:
            desde, hasta = rango
            if desde:
                sql += f" AND t.{columna} >= ?"
                params.append(_iso(desde))
            if hasta:
                sql += f" AND t.{columna} <= ?"
                params.append(_iso(hasta))
    sql += " ORDER BY t.fecha_inicio DESC, t.codigo"
    with _conexion() as con:
        return [dict(r) for r in con.execute(sql, params)]


def obtener_torneo(codigo: str, incluir_ocultos: bool = False) -> Optional[dict]:
    """El torneo, o None si no existe o está oculto (salvo `incluir_ocultos=True`)."""
    with _conexion() as con:
        fila = con.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM jugadores j WHERE j.torneo = t.codigo) AS num_jugadores, "
            "(SELECT nombre FROM jugadores j WHERE j.id = t.campeon_id) AS campeon "
            "FROM torneos t WHERE t.codigo = ?", (codigo,)).fetchone()
        if fila is None or (not fila["visible"] and not incluir_ocultos):
            return None
        return dict(fila)


def partidos_de(codigo: str) -> List[dict]:
    """Todos los partidos del torneo con nombres de jugador y ganador."""
    with _conexion() as con:
        filas = con.execute(
            "SELECT p.*, j1.nombre AS nombre1, j1.ranking AS ranking1, "
            "j2.nombre AS nombre2, j2.ranking AS ranking2, g.nombre AS nombre_ganador "
            "FROM partidos p "
            "LEFT JOIN jugadores j1 ON j1.id = p.jugador1 "
            "LEFT JOIN jugadores j2 ON j2.id = p.jugador2 "
            "LEFT JOIN jugadores g ON g.id = p.ganador "
            "WHERE p.torneo = ? ORDER BY p.fase, p.cuadro, p.ronda, p.posicion", (codigo,)).fetchall()
        return [dict(f) for f in filas]


# ---------------------------------------------------------------------------
# Teléfonos (solo administrador: nunca forman parte de las consultas de los invitados)
# ---------------------------------------------------------------------------

def telefonos_de(codigo: str) -> dict:
    """{id_jugador: teléfono normalizado} de los jugadores del torneo que tienen teléfono."""
    with _conexion() as con:
        filas = con.execute("SELECT id, telefono FROM jugadores WHERE torneo = ? AND telefono IS NOT NULL "
                            "AND telefono <> ''", (codigo,)).fetchall()
    return {f["id"]: f["telefono"] for f in filas}


def jugadores_de(codigo: str) -> List[dict]:
    """Jugadores del torneo SIN teléfono (seguro para cualquier usuario)."""
    with _conexion() as con:
        filas = con.execute("SELECT id, nombre, ranking, grupo FROM jugadores WHERE torneo = ? "
                            "ORDER BY ranking, nombre", (codigo,)).fetchall()
    return [dict(f) for f in filas]


def establecer_telefono(jugador_id: int, telefono) -> str:
    """Guarda (o borra, si va vacío) el teléfono de un jugador. Devuelve el valor normalizado."""
    normal = normalizar_telefono(telefono)
    with _conexion() as con:
        cur = con.execute("UPDATE jugadores SET telefono = ? WHERE id = ?", (normal or None, jugador_id))
        if cur.rowcount == 0:
            raise ValueError("Jugador no encontrado.")
    return normal


# ---------------------------------------------------------------------------
# Patrocinadores del torneo (banner superior; los gestiona el administrador, los ve todo el mundo)
# ---------------------------------------------------------------------------

MAX_PATROCINADORES = 12
MAX_BYTES_LOGO = 800_000
_FIRMAS_IMAGEN = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF87a", "image/gif"),
                  (b"GIF89a", "image/gif"))


def tipo_de_imagen(datos: bytes) -> Optional[str]:
    """Tipo MIME según el contenido real (no el nombre del fichero). SVG no se admite: puede llevar scripts."""
    for firma, mime in _FIRMAS_IMAGEN:
        if datos.startswith(firma):
            return mime
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar_url_patrocinador(url) -> str:
    """"" o una URL http(s) limpia; ValueError en otro caso (nada de javascript:, data:…)."""
    url = (url or "").strip()
    if not url:
        return ""
    if len(url) > 300 or not re.fullmatch(r"https?://[^\s<>\"']+", url, flags=re.IGNORECASE) or "." not in url:
        raise ValueError("La dirección web debe empezar por http:// o https:// (y no puede llevar espacios).")
    return url


def patrocinadores_de(codigo: str) -> List[dict]:
    with _conexion() as con:
        return [dict(f) for f in con.execute(
            "SELECT id, nombre, url, mime, imagen, orden FROM patrocinadores WHERE torneo = ? "
            "ORDER BY orden, id", (codigo,))]


def anadir_patrocinador(codigo: str, nombre: str, imagen: bytes, url: str = "") -> int:
    nombre = " ".join((nombre or "").split())
    if not nombre or len(nombre) > 80:
        raise ValueError("El nombre del patrocinador es obligatorio (máximo 80 caracteres).")
    url = validar_url_patrocinador(url)
    if not imagen:
        raise ValueError("Falta la imagen del logotipo.")
    if len(imagen) > MAX_BYTES_LOGO:
        raise ValueError(f"El logotipo pesa demasiado (máximo {MAX_BYTES_LOGO // 1000} KB).")
    mime = tipo_de_imagen(imagen)
    if mime is None:
        raise ValueError("El logotipo debe ser una imagen PNG, JPG, GIF o WEBP.")
    with _conexion() as con:
        if not con.execute("SELECT 1 FROM torneos WHERE codigo = ?", (codigo,)).fetchone():
            raise ValueError("Torneo no encontrado.")
        fila = con.execute("SELECT COUNT(*) AS n, COALESCE(MAX(orden), 0) AS m FROM patrocinadores "
                           "WHERE torneo = ?", (codigo,)).fetchone()
        if fila["n"] >= MAX_PATROCINADORES:
            raise ValueError(f"Un torneo admite como máximo {MAX_PATROCINADORES} patrocinadores.")
        return con.execute(
            "INSERT INTO patrocinadores (torneo, nombre, url, mime, imagen, orden) VALUES (?, ?, ?, ?, ?, ?)",
            (codigo, nombre, url or None, mime, imagen, fila["m"] + 1)).lastrowid


def actualizar_patrocinador(patrocinador_id: int, nombre: str, url: str = "") -> None:
    nombre = " ".join((nombre or "").split())
    if not nombre or len(nombre) > 80:
        raise ValueError("El nombre del patrocinador es obligatorio (máximo 80 caracteres).")
    url = validar_url_patrocinador(url)
    with _conexion() as con:
        cur = con.execute("UPDATE patrocinadores SET nombre = ?, url = ? WHERE id = ?",
                          (nombre, url or None, patrocinador_id))
        if cur.rowcount == 0:
            raise ValueError("Patrocinador no encontrado.")


def eliminar_patrocinador(patrocinador_id: int) -> None:
    with _conexion() as con:
        cur = con.execute("DELETE FROM patrocinadores WHERE id = ?", (patrocinador_id,))
        if cur.rowcount == 0:
            raise ValueError("Patrocinador no encontrado.")


def mover_patrocinador(patrocinador_id: int, delta: int) -> None:
    """Sube (delta=-1) o baja (+1) un patrocinador en el banner."""
    with _conexion() as con:
        fila = con.execute("SELECT torneo FROM patrocinadores WHERE id = ?", (patrocinador_id,)).fetchone()
        if fila is None:
            raise ValueError("Patrocinador no encontrado.")
        ids = [f["id"] for f in con.execute(
            "SELECT id FROM patrocinadores WHERE torneo = ? ORDER BY orden, id", (fila["torneo"],))]
        i = ids.index(patrocinador_id)
        j = i + (1 if delta > 0 else -1)
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
        con.executemany("UPDATE patrocinadores SET orden = ? WHERE id = ?",
                        [(n, pid) for n, pid in enumerate(ids, 1)])

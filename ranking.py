"""
Ranking continuo del club: una clasificación siempre abierta que se mueve por «ventanas».

Un ciclo tiene cuatro ventanas, que se abren de una en una y en este orden:

  Ventana 1 (salto 1)   partidos entre jugadores contiguos.
  Ventana 2 (salto 3)   cada jugador juega contra el que tiene 3 puestos por encima.
  Ventana 3 (salto 5)   cada jugador juega contra el que tiene 5 puestos por encima.
  Ventana Reto          retos voluntarios a un jugador hasta 7 puestos por encima.

Al abrir cada ventana se usan las posiciones del momento («tras la ventana 1 se reposicionan los números»).

Emparejamientos de las ventanas 1-3 (salto g): las posiciones se agrupan en bloques de 2g
(1..2g, 2g+1..4g, …) y en cada bloque se juega p contra p+g. Así nadie juega dos veces en la misma
ventana; los jugadores de un último bloque incompleto sin rival descansan.

Resultado: si gana el jugador peor situado, toma la posición del perdedor y este ocupa la que dejó el
ganador (intercambio). Si gana el mejor situado, nadie se mueve. Como el intercambio solo afecta a los dos
jugadores del partido, el orden en que se anoten los resultados de una ventana no influye.
"""

import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from torneo import _conexion
from whatsapp import normalizar_telefono

TIPOS = ("v1", "v2", "v3", "reto")
SALTOS = {"v1": 1, "v2": 3, "v3": 5}
MAX_RETO = 7
NOMBRES = {"v1": "Ventana 1", "v2": "Ventana 2", "v3": "Ventana 3", "reto": "Ventana Reto"}
MAX_NOMBRE = 100


def emparejar_ventana(n: int, salto: int) -> List[Tuple[int, int]]:
    """Pares (posición alta, posición baja) de una ventana con `n` jugadores."""
    pares = []
    for inicio in range(1, n + 1, 2 * salto):
        for p in range(inicio, inicio + salto):
            if p + salto <= n:
                pares.append((p, p + salto))
    return pares


def _limpiar(nombre) -> str:
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        raise ValueError("El nombre del jugador es obligatorio.")
    if len(nombre) > MAX_NOMBRE:
        raise ValueError(f"El nombre supera los {MAX_NOMBRE} caracteres.")
    return nombre


# ---------------------------------------------------------------------------
# Jugadores
# ---------------------------------------------------------------------------

def jugadores() -> List[dict]:
    """Jugadores activos por posición."""
    with _conexion() as con:
        return [dict(f) for f in con.execute(
            "SELECT id, nombre, posicion FROM ranking_jugadores WHERE activo = 1 ORDER BY posicion")]


def _siguiente_posicion(con) -> int:
    return con.execute("SELECT COUNT(*) FROM ranking_jugadores WHERE activo = 1").fetchone()[0] + 1


def anadir_jugador(nombre, telefono="") -> int:
    """Añade un jugador al final del ranking (o reactiva uno dado de baja con el mismo nombre)."""
    nombre = _limpiar(nombre)
    telefono = normalizar_telefono(telefono) or None
    with _conexion() as con:
        fila = con.execute("SELECT id, activo FROM ranking_jugadores WHERE nombre = ?", (nombre,)).fetchone()
        pos = _siguiente_posicion(con)
        if fila is None:
            return con.execute("INSERT INTO ranking_jugadores (nombre, posicion, telefono) VALUES (?, ?, ?)",
                               (nombre, pos, telefono)).lastrowid
        if fila["activo"]:
            raise ValueError(f"«{nombre}» ya está en el ranking.")
        con.execute("UPDATE ranking_jugadores SET activo = 1, posicion = ?, telefono = COALESCE(?, telefono) "
                    "WHERE id = ?", (pos, telefono, fila["id"]))
        return fila["id"]


def cargar_jugadores_iniciales(nombres: List[str], telefonos: Optional[List[str]] = None) -> int:
    """
    Carga la clasificación inicial (de la primera a la última posición). Solo con el ranking vacío.
    `telefonos`, si se da, va en el mismo orden que `nombres` (vacío = sin teléfono).
    """
    limpios = [_limpiar(n) for n in nombres]
    tels = [normalizar_telefono(x) or None for x in (telefonos or [""] * len(limpios))]
    if len(tels) != len(limpios):
        raise ValueError("Debe haber un teléfono (o vacío) por jugador.")
    if len({n.casefold() for n in limpios}) != len(limpios):
        raise ValueError("Hay nombres repetidos en la lista.")
    with _conexion() as con:
        if con.execute("SELECT 1 FROM ranking_jugadores").fetchone():
            raise ValueError("El ranking ya tiene jugadores; la carga inicial solo vale con el ranking vacío.")
        con.executemany("INSERT INTO ranking_jugadores (nombre, posicion, telefono) VALUES (?, ?, ?)",
                        [(n, i, tel) for i, (n, tel) in enumerate(zip(limpios, tels), 1)])
    return len(limpios)


def telefonos() -> Dict[int, str]:
    """{id_jugador: teléfono} de los jugadores activos con teléfono. Solo para el administrador."""
    with _conexion() as con:
        return {f["id"]: f["telefono"] for f in con.execute(
            "SELECT id, telefono FROM ranking_jugadores WHERE activo = 1 AND telefono IS NOT NULL AND telefono <> ''")}


def establecer_telefono(jugador_id: int, telefono) -> str:
    """Guarda (o borra, si va vacío) el teléfono de un jugador del ranking."""
    normal = normalizar_telefono(telefono)
    with _conexion() as con:
        cur = con.execute("UPDATE ranking_jugadores SET telefono = ? WHERE id = ? AND activo = 1",
                          (normal or None, jugador_id))
        if cur.rowcount == 0:
            raise ValueError("Jugador no encontrado.")
    return normal


def dar_de_baja(jugador_id: int) -> None:
    """Quita a un jugador del ranking (su historial se conserva); los de abajo suben un puesto."""
    with _conexion() as con:
        if con.execute("SELECT 1 FROM ranking_ventanas WHERE estado = 'abierta'").fetchone():
            raise ValueError("No se puede dar de baja a nadie con una ventana abierta: ciérrala primero.")
        fila = con.execute("SELECT posicion FROM ranking_jugadores WHERE id = ? AND activo = 1",
                           (jugador_id,)).fetchone()
        if fila is None:
            raise ValueError("Jugador no encontrado.")
        con.execute("UPDATE ranking_jugadores SET activo = 0, posicion = NULL WHERE id = ?", (jugador_id,))
        con.execute("UPDATE ranking_jugadores SET posicion = posicion - 1 WHERE activo = 1 AND posicion > ?",
                    (fila["posicion"],))


# ---------------------------------------------------------------------------
# Ventanas
# ---------------------------------------------------------------------------

def ventana_abierta() -> Optional[dict]:
    with _conexion() as con:
        f = con.execute("SELECT * FROM ranking_ventanas WHERE estado = 'abierta'").fetchone()
        return dict(f) if f else None


def ventanas(limite: int = 50) -> List[dict]:
    with _conexion() as con:
        return [dict(f) for f in con.execute(
            "SELECT * FROM ranking_ventanas ORDER BY id DESC LIMIT ?", (limite,))]


def siguiente_ventana() -> Tuple[int, str]:
    """(ciclo, tipo) de la próxima ventana que se abrirá."""
    with _conexion() as con:
        ult = con.execute("SELECT ciclo, tipo FROM ranking_ventanas ORDER BY id DESC LIMIT 1").fetchone()
    if ult is None:
        return 1, "v1"
    if ult["tipo"] == "reto":
        return ult["ciclo"] + 1, "v1"
    return ult["ciclo"], TIPOS[TIPOS.index(ult["tipo"]) + 1]


def _instantanea(con, ventana_id: int, momento: str) -> None:
    """Guarda la posición de todos los jugadores activos al abrir o cerrar una ventana (para las gráficas)."""
    con.execute(
        "INSERT INTO ranking_posiciones (ventana, momento, jugador, posicion) "
        "SELECT ?, ?, id, posicion FROM ranking_jugadores WHERE activo = 1", (ventana_id, momento))


def abrir_ventana() -> int:
    """Abre la siguiente ventana del ciclo; en las ventanas 1-3 genera sus partidos con las posiciones actuales."""
    with _conexion() as con:
        if con.execute("SELECT 1 FROM ranking_ventanas WHERE estado = 'abierta'").fetchone():
            raise ValueError("Ya hay una ventana abierta: ciérrala antes de abrir otra.")
        js = [dict(f) for f in con.execute(
            "SELECT id, posicion FROM ranking_jugadores WHERE activo = 1 ORDER BY posicion")]
    ciclo, tipo = siguiente_ventana()
    if len(js) < 2:
        raise ValueError("Se necesitan al menos 2 jugadores en el ranking.")
    with _conexion() as con:
        vid = con.execute("INSERT INTO ranking_ventanas (ciclo, tipo) VALUES (?, ?)", (ciclo, tipo)).lastrowid
        _instantanea(con, vid, "abrir")
        if tipo in SALTOS:
            por_pos = {j["posicion"]: j["id"] for j in js}
            for alta, baja in emparejar_ventana(len(js), SALTOS[tipo]):
                con.execute(
                    "INSERT INTO ranking_partidos (ventana, jugador_alto, jugador_bajo, pos_alto, pos_bajo) "
                    "VALUES (?, ?, ?, ?, ?)", (vid, por_pos[alta], por_pos[baja], alta, baja))
    return vid


def cerrar_ventana() -> None:
    with _conexion() as con:
        v = con.execute("SELECT id FROM ranking_ventanas WHERE estado = 'abierta'").fetchone()
        if v is None:
            raise ValueError("No hay ninguna ventana abierta.")
        if con.execute("SELECT 1 FROM ranking_partidos WHERE ventana = ? AND estado = 'pendiente'",
                       (v["id"],)).fetchone():
            raise ValueError("Quedan partidos pendientes: anota su resultado (o quita el reto) antes de cerrar.")
        con.execute("UPDATE ranking_ventanas SET estado = 'cerrada', cerrada = CURRENT_TIMESTAMP WHERE id = ?",
                    (v["id"],))
        _instantanea(con, v["id"], "cerrar")


# ---------------------------------------------------------------------------
# Retos
# ---------------------------------------------------------------------------

def crear_reto(retador_id: int, retado_id: int) -> int:
    """Reto de `retador_id` a `retado_id`, que debe estar entre 1 y 7 puestos por encima."""
    if retador_id == retado_id:
        raise ValueError("Un jugador no puede retarse a sí mismo.")
    with _conexion() as con:
        v = con.execute("SELECT id, tipo FROM ranking_ventanas WHERE estado = 'abierta'").fetchone()
        if v is None or v["tipo"] != "reto":
            raise ValueError("Los retos solo se pueden crear con la ventana Reto abierta.")
        pos = {}
        for jid in (retador_id, retado_id):
            f = con.execute("SELECT posicion FROM ranking_jugadores WHERE id = ? AND activo = 1", (jid,)).fetchone()
            if f is None:
                raise ValueError("Jugador no encontrado en el ranking.")
            pos[jid] = f["posicion"]
        dist = pos[retador_id] - pos[retado_id]
        if dist < 1:
            raise ValueError("Solo se puede retar a un jugador que esté por encima.")
        if dist > MAX_RETO:
            raise ValueError(f"Solo se puede retar hasta {MAX_RETO} posiciones por encima (aquí hay {dist}).")
        for jid in (retador_id, retado_id):
            if con.execute("SELECT 1 FROM ranking_partidos WHERE ventana = ? AND ? IN (jugador_alto, jugador_bajo)",
                           (v["id"], jid)).fetchone():
                raise ValueError("Ese jugador ya tiene un reto en esta ventana (como máximo uno por ventana).")
        return con.execute(
            "INSERT INTO ranking_partidos (ventana, jugador_alto, jugador_bajo, pos_alto, pos_bajo) "
            "VALUES (?, ?, ?, ?, ?)", (v["id"], retado_id, retador_id, pos[retado_id], pos[retador_id])).lastrowid


def programar_partido(partido_id: int, fecha_hora: Optional[datetime]) -> None:
    """Día y hora previstos de un partido pendiente de la ventana abierta (None los quita)."""
    with _conexion() as con:
        f = con.execute(
            "SELECT p.estado, v.estado AS vest FROM ranking_partidos p JOIN ranking_ventanas v ON v.id = p.ventana "
            "WHERE p.id = ?", (partido_id,)).fetchone()
        if f is None:
            raise ValueError("Partido no encontrado.")
        if f["vest"] != "abierta" or f["estado"] != "pendiente":
            raise ValueError("Solo se puede programar un partido pendiente de la ventana abierta.")
        valor = None
        if fecha_hora is not None:
            if not isinstance(fecha_hora, datetime):
                raise ValueError("Fecha y hora no válidas.")
            valor = fecha_hora.replace(second=0, microsecond=0).isoformat(timespec="minutes")
        con.execute("UPDATE ranking_partidos SET fecha_hora = ? WHERE id = ?", (valor, partido_id))


def quitar_reto(partido_id: int) -> None:
    with _conexion() as con:
        f = con.execute(
            "SELECT p.estado, v.tipo, v.estado AS vest FROM ranking_partidos p "
            "JOIN ranking_ventanas v ON v.id = p.ventana WHERE p.id = ?", (partido_id,)).fetchone()
        if f is None:
            raise ValueError("Partido no encontrado.")
        if f["tipo"] != "reto" or f["vest"] != "abierta" or f["estado"] != "pendiente":
            raise ValueError("Solo se puede quitar un reto pendiente de la ventana Reto abierta.")
        con.execute("DELETE FROM ranking_partidos WHERE id = ?", (partido_id,))


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------

def registrar_resultado(partido_id: int, ganador_id: Optional[int] = None, marcador: str = "",
                        incomparecencia_de: Optional[int] = None) -> None:
    """
    Anota el ganador (o, si alguien no se presentó, su rival gana por incomparecencia) y recoloca a los jugadores.
    """
    with _conexion() as con:
        p = con.execute(
            "SELECT p.*, v.estado AS vest FROM ranking_partidos p JOIN ranking_ventanas v ON v.id = p.ventana "
            "WHERE p.id = ?", (partido_id,)).fetchone()
        if p is None:
            raise ValueError("Partido no encontrado.")
        if p["vest"] != "abierta":
            raise ValueError("La ventana de este partido ya está cerrada.")
        if p["estado"] != "pendiente":
            raise ValueError("Este partido ya tiene resultado; anúlalo primero si quieres corregirlo.")
        pareja = (p["jugador_alto"], p["jugador_bajo"])
        walkover = incomparecencia_de is not None
        if walkover:
            if incomparecencia_de not in pareja:
                raise ValueError("El jugador que no se presentó no juega este partido.")
            ganador_id = pareja[1] if incomparecencia_de == pareja[0] else pareja[0]
        if ganador_id not in pareja:
            raise ValueError("El ganador debe ser uno de los dos jugadores del partido.")
        perdedor_id = pareja[1] if ganador_id == pareja[0] else pareja[0]
        pos = {j: con.execute("SELECT posicion FROM ranking_jugadores WHERE id = ?", (j,)).fetchone()[0]
               for j in pareja}
        if None in pos.values():
            raise ValueError("Alguno de los jugadores ya no está en el ranking.")
        if pos[ganador_id] > pos[perdedor_id]:  # gana el peor situado: intercambio de posiciones
            con.execute("UPDATE ranking_jugadores SET posicion = ? WHERE id = ?", (pos[perdedor_id], ganador_id))
            con.execute("UPDATE ranking_jugadores SET posicion = ? WHERE id = ?", (pos[ganador_id], perdedor_id))
            con.executemany(
                "INSERT INTO ranking_movimientos (partido, jugador, pos_antes, pos_despues) VALUES (?, ?, ?, ?)",
                [(partido_id, ganador_id, pos[ganador_id], pos[perdedor_id]),
                 (partido_id, perdedor_id, pos[perdedor_id], pos[ganador_id])])
        con.execute("UPDATE ranking_partidos SET ganador = ?, marcador = ?, walkover = ?, estado = 'jugado', "
                    "jugado = CURRENT_TIMESTAMP WHERE id = ?",
                    (ganador_id, " ".join((marcador or "").split())[:60] or None, 1 if walkover else 0, partido_id))


def anular_resultado(partido_id: int) -> None:
    """Deshace un resultado de la ventana abierta si los dos jugadores no se han movido desde entonces."""
    with _conexion() as con:
        p = con.execute(
            "SELECT p.*, v.estado AS vest FROM ranking_partidos p JOIN ranking_ventanas v ON v.id = p.ventana "
            "WHERE p.id = ?", (partido_id,)).fetchone()
        if p is None:
            raise ValueError("Partido no encontrado.")
        if p["vest"] != "abierta":
            raise ValueError("La ventana ya está cerrada: sus resultados no se pueden anular.")
        if p["estado"] != "jugado":
            raise ValueError("Este partido no tiene resultado.")
        movs = [dict(m) for m in con.execute("SELECT * FROM ranking_movimientos WHERE partido = ?", (partido_id,))]
        for m in movs:
            actual = con.execute("SELECT posicion FROM ranking_jugadores WHERE id = ?", (m["jugador"],)).fetchone()
            if actual is None or actual[0] != m["pos_despues"]:
                raise ValueError("Alguno de los jugadores ya se ha movido en el ranking: no se puede anular.")
        for m in movs:
            con.execute("UPDATE ranking_jugadores SET posicion = ? WHERE id = ?", (m["pos_antes"], m["jugador"]))
        con.execute("DELETE FROM ranking_movimientos WHERE partido = ?", (partido_id,))
        con.execute("UPDATE ranking_partidos SET ganador = NULL, marcador = NULL, walkover = 0, "
                    "estado = 'pendiente', jugado = NULL WHERE id = ?", (partido_id,))


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

_SQL_PARTIDOS = (
    "SELECT p.*, a.nombre AS nombre_alto, b.nombre AS nombre_bajo, g.nombre AS nombre_ganador, "
    "v.tipo, v.ciclo FROM ranking_partidos p "
    "JOIN ranking_jugadores a ON a.id = p.jugador_alto JOIN ranking_jugadores b ON b.id = p.jugador_bajo "
    "LEFT JOIN ranking_jugadores g ON g.id = p.ganador JOIN ranking_ventanas v ON v.id = p.ventana ")


def partidos_de_ventana(ventana_id: int) -> List[dict]:
    with _conexion() as con:
        return [dict(f) for f in con.execute(_SQL_PARTIDOS + "WHERE p.ventana = ? ORDER BY p.pos_alto, p.id",
                                             (ventana_id,))]


def historial(limite: int = 30) -> List[dict]:
    """Últimos partidos jugados con los movimientos que provocaron."""
    with _conexion() as con:
        filas = [dict(f) for f in con.execute(
            _SQL_PARTIDOS + "WHERE p.estado = 'jugado' ORDER BY p.jugado DESC, p.id DESC LIMIT ?", (limite,))]
        for f in filas:
            f["subio"] = bool(con.execute("SELECT 1 FROM ranking_movimientos WHERE partido = ?", (f["id"],)).fetchone())
    return filas


def _plano(texto) -> str:
    """Minúsculas y sin acentos: «García» -> «garcia»."""
    sin = "".join(c for c in unicodedata.normalize("NFKD", str(texto or "")) if not unicodedata.combining(c))
    return " ".join(sin.casefold().split())


def filtrar_partidos(partidos: List[dict], texto) -> List[dict]:
    """
    Partidos en los que juega algún jugador cuyo nombre contiene todas las palabras buscadas
    (sin distinguir mayúsculas ni acentos). Con el texto vacío devuelve todos.
    """
    palabras = _plano(texto).split()
    if not palabras:
        return list(partidos)
    return [p for p in partidos
            if any(all(w in _plano(p[campo]) for w in palabras) for campo in ("nombre_alto", "nombre_bajo"))]


_CORTO = {"v1": "V1", "v2": "V2", "v3": "V3", "reto": "Reto"}


def evolucion_jugador(jugador_id: int) -> List[dict]:
    """
    Puestos de un jugador a lo largo del tiempo: «Inicio» (al abrir la primera ventana en la que ya estaba),
    el puesto al cerrar cada ventana y, si hay una ventana abierta, su puesto actual («en curso»).
    Cada punto: {etiqueta, posicion, en_curso}.
    """
    with _conexion() as con:
        actual = con.execute("SELECT posicion FROM ranking_jugadores WHERE id = ? AND activo = 1",
                             (jugador_id,)).fetchone()
        if actual is None:
            raise ValueError("Jugador no encontrado en el ranking.")
        puntos: List[dict] = []
        primera = con.execute(
            "SELECT p.posicion FROM ranking_posiciones p WHERE p.jugador = ? AND p.momento = 'abrir' "
            "ORDER BY p.ventana LIMIT 1", (jugador_id,)).fetchone()
        if primera is not None:
            puntos.append({"etiqueta": "Inicio", "posicion": primera["posicion"], "en_curso": False})
        for f in con.execute(
                "SELECT v.ciclo, v.tipo, p.posicion FROM ranking_posiciones p JOIN ranking_ventanas v ON v.id = p.ventana "
                "WHERE p.jugador = ? AND p.momento = 'cerrar' ORDER BY v.id", (jugador_id,)):
            puntos.append({"etiqueta": f"C{f['ciclo']} {_CORTO[f['tipo']]}", "posicion": f["posicion"],
                           "en_curso": False})
        abierta = con.execute("SELECT ciclo, tipo FROM ranking_ventanas WHERE estado = 'abierta'").fetchone()
        if abierta is not None and puntos:
            puntos.append({"etiqueta": f"C{abierta['ciclo']} {_CORTO[abierta['tipo']]} (en curso)",
                           "posicion": actual["posicion"], "en_curso": True})
    return puntos

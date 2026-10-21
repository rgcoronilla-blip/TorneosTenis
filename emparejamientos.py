"""
Emparejamientos cargados desde un CSV, sin sorteo previo.

Cada tipo de campeonato tiene su propio formato de fichero:

ELIMINATORIAS: el cuadro de primera ronda, un partido por fila y en el orden del cuadro
(el ganador de la fila 1 se cruza con el de la fila 2, el de la 3 con el de la 4, etc.).

    jugador1;jugador2;ranking1;ranking2
    Ana García;BYE;1;
    Elena Torres;Sofía Marín;4;6

  - Un pase directo se indica escribiendo BYE como rival.
  - El número de filas debe ser 1, 2, 4, 8, 16... (si faltan, se rellenan con filas BYE).
  - Las columnas ranking1 y ranking2 son opcionales.

FASE DE GRUPOS + ELIMINATORIAS: la composición de los grupos, una fila por jugador.

    grupo;jugador;ranking
    A;Ana García;1
    A;Elena Torres;4

  - Los grupos se llaman A, B, C... sin saltarse ninguna letra, y tienen 4 jugadores (o 3).
  - La columna ranking es opcional.
  - Dentro de cada grupo se juegan todos contra todos. Al terminar los
    grupos se construyen solos dos cuadros de eliminatorias: el principal (1º y 2º de cada
    grupo) y el de consolación (3º, y 4º en los grupos de 4), sin cruzar jugadores del mismo grupo en la
    primera ronda, igual que cuando el torneo se sortea.

Valen los separadores «,» «;» y tabulador, la cabecera en cualquier combinación de
mayúsculas, con o sin acentos y con espacios o guiones bajos («Jugador 1», «jugador_1»),
y los ficheros en UTF-8 (con o sin BOM) o en la codificación de Excel en español.
Si no hay ranking, el jugador queda con SIN_RANKING: no se muestra y cuenta el último en
los desempates.

Todos los errores del fichero se devuelven juntos (con su número de línea) para
corregirlos de una vez.
"""

import csv
import io
import math
import re
import string
import unicodedata
from typing import Dict, List, Optional, Tuple

from whatsapp import normalizar_telefono
from sorteo_torneo_tenis import (
    SIN_RANKING,
    FaseDeGruposYEliminatorias,
    Jugador,
    generar_cuadro_clasificados,
    generar_cuadro_consolacion,
    nombres_de_rondas,
)

MAX_BYTES = 1_000_000
MAX_FILAS = 2000
MAX_NOMBRE = 100
MAX_ERRORES_MOSTRADOS = 15


class ErrorCSV(ValueError):
    """El fichero tiene uno o varios errores; `errores` los lista (con su número de línea)."""

    def __init__(self, errores: List[str]):
        self.errores = list(errores)
        super().__init__("\n".join(self.errores))


# ---------------------------------------------------------------------------
# Objetos compatibles con torneo.crear_torneo y con la vista previa de la app
# ---------------------------------------------------------------------------

class EliminatoriasManual:
    """Cuadro de eliminatorias definido a mano (equivale a SorteoTorneo ya generado)."""

    manual = True
    num_seeds = 0

    def __init__(self, cuadro: list):
        self.cuadro = list(cuadro)
        self.draw_size = len(self.cuadro)
        self.jugadores = [x for x in self.cuadro if isinstance(x, Jugador)]
        self.byes = self.draw_size - len(self.jugadores)

    def generar(self):
        return self.cuadro

    def nombre_rondas(self):
        return nombres_de_rondas(self.draw_size)


class FaseDeGruposManual(FaseDeGruposYEliminatorias):
    """Grupos definidos a mano; el cuadro de eliminatorias se deriva de ellos."""

    manual = True

    def __init__(self, grupos: List[List[Jugador]]):
        super().__init__([j for g in grupos for j in g])
        self.grupos = [list(g) for g in grupos]
        self.cuadro, self.draw_size = generar_cuadro_clasificados(len(self.grupos), 1, 2)
        self.cuadro_consolacion, self.draw_size_consolacion = generar_cuadro_consolacion([len(g) for g in self.grupos])

    def generar(self):
        return self.grupos, self.cuadro


# ---------------------------------------------------------------------------
# Lectura del fichero
# ---------------------------------------------------------------------------

def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos ni espacios ni signos: «Jugador_1» -> «jugador1»."""
    sin_acentos = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", sin_acentos.lower())


def decodificar(datos) -> str:
    if isinstance(datos, str):
        texto = datos.lstrip("﻿")
    else:
        if len(datos) > MAX_BYTES:
            raise ErrorCSV([f"El fichero es demasiado grande (máximo {MAX_BYTES // 1000} KB)."])
        for codificacion in ("utf-8-sig", "cp1252"):
            try:
                texto = datos.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue
        else:
            texto = datos.decode("latin-1")
    if "\x00" in texto:
        raise ErrorCSV(["El fichero no parece un CSV de texto (¿es un Excel .xlsx?). "
                        "Guárdalo como «CSV (delimitado por comas o punto y coma)»."])
    return texto


def _leer_filas(texto: str) -> Tuple[List[str], List[Tuple[int, List[str]]]]:
    """Devuelve (cabecera normalizada, [(nº de línea, celdas)]) sin las filas vacías."""
    primera = next((linea for linea in texto.splitlines() if linea.strip()), "")
    delimitador = max(",;\t", key=primera.count) if any(d in primera for d in ",;\t") else ","
    lector = csv.reader(io.StringIO(texto), delimiter=delimitador)
    cabecera: Optional[List[str]] = None
    filas: List[Tuple[int, List[str]]] = []
    try:
        for celdas in lector:
            if not any(c.strip() for c in celdas):
                continue
            if cabecera is None:
                cabecera = [_normalizar(c) for c in celdas]
                continue
            filas.append((lector.line_num, [c.strip() for c in celdas]))
            if len(filas) > MAX_FILAS:
                raise ErrorCSV([f"El fichero tiene demasiadas filas (máximo {MAX_FILAS})."])
    except csv.Error as e:
        raise ErrorCSV([f"El fichero no es un CSV válido: {e}"])
    if cabecera is None:
        raise ErrorCSV(["El fichero está vacío."])
    return cabecera, filas


def _localizar_columnas(cabecera: List[str], requeridas: Dict[str, tuple], opcionales: Dict[str, tuple],
                        formato: str) -> Dict[str, int]:
    posiciones: Dict[str, int] = {}
    faltan = []
    for nombre, alias in {**requeridas, **opcionales}.items():
        indice = next((cabecera.index(a) for a in alias if a in cabecera), None)
        if indice is not None:
            posiciones[nombre] = indice
        elif nombre in requeridas:
            faltan.append(nombre)
    if faltan:
        raise ErrorCSV([f"Faltan las columnas: {', '.join(faltan)}. La primera línea debe ser la cabecera: {formato}."])
    return posiciones


def _celda(celdas: List[str], indice: int) -> str:
    return celdas[indice] if indice < len(celdas) else ""


def _limpiar_nombre(valor: str) -> str:
    return " ".join(valor.split())


def _leer_ranking(valor: str, linea: int, columna: str, errores: List[str]) -> int:
    if valor == "":
        return SIN_RANKING
    if re.fullmatch(r"[0-9]+", valor) and 1 <= int(valor) < SIN_RANKING:
        return int(valor)
    errores.append(f"Línea {linea}: «{columna}» debe ser un número entero mayor que 0 (no «{valor}»).")
    return SIN_RANKING


def _cierre(errores: List[str]):
    if errores:
        raise ErrorCSV(errores)


# ---------------------------------------------------------------------------
# Eliminatorias
# ---------------------------------------------------------------------------

FORMATO_ELIMINATORIAS = "jugador1;jugador2 (y opcionalmente ranking1;ranking2)"


def leer_eliminatorias(datos) -> EliminatoriasManual:
    cabecera, filas = _leer_filas(decodificar(datos))
    cols = _localizar_columnas(
        cabecera,
        requeridas={"jugador1": ("jugador1", "jugadora1", "nombre1"),
                    "jugador2": ("jugador2", "jugadora2", "nombre2")},
        opcionales={"ranking1": ("ranking1",), "ranking2": ("ranking2",)},
        formato=FORMATO_ELIMINATORIAS,
    )
    errores: List[str] = []
    cuadro: list = []
    vistos: Dict[str, int] = {}
    for linea, celdas in filas:
        pareja: list = []
        for k in (1, 2):
            nombre = _limpiar_nombre(_celda(celdas, cols[f"jugador{k}"]))
            if nombre.upper() == "BYE":
                pareja.append("BYE")
                continue
            if not nombre:
                errores.append(f"Línea {linea}: falta «jugador{k}» (escribe BYE si pasa directamente).")
                pareja.append(None)
                continue
            if len(nombre) > MAX_NOMBRE:
                errores.append(f"Línea {linea}: el nombre de «jugador{k}» supera los {MAX_NOMBRE} caracteres.")
            ranking = SIN_RANKING
            if f"ranking{k}" in cols:
                ranking = _leer_ranking(_celda(celdas, cols[f"ranking{k}"]), linea, f"ranking{k}", errores)
            clave = nombre.casefold()
            if clave in vistos:
                errores.append(f"Línea {linea}: «{nombre}» ya aparece en la línea {vistos[clave]}.")
            else:
                vistos[clave] = linea
            pareja.append(Jugador(nombre, ranking))
        if pareja[0] == "BYE" and pareja[1] == "BYE":
            errores.append(f"Línea {linea}: un partido no puede ser BYE contra BYE.")
        cuadro.extend(pareja)

    partidos = len(filas)
    if partidos == 0:
        errores.append("El fichero no tiene ningún partido (solo la cabecera).")
    elif partidos & (partidos - 1):
        siguiente = 2 ** math.ceil(math.log2(partidos))
        errores.append(
            f"La primera ronda necesita 1, 2, 4, 8, 16… partidos y el fichero tiene {partidos}. "
            f"Añade {siguiente - partidos} fila(s) hasta llegar a {siguiente}, con BYE como rival "
            f"de quien pase directamente."
        )
    if sum(1 for x in cuadro if isinstance(x, Jugador)) < 2 and partidos:
        errores.append("Hacen falta al menos 2 jugadores.")
    _cierre(errores)
    return EliminatoriasManual(cuadro)


# ---------------------------------------------------------------------------
# Fase de grupos
# ---------------------------------------------------------------------------

FORMATO_GRUPOS = "grupo;jugador (y opcionalmente ranking)"


def _letra_de_grupo(valor: str) -> Optional[str]:
    coincidencia = re.fullmatch(r"(?:grupo\s*)?([a-z])", valor.strip().casefold())
    return coincidencia.group(1).upper() if coincidencia else None


def leer_grupos(datos) -> FaseDeGruposManual:
    cabecera, filas = _leer_filas(decodificar(datos))
    cols = _localizar_columnas(
        cabecera,
        requeridas={"grupo": ("grupo",), "jugador": ("jugador", "jugadora", "nombre")},
        opcionales={"ranking": ("ranking",)},
        formato=FORMATO_GRUPOS,
    )
    errores: List[str] = []
    por_grupo: Dict[str, List[Jugador]] = {}
    vistos: Dict[str, int] = {}
    for linea, celdas in filas:
        valor_grupo = _celda(celdas, cols["grupo"])
        letra = _letra_de_grupo(valor_grupo)
        if letra is None:
            errores.append(f"Línea {linea}: «{valor_grupo}» no es un grupo válido (usa A, B, C…).")
        nombre = _limpiar_nombre(_celda(celdas, cols["jugador"]))
        if not nombre:
            errores.append(f"Línea {linea}: falta el nombre del jugador.")
            continue
        if len(nombre) > MAX_NOMBRE:
            errores.append(f"Línea {linea}: el nombre supera los {MAX_NOMBRE} caracteres.")
        ranking = SIN_RANKING
        if "ranking" in cols:
            ranking = _leer_ranking(_celda(celdas, cols["ranking"]), linea, "ranking", errores)
        clave = nombre.casefold()
        if clave in vistos:
            errores.append(f"Línea {linea}: «{nombre}» ya aparece en la línea {vistos[clave]}.")
        else:
            vistos[clave] = linea
        if letra is not None:
            por_grupo.setdefault(letra, []).append(Jugador(nombre, ranking))

    if not filas:
        errores.append("El fichero no tiene ningún jugador (solo la cabecera).")
    letras = sorted(por_grupo)
    if letras and letras != list(string.ascii_uppercase[:len(letras)]):
        errores.append(f"Los grupos deben llamarse A, B, C… sin saltarse ninguna letra (el fichero tiene: "
                       f"{', '.join(letras)}).")
    for letra in letras:
        if len(por_grupo[letra]) not in (3, 4):
            errores.append(f"El grupo {letra} tiene {len(por_grupo[letra])} jugador(es); debe tener 3 o 4.")
    _cierre(errores)
    return FaseDeGruposManual([por_grupo[letra] for letra in letras])


# ---------------------------------------------------------------------------
# Punto de entrada y plantillas
# ---------------------------------------------------------------------------

FORMATO_JUGADORES = "jugador;ranking[;telefono]"
PLANTILLA_JUGADORES = (
    "jugador;ranking;telefono\n"
    "Ana García;1;600123456\n"
    "Laura Pérez;2;+34 611 22 33 44\n"
    "Marta Ruiz;3;\n"
    "Elena Torres;4;622334455\n"
)
AYUDA_JUGADORES = (
    "Una fila por jugador con las columnas **jugador** y **ranking** (un número entero, 1 es el mejor). "
    "La columna **telefono** es opcional (móvil de 9 cifras o con prefijo, p. ej. +34 600 123 456) y sirve "
    "para avisar por WhatsApp; solo la ve el administrador. Valen los separadores «,» «;» y tabulador."
)


def leer_jugadores(datos) -> List[Jugador]:
    """Lista de jugadores para el sorteo: columnas «jugador» (o «nombre») y «ranking», ambas obligatorias."""
    cabecera, filas = _leer_filas(decodificar(datos))
    cols = _localizar_columnas(
        cabecera,
        requeridas={"jugador": ("jugador", "jugadora", "nombre"), "ranking": ("ranking",)},
        opcionales={"telefono": ("telefono", "movil", "whatsapp", "tlf", "tel")},
        formato=FORMATO_JUGADORES,
    )
    errores: List[str] = []
    jugadores: List[Jugador] = []
    vistos: Dict[str, int] = {}
    for linea, celdas in filas:
        nombre = _limpiar_nombre(_celda(celdas, cols["jugador"]))
        if not nombre:
            errores.append(f"Línea {linea}: falta el nombre del jugador.")
            continue
        if len(nombre) > MAX_NOMBRE:
            errores.append(f"Línea {linea}: el nombre supera los {MAX_NOMBRE} caracteres.")
        valor = _celda(celdas, cols["ranking"])
        if valor == "":
            errores.append(f"Línea {linea}: falta el ranking de «{nombre}».")
            ranking = SIN_RANKING
        else:
            ranking = _leer_ranking(valor, linea, "ranking", errores)
        clave = nombre.casefold()
        if clave in vistos:
            errores.append(f"Línea {linea}: «{nombre}» ya aparece en la línea {vistos[clave]}.")
        else:
            vistos[clave] = linea
        try:
            telefono = normalizar_telefono(_celda(celdas, cols["telefono"])) if "telefono" in cols else ""
        except ValueError as err:
            errores.append(f"Línea {linea}: {err}")
            telefono = ""
        jugadores.append(Jugador(nombre, ranking, telefono))
    if not filas:
        errores.append("El fichero no tiene ningún jugador (solo la cabecera).")
    _cierre(errores)
    return jugadores


def plantilla_jugadores() -> bytes:
    return PLANTILLA_JUGADORES.encode("utf-8-sig")


def cargar(tipo: str, datos):
    """Lee el CSV de emparejamientos según el tipo de campeonato."""
    if tipo == "eliminatorias":
        return leer_eliminatorias(datos)
    if tipo == "grupos":
        return leer_grupos(datos)
    raise ValueError(f"Tipo de campeonato desconocido: {tipo}")


PLANTILLAS = {
    "eliminatorias": (
        "jugador1;jugador2;ranking1;ranking2\n"
        "Ana García;BYE;1;\n"
        "Elena Torres;Sofía Marín;4;6\n"
        "Laura Pérez;BYE;2;\n"
        "Marta Ruiz;Paula Ortiz;3;7\n"
    ),
    "grupos": (
        "grupo;jugador;ranking\n"
        "A;Ana García;1\n"
        "A;Elena Torres;4\n"
        "A;Cristina Vidal;5\n"
        "A;Lucía Navarro;8\n"
        "B;Laura Pérez;2\n"
        "B;Marta Ruiz;3\n"
        "B;Sofía Marín;6\n"
        "B;Paula Ortiz;7\n"
    ),
}

AYUDA = {
    "eliminatorias": (
        "Un partido de primera ronda por fila, en el orden del cuadro (el ganador de la fila 1 se cruza con "
        "el de la fila 2, y así sucesivamente). Columnas: **jugador1**, **jugador2** y, opcionalmente, "
        "**ranking1** y **ranking2**. Para un pase directo escribe **BYE** como rival. El número de filas "
        "debe ser 1, 2, 4, 8, 16…"
    ),
    "grupos": (
        "Una fila por jugador. Columnas: **grupo**, **jugador** y, opcionalmente, **ranking**. Los grupos se "
        "llaman A, B, C… sin saltarse ninguna y tienen 4 jugadores (o 3). Dentro de cada grupo se juega todos "
        "contra todos, y después se construyen solos el cuadro principal (1º y 2º de cada grupo) y el de "
        "consolación (3º, y 4º en los grupos de 4)."
    ),
}


def plantilla(tipo: str) -> bytes:
    """Plantilla descargable (UTF-8 con BOM y «;», para que Excel en español la abra bien)."""
    return PLANTILLAS[tipo].encode("utf-8-sig")


def nombre_plantilla(tipo: str) -> str:
    return f"plantilla_emparejamientos_{tipo}.csv"


def resumen_errores(error: ErrorCSV) -> str:
    """Errores en forma de lista para mostrarlos al usuario (acotada a MAX_ERRORES_MOSTRADOS)."""
    mostrados = error.errores[:MAX_ERRORES_MOSTRADOS]
    texto = "\n".join(f"- {e}" for e in mostrados)
    resto = len(error.errores) - len(mostrados)
    if resto > 0:
        texto += f"\n- … y {resto} error(es) más."
    return texto

"""
Prototipo de aplicación para generar sorteos (draws) de torneos de tenis
en función del ranking de los jugadores.

Tipos de campeonato soportados:

1. "eliminatorias": eliminación directa desde el principio. El perdedor de
   cada partido queda eliminado. Reglas aplicadas (estándar en tenis):
   - El cuadro se redondea a la potencia de 2 superior al número de jugadores.
   - Si sobran huecos, se reparten "byes" (pases directos) a los mejores
     rankeados.
   - Los cabezas de serie se distribuyen de forma que el 1 y el 2 no puedan
     cruzarse hasta la final, el 3 y el 4 no antes de semifinales, etc.
   - El resto de jugadores se sortea de forma aleatoria en los huecos
     restantes.

2. "grupos": fase previa de grupos de 4 jugadores (o de 3 si no se puede formar
   con grupos de 4) repartidos en serpentina para equilibrar el nivel. Cuando
   se han jugado todos los partidos de grupo se disputan dos cuadros de
   eliminatorias: el principal (1º y 2º de cada grupo) y el de consolación
   (el 3º de cada grupo y el 4º de los grupos de 4). Los cuadros se generan
   con marcadores ("1º Grupo A", "4º Grupo B"...) evitando, si es posible,
   que dos jugadores del mismo grupo se crucen en la primera ronda.

Uso:
    python sorteo_torneo_tenis.py                              # ejemplo, eliminatorias
    python sorteo_torneo_tenis.py --tipo grupos                # ejemplo, fase de grupos
    python sorteo_torneo_tenis.py --csv jugadores.csv --tipo grupos
    python sorteo_torneo_tenis.py --csv jugadores.csv --seed 42

El CSV debe tener columnas: jugador;ranking
"""

import argparse
import csv
import math
import random
import string
from dataclasses import dataclass, field
from typing import List, Optional


# Ranking que se asigna a quien no lo tiene (p. ej. en un CSV de emparejamientos sin
# ranking): queda por detrás de todos los demás y no se muestra en pantalla.
SIN_RANKING = 999_999


def etiqueta_jugador(nombre: str, ranking: int) -> str:
    """Nombre con su ranking entre paréntesis, o solo el nombre si no tiene ranking."""
    return nombre if ranking >= SIN_RANKING else f"{nombre} (#{ranking})"


@dataclass
class Jugador:
    nombre: str
    ranking: int  # 1 = mejor ranking; SIN_RANKING si no se conoce
    # Opcional, para los avisos por WhatsApp. No cuenta en la igualdad ni se muestra en repr (dato personal).
    telefono: str = field(default="", compare=False, repr=False)

    def __str__(self):
        return etiqueta_jugador(self.nombre, self.ranking)


def siguiente_potencia_de_dos(n: int) -> int:
    return 1 if n <= 1 else 2 ** math.ceil(math.log2(n))


def numero_de_cabezas_de_serie(draw_size: int, num_jugadores: int) -> int:
    """
    Número estándar de cabezas de serie según el tamaño del cuadro (ATP/WTA):
    128 -> 32, 64 -> 16, 32 -> 8, 16 -> 4, 8 -> 2, 4 -> 1
    """
    tabla = {128: 32, 64: 16, 32: 8, 16: 4, 8: 2, 4: 1, 2: 1}
    seeds = tabla.get(draw_size, max(1, draw_size // 4))
    return min(seeds, num_jugadores)


def plan_eliminatorias(num_jugadores: int):
    """
    Devuelve (tamaño del cuadro, nº de cabezas de serie, nº de byes).
    Los byes se dan siempre a los mejores clasificados; si hay más byes que
    cabezas de serie estándar (p.ej. 9 jugadores en un cuadro de 16 -> 7 byes),
    todos los que reciben bye cuentan como cabezas de serie.
    """
    draw_size = siguiente_potencia_de_dos(num_jugadores)
    byes = draw_size - num_jugadores
    seeds = numero_de_cabezas_de_serie(draw_size, num_jugadores)
    seeds = min(num_jugadores, max(seeds, byes))
    return draw_size, seeds, byes


def orden_de_siembra(size: int) -> List[int]:
    """
    Genera recursivamente el orden estándar en el que los cabezas de serie
    ocupan las posiciones del cuadro, de forma que el 1 y el 2 queden en
    mitades opuestas, el 3-4 en cuartos distintos, etc.
    orden[i] = número de "seed" que ocupa la posición i (0-indexada).
    """
    if size == 1:
        return [1]
    anterior = orden_de_siembra(size // 2)
    resultado = []
    for x in anterior:
        resultado.append(x)
        resultado.append(size + 1 - x)
    return resultado


def nombres_de_rondas(draw_size: int) -> List[str]:
    """Nombre de cada ronda desde la primera (draw_size jugadores) hasta la final."""
    nombres_especiales = {
        2: "Final", 4: "Semifinales", 8: "Cuartos de final",
        16: "Octavos de final", 32: "Dieciseisavos de final",
        64: "Treintaidosavos de final", 128: "Sesentaicuatroavos de final",
    }
    rondas = []
    tamano = draw_size
    while tamano >= 2:
        rondas.append(nombres_especiales.get(tamano, f"Ronda de {tamano}"))
        tamano //= 2
    return rondas


# --------------------------------------------------------------------------
# Tipo de campeonato 1: eliminatorias directas
# --------------------------------------------------------------------------

class SorteoTorneo:
    def __init__(self, jugadores: List[Jugador], seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.jugadores = sorted(jugadores, key=lambda j: j.ranking)
        self.draw_size, self.num_seeds, _ = plan_eliminatorias(len(self.jugadores))
        self.cuadro: List[Optional[Jugador]] = [None] * self.draw_size
        self.byes = 0

    def generar(self):
        cabezas = self.jugadores[:self.num_seeds]
        resto = self.jugadores[self.num_seeds:]

        orden = orden_de_siembra(self.draw_size)
        for posicion, num_seed in enumerate(orden):
            if num_seed <= len(cabezas):
                self.cuadro[posicion] = cabezas[num_seed - 1]

        # Los byes se asignan directamente como rival de los mejores cabezas
        # de serie (nunca dos byes enfrentados entre sí), tal y como se hace
        # en los torneos reales.
        num_byes = self.draw_size - len(self.jugadores)
        for num_seed in range(1, num_byes + 1):
            posicion_seed = self.cuadro.index(cabezas[num_seed - 1])
            posicion_rival = posicion_seed + 1 if posicion_seed % 2 == 0 else posicion_seed - 1
            self.cuadro[posicion_rival] = "BYE"

        huecos_libres = [i for i, slot in enumerate(self.cuadro) if slot is None]
        random.shuffle(huecos_libres)

        for jugador in resto:
            posicion = huecos_libres.pop()
            self.cuadro[posicion] = jugador

        self.byes = num_byes
        return self.cuadro

    def imprimir(self):
        print(f"\n{'='*60}")
        print(f" CUADRO DEL TORNEO ({self.draw_size} plazas, "
              f"{self.num_seeds} cabezas de serie, {self.byes} byes)")
        print(f"{'='*60}\n")
        for i in range(0, self.draw_size, 2):
            j1 = self.cuadro[i] if self.cuadro[i] is not None else "BYE"
            j2 = self.cuadro[i + 1] if self.cuadro[i + 1] is not None else "BYE"
            print(f"  Partido {i//2 + 1:>3}:  {str(j1):<28} vs  {j2}")
        print()

    def nombre_rondas(self):
        return nombres_de_rondas(self.draw_size)


# --------------------------------------------------------------------------
# Tipo de campeonato 2: fase de grupos + eliminatorias
# --------------------------------------------------------------------------

def calcular_tamanos_grupos(n: int) -> List[int]:
    """
    Grupos de 4 jugadores y, solo cuando no se pueda formar con grupos de 4, grupos
    de 3 (se usan los menos posibles). Ejemplos: 8 -> [4, 4]; 10 -> [4, 3, 3];
    11 -> [4, 4, 3]; 9 -> [3, 3, 3]. No es posible con 1, 2 ni 5 jugadores.
    """
    # 4a + 3b = n con b mínimo: 3b ≡ n (mod 4)  =>  b ≡ 3n (mod 4)
    b = (3 * n) % 4 if n > 0 else 0
    if n < 3 or n - 3 * b < 0:
        raise ValueError(
            f"Con fase de grupos los grupos son de 4 jugadores (o de 3 si no se puede formar con grupos "
            f"de 4): hacen falta 3, 4 o 6 o más jugadores. Ahora hay {n}.")
    return [4] * ((n - 3 * b) // 4) + [3] * b


def distribuir_en_grupos(jugadores: List[Jugador], tamanos: List[int]) -> List[List[Jugador]]:
    """
    Reparte a los jugadores (ordenados por ranking) en grupos en forma de
    "serpentina" (1-2-3-4 / 4-3-2-1 / 1-2-3-4...), igual que se hace en los
    sorteos reales para que no todos los mejores rankings caigan en el
    mismo grupo.
    """
    num_grupos = len(tamanos)
    grupos: List[List[Jugador]] = [[] for _ in range(num_grupos)]
    pendientes = list(jugadores)
    de_ida = True
    while pendientes:
        rango = range(num_grupos) if de_ida else range(num_grupos - 1, -1, -1)
        for g in rango:
            if not pendientes:
                break
            if len(grupos[g]) < tamanos[g]:
                grupos[g].append(pendientes.pop(0))
        de_ida = not de_ida
    return grupos


def formar_bombos(jugadores: List[Jugador], tamanos: List[int]) -> List[List[Jugador]]:
    """
    Cuatro bombos ordenados por ranking. Los tres primeros tienen un jugador por grupo
    (los mejores en el bombo 1, los siguientes en el 2…); el cuarto solo tiene tantos
    jugadores como grupos de 4 haya (los de peor ranking). Si todos los grupos son de 3,
    solo hay tres bombos.
    """
    ordenados = sorted(jugadores, key=lambda j: j.ranking)
    g = len(tamanos)
    cuartos = sum(1 for t in tamanos if t == 4)
    cortes = [0, g, 2 * g, 3 * g, 3 * g + cuartos]
    bombos = [ordenados[cortes[i]:cortes[i + 1]] for i in range(4)]
    return [b for b in bombos if b]


def distribuir_por_bombos(jugadores: List[Jugador], tamanos: List[int],
                          rng: Optional[random.Random] = None):
    """
    Sortea los grupos con bombos: cada grupo recibe un jugador de cada bombo (los grupos de 3
    no reciben del cuarto). Devuelve (grupos, bombos). Los grupos de 4 son los primeros (A, B…).
    """
    rng = rng or random.Random()
    bombos = formar_bombos(jugadores, tamanos)
    grupos: List[List[Jugador]] = [[] for _ in tamanos]
    for bombo in bombos:
        candidatos = [i for i, t in enumerate(tamanos) if t > len(grupos[i])]
        # en el cuarto bombo solo entran los grupos de 4 (los primeros)
        candidatos = candidatos[:len(bombo)] if len(bombo) < len(tamanos) else candidatos
        elegidos = list(bombo)
        rng.shuffle(elegidos)
        for i, jugador in zip(candidatos, elegidos):
            grupos[i].append(jugador)
    return grupos, bombos


def generar_cuadro_clasificados(num_grupos: int, mejores: int = 1, peores: int = 2):
    """
    Genera un cuadro de eliminatorias a partir de marcadores de posición
    ("1º Grupo A", "2º Grupo B"...). Por defecto es el cuadro principal
    (1º y 2º de cada grupo); para el cuadro de consolación se usa
    `mejores=3, peores=4` (3º y 4º de cada grupo).

    Los `mejores` de cada grupo hacen de cabezas de serie y se emparejan en la
    primera ronda con el `peores` de OTRO grupo, para que nadie repita rival de
    su fase de grupos (siempre que haya más de un grupo).
    """
    letras = list(string.ascii_uppercase[:num_grupos])
    primeros = [f"{mejores}º Grupo {l}" for l in letras]

    segundos_por_seed = {}
    for i in range(num_grupos):
        seed_rival = 2 * num_grupos - i
        grupo_rival = letras[(i + 1) % num_grupos]
        segundos_por_seed[seed_rival] = f"{peores}º Grupo {grupo_rival}"

    clasificados = list(primeros)
    for seed in range(num_grupos + 1, 2 * num_grupos + 1):
        clasificados.append(segundos_por_seed[seed])

    draw_size = siguiente_potencia_de_dos(len(clasificados))
    orden = orden_de_siembra(draw_size)
    cuadro: List[Optional[str]] = [None] * draw_size
    for posicion, num_seed in enumerate(orden):
        if num_seed <= len(clasificados):
            cuadro[posicion] = clasificados[num_seed - 1]

    # Si el nº de clasificados no es potencia de 2 (nº de grupos impar, p.ej.
    # 3 grupos = 6 clasificados), se reparten byes igual que en eliminatorias.
    num_byes = draw_size - len(clasificados)
    for num_seed in range(1, num_byes + 1):
        posicion_seed = cuadro.index(clasificados[num_seed - 1])
        posicion_rival = posicion_seed + 1 if posicion_seed % 2 == 0 else posicion_seed - 1
        cuadro[posicion_rival] = "BYE"

    return cuadro, draw_size


def generar_cuadro_consolacion(tamanos: List[int]):
    """
    Cuadro de consolación: el 3º de cada grupo y, en los grupos de 4, también el 4º.
    Devuelve (cuadro, draw_size), o ([], 0) si hay menos de 2 jugadores (no hay cuadro).
    Los terceros hacen de cabezas de serie; se evita, si es posible, que en la primera
    ronda se crucen dos jugadores del mismo grupo.
    """
    if all(t == 4 for t in tamanos):
        return generar_cuadro_clasificados(len(tamanos), 3, 4)
    letras = list(string.ascii_uppercase[:len(tamanos)])
    # (etiqueta, grupo) en orden de siembra: primero los terceros, luego los cuartos
    plazas = [(f"3º Grupo {l}", l) for l in letras]
    plazas += [(f"4º Grupo {l}", l) for l, t in zip(reversed(letras), reversed(tamanos)) if t == 4]
    if len(plazas) < 2:
        return [], 0
    draw_size = siguiente_potencia_de_dos(len(plazas))
    orden = orden_de_siembra(draw_size)
    seed_en = {pos: seed for pos, seed in enumerate(orden)}
    cuadro: List[Optional[str]] = [None] * draw_size
    for pos, seed in seed_en.items():
        if seed <= len(plazas):
            cuadro[pos] = plazas[seed - 1][0]
    grupo_de = {etq: g for etq, g in plazas}
    for num_seed in range(1, draw_size - len(plazas) + 1):      # byes para los mejores sembrados
        pos = cuadro.index(plazas[num_seed - 1][0])
        cuadro[pos + 1 if pos % 2 == 0 else pos - 1] = "BYE"

    def conflicto(a, b):
        return a in grupo_de and b in grupo_de and grupo_de[a] == grupo_de[b]

    # Reparación: se intercambian rivales (el de peor siembra de cada pareja) entre parejas.
    def rival(par):
        i, j = 2 * par, 2 * par + 1
        a, b = cuadro[i], cuadro[j]
        if a in grupo_de and b in grupo_de:
            return j if seed_en[j] > seed_en[i] else i
        return None

    for par in range(draw_size // 2):
        i, j = 2 * par, 2 * par + 1
        if not conflicto(cuadro[i], cuadro[j]):
            continue
        r = rival(par)
        for otro in range(draw_size // 2):
            ro = rival(otro)
            if otro == par or ro is None:
                continue
            mio = cuadro[r]
            pareja_r = cuadro[r ^ 1]
            pareja_o = cuadro[ro ^ 1]
            if not conflicto(pareja_r, cuadro[ro]) and not conflicto(pareja_o, mio):
                cuadro[r], cuadro[ro] = cuadro[ro], cuadro[r]
                break
    return cuadro, draw_size


class FaseDeGruposYEliminatorias:
    def __init__(self, jugadores: List[Jugador], por_bombos: bool = False, seed: Optional[int] = None):
        self.por_bombos = por_bombos
        self.seed = seed
        self.bombos: List[List[Jugador]] = []
        self.jugadores = sorted(jugadores, key=lambda j: j.ranking)
        self.grupos: List[List[Jugador]] = []
        self.cuadro: List[Optional[str]] = []              # cuadro principal (1º y 2º)
        self.cuadro_consolacion: List[Optional[str]] = []  # cuadro consolación (3º y 4º)
        self.draw_size = 0
        self.draw_size_consolacion = 0

    def generar(self):
        tamanos = calcular_tamanos_grupos(len(self.jugadores))
        if self.por_bombos:
            rng = random.Random(self.seed) if self.seed is not None else random.Random()
            self.grupos, self.bombos = distribuir_por_bombos(self.jugadores, tamanos, rng)
        else:
            self.grupos = distribuir_en_grupos(self.jugadores, tamanos)
        self.cuadro, self.draw_size = generar_cuadro_clasificados(len(self.grupos), 1, 2)
        self.cuadro_consolacion, self.draw_size_consolacion = generar_cuadro_consolacion(
            [len(g) for g in self.grupos])
        return self.grupos, self.cuadro

    def nombre_rondas(self):
        return nombres_de_rondas(self.draw_size)

    def nombre_rondas_consolacion(self):
        return nombres_de_rondas(self.draw_size_consolacion) if self.draw_size_consolacion else []

    def imprimir(self):
        letras = list(string.ascii_uppercase[:len(self.grupos)])
        if self.bombos:
            print(f"\n{'='*60}\n BOMBOS (por ranking)\n{'='*60}")
            for i, bombo in enumerate(self.bombos, 1):
                print(f"Bombo {i}: " + ", ".join(str(j) for j in bombo))
        print(f"\n{'='*60}")
        print(f" FASE DE GRUPOS ({len(self.grupos)} grupos)")
        print(f"{'='*60}\n")
        for letra, grupo in zip(letras, self.grupos):
            print(f"Grupo {letra}:")
            for j in grupo:
                print(f"   - {j}")
            print()

        print(f"{'='*60}")
        for titulo, cuadro, rondas in (
                ("CUADRO PRINCIPAL (clasifican 1º y 2º de cada grupo)", self.cuadro, self.nombre_rondas()),
                ("CUADRO CONSOLACIÓN (3º de cada grupo y 4º de los grupos de 4)", self.cuadro_consolacion,
                 self.nombre_rondas_consolacion())):
            if not cuadro:
                continue
            print(f"{'='*60}")
            print(f" {titulo}")
            print(f"{'='*60}\n")
            print(f"Primera ronda: {rondas[0]}\n")
            for i in range(0, len(cuadro), 2):
                a = cuadro[i] if cuadro[i] is not None else "BYE"
                b = cuadro[i + 1] if cuadro[i + 1] is not None else "BYE"
                print(f"  Partido {i//2 + 1:>3}:  {a:<20} vs  {b}")
            print("\nEstructura:", " → ".join(rondas), "\n")


def cargar_jugadores_csv(ruta: str) -> List[Jugador]:
    """Lee un CSV con columnas «jugador;ranking» (también vale «nombre» y los separadores «,» «;»)."""
    import emparejamientos  # import tardío: ese módulo depende de este
    with open(ruta, "rb") as f:
        return emparejamientos.leer_jugadores(f.read())


def main():
    parser = argparse.ArgumentParser(description="Sorteo de torneo de tenis por ranking")
    parser.add_argument("--csv", help="Ruta a un CSV con columnas 'nombre,ranking'")
    parser.add_argument("--tipo", choices=["eliminatorias", "grupos"], default="eliminatorias",
                         help="Tipo de campeonato (por defecto: eliminatorias)")
    parser.add_argument("--bombos", action="store_true",
                        help="Con --tipo grupos: forma bombos por ranking y cada grupo lleva un jugador de cada bombo")
    parser.add_argument("--seed", type=int, default=None,
                         help="Semilla aleatoria (opcional, para resultados reproducibles)")
    args = parser.parse_args()

    if args.csv:
        jugadores = cargar_jugadores_csv(args.csv)
    else:
        jugadores = [
            Jugador("Carlos Alcaraz", 1),
            Jugador("Jannik Sinner", 2),
            Jugador("Novak Djokovic", 3),
            Jugador("Alexander Zverev", 4),
            Jugador("Daniil Medvedev", 5),
            Jugador("Andrey Rublev", 6),
            Jugador("Casper Ruud", 7),
            Jugador("Hubert Hurkacz", 8),
            Jugador("Grigor Dimitrov", 9),
            Jugador("Stefanos Tsitsipas", 10),
            Jugador("Taylor Fritz", 11),
            Jugador("Tommy Paul", 12),
        ]

    if args.tipo == "grupos":
        campeonato = FaseDeGruposYEliminatorias(jugadores, por_bombos=args.bombos, seed=args.seed)
        campeonato.generar()
        campeonato.imprimir()
    else:
        sorteo = SorteoTorneo(jugadores, seed=args.seed)
        sorteo.generar()
        sorteo.imprimir()
        print("Estructura de rondas:", " -> ".join(reversed(sorteo.nombre_rondas())))


if __name__ == "__main__":
    main()

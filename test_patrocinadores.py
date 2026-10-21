"""Pruebas del banner de patrocinadores de cada torneo."""
import base64
import os
import tempfile
from datetime import date

import estilo
import torneo as db
from sorteo_torneo_tenis import Jugador, SorteoTorneo

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "sp.db")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
JPG = b"\xff\xd8\xff\xe0" + b"0" * 50
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"0" * 20


def falla(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    raise SystemExit(f"debería fallar: {a}")


js = [Jugador("A", 1), Jugador("B", 2)]
o = SorteoTorneo(js, seed=1); o.generar()
db.crear_torneo(codigo="T1", nombre="T", fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 6, 2),
                tipo="eliminatorias", sets_ganar=2, jugadores=js, sorteo=o)

# 1. alta y orden
assert db.patrocinadores_de("T1") == [] and estilo.patrocinadores_html([]) == ""
a = db.anadir_patrocinador("T1", "  Bodegas   Lustau ", PNG, "https://lustau.es")
b = db.anadir_patrocinador("T1", "Óptica Sol", JPG)
c = db.anadir_patrocinador("T1", "Taller Pepe", WEBP, "HTTP://pepe.example.com/x?a=1&b=2")
ls = db.patrocinadores_de("T1")
assert [p["nombre"] for p in ls] == ["Bodegas Lustau", "Óptica Sol", "Taller Pepe"]
assert [p["mime"] for p in ls] == ["image/png", "image/jpeg", "image/webp"] and ls[1]["url"] is None
db.mover_patrocinador(c, -1); db.mover_patrocinador(a, -1)  # a ya es el primero: no cambia
assert [p["id"] for p in db.patrocinadores_de("T1")] == [a, c, b]
db.mover_patrocinador(a, 1)
assert [p["id"] for p in db.patrocinadores_de("T1")] == [c, a, b]
db.mover_patrocinador(b, 1)  # el último no baja
assert [p["id"] for p in db.patrocinadores_de("T1")] == [c, a, b]
print("OK 1 alta y orden")

# 2. validaciones
falla(db.anadir_patrocinador, "T1", "", PNG)
falla(db.anadir_patrocinador, "T1", "x" * 81, PNG)
falla(db.anadir_patrocinador, "T1", "Sin logo", b"")
falla(db.anadir_patrocinador, "T1", "Falso", b"<svg onload=alert(1)></svg>")
falla(db.anadir_patrocinador, "T1", "Falso", b"MZ\x90\x00" + b"0" * 30)
falla(db.anadir_patrocinador, "T1", "Grande", PNG + b"0" * db.MAX_BYTES_LOGO)
for url in ("javascript:alert(1)", "data:text/html,x", "ftp://x.es", "https://a b.es", "https://x.es/<s>", "//x.es"):
    falla(db.anadir_patrocinador, "T1", "Mala url", PNG, url)
falla(db.anadir_patrocinador, "NOEXISTE", "X", PNG)
assert len(db.patrocinadores_de("T1")) == 3
for i in range(db.MAX_PATROCINADORES - 3):
    db.anadir_patrocinador("T1", f"P{i}", PNG)
falla(db.anadir_patrocinador, "T1", "Uno más", PNG)
print("OK 2 validaciones y límite")

# 3. editar y eliminar
db.actualizar_patrocinador(a, "Lustau SA", "")
assert next(p for p in db.patrocinadores_de("T1") if p["id"] == a)["url"] is None
falla(db.actualizar_patrocinador, a, "X", "javascript:1")
falla(db.actualizar_patrocinador, 9999, "X")
db.eliminar_patrocinador(b)
falla(db.eliminar_patrocinador, b)
assert b not in [p["id"] for p in db.patrocinadores_de("T1")]
print("OK 3 editar y eliminar")

# 4. HTML seguro
malo = {"nombre": '<script>alert(1)</script>"x', "url": 'https://x.es/?a="onmouseover="alert(1)', "mime": "text/html",
        "imagen": PNG}
h = estilo.patrocinadores_html([malo, {"nombre": "Sin web", "url": "javascript:alert(1)", "mime": "image/png", "imagen": PNG}])
assert "<script>" not in h and '"onmouseover="' not in h and "javascript:" not in h and "\n" not in h
assert h.count('<a class="sp-logo"') == 1 and h.count("<span class=\"sp-logo\"") == 1
assert 'rel="noopener noreferrer sponsored"' in h and "data:image/png;base64," in h and "data:text/html" not in h
print("OK 4 HTML escapado")

# 5. se borran con el torneo y no se mezclan entre torneos
o2 = SorteoTorneo(js, seed=2); o2.generar()
db.crear_torneo(codigo="T2", nombre="T2", fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 6, 2),
                tipo="eliminatorias", sets_ganar=2, jugadores=js, sorteo=o2)
assert db.patrocinadores_de("T2") == []
print("OK 5 aislados por torneo")
print("TODO OK PATROCINADORES")

# 6. ancho del banner según el número de logos (máximo tres por fila)
import re
assert [estilo.columnas_patrocinadores(n) for n in range(1, 13)] == [1, 2, 3, 2, 3, 3, 3, 3, 3, 3, 3, 3]
for n in (1, 2, 3, 4, 5, 7, 12):
    h = estilo.patrocinadores_html([{"nombre": f"P{i}", "url": "", "mime": "image/png", "imagen": PNG} for i in range(n)])
    assert f'sp-c{estilo.columnas_patrocinadores(n)}"' in h and h.count('class="sp-logo"') == n, n
assert ".sp-c3 .sp-logo{flex:0 0 calc((100% - 20px) / 3)}" in estilo.css_global()
print("OK 6 columnas del banner")
print("TODO OK PATROCINADORES 2")

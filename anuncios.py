"""
Tablón de anuncios del club. Cada anuncio es General, de un torneo o del Ranking continuo.

Los gestiona el administrador; los invitados solo los leen. Los anuncios de un torneo oculto no los ve
ningún invitado, y un anuncio con fecha de caducidad deja de mostrarse a los invitados al pasar ese día
(el administrador sigue viéndolo marcado como caducado).
"""

from datetime import date
from typing import List, Optional

from torneo import _conexion

AMBITOS = ("general", "torneo", "ranking")
NOMBRES_AMBITO = {"general": "General", "torneo": "Torneo", "ranking": "Ranking continuo"}
MAX_TITULO = 120
MAX_TEXTO = 2000


def _validar(ambito, torneo, titulo, texto, caduca):
    if ambito not in AMBITOS:
        raise ValueError("Ámbito de anuncio no válido.")
    titulo = " ".join((titulo or "").split())
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not titulo:
        raise ValueError("El anuncio necesita un título.")
    if len(titulo) > MAX_TITULO:
        raise ValueError(f"El título supera los {MAX_TITULO} caracteres.")
    if not texto:
        raise ValueError("El anuncio necesita un texto.")
    if len(texto) > MAX_TEXTO:
        raise ValueError(f"El texto supera los {MAX_TEXTO} caracteres.")
    if ambito == "torneo":
        if not torneo:
            raise ValueError("Elige el torneo del anuncio.")
    else:
        torneo = None
    if caduca is not None:
        if not isinstance(caduca, date):
            raise ValueError("Fecha de caducidad no válida.")
        caduca = caduca.isoformat()
    return ambito, torneo, titulo, texto, caduca


def crear_anuncio(ambito: str, titulo: str, texto: str, torneo: Optional[str] = None, fijado: bool = False,
                  caduca: Optional[date] = None) -> int:
    ambito, torneo, titulo, texto, caduca = _validar(ambito, torneo, titulo, texto, caduca)
    with _conexion() as con:
        if torneo and not con.execute("SELECT 1 FROM torneos WHERE codigo = ?", (torneo,)).fetchone():
            raise ValueError("Torneo no encontrado.")
        return con.execute(
            "INSERT INTO anuncios (ambito, torneo, titulo, texto, fijado, caduca) VALUES (?, ?, ?, ?, ?, ?)",
            (ambito, torneo, titulo, texto, 1 if fijado else 0, caduca)).lastrowid


def editar_anuncio(anuncio_id: int, titulo: str, texto: str, fijado: bool = False,
                   caduca: Optional[date] = None) -> None:
    """Cambia título, texto, fijado y caducidad (el ámbito no se cambia: se borra y se crea de nuevo)."""
    with _conexion() as con:
        f = con.execute("SELECT ambito, torneo FROM anuncios WHERE id = ?", (anuncio_id,)).fetchone()
        if f is None:
            raise ValueError("Anuncio no encontrado.")
        _, _, titulo, texto, caduca = _validar(f["ambito"], f["torneo"] or "-", titulo, texto, caduca)
        con.execute("UPDATE anuncios SET titulo = ?, texto = ?, fijado = ?, caduca = ?, "
                    "actualizado = CURRENT_TIMESTAMP WHERE id = ?",
                    (titulo, texto, 1 if fijado else 0, caduca, anuncio_id))


def fijar_anuncio(anuncio_id: int, fijado: bool) -> None:
    with _conexion() as con:
        if con.execute("UPDATE anuncios SET fijado = ? WHERE id = ?", (1 if fijado else 0, anuncio_id)).rowcount == 0:
            raise ValueError("Anuncio no encontrado.")


def eliminar_anuncio(anuncio_id: int) -> None:
    with _conexion() as con:
        if con.execute("DELETE FROM anuncios WHERE id = ?", (anuncio_id,)).rowcount == 0:
            raise ValueError("Anuncio no encontrado.")


def listar_anuncios(ambito: Optional[str] = None, torneo: Optional[str] = None, incluir_ocultos: bool = False,
                    hoy: Optional[date] = None, limite: int = 100) -> List[dict]:
    """
    Anuncios, los fijados primero y luego los más recientes. Con `incluir_ocultos=False` (invitados) se
    excluyen los de torneos no visibles y los caducados; con True (administrador) salen todos y cada uno
    lleva `caducado`.
    """
    hoy = (hoy or date.today()).isoformat()
    sql = ("SELECT a.*, t.nombre AS torneo_nombre, COALESCE(t.visible, 1) AS torneo_visible, "
           "(a.caduca IS NOT NULL AND a.caduca < ?) AS caducado "
           "FROM anuncios a LEFT JOIN torneos t ON t.codigo = a.torneo WHERE 1 = 1")
    params: list = [hoy]
    if ambito:
        sql += " AND a.ambito = ?"
        params.append(ambito)
    if torneo:
        sql += " AND a.torneo = ?"
        params.append(torneo)
    if not incluir_ocultos:
        sql += " AND COALESCE(t.visible, 1) = 1 AND (a.caduca IS NULL OR a.caduca >= ?)"
        params.append(hoy)
    sql += " ORDER BY a.fijado DESC, a.creado DESC, a.id DESC LIMIT ?"
    params.append(limite)
    with _conexion() as con:
        return [dict(f) for f in con.execute(sql, params)]

"""
Avisos por WhatsApp mediante enlaces «click to chat» (https://wa.me/<teléfono>?text=<mensaje>).

No se usa ninguna API: la aplicación solo construye el enlace y el administrador lo abre; se abre
WhatsApp con el mensaje ya escrito y es él quien pulsa «Enviar». Por eso no hay envíos automáticos.

Los teléfonos son datos personales: solo se leen para el administrador (ver torneo.telefonos_de)
y nunca se incluyen en las consultas que ven los invitados.
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote

PREFIJO_DEFECTO = "34"  # España
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def normalizar_telefono(valor, prefijo: str = PREFIJO_DEFECTO) -> str:
    """
    Devuelve el teléfono en formato internacional solo con dígitos («34600123456»), o "" si está vacío.
    Admite espacios, puntos, guiones y paréntesis, «+34…» y «0034…». Un número de 9 cifras sin prefijo
    se toma como español. Lanza ValueError si no es un número válido.
    """
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto == "" or texto.lower() == "nan":
        return ""
    if re.search(r"[^\d\s.\-()+/]", texto):
        raise ValueError(f"Teléfono no válido: «{texto}» (solo cifras, espacios y +).")
    internacional = texto.startswith("+")
    digitos = re.sub(r"\D", "", texto)
    if digitos.startswith("00"):
        digitos, internacional = digitos[2:], True
    if not internacional and len(digitos) == 9:
        digitos = prefijo + digitos
    if not (9 <= len(digitos) <= 15) or digitos.startswith("0"):
        raise ValueError(f"Teléfono no válido: «{texto}».")
    if digitos.startswith(prefijo) and len(digitos) - len(prefijo) != 9 and prefijo == "34":
        raise ValueError(f"Teléfono español no válido: «{texto}» (deben ser 9 cifras tras el +34).")
    return digitos


def enlace_whatsapp(telefono: str, mensaje: str) -> str:
    """Enlace wa.me con el mensaje codificado. El teléfono debe estar ya normalizado."""
    digitos = normalizar_telefono(telefono)
    if not digitos:
        raise ValueError("No hay teléfono.")
    return f"https://wa.me/{digitos}?text={quote(mensaje, safe='')}"


def _cuando(fecha_hora: Optional[str]) -> str:
    if not fecha_hora:
        return "aún no tiene día y hora (te avisaremos en cuanto se fijen)"
    d = datetime.fromisoformat(fecha_hora)
    return f"es el {DIAS[d.weekday()]} {d:%d/%m/%Y} a las {d:%H:%M}"


def mensaje_partido(torneo: str, partido: dict, destinatario: str, rival: str, club: str = "") -> str:
    """Texto del aviso de un partido para `destinatario` (nombre) frente a `rival`."""
    primero = destinatario.split()[0] if destinatario.strip() else ""
    saludo = f"Hola {primero}," if primero else "Hola,"
    donde = f" en {club}" if club else ""
    fase = ""
    if partido.get("fase") == "grupo" and partido.get("grupo"):
        fase = f" (Grupo {partido['grupo']})"
    return (f"{saludo} tu partido del torneo «{torneo}»{fase}{donde} contra {rival} "
            f"{_cuando(partido.get('fecha_hora'))}. "
            f"Si no puedes jugar, avísanos cuanto antes. ¡Gracias!")


def mensaje_ranking(ventana: str, partido: dict, destinatario: str, rival: str, club: str = "") -> str:
    """Aviso de un partido del ranking continuo (`ventana`: «Ventana 2», «Ventana Reto»…)."""
    primero = destinatario.split()[0] if destinatario.strip() else ""
    saludo = f"Hola {primero}," if primero else "Hola,"
    donde = f" en {club}" if club else ""
    return (f"{saludo} tu partido del Ranking continuo ({ventana}){donde} contra {rival} "
            f"{_cuando(partido.get('fecha_hora'))}. "
            f"Si no puedes jugar, avísanos cuanto antes. ¡Gracias!")

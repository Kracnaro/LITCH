"""Sistema de permisos de Litch — controla capacidades autónomas.

Cada permiso puede estar en tres estados:
  "siempre"  — Litch actúa sin pedir confirmación
  "pedir"    — pregunta al usuario antes de cada acción
  "nunca"    — acción bloqueada completamente

Los permisos se persisten en data/permisos.json.
"""
import json
import os

from . import memoria as _mem

RUTA = os.path.join(_mem.RUTA_DATA, "permisos.json")

# Definición de todos los permisos disponibles
CATALOGO: dict = {
    "web_buscar": {
        "nombre": "Búsqueda en internet",
        "desc":   "Buscar información en DuckDuckGo y Wikipedia",
        "defecto": "siempre",
        "icono":  "🌐",
    },
    "web_leer": {
        "nombre": "Leer páginas web",
        "desc":   "Abrir y leer el contenido de URLs para investigar",
        "defecto": "siempre",
        "icono":  "📄",
    },
    "web_noticias": {
        "nombre": "Noticias y mercados",
        "desc":   "Consultar noticias financieras y datos de mercado",
        "defecto": "siempre",
        "icono":  "📰",
    },
    "correo_leer": {
        "nombre": "Leer correo electrónico",
        "desc":   "Acceder a la bandeja de entrada de las cuentas configuradas",
        "defecto": "pedir",
        "icono":  "📬",
    },
    "correo_enviar": {
        "nombre": "Enviar correos electrónicos",
        "desc":   "Redactar y enviar emails de forma autónoma",
        "defecto": "pedir",
        "icono":  "📤",
    },
    "correo_responder": {
        "nombre": "Responder correos automáticamente",
        "desc":   "Responder emails sin confirmación manual",
        "defecto": "nunca",
        "icono":  "↩️",
    },
    "ia_externa": {
        "nombre": "Usar IA externa",
        "desc":   "Llamar a APIs de Claude / OpenAI para respuestas avanzadas",
        "defecto": "pedir",
        "icono":  "🤖",
    },
    "ia_local": {
        "nombre": "Usar Ollama local",
        "desc":   "Usar el modelo de IA local para análisis y resúmenes",
        "defecto": "siempre",
        "icono":  "🧠",
    },
    "guardar_archivos": {
        "nombre": "Guardar archivos locales",
        "desc":   "Escribir datos aprendidos en disco (reportes, investigaciones)",
        "defecto": "siempre",
        "icono":  "💾",
    },
    "investigacion_autonoma": {
        "nombre": "Investigación autónoma",
        "desc":   "Iniciar ciclos de investigación sin instrucción explícita",
        "defecto": "pedir",
        "icono":  "🔍",
    },
}


def _cargar() -> dict:
    if not os.path.exists(RUTA):
        return {k: v["defecto"] for k, v in CATALOGO.items()}
    try:
        with open(RUTA, encoding="utf-8") as f:
            guardados = json.load(f)
        base = {k: v["defecto"] for k, v in CATALOGO.items()}
        base.update({k: v for k, v in guardados.items() if k in CATALOGO
                     and v in ("siempre", "pedir", "nunca")})
        return base
    except Exception:
        return {k: v["defecto"] for k, v in CATALOGO.items()}


def _guardar(estado: dict):
    os.makedirs(_mem.RUTA_DATA, exist_ok=True)
    with open(RUTA, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


# ─── Estado en memoria ────────────────────────────────────────────────────────
_estado: dict = {}


def _estado_cargado() -> dict:
    global _estado
    if not _estado:
        _estado = _cargar()
    return _estado


# ─── API pública ──────────────────────────────────────────────────────────────

def tiene(permiso: str) -> bool:
    """True si el permiso está en estado 'siempre'."""
    return _estado_cargado().get(permiso, "nunca") == "siempre"


def estado(permiso: str) -> str:
    """Devuelve 'siempre', 'pedir' o 'nunca'."""
    return _estado_cargado().get(permiso, "nunca")


def conceder(permiso: str):
    _estado_cargado()[permiso] = "siempre"
    _guardar(_estado)


def pedir(permiso: str):
    _estado_cargado()[permiso] = "pedir"
    _guardar(_estado)


def revocar(permiso: str):
    _estado_cargado()[permiso] = "nunca"
    _guardar(_estado)


def set_estado(permiso: str, valor: str):
    if valor in ("siempre", "pedir", "nunca") and permiso in CATALOGO:
        _estado_cargado()[permiso] = valor
        _guardar(_estado)


def resumen() -> str:
    e = _estado_cargado()
    activos = [CATALOGO[k]["icono"] + " " + CATALOGO[k]["nombre"]
               for k, v in e.items() if v == "siempre"]
    return ("Permisos activos: " + ", ".join(activos)) if activos else "Sin permisos concedidos."


def recargar():
    global _estado
    _estado = _cargar()

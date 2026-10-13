"""Conocimiento online de Litch — sin servidor propio.

Consulta fuentes públicas gratuitas directamente desde tu equipo:
Wikipedia (resúmenes), DuckDuckGo (respuestas instantáneas) y wttr.in (clima).
"""
import json
import urllib.parse
import urllib.request


def _leer(url, timeout=8):
    peticion = urllib.request.Request(url, headers={"User-Agent": "LitchIA/1.0"})
    with urllib.request.urlopen(peticion, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def wikipedia(consulta, idioma="es"):
    try:
        titulo = urllib.parse.quote(consulta.strip().replace(" ", "_"))
        url = f"https://{idioma}.wikipedia.org/api/rest_v1/page/summary/{titulo}"
        datos = json.loads(_leer(url))
        extracto = datos.get("extract")
        if extracto and len(extracto) > 30:
            return extracto[:600]
    except Exception:
        pass
    return None


def duckduckgo(consulta, idioma="es"):
    try:
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
            "q": consulta, "format": "json", "no_html": 1,
            "kl": "es-es" if idioma == "es" else "us-en"})
        datos = json.loads(_leer(url))
        texto = datos.get("AbstractText") or datos.get("Answer") or ""
        if texto and len(texto) > 20:
            return texto[:600]
    except Exception:
        pass
    return None


def clima(lugar, idioma="es"):
    try:
        url = (f"https://wttr.in/{urllib.parse.quote(lugar.strip())}"
               f"?format=3&lang={idioma}")
        reporte = _leer(url).strip()
        if reporte and "Unknown" not in reporte:
            return reporte
    except Exception:
        pass
    return None


def buscar(consulta, idioma="es"):
    """Busca en Wikipedia y, si no hay resultado, en DuckDuckGo."""
    resultado = wikipedia(consulta, idioma) or duckduckgo(consulta, idioma)
    if resultado:
        return resultado
    if idioma == "en":
        return ("I couldn't find reliable information about that online, sir. "
                "Try rephrasing the question.")
    return ("No encontré información confiable sobre eso en línea, señor. "
            "Intente reformular la pregunta.")

"""Agente web autónomo de Litch — investigación inteligente en internet.

Sin API keys externas. Usa fuentes públicas:
  • DuckDuckGo HTML  — búsqueda general sin registro
  • Wikipedia API    — artículos enciclopédicos
  • Yahoo Finance    — precios y datos de mercado
  • RSS financieros  — noticias de Investing.com / MarketWatch / El Economista
  • Cualquier URL    — lectura y extracción de texto

Flujo de investigación autónoma `investigar(tema)`:
  1. Busca en DuckDuckGo → obtiene 5 resultados
  2. Lee el contenido de los 2 mejores
  3. Consulta Wikipedia
  4. Resume todo con Ollama (mente.py)
  5. Devuelve respuesta coherente y guardada en memoria

Todo el conocimiento investigado se guarda en data/investigaciones.json
para que Litch lo recuerde y lo use en conversaciones futuras.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

from . import memoria as _mem
from . import permisos

RUTA_INV = os.path.join(_mem.RUTA_DATA, "investigaciones.json")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.7",
    "Accept-Encoding": "identity",
    "Connection": "close",
}

RSS_FINANCIEROS = [
    "https://es.investing.com/rss/news.rss",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^DJI&region=US&lang=en-US",
    "https://www.eleconomista.com.co/feed",
]


# ─── HTTP ─────────────────────────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "latin-1", "utf-8-sig"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "ignore")


def _limpiar(html: str, max_chars: int = 4000) -> str:
    """Elimina etiquetas y extrae texto plano."""
    t = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    t = re.sub(r"<style[^>]*>.*?</style>",   " ", t,    flags=re.DOTALL | re.I)
    t = re.sub(r"<!--.*?-->",                " ", t,    flags=re.DOTALL)
    t = re.sub(r"<[^>]+>",                  " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:max_chars]


# ─── DuckDuckGo ──────────────────────────────────────────────────────────────

def buscar(query: str, n: int = 5, idioma: str = "es") -> list:
    """Busca en DuckDuckGo y devuelve lista de {'titulo', 'url', 'snippet'}.

    Sin API key. Usa el endpoint HTML público de DDG.
    """
    if not permisos.tiene("web_buscar"):
        return [{"titulo": "Sin permiso", "url": "", "snippet": "Permiso web_buscar no concedido."}]
    try:
        params = urllib.parse.urlencode({"q": query, "kl": "co-es" if idioma == "es" else "us-en"})
        url    = f"https://html.duckduckgo.com/html/?{params}"
        html   = _fetch(url, timeout=12)

        # Extraer títulos
        titulos  = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)<', html)
        snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)<', html)

        resultados = []
        for i, (url_r, titulo) in enumerate(titulos[:n]):
            snippet = snippets[i] if i < len(snippets) else ""
            # DuckDuckGo redirige via //duckduckgo.com/l/?uddg=
            url_real = _decodificar_ddg_url(url_r)
            resultados.append({
                "titulo":  titulo.strip(),
                "url":     url_real,
                "snippet": snippet.strip(),
            })
        return resultados if resultados else _ddg_api(query, idioma, n)
    except Exception as e:
        return _ddg_api(query, idioma, n)


def _decodificar_ddg_url(url_ddg: str) -> str:
    """Extrae la URL real de los redirects de DuckDuckGo."""
    if "uddg=" in url_ddg:
        try:
            return urllib.parse.unquote(url_ddg.split("uddg=")[1].split("&")[0])
        except Exception:
            pass
    if url_ddg.startswith("//"):
        url_ddg = "https:" + url_ddg
    return url_ddg


def _ddg_api(query: str, idioma: str, n: int) -> list:
    """Fallback: DuckDuckGo Instant Answer API (solo resúmenes)."""
    try:
        params = urllib.parse.urlencode({
            "q": query, "format": "json",
            "no_html": 1, "kl": "co-es" if idioma == "es" else "us-en"
        })
        datos = json.loads(_fetch(f"https://api.duckduckgo.com/?{params}", timeout=8))
        results = []
        texto = datos.get("AbstractText", "") or datos.get("Answer", "")
        if texto:
            results.append({
                "titulo":  datos.get("Heading", query),
                "url":     datos.get("AbstractURL", ""),
                "snippet": texto[:400],
            })
        for t in datos.get("RelatedTopics", [])[:n - 1]:
            if isinstance(t, dict) and t.get("Text"):
                results.append({
                    "titulo":  t.get("Text", "")[:60],
                    "url":     t.get("FirstURL", ""),
                    "snippet": t.get("Text", "")[:300],
                })
        return results
    except Exception:
        return []


# ─── Wikipedia ───────────────────────────────────────────────────────────────

def wikipedia(tema: str, idioma: str = "es") -> str:
    """Devuelve el extracto introductorio de Wikipedia sobre el tema."""
    if not permisos.tiene("web_buscar"):
        return ""
    try:
        lang   = idioma if idioma in ("es", "en") else "es"
        params = urllib.parse.urlencode({
            "action":      "query",
            "prop":        "extracts",
            "exintro":     True,
            "explaintext": True,
            "redirects":   True,
            "titles":      tema,
            "format":      "json",
        })
        url  = f"https://{lang}.wikipedia.org/w/api.php?{params}"
        data = json.loads(_fetch(url, timeout=10))
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid != "-1":
                return page.get("extract", "")[:2000]
    except Exception:
        pass
    return ""


# ─── Leer URL ────────────────────────────────────────────────────────────────

def leer_url(url: str, max_chars: int = 3500) -> str:
    """Lee una URL y devuelve el texto limpio."""
    if not permisos.tiene("web_leer"):
        return "Permiso web_leer no concedido."
    if not url or not url.startswith("http"):
        return ""
    try:
        html = _fetch(url, timeout=12)
        return _limpiar(html, max_chars)
    except Exception as e:
        return ""


# ─── Datos de mercado ─────────────────────────────────────────────────────────

def datos_mercado(simbolo: str) -> dict:
    """Obtiene precio y datos básicos via Yahoo Finance (sin API key)."""
    if not permisos.tiene("web_noticias"):
        return {}
    try:
        url  = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{urllib.parse.quote(simbolo)}?interval=1d&range=5d")
        req  = urllib.request.Request(url, headers={**_HEADERS,
               "Accept": "application/json"})
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        meta = data["chart"]["result"][0]["meta"]
        return {
            "simbolo":  simbolo.upper(),
            "precio":   round(meta.get("regularMarketPrice", 0), 4),
            "moneda":   meta.get("currency", "USD"),
            "mercado":  meta.get("fullExchangeName", ""),
            "tipo":     meta.get("instrumentType", ""),
        }
    except Exception:
        return {}


# ─── Noticias RSS ─────────────────────────────────────────────────────────────

def noticias_rss(n: int = 8) -> list:
    """Obtiene noticias financieras recientes de fuentes RSS."""
    if not permisos.tiene("web_noticias"):
        return []
    noticias = []
    for rss_url in RSS_FINANCIEROS:
        try:
            xml      = _fetch(rss_url, timeout=8)
            titulos  = re.findall(r"<title><!\[CDATA\[(.+?)\]\]></title>|<title>([^<]{5,200})</title>", xml)
            for t1, t2 in titulos[1:n + 1]:   # skip feed title
                titulo = (t1 or t2).strip()
                if titulo and not titulo.startswith("http"):
                    noticias.append(titulo)
            if noticias:
                break
        except Exception:
            continue
    return noticias[:n]


# ─── Motor de investigación autónoma ─────────────────────────────────────────

def investigar(tema: str, idioma: str = "es", profundidad: int = 2) -> str:
    """Investiga un tema de forma autónoma combinando múltiples fuentes.

    Flujo:
      1. Búsqueda DuckDuckGo → top 5 resultados
      2. Lee los 2 mejores resultados (profundidad=2)
      3. Consulta Wikipedia
      4. Resume todo con IA local (Ollama)
      5. Guarda el resultado en data/investigaciones.json

    Devuelve la síntesis final.
    """
    from . import mente

    if not permisos.tiene("web_buscar"):
        return "Necesito permiso web_buscar para investigar. Active el permiso en el panel de permisos."

    partes = []

    # ── 1. DuckDuckGo ────────────────────────────────────────────────────
    resultados = buscar(tema, n=5, idioma=idioma)
    if resultados:
        resumen_ddg = []
        for r in resultados[:3]:
            if r.get("snippet"):
                resumen_ddg.append(f"• {r['titulo']}: {r['snippet']}")
        if resumen_ddg:
            partes.append("Resultados de búsqueda:\n" + "\n".join(resumen_ddg))

    # ── 2. Leer páginas (las mejores con URL real) ───────────────────────
    urls_leidas = 0
    for r in resultados[:profundidad]:
        url = r.get("url", "")
        if not url or not url.startswith("http"):
            continue
        texto = leer_url(url, max_chars=2000)
        if texto and len(texto) > 200:
            partes.append(f"Contenido de {url[:60]}:\n{texto}")
            urls_leidas += 1
        time.sleep(0.3)

    # ── 3. Wikipedia ─────────────────────────────────────────────────────
    wiki = wikipedia(tema, idioma)
    if wiki and len(wiki) > 100:
        partes.append(f"Wikipedia: {wiki[:1500]}")

    if not partes:
        return (f"No encontré información sobre «{tema}» en este momento, señor. "
                f"Revisa la conexión a internet o prueba un término diferente.")

    # ── 4. Resumir con IA local ──────────────────────────────────────────
    contexto = "\n\n---\n\n".join(partes)
    if idioma == "es":
        prompt = (f"Eres Litch, un asistente de IA. Tu usuario te preguntó sobre: "
                  f"«{tema}»\n\nAquí está la información que encontré en internet:\n\n"
                  f"{contexto[:3500]}\n\n"
                  f"Resume esta información de manera clara, concisa y útil en 3-5 oraciones. "
                  f"Habla en primera persona como si fueras Litch respondiendo al señor.")
    else:
        prompt = (f"You are Litch, an AI assistant. Your user asked about: "
                  f"«{tema}»\n\nHere is what I found online:\n\n"
                  f"{contexto[:3500]}\n\n"
                  f"Summarize this information clearly and concisely in 3-5 sentences. "
                  f"Speak in first person as Litch answering the sir.")

    respuesta_ia = None
    if mente.disponible():
        respuesta_ia = mente.responder(prompt, historial=[])

    if respuesta_ia:
        resultado_final = respuesta_ia
    else:
        # Sin IA disponible: síntesis manual
        if partes:
            resultado_final = (
                f"Sobre «{tema}»: " + (wiki[:400] if wiki else partes[0][:400])
            )
        else:
            resultado_final = f"No encontré información suficiente sobre «{tema}»."

    # ── 5. Guardar en memoria de investigaciones ─────────────────────────
    _guardar_investigacion(tema, resultado_final, idioma)

    return resultado_final


def _guardar_investigacion(tema: str, resultado: str, idioma: str):
    """Persiste el resultado en data/investigaciones.json."""
    try:
        os.makedirs(_mem.RUTA_DATA, exist_ok=True)
        historial = []
        if os.path.exists(RUTA_INV):
            with open(RUTA_INV, encoding="utf-8") as f:
                historial = json.load(f)
        historial.append({
            "t":       time.time(),
            "tema":    tema,
            "idioma":  idioma,
            "resultado": resultado,
        })
        historial = historial[-200:]   # últimas 200 investigaciones
        with open(RUTA_INV, "w", encoding="utf-8") as f:
            json.dump(historial, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def investigaciones_recientes(n: int = 10) -> list:
    """Devuelve las últimas N investigaciones guardadas."""
    if not os.path.exists(RUTA_INV):
        return []
    try:
        with open(RUTA_INV, encoding="utf-8") as f:
            data = json.load(f)
        return data[-n:]
    except Exception:
        return []


# ─── Búsqueda rápida (sin IA, texto plano) ────────────────────────────────────

def respuesta_rapida(query: str, idioma: str = "es") -> str:
    """Búsqueda rápida: DuckDuckGo instant answer + Wikipedia. Sin IA."""
    resultados = buscar(query, n=3, idioma=idioma)
    wiki       = wikipedia(query, idioma)

    partes = []
    for r in resultados[:2]:
        if r.get("snippet") and len(r["snippet"]) > 30:
            partes.append(r["snippet"])
    if wiki and len(wiki) > 80:
        partes.append(wiki[:400])

    if not partes:
        return (f"No encontré resultados rápidos para «{query}», señor. "
                f"Diga «investiga sobre {query}» para una búsqueda profunda.")

    return " ".join(partes[:2])[:600]

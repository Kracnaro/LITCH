"""Scraper de resultados de loterías colombianas — sin APIs de pago.

Estrategia de tres capas (robustez ante cambios de sitios):
  1. Petición directa a la URL oficial de cada lotería
  2. Petición a un agregador alternativo
  3. Búsqueda DuckDuckGo con extracción de números del snippet

Cada capa usa regex para extraer números del HTML/texto sin depender de la
estructura exacta de la página — así funciona aunque cambien el diseño.

Honestidad: el scraping puede fallar si la lotería bloquea robots o cambia
su HTML. En ese caso se activa la opción de ingreso manual.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

# ─── Configuración de cada lotería ───────────────────────────────────────────

LOTERIAS: dict = {
    "Boyacá": {
        "nombre_completo": "Lotería de Boyacá",
        "dia": "sábado",
        "tipo": "4digit",           # número de 4 cifras
        "rango": (0, 9999),
        "urls": [
            "https://www.loteriadeboyaca.gov.co/resultados/",
            "https://resultados.loterias.com.co/loteria-de-boyaca",
            "https://www.apuestasonline.net/loterias/boyaca/",
        ],
        "ddg": "resultado lotería Boyacá Colombia número ganador",
    },
    "Meta": {
        "nombre_completo": "Lotería del Meta",
        "dia": "jueves",
        "tipo": "4digit",
        "rango": (0, 9999),
        "urls": [
            "https://loteriadelmeta.com.co/resultados/",
            "https://resultados.loterias.com.co/loteria-del-meta",
        ],
        "ddg": "resultado lotería del Meta Colombia número ganador",
    },
    "Bogotá": {
        "nombre_completo": "Lotería de Bogotá",
        "dia": "jueves",
        "tipo": "4digit",
        "rango": (0, 9999),
        "urls": [
            "https://www.loteriabogota.gov.co/resultados/",
            "https://resultados.loterias.com.co/loteria-de-bogota",
        ],
        "ddg": "resultado lotería Bogotá Colombia número ganador",
    },
    "Cundinamarca": {
        "nombre_completo": "Lotería de Cundinamarca",
        "dia": "lunes",
        "tipo": "4digit",
        "rango": (0, 9999),
        "urls": [
            "https://www.loteriacundinamarca.com/resultados/",
            "https://resultados.loterias.com.co/loteria-de-cundinamarca",
        ],
        "ddg": "resultado lotería Cundinamarca Colombia número ganador",
    },
    "Huila": {
        "nombre_completo": "Lotería del Huila",
        "dia": "viernes",
        "tipo": "4digit",
        "rango": (0, 9999),
        "urls": [
            "https://resultados.loterias.com.co/loteria-del-huila",
        ],
        "ddg": "resultado lotería Huila Colombia número ganador",
    },
    "Baloto": {
        "nombre_completo": "Baloto",
        "dia": "miércoles y sábado",
        "tipo": "multiball",        # 5 bolas de 1-43 + 1 SuperBalota de 1-16
        "rango": (1, 43),
        "cantidad": 5,
        "super_rango": (1, 16),
        "tiene_super": True,        # el último elemento de cada sorteo es la SuperBalota
        "urls": [
            "https://baloto.com/resultados",
            "https://www.baloto.com/resultados",
            "https://resultados.loterias.com.co/baloto",
            "https://www.apuestasonline.net/loterias/baloto/",
            "https://www.suertia.co/resultados/baloto/",
        ],
        "url_pagina": "https://baloto.com/resultados?page={page}",
        "ddg": "resultado Baloto Colombia 5 números ganadores superbalota hoy",
        "es_baloto": True,
    },
    "Balota Revancha": {
        "nombre_completo": "Balota Revancha",
        "dia": "miércoles y sábado",
        "tipo": "multiball",        # misma estructura 5+1 que Baloto
        "rango": (1, 43),
        "cantidad": 5,
        "super_rango": (1, 16),
        "tiene_super": True,
        "urls": [
            "https://baloto.com/resultados",
            "https://www.baloto.com/resultados",
            "https://resultados.loterias.com.co/baloto-revancha",
            "https://www.apuestasonline.net/loterias/baloto-revancha/",
        ],
        "url_pagina": "https://baloto.com/resultados?page={page}",
        "ddg": "resultado Balota Revancha Colombia 5 números ganadores superbalota",
        "es_baloto": True,
        "revancha": True,           # flag para filtrar la segunda jugada del sorteo
    },
    "SuperAstro": {
        "nombre_completo": "SuperAstro",
        "dia": "diario",
        "tipo": "4digit",
        "rango": (0, 9999),
        "urls": [
            "https://resultados.loterias.com.co/superastro",
        ],
        "ddg": "resultado SuperAstro Colombia número ganador",
    },
    "Astro Luna": {
        "nombre_completo": "Astro Luna (SuperAstro nocturno)",
        "dia": "diario",
        "tipo": "4digit",
        "rango": (0, 9999),
        "astro": True,              # 4 cifras + signo zodiacal
        "urls": [
            "https://resultados.loterias.com.co/astro-luna",
            "https://www.apuestasonline.net/loterias/astro-luna/",
            "https://superastro.com.co/resultados/",
        ],
        "ddg": "resultado Astro Luna hoy Colombia numero ganador signo zodiacal",
    },
    "Astro Sol": {
        "nombre_completo": "Astro Sol (SuperAstro diurno)",
        "dia": "diario",
        "tipo": "4digit",
        "rango": (0, 9999),
        "astro": True,              # 4 cifras + signo zodiacal
        "urls": [
            "https://resultados.loterias.com.co/astro-sol",
            "https://www.apuestasonline.net/loterias/astro-sol/",
            "https://superastro.com.co/resultados/",
        ],
        "ddg": "resultado Astro Sol hoy Colombia numero ganador signo zodiacal",
    },
}

# ─── Signos zodiacales (SuperAstro: Astro Luna / Astro Sol) ─────────────────

SIGNOS_ZODIACO = [
    "aries", "tauro", "geminis", "cancer", "leo", "virgo",
    "libra", "escorpion", "sagitario", "capricornio", "acuario", "piscis",
]

# Último resultado de signos por lotería astro (se llena en cada búsqueda):
#   ULTIMOS_SIGNOS["Astro Luna"] = ["leo", "piscis", ...]  (más reciente primero)
ULTIMOS_SIGNOS: dict = {}


def _normalizar_signo(s: str) -> str:
    s = (s.lower().replace("é", "e").replace("á", "a").replace("í", "i")
         .replace("ó", "o").replace("ú", "u").strip())
    if s.startswith("escorpi"):
        return "escorpion"
    if s.startswith("gemini"):
        return "geminis"
    return s


def _extraer_astro(texto: str) -> tuple:
    """Extrae pares (número de 4 cifras, signo) de un texto de resultados.

    Devuelve (sorteos, signos): sorteos = [[n], ...] compatible con el
    pipeline 4digit; signos = ['leo', ...] en el mismo orden.
    """
    patron_signo = "|".join(SIGNOS_ZODIACO) + "|escorpio|géminis|cáncer"
    pares = re.findall(
        rf"\b(\d{{4}})\b[\s\-·:]{{0,10}}\b({patron_signo})\b",
        texto, flags=re.I)
    # También signo antes del número
    pares += [(n, s) for s, n in re.findall(
        rf"\b({patron_signo})\b[\s\-·:]{{0,10}}\b(\d{{4}})\b",
        texto, flags=re.I)]
    sorteos, signos, vistos = [], [], set()
    for num, sig in pares:
        n = int(num)
        sig = _normalizar_signo(sig)
        if (n, sig) in vistos or sig not in SIGNOS_ZODIACO:
            continue
        vistos.add((n, sig))
        sorteos.append([n])
        signos.append(sig)
        if len(sorteos) >= 60:
            break
    return sorteos, signos


# ─── HTTP helper ─────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "close",
}


def _fetch(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    # Try UTF-8, fallback to latin-1
    for enc in ("utf-8", "latin-1", "utf-8-sig"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "ignore")


def _limpiar_html(html: str) -> str:
    """Elimina etiquetas HTML, scripts y estilos; normaliza espacios."""
    texto = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    texto = re.sub(r"<style[^>]*>.*?</style>",  " ", texto, flags=re.DOTALL | re.I)
    texto = re.sub(r"<!--.*?-->",               " ", texto, flags=re.DOTALL)
    texto = re.sub(r"<[^>]+>",                 " ", texto)
    texto = texto.replace("&nbsp;", " ").replace("&amp;", "&")
    texto = texto.replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", texto)


# ─── Parsers por tipo ─────────────────────────────────────────────────────────

def _extraer_4digit(texto: str) -> list:
    """Extrae posibles números de lotería de 4 dígitos del texto plano."""
    # Captura bloques de 4 dígitos — puede incluir ruido
    raw = re.findall(r"\b(\d{4})\b", texto)
    numeros = [int(n) for n in raw]
    # Descartar duplicados consecutivos y retener posibles sorteos
    vistos = set()
    resultado = []
    for n in numeros:
        if n not in vistos and 0 <= n <= 9999:
            vistos.add(n)
            resultado.append([n])
        if len(resultado) >= 60:
            break
    return resultado


def _extraer_multiball(texto: str) -> list:
    """Extrae combinaciones de 5 bolas (1-43) genéricas."""
    sorteos = []
    tokens = re.findall(r"\b(\d{1,2})\b", texto)
    nums   = [int(t) for t in tokens if 1 <= int(t) <= 43]
    i = 0
    while i <= len(nums) - 5:
        grupo = nums[i: i + 5]
        if len(set(grupo)) == 5:
            sorteos.append(sorted(grupo))
            i += 5
        else:
            i += 1
        if len(sorteos) >= 40:
            break
    return sorteos


# ─── Extractor especializado Baloto (5 bolas 1-43 + 1 SuperBalota 1-16) ──────

# Patrón con separador explícito y SuperBalota etiquetada
_PAT_BALOTO_ETIQ = re.compile(
    r"\b(\d{1,2})\s*[-–·]\s*(\d{1,2})\s*[-–·]\s*(\d{1,2})\s*[-–·]\s*"
    r"(\d{1,2})\s*[-–·]\s*(\d{1,2})"
    r"\s*(?:[-–+·]\s*(?:[Ss]uper\s*[Bb]alota?[:\s]*|\(SB\)|\bSB\b|\bbalota\b)?\s*)"
    r"(\d{1,2})\b",
    re.IGNORECASE,
)

# Patrón genérico: 6 números contiguos donde el 6to es ≤ 16
_PAT_BALOTO_GEN = re.compile(r"\b(\d{1,2})\b")


def _extraer_baloto(texto: str, revancha: bool = False) -> list:
    """
    Extrae combinaciones Baloto del texto.
    Devuelve lista de sorteos: cada uno es [b1,b2,b3,b4,b5,super].
    Si revancha=True intenta filtrar el bloque de 'Revancha' del HTML.
    """
    sorteos = []

    # Si busca Revancha, intentar aislar esa sección del HTML/texto
    if revancha:
        partes = re.split(r"[Rr]evan[cz]ha", texto, maxsplit=1)
        texto_busq = partes[1] if len(partes) > 1 else texto
    else:
        # Si NO es revancha, quedarse solo con la primera sección
        partes = re.split(r"[Rr]evan[cz]ha", texto, maxsplit=1)
        texto_busq = partes[0]

    # Intento 1: patrón con etiqueta explícita
    for m in _PAT_BALOTO_ETIQ.finditer(texto_busq):
        nums    = [int(m.group(i)) for i in range(1, 6)]
        super_b = int(m.group(6))
        if (all(1 <= n <= 43 for n in nums)
                and 1 <= super_b <= 16
                and len(set(nums)) == 5):
            sorteos.append(sorted(nums) + [super_b])
        if len(sorteos) >= 60:
            break

    if len(sorteos) >= 2:
        return sorteos

    # Intento 2: 6 números seguidos donde el último ≤ 16
    tokens = [int(t) for t in _PAT_BALOTO_GEN.findall(texto_busq)
              if 1 <= int(t) <= 43]
    i = 0
    while i <= len(tokens) - 6:
        grupo   = tokens[i: i + 6]
        princi  = grupo[:5]
        super_b = grupo[5]
        if (all(1 <= n <= 43 for n in princi)
                and 1 <= super_b <= 16
                and len(set(princi)) == 5
                and super_b not in princi):
            sorteos.append(sorted(princi) + [super_b])
            i += 6
        else:
            i += 1
        if len(sorteos) >= 60:
            break

    return sorteos


def _paginar_baloto(n_sorteos: int, revancha: bool = False) -> list:
    """
    Descarga resultados históricos de baloto.com paginando hasta obtener
    n_sorteos resultados únicos. Cada página suele tener ~10 sorteos.
    Devuelve lista de sorteos [b1..b5, super].
    """
    cfg      = LOTERIAS.get("Baloto", {})
    url_tmpl = cfg.get("url_pagina", "https://baloto.com/resultados?page={page}")
    todos    = []
    vistos   = set()
    max_pags = max(1, (n_sorteos // 8) + 3)   # páginas estimadas (8 sorteos/pag)

    for page in range(1, max_pags + 1):
        url = url_tmpl.format(page=page)
        try:
            html   = _fetch(url, timeout=14)
            texto  = _limpiar_html(html)
            nuevos = _extraer_baloto(texto, revancha=revancha)
            for s in nuevos:
                key = tuple(s)
                if key not in vistos:
                    vistos.add(key)
                    todos.append(s)
            if len(todos) >= n_sorteos:
                break
        except Exception:
            break
        time.sleep(0.5)

    return todos[:n_sorteos]


# ─── DuckDuckGo fallback ────────────────────────────────────────────────────

def _ddg(query: str, tipo: str) -> list:
    """Busca en DuckDuckGo y extrae números del snippet de respuesta."""
    try:
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
            {"q": query, "format": "json", "no_html": 1, "kl": "co-es"})
        datos = json.loads(_fetch(url, timeout=8))
        texto = " ".join([
            datos.get("AbstractText", ""),
            datos.get("Answer",       ""),
            " ".join(r.get("Text", "") for r in datos.get("RelatedTopics", [])[:5])
        ])
        if tipo == "multiball":
            return _extraer_multiball(texto)
        return _extraer_4digit(texto)
    except Exception:
        return []


# ─── Función principal ───────────────────────────────────────────────────────

def obtener_resultados(nombre: str, n_sorteos: int = 20) -> tuple:
    """Descarga los últimos N resultados de una lotería.

    Retorna (lista_de_sorteos, mensaje_de_estado).
    Para Baloto/Balota Revancha cada sorteo es [b1,b2,b3,b4,b5,super_balota].
    Para loterías 4 cifras cada sorteo es [numero].
    """
    cfg = LOTERIAS.get(nombre)
    if not cfg:
        return [], f"Lotería «{nombre}» no configurada."

    tipo       = cfg["tipo"]
    es_baloto  = cfg.get("es_baloto", False)
    revancha   = cfg.get("revancha", False)
    sorteos    = []
    intentos   = []

    # ── Baloto / Balota Revancha: paginación dedicada ─────────────────────────
    if es_baloto and n_sorteos > 5:
        sorteos = _paginar_baloto(n_sorteos, revancha=revancha)
        if sorteos:
            return sorteos, (
                f"✓ {len(sorteos)} sorteos de {cfg['nombre_completo']} cargados "
                f"(incluyendo SuperBalota)."
            )

    # ── URLs directas ─────────────────────────────────────────────────────────
    for url in cfg.get("urls", []):
        try:
            html   = _fetch(url, timeout=12)
            texto  = _limpiar_html(html)
            if es_baloto:
                extraidos = _extraer_baloto(texto, revancha=revancha)
            elif tipo == "multiball":
                extraidos = _extraer_multiball(texto)
            elif cfg.get("astro"):
                extraidos, _signos = _extraer_astro(texto)
                if extraidos:
                    ULTIMOS_SIGNOS[nombre] = _signos
                else:
                    # Sin pares número+signo: al menos los números
                    extraidos = _extraer_4digit(texto)
            else:
                extraidos = _extraer_4digit(texto)

            if len(extraidos) >= 2:
                sorteos = extraidos
                intentos.append(f"OK · {url}")
                break
            intentos.append(f"sin datos · {url}")
        except Exception as e:
            intentos.append(f"error · {url} ({e!s:.40})")
        time.sleep(0.4)

    # ── DuckDuckGo fallback ───────────────────────────────────────────────────
    if not sorteos:
        if es_baloto:
            ddg_res = _ddg(cfg["ddg"], "multiball")
            sorteos = _extraer_baloto(" ".join(str(s) for s in ddg_res), revancha=revancha) or ddg_res
        else:
            sorteos = _ddg(cfg["ddg"], tipo)
        intentos.append("DuckDuckGo fallback")

    if not sorteos:
        return [], (
            f"⚠ No pude obtener resultados de {cfg['nombre_completo']}.\n"
            f"Intentos: {' | '.join(intentos)}\n"
            f"Puede ingresar los sorteos manualmente."
        )

    n = min(n_sorteos, len(sorteos))
    extra = " (con SuperBalota)" if es_baloto else ""
    return sorteos[:n], f"✓ {n} sorteos de {cfg['nombre_completo']} cargados{extra}."


def nombres_disponibles() -> list:
    return list(LOTERIAS.keys())


def formato_tipo(nombre: str) -> str:
    """Devuelve el tipo de la lotería ('4digit' o 'multiball')."""
    return LOTERIAS.get(nombre, {}).get("tipo", "4digit")


def rango_numeros(nombre: str) -> tuple:
    """Devuelve el rango válido de números de esta lotería."""
    return LOTERIAS.get(nombre, {}).get("rango", (0, 9999))


def tiene_super(nombre: str) -> bool:
    """True si la lotería tiene SuperBalota (6º número, rango 1-16)."""
    return bool(LOTERIAS.get(nombre, {}).get("tiene_super", False))


def rango_super(nombre: str) -> tuple:
    """Devuelve el rango de la SuperBalota (o (0,0) si no aplica)."""
    return LOTERIAS.get(nombre, {}).get("super_rango", (0, 0))

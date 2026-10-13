"""
mercado_y_tamano.py — Qué mercado es, y cuánto poner en él.

━━━ DOS COSAS QUE LITCH NO SABÍA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**1. EN QUÉ MERCADO ESTÁ.**
No es lo mismo EUR/USD que Nvidia que Bitcoin. Cada uno tiene su horario,
su volatilidad y su comportamiento. Y hay una distinción que cambia todo
lo demás:

    OTC — «Over The Counter»

Un activo marcado OTC en IQ Option **no cotiza en ningún mercado**. El
precio lo genera el propio bróker con un modelo suyo. «Nvidia (OTC)» no
es Nvidia: es una serie sintética que IQ Option produce, disponible los
fines de semana y cuando la bolsa está cerrada, precisamente porque no
depende de ella.

Esto importa para el aprendizaje: los patrones que Litch memorice en un
OTC son patrones **del generador del bróker**, no del mercado. Pueden
funcionar ahí y no significar nada en el activo real. Litch debe saberlo
y guardarlos por separado.

**2. CUÁNTO PONER.**
El señor tenía CO$ 1.501,92 de saldo y CO$ 1.500 de inversión: el 99,9 %
de la cuenta en una sola operación de un minuto. Con un 80 % de aciertos
—que es bueno— la probabilidad de perderlo todo en la siguiente es del
20 %. Una de cada cinco veces.

No hace falta fallar mucho para quedarse a cero: basta con fallar una vez
cuando se apuesta todo.

La regla profesional es fija: **entre el 1 % y el 2 % del capital por
operación**. Con eso hacen falta decenas de fallos seguidos para hacer
daño de verdad, y ninguna racha mala te saca del juego.
"""

from __future__ import annotations

import re

# ── 1. Qué mercado es ────────────────────────────────────────────────────────

TIPOS = {
    "forex":   "divisas",
    "cripto":  "criptomonedas",
    "accion":  "acciones",
    "indice":  "índices",
    "materia": "materias primas",
    "otc":     "sintético del bróker (OTC)",
}

_CRIPTO = ("btc", "bitcoin", "eth", "ethereum", "ltc", "litecoin", "xrp",
           "ripple", "doge", "ada", "cardano", "sol", "solana", "bnb",
           "melania", "trump", "shib", "usdt", "matic", "dot", "link")
_DIVISAS = ("eur", "usd", "gbp", "jpy", "chf", "aud", "nzd", "cad", "cop",
            "mxn", "brl", "try", "zar")
_INDICES = ("us 500", "us500", "sp500", "s&p", "nasdaq", "dow", "dax",
            "ftse", "nikkei", "ibex", "us 100", "us 30")
_MATERIAS = ("oro", "gold", "plata", "silver", "petroleo", "petróleo",
             "oil", "brent", "wti", "gas", "cobre", "copper")


def _plano(t: str) -> str:
    t = (t or "").lower()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u")):
        t = t.replace(a, b)
    return t


def identificar(nombre: str) -> dict:
    """
    Qué clase de activo es, a partir de su nombre en pantalla.

    Devuelve {tipo, nombre, otc, sintetico, aviso}. El campo `otc` es el
    más importante: cambia el valor de todo lo que se aprenda ahí.
    """
    r = {"tipo": "", "nombre": nombre or "", "otc": False,
         "sintetico": False, "descripcion": "", "aviso": ""}
    if not nombre:
        return r
    p = _plano(nombre)

    # OTC primero: manda sobre lo demás
    if "otc" in p or "(otc)" in p:
        r["otc"] = True
        r["sintetico"] = True
        r["aviso"] = (
            "OTC significa que el precio lo genera IQ Option, no el "
            "mercado. Esto NO es el activo real: es una serie sintética "
            "del bróker, disponible cuando la bolsa está cerrada. Los "
            "patrones que aprenda aquí son del generador, no del mercado.")

    # Tipo del subyacente
    if any(c in p for c in _CRIPTO):
        r["tipo"] = "cripto"
    elif any(i in p for i in _INDICES):
        r["tipo"] = "indice"
    elif any(m in p for m in _MATERIAS):
        r["tipo"] = "materia"
    elif re.search(r"\b[a-z]{3}\s*/\s*[a-z]{3}\b", p) or \
         (sum(1 for d in _DIVISAS if d in p) >= 2):
        r["tipo"] = "forex"
    elif re.match(r"^[a-z\s\.]{2,30}$", p.replace("(otc)", "").strip()):
        r["tipo"] = "accion"

    r["descripcion"] = TIPOS.get(r["tipo"], "sin clasificar")
    if r["otc"]:
        r["descripcion"] += " · OTC"
    return r


def clave_memoria(nombre: str) -> str:
    """
    Bajo qué nombre guardar los patrones de este activo.

    Los OTC van aparte. Mezclar patrones de «Nvidia (OTC)» con los de
    Nvidia real sería contaminar el aprendizaje con datos de otro
    universo — el mismo error que las operaciones fantasma, pero más
    difícil de detectar.
    """
    d = identificar(nombre)
    base = _plano(nombre).replace("(otc)", "").strip().replace(" ", "_")
    return f"otc__{base}" if d["otc"] else base


# ── 2. Cuánto poner ──────────────────────────────────────────────────────────

RIESGO_PRUDENTE = 0.01      # 1 % del capital
RIESGO_NORMAL = 0.02        # 2 % — el máximo que recomienda cualquier manual
RIESGO_LIMITE = 0.05        # 5 % — a partir de aquí, aviso serio


def tamano(capital: float, riesgo_pct: float = RIESGO_NORMAL,
           minimo: float = 0.0) -> float:
    """Cuánto invertir para arriesgar ese porcentaje del capital."""
    try:
        c = float(capital); r = float(riesgo_pct)
        if r > 1:
            r = r / 100.0
        v = c * r
        return max(v, minimo) if minimo else v
    except Exception:
        return 0.0


def evaluar_tamano(capital: float, monto: float,
                   divisa: str = "") -> dict:
    """
    ¿Es sensato ese monto para ese capital?

    Devuelve el diagnóstico y —lo importante— cuántas pérdidas seguidas
    se aguantan. Ese número dice más que cualquier porcentaje.
    """
    r = {"pct": 0.0, "nivel": "", "aguanta": 0, "sugerido": 0.0,
         "mensaje": "", "grave": False}
    try:
        c = float(capital); m = float(monto)
    except Exception:
        r["mensaje"] = "no tengo las dos cifras"
        return r
    if c <= 0 or m <= 0:
        r["mensaje"] = "capital o monto sin valor"
        return r

    pct = m / c
    r["pct"] = round(pct * 100, 2)
    r["sugerido"] = round(tamano(c, RIESGO_NORMAL), 2)
    # Cuántas pérdidas seguidas hasta quedarse sin capital operable
    r["aguanta"] = int(c // m) if m <= c else 0

    try:
        from . import monto_real as _mr
        f_m = _mr.formatear(m, divisa)
        f_s = _mr.formatear(r["sugerido"], divisa)
        f_c = _mr.formatear(c, divisa)
    except Exception:
        f_m, f_s, f_c = str(m), str(r["sugerido"]), str(c)

    if pct >= 0.90:
        r["nivel"] = "temerario"; r["grave"] = True
        r["mensaje"] = (
            f"⚠ SEÑOR: está poniendo {f_m} de un capital de {f_c}. Es el "
            f"{r['pct']:.1f} % de todo lo que tiene, en UNA operación. "
            f"Si falla, no queda nada — y aunque acierte 8 de cada 10 "
            f"veces, la que falla llega. Lo prudente serían {f_s}.")
    elif pct >= RIESGO_LIMITE:
        r["nivel"] = "alto"; r["grave"] = True
        r["mensaje"] = (
            f"{f_m} es el {r['pct']:.1f} % de su capital. Aguanta "
            f"{r['aguanta']} pérdidas seguidas antes de quedarse sin nada. "
            f"Con {f_s} aguantaría 50. Rachas de 8 fallos seguidos ocurren "
            f"aunque se acierte el 80 %.")
    elif pct > RIESGO_NORMAL:
        r["nivel"] = "moderado"
        r["mensaje"] = (f"{f_m} es el {r['pct']:.1f} %. Algo por encima del "
                        f"2 % recomendado, pero manejable: aguanta "
                        f"{r['aguanta']} fallos seguidos.")
    else:
        r["nivel"] = "prudente"
        r["mensaje"] = (f"{f_m} es el {r['pct']:.2f} % — dentro de lo sano. "
                        f"Aguanta {r['aguanta']} pérdidas seguidas.")
    return r


def sugerir(app, riesgo_pct: float = RIESGO_NORMAL) -> str:
    """Cuánto debería poner el señor, según su capital real."""
    cfg = app.mem.get("config", {})
    cap = cfg.get("saldo") or cfg.get("capital") or 0
    monto = cfg.get("monto_broker") or cfg.get("monto_base") or 0
    div = cfg.get("divisa", "")

    if not cap:
        return ("No sé cuál es su saldo, señor. Dígame «mi saldo es X» y "
                "calculo el monto que le corresponde. Sin saber el "
                "capital, cualquier cifra que le diga sería inventada.")

    ev = evaluar_tamano(cap, monto, div) if monto else {}
    try:
        from . import monto_real as _mr
        f = lambda v: _mr.formatear(v, div)
    except Exception:
        f = lambda v: str(v)

    l = [f"TAMAÑO DE POSICIÓN — capital {f(cap)}", ""]
    l.append(f"· 1 % (prudente) : {f(tamano(cap, RIESGO_PRUDENTE))}")
    l.append(f"· 2 % (normal)   : {f(tamano(cap, RIESGO_NORMAL))}")
    l.append(f"· 5 % (límite)   : {f(tamano(cap, RIESGO_LIMITE))}")
    if ev.get("mensaje"):
        l.append("")
        l.append(f"Ahora tiene puesto: {ev['mensaje']}")
    l.append("")
    l.append("La regla no es capricho: con el 2 %, hacen falta 50 pérdidas "
             "seguidas para quedarse sin capital. Ninguna racha mala le "
             "saca del juego. Con el 100 %, basta una.")
    return "\n".join(l)


def informe(app, asset: str = "") -> str:
    """Qué mercado es y cuánto conviene poner en él."""
    cfg = app.mem.get("config", {})
    nombre = asset or cfg.get("asset", "") or ""
    d = identificar(nombre)

    l = [f"MERCADO — {nombre or 'sin identificar'}", ""]
    l.append(f"· Tipo   : {d['descripcion'] or 'no lo reconozco'}")
    if d["otc"]:
        l.append("")
        l.append(f"⚠ {d['aviso']}")
        l.append("")
        l.append(f"Guardo sus patrones aparte, bajo «{clave_memoria(nombre)}», "
                 f"para no mezclarlos con los del activo real.")
    l.append("")
    l.append(sugerir(app))
    return "\n".join(l)


__all__ = ["identificar", "clave_memoria", "tamano", "evaluar_tamano",
           "sugerir", "informe", "TIPOS",
           "RIESGO_PRUDENTE", "RIESGO_NORMAL", "RIESGO_LIMITE"]

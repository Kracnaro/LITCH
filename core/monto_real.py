"""
monto_real.py — El monto y la divisa los pone el señor, no Litch.

━━━ EL PROBLEMA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En la pantalla de IQ Option el señor tenía puesto:

    Invers   CO$ 2,000

Y Litch anunciaba: «Operaré con dinero DEMO de práctica: **$50** por
trade». Dos errores en una sola frase:

  1. LA CIFRA. Litch usaba su propio `monto` guardado en configuración,
     que no tiene nada que ver con lo que el señor puso en el bróker.
     El que manda es el campo del bróker: es el que mueve el dinero.

  2. LA DIVISA. Decía «$» dando a entender dólares, cuando la cuenta
     está en **pesos colombianos**. CO$ 2.000 y US$ 2.000 no se parecen
     en nada — hay un factor de unos 4.000 entre uno y otro.

━━━ POR QUÉ ES GRAVE Y NO SOLO FEO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Todo lo que Litch calcula con el monto queda mal: la esperanza
matemática, el tamaño por riesgo, el P&L estimado, los límites de
pérdida diaria. Si cree que arriesga 50 cuando arriesga 2.000, sus
frenos de seguridad saltan cuarenta veces más tarde de lo debido.

Un sistema de riesgo que no sabe cuánto se está arriesgando no es un
sistema de riesgo.

━━━ LA REGLA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Manda lo que hay en la pantalla del bróker.

Litch lee el campo «Invers», guarda la cifra y la divisa, y las usa tal
cual. Si no puede leerlo, lo dice — no se inventa un número.
"""

from __future__ import annotations

import re

# Símbolos de divisa que IQ Option puede mostrar, y su nombre.
DIVISAS = {
    "CO$": "pesos colombianos", "COP": "pesos colombianos",
    "US$": "dólares", "USD": "dólares", "$": "dólares",
    "€":   "euros",   "EUR": "euros",
    "R$":  "reales",  "BRL": "reales",
    "MX$": "pesos mexicanos", "MXN": "pesos mexicanos",
    "AR$": "pesos argentinos", "ARS": "pesos argentinos",
    "£":   "libras",  "GBP": "libras",
}

# Se prueban primero los símbolos largos: si se buscara «$» antes que
# «CO$», todo pasaría por dólares y ese es justo el error que se corrige.
_ORDEN = sorted(DIVISAS.keys(), key=len, reverse=True)


def interpretar(texto: str) -> dict:
    """
    Saca cifra y divisa de un texto como «CO$ 2,000» o «Invers $50».

    Devuelve {"monto": float|None, "divisa": str, "nombre": str,
              "texto": str}. Si no hay número claro, monto es None —
    nunca un valor inventado.
    """
    r = {"monto": None, "divisa": "", "nombre": "", "texto": texto or ""}
    if not texto:
        return r

    t = str(texto).strip()

    for sim in _ORDEN:
        if sim in t:
            r["divisa"] = sim
            r["nombre"] = DIVISAS[sim]
            break

    # El número: se admiten «2,000», «2.000», «2000.50», «50»
    m = re.search(r"(\d[\d.,\s]*)", t)
    if not m:
        return r
    crudo = m.group(1).strip().replace(" ", "")

    # ¿La coma y el punto son separador de miles o decimal? Se decide por
    # la posición: si el último separador deja 1-2 cifras detrás, es
    # decimal; si deja 3, es de miles.
    try:
        if "," in crudo and "." in crudo:
            ult = max(crudo.rfind(","), crudo.rfind("."))
            dec = len(crudo) - ult - 1
            if dec <= 2:
                ent = re.sub(r"[.,]", "", crudo[:ult])
                r["monto"] = float(f"{ent}.{crudo[ult+1:]}")
            else:
                r["monto"] = float(re.sub(r"[.,]", "", crudo))
        elif "," in crudo or "." in crudo:
            sep = "," if "," in crudo else "."
            dec = len(crudo) - crudo.rfind(sep) - 1
            if dec == 3:                       # 2,000 -> dos mil
                r["monto"] = float(crudo.replace(sep, ""))
            else:                              # 50,5 -> cincuenta y medio
                r["monto"] = float(crudo.replace(sep, "."))
        else:
            r["monto"] = float(crudo)
    except Exception:
        r["monto"] = None
    return r


def formatear(monto: float, divisa: str = "") -> str:
    """«2000» + «CO$» → «CO$ 2,000». Sin divisa, no inventa el símbolo."""
    try:
        m = float(monto)
    except Exception:
        return str(monto)
    txt = f"{m:,.0f}" if abs(m - round(m)) < 0.005 else f"{m:,.2f}"
    return f"{divisa} {txt}".strip() if divisa else txt


# ── Leer de la pantalla del bróker ───────────────────────────────────────────

def leer_de_pantalla(app) -> dict:
    """
    Lee el campo «Invers» de IQ Option.

    Si hay una región calibrada para el monto, se mira ahí. Si no, se
    devuelve lo guardado, avisando de que no se ha comprobado contra la
    pantalla.
    """
    cfg = app.mem.get("config", {})
    region = cfg.get("region_monto")

    if region:
        try:
            import pyautogui, pytesseract
            x1, y1, x2, y2 = (int(v) for v in region[:4])
            img = pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1))
            txt = pytesseract.image_to_string(img, config="--psm 7")
            d = interpretar(txt)
            if d["monto"]:
                d["fuente"] = "pantalla"
                return d
        except Exception:
            pass

    d = {"monto": cfg.get("monto_broker") or cfg.get("monto_base")
                  or cfg.get("monto"),
         "divisa": cfg.get("divisa", ""),
         "nombre": DIVISAS.get(cfg.get("divisa", ""), ""),
         "texto": "", "fuente": "memoria"}
    try:
        d["monto"] = float(d["monto"]) if d["monto"] is not None else None
    except Exception:
        d["monto"] = None
    return d


def fijar(app, monto: float, divisa: str = "") -> str:
    """Guarda el monto y la divisa que el señor está usando de verdad."""
    from . import memoria as _m
    cfg = app.mem.setdefault("config", {})
    try:
        cfg["monto_broker"] = float(monto)
        cfg["monto_base"] = float(monto)
        cfg["monto"] = float(monto)
        if divisa:
            cfg["divisa"] = divisa
        _m.guardar(app.mem)
    except Exception as e:
        return f"No pude guardarlo: {e}"
    nom = DIVISAS.get(divisa, "")
    return (f"Anotado, señor: opero con {formatear(monto, divisa)}"
            + (f" ({nom})" if nom else "") +
            ". Con esta cifra calculo la esperanza, el riesgo y los "
            "límites de pérdida — antes usaba 50 y eso descuadraba todos "
            "mis frenos.")


def descripcion(app) -> str:
    """Qué monto cree Litch que está usando, y de dónde lo sacó."""
    d = leer_de_pantalla(app)
    if d["monto"] is None:
        return ("No sé con cuánto está operando, señor. Dígamelo — «opero "
                "con 2000 pesos» — y lo uso para todos mis cálculos. "
                "Prefiero preguntar a suponer 50 y equivocarme en todo lo "
                "que dependa de esa cifra.")
    fuente = ("leído de la pantalla del bróker" if d.get("fuente") == "pantalla"
              else "de lo que usted me dijo")
    txt = f"Opero con {formatear(d['monto'], d['divisa'])}"
    if d["nombre"]:
        txt += f" — {d['nombre']}"
    return (f"{txt}. ({fuente}.)\n\n"
            f"Con esta cifra calculo la esperanza matemática, el tamaño por "
            f"riesgo y los límites de pérdida diaria. Si la cambia en el "
            f"bróker, dígamelo: si creo que arriesgo 50 cuando arriesga "
            f"2.000, mis frenos saltarían cuarenta veces más tarde de lo "
            f"debido.")


__all__ = ["interpretar", "formatear", "leer_de_pantalla", "fijar",
           "descripcion", "DIVISAS"]

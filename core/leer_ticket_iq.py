"""
leer_ticket_iq.py — Litch lee de la pantalla lo que el señor puso.

━━━ EL PROBLEMA, POR TERCERA VEZ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En la pantalla de IQ Option el señor tenía:

    Invers        CO$ 6,000
    Vencimiento   30 seg
    Beneficio     +85 %   (+CO$ 5,100)

Y Litch anunciaba: «Operaré con dinero DEMO: **$50** por trade».

No es solo un letrero mal puesto. Con esas cifras Litch calcula la
esperanza matemática, el tamaño por riesgo, el límite de pérdida diaria
y el punto de equilibrio. **Si cree que arriesga 50 cuando arriesga
6.000, todos sus frenos saltan 120 veces más tarde de lo debido.**

Eso ya costó dinero real.

━━━ LA SOLUCIÓN: MIRAR, NO SUPONER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Litch ya sabe leer píxeles — lleva toda la sesión leyendo velas. Lo que
faltaba era apuntar esa capacidad al sitio correcto: el panel derecho
del ticket, donde están las tres cifras que gobiernan cada operación.

Se calibra una vez (el señor señala dónde están) y a partir de ahí se
lee sola antes de cada operación. Si cambia el monto en el bróker, Litch
se entera en la siguiente lectura sin que nadie le diga nada.

━━━ Y SI NO PUEDE LEER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lo dice. No supone. Un número inventado en el sitio del monto es peor
que no tener número, porque los cálculos siguen adelante con confianza.
"""

from __future__ import annotations

import re
import time

# Dónde están las cifras dentro del panel derecho de IQ Option, en
# proporción de la pantalla. Son el punto de partida; la calibración
# del señor las sustituye por las suyas.
ZONAS_POR_DEFECTO = {
    "monto":       (0.918, 0.125, 0.995, 0.180),
    "vencimiento": (0.918, 0.195, 0.995, 0.245),
    "pago":        (0.918, 0.290, 0.995, 0.360),
}

_CACHE = {"t": 0.0, "datos": {}}
_TTL = 4.0        # segundos: el señor no cambia el monto cada segundo


def _zonas(app) -> dict:
    try:
        z = app.mem.get("config", {}).get("zonas_ticket_iq")
        if isinstance(z, dict) and z:
            return {k: tuple(v) for k, v in z.items()}
    except Exception:
        pass
    return dict(ZONAS_POR_DEFECTO)


def _ocr(region_abs) -> str:
    """Texto de una región de pantalla. Cadena vacía si no se puede."""
    try:
        import pyautogui, pytesseract
        x1, y1, x2, y2 = (int(v) for v in region_abs)
        img = pyautogui.screenshot(region=(x1, y1, max(1, x2 - x1),
                                           max(1, y2 - y1)))
        # psm 7 = una sola línea de texto. Es lo que hay en estos campos.
        return pytesseract.image_to_string(img, config="--psm 7").strip()
    except Exception:
        return ""


def _abs(app, prop) -> tuple:
    """De proporción de pantalla a píxeles."""
    try:
        from . import vision_total as _vt
        sw, sh = _vt.tamano_pantalla()
    except Exception:
        sw, sh = 1920, 1080
    x1, y1, x2, y2 = prop
    return (int(x1 * sw), int(y1 * sh), int(x2 * sw), int(y2 * sh))


def interpretar_vencimiento(texto: str) -> int:
    """«30 seg» → 30 · «1 min» → 60 · «5 min» → 300. 0 si no se entiende."""
    t = (texto or "").lower()
    m = re.search(r"(\d+)\s*(seg|s\b|min|m\b|hor|h\b)", t)
    if not m:
        m2 = re.search(r"(\d+)", t)
        return int(m2.group(1)) if m2 else 0
    n = int(m.group(1)); u = m.group(2)
    if u.startswith("seg") or u == "s":
        return n
    if u.startswith("min") or u == "m":
        return n * 60
    return n * 3600


def interpretar_pago(texto: str) -> float:
    """«+85 %» → 85.0"""
    m = re.search(r"(\d{1,3})\s*%", texto or "")
    return float(m.group(1)) if m else 0.0


def leer(app, forzar: bool = False) -> dict:
    """
    Lee monto, vencimiento y pago del ticket de IQ Option.

    Devuelve lo que consiguió leer y de dónde. Lo que no pueda leer sale
    como None — nunca como un valor por defecto disfrazado de lectura.
    """
    ahora = time.time()
    if not forzar and (ahora - _CACHE["t"]) < _TTL and _CACHE["datos"]:
        return dict(_CACHE["datos"])

    z = _zonas(app)
    r = {"monto": None, "divisa": "", "vencimiento": None, "pago": None,
         "leido": [], "fallado": [], "hora": time.strftime("%H:%M:%S")}

    # ── Monto ──
    txt = _ocr(_abs(app, z.get("monto", ZONAS_POR_DEFECTO["monto"])))
    if txt:
        try:
            from . import monto_real as _mr
            d = _mr.interpretar(txt)
            if d["monto"]:
                r["monto"] = d["monto"]
                r["divisa"] = d["divisa"]
                r["leido"].append("monto")
        except Exception:
            pass
    if r["monto"] is None:
        r["fallado"].append("monto")

    # ── Vencimiento ──
    txt = _ocr(_abs(app, z.get("vencimiento", ZONAS_POR_DEFECTO["vencimiento"])))
    v = interpretar_vencimiento(txt)
    if v > 0:
        r["vencimiento"] = v
        r["leido"].append("vencimiento")
    else:
        r["fallado"].append("vencimiento")

    # ── Pago ──
    txt = _ocr(_abs(app, z.get("pago", ZONAS_POR_DEFECTO["pago"])))
    p = interpretar_pago(txt)
    if p > 0:
        r["pago"] = p
        r["leido"].append("pago")
    else:
        r["fallado"].append("pago")

    _CACHE.update({"t": ahora, "datos": dict(r)})
    return r


def sincronizar(app, hablar: bool = False) -> str:
    """
    Lee el ticket y pone esos valores en la configuración de Litch.

    Es la función que hace que Litch trabaje con LOS NÚMEROS DEL SEÑOR y
    no con los suyos. Solo pisa lo que consiguió leer: si no leyó el
    vencimiento, no lo toca.
    """
    d = leer(app, forzar=True)
    cfg = app.mem.setdefault("config", {})
    cambios = []

    if d["monto"]:
        antes = cfg.get("monto_broker") or cfg.get("monto_base")
        if antes != d["monto"]:
            cambios.append(f"monto {antes} → {d['monto']}")
        cfg["monto_broker"] = d["monto"]
        cfg["monto_base"] = d["monto"]
        cfg["monto"] = d["monto"]
        if d["divisa"]:
            cfg["divisa"] = d["divisa"]

    if d["vencimiento"]:
        antes = cfg.get("vencimiento")
        if antes != d["vencimiento"]:
            cambios.append(f"vencimiento {antes}s → {d['vencimiento']}s")
        cfg["vencimiento"] = d["vencimiento"]
        cfg["periodo_vela"] = d["vencimiento"]

    if d["pago"]:
        antes = cfg.get("pago_pct")
        if antes != d["pago"]:
            cambios.append(f"pago {antes}% → {d['pago']}%")
        cfg["pago_pct"] = d["pago"]

    try:
        from . import memoria as _m
        _m.guardar(app.mem)
    except Exception:
        pass

    if not d["leido"]:
        msg = ("No consigo leer el ticket de IQ Option, señor. Dígame "
               "«calibra el ticket» y me señala dónde están el monto, el "
               "vencimiento y el pago. Prefiero preguntar a suponer.")
    else:
        partes = []
        if d["monto"]:
            try:
                from . import monto_real as _mr
                partes.append(_mr.formatear(d["monto"], d["divisa"]))
            except Exception:
                partes.append(str(d["monto"]))
        if d["vencimiento"]:
            partes.append(f"{d['vencimiento']} s")
        if d["pago"]:
            partes.append(f"pago {d['pago']:.0f} %")
        msg = "Leído de su pantalla: " + " · ".join(partes) + "."
        if cambios:
            msg += " Cambios: " + "; ".join(cambios) + "."
        if d["fallado"]:
            msg += (f" No pude leer: {', '.join(d['fallado'])} — "
                    f"esos los dejo como estaban.")
        # El equilibrio depende del pago: si cambió, el umbral cambia.
        if d["pago"]:
            try:
                from . import ventaja_real as _vr
                eq = _vr.punto_equilibrio(d["pago"])
                msg += (f" Con un pago del {d['pago']:.0f} % necesito acertar "
                        f"el {eq*100:.1f} % para no perder.")
            except Exception:
                pass

    if hablar:
        try:
            app.decir(msg)
        except Exception:
            app.log(msg)
    return msg


def calibrar(app, segundos: int = 6) -> str:
    """
    El señor señala con el ratón dónde está cada cifra.

    Mismo método que ya funcionó con el ticket de TWS: se pone el ratón
    encima, Litch anota la proporción. Sobrevive a cambios de resolución.
    """
    import threading

    campos = [("monto", "el campo «Invers» con la cantidad"),
              ("vencimiento", "el campo «Vencimiento»"),
              ("pago", "el porcentaje de «Beneficio»")]

    def _tarea():
        try:
            import pyautogui
            from . import vision_total as _vt
            sw, sh = _vt.tamano_pantalla()
            z = {}
            for clave, desc in campos:
                app.decir(f"Ponga el ratón sobre {desc}. Tiene "
                          f"{segundos} segundos.")
                time.sleep(segundos)
                x, y = pyautogui.position()
                # Una caja alrededor del punto: el texto ocupa algo más
                # que el píxel exacto donde se puso el ratón.
                z[clave] = (max(0.0, (x - 70) / sw), max(0.0, (y - 16) / sh),
                            min(1.0, (x + 70) / sw), min(1.0, (y + 16) / sh))
                app.log(f"[Ticket] {clave} anotado en ({x},{y})")
            app.mem.setdefault("config", {})["zonas_ticket_iq"] = \
                {k: list(v) for k, v in z.items()}
            from . import memoria as _m
            _m.guardar(app.mem)
            app.decir("Ticket calibrado, señor. " + sincronizar(app))
        except Exception as e:
            app.log(f"[Ticket] Error calibrando: {e}")

    threading.Thread(target=_tarea, daemon=True, name="CalibTicketIQ").start()
    return (f"Empezamos, señor. Le voy pidiendo que ponga el ratón sobre "
            f"cada cifra del ticket, {segundos} segundos cada una. "
            f"Guardo proporciones, no píxeles: así sigue sirviendo aunque "
            f"cambie el tamaño de la ventana.")


def descripcion(app) -> str:
    """Con qué números está trabajando Litch, y de dónde salieron."""
    d = leer(app)
    cfg = app.mem.get("config", {})
    l = ["CON QUÉ NÚMEROS ESTOY OPERANDO", ""]

    def _fmt(v, suf=""):
        return f"{v}{suf}" if v is not None else "— no lo sé —"

    try:
        from . import monto_real as _mr
        m_txt = (_mr.formatear(d["monto"], d["divisa"]) if d["monto"]
                 else _fmt(cfg.get("monto_broker")))
    except Exception:
        m_txt = _fmt(d["monto"])

    l.append(f"· Monto        : {m_txt}"
             + ("  (leído de su pantalla)" if "monto" in d["leido"]
                else "  (de memoria — NO leído)"))
    l.append(f"· Vencimiento  : {_fmt(d['vencimiento'] or cfg.get('vencimiento'), ' s')}"
             + ("  (leído)" if "vencimiento" in d["leido"] else "  (de memoria)"))
    l.append(f"· Pago         : {_fmt(d['pago'] or cfg.get('pago_pct'), ' %')}"
             + ("  (leído)" if "pago" in d["leido"] else "  (de memoria)"))

    pago = d["pago"] or cfg.get("pago_pct") or 85
    try:
        from . import ventaja_real as _vr
        eq = _vr.punto_equilibrio(pago)
        monto = d["monto"] or cfg.get("monto_broker") or 0
        l.append("")
        l.append(f"Con pago {pago:.0f} % necesito acertar {eq*100:.2f} % "
                 f"para no perder.")
        if monto:
            l.append(f"Cada operación pone {m_txt} en juego. Acertando la "
                     f"mitad, cada 100 operaciones perdería "
                     f"{abs(_vr.esperanza(0.5, pago, monto))*100:,.0f}.")
    except Exception:
        pass

    if d["fallado"]:
        l.append("")
        l.append(f"NO consigo leer: {', '.join(d['fallado'])}. "
                 f"Dígame «calibra el ticket» y lo arreglamos.")
    return "\n".join(l)


__all__ = ["leer", "sincronizar", "calibrar", "descripcion",
           "interpretar_vencimiento", "interpretar_pago", "ZONAS_POR_DEFECTO"]

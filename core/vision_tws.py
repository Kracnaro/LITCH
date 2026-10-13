"""
vision_tws.py — Los OJOS de Litch para Trader Workstation (IBKR).

Litch ya sabía ver el gráfico de IQ Option. Este módulo le enseña a ver el
de TWS, que es distinto: el gráfico está en el centro-izquierda, la barra
roja de "negociación simulada" arriba, la watchlist a la derecha.

QUÉ HACE:
  · Detecta automáticamente la ventana de TWS y la región de su gráfico.
  · Lee el número de cuenta (DU = simulada, U = real) — seguridad crítica.
  · Distingue si TWS está al frente o tapado por otra ventana.
  · Cambia la calibración de Litch entre IQ Option y TWS sin perder ninguna.

FILOSOFÍA: los ojos sirven para ANALIZAR (leer velas, ver el contexto).
La ejecución va por la API (bracket con stop y objetivo). Nunca clics a
ciegas sobre el botón que mueve dinero.
"""

from __future__ import annotations

import time

try:
    import numpy as np
    _NP_OK = True
except Exception:
    _NP_OK = False


# ═══════════════════════════════════════════════════════════════════════════
#  Detección de la ventana de TWS
# ═══════════════════════════════════════════════════════════════════════════

def ventana_tws() -> dict | None:
    """Busca la ventana de TWS y devuelve su posición y tamaño.

    Devuelve {"titulo": str, "x": int, "y": int, "w": int, "h": int,
              "al_frente": bool} o None si no la encuentra.
    """
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        encontrada = {}

        # Claves normalizadas SIN espacios.
        #
        # ESTO ERA EL FALLO: la ventana real de IBKR se titula
        # "InteractiveBrokers" —todo junto— y aquí se buscaba
        # "interactive brokers" con espacio. Litch tenía TWS delante de las
        # narices y contestaba que no lo veía. Comparar quitando espacios
        # hace que dé igual cómo lo escriban.
        CLAVES = ("traderworkstation", "interactivebrokers", "tws",
                  "ibgateway", "ibkr", "mosaico", "mosaic")

        import re as _re_w

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _lparam):
            if not u32.IsWindowVisible(hwnd):
                return True
            n = u32.GetWindowTextLengthW(hwnd)
            if n == 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            titulo = buf.value or ""
            tl = titulo.lower()
            # Normalizar: sin espacios, guiones ni puntos
            plano = _re_w.sub(r"[\s\-_.]+", "", tl)
            # Reconocer también por el número de cuenta (DU… o U…),
            # que aparece en el título de TWS aunque cambien el nombre.
            por_cuenta = bool(_re_w.search(r"\bdu[a-z]*\d{6,}", tl))
            if any(k in plano for k in CLAVES) or por_cuenta:
                rect = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(rect))
                ancho = rect.right - rect.left
                alto = rect.bottom - rect.top
                # Quedarse con la ventana más grande (la principal)
                if ancho > 400 and alto > 300:
                    if ancho * alto > encontrada.get("area", 0):
                        encontrada.update({
                            "titulo": titulo, "hwnd": hwnd,
                            "x": rect.left, "y": rect.top,
                            "w": ancho, "h": alto,
                            "area": ancho * alto,
                        })
            return True

        u32.EnumWindows(_cb, 0)
        if not encontrada:
            return None
        # ¿Está al frente?
        try:
            encontrada["al_frente"] = (
                u32.GetForegroundWindow() == encontrada["hwnd"])
        except Exception:
            encontrada["al_frente"] = False
        encontrada.pop("area", None)
        encontrada.pop("hwnd", None)
        return encontrada
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  Región del gráfico dentro de TWS (layout Mosaico)
# ═══════════════════════════════════════════════════════════════════════════

# Proporciones del layout Mosaico de TWS, medidas sobre la ventana:
#   · El gráfico ocupa aprox. del 23% al 64% del ancho
#   · y del 28% al 72% del alto
# Se ajustan solos si el usuario recalibra a mano.
PROP_GRAFICO = {"x1": 0.23, "y1": 0.28, "x2": 0.64, "y2": 0.72}


def diagnostico_ventanas() -> str:
    """Lista TODAS las ventanas visibles y dice cuál cree que es TWS.

    Existe por una razón concreta: cuando Litch decía "no veo TWS" con TWS
    abierto delante, no había forma de saber por qué. Resultó ser que la
    ventana se titula «InteractiveBrokers» —sin espacio— y se buscaba
    «Interactive Brokers». Un espacio.

    Con esto, si vuelve a fallar, se ve el título exacto en un segundo en
    lugar de adivinar.
    """
    try:
        import ctypes
        import re
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        vistas = []
        try:
            frente = u32.GetForegroundWindow()
        except Exception:
            frente = None

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _lp):
            try:
                if not u32.IsWindowVisible(hwnd):
                    return True
                n = u32.GetWindowTextLengthW(hwnd)
                if n == 0:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, buf, n + 1)
                t = (buf.value or "").strip()
                if not t:
                    return True
                r = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(r))
                w, h = r.right - r.left, r.bottom - r.top
                if w > 200 and h > 150:
                    vistas.append((t, w, h, hwnd == frente))
            except Exception:
                pass
            return True

        u32.EnumWindows(_cb, 0)

        if not vistas:
            return "No veo ninguna ventana, señor. Eso es raro de por sí."

        CLAVES = ("traderworkstation", "interactivebrokers", "tws",
                  "ibgateway", "ibkr", "mosaico", "mosaic")
        lineas = [f"Veo {len(vistas)} ventanas. Estas son, con su título "
                  f"exacto:"]
        candidatas = 0
        for t, w, h, ff in sorted(vistas, key=lambda x: -x[1] * x[2])[:14]:
            plano = re.sub(r"[\s\-_.]+", "", t.lower())
            cuenta = re.search(r"\bdu[a-z]*\d{6,}", t.lower())
            es = any(k in plano for k in CLAVES) or bool(cuenta)
            if es:
                candidatas += 1
            marca = "→ ES TWS" if es else "        "
            frente_m = " [al frente]" if ff else ""
            lineas.append(f"  {marca}  «{t[:62]}»  {w}×{h}{frente_m}")

        v = ventana_tws()
        lineas.append("")
        if v:
            lineas.append(f"Elijo «{v['titulo'][:60]}» ({v['w']}×{v['h']}) "
                          f"como la ventana de Interactive Brokers.")
        elif candidatas:
            lineas.append("Reconozco candidatas pero ninguna pasa el filtro "
                          "de tamaño (mínimo 400×300).")
        else:
            lineas.append("NINGUNA me cuadra con Interactive Brokers. Si "
                          "alguna de las de arriba es TWS, dígamelo y "
                          "añado ese título a los que reconozco.")
        return "\n".join(lineas)
    except Exception as e:
        return f"No pude listar las ventanas: {e}"


def region_grafico_tws() -> list | None:
    """Calcula la región del gráfico de TWS en coordenadas de pantalla.

    Devuelve [x1, y1, x2, y2] listo para la visión de Litch, o None.
    """
    v = ventana_tws()
    if not v:
        return None
    x1 = int(v["x"] + v["w"] * PROP_GRAFICO["x1"])
    y1 = int(v["y"] + v["h"] * PROP_GRAFICO["y1"])
    x2 = int(v["x"] + v["w"] * PROP_GRAFICO["x2"])
    y2 = int(v["y"] + v["h"] * PROP_GRAFICO["y2"])
    return [x1, y1, x2, y2]


def calibrar_para_tws(app) -> str:
    """Cambia la visión de Litch al gráfico de TWS.

    Guarda la calibración de IQ Option para poder volver después.
    """
    v = ventana_tws()
    if not v:
        return ("No encuentro la ventana de Trader Workstation, señor. "
                "Ábrala y déjela visible (no minimizada).")

    reg = region_grafico_tws()
    if not reg:
        return "Encontré TWS pero no pude calcular la región del gráfico."

    cfg = app.mem["config"]
    # Guardar la calibración anterior (IQ Option) para no perderla
    if cfg.get("region_grafico") and not cfg.get("region_grafico_iq"):
        cfg["region_grafico_iq"] = list(cfg["region_grafico"])

    cfg["region_grafico"] = reg
    cfg["region_grafico_tws"] = list(reg)
    cfg["broker_visual"] = "tws"
    try:
        from . import memoria
        memoria.guardar(app.mem)
    except Exception:
        pass

    return (f"Visión calibrada para Interactive Brokers, señor. "
            f"Ventana «{v['titulo'][:40]}» detectada "
            f"({v['w']}x{v['h']}). Región del gráfico: {reg}. "
            f"Ya leo las velas de TWS. Si el gráfico no queda bien "
            f"encuadrado, use el botón 📐 para ajustarlo a mano.")


def volver_a_iq(app) -> str:
    """Restaura la calibración de IQ Option."""
    cfg = app.mem["config"]
    prev = cfg.get("region_grafico_iq")
    if not prev:
        return "No tengo guardada una calibración previa de IQ Option, señor."
    cfg["region_grafico"] = list(prev)
    cfg["broker_visual"] = "iq"
    try:
        from . import memoria
        memoria.guardar(app.mem)
    except Exception:
        pass
    return "Visión restaurada a IQ Option, señor."


# ═══════════════════════════════════════════════════════════════════════════
#  Lectura del estado de TWS
# ═══════════════════════════════════════════════════════════════════════════

def leer_estado_tws(app) -> dict:
    """Lee el estado visual de TWS: ventana, cuenta, si está al frente.

    Es la "conciencia visual" de Litch sobre IBKR.
    """
    estado = {"tws_abierta": False, "al_frente": False, "titulo": "",
              "cuenta": "", "es_paper": None, "region_ok": False,
              "mensaje": ""}

    v = ventana_tws()
    if not v:
        estado["mensaje"] = ("No veo Trader Workstation abierto. Para operar "
                             "en Wall Street necesito que TWS esté abierto "
                             "y visible.")
        return estado

    estado.update({"tws_abierta": True, "al_frente": v.get("al_frente", False),
                   "titulo": v["titulo"]})

    # El título de TWS suele traer la cuenta: "DU1234567 ... Simulated Trading"
    import re
    m = re.search(r"\b(DU?[A-Z]*\d{6,})\b", v["titulo"].upper())
    if m:
        estado["cuenta"] = m.group(1)
        estado["es_paper"] = m.group(1).startswith("DU")
    elif "simulated" in v["titulo"].lower() or "simulada" in v["titulo"].lower():
        estado["es_paper"] = True

    # ¿La región calibrada corresponde a TWS?
    cfg = app.mem.get("config", {})
    estado["region_ok"] = (cfg.get("broker_visual") == "tws"
                           and bool(cfg.get("region_grafico")))

    partes = [f"TWS abierto ({v['w']}x{v['h']})."]
    partes.append("Está al frente." if estado["al_frente"]
                  else "Está detrás de otra ventana — puedo verlo igual, "
                       "pero si lo tapan del todo perderé la vista.")
    if estado["es_paper"] is True:
        partes.append(f"Cuenta {estado['cuenta'] or 'simulada'}: PAPER "
                      f"(dinero ficticio) ✓ seguro para practicar.")
    elif estado["es_paper"] is False:
        partes.append(f"⚠ Cuenta {estado['cuenta']}: REAL. Cada operación "
                      f"movería dinero verdadero.")
    partes.append("Visión calibrada para TWS ✓" if estado["region_ok"]
                  else "Mi visión NO está calibrada para TWS todavía — "
                       "dígame 'calibra para IBKR'.")
    estado["mensaje"] = " ".join(partes)
    return estado


def analizar_grafico_tws(app) -> dict:
    """Lee las velas del gráfico de TWS con la visión de Litch.

    Reutiliza el motor de visión que ya funciona con IQ Option, apuntado
    a la región de TWS.
    """
    from . import vision as _vis

    res = {"ok": False, "color_ultima": None, "mensaje": ""}
    cfg = app.mem.get("config", {})
    if cfg.get("broker_visual") != "tws":
        res["mensaje"] = ("Mi visión no está apuntando a TWS. Dígame "
                          "'calibra para IBKR' primero.")
        return res
    reg = cfg.get("region_grafico")
    if not reg:
        res["mensaje"] = "No tengo región de gráfico calibrada."
        return res
    try:
        color = _vis.color_vela(reg)
        res["color_ultima"] = color
        res["ok"] = color is not None
        res["mensaje"] = (f"Última vela leída en TWS: "
                          f"{'VERDE (subió)' if color == 'V' else 'ROJA (bajó)' if color == 'R' else 'sin lectura clara'}.")
    except Exception as e:
        res["mensaje"] = f"No pude leer el gráfico de TWS: {e}"
    return res

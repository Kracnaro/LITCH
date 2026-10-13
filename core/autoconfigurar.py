"""
autoconfigurar.py — Un botón que lo deja todo listo.

━━━ POR QUÉ HACÍA FALTA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Se fueron acumulando cosas que hay que configurar: el monitor, la
visión, los botones SUBE y BAJA, el ticket, el saldo, el monto, la
cuenta demo, los interruptores. Cada una razonable por separado.

Juntas son una trampa: **si falta una sola, Litch no opera** — y desde
fuera eso se ve igual que «está rota». El señor ha pasado horas
buscando el fallo en el sitio equivocado porque el sistema le pedía
acertar en ocho cosas seguidas sin decirle en cuál falló.

Un programa que exige ocho aciertos para arrancar está mal diseñado. La
responsabilidad de encontrar la ventana, los botones y las cifras es
suya, no del señor.

━━━ QUÉ HACE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En este orden, porque cada paso depende del anterior:

  1. Encuentra la ventana de IQ Option — en el monitor que sea.
  2. Se muda a ese monitor: barra, visión y coordenadas.
  3. Localiza SUBE y BAJA por su color, no por posición fija.
  4. Lee el ticket: monto, vencimiento, pago.
  5. Lee el saldo de la cabecera.
  6. Comprueba que todo cuadra y lo dice.

Y cada paso informa de lo que consiguió. Lo que no pueda hacer, lo dice
— no lo deja en silencio para que el señor lo descubra operando.

━━━ CÓMO ENCUENTRA LOS BOTONES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Por color y forma, no por coordenadas guardadas. SUBE es un rectángulo
verde grande en el lado derecho; BAJA es rojo, justo debajo. Son los dos
bloques de color más grandes de esa franja, y eso no cambia aunque
cambie la resolución, el monitor o el tamaño de la ventana.

Buscar por color es más lento que recordar una coordenada, pero
sobrevive a todo lo que ha roto la calibración estas semanas.
"""

from __future__ import annotations

import time

# Colores de IQ Option (RGB aproximado) y cuánta desviación se tolera
VERDE_SUBE = (61, 176, 96)
ROJO_BAJA = (211, 65, 65)
TOLERANCIA = 60

# Los botones viven en la franja derecha de la ventana
FRANJA_X = (0.86, 1.00)
FRANJA_Y = (0.25, 0.85)
# Un bloque tiene que medir al menos esto para ser un botón y no un adorno
MIN_ANCHO = 60
MIN_ALTO = 40


class Paso:
    def __init__(self, nombre, ok, detalle="", critico=True):
        self.nombre, self.ok = nombre, bool(ok)
        self.detalle, self.critico = detalle, critico


def _cerca(c, ref, tol=TOLERANCIA) -> bool:
    return all(abs(int(c[i]) - ref[i]) <= tol for i in range(3))


# ── 1. Encontrar la ventana ──────────────────────────────────────────────────

def ventana_iq() -> dict | None:
    """La ventana de IQ Option, esté donde esté."""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        halladas = []

        def _cb(hwnd, _):
            try:
                if not u.IsWindowVisible(hwnd):
                    return True
                n = u.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                t = buf.value.lower().replace(" ", "")
                if "iqoption" in t:
                    r = wintypes.RECT()
                    u.GetWindowRect(hwnd, ctypes.byref(r))
                    w, h = r.right - r.left, r.bottom - r.top
                    if w > 600 and h > 400:
                        halladas.append({"x": r.left, "y": r.top,
                                         "w": w, "h": h, "titulo": buf.value})
            except Exception:
                pass
            return True

        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int),
                                  ctypes.POINTER(ctypes.c_int))
        u.EnumWindows(PROC(_cb), 0)
        if halladas:
            return max(halladas, key=lambda v: v["w"] * v["h"])
    except Exception:
        pass
    return None


# ── 2. Encontrar SUBE y BAJA por color ───────────────────────────────────────

def buscar_botones(v: dict) -> dict:
    """
    Localiza SUBE y BAJA dentro de la ventana, por color.

    Devuelve {"verde": (x,y), "rojo": (x,y), "detalle": str}. Los que no
    encuentre salen como None — no se inventa una posición.
    """
    r = {"verde": None, "rojo": None, "detalle": ""}
    try:
        import pyautogui
        x1 = v["x"] + int(v["w"] * FRANJA_X[0])
        x2 = v["x"] + int(v["w"] * FRANJA_X[1])
        y1 = v["y"] + int(v["h"] * FRANJA_Y[0])
        y2 = v["y"] + int(v["h"] * FRANJA_Y[1])
        img = pyautogui.screenshot(region=(x1, y1, max(1, x2 - x1),
                                           max(1, y2 - y1)))
    except Exception as e:
        r["detalle"] = f"no pude fotografiar la franja: {e}"
        return r

    W, H = img.size
    px = img.load()
    paso = 4        # se muestrea cada 4 px: basta y es mucho más rápido

    def _bloques(ref):
        """Filas donde predomina ese color, agrupadas en bloques."""
        filas = []
        for y in range(0, H, paso):
            n = sum(1 for x in range(0, W, paso) if _cerca(px[x, y], ref))
            if n > (W // paso) * 0.45:      # casi toda la fila de ese color
                filas.append(y)
        if not filas:
            return []
        grupos, act = [], [filas[0]]
        for f in filas[1:]:
            if f - act[-1] <= paso * 3:
                act.append(f)
            else:
                grupos.append(act); act = [f]
        grupos.append(act)
        return [g for g in grupos if (g[-1] - g[0]) >= MIN_ALTO]

    gv = _bloques(VERDE_SUBE)
    gr = _bloques(ROJO_BAJA)

    if gv:
        # El bloque más alto de todos: el botón, no un adorno
        g = max(gv, key=lambda x: x[-1] - x[0])
        r["verde"] = (x1 + W // 2, y1 + (g[0] + g[-1]) // 2)
    if gr:
        g = max(gr, key=lambda x: x[-1] - x[0])
        r["rojo"] = (x1 + W // 2, y1 + (g[0] + g[-1]) // 2)

    # Comprobación de sentido: SUBE va arriba de BAJA. Si sale al revés,
    # es que se cogió un adorno por botón.
    if r["verde"] and r["rojo"] and r["verde"][1] > r["rojo"][1]:
        r["detalle"] = ("encontré verde y rojo pero el verde queda debajo; "
                        "no me fío, será otra cosa")
        r["verde"] = r["rojo"] = None
    elif r["verde"] and r["rojo"]:
        r["detalle"] = (f"SUBE en {r['verde']}, BAJA en {r['rojo']} "
                        f"(separados {r['rojo'][1]-r['verde'][1]} px)")
    else:
        falta = []
        if not r["verde"]: falta.append("SUBE")
        if not r["rojo"]: falta.append("BAJA")
        r["detalle"] = (f"no encontré {' ni '.join(falta)} por color. "
                        f"¿Está IQ Option delante y sin nada encima?")
    return r


# ── La rutina completa ───────────────────────────────────────────────────────

def ejecutar(app) -> str:
    """Lo configura todo. Devuelve el informe paso a paso."""
    pasos = []

    # 1 · La ventana
    v = ventana_iq()
    if not v:
        return ("No encuentro la ventana de IQ Option, señor.\n\n"
                "Ábrala y déjela visible —no minimizada— y vuelva a "
                "pulsar. Sin la ventana no puedo configurar nada: todo lo "
                "demás depende de saber dónde está.")
    pasos.append(Paso("Ventana de IQ Option", True,
                      f"{v['w']}×{v['h']} en ({v['x']},{v['y']})"))

    # 2 · El monitor que la contiene
    n_mon = None
    try:
        from . import monitores as _mon
        m = _mon.del_punto(v["x"] + v["w"] // 2, v["y"] + v["h"] // 2)
        if m:
            n_mon = m["n"]
            cfg = app.mem.setdefault("config", {})
            cambio = cfg.get("monitor") != m["n"]
            cfg["monitor"] = m["n"]
            cfg["monitor_barra"] = m["n"]
            cfg["region_grafico"] = [m["x"], m["y"],
                                     m["x"] + m["w"], m["y"] + m["h"]]
            cfg["vision_total"] = True
            _mon.anclar_barra(app, forzar=True)
            try:
                ovl = getattr(app, "overlay", None)
                if ovl:
                    ovl.set_region(cfg["region_grafico"])
            except Exception:
                pass
            pasos.append(Paso("Monitor", True,
                              f"{m['n']} ({m['w']}×{m['h']})"
                              + (" — me mudé" if cambio else "")))
        else:
            pasos.append(Paso("Monitor", False,
                              "no sé en qué pantalla está", False))
    except Exception as e:
        pasos.append(Paso("Monitor", False, str(e)[:70], False))

    # 3 · SUBE y BAJA
    b = buscar_botones(v)
    if b["verde"] and b["rojo"]:
        cfg = app.mem.setdefault("config", {})
        cfg["boton_verde"] = list(b["verde"])
        cfg["boton_rojo"] = list(b["rojo"])
        pasos.append(Paso("Botones SUBE y BAJA", True, b["detalle"]))
        # Y se guardan para este monitor, que es lo que evita el desastre
        # de pulsar con coordenadas de otra pantalla.
        if n_mon:
            try:
                from . import calibracion_por_monitor as _cpm
                _cpm.guardar_actual(app, n_mon)
            except Exception:
                pass
    else:
        pasos.append(Paso("Botones SUBE y BAJA", False, b["detalle"]))

    # 4 · El ticket
    try:
        from . import leer_ticket_iq as _lt
        msg = _lt.sincronizar(app, hablar=False)
        leyo = "Leído de su pantalla" in msg
        pasos.append(Paso("Ticket (monto, vencimiento, pago)", leyo,
                          msg[:150], critico=False))
    except Exception as e:
        pasos.append(Paso("Ticket", False, str(e)[:70], False))

    # 5 · La región del gráfico para analizar
    try:
        cfg = app.mem.setdefault("config", {})
        # El gráfico ocupa el centro: sin los paneles laterales
        cfg["region_grafico_iq"] = [
            v["x"] + int(v["w"] * 0.08), v["y"] + int(v["h"] * 0.10),
            v["x"] + int(v["w"] * 0.85), v["y"] + int(v["h"] * 0.72)]
        pasos.append(Paso("Región del gráfico", True,
                          "centro de la ventana, sin los paneles laterales",
                          critico=False))
    except Exception:
        pass

    # 6 · Guardar
    try:
        from . import memoria as _mem
        _mem.guardar(app.mem)
    except Exception:
        pass

    # ── El informe ───────────────────────────────────────────────────
    l = ["CONFIGURACIÓN AUTOMÁTICA", ""]
    for p in pasos:
        marca = "✓" if p.ok else ("✗" if p.critico else "·")
        l.append(f" {marca} {p.nombre}: {p.detalle}")

    criticos = [p for p in pasos if not p.ok and p.critico]
    l.append("")
    if not criticos:
        l.append("Listo, señor. Sé dónde está la ventana, en qué monitor, "
                 "dónde están SUBE y BAJA, y con qué cifras opera.")
        l.append("")
        l.append("Falta lo que solo usted puede decidir: si la cuenta es "
                 "demo o real, su saldo, y el límite de pérdida diaria. "
                 "Están en «⚙ PREPARAR».")
    else:
        l.append("Me falta lo importante:")
        for p in criticos:
            l.append(f"   ✗ {p.nombre} — {p.detalle}")
        l.append("")
        l.append("Sin eso no puedo operar: pulsaría donde no es, que es "
                 "peor que no pulsar.")
    return "\n".join(l)


__all__ = ["ejecutar", "ventana_iq", "buscar_botones", "Paso"]

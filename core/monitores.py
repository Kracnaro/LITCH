"""
monitores.py — En qué pantalla tiene que mirar Litch.

━━━ EL PROBLEMA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Litch daba por hecho que solo había una pantalla. Toda su visión se
calculaba con `GetSystemMetrics(0)` y `GetSystemMetrics(1)`, que
devuelven el tamaño del monitor PRINCIPAL y nada más.

El señor tiene IQ Option en el monitor 2. Para Windows, ese monitor
empieza en la coordenada x=1920 (o en x=−1920 si está a la izquierda) —
fuera por completo del rectángulo que Litch creía que era «la pantalla».
Resultado: miraba el monitor equivocado y no encontraba nada, o peor,
leía píxeles de otro programa como si fueran velas.

━━━ CÓMO SE RESUELVE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Se le pregunta a Windows qué monitores hay y dónde empieza cada uno.
Windows los expone como un «escritorio virtual»: un rectángulo que
engloba todos, con coordenadas que pueden ser negativas.

    Monitor 1:  (    0, 0) → (1920, 1080)
    Monitor 2:  ( 1920, 0) → (3840, 1080)     ← a la derecha
    Monitor 2:  (-1920, 0) → (   0, 1080)     ← a la izquierda

El señor elige en cuál trabajar, y Litch calcula todas sus regiones
relativas a ESE monitor. Si no elige, Litch busca dónde está el bróker
y usa el monitor que lo contiene — que es lo que él querría.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes


def listar() -> list[dict]:
    """
    Todos los monitores conectados, con su rectángulo real.

    Devuelve [{n, x, y, w, h, principal}] en coordenadas de Windows,
    que pueden ser negativas si un monitor está a la izquierda.
    """
    monitores = []
    try:
        u = ctypes.windll.user32
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        PROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                                  ctypes.POINTER(RECT), ctypes.c_double)

        def _cb(hmon, hdc, lprect, data):
            r = lprect.contents
            monitores.append({
                "n": len(monitores) + 1,
                "x": int(r.left), "y": int(r.top),
                "w": int(r.right - r.left), "h": int(r.bottom - r.top),
                "principal": (r.left == 0 and r.top == 0),
            })
            return 1

        u.EnumDisplayMonitors(0, 0, PROC(_cb), 0)
    except Exception:
        pass

    if not monitores:
        # Sin API, al menos el principal
        try:
            u = ctypes.windll.user32
            monitores = [{"n": 1, "x": 0, "y": 0,
                          "w": int(u.GetSystemMetrics(0)),
                          "h": int(u.GetSystemMetrics(1)),
                          "principal": True}]
        except Exception:
            monitores = [{"n": 1, "x": 0, "y": 0, "w": 1920, "h": 1080,
                          "principal": True}]
    return monitores


def escritorio_virtual() -> tuple[int, int, int, int]:
    """El rectángulo que engloba TODOS los monitores. (x, y, w, h)"""
    try:
        u = ctypes.windll.user32
        return (int(u.GetSystemMetrics(76)), int(u.GetSystemMetrics(77)),
                int(u.GetSystemMetrics(78)), int(u.GetSystemMetrics(79)))
    except Exception:
        ms = listar()
        x1 = min(m["x"] for m in ms); y1 = min(m["y"] for m in ms)
        x2 = max(m["x"] + m["w"] for m in ms)
        y2 = max(m["y"] + m["h"] for m in ms)
        return (x1, y1, x2 - x1, y2 - y1)


def del_punto(x: int, y: int) -> dict | None:
    """Qué monitor contiene ese punto."""
    for m in listar():
        if m["x"] <= x < m["x"] + m["w"] and m["y"] <= y < m["y"] + m["h"]:
            return m
    return None


def del_ventana(titulo_parcial: str) -> dict | None:
    """
    En qué monitor está la ventana cuyo título contenga ese texto.

    Es la vía que de verdad se usa: el señor no tiene por qué saber
    números de monitor, solo dónde tiene abierto el bróker.
    """
    try:
        u = ctypes.windll.user32
        buscado = (titulo_parcial or "").lower()
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
                if buscado in buf.value.lower():
                    r = wintypes.RECT()
                    u.GetWindowRect(hwnd, ctypes.byref(r))
                    if (r.right - r.left) > 300 and (r.bottom - r.top) > 200:
                        halladas.append((r.left, r.top,
                                         r.right - r.left, r.bottom - r.top))
            except Exception:
                pass
            return True

        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int),
                                  ctypes.POINTER(ctypes.c_int))
        u.EnumWindows(PROC(_cb), 0)
        if halladas:
            x, y, w, h = max(halladas, key=lambda v: v[2] * v[3])
            return del_punto(x + w // 2, y + h // 2)
    except Exception:
        pass
    return None


# ── Cuál usa Litch ───────────────────────────────────────────────────────────

def elegido(app) -> dict:
    """
    El monitor donde Litch tiene que mirar AHORA.

    Orden de preferencia:
      1. El que el señor eligió a mano.
      2. Aquel donde esté el bróker que se está usando.
      3. El principal.
    """
    ms = listar()
    try:
        n = app.mem.get("config", {}).get("monitor")
        if n:
            for m in ms:
                if m["n"] == int(n):
                    return m
    except Exception:
        pass

    # ¿Dónde está el bróker?
    try:
        bv = str(app.mem.get("config", {}).get("broker_visual") or "")
        titulo = "interactivebrokers" if bv == "tws" else "iq option"
        m = del_ventana(titulo)
        if m:
            return m
    except Exception:
        pass

    for m in ms:
        if m["principal"]:
            return m
    return ms[0]


def fijar(app, n: int) -> str:
    """El señor elige monitor. Se recalcula la visión para ese monitor."""
    ms = listar()
    elegidos = [m for m in ms if m["n"] == int(n)]
    if not elegidos:
        return (f"No tengo un monitor {n}, señor. "
                f"Veo {len(ms)}: " +
                ", ".join(f"{m['n']} ({m['w']}×{m['h']})" for m in ms))
    m = elegidos[0]
    try:
        app.mem.setdefault("config", {})["monitor"] = int(n)
        # La visión pasa a cubrir ESE monitor, no el principal
        app.mem["config"]["region_grafico"] = [m["x"], m["y"],
                                               m["x"] + m["w"], m["y"] + m["h"]]
        app.mem["config"]["vision_total"] = True
        from . import memoria as _mem
        _mem.guardar(app.mem)
        try:
            ovl = getattr(app, "overlay", None)
            if ovl:
                ovl.set_region(app.mem["config"]["region_grafico"])
        except Exception:
            pass
    except Exception as e:
        return f"No pude fijarlo: {e}"
    return (f"Monitor {n} elegido, señor: {m['w']}×{m['h']} empezando en "
            f"({m['x']},{m['y']}). Mi visión pasa a cubrir esa pantalla "
            f"entera. Todo lo que calibre a partir de ahora será relativo "
            f"a ella.")


def mover_barra(app, n: int) -> str:
    """
    Lleva la barra de Litch a otro monitor, sin reiniciar.

    Es un ajuste distinto del de la visión, y a propósito: lo más cómodo
    es tener la barra en una pantalla y que Litch mire la otra, así la
    barra no tapa el gráfico que está analizando.
    """
    ms = listar()
    m = next((x for x in ms if x["n"] == int(n)), None)
    if m is None:
        return (f"No tengo un monitor {n}, señor. Veo {len(ms)}: " +
                ", ".join(f"{x['n']} ({x['w']}×{x['h']})" for x in ms))
    try:
        app.mem.setdefault("config", {})["monitor_barra"] = int(n)
        from . import memoria as _mem
        _mem.guardar(app.mem)
    except Exception as e:
        return f"No pude guardarlo: {e}"

    # Moverla ya, sin esperar al reinicio. Se usa el mismo anclaje que
    # luego vigila los cambios, para que no haya dos formas distintas de
    # colocar la barra — una discrepancia ahí sería difícil de perseguir.
    movida = anclar_barra(app, forzar=True)

    vis = ""
    try:
        act = elegido(app)
        if act["n"] != int(n):
            vis = (f" Sigo mirando el monitor {act['n']}, que es donde está "
                   f"el bróker — así la barra no le tapa el gráfico.")
        else:
            vis = (f" Aviso: la barra queda en el mismo monitor que estoy "
                   f"mirando, así que taparé parte de lo que analizo. "
                   f"Puede plegarla con «⌃ OCULTAR BARRA».")
    except Exception:
        pass

    return (f"Barra en el monitor {n}, señor "
            f"({m['w']}×{m['h']} en ({m['x']},{m['y']}))."
            + ("" if movida else " Se aplicará al reiniciar.") + vis)


# ── Anclaje que se adapta solo ───────────────────────────────────────────────
#
# Mover la barra una vez no basta. Los monitores cambian: se desconectan,
# se cambia la resolución, Windows los reordena al despertar del suspendido.
# Si la barra se quedó anclada a un monitor de 1920 y ahora ese monitor mide
# 1366, la barra sobresale y se pierde media fila de botones. Y si el monitor
# desaparece, la barra se queda en una pantalla que ya no existe.
#
# `firma_monitores()` resume la configuración actual en una cadena. Si esa
# cadena cambia, algo se movió y hay que re-anclar.

_ULTIMA_FIRMA = {"v": ""}


def firma_monitores() -> str:
    """Resumen de la configuración actual. Cambia si cambian los monitores."""
    try:
        return "|".join(f"{m['n']}:{m['x']},{m['y']},{m['w']},{m['h']}"
                        for m in listar())
    except Exception:
        return ""


def factor_escala(app) -> float:
    """
    Cuánto difieren las unidades de Tk de las de Windows.

    Devuelve 1.0 si coinciden. Si Windows dice que el escritorio mide
    4200 px y Tk cree que mide 3360, el factor es 0,8: hay que multiplicar
    por él todo lo que se le pase a Tk.

    Esto pasa cuando el escalado de pantalla no es del 100 % y el proceso
    se hizo consciente del DPI después de crear la ventana — que es
    exactamente lo que ocurre aquí.
    """
    try:
        root = app.interfaz.root
        tk_w = int(root.winfo_screenwidth())
        import ctypes
        win_w = int(ctypes.windll.user32.GetSystemMetrics(0))
        if tk_w > 0 and win_w > 0:
            f = tk_w / win_w
            # Solo se considera si la diferencia es real; ruido de 1-2 px no
            if 0.4 < f < 2.6 and abs(f - 1.0) > 0.02:
                return round(f, 4)
    except Exception:
        pass
    return 1.0


def monitor_de_barra(app) -> dict:
    """
    En qué monitor debe estar la barra AHORA.

    Si el que eligió el señor ya no existe —lo desconectó, o Windows lo
    renumeró— se cae al principal en vez de dejar la barra flotando en
    coordenadas de una pantalla que no está.
    """
    ms = listar()
    try:
        n = app.mem.get("config", {}).get("monitor_barra")
        if n:
            m = next((x for x in ms if x["n"] == int(n)), None)
            if m:
                return m
    except Exception:
        pass
    return next((m for m in ms if m["principal"]), ms[0])


def anclar_barra(app, forzar: bool = False) -> bool:
    """
    Pone la barra donde toca, con el ancho del monitor que le corresponde.

    Devuelve True si la movió. Está pensada para llamarse a menudo: si
    nada cambió, no toca nada y cuesta casi cero.
    """
    try:
        ui = getattr(app, "interfaz", None)
        v = getattr(ui, "_barra_win", None)
        if v is None or not v.winfo_exists():
            return False

        firma = firma_monitores()
        cambio = (firma != _ULTIMA_FIRMA["v"])
        if cambio:
            _ULTIMA_FIRMA["v"] = firma

        m = monitor_de_barra(app)
        v.update_idletasks()
        geo = v.winfo_geometry()                    # "1920x104+0+0"
        tam, x, y = geo.split("+")[0], geo.split("+")[1], geo.split("+")[2]
        ancho_act, alto = (int(p) for p in tam.split("x"))
        x, y = int(x), int(y)

        dock = app.mem.get("config", {}).get("barra_dock", "arriba")

        # Si Tk y Windows miden distinto (escalado de pantalla), se traduce
        # antes de pedir nada. Es más limpio que pedir mal y corregir.
        esc = factor_escala(app)
        x_ok = int(m["x"] * esc)
        y_base = int(m["y"] * esc)
        h_esc = int(m["h"] * esc)
        y_ok = (y_base + h_esc - alto - 48) if dock == "abajo" else y_base
        w_ok = int(m["w"] * esc)

        # ¿Ya está bien? Se tolera 1 px de holgura por el redondeo de Tk.
        if (not forzar and not cambio
                and abs(x - x_ok) <= 1 and abs(y - y_ok) <= 1
                and abs(ancho_act - w_ok) <= 1):
            return False

        v.geometry(f"{w_ok}x{alto}+{x_ok}+{y_ok}")

        # ── SE COMPRUEBA LO QUE DE VERDAD PASÓ ────────────────────────
        #
        # Windows y Tk no siempre hablan en las mismas unidades. Con
        # escalado de pantalla distinto del 100 % —y una resolución como
        # 1800×1125 huele a escalado— se pide 1800 de ancho y sale otra
        # cosa.
        #
        # Pedir y dar por hecho es el error de siempre en este proyecto.
        # Aquí se mide UNA vez qué proporción salió, y se corrige todo con
        # ese mismo factor. Corregir ancho y posición por separado hacía
        # que la segunda pasada deshiciera la primera.
        try:
            v.update_idletasks()
            g2 = v.winfo_geometry()
            w2 = int(g2.split("+")[0].split("x")[0])
            if w2 > 0 and abs(w2 - w_ok) > 2:
                fac = w_ok / w2          # cuánto hay que agrandar la petición
                v.geometry(f"{int(w_ok * fac)}x{alto}"
                           f"+{int(x_ok * fac)}+{int(y_ok * fac)}")
                v.update_idletasks()
                g3 = v.winfo_geometry()
                w3 = int(g3.split("+")[0].split("x")[0])
                if abs(w3 - w_ok) > abs(w2 - w_ok):
                    # La corrección empeoró: se vuelve a lo anterior. Más
                    # vale una barra algo estrecha que una descolocada.
                    v.geometry(f"{w_ok}x{alto}+{x_ok}+{y_ok}")
        except Exception:
            pass

        # ── QUE LA CINTA SE REORGANICE AL CAMBIAR DE ANCHO ────────────
        #
        # La barra se movía y se estiraba, pero sus botones seguían
        # colocados para el ancho anterior. En un monitor de 1800 con
        # una cinta calculada para 1920, los grupos quedaban partidos y
        # el conjunto se veía desordenado.
        #
        # `_ajustar_ribbon` recalcula la zona desplazable y el alto real
        # que necesita el contenido. Se llama con un pequeño retardo
        # porque Tk necesita un ciclo para aplicar la geometría nueva
        # antes de poder medir bien.
        try:
            ui = getattr(app, "interfaz", None)
            fn = getattr(ui, "_ajustar_ribbon", None)
            if callable(fn):
                v.after(120, fn)
                v.after(400, fn)      # segunda pasada: ya con todo asentado
        except Exception:
            pass

        if cambio:
            try:
                app.log(f"[Monitores] La configuración de pantallas cambió. "
                        f"Re-anclo la barra al monitor {m['n']} "
                        f"({m['w']}×{m['h']}).")
            except Exception:
                pass
        return True
    except Exception:
        return False


def vigilar(app, cada_ms: int = 3000) -> None:
    """
    Deja la barra vigilándose sola.

    Cada pocos segundos comprueba que sigue anclada donde debe y con el
    ancho que le corresponde. Si el señor cambia de monitor, desconecta
    uno o cambia la resolución, se adapta sin que nadie haga nada.
    """
    try:
        root = app.interfaz.root
    except Exception:
        return

    def _tic():
        try:
            anclar_barra(app)
        except Exception:
            pass
        try:
            root.after(cada_ms, _tic)
        except Exception:
            pass

    try:
        root.after(cada_ms, _tic)
    except Exception:
        pass


def siguiente(app) -> dict:
    """
    Pasa Litch al siguiente monitor. Un clic y ya.

    Mueve las dos cosas a la vez —la barra y la visión— porque tenerlas
    separadas era útil para afinar, pero para el día a día el señor solo
    quiere que Litch «se vaya a la otra pantalla». Si luego las quiere
    separadas, los comandos de antes siguen ahí.

    Devuelve el monitor al que fue.
    """
    ms = listar()
    if len(ms) <= 1:
        return {"n": 1, "solo_uno": True,
                "texto": "Solo tengo una pantalla, señor. No hay a dónde ir."}

    actual = monitor_de_barra(app)
    idx = next((i for i, m in enumerate(ms) if m["n"] == actual["n"]), 0)
    nuevo = ms[(idx + 1) % len(ms)]

    cfg = app.mem.setdefault("config", {})

    # ── LO QUE LITCH TOCA TAMBIÉN SE MUDA ─────────────────────────────
    #
    # Mover la barra y la visión era la mitad del trabajo. Litch no solo
    # mira: pulsa SUBE, pulsa BAJA, escribe en el ticket. Y todo eso vive
    # en coordenadas absolutas calibradas en el monitor de origen.
    #
    # Sin esto, al cambiar de pantalla Litch creería pulsar SUBE y
    # pulsaría lo que hubiera en esa zona de la otra. El mismo fallo que
    # costó 86 operaciones fantasma: el clic sale, pero no llega.
    aviso_calib = ""
    try:
        from . import calibracion_por_monitor as _cpm
        aviso_calib = _cpm.al_cambiar(app, actual["n"], nuevo)
    except Exception:
        pass

    cfg["monitor_barra"] = nuevo["n"]      # dónde vive la barra
    cfg["monitor"] = nuevo["n"]            # dónde mira Litch
    cfg["vision_total"] = True

    # ── LA VISIÓN SIGUE AL MONITOR, SIEMPRE ───────────────────────────
    #
    # Antes esto dependía de si el aviso de calibración contenía cierta
    # frase. Frágil y equivocado: el señor cambiaba de pantalla y Litch
    # seguía mirando la anterior, así que no se enteraba de nada de lo
    # que pasaba delante.
    #
    # Son dos cosas distintas y hay que tenerlas separadas:
    #   · DÓNDE MIRA  → siempre el monitor actual, entero
    #   · DÓNDE PULSA → las coordenadas calibradas de ese monitor
    #
    # Mezclarlas hacía que una calibración vieja secuestrara la visión.
    cfg["region_grafico"] = [nuevo["x"], nuevo["y"],
                             nuevo["x"] + nuevo["w"],
                             nuevo["y"] + nuevo["h"]]
    try:
        from . import memoria as _mem
        _mem.guardar(app.mem)
    except Exception:
        pass

    anclar_barra(app, forzar=True)

    # El cuadro verde tiene que mudarse también, o seguirá dibujado sobre
    # el monitor viejo diciendo que Litch mira ahí. Un indicador que se
    # queda atrás miente igual que uno que nunca fue verdad.
    try:
        ovl = getattr(app, "overlay", None)
        if ovl:
            ovl.set_region(cfg["region_grafico"])
    except Exception:
        pass

    # Y la conciencia de pantalla, que es la que dice «veo su pantalla
    # completa, 1920×1080»: si no se entera del cambio, sigue anunciando
    # las medidas del monitor anterior.
    try:
        from . import conciencia_pantalla as _cp
        if hasattr(_cp, "_CACHE"):
            _cp._CACHE.clear()
    except Exception:
        pass
    try:
        from . import vision_total as _vt2
        _vt2._sincronizar_overlay(app, cfg["region_grafico"])
    except Exception:
        pass

    nuevo = dict(nuevo)
    nuevo["solo_uno"] = False
    nuevo["calibracion"] = aviso_calib
    nuevo["texto"] = (f"Monitor {nuevo['n']} — {nuevo['w']}×{nuevo['h']}. "
                      f"Me llevo la barra, la visión y las coordenadas."
                      + (f"\n\n{aviso_calib}" if aviso_calib else ""))
    try:
        app.log("[Monitores] " + nuevo["texto"])
    except Exception:
        pass
    return nuevo


def etiqueta(app) -> str:
    """Texto corto para el botón: «🖥 1/2»."""
    try:
        ms = listar()
        m = monitor_de_barra(app)
        return f"🖥 {m['n']}/{len(ms)}"
    except Exception:
        return "🖥"


def automatico(app) -> str:
    """Que Litch decida sola, siguiendo al bróker."""
    try:
        app.mem.setdefault("config", {}).pop("monitor", None)
        from . import memoria as _mem
        _mem.guardar(app.mem)
    except Exception:
        pass
    m = elegido(app)
    return (f"De acuerdo, señor: elijo yo. Ahora mismo miraría el monitor "
            f"{m['n']} ({m['w']}×{m['h']} en ({m['x']},{m['y']})), porque "
            f"es donde veo el bróker. Si mueve la ventana a otra pantalla, "
            f"la sigo.")


def descripcion(app) -> str:
    """Qué monitores hay y en cuál está mirando."""
    ms = listar()
    act = elegido(app)
    manual = None
    try:
        manual = app.mem.get("config", {}).get("monitor")
    except Exception:
        pass

    l = [f"MONITORES — veo {len(ms)}", ""]
    for m in ms:
        marca = "►" if m["n"] == act["n"] else " "
        pos = ("principal" if m["principal"]
               else "a la derecha" if m["x"] > 0
               else "a la izquierda" if m["x"] < 0
               else "arriba" if m["y"] < 0 else "abajo")
        l.append(f" {marca} Monitor {m['n']}: {m['w']}×{m['h']} "
                 f"en ({m['x']},{m['y']}) — {pos}")
    vx, vy, vw, vh = escritorio_virtual()
    l.append("")
    l.append(f"Escritorio completo: {vw}×{vh} desde ({vx},{vy})")
    l.append("")
    if manual:
        l.append(f"Estoy mirando el monitor {act['n']} porque usted lo eligió.")
    else:
        l.append(f"Estoy mirando el monitor {act['n']} porque es donde veo "
                 f"el bróker. Si lo mueve, le sigo.")
    l.append("")
    l.append("Dígame «mira el monitor 2» para fijarlo, o «elige tú el "
             "monitor» para que lo decida yo.")
    return "\n".join(l)


__all__ = ["listar", "escritorio_virtual", "del_punto", "del_ventana",
           "elegido", "fijar", "automatico", "descripcion"]

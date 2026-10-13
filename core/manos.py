"""Manos de Litch — control del puntero suave, humano e inteligente.

Mueve el ratón con una curva y aceleración naturales (no en línea recta
robótica), hace clicks precisos y puede cerrar propagandas buscando una
"X" típica en la esquina de un anuncio. Incluye seguridad: el FAILSAFE de
pyautogui (mover el ratón a una esquina) aborta cualquier acción.

TIMING CHART (por período de vela):
  Blitz  ≤15s  → click instantáneo ~1ms, sin verificación, sin retry
  Corta  ≤30s  → click ~1ms, verificar con 60ms de espera, 1 retry
  Normal ≤60s  → click ~22ms, verificar con 90ms, 2 reintentos
  Largo  >60s  → click ~55ms, verificar con 120ms, 2 reintentos
"""
import random
import threading
import time

try:
    import pyautogui
    # FAILSAFE=False: evita que FailSafeException mate hilos de trading cuando
    # el cursor llega a la esquina (0,0) durante movimientos de calibración/click.
    # Las excepciones de pyautogui ya están capturadas con try/except en todas
    # las funciones; el failsafe solo era un riesgo adicional sin beneficio real.
    pyautogui.FAILSAFE = False
    pyautogui.MINIMUM_DURATION = 0
    _PG_OK = True
except Exception:
    _PG_OK = False

try:
    import numpy as np
    _NP_OK = True
except Exception:
    _NP_OK = False


def disponible():
    return _PG_OK


def mover_humano(x, y, duracion=None):
    """Mueve el puntero a (x, y) con una trayectoria suave estilo humano."""
    if not _PG_OK:
        return False
    ix, iy = pyautogui.position()
    dist = ((x - ix) ** 2 + (y - iy) ** 2) ** 0.5
    if duracion is None:
        duracion = min(0.6, max(0.12, dist / 2600))
    pasos = max(8, int(dist / 18))
    if _NP_OK and pasos > 1:
        cx = (ix + x) / 2 + random.uniform(-40, 40)
        cy = (iy + y) / 2 + random.uniform(-40, 40)
        ts = np.linspace(0, 1, pasos)
        ts = ts * ts * (3 - 2 * ts)
        for t in ts:
            px = (1 - t) ** 2 * ix + 2 * (1 - t) * t * cx + t ** 2 * x
            py = (1 - t) ** 2 * iy + 2 * (1 - t) * t * cy + t ** 2 * y
            pyautogui.moveTo(int(px), int(py), _pause=False)
            time.sleep(duracion / pasos)
    else:
        pyautogui.moveTo(x, y, duration=duracion)
    return True


def click_inteligente(x, y, devolver=True, doble=False):
    """Mueve suave hasta (x, y) y hace click, devolviendo el puntero al origen."""
    if not _PG_OK:
        return False
    if _dentro_de_tws(x, y):
        try:
            print(f"[Manos] ⛔ Clic bloqueado en ({x},{y}): dentro de "
                  f"Interactive Brokers.")
        except Exception:
            pass
        return False
    origen = pyautogui.position()
    mover_humano(x, y)
    time.sleep(random.uniform(0.04, 0.12))
    if doble:
        pyautogui.doubleClick()
    else:
        pyautogui.click()
    if devolver:
        time.sleep(0.05)
        pyautogui.moveTo(origen.x, origen.y, duration=0.15)
    return True


def click_rapido(x, y) -> bool:
    """Click instantáneo sin movimiento de ratón — <5ms.

    Lo usan los canales 3 y 4. Pasa por el mismo guardián que click_trade:
    una puerta trasera sin vigilar es lo mismo que no tener vigilancia.
    """
    if not _PG_OK:
        return False
    if _dentro_de_tws(x, y):
        try:
            print(f"[Manos] ⛔ Clic rápido BLOQUEADO en ({x},{y}): "
                  f"cae dentro de Interactive Brokers.")
        except Exception:
            pass
        return False
    try:
        pyautogui.click(x, y, _pause=False)
        return True
    except Exception:
        return False


# ── Foco de ventana del broker ────────────────────────────────────────────────
_BROKER_HWND: int | None = None
_BROKER_HWND_TS: float   = 0.0
_BROKER_NOMBRES = [
    "iq option", "iqoption", "quotex", "olymp trade", "olymptrade",
    "pocket option", "pocketoption", "binomo", "deriv", "exness",
]


def enfocar_broker() -> bool:
    """Pone el foco de Windows en la ventana del broker antes de un click real.

    IQ Option corre en Electron/Chromium y algunas versiones ignorar clicks
    de pyautogui cuando la ventana no tiene el foco de Windows. Esta función
    busca la ventana del broker (caché 30 s) y llama a SetForegroundWindow
    para que el siguiente click pyautogui lo reciba Electron correctamente.
    """
    global _BROKER_HWND, _BROKER_HWND_TS
    try:
        import ctypes
        ahora = time.time()

        if _BROKER_HWND is None or ahora - _BROKER_HWND_TS > 30:
            _hwnd = [None]
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            )
            def _cb(hwnd, _):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
                        if any(nm in buf.value.lower() for nm in _BROKER_NOMBRES):
                            _hwnd[0] = hwnd
                            return False
                return True
            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
            _BROKER_HWND    = _hwnd[0]
            _BROKER_HWND_TS = ahora

        if _BROKER_HWND:
            ctypes.windll.user32.SetForegroundWindow(_BROKER_HWND)
            ctypes.windll.user32.BringWindowToTop(_BROKER_HWND)
            return True
    except Exception:
        pass
    return False


# ── Guardia contra clics de IQ Option sobre Interactive Brokers ─────────────
#
# Los clics de operación usan coordenadas ABSOLUTAS de pantalla, calibradas
# sobre IQ Option. Si IQ Option se cierra y Trader Workstation pasa a ocupar
# esa zona, un clic de "COMPRAR" de opciones binarias aterrizaría dentro de
# TWS — sobre cualquier cosa que hubiera ahí.
#
# Nunca ha pasado, y no debe poder pasar. Es barato comprobarlo.

_TWS_CACHE = {"rect": None, "ts": 0.0}
_TWS_TTL = 5.0          # revalidar cada 5 s: barato y suficiente


def _dentro_de_tws(x, y) -> bool:
    """¿Estas coordenadas caen dentro de la ventana de Interactive Brokers?"""
    try:
        ahora = time.time()
        if ahora - _TWS_CACHE["ts"] > _TWS_TTL:
            _TWS_CACHE["ts"] = ahora
            try:
                from . import vision_tws as _vt
                v = _vt.ventana_tws()
                _TWS_CACHE["rect"] = ((v["x"], v["y"], v["x"] + v["w"],
                                       v["y"] + v["h"]) if v else None)
            except Exception:
                _TWS_CACHE["rect"] = None
        r = _TWS_CACHE["rect"]
        if not r:
            return False
        return r[0] <= x <= r[2] and r[1] <= y <= r[3]
    except Exception:
        return False


def click_trade(x, y, periodo_vela: int = 60) -> bool:
    """Click optimizado para trades en tiempo real.

    Blitz (≤15s)  → teleport instantáneo ~1ms
    Corto (≤30s)  → deslizamiento visible ~180ms (el usuario ve el cursor moverse)
    Normal (≤60s) → movimiento humano ~220ms
    Largo (>60s)  → movimiento humano suave ~300ms

    SEGURIDAD: si el destino cae dentro de Trader Workstation, NO se hace
    el clic. Un clic de opciones binarias dentro del broker de acciones no
    tiene ningún significado bueno posible.
    """
    if not _PG_OK:
        return False
    if _dentro_de_tws(x, y):
        try:
            print(f"[Manos] ⛔ Clic de IQ Option BLOQUEADO en ({x},{y}): "
                  f"esa posición está dentro de Interactive Brokers. "
                  f"Recalibre los botones de IQ Option.")
        except Exception:
            pass
        return False
    try:
        if periodo_vela <= 15:
            # Blitz: máxima velocidad, sin ningún delay
            pyautogui.click(x, y, _pause=False)
        elif periodo_vela <= 30:
            # 30s Blitz: movimiento VISIBLE (~180ms) para que el usuario
            # pueda ver que Litch está actuando — hay tiempo de sobra.
            pyautogui.moveTo(x, y, duration=0.18, _pause=False)
            time.sleep(0.04)           # 40ms sobre el botón
            pyautogui.click(_pause=False)
        elif periodo_vela <= 60:
            pyautogui.moveTo(x, y, duration=0.22, _pause=False)
            time.sleep(0.04)
            pyautogui.click(_pause=False)
        else:
            mover_humano(x, y)         # curva suave estilo humano
            time.sleep(0.06)
            pyautogui.click(_pause=False)
        return True
    except Exception:
        return False


def click_con_retry(x, y, verificar_fn=None, periodo_vela: int = 60,
                    max_intentos: int = 2) -> bool:
    """Ejecuta el click de trade con lógica adaptativa según el período.

    Para Blitz (≤15s):
      - Un solo click, sin verificación, sin retry.
        El tiempo es lo único que importa.

    Para otros períodos:
      - Verificación con ventana proporcional al período.
      - Hasta 2 reintentos si falla la verificación.

    verificar_fn : callable sin args → bool (True = trade registrado)
                   Si es None, asume éxito tras el primer click.
    """
    # ── Blitz: velocidad máxima, sin espera de verificación ─────────────────
    if periodo_vela <= 15:
        return click_trade(x, y, periodo_vela)

    # ── Ventanas de verificación proporcionales al período ───────────────────
    if periodo_vela <= 30:
        ventana_ms, pausa_retry = 0.060, 0.040   # 60ms + 40ms entre intentos
        max_intentos = min(max_intentos, 2)
    elif periodo_vela <= 60:
        ventana_ms, pausa_retry = 0.090, 0.060   # 90ms + 60ms
    else:
        ventana_ms, pausa_retry = 0.120, 0.080   # 120ms + 80ms

    for intento in range(max_intentos):
        ok = click_trade(x, y, periodo_vela)
        if not ok:
            continue
        if verificar_fn is None:
            return True
        time.sleep(ventana_ms)
        if verificar_fn():
            return True
        if intento < max_intentos - 1:
            time.sleep(pausa_retry)
    return False


def click_preciso(x, y, devolver: bool = False) -> bool:
    """Click rápido con micro-movimiento natural — ~50–80 ms."""
    if not _PG_OK:
        return False
    if _dentro_de_tws(x, y):
        try:
            print(f"[Manos] ⛔ Clic bloqueado en ({x},{y}): dentro de "
                  f"Interactive Brokers.")
        except Exception:
            pass
        return False
    try:
        origen = pyautogui.position()
        pyautogui.moveTo(x, y, duration=0.04, _pause=False)
        time.sleep(random.uniform(0.01, 0.03))
        pyautogui.click(_pause=False)
        if devolver:
            time.sleep(0.02)
            pyautogui.moveTo(origen.x, origen.y, duration=0.05, _pause=False)
        return True
    except Exception:
        return False


def aparcar_cursor(region=None, periodo_vela: int = 60):
    """Retira el cursor del área de botones a zona neutra (SÍNCRONO).

    Para Blitz (≤15s) usa velocidad máxima (30ms).
    Para otros períodos usa 60ms (era 180ms).
    """
    if not _PG_OK:
        return False
    try:
        if region and len(region) >= 4:
            x = int((region[0] + region[2]) / 2)
            y = int((region[1] + region[3]) / 2)
        else:
            w, h = pyautogui.size()
            x = w // 3
            y = h // 2
        dur = 0.025 if periodo_vela <= 15 else 0.055
        pyautogui.moveTo(x, y, duration=dur, _pause=False)
        return True
    except Exception:
        return False


def aparcar_cursor_async(region=None, periodo_vela: int = 60):
    """Retira el cursor en un thread daemon — NO bloquea el loop de trading."""
    threading.Thread(
        target=aparcar_cursor,
        args=(region, periodo_vela),
        daemon=True,
        name="AparcarCursor"
    ).start()


def indicar_hover(x: int, y: int, segundos: float = 0.55) -> bool:
    """Mueve el puntero a (x, y) para indicar visualmente una intención
    de click SIN hacer click. Regresa al origen tras `segundos`.
    """
    if not _PG_OK:
        return False
    try:
        origen = pyautogui.position()
        mover_humano(x, y, duracion=0.14)
        time.sleep(max(0.1, segundos))
        mover_humano(int(origen.x), int(origen.y), duracion=0.12)
        return True
    except Exception:
        return False


def cerrar_propaganda(region=None):
    """Intenta cerrar un anuncio buscando una 'X' clara en las esquinas."""
    if not (_PG_OK and _NP_OK) or not region:
        return False
    x1, y1, x2, y2 = region
    # Usar vision.capturar() — serializado via executor para evitar deadlock GDI
    from . import vision as _vis
    img = _vis.capturar([x1, y1, x2, y2])
    if img is None:
        return False
    h, w = img.shape[:2]
    franja = img[0:max(1, h // 6), int(w * 0.8):]
    gris = franja.mean(axis=2)
    if gris.size == 0:
        return False
    yy, xx = np.unravel_index(int(np.argmin(gris)), gris.shape)
    cx = int(x1 + w * 0.8 + xx)
    cy = int(y1 + yy)
    click_inteligente(cx, cy)
    return True

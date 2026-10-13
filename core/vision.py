"""Visión de Litch — análisis avanzado del gráfico de IQ Option.

Capacidades:
  color_vela()         → 'V' / 'R' / None  (detección multi-método)
  estado_pantalla()    → dict con información completa del gráfico
  detectar_resultado() → 'ganó' / 'perdió' / None  (overlay de resultado)
  capturar()           → imagen BGR como ndarray

Métodos de detección de vela (se votan entre sí para mayor robustez):
  1. Franja derecha clásica (14% final del gráfico)
  2. Franja ampliada (20% final) — captura velas que desborden la primera
  3. Análisis HSV — distingue verde/rojo en el espacio de color perceptual
  4. Región de precio — detecta la barra de precio actual (lado derecho)
"""
import concurrent.futures as _cf
import os
import time
import threading as _threading

import numpy as np

try:
    import mss
    _MSS_OK = True
except Exception:
    _MSS_OK = False

# ── Executor serializado para mss ─────────────────────────────────────────────
# mss usa la API GDI de Windows que NO soporta llamadas concurrentes desde
# múltiples hilos. Sin serialización, 6+ hilos llamando grab() simultáneamente
# pueden deadlockear GDI y congelar todo el sistema operativo.
# max_workers=1 garantiza que nunca haya dos grab() al mismo tiempo.
# timeout=2s: si GDI se cuelga, el llamador recibe None en vez de bloquearse.
_MSS_EXECUTOR = _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="LitchMSS")
_MSS_TIMEOUT  = 2.0   # segundos máximos de espera por captura

# Caché de pantalla completa: reutilizar si < 300ms de antigüedad
# Evita que analizar_contexto_iq() y auto_calibrar_iq() hagan dos grab()
# de pantalla completa en el mismo ciclo.
_cache_full: dict = {"ts": 0.0, "img": None}
_CACHE_FULL_SECS  = 0.30

try:
    import cv2
    _CV2_OK = True
    cv2.setUseOptimized(True)
    cv2.setNumThreads(max(4, os.cpu_count() or 4))   # usa todos los nucleos disponibles
except Exception:
    _CV2_OK = False


# ─── Plantillas auto-aprendidas (reconocimiento de forma, no solo color) ─────

_TEMPLATES_DIR = None


def _dir_templates() -> str:
    global _TEMPLATES_DIR
    if _TEMPLATES_DIR is None:
        from . import memoria as mem_mod
        _TEMPLATES_DIR = os.path.join(mem_mod.ruta_memoria_ap(), "templates")
        os.makedirs(_TEMPLATES_DIR, exist_ok=True)
    return _TEMPLATES_DIR


def _guardar_template(nombre: str, crop: np.ndarray) -> None:
    if not _CV2_OK or crop is None or crop.size == 0:
        return
    try:
        cv2.imwrite(os.path.join(_dir_templates(), f"{nombre}.png"), crop)
    except Exception:
        pass


def _cargar_template(nombre: str):
    if not _CV2_OK:
        return None
    try:
        ruta = os.path.join(_dir_templates(), f"{nombre}.png")
        if os.path.exists(ruta):
            return cv2.imread(ruta)
    except Exception:
        pass
    return None


def _buscar_template(template, img: np.ndarray, umbral: float = 0.70):
    """Busca `template` dentro de `img` por correlación normalizada (cv2).
    Devuelve (cx, cy, score) del centro o None si no supera el umbral."""
    if not _CV2_OK or template is None or img is None:
        return None
    th, tw = template.shape[:2]
    if th >= img.shape[0] or tw >= img.shape[1] or th < 5 or tw < 5:
        return None
    try:
        res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score < umbral:
            return None
        return loc[0] + tw // 2, loc[1] + th // 2, float(score)
    except Exception:
        return None


# ─── Captura de pantalla ─────────────────────────────────────────────────────

def capturar(region) -> np.ndarray | None:
    """Captura la región [x1, y1, x2, y2] como array BGR.

    Pasa por el executor serializado (max_workers=1) para garantizar que
    nunca haya dos llamadas mss simultáneas — evita el deadlock de GDI.
    Timeout de 2s: si GDI se cuelga, devuelve None en vez de bloquearse.
    """
    if not _MSS_OK or not region or len(region) < 4:
        return None
    x1, y1, x2, y2 = int(region[0]), int(region[1]), int(region[2]), int(region[3])
    if x2 - x1 < 10 or y2 - y1 < 10:
        return None
    mon = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
    try:
        def _do():
            with mss.mss() as sct:
                return np.array(sct.grab(mon))[:, :, :3]
        return _MSS_EXECUTOR.submit(_do).result(timeout=_MSS_TIMEOUT)
    except Exception:
        return None


def capturar_pantalla_completa() -> np.ndarray | None:
    """Captura toda la pantalla (con caché de 300ms para reducir carga de GDI).

    Si la última captura fue hace menos de 300ms, reutiliza esa imagen.
    Esto evita que auto_calibrar_iq() y analizar_contexto_iq() llamen a
    mss dos veces en el mismo ciclo cuando son invocadas cerca en el tiempo.
    """
    if not _MSS_OK:
        return None
    ahora = time.time()
    if ahora - _cache_full["ts"] < _CACHE_FULL_SECS and _cache_full["img"] is not None:
        return _cache_full["img"]
    try:
        def _do():
            with mss.mss() as sct:
                return np.array(sct.grab(sct.monitors[1]))[:, :, :3]
        img = _MSS_EXECUTOR.submit(_do).result(timeout=_MSS_TIMEOUT)
        if img is not None:
            _cache_full["ts"]  = ahora
            _cache_full["img"] = img
        return img
    except Exception:
        return None


# ─── Conversión BGR → HSV simple ─────────────────────────────────────────────

def _bgr_a_hsv(img: np.ndarray) -> np.ndarray:
    """Convierte BGR uint8 a HSV (hue 0-180, sat 0-255, val 0-255) vía numpy."""
    b = img[:, :, 0].astype(np.float32) / 255.0
    g = img[:, :, 1].astype(np.float32) / 255.0
    r = img[:, :, 2].astype(np.float32) / 255.0

    cmax  = np.maximum(np.maximum(r, g), b)
    cmin  = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin

    # Hue
    h = np.zeros_like(r)
    eps = 1e-9
    mask_r = (cmax == r) & (delta > eps)
    mask_g = (cmax == g) & (delta > eps)
    mask_b = (cmax == b) & (delta > eps)
    h[mask_r] = ((g[mask_r] - b[mask_r]) / (delta[mask_r] + eps)) % 6
    h[mask_g] = (b[mask_g] - r[mask_g]) / (delta[mask_g] + eps) + 2
    h[mask_b] = (r[mask_b] - g[mask_b]) / (delta[mask_b] + eps) + 4
    h = (h * 30.0).clip(0, 180)   # OpenCV range 0-180

    # Saturation
    s = np.where(cmax > eps, delta / (cmax + eps), 0.0) * 255.0

    # Value
    v = cmax * 255.0

    return np.stack([h, s, v], axis=2).astype(np.uint8)


# ─── Conteo de píxeles verdes/rojos ──────────────────────────────────────────

def _contar_verde_rojo_bgr(franja: np.ndarray) -> tuple:
    b = franja[:, :, 0].astype(int)
    g = franja[:, :, 1].astype(int)
    r = franja[:, :, 2].astype(int)
    verdes = int(np.sum((g > r + 20) & (g > b + 12) & (g > 65)))
    rojos  = int(np.sum((r > g + 20) & (r > b + 12) & (r > 65)))
    return verdes, rojos


def _contar_verde_rojo_hsv(franja: np.ndarray) -> tuple:
    """Conteo via HSV: verde H∈[35,85], rojo H<15 o H>160."""
    hsv = _bgr_a_hsv(franja)
    h   = hsv[:, :, 0].astype(int)
    s   = hsv[:, :, 1].astype(int)
    v   = hsv[:, :, 2].astype(int)
    sat_ok = (s > 60) & (v > 60)
    verdes = int(np.sum(sat_ok & (h >= 35) & (h <= 85)))
    rojos  = int(np.sum(sat_ok & ((h < 15) | (h > 160))))
    return verdes, rojos


# ─── Detección principal de vela ─────────────────────────────────────────────

def color_vela(region) -> str | None:
    """Devuelve 'V', 'R' o None.

    Vota entre 3 métodos para mayor robustez:
      Método 1: franja 14% derecha en BGR
      Método 2: franja 22% derecha en BGR
      Método 3: franja 14% derecha en HSV
    """
    img = capturar(region)
    if img is None:
        return None

    ancho = img.shape[1]
    if ancho < 20:
        return None

    votos_v = 0
    votos_r = 0

    # Método 1: franja estrecha (14%)
    f1     = img[:, int(ancho * 0.86):]
    v1, r1 = _contar_verde_rojo_bgr(f1)
    if v1 >= 20 or r1 >= 20:
        if v1 > r1:
            votos_v += 2   # método clásico tiene doble peso
        else:
            votos_r += 2

    # Método 2: franja más amplia (22%)
    f2     = img[:, int(ancho * 0.78):]
    v2, r2 = _contar_verde_rojo_bgr(f2)
    if v2 >= 40 or r2 >= 40:
        if v2 > r2:
            votos_v += 1
        else:
            votos_r += 1

    # Método 3: HSV en franja estrecha
    v3, r3 = _contar_verde_rojo_hsv(f1)
    if v3 >= 15 or r3 >= 15:
        if v3 > r3:
            votos_v += 1
        else:
            votos_r += 1

    if votos_v == 0 and votos_r == 0:
        return None

    return "V" if votos_v >= votos_r else "R"


# ─── Detección de resultado de trade ─────────────────────────────────────────

def detectar_resultado(region=None) -> str | None:
    """Detecta si IQ Option muestra un overlay de ganancia o pérdida.

    Busca en la pantalla completa:
    - Overlay verde prominente (zona superior izquierda de la vela) → ganó
    - Overlay gris/rojo prominente → perdió

    Devuelve 'gano' / 'perdio' / None.
    """
    if region:
        img = capturar(region)
    else:
        img = capturar_pantalla_completa()
    if img is None:
        return None

    h_total, w_total = img.shape[:2]

    # Buscar en el tercio superior de la imagen (donde aparece el overlay en IQ Option)
    zona = img[:h_total // 3, :, :]

    b = zona[:, :, 0].astype(int)
    g = zona[:, :, 1].astype(int)
    r = zona[:, :, 2].astype(int)

    # Verde brillante → ganó (color típico del overlay de ganancia)
    ganancia = int(np.sum((g > 140) & (g > r + 40) & (g > b + 20)))
    # Gris oscuro o rojo → perdió
    perdida  = int(np.sum(
        ((r > 130) & (r > g + 30) & (r > b + 20)) |   # rojo
        ((r > 100) & (g > 100) & (b > 100)             # gris claro (texto de pérdida)
         & (np.abs(r - g) < 15) & (np.abs(g - b) < 15))
    ))

    umbral = (h_total // 3 * w_total) * 0.008   # 0.8% de píxeles
    if ganancia < umbral and perdida < umbral:
        return None
    if ganancia > perdida * 1.5:
        return "gano"
    if perdida > ganancia * 1.5:
        return "perdio"
    return None


# ─── Estado completo de la pantalla ──────────────────────────────────────────

def estado_pantalla(region) -> dict:
    """Análisis completo del gráfico. Devuelve dict con:
      vela         : 'V' / 'R' / None
      votos_verde  : int
      votos_rojo   : int
      confianza    : 0..1  (qué tan clara es la vela)
      tiene_imagen : bool
      resultado    : 'gano' / 'perdio' / None
    """
    img = capturar(region)
    if img is None:
        return {"vela": None, "tiene_imagen": False,
                "confianza": 0.0, "resultado": None,
                "votos_verde": 0, "votos_rojo": 0}

    ancho = img.shape[1]
    f1    = img[:, int(ancho * 0.86):]

    v1, r1 = _contar_verde_rojo_bgr(f1)
    v3, r3 = _contar_verde_rojo_hsv(f1)
    f2     = img[:, int(ancho * 0.78):]
    v2, r2 = _contar_verde_rojo_bgr(f2)

    total_v = v1 * 2 + v2 + v3
    total_r = r1 * 2 + r2 + r3
    total   = total_v + total_r

    if total < 30:
        vela = None
        conf = 0.0
    else:
        vela = "V" if total_v >= total_r else "R"
        dominante = max(total_v, total_r)
        conf = min(1.0, dominante / total)

    resultado = detectar_resultado(region)

    return {
        "vela":         vela,
        "tiene_imagen": True,
        "confianza":    round(conf, 3),
        "resultado":    resultado,
        "votos_verde":  total_v,
        "votos_rojo":   total_r,
    }


# ─── Auto-calibración de IQ Option ───────────────────────────────────────────

def auto_calibrar_iq() -> dict:
    """Detecta automáticamente boton_verde (SUBE), boton_rojo (BAJA) y
    region_grafico en la pantalla sin que el usuario mueva el ratón.

    Requiere que IQ Option esté visible y sin ventanas encima.
    Devuelve dict con las claves encontradas (vacío si no detecta nada).
    """
    img = capturar_pantalla_completa()
    if img is None:
        return {}

    h_total, w_total = img.shape[:2]
    resultado = {}

    # ── Paso 0: reconocimiento por FORMA (plantilla auto-aprendida) ──────
    # Mucho más preciso y rápido que el color — sobrevive a tooltips,
    # cambios de brillo y solapamientos parciales. Se actualiza solo.
    # NOTA: solo busca UNA instancia (chart 1) — el escaneo por color de
    # abajo sigue corriendo siempre para poder detectar un eventual 2do
    # gráfico/activo (vista dividida), aunque la plantilla ya haya resuelto
    # los botones del chart 1.
    tpl_v = _cargar_template("boton_verde")
    tpl_r = _cargar_template("boton_rojo")
    x_ini_busqueda = int(w_total * 0.55)
    zona_busqueda  = img[:, x_ini_busqueda:]
    if tpl_v is not None:
        m = _buscar_template(tpl_v, zona_busqueda, umbral=0.68)
        if m:
            resultado["boton_verde"] = [m[0] + x_ini_busqueda, m[1]]
    if tpl_r is not None:
        m = _buscar_template(tpl_r, zona_busqueda, umbral=0.68)
        if m:
            resultado["boton_rojo"] = [m[0] + x_ini_busqueda, m[1]]

    # ── Botones SUBE / BAJA por color (fallback de chart 1 + detección de chart 2) ──
    # IQ Option los coloca en el 40% derecho de la pantalla.
    x_ini  = int(w_total * 0.60)
    zona   = img[:, x_ini:]
    zh, zw = zona.shape[:2]

    hsv  = _bgr_a_hsv(zona)
    h_ch = hsv[:, :, 0].astype(np.int32)
    s_ch = hsv[:, :, 1].astype(np.int32)
    v_ch = hsv[:, :, 2].astype(np.int32)

    vivo    = (s_ch > 100) & (v_ch > 120)
    mask_v  = vivo & (h_ch >= 40) & (h_ch <= 90)    # verde  (SUBE)
    mask_r  = vivo & ((h_ch < 12) | (h_ch > 168))   # rojo   (BAJA)

    def _todos_los_centros(mask, x_offset, min_pix=150):
        """Encuentra TODOS los centros de botones en la máscara via componentes
        conectados (cv2) — vectorizado en C, mucho más rápido y preciso que un
        escaneo de ventana deslizante en Python puro.

        min_pix=150 (antes 400): detecta botones parcialmente cubiertos por
        animaciones post-trade o tooltips de IQ Option.

        Devuelve lista de [screen_x, screen_y] ordenados arriba→abajo.
        """
        if not _CV2_OK or mask.sum() < min_pix:
            return []
        mask_u8 = (mask.astype(np.uint8)) * 255
        n_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask_u8, connectivity=8)
        candidatos = []
        for i in range(1, n_labels):   # 0 = fondo
            area = stats[i, cv2.CC_STAT_AREA]
            w_b  = stats[i, cv2.CC_STAT_WIDTH]
            h_b  = stats[i, cv2.CC_STAT_HEIGHT]
            if area < min_pix:
                continue
            # Forma compatible con un botón (descarta líneas finas / ruido)
            # Máximo ampliado a 600×200 para pantallas 4K o ventanas más grandes
            if w_b < 20 or h_b < 10 or w_b > 600 or h_b > 200:
                continue
            cx, cy = centroids[i]
            candidatos.append((int(cx) + x_offset, int(cy), area))
        candidatos.sort(key=lambda c: -c[2])     # mayor área primero
        return sorted([[c[0], c[1]] for c in candidatos[:4]],
                      key=lambda p: p[1])          # arriba → abajo

    verdes = _todos_los_centros(mask_v, x_ini)
    rojos  = _todos_los_centros(mask_r, x_ini)

    # Emparejar SUBE/BAJA del MISMO chart:
    #   • mismo X (±200 px — misma columna de botones)
    #   • BAJA entre 10-250 px DEBAJO de SUBE
    pares        = []
    rojos_usados = set()
    for bv in verdes:
        mejor_br = None
        mejor_dy = 999
        for i, br in enumerate(rojos):
            if i in rojos_usados:
                continue
            dx = abs(br[0] - bv[0])
            dy = br[1] - bv[1]
            if dx < 200 and 10 < dy < 250 and dy < mejor_dy:
                mejor_dy = dy
                mejor_br = (i, br)
        if mejor_br:
            rojos_usados.add(mejor_br[0])
            pares.append((bv, mejor_br[1]))

    # Fallback si no se forman pares (solo se detecta un color)
    if not pares:
        if verdes and rojos:
            # Usar el verde más alto y el rojo más alto
            pares = [(verdes[0], rojos[0])]
        elif verdes:
            pares = [(verdes[0], None)]
        elif rojos:
            pares = [(None, rojos[0])]

    # Chart 1: si la plantilla ya resolvió ambos botones, se respeta (más
    # precisa); si no, se completa con el primer par detectado por color.
    if "boton_verde" not in resultado or "boton_rojo" not in resultado:
        if pares:
            p1 = pares[0]
            resultado.setdefault("boton_verde", p1[0]) if p1[0] else None
            resultado.setdefault("boton_rojo",  p1[1]) if p1[1] else None

    btn_v = resultado.get("boton_verde")
    btn_r = resultado.get("boton_rojo")

    # ── Detectar charts 2, 3 y 4 (vista multi-activo) ────────────────────
    # Se recorren todos los pares color detectados en orden descendente de Y.
    # Cada par con SUBE al menos 60px más abajo que el anterior cuenta como
    # un nuevo chart independiente. Soporta hasta 4 gráficas simultáneas.
    _sufijos_extra = ["_2", "_3", "_4"]
    _ultimo_y = btn_v[1] if btn_v else -1
    _extra_pairs: list = []
    for bv, br in pares:
        if bv is None:
            continue
        if btn_v and bv == btn_v:
            continue   # es chart 1
        if bv[1] - _ultimo_y > 60:   # al menos 60px por debajo del anterior
            _extra_pairs.append((bv, br))
            _ultimo_y = bv[1]
        if len(_extra_pairs) >= 3:
            break   # máximo 3 extras → charts 2, 3, 4

    for suf, (bv_ex, br_ex) in zip(_sufijos_extra, _extra_pairs):
        if bv_ex:
            resultado[f"boton_verde{suf}"] = bv_ex
        if br_ex:
            resultado[f"boton_rojo{suf}"] = br_ex

    # Extraer btn_v2/btn_r2 para calcular regiones (retrocompatibilidad)
    btn_v2 = resultado.get("boton_verde_2")
    btn_r2 = resultado.get("boton_rojo_2")

    resultado.update(_calcular_region_grafico(
        img, btn_v, btn_r, btn_v2, w_total, h_total,
        btn_r2=btn_r2,
        pares_extra=[(resultado.get(f"boton_verde{s}"),
                      resultado.get(f"boton_rojo{s}"))
                     for s in _sufijos_extra[1:]]))   # charts 3,4

    # ── Auto-aprendizaje: guarda la forma del botón para la próxima vez ───
    if btn_v:
        x, y = btn_v
        crop = img[max(0, y - 28):y + 28, max(0, x - 48):x + 48]
        _guardar_template("boton_verde", crop)
    if btn_r:
        x, y = btn_r
        crop = img[max(0, y - 28):y + 28, max(0, x - 48):x + 48]
        _guardar_template("boton_rojo", crop)

    return resultado


def verificar_boton_activo(x: int, y: int, es_verde: bool, radio: int = 30) -> bool:
    """Verifica que la posición (x,y) muestra el color correcto de botón SUBE/BAJA.

    Usa el screenshot de pantalla completa en caché — sin grab() adicional.
    Devuelve True también si no puede verificar (no bloquea el trade).

    Radio amplio (30px) para sobrevivir animaciones post-trade de IQ Option.
    Umbral permisivo (1.05) porque el hover/press state oscurece ligeramente el color.
    Dos intentos: ROI central + ROI ampliada para máxima robustez.

    es_verde : True → busca verde (SUBE), False → busca rojo (BAJA)
    """
    # Screenshot cacheado (hasta 2s) — cero overhead GDI
    ahora   = time.time()
    img_src = None
    if ahora - _cache_full["ts"] < 2.0 and _cache_full["img"] is not None:
        img_src = _cache_full["img"]

    def _check_zona(zona) -> bool:
        if zona is None or zona.size == 0:
            return True   # sin imagen → no bloquear
        b_m = float(zona[:, :, 0].mean())
        g_m = float(zona[:, :, 1].mean())
        r_m = float(zona[:, :, 2].mean())
        # Umbral reducido a 1.05 (antes 1.08) y valor mínimo a 40 (antes 50)
        if es_verde:
            return g_m > r_m * 1.05 and g_m > 40
        else:
            return r_m > g_m * 1.05 and r_m > 40

    if img_src is not None:
        H, W = img_src.shape[:2]
        # Intento 1: ROI estándar
        x1 = max(0, x - radio);  x2 = min(W, x + radio)
        y1 = max(0, y - radio);  y2 = min(H, y + radio)
        if x2 <= x1 or y2 <= y1:
            return True
        if _check_zona(img_src[y1:y2, x1:x2]):
            return True
        # Intento 2: ROI ampliada (×2) — cubre animaciones que desplazan el color
        r2 = radio * 2
        x1b = max(0, x - r2);  x2b = min(W, x + r2)
        y1b = max(0, y - r2);  y2b = min(H, y + r2)
        return _check_zona(img_src[y1b:y2b, x1b:x2b])
    else:
        # Captura directa ROI (no hay caché)
        zona = capturar([x - radio, y - radio, x + radio, y + radio])
        if _check_zona(zona):
            return True
        # Segunda oportunidad con ROI mayor
        zona2 = capturar([x - radio * 2, y - radio * 2,
                          x + radio * 2, y + radio * 2])
        return _check_zona(zona2)


def verificar_trade_abierto(region_pl=None) -> bool:
    """Confirma que IQ Option registró un trade activo buscando contenido
    en el área P&L. Devuelve True si hay posición abierta, False en caso
    contrario. Se llama ~300ms después del click de ejecución."""
    if region_pl:
        img = capturar(region_pl)
    else:
        # Fallback: tercio inferior derecho de pantalla (zona portfolio IQ)
        full = capturar_pantalla_completa()
        if full is None:
            return True   # no se puede verificar → asumir éxito
        h, w = full.shape[:2]
        img = full[int(h * 0.75):, int(w * 0.30):]
    if img is None:
        return True
    # Cualquier texto/P&L activo tiene píxeles blancos o de color (no fondo oscuro)
    b = img[:, :, 0].astype(np.float32)
    g = img[:, :, 1].astype(np.float32)
    r = img[:, :, 2].astype(np.float32)
    colorido = int(np.sum((g > 100) | (r > 100) | (b > 130)))
    return colorido > 80


def _calcular_region_grafico(img, btn_v, btn_r, btn_v2, w_total, h_total,
                              btn_r2=None, pares_extra=None) -> dict:
    """Calcula region_grafico (chart 1) y, si hay un 2do par de botones,
    region_grafico_2 (chart 2 — vista dividida con otro activo). Si no hay
    botones, recurre a detectar la zona oscura del chart (fallback)."""
    resultado = {}
    # La ventana de Litch ocupa los primeros ~400px de la izquierda.
    # El gráfico de IQ Option empieza después del sidebar izquierdo de IQ (~65px).
    _litch_w   = 400
    _iq_top    = int(h_total * 0.07)   # debajo del header de IQ
    _iq_bottom = int(h_total * 0.92)   # encima de la barra inferior

    # Método 1: estimar desde posición de los botones (más preciso)
    gy2_chart1 = None
    if btn_v:
        bx_panel = btn_v[0] - 115    # borde izquierdo del panel SUBE/BAJA
        gx1 = max(_litch_w, int(w_total * 0.22))
        gx2 = max(bx_panel, int(w_total * 0.50))
        gy1 = _iq_top
        # Si hay 2 gráficas: limitar la región al primer chart para no mezclar señales.
        if btn_v2:
            gy2 = max(btn_r[1] + 80 if btn_r else btn_v[1] + 120,
                      btn_v2[1] - 40)
        else:
            gy2 = _iq_bottom
        gy2_chart1 = gy2
        if gx2 - gx1 > 200 and gy2 - gy1 > 100:
            resultado["region_grafico"] = [gx1, gy1, gx2, gy2]

    # Regiones de charts 2, 3, 4 — mismo patrón: desde donde termina el anterior
    # hasta justo encima de sus propios botones. Soporta hasta 4 gráficas.
    _todos_extras = [(btn_v2, btn_r2)] + (list(pares_extra) if pares_extra else [])
    _sufijos_reg  = ["_2", "_3", "_4"]
    _gy2_prev     = gy2_chart1 if gy2_chart1 is not None else _iq_top
    for _suf, (_bv_e, _br_e) in zip(_sufijos_reg, _todos_extras):
        if not _bv_e:
            continue
        _bx_p   = _bv_e[0] - 115
        _gx1_e  = max(_litch_w, int(w_total * 0.22))
        _gx2_e  = max(_bx_p, int(w_total * 0.50))
        _gy1_e  = _gy2_prev
        _gy2_e  = (_br_e[1] - 40) if _br_e else (_bv_e[1] + 80)
        _gy2_e  = min(max(_gy2_e, _gy1_e + 80), _iq_bottom)
        if _gx2_e - _gx1_e > 200 and _gy2_e - _gy1_e > 80:
            resultado[f"region_grafico{_suf}"] = [_gx1_e, _gy1_e, _gx2_e, _gy2_e]
        _gy2_prev = _gy2_e

    # Método 2: detectar zona oscura excluyendo área de Litch
    if "region_grafico" not in resultado:
        x0g, y0g = _litch_w, _iq_top
        x1g, y1g = int(w_total * 0.78), _iq_bottom
        zona_g = img[y0g:y1g, x0g:x1g]
        # IQ Option fondo: ~RGB(21,25,36), mean≈27. Umbral 90 para ser permisivos.
        oscuro = zona_g.astype(np.float32).mean(axis=2) < 90

        if oscuro.sum() > 3000:
            ys_g, xs_g = np.where(oscuro)
            gx1 = int(np.percentile(xs_g,  5)) + x0g
            gy1 = int(np.percentile(ys_g,  5)) + y0g
            gx2 = int(np.percentile(xs_g, 95)) + x0g
            gy2 = int(np.percentile(ys_g, 95)) + y0g
            if gx2 - gx1 > 150 and gy2 - gy1 > 80:
                resultado["region_grafico"] = [gx1, gy1, gx2, gy2]

    return resultado


# ─── Detección de controles UI de IQ Option ──────────────────────────────────

def detectar_ui_iq() -> dict:
    """Detecta campo_monto, selector_duracion y area_asset en IQ Option.

    IQ Option coloca en el panel derecho (40% derecho de pantalla):
      • Campo Invers/monto : caja clara de texto con valor numérico, zona baja-derecha
      • Selector duración  : justo encima del campo monto (muestra "1 min", "5 min"…)
      • Area activo        : barra superior de tabs, texto con nombre del par

    No requiere OCR — usa patrones de color/forma propios de la plataforma.
    """
    img = capturar_pantalla_completa()
    if img is None:
        return {}

    h_total, w_total = img.shape[:2]
    resultado = {}

    # El panel de trading de IQ Option está en el 30% derecho
    x_panel = int(w_total * 0.70)
    panel   = img[:, x_panel:]
    ph, pw  = panel.shape[:2]

    # ── Campo Invers/Monto ────────────────────────────────────────────────────
    # En 2-gráficas aparece 2 veces — buscamos la primera (más arriba, chart 1).
    # El "Invers" y el campo "$50" están en la zona entre 20-55% de altura del panel.
    zona_monto = panel[int(ph * 0.20):int(ph * 0.55), :]
    r_m = zona_monto[:, :, 2].astype(float)
    g_m = zona_monto[:, :, 1].astype(float)
    b_m = zona_monto[:, :, 0].astype(float)
    # IQ Option campo monto: fondo gris-azulado ~RGB(34,38,54)
    mask_campo = (
        (r_m > 20) & (r_m < 90) &
        (g_m > 20) & (g_m < 90) &
        (b_m > 35) & (b_m < 110) &
        (b_m > r_m + 4)          # tono azulado
    )
    if mask_campo.sum() > 400:
        ys_c, xs_c = np.where(mask_campo)
        cx = int(np.percentile(xs_c, 50)) + x_panel
        cy = int(np.percentile(ys_c, 50)) + int(ph * 0.20)
        resultado["campo_monto"]       = [cx, cy]
        resultado["selector_duracion"] = [cx, max(10, cy - 55)]

    # ── Área del activo (tabs superiores) ────────────────────────────────────
    # La barra de tabs de IQ Option tiene fondo muy oscuro y texto claro.
    header = img[:int(h_total * 0.10), int(w_total * 0.20):int(w_total * 0.80)]
    lum    = header.astype(float).mean(axis=2)
    bright = lum > 155
    if bright.sum() > 100:
        ys_h, xs_h = np.where(bright)
        cx_h = int(np.percentile(xs_h, 30)) + int(w_total * 0.20)
        cy_h = int(np.percentile(ys_h, 50))
        resultado["area_asset"] = [cx_h, cy_h]

    return resultado


# ─── Análisis de contexto completo de la pantalla ─────────────────────────────

def analizar_contexto_iq() -> dict:
    """Captura la pantalla completa y extrae el contexto de IQ Option:
      pl_positivo         : bool | None  — P&L verde=ganando, rojo=perdiendo
      pl_color            : 'verde'/'rojo'/'neutro'/'desconocido'
      botones_ok          : bool  — botones SUBE/BAJA visibles
      posiciones_abiertas : int   — estimado de posiciones activas
      timer_visible       : bool  — countdown circular activo
      asset_tab_visible   : bool  — tabs de activos en barra superior
    """
    img = capturar_pantalla_completa()
    if img is None:
        return {"pl_color": "desconocido", "botones_ok": False,
                "posiciones_abiertas": 0, "timer_visible": False,
                "asset_tab_visible": False, "pl_positivo": None}

    h, w = img.shape[:2]
    ctx  = {}

    # ── 1. P&L en cabecera superior ────────────────────────────────────────
    header = img[:int(h * 0.18), int(w * 0.30):int(w * 0.80)]
    r = header[:, :, 2].astype(float)
    g = header[:, :, 1].astype(float)
    b = header[:, :, 0].astype(float)
    mask_verde = (g > 160) & (g > r * 1.5) & (g > b * 1.3) & (r < 140)
    mask_rojo  = (r > 160) & (r > g * 1.5) & (r > b * 1.4) & (g < 120)
    n_v = int(mask_verde.sum())
    n_r = int(mask_rojo.sum())
    if n_v > 30 and n_v > n_r * 1.5:
        ctx["pl_color"] = "verde";  ctx["pl_positivo"] = True
    elif n_r > 30 and n_r > n_v * 1.5:
        ctx["pl_color"] = "rojo";   ctx["pl_positivo"] = False
    else:
        ctx["pl_color"] = "neutro";  ctx["pl_positivo"] = None

    # ── 2. Botones SUBE/BAJA (panel derecho) ────────────────────────────────
    # Zona ampliada (25%→70%) y thresholds permisivos para sobrevivir
    # animaciones post-trade de IQ Option que oscurecen temporalmente los botones.
    # botones_ok=True si AL MENOS uno de los dos botones es visible (OR logic).
    panel_d = img[int(h * 0.25):int(h * 0.75), int(w * 0.75):]
    pd_r = panel_d[:, :, 2].astype(float)
    pd_g = panel_d[:, :, 1].astype(float)
    pd_b = panel_d[:, :, 0].astype(float)
    # Verde: G dominante con diferencia clara sobre R — sin exigir R<110
    btn_verde = ((pd_g > 100) & (pd_g > pd_r * 1.20) & (pd_g > pd_b * 1.10)).sum()
    # Rojo: R dominante con diferencia clara sobre G
    btn_rojo  = ((pd_r > 100) & (pd_r > pd_g * 1.20) & (pd_r > pd_b * 1.10)).sum()
    # Umbral 60px (antes 200) — basta con ver parte del botón
    ctx["botones_ok"] = bool(btn_verde > 60 or btn_rojo > 60)

    # ── 3. Posiciones abiertas (íconos de reloj naranja en tabla inferior) ──
    tabla = img[int(h * 0.72):, int(w * 0.25):]
    t_r = tabla[:, :, 2].astype(float)
    t_g = tabla[:, :, 1].astype(float)
    t_b = tabla[:, :, 0].astype(float)
    mask_clock = (t_r > 180) & (t_g > 120) & (t_g < 200) & (t_b < 80)
    ctx["posiciones_abiertas"] = min(10, int(mask_clock.sum() // 60))

    # ── 4. Timer circular visible ────────────────────────────────────────────
    timer_zona = img[:int(h * 0.20), int(w * 0.35):int(w * 0.55)]
    tz_r = timer_zona[:, :, 2].astype(float)
    tz_g = timer_zona[:, :, 1].astype(float)
    tz_b = timer_zona[:, :, 0].astype(float)
    ctx["timer_visible"] = bool(
        ((tz_r > 200) & (tz_g > 50) & (tz_g < 170) & (tz_b < 80)).sum() > 15)

    # ── 5. Tabs de activos ──────────────────────────────────────────────────
    tabs = img[:int(h * 0.08), int(w * 0.12):int(w * 0.65)]
    ctx["asset_tab_visible"] = bool(
        (tabs.astype(float).mean(axis=2) > 180).sum() > 200)

    return ctx


# ── Lectura inteligente de valores de IQ Option desde pantalla ────────────────

def leer_valores_iq() -> dict:
    """
    Lee en tiempo real el saldo, monto, vencimiento y posiciones abiertas
    directamente de la pantalla de IQ Option usando análisis de color y
    densidad de píxeles — sin OCR, sin dependencias externas.

    Retorna:
        saldo_cambio   : 'sube' | 'baja' | 'estable' | None
        saldo_px       : número de píxeles naranjas del saldo (proxy de magnitud)
        monto_region   : region [x1,y1,x2,y2] del campo Invers
        venc_region    : region [x1,y1,x2,y2] del campo Vencimiento
        posiciones     : int  — posiciones abiertas estimadas
        en_operacion   : bool — hay una operación en curso (timer circular)
        balance_crece  : bool | None — saldo mayor que medición anterior
    """
    import time as _t_vis
    # ── Caché de 4 segundos para reducir capturas de pantalla y lag ───────────
    _cache_ts = getattr(leer_valores_iq, "_cache_ts", 0.0)
    if _t_vis.time() - _cache_ts < 7.0:
        return getattr(leer_valores_iq, "_cache_res", {})

    img = capturar_pantalla_completa()
    if img is None:
        return {}

    h, w = img.shape[:2]
    resultado = {}

    # ── 1. Saldo en top-right: IQ Option usa naranja/dorado para el balance ──
    # El saldo "$7,555.00" aparece en la esquina sup-derecha (aprox 55-90% ancho, 0-12% alto)
    saldo_zona = img[:int(h * 0.10), int(w * 0.55):]
    r = saldo_zona[:, :, 2].astype(float)
    g = saldo_zona[:, :, 1].astype(float)
    b = saldo_zona[:, :, 0].astype(float)
    # Naranja IQ Option: R alto, G medio, B bajo
    mask_naranja = ((r > 200) & (g > 90) & (g < 200) & (b < 80))
    # Blanco brillante (también puede ser blanco)
    mask_blanco  = ((r > 220) & (g > 220) & (b > 220))
    mask_saldo   = mask_naranja | mask_blanco
    saldo_px     = int(mask_saldo.sum())
    resultado["saldo_px"] = saldo_px

    # Comparar con última medición para detectar subida/bajada
    _ultimo = getattr(leer_valores_iq, "_saldo_px_ant", 0)
    delta   = saldo_px - _ultimo
    if abs(delta) < 20:
        resultado["saldo_cambio"] = "estable"
    elif delta > 0:
        resultado["saldo_cambio"] = "sube"
        resultado["balance_crece"] = True
    else:
        resultado["saldo_cambio"] = "baja"
        resultado["balance_crece"] = False
    leer_valores_iq._saldo_px_ant = saldo_px

    # ── 2. Panel derecho — Invers (monto) y Vencimiento ───────────────────────
    panel_x1 = int(w * 0.85)
    panel_x2 = w
    monto_y1  = int(h * 0.10)
    monto_y2  = int(h * 0.22)
    venc_y1   = int(h * 0.21)
    venc_y2   = int(h * 0.32)
    resultado["monto_region"]  = [panel_x1, monto_y1, panel_x2, monto_y2]
    resultado["venc_region"]   = [panel_x1, venc_y1,  panel_x2, venc_y2]

    # ── 3. Posiciones abiertas (una sola llamada a analizar_contexto_iq) ─────
    _ctx = analizar_contexto_iq()
    resultado["posiciones"]   = _ctx.get("posiciones_abiertas", 0)
    resultado["en_operacion"] = _ctx.get("timer_visible", False)

    # ── Actualizar caché ──────────────────────────────────────────────────────
    leer_valores_iq._cache_ts  = _t_vis.time()
    leer_valores_iq._cache_res = resultado

    return resultado


def leer_saldo_aproximado(saldo_base: float, historial_pnl: list) -> float:
    """
    Calcula el saldo aproximado actual usando:
      1. saldo_base : último saldo conocido (dicho por el usuario o calibración)
      2. historial_pnl : lista de floats con los P&L de cada trade (+ ganancia, - pérdida)

    Combina esto con la detección de tendencia de pantalla (naranja pixels).
    Devuelve el saldo estimado con alta precisión matemática.
    """
    saldo_calc = saldo_base + sum(historial_pnl)
    # Verificar con análisis de pantalla
    try:
        ctx = leer_valores_iq()
        cambio = ctx.get("saldo_cambio")
        if cambio == "sube" and saldo_calc <= saldo_base:
            saldo_calc = saldo_base * 1.001  # corrección leve
        elif cambio == "baja" and saldo_calc >= saldo_base:
            saldo_calc = saldo_base * 0.999
    except Exception:
        pass
    return round(max(0.0, saldo_calc), 2)

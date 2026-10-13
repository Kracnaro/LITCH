"""
UI Learner — LITCH aprende a usar la interfaz del broker de forma visual,
agnóstica de idioma y ultrarrápida.

Identifica botones por COLOR + FORMA + POSICIÓN, nunca por texto.
  · Botón verde (H 40-90 HSV)  → compra/sube
  · Botón rojo  (H 0-12|168+)  → venta/baja

Fases de aprendizaje
─────────────────────
  OBSERVANDO  (< 10 interacciones)  — solo registra, sin caché propia
  APRENDIENDO (10 – 49)             — construye mapa, sugiere posiciones
  ENTRENADO   (≥ 50, conf ≥ 0.75)  — lookup O(1) desde mapa persistente
  AUTONOMO    (entrenado + gate)    — guía al sistema con plena autonomía

Optimizaciones de velocidad
────────────────────────────
  · Reutiliza la caché de vision.py (sin duplicar capturas)
  · ROI captures para verificación rápida (no pantalla completa)
  · Frame differencing: omite frames sin cambios significativos
  · Actualización Bayesiana (Laplace) en cada interacción

Persistencia
────────────
  MEMORIA_AP/ui_map.json — sobrevive reinicios
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

# ── Dependencias opcionales ────────────────────────────────────────────────────
try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

try:
    import cv2 as _cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss as _mss_mod
    _MSS = True
except ImportError:
    _MSS = False

# ── Rutas ─────────────────────────────────────────────────────────────────────
_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA_MAP  = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "ui_map.json")

# ── Umbrales de fase ──────────────────────────────────────────────────────────
_MIN_INTER    = 10    # interacciones antes de APRENDIENDO
_UMBRAL_ENT   = 50    # interacciones para ENTRENADO
_CONF_MIN     = 0.75  # confianza media mínima para ENTRENADO
_DIFF_UMBRAL  = 4.0   # diferencia media de píxeles para considerar frame "cambiado"
_ROI_RADIO    = 80    # px de margen para ROI alrededor de un elemento

# ── Firmas de color HSV (H en [0,179], S/V en [0,255]) ───────────────────────
# Agnósticas de idioma: el botón verde siempre es verde, el rojo siempre es rojo.
_COLOR: Dict[str, Dict] = {
    "compra": {
        "h_lo": 40, "h_hi": 90,
        "s_lo": 100, "v_lo": 110,
        "desc": "verde (compra/sube)",
    },
    "venta": {
        "h_lo": 0,  "h_hi": 12,
        "h_lo2": 166, "h_hi2": 179,   # rojo envuelve 0°
        "s_lo": 100, "v_lo": 110,
        "desc": "rojo (venta/baja)",
    },
}

# ── Fases ─────────────────────────────────────────────────────────────────────
OBSERVANDO  = "OBSERVANDO"
APRENDIENDO = "APRENDIENDO"
ENTRENADO   = "ENTRENADO"
AUTONOMO    = "AUTONOMO"


# ── Dataclasses ───────────────────────────────────────────────────────────────
@dataclass
class ElementoUI:
    """Un elemento de interfaz aprendido visualmente."""
    funcion:    str
    x:          int   = 0
    y:          int   = 0
    ancho:      int   = 60
    alto:       int   = 30
    confianza:  float = 0.50   # Bayesiana: (exitos+1)/(total+2)
    n_exitos:   int   = 0
    n_fallos:   int   = 0
    firma:      str   = ""     # "compra" | "venta" | ""
    h_med:      float = 0.0    # tono HSV medio del centro
    s_med:      float = 0.0
    v_med:      float = 0.0
    ts:         float = 0.0    # timestamp última interacción
    activo:     bool  = True

    def update_conf(self, exito: bool) -> None:
        if exito:
            self.n_exitos += 1
        else:
            self.n_fallos += 1
        total = self.n_exitos + self.n_fallos
        self.confianza = (self.n_exitos + 1) / (total + 2)
        self.ts = time.time()


@dataclass
class Interaccion:
    """Registro de una interacción con la interfaz."""
    ts:        float
    funcion:   str
    x:         int
    y:         int
    resultado: Optional[str]   # "win"|"loss"|"ejecutado"|"fallido"|None
    fase:      str
    conf_pre:  float
    dur_ms:    float = 0.0


# ── UILearner ─────────────────────────────────────────────────────────────────
class UILearner:
    """
    Sistema de aprendizaje visual de interfaz de broker.

    Aprende qué posiciones/colores corresponden a cada función de la UI,
    actualiza su confianza con cada interacción y provee lookups O(1)
    una vez entrenado.

    Instanciar una vez desde litch.py:
        app.ui_learner = UILearner(app)
    """

    def __init__(self, app):
        self.app   = app
        self._lock = threading.Lock()

        self._mapa:      Dict[str, ElementoUI] = {}
        self._historial: List[Interaccion]     = []
        self._n_total:   int                   = 0
        self._fase:      str                   = OBSERVANDO

        # caché de frame para frame-differencing (captura propia)
        self._frame:    Optional[object]   = None   # np.ndarray
        self._frame_ts: float              = 0.0

        self._mss_inst = None
        if _MSS:
            try:
                self._mss_inst = _mss_mod.mss()
            except Exception:
                pass

        self._cargar()

    # ══════════════════════════════════════════════════════════════════════════
    # API pública
    # ══════════════════════════════════════════════════════════════════════════

    @property
    def fase(self) -> str:
        return self._fase

    @property
    def es_autonomo(self) -> bool:
        return self._fase == AUTONOMO

    def estado_resumen(self) -> str:
        """Texto de estado para mostrar en logs/UI."""
        with self._lock:
            n_e   = len([e for e in self._mapa.values() if e.activo])
            confs = [e.confianza for e in self._mapa.values() if e.activo]
            c_med = sum(confs) / len(confs) if confs else 0.0
        return (f"UILearner·{self._fase}  elem={n_e}  "
                f"conf={c_med:.2f}  n={self._n_total}")

    # ── Alimentación desde autocalibracion.py ─────────────────────────────────

    def alimentar_calibracion(self,
                               boton_verde=None,
                               boton_rojo=None,
                               region_grafico=None) -> None:
        """
        Recibe posiciones ya verificadas por autocalibracion.py y las
        incorpora al mapa (confianza inicial = 0.65 — validadas visualmente).
        """
        with self._lock:
            if boton_verde and len(boton_verde) >= 2:
                self._upsert("compra",  boton_verde[0],  boton_verde[1],
                             conf=0.65, firma="compra")
            if boton_rojo and len(boton_rojo) >= 2:
                self._upsert("venta",   boton_rojo[0],   boton_rojo[1],
                             conf=0.65, firma="venta")
            if region_grafico and len(region_grafico) >= 4:
                cx = (region_grafico[0] + region_grafico[2]) // 2
                cy = (region_grafico[1] + region_grafico[3]) // 2
                self._upsert("grafico", cx, cy, conf=0.70, firma="")
        self._actualizar_fase()

    # ── Notificación de click (desde trading._ejecutar_click) ─────────────────

    def notificar_click(self, funcion: str, x: int, y: int) -> None:
        """
        Llamar justo después de cada click ejecutado por trading.py.
        Registra la interacción para aprendizaje futuro.
        """
        conf_pre = 0.5
        with self._lock:
            if funcion in self._mapa:
                conf_pre = self._mapa[funcion].confianza
            inter = Interaccion(
                ts=time.time(), funcion=funcion, x=x, y=y,
                resultado=None, fase=self._fase, conf_pre=conf_pre)
            self._historial.append(inter)
            if len(self._historial) > 500:
                self._historial = self._historial[-400:]
            self._n_total += 1
            # Actualizar posición con media ponderada (nueva posición 70%, anterior 30%)
            self._upsert(funcion, x, y, conf=conf_pre, firma=funcion
                         if funcion in _COLOR else "")
        self._actualizar_fase()

    def registrar_resultado(self, funcion: str, resultado: str) -> None:
        """
        Llamar cuando se conoce el resultado de un trade ("win" | "loss" |
        "ejecutado" | "fallido").  Actualiza la confianza del elemento.
        """
        exito = resultado in ("win", "ejecutado")
        with self._lock:
            # Anotar en la última interacción pendiente de esa función
            for inter in reversed(self._historial[-100:]):
                if inter.funcion == funcion and inter.resultado is None:
                    inter.resultado = resultado
                    break
            e = self._mapa.get(funcion)
            if e:
                e.update_conf(exito)
        self._actualizar_fase()
        self._guardar()

    # ── Obtener posición de un elemento ───────────────────────────────────────

    def obtener_pos(self, funcion: str) -> Optional[Tuple[int, int]]:
        """
        Devuelve (x, y) más confiable para `funcion`.
        1) Mapa aprendido si confianza ≥ 0.45
        2) Re-escaneo de pantalla en tiempo real
        3) None
        """
        with self._lock:
            e = self._mapa.get(funcion)
            if e and e.activo and e.confianza >= 0.45:
                return (e.x, e.y)

        # Fallback: detección visual en tiempo real
        pos = self._detectar_en_pantalla(funcion)
        if pos:
            with self._lock:
                self._upsert(funcion, pos[0], pos[1],
                             conf=0.50,
                             firma=funcion if funcion in _COLOR else "")
        return pos

    # ── Escaneo activo (llamar periódicamente en background) ──────────────────

    def escanear(self) -> None:
        """
        Detecta todos los elementos conocibles en pantalla y actualiza el mapa.
        Llamar desde un hilo daemon; no bloquea la UI.
        """
        try:
            img = self._capturar()
            if img is None or not _NP:
                return
            hsv = self._bgr_a_hsv(img)
            h_t, w_t = img.shape[:2]

            for firma in ("compra", "venta"):
                mask = self._mask_color(hsv, firma)
                # IQ Option: botones siempre en el 40% derecho
                mask[:, :int(w_t * 0.55)] = False
                res = self._mayor_blob(mask)
                if res:
                    with self._lock:
                        self._upsert(firma, res[0], res[1],
                                     conf=0.55, firma=firma)

            self._actualizar_firmas_hsv(img)
            self._guardar()
        except Exception as ex:
            self._log(f"[UILearner] escanear error: {ex}")

    # ══════════════════════════════════════════════════════════════════════════
    # Detección visual interna
    # ══════════════════════════════════════════════════════════════════════════

    def _detectar_en_pantalla(self, funcion: str) -> Optional[Tuple[int, int]]:
        if funcion not in _COLOR:
            return None
        img = self._capturar()
        if img is None or not _NP:
            return None
        h_t, w_t = img.shape[:2]
        hsv  = self._bgr_a_hsv(img)
        mask = self._mask_color(hsv, funcion)
        mask[:, :int(w_t * 0.55)] = False
        res = self._mayor_blob(mask)
        return (res[0], res[1]) if res else None

    # ── Captura con frame-diff ────────────────────────────────────────────────

    def _capturar(self) -> Optional[object]:
        """
        Captura la pantalla completa.
        Reutiliza el frame anterior si la pantalla no cambió
        (frame-diff medio < _DIFF_UMBRAL).
        Prioritiza la caché de vision.py cuando está disponible.
        """
        # 1° Intentar usar la caché compartida de vision.py (cero overhead)
        try:
            from . import vision as _vis
            img = _vis.capturar_pantalla_completa()
            if img is not None:
                return img
        except Exception:
            pass

        # 2° Captura propia con mss
        if not _NP or not _MSS or not self._mss_inst:
            return None
        try:
            mon = self._mss_inst.monitors[1]
            raw = self._mss_inst.grab(mon)
            nuevo = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(
                mon["height"], mon["width"], 4)[:, :, :3]

            if self._frame is not None:
                diff = float(np.mean(
                    np.abs(nuevo.astype(np.int32) - self._frame.astype(np.int32))))
                if diff < _DIFF_UMBRAL:
                    self._frame_ts = time.time()
                    return self._frame

            self._frame    = nuevo
            self._frame_ts = time.time()
            return nuevo
        except Exception:
            return None

    # ── Color HSV ─────────────────────────────────────────────────────────────

    def _bgr_a_hsv(self, bgr):
        if _CV2:
            return _cv2.cvtColor(bgr, _cv2.COLOR_BGR2HSV)
        # Conversión manual vectorizada (sin cv2)
        f    = bgr.astype(np.float32) / 255.0
        r, g, b = f[:,:,2], f[:,:,1], f[:,:,0]
        cmax = np.maximum.reduce([r, g, b])
        cmin = np.minimum.reduce([r, g, b])
        d    = cmax - cmin
        h    = np.zeros_like(r)
        mr = (cmax == r) & (d > 0)
        mg = (cmax == g) & (d > 0)
        mb = (cmax == b) & (d > 0)
        h[mr] = (60 * ((g[mr] - b[mr]) / d[mr])) % 360
        h[mg] = 60 * ((b[mg] - r[mg]) / d[mg]) + 120
        h[mb] = 60 * ((r[mb] - g[mb]) / d[mb]) + 240
        s = np.where(cmax > 0, d / cmax, 0)
        return np.stack([(h / 2).clip(0, 179).astype(np.uint8),
                         (s * 255).clip(0, 255).astype(np.uint8),
                         (cmax * 255).clip(0, 255).astype(np.uint8)], axis=2)

    def _mask_color(self, hsv, firma: str) -> object:
        f = _COLOR.get(firma)
        if f is None:
            return np.zeros(hsv.shape[:2], dtype=bool)
        h = hsv[:,:,0].astype(np.int32)
        s = hsv[:,:,1].astype(np.int32)
        v = hsv[:,:,2].astype(np.int32)
        s_ok = s >= f["s_lo"]
        v_ok = v >= f["v_lo"]
        h_ok = (h >= f["h_lo"]) & (h <= f["h_hi"])
        if "h_lo2" in f:
            h_ok = h_ok | ((h >= f["h_lo2"]) & (h <= f["h_hi2"]))
        return h_ok & s_ok & v_ok

    def _mayor_blob(self, mask, min_pix: int = 350) -> Optional[Tuple[int, int, int]]:
        """Devuelve (cx, cy, area) del blob más grande que cumpla criterios de botón."""
        if not _NP or mask.sum() < min_pix:
            return None
        if _CV2:
            m8  = mask.astype(np.uint8) * 255
            n, _, stats, cents = _cv2.connectedComponentsWithStats(m8, connectivity=8)
            mejor = None
            for i in range(1, n):
                a  = int(stats[i, _cv2.CC_STAT_AREA])
                wb = int(stats[i, _cv2.CC_STAT_WIDTH])
                hb = int(stats[i, _cv2.CC_STAT_HEIGHT])
                if a < min_pix or wb < 20 or hb < 10 or wb > 500 or hb > 200:
                    continue
                if mejor is None or a > mejor[2]:
                    mejor = (int(cents[i][0]), int(cents[i][1]), a)
            return mejor
        # Fallback sin cv2
        ys, xs = np.where(mask)
        if len(ys) < min_pix:
            return None
        return (int(np.mean(xs)), int(np.mean(ys)), int(len(ys)))

    def _actualizar_firmas_hsv(self, img) -> None:
        """Para cada elemento conocido, actualiza su firma de color HSV actual."""
        if not _NP:
            return
        hsv = self._bgr_a_hsv(img)
        H, W = img.shape[:2]
        with self._lock:
            for e in self._mapa.values():
                if not e.activo:
                    continue
                x1 = max(0, e.x - 15); x2 = min(W, e.x + 15)
                y1 = max(0, e.y - 8);  y2 = min(H, e.y + 8)
                roi = hsv[y1:y2, x1:x2]
                if roi.size == 0:
                    continue
                e.h_med = float(np.mean(roi[:,:,0]))
                e.s_med = float(np.mean(roi[:,:,1]))
                e.v_med = float(np.mean(roi[:,:,2]))

    # ══════════════════════════════════════════════════════════════════════════
    # Mapa interno
    # ══════════════════════════════════════════════════════════════════════════

    def _upsert(self, funcion: str, x: int, y: int,
                conf: float = 0.50, firma: str = "") -> None:
        """Inserta o actualiza un elemento. NO adquiere el lock (caller lo hace)."""
        if funcion in self._mapa:
            e = self._mapa[funcion]
            # Media ponderada: posición nueva 70%, anterior 30%
            e.x     = int(e.x * 0.3 + x * 0.7)
            e.y     = int(e.y * 0.3 + y * 0.7)
            e.confianza = max(e.confianza, conf)
            if firma:
                e.firma = firma
        else:
            self._mapa[funcion] = ElementoUI(
                funcion=funcion, x=x, y=y,
                confianza=conf, firma=firma, ts=time.time())

    # ══════════════════════════════════════════════════════════════════════════
    # Gestión de fases
    # ══════════════════════════════════════════════════════════════════════════

    def _actualizar_fase(self) -> None:
        n = self._n_total
        with self._lock:
            activos = [e for e in self._mapa.values() if e.activo]
        confs  = [e.confianza for e in activos]
        c_med  = sum(confs) / len(confs) if confs else 0.0
        gate   = (getattr(self.app, "autoclick_on", False) and
                  getattr(self.app, "modo_autonomo", False))

        if gate and n >= _UMBRAL_ENT and c_med >= _CONF_MIN:
            nueva = AUTONOMO
        elif n >= _UMBRAL_ENT and c_med >= _CONF_MIN:
            nueva = ENTRENADO
        elif n >= _MIN_INTER:
            nueva = APRENDIENDO
        else:
            nueva = OBSERVANDO

        if nueva != self._fase:
            self._fase = nueva
            self._log(f"[UILearner] Fase → {nueva}  "
                      f"(n={n}, conf_med={c_med:.2f})")

    # ══════════════════════════════════════════════════════════════════════════
    # Persistencia
    # ══════════════════════════════════════════════════════════════════════════

    def _cargar(self) -> None:
        try:
            if not os.path.exists(_RUTA_MAP):
                return
            with open(_RUTA_MAP, "r", encoding="utf-8") as f:
                d = json.load(f)
            for fn, raw in d.get("mapa", {}).items():
                try:
                    self._mapa[fn] = ElementoUI(**raw)
                except Exception:
                    pass
            self._n_total = int(d.get("n_total", 0))
            self._fase    = d.get("fase", OBSERVANDO)
        except Exception as ex:
            print(f"[UILearner] No se pudo cargar ui_map.json: {ex}")

    def _guardar(self) -> None:
        import uuid
        try:
            os.makedirs(os.path.dirname(_RUTA_MAP), exist_ok=True)
            with self._lock:
                payload = {
                    "n_total": self._n_total,
                    "fase":    self._fase,
                    "mapa":    {fn: asdict(e) for fn, e in self._mapa.items()},
                }
            # Nombre único para evitar colisión en Windows con otro hilo
            tmp = _RUTA_MAP + f".{uuid.uuid4().hex[:8]}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            # os.replace falla en Windows si el destino está abierto → retry
            for _intento in range(3):
                try:
                    os.replace(tmp, _RUTA_MAP)
                    return
                except OSError:
                    import time as _t
                    _t.sleep(0.12 * (_intento + 1))
            # Último intento: copiar y borrar manualmente
            import shutil
            shutil.copy2(tmp, _RUTA_MAP)
            try:
                os.remove(tmp)
            except OSError:
                pass
        except Exception as ex:
            print(f"[UILearner] Error guardando ui_map.json: {ex}")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        try:
            self.app.log(msg)
        except Exception:
            print(msg)


# ══════════════════════════════════════════════════════════════════════════════
# Hilo de exploración en background (daemon)
# ══════════════════════════════════════════════════════════════════════════════

class UILearnerDaemon(threading.Thread):
    """
    Escanea la pantalla cada N segundos para mantener el mapa actualizado.
    Se activa solo cuando el trading está activo (no consume CPU en idle).
    """

    def __init__(self, learner: UILearner):
        super().__init__(daemon=True, name="UILearnerDaemon")
        self._learner = learner

    def run(self) -> None:
        time.sleep(5.0)   # esperar arranque
        while True:
            try:
                app  = self._learner.app
                activo = getattr(app, "trading_on", False)
                if activo:
                    self._learner.escanear()
                    time.sleep(15.0)   # cada 15s cuando trading está activo
                else:
                    time.sleep(30.0)   # cada 30s en idle
            except Exception:
                time.sleep(30.0)

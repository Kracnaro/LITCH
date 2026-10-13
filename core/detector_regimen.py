"""
detector_regimen.py — Detector profesional de régimen de mercado para LITCH v3.

Clasifica el mercado en tiempo real en uno de 5 regímenes:
  • TRENDING_UP    — tendencia alcista clara (Hurst>0.6, ADX>25, pendent>0)
  • TRENDING_DOWN  — tendencia bajista clara
  • RANGING        — mercado lateral (Hurst<0.45, ATR bajo, BB angosto)
  • BREAKOUT       — ruptura de rango (BB squeeze + expansión súbita)
  • CHAOTIC        — ruido puro (Hurst~0.5, entropía alta, sin estructura)

Cada régimen tiene estrategias óptimas y penalizaciones asociadas para
que el sistema de votación pese las señales correctamente.

100% NumPy, sin dependencias externas.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np


# ── Constantes de umbral ──────────────────────────────────────────────────────

_HURST_TREND  = 0.58   # Hurst >0.58 → mercado con memoria (trending)
_HURST_ANTI   = 0.42   # Hurst <0.42 → media-reversión
_ADX_TREND    = 22.0   # ADX >22 → tendencia definida
_ATR_PCT_LOW  = 0.004  # ATR < 0.4% del precio → rango apretado
_ATR_PCT_HIGH = 0.012  # ATR > 1.2% del precio → volatilidad alta
_BB_SQUEEZE   = 0.015  # BB width < 1.5% del precio → squeeze
_ENTROPIA_CAO = 0.75   # Entropía permutation > 75% → ruido puro
_MIN_VELAS    = 20     # mínimo de velas para análisis


class Regimen(NamedTuple):
    tipo:        str    # TRENDING_UP | TRENDING_DOWN | RANGING | BREAKOUT | CHAOTIC
    confianza:   float  # 0–1
    hurst:       float
    adx:         float
    atr_pct:     float
    entropia:    float
    bb_width:    float
    pendiente:   float  # pendiente normalizada de la EMA20
    descripcion: str

    @property
    def es_trending(self) -> bool:
        return self.tipo in ("TRENDING_UP", "TRENDING_DOWN")

    @property
    def es_favorable(self) -> bool:
        return self.tipo in ("TRENDING_UP", "TRENDING_DOWN", "BREAKOUT")

    @property
    def factor_confianza(self) -> float:
        """Multiplicador de confianza de señal según el régimen."""
        _factores = {
            "TRENDING_UP":   1.15,
            "TRENDING_DOWN": 1.15,
            "RANGING":       0.90,
            "BREAKOUT":      1.05,
            "CHAOTIC":       0.60,
        }
        return _factores.get(self.tipo, 1.0)

    def resumen(self) -> str:
        return (f"[Régimen] {self.tipo} conf={self.confianza:.2f} "
                f"Hurst={self.hurst:.3f} ADX={self.adx:.1f} "
                f"ATR%={self.atr_pct:.3f} Ent={self.entropia:.3f}")


def detectar(sec: list, precios: list | None = None) -> Regimen:
    """
    Detecta el régimen de mercado actual.

    sec     : lista de velas ("V"|"R") recientes
    precios : lista de precios de cierre (opcional; si se omite, no se calculan
              ATR/BB — Hurst y entropía se calculan desde la secuencia binaria)

    Retorna un objeto Regimen con todos los campos.
    """
    if len(sec) < _MIN_VELAS:
        return _regimen_neutro()

    # ── 1. Entropía de permutación sobre la secuencia binaria ─────────────────
    entropia = _entropia_perm(sec[-60:])

    # ── 2. Hurst exponente ────────────────────────────────────────────────────
    serie_bin = np.array([1.0 if c in ("V", "verde", "g") else 0.0 for c in sec[-80:]])
    hurst = _hurst_exp(serie_bin)

    # ── 3. Indicadores de precio si están disponibles ─────────────────────────
    adx      = 0.0
    atr_pct  = 0.0
    bb_width = 0.3    # valor neutro si no hay precios
    pendiente = 0.0

    if precios and len(precios) >= 20:
        arr = np.array(precios[-60:], dtype=float)
        atr_pct  = _atr_pct(arr)
        adx      = _adx(arr)
        bb_width = _bb_width(arr)
        pendiente = _pendiente_ema(arr, 20)
    else:
        # Sin precios: estimar ADX desde la racha binaria
        adx = _adx_proxy(sec[-40:])

    # ── 4. Clasificación ──────────────────────────────────────────────────────
    tipo, confianza, desc = _clasificar(
        hurst, adx, atr_pct, bb_width, entropia, pendiente, bool(precios))

    return Regimen(
        tipo       = tipo,
        confianza  = round(confianza, 3),
        hurst      = round(hurst, 4),
        adx        = round(adx, 2),
        atr_pct    = round(atr_pct, 5),
        entropia   = round(entropia, 4),
        bb_width   = round(bb_width, 4),
        pendiente  = round(pendiente, 6),
        descripcion= desc,
    )


# ── Clasificador principal ────────────────────────────────────────────────────

def _clasificar(hurst, adx, atr_pct, bb_width, entropia,
                pendiente, tiene_precios) -> tuple[str, float, str]:
    """Clasifica el régimen y devuelve (tipo, confianza, descripcion)."""

    # CAÓTICO: entropía alta + Hurst ~0.5
    if entropia > _ENTROPIA_CAO and abs(hurst - 0.5) < 0.08:
        conf = min(1.0, (entropia - _ENTROPIA_CAO) / 0.15 + 0.5)
        return ("CHAOTIC", conf,
                f"Ruido puro: entropía={entropia:.2f}, Hurst~0.5")

    # BREAKOUT: BB squeeze + ATR expandiéndose
    if tiene_precios and bb_width < _BB_SQUEEZE and atr_pct > _ATR_PCT_HIGH * 0.7:
        return ("BREAKOUT", 0.80,
                f"Ruptura de rango: BB={bb_width:.3f} squeeze, ATR={atr_pct:.3f}")

    # RANGING: Hurst anti-persistente + ATR bajo + BB neutro
    if hurst < _HURST_ANTI and (not tiene_precios or atr_pct < _ATR_PCT_HIGH):
        conf = min(1.0, (_HURST_ANTI - hurst) / 0.10 + 0.5)
        return ("RANGING", conf,
                f"Mercado lateral: Hurst={hurst:.3f}, ADX={adx:.1f}")

    # TRENDING: Hurst alto + ADX alto + pendiente clara
    if hurst > _HURST_TREND and adx > _ADX_TREND:
        conf = min(1.0, (hurst - _HURST_TREND) / 0.12
                   + (adx - _ADX_TREND) / 30.0 + 0.4)
        if pendiente > 0:
            return ("TRENDING_UP", conf,
                    f"Tendencia alcista: Hurst={hurst:.3f}, ADX={adx:.1f}")
        else:
            return ("TRENDING_DOWN", conf,
                    f"Tendencia bajista: Hurst={hurst:.3f}, ADX={adx:.1f}")

    # RANGING moderado: ADX bajo
    if adx < 16:
        return ("RANGING", 0.65,
                f"Rango moderado: ADX={adx:.1f}, Hurst={hurst:.3f}")

    # Por defecto: caótico moderado
    return ("CHAOTIC", 0.50, f"Sin estructura clara: Hurst={hurst:.3f}")


# ── Cálculos matemáticos ──────────────────────────────────────────────────────

def _hurst_exp(serie: np.ndarray, max_lag: int = 20) -> float:
    """
    Hurst exponente por R/S analysis.
    Retorna valor en [0, 1]; ~0.5 = ruido blanco, >0.5 = tendencial, <0.5 = reversivo.
    """
    n = len(serie)
    if n < 12:
        return 0.5
    lags   = range(4, min(max_lag, n // 3))
    rs_arr = []
    lag_arr= []
    for lag in lags:
        chunks = n // lag
        if chunks < 2:
            continue
        rs_vals = []
        for i in range(chunks):
            sub = serie[i*lag:(i+1)*lag]
            mean = sub.mean()
            dev  = np.cumsum(sub - mean)
            R = dev.max() - dev.min()
            S = sub.std(ddof=1)
            if S > 1e-10:
                rs_vals.append(R / S)
        if rs_vals:
            rs_arr.append(math.log(max(1e-10, float(np.mean(rs_vals)))))
            lag_arr.append(math.log(lag))
    if len(lag_arr) < 3:
        return 0.5
    # OLS: pendiente = Hurst
    x = np.array(lag_arr)
    y = np.array(rs_arr)
    slope = float(np.cov(x, y)[0, 1] / max(1e-10, float(np.var(x))))
    return float(np.clip(slope, 0.0, 1.0))


def _entropia_perm(sec: list, orden: int = 3) -> float:
    """Entropía de permutación sobre secuencia binaria (0=R, 1=V)."""
    arr = np.array([1.0 if c in ("V", "verde", "g") else 0.0 for c in sec])
    n = len(arr)
    if n < orden + 2:
        return 0.5
    conteos: dict[tuple, int] = {}
    total = 0
    for i in range(n - orden + 1):
        perm = tuple(np.argsort(arr[i:i+orden]))
        conteos[perm] = conteos.get(perm, 0) + 1
        total += 1
    if total == 0:
        return 0.5
    probs = [v / total for v in conteos.values()]
    entropia = -sum(p * math.log(p + 1e-12) for p in probs)
    max_ent = math.log(math.factorial(orden))
    return float(np.clip(entropia / max(1e-9, max_ent), 0.0, 1.0))


def _atr_pct(arr: np.ndarray, p: int = 14) -> float:
    """ATR como porcentaje del precio medio."""
    if len(arr) < p + 2:
        return 0.005
    diffs = np.abs(np.diff(arr))
    atr   = float(np.mean(diffs[-p:]))
    precio_medio = float(np.mean(arr[-p:])) or 1.0
    return atr / precio_medio


def _bb_width(arr: np.ndarray, p: int = 20) -> float:
    """Bollinger Band Width = (upper - lower) / media."""
    if len(arr) < p:
        return 0.05
    ventana = arr[-p:]
    media   = float(np.mean(ventana))
    std     = float(np.std(ventana))
    if media < 1e-9:
        return 0.0
    return (2 * 2 * std) / media   # 2σ each side


def _adx(arr: np.ndarray, p: int = 14) -> float:
    """ADX simplificado desde precios de cierre (sin high/low)."""
    if len(arr) < p + 5:
        return 15.0
    diffs   = np.diff(arr)
    pos_dm  = np.where(diffs > 0, diffs, 0.0)
    neg_dm  = np.where(diffs < 0, -diffs, 0.0)
    tr      = np.abs(diffs)
    atr_p   = float(np.mean(tr[-p:])) or 1e-10
    plus_di = float(np.mean(pos_dm[-p:])) / atr_p * 100
    minus_di= float(np.mean(neg_dm[-p:])) / atr_p * 100
    denom   = plus_di + minus_di
    if denom < 1e-9:
        return 0.0
    dx = abs(plus_di - minus_di) / denom * 100
    return float(np.clip(dx, 0.0, 100.0))


def _adx_proxy(sec: list, p: int = 20) -> float:
    """ADX proxy desde secuencia binaria cuando no hay precios."""
    if len(sec) < p:
        return 15.0
    ult = sec[-p:]
    v_count = sum(1 for c in ult if c in ("V", "verde", "g"))
    r_count = p - v_count
    directionalidad = abs(v_count - r_count) / p   # 0=aleatorio, 1=todos iguales
    return directionalidad * 50.0   # escalar a rango ADX-like [0, 50]


def _pendiente_ema(arr: np.ndarray, p: int = 20) -> float:
    """Pendiente normalizada de la EMA(p) en las últimas 5 velas."""
    if len(arr) < p + 5:
        return 0.0
    alpha = 2.0 / (p + 1)
    ema   = arr[0]
    for v in arr[1:]:
        ema = alpha * v + (1 - alpha) * ema
    # Calcular EMA en los últimos puntos para estimar pendiente
    emas = []
    for i in range(-6, 0):
        e = arr[i]
        emas.append(e)   # simplificado: usar últimas velas como proxy
    slope = float(np.polyfit(range(len(emas)), emas, 1)[0])
    precio_medio = float(np.mean(arr[-20:])) or 1.0
    return slope / precio_medio


def _regimen_neutro() -> Regimen:
    return Regimen(
        tipo="CHAOTIC", confianza=0.3,
        hurst=0.5, adx=0.0, atr_pct=0.0,
        entropia=0.5, bb_width=0.1, pendiente=0.0,
        descripcion="Sin suficientes datos",
    )

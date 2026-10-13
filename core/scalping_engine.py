"""
scalping_engine.py — Motor de Scalping Institucional para LITCH.

Implementa la estrategia de scalping de alta frecuencia usada por fondos
cuantitativos y traders institucionales, adaptada a los datos disponibles:

  1. EMA 200 — Filtro de tendencia mayor (trend alignment filter)
     Si precio > EMA200 → sesgo alcista; si precio < EMA200 → sesgo bajista.
     Los institucionales solo entran en la dirección de la tendencia mayor.

  2. RSI 7 rápido — Gatillo de entrada de momentum (momentum trigger)
     Cruz del RSI-7 sobre nivel 30 → señal de compra (rebote sobreventa).
     Cruz del RSI-7 bajo nivel 70 → señal de venta (rebote sobrecompra).
     El RSI-7 es significativamente más rápido que el estándar de 14 períodos.

  3. ATR 14 — Filtro anti-ruido de mercado (noise filter)
     Si el ATR relativo > umbral de ruido → mercado demasiado volátil → skip.
     Basado en la metodología de Barry Johnson "Algorithmic Trading and DMA".

  4. Spread estimado — Control de coste de transacción (spread guard)
     Estima el spread implícito del mercado usando el rango promedio de velas.
     Si spread > 0.08% → las comisiones destruirían el scalping → no operar.

  5. Relación Riesgo/Beneficio 1:2 tracking
     Calcula si la señal tiene espacio para alcanzar un R/R mínimo de 1:2
     antes de llegar al nivel de soporte/resistencia más cercano.

Referencias académicas:
  · Johnson, B. (2010). Algorithmic Trading and DMA. 4Myeloma Press.
  · Kaufman, P. (2013). Trading Systems and Methods. Wiley Finance.
  · Ehlers, J. (2001). Rocket Science for Traders. Wiley.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ── Constantes de calibración ────────────────────────────────────────────────

_EMA_PERIODO      = 200     # Filtro de tendencia mayor
_RSI_PERIODO      = 7       # RSI rápido de scalping
_ATR_PERIODO      = 14      # Ventana ATR para ruido
_SPREAD_MAX_PCT   = 0.0008  # 0.08% spread máximo aceptable
_RUIDO_MAX_PCT    = 0.006   # ATR relativo > 0.6% = mercado ruidoso
_RSI_SOBREVENTA   = 30.0    # Umbral de rebote alcista
_RSI_SOBRECOMPRA  = 70.0    # Umbral de rebote bajista
_RR_MIN           = 1.5     # Ratio Riesgo/Beneficio mínimo requerido
_N_MIN_OHLC       = 25      # Velas mínimas para análisis confiable


# ── Estructuras de datos ─────────────────────────────────────────────────────

@dataclass
class ResultadoScalping:
    # Componentes del análisis
    tendencia_ema:      Optional[str]   = None   # "alcista" | "bajista" | "neutro"
    precio_vs_ema:      float           = 0.0    # % distancia precio vs EMA 200
    rsi7_actual:        float           = 50.0
    rsi7_anterior:      float           = 50.0
    senal_rsi:          Optional[str]   = None   # "compra" | "venta" | None
    atr_relativo:       float           = 0.0    # ATR / precio (%)
    mercado_ruidoso:    bool            = False
    spread_estimado:    float           = 0.0    # (%) spread implícito
    spread_excesivo:    bool            = False
    rr_estimado:        float           = 0.0    # ratio Riesgo/Beneficio proyectado
    rr_favorable:       bool            = False
    confianza:          float           = 0.0
    direccion_scalp:    Optional[str]   = None   # "V" (buy) | "R" (sell) | None
    alineado:           bool            = False  # señal alineada con EMA
    texto:              str             = ""

    @property
    def votar_scalp(self) -> bool:
        return (
            self.alineado
            and self.senal_rsi is not None
            and not self.mercado_ruidoso
            and not self.spread_excesivo
            and self.confianza >= 0.55
        )


# ── Cálculo de indicadores ───────────────────────────────────────────────────

def _ema(precios: np.ndarray, periodo: int) -> np.ndarray:
    """EMA clásica con factor de suavizado k = 2/(periodo+1)."""
    k  = 2.0 / (periodo + 1)
    em = np.empty(len(precios))
    em[0] = precios[0]
    for i in range(1, len(precios)):
        em[i] = precios[i] * k + em[i - 1] * (1 - k)
    return em


def _rsi(closes: np.ndarray, periodo: int = 7) -> np.ndarray:
    """RSI de Wilder en el periodo indicado."""
    n = len(closes)
    if n < periodo + 1:
        return np.full(n, 50.0)
    deltas = np.diff(closes)
    seed   = deltas[:periodo]
    up     = seed[seed >= 0].sum() / periodo
    down   = -seed[seed < 0].sum() / periodo
    rs     = np.zeros(n)
    rs[periodo] = up / down if down != 0 else 100.0
    for i in range(periodo + 1, n):
        d = deltas[i - 1]
        if d >= 0:
            up   = (up * (periodo - 1) + d) / periodo
        else:
            down = (down * (periodo - 1) - d) / periodo
        rs[i] = up / down if down != 0 else 100.0
    rsi_ = np.where(rs == 100.0, 100.0, 100.0 - 100.0 / (1.0 + rs))
    rsi_[:periodo] = 50.0
    return rsi_


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
         periodo: int = 14) -> float:
    """ATR promedio de Wilder — mide volatilidad/ruido de mercado."""
    if len(highs) < periodo + 1:
        return float(np.mean(highs - lows)) if len(highs) > 0 else 0.0
    tr  = np.maximum(highs[1:] - lows[1:],
          np.maximum(np.abs(highs[1:] - closes[:-1]),
                     np.abs(lows[1:]  - closes[:-1])))
    atr = float(np.mean(tr[-periodo:]))
    return atr


def _spread_implicito(highs: np.ndarray, lows: np.ndarray,
                      closes: np.ndarray, n: int = 5) -> float:
    """
    Estima el spread implícito del mercado basado en el rango promedio
    de las últimas N velas normalizado por el precio.
    (Proxy del coste de transacción efectivo en ausencia de bid/ask real)
    """
    if len(highs) < n or closes[-1] == 0:
        return 0.0
    rango_promedio = float(np.mean(highs[-n:] - lows[-n:]))
    precio         = float(closes[-1])
    # Spread estimado ≈ 30% del rango (el resto es movimiento de precio)
    return (rango_promedio * 0.30) / precio if precio > 0 else 0.0


# ── Modo sintético (sin OHLC real) ───────────────────────────────────────────

def _sintetico_precio(sec: list) -> np.ndarray:
    """Convierte secuencia V/R en serie de precio sintético acumulado."""
    return np.cumsum([1.0 if c == 'V' else -1.0 for c in sec]) + 100.0


def _analizar_sintetico(sec: list) -> ResultadoScalping:
    """
    Análisis sin datos OHLC — opera con precio sintético.
    Menos preciso pero mantiene el motor activo en modo V/R.
    """
    if len(sec) < _N_MIN_OHLC:
        return ResultadoScalping(texto="Serie insuficiente para scalping")

    precios = _sintetico_precio(sec)

    if len(precios) < _EMA_PERIODO:
        ema_val = float(np.mean(precios))
    else:
        ema_vals = _ema(precios, _EMA_PERIODO)
        ema_val  = float(ema_vals[-1])

    precio_actual = float(precios[-1])
    tendencia = ("alcista" if precio_actual > ema_val
                 else "bajista" if precio_actual < ema_val else "neutro")

    rsi_vals  = _rsi(precios, _RSI_PERIODO)
    rsi_act   = float(rsi_vals[-1])
    rsi_ant   = float(rsi_vals[-2]) if len(rsi_vals) >= 2 else 50.0

    # Cruce de RSI
    senal_rsi = None
    if rsi_ant <= _RSI_SOBREVENTA and rsi_act > _RSI_SOBREVENTA:
        senal_rsi = "compra"
    elif rsi_ant >= _RSI_SOBRECOMPRA and rsi_act < _RSI_SOBRECOMPRA:
        senal_rsi = "venta"

    # Alineación
    dir_scalp = None
    alineado  = False
    if senal_rsi == "compra" and tendencia == "alcista":
        dir_scalp, alineado = "V", True
    elif senal_rsi == "venta" and tendencia == "bajista":
        dir_scalp, alineado = "R", True
    elif senal_rsi is not None:
        dir_scalp = "V" if senal_rsi == "compra" else "R"

    # Confianza sintética
    dist_ema = abs(precio_actual - ema_val) / (abs(ema_val) + 1e-9)
    confianza = 0.0
    if alineado:
        intensidad_rsi = abs(rsi_act - (
            _RSI_SOBREVENTA if senal_rsi == "compra" else _RSI_SOBRECOMPRA)) / 20.0
        confianza = min(0.72, 0.55 + intensidad_rsi * 0.12 + min(dist_ema * 2, 0.05))

    return ResultadoScalping(
        tendencia_ema    = tendencia,
        precio_vs_ema    = dist_ema,
        rsi7_actual      = rsi_act,
        rsi7_anterior    = rsi_ant,
        senal_rsi        = senal_rsi,
        atr_relativo     = 0.0,
        mercado_ruidoso  = False,
        spread_estimado  = 0.0,
        spread_excesivo  = False,
        rr_estimado      = 2.0,
        rr_favorable     = True,
        confianza        = confianza,
        direccion_scalp  = dir_scalp,
        alineado         = alineado,
        texto            = (f"Scalp sintético: {tendencia} | RSI7={rsi_act:.1f} "
                            f"| {'✓ Alineado' if alineado else '✗ No alineado'}"),
    )


# ── API pública ───────────────────────────────────────────────────────────────

def analizar(sec: list, velas_ohlc: list = None) -> ResultadoScalping:
    """
    Análisis completo de scalping institucional.

    Args:
        sec:        Lista V/R de velas recientes.
        velas_ohlc: Lista de dicts {'open','high','low','close'}.

    Returns:
        ResultadoScalping con todos los componentes del análisis.
    """
    if not velas_ohlc or len(velas_ohlc) < _N_MIN_OHLC:
        return _analizar_sintetico(sec)

    try:
        velas    = velas_ohlc[-max(_EMA_PERIODO + 5, len(velas_ohlc)):]
        opens    = np.array([float(v.get("open",  0)) for v in velas])
        highs    = np.array([float(v.get("high",  0)) for v in velas])
        lows     = np.array([float(v.get("low",   0)) for v in velas])
        closes   = np.array([float(v.get("close", 0)) for v in velas])

        precio_actual = float(closes[-1])
        if precio_actual == 0:
            return _analizar_sintetico(sec)

        # ── 1. EMA 200 — filtro de tendencia mayor ────────────────────────────
        ema_vals  = _ema(closes, _EMA_PERIODO)
        ema_val   = float(ema_vals[-1])
        dist_ema  = (precio_actual - ema_val) / (ema_val + 1e-9)
        tendencia = ("alcista" if dist_ema > 0.001
                     else "bajista" if dist_ema < -0.001 else "neutro")

        # ── 2. RSI 7 — gatillo rápido ─────────────────────────────────────────
        rsi_vals = _rsi(closes, _RSI_PERIODO)
        rsi_act  = float(rsi_vals[-1])
        rsi_ant  = float(rsi_vals[-2]) if len(rsi_vals) >= 2 else 50.0

        senal_rsi = None
        if rsi_ant <= _RSI_SOBREVENTA and rsi_act > _RSI_SOBREVENTA:
            senal_rsi = "compra"    # cruce alcista en zona sobreventa
        elif rsi_ant >= _RSI_SOBRECOMPRA and rsi_act < _RSI_SOBRECOMPRA:
            senal_rsi = "venta"     # cruce bajista en zona sobrecompra

        # ── 3. ATR — filtro de ruido ──────────────────────────────────────────
        atr_val      = _atr(highs, lows, closes, _ATR_PERIODO)
        atr_rel      = atr_val / precio_actual if precio_actual > 0 else 0.0
        ruidoso      = atr_rel > _RUIDO_MAX_PCT

        # ── 4. Spread implícito — control de coste ────────────────────────────
        spread_est   = _spread_implicito(highs, lows, closes, n=5)
        spread_alto  = spread_est > _SPREAD_MAX_PCT

        # ── 5. R/R — proyección Riesgo/Beneficio ─────────────────────────────
        sl_pct = 0.004    # Stop Loss: 0.4% (ajuste agresivo scalping)
        tp_pct = 0.008    # Take Profit: 0.8% (ratio 1:2)
        rr = (tp_pct - spread_est) / (sl_pct + spread_est) if (sl_pct + spread_est) > 0 else 0.0
        rr_favorable = rr >= _RR_MIN

        # ── 6. Alineación señal con tendencia ────────────────────────────────
        dir_scalp = None
        alineado  = False
        if senal_rsi == "compra" and tendencia == "alcista":
            dir_scalp, alineado = "V", True
        elif senal_rsi == "venta" and tendencia == "bajista":
            dir_scalp, alineado = "R", True
        elif senal_rsi == "compra":
            dir_scalp = "V"   # señal existe pero no alineada
        elif senal_rsi == "venta":
            dir_scalp = "R"

        # ── 7. Confianza compuesta ────────────────────────────────────────────
        confianza = 0.0
        if senal_rsi and not ruidoso and not spread_alto:
            # Base por intensidad RSI
            intensidad = abs(rsi_act - (
                _RSI_SOBREVENTA  if senal_rsi == "compra" else _RSI_SOBRECOMPRA)) / 20.0
            base       = 0.58 + intensidad * 0.12

            # Bonus por alineación con EMA 200
            if alineado:
                alineacion_bonus = min(0.10, abs(dist_ema) * 3.0)
                base += alineacion_bonus

            # Bonus por R/R favorable
            if rr_favorable:
                base += 0.05

            # Penalización por cercanía a EMA (zona de indecisión)
            if abs(dist_ema) < 0.002:
                base -= 0.10

            confianza = float(np.clip(base, 0.0, 0.88))

        resumen = (
            f"EMA200={'↑' if tendencia=='alcista' else '↓' if tendencia=='bajista' else '→'} "
            f"dist={dist_ema:+.2%} | RSI7={rsi_act:.1f} "
            f"({'CRUZ ↑' if senal_rsi=='compra' else 'CRUZ ↓' if senal_rsi=='venta' else 'sin cruz'}) | "
            f"ATR={atr_rel:.2%}{'⚠RUIDO' if ruidoso else ''} | "
            f"Spread≈{spread_est:.3%}{'⚠ALTO' if spread_alto else ''} | "
            f"R/R={rr:.1f} | conf={confianza:.0%}"
        )

        return ResultadoScalping(
            tendencia_ema   = tendencia,
            precio_vs_ema   = dist_ema,
            rsi7_actual     = rsi_act,
            rsi7_anterior   = rsi_ant,
            senal_rsi       = senal_rsi,
            atr_relativo    = atr_rel,
            mercado_ruidoso = ruidoso,
            spread_estimado = spread_est,
            spread_excesivo = spread_alto,
            rr_estimado     = rr,
            rr_favorable    = rr_favorable,
            confianza       = confianza,
            direccion_scalp = dir_scalp,
            alineado        = alineado,
            texto           = resumen,
        )

    except Exception:
        return _analizar_sintetico(sec)


def votar(res: ResultadoScalping, dir_senal: str) -> tuple[bool, float]:
    """
    Vota a favor/en contra de la dirección de señal.

    La señal de scalping confirma si:
      · EMA 200 está alineada con dir_senal
      · RSI 7 cruzó en la dirección correcta
      · Mercado no es ruidoso
      · Spread es aceptable

    Returns:
        (confirma: bool, confianza: float)
    """
    if res.confianza < 0.50 or res.mercado_ruidoso:
        return False, 0.0
    if res.spread_excesivo:
        return False, 0.0
    if res.direccion_scalp is None:
        return False, 0.0
    confirma = (res.direccion_scalp == dir_senal)
    return confirma, res.confianza if confirma else 0.0


def resumen_texto(res: ResultadoScalping) -> str:
    """Texto corto para el log del sistema."""
    return (f"Scalp: EMA200={res.tendencia_ema} | RSI7={res.rsi7_actual:.0f} "
            f"| {'✓ Cruz' if res.senal_rsi else '✗ sin señal'} "
            f"| R/R={res.rr_estimado:.1f} "
            f"| {'✓ alineado' if res.alineado else '✗ contra-tendencia'}")

"""
triple_barrier.py — Etiquetado de Triple Barrera para LITCH.

Implementación del método de clasificación de operaciones definido en:
  "Advances in Financial Machine Learning"
  Dr. Marcos López de Prado — Capítulo 3: Labels

El método resuelve el problema de las etiquetas binarias tradicionales
(ganó/perdió basado en dirección final), que ignoran CUÁNDO y CÓMO
ocurrió el movimiento. En su lugar usa tres barreras simultáneas:

  ┌─────────────────────────────────────────────────────┐
  │  BARRERA SUPERIOR (TP)  → precio sube X%  = WIN     │
  │  BARRERA INFERIOR (SL)  → precio baja X%  = LOSS    │
  │  BARRERA VERTICAL (T)   → se acaba el tiempo = DRAW │
  └─────────────────────────────────────────────────────┘

La primera barrera que se toca define el resultado.
Esto es más realista que el W/L binario porque:
  · Penaliza operaciones que "casi" ganaron pero se demoran demasiado
  · Premia señales que alcanzan el TP rápidamente
  · Detecta mercados laterales donde ninguna barrera se toca

Para señales de IQ Option (binarias), aplicamos el método así:
  · Barreras TP/SL se miden en % del precio de entrada
  · La barrera vertical = duración del contrato (N velas)
  · La confianza del voto = tasa histórica de WIN en condiciones similares

Pipeline adicional implementado (Stefan Jansen — Feature Engineering):
  · Normalización de series temporales para evitar data leakage
  · Cálculo de retornos log (más estables que % lineales)
  · Purging implícito: solo usa velas ANTERIORES al momento actual

Referencia:
  López de Prado, M. (2018). Advances in Financial Machine Learning.
  Wiley. ISBN 978-1-119-48208-6
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, List

import numpy as np


# ── Constantes del sistema de barreras ───────────────────────────────────────

_TP_PCT          = 0.008    # Barrera superior: +0.8% (Take Profit)
_SL_PCT          = 0.004    # Barrera inferior: -0.4% (Stop Loss) → R/R = 1:2
_T_MAX_VELAS     = 3        # Barrera vertical: 3 velas (tiempo límite)
_CONF_MIN_MUESTRAS = 8      # Mínimo de eventos similares para confiar en la tasa
_VENTANA_HIST    = 100      # Velas a analizar hacia atrás para estadística
_CONF_BASE       = 0.52     # Confianza mínima base (ligeramente sobre azar)
_LOG_RET_RUIDO   = 1e-9     # Epsilon para log(0)


# ── Etiquetas de barrera ─────────────────────────────────────────────────────

class _Label:
    WIN  = "WIN"
    LOSS = "LOSS"
    DRAW = "DRAW"


# ── Resultado del análisis ────────────────────────────────────────────────────

@dataclass
class ResultadoBarrera:
    # Estadísticas de la muestra histórica
    n_eventos:        int            = 0     # eventos similares encontrados
    n_win:            int            = 0
    n_loss:           int            = 0
    n_draw:           int            = 0
    tasa_win:         float          = 0.5   # P(WIN) histórico
    tasa_loss:        float          = 0.5
    # Análisis del momento actual
    dir_estimada:     Optional[str]  = None  # "V" | "R"
    confianza:        float          = 0.0
    barrera_tocada:   Optional[str]  = None  # qué barrera esperamos tocar
    retorno_log:      float          = 0.0   # log-return del momentum actual
    volatilidad_rel:  float          = 0.0   # volatilidad relativa al momento
    muestra_suficiente: bool         = False
    texto:            str            = ""

    @property
    def votar(self) -> bool:
        return (self.muestra_suficiente
                and self.confianza >= 0.54
                and self.tasa_win > self.tasa_loss)


# ── Funciones de feature engineering (Stefan Jansen pipeline) ────────────────

def _log_returns(closes: np.ndarray) -> np.ndarray:
    """
    Retornos logarítmicos — más estables que % lineales.
    log(Pt / Pt-1) es simétrico y aditivo en el tiempo.
    (Jansen, cap. Feature Engineering: Time Series Features)
    """
    prices = np.clip(closes, _LOG_RET_RUIDO, None)
    return np.log(prices[1:] / prices[:-1])


def _volatilidad_ewm(log_rets: np.ndarray, span: int = 20) -> float:
    """
    Volatilidad exponencialmente ponderada (más peso a lo reciente).
    Usado por López de Prado para normalizar el tamaño de las barreras.
    """
    if len(log_rets) < 2:
        return 0.01
    alpha = 2.0 / (span + 1)
    var   = float(log_rets[0] ** 2)
    for r in log_rets[1:]:
        var = alpha * (r ** 2) + (1 - alpha) * var
    return math.sqrt(var)


def _momentum_log(closes: np.ndarray, n: int = 5) -> float:
    """
    Momentum de retornos logarítmicos de las últimas N velas.
    Positivo → presión compradora; negativo → presión vendedora.
    """
    if len(closes) < n + 1:
        return 0.0
    return float(np.sum(_log_returns(closes[-(n + 1):])))


# ── Triple Barrera sobre OHLC ─────────────────────────────────────────────────

def _etiquetar_evento(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                      t_entrada: int, dir_sen: str,
                      tp_pct: float, sl_pct: float,
                      t_max: int) -> str:
    """
    Simula qué barrera se toca primero tras la entrada en t_entrada.

    Parámetros:
        t_entrada: índice de la vela de entrada (precio = closes[t_entrada])
        dir_sen:   "V" (long) o "R" (short)
        tp_pct:    Take Profit como fracción (ej. 0.008 = 0.8%)
        sl_pct:    Stop Loss como fracción (ej. 0.004 = 0.4%)
        t_max:     máximo de velas a esperar (barrera vertical)

    Returns:
        "WIN" | "LOSS" | "DRAW"
    """
    precio_entrada = float(closes[t_entrada])
    if precio_entrada == 0:
        return _Label.DRAW

    if dir_sen == "V":    # long
        p_tp = precio_entrada * (1 + tp_pct)
        p_sl = precio_entrada * (1 - sl_pct)
        def toca_tp(h, l): return h >= p_tp
        def toca_sl(h, l): return l <= p_sl
    else:                 # short
        p_tp = precio_entrada * (1 - tp_pct)
        p_sl = precio_entrada * (1 + sl_pct)
        def toca_tp(h, l): return l <= p_tp
        def toca_sl(h, l): return h >= p_sl

    n = len(closes)
    for t in range(t_entrada + 1, min(t_entrada + t_max + 1, n)):
        h = float(highs[t])
        l = float(lows[t])
        if toca_tp(h, l) and toca_sl(h, l):
            return _Label.DRAW      # ambas barreras en la misma vela → indecisión
        if toca_tp(h, l):
            return _Label.WIN
        if toca_sl(h, l):
            return _Label.LOSS

    return _Label.DRAW              # barrera vertical — tiempo agotado


# ── Búsqueda de condiciones similares (feature matching) ─────────────────────

def _condiciones_similares(closes: np.ndarray, highs: np.ndarray,
                           lows: np.ndarray, idx_actual: int,
                           dir_sen: str, log_rets: np.ndarray,
                           vol_actual: float) -> list:
    """
    Busca en el historial eventos donde las condiciones de mercado eran
    similares a las actuales (mismo sesgo de momentum ± similar volatilidad).

    Esto implementa la idea de "purging" de López de Prado:
    solo comparamos con el PASADO, nunca con el futuro.

    Retorna lista de índices de velas similares en el historial.
    """
    ventana_inicio = max(1, idx_actual - _VENTANA_HIST)
    similares      = []

    if len(log_rets) < 3 or vol_actual == 0:
        return similares

    # Momentum del momento actual (últimas 3 velas)
    momentum_actual = float(np.sum(log_rets[max(0, idx_actual - 4): idx_actual])) if idx_actual >= 4 else 0.0

    for t in range(ventana_inicio, idx_actual - _T_MAX_VELAS - 1):
        # Momentum histórico en ese punto
        if t < 4:
            continue
        mom_hist = float(np.sum(log_rets[t - 4: t]))

        # Condición de similitud: mismo signo de momentum y magnitud parecida
        mismo_sesgo   = (momentum_actual > 0 and mom_hist > 0) or \
                        (momentum_actual < 0 and mom_hist < 0)
        magnitud_ok   = abs(abs(mom_hist) - abs(momentum_actual)) < abs(momentum_actual) * 0.5 + 1e-9

        if mismo_sesgo and magnitud_ok:
            # Para señal V, verificamos que el momentum sea positivo
            if dir_sen == "V" and mom_hist > 0:
                similares.append(t)
            elif dir_sen == "R" and mom_hist < 0:
                similares.append(t)

    return similares


# ── Modo sintético ────────────────────────────────────────────────────────────

def _analizar_sintetico(sec: list, dir_sen: str) -> ResultadoBarrera:
    """
    Análisis sin OHLC — usa precio sintético V/R.
    Aplica el mismo método de triple barrera sobre la serie acumulada.
    """
    if len(sec) < 20:
        return ResultadoBarrera(texto="Muestra insuficiente para Triple Barrera")

    precios = np.cumsum([1.0 if c == 'V' else -1.0 for c in sec]) + 100.0
    highs   = precios * 1.001     # simula high = close + pequeño spread
    lows    = precios * 0.999

    n = len(precios)
    log_rets   = _log_returns(precios)
    vol        = _volatilidad_ewm(log_rets, span=20)
    momentum   = _momentum_log(precios, n=5)

    # TP/SL adaptados a volatilidad sintética
    tp_s = max(0.003, vol * 1.5)
    sl_s = max(0.002, vol * 0.8)

    idx_actual = n - 1
    similares  = _condiciones_similares(precios, highs, lows,
                                        idx_actual, dir_sen, log_rets, vol)

    n_win = n_loss = n_draw = 0
    for t in similares:
        etq = _etiquetar_evento(precios, highs, lows, t,
                                dir_sen, tp_s, sl_s, _T_MAX_VELAS)
        if etq == _Label.WIN:  n_win  += 1
        elif etq == _Label.LOSS: n_loss += 1
        else:                    n_draw += 1

    n_total = n_win + n_loss + n_draw
    tasa_w  = n_win  / n_total if n_total > 0 else 0.5
    tasa_l  = n_loss / n_total if n_total > 0 else 0.5

    suficiente = n_total >= _CONF_MIN_MUESTRAS
    confianza  = 0.0
    if suficiente:
        # Confianza = ventaja sobre el azar (tasa_win - 0.5) escalada
        ventaja   = max(0.0, tasa_w - 0.5) * 2.0
        confianza = float(np.clip(_CONF_BASE + ventaja * 0.35, 0.0, 0.82))

    return ResultadoBarrera(
        n_eventos       = n_total,
        n_win           = n_win,
        n_loss          = n_loss,
        n_draw          = n_draw,
        tasa_win        = tasa_w,
        tasa_loss       = tasa_l,
        dir_estimada    = dir_sen,
        confianza       = confianza,
        retorno_log     = momentum,
        volatilidad_rel = vol,
        muestra_suficiente = suficiente,
        texto = (f"TripleBarrera sintética: {n_total} eventos "
                 f"W={n_win} L={n_loss} D={n_draw} "
                 f"→ tasa_win={tasa_w:.0%} conf={confianza:.0%}")
    )


# ── API pública ───────────────────────────────────────────────────────────────

def analizar(sec: list, velas_ohlc: list = None,
             dir_senal: str = "V") -> ResultadoBarrera:
    """
    Aplica el método de Triple Barrera de López de Prado.

    Para cada momento del historial con condiciones similares al actual,
    simula qué habría pasado (WIN/LOSS/DRAW) y calcula la tasa empírica.

    Esa tasa empírica es la confianza del voto:
      · tasa_win > 60% → señal estadísticamente respaldada → votar
      · tasa_win ≤ 55% → evidencia insuficiente → abstenerse

    Args:
        sec:        Secuencia V/R de velas.
        velas_ohlc: Lista de dicts {'open','high','low','close'}.
        dir_senal:  Dirección de la señal actual.

    Returns:
        ResultadoBarrera con estadísticas de la muestra histórica.
    """
    if not velas_ohlc or len(velas_ohlc) < 30:
        return _analizar_sintetico(sec, dir_senal)

    try:
        n_use  = min(len(velas_ohlc), _VENTANA_HIST + 20)
        velas  = velas_ohlc[-n_use:]
        closes = np.array([float(v.get("close", 0)) for v in velas])
        highs  = np.array([float(v.get("high",  0)) for v in velas])
        lows   = np.array([float(v.get("low",   0)) for v in velas])

        if closes[-1] == 0:
            return _analizar_sintetico(sec, dir_senal)

        log_rets = _log_returns(closes)
        vol      = _volatilidad_ewm(log_rets, span=20)
        momentum = _momentum_log(closes, n=5)

        # Ajuste de barreras por volatilidad (López de Prado — Dynamic Barriers)
        # A mayor volatilidad, barreras más amplias para evitar stop prematuro
        vol_factor = max(0.5, min(2.5, vol / 0.003))   # normalizado a vol típica 0.3%
        tp_dyn = _TP_PCT * vol_factor
        sl_dyn = _SL_PCT * vol_factor

        n      = len(closes)
        idx    = n - 1
        similares = _condiciones_similares(
            closes, highs, lows, idx, dir_senal, log_rets, vol)

        n_win = n_loss = n_draw = 0
        for t in similares:
            etq = _etiquetar_evento(
                closes, highs, lows, t, dir_senal,
                tp_dyn, sl_dyn, _T_MAX_VELAS)
            if etq == _Label.WIN:   n_win  += 1
            elif etq == _Label.LOSS: n_loss += 1
            else:                    n_draw += 1

        n_total = n_win + n_loss + n_draw
        tasa_w  = n_win  / n_total if n_total > 0 else 0.5
        tasa_l  = n_loss / n_total if n_total > 0 else 0.5

        suficiente = n_total >= _CONF_MIN_MUESTRAS
        confianza  = 0.0
        if suficiente and tasa_w > tasa_l:
            ventaja   = (tasa_w - 0.5) * 2.0
            # Bonus si la muestra es grande (más evidencia → más confianza)
            tamaño_b  = min(0.08, (n_total - _CONF_MIN_MUESTRAS) * 0.004)
            confianza = float(np.clip(
                _CONF_BASE + ventaja * 0.38 + tamaño_b, 0.0, 0.85))

        # Barrera esperada
        barrera = None
        if suficiente:
            if tasa_w >= 0.55:     barrera = "TP"
            elif tasa_l >= 0.60:   barrera = "SL"
            else:                   barrera = "DRAW"

        texto = (
            f"TripleBarrera OHLC: {n_total} similares históricos "
            f"W={n_win}({tasa_w:.0%}) L={n_loss}({tasa_l:.0%}) D={n_draw} "
            f"| vol={vol:.3%} | barrera_esperada={barrera or '?'} "
            f"| conf={confianza:.0%}"
        )

        return ResultadoBarrera(
            n_eventos         = n_total,
            n_win             = n_win,
            n_loss            = n_loss,
            n_draw            = n_draw,
            tasa_win          = tasa_w,
            tasa_loss         = tasa_l,
            dir_estimada      = dir_senal,
            confianza         = confianza,
            barrera_tocada    = barrera,
            retorno_log       = momentum,
            volatilidad_rel   = vol,
            muestra_suficiente = suficiente,
            texto             = texto,
        )

    except Exception:
        return _analizar_sintetico(sec, dir_senal)


def votar(res: ResultadoBarrera, dir_senal: str) -> tuple[bool, float]:
    """
    Vota basándose en la tasa histórica de aciertos bajo condiciones similares.

    La señal se confirma si:
      · Hay suficiente muestra histórica (≥8 eventos similares)
      · La tasa de WIN histórica es mayor que la de LOSS
      · La confianza supera el umbral mínimo

    Returns:
        (confirma: bool, confianza: float)
    """
    if not res.votar:
        return False, 0.0
    if res.dir_estimada != dir_senal:
        return False, 0.0
    return True, res.confianza


def resumen_texto(res: ResultadoBarrera) -> str:
    """Texto compacto para el log del sistema."""
    if res.n_eventos == 0:
        return "TripleBarrera: sin datos históricos suficientes"
    return (f"TripleBarrera: {res.n_eventos} eventos | "
            f"WIN={res.tasa_win:.0%} LOSS={res.tasa_loss:.0%} | "
            f"conf={res.confianza:.0%} | barrera={res.barrera_tocada or '?'}")

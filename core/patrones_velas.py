"""
patrones_velas.py — Reconocimiento profesional de patrones de velas japonesas.

Detecta 20 patrones clásicos y proporciona un voto al motor de consenso de LITCH.

Trabaja en dos modos:
  · OHLC real (cuando el broker entrega datos): detección precisa.
  · Sintético (serie V/R): patrones basados en secuencia de dirección.

Patrones soportados (categorías):
  Reversión alcista  : Hammer, Inverted Hammer, Bullish Engulfing,
                       Morning Star, Bullish Harami, Tweezer Bottom,
                       Three White Soldiers, Dragonfly Doji, Marubozu Verde.
  Reversión bajista  : Shooting Star, Hanging Man, Bearish Engulfing,
                       Evening Star, Bearish Harami, Tweezer Top,
                       Three Black Crows, Gravestone Doji, Marubozu Roja.
  Indecisión / Doji  : Doji Estándar, Long-Legged Doji.

Referencia bibliográfica:
  Nison S. (1991). Japanese Candlestick Charting Techniques.
  Murphy J. (1999). Technical Analysis of the Financial Markets.
  Bulkowski T. (2008). Encyclopedia of Candlestick Charts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ── Constantes de tolerancia ──────────────────────────────────────────────────

_DOJI_RATIO    = 0.08   # cuerpo / rango total ≤ 8% → Doji
_SHADOW_RATIO  = 0.60   # sombra / rango total ≥ 60% → Pinbar/Hammer/Star
_ENGULF_RATIO  = 1.05   # cuerpo nuevo ≥ 105% del anterior → Engulfing confirmado
_MARUBOZU_MIN  = 0.75   # cuerpo / rango total ≥ 75% → Marubozu


# ── Estructura de resultado ───────────────────────────────────────────────────

@dataclass
class PatronVela:
    nombre:     str
    direccion:  Optional[str]   # "V" (alcista), "R" (bajista), None (indecisión)
    confianza:  float           # [0, 1]
    descripcion: str = ""
    es_doji:    bool = False
    fuerza:     str = "media"   # "baja" | "media" | "alta"

    @property
    def votar(self) -> bool:
        return self.direccion is not None and self.confianza >= 0.55

    def __str__(self):
        if not self.direccion:
            return f"{self.nombre} (Indecisión {self.confianza:.0%})"
        ico = "▲" if self.direccion == "V" else "▼"
        return f"{ico} {self.nombre} ({self.confianza:.0%} {self.fuerza})"


_PATRON_NEUTRO = PatronVela(
    nombre="Sin patrón", direccion=None, confianza=0.0,
    descripcion="No se detectó ningún patrón de velas reconocible.")


# ── Primitivas OHLC ──────────────────────────────────────────────────────────

def _cuerpo(o, c):   return abs(c - o)
def _rango(h, l):    return max(h - l, 1e-9)
def _somb_sup(o, c, h): return h - max(o, c)
def _somb_inf(o, c, l): return min(o, c) - l
def _es_verde(o, c): return c > o
def _es_roja(o, c):  return c < o
def _cuerpo_pct(o, c, h, l): return _cuerpo(o, c) / _rango(h, l)
def _somb_sup_pct(o, c, h, l): return _somb_sup(o, c, h) / _rango(h, l)
def _somb_inf_pct(o, c, h, l): return _somb_inf(o, c, l) / _rango(h, l)


# ── Detección de patrones individuales ───────────────────────────────────────

def _es_doji(o, c, h, l) -> bool:
    return _cuerpo_pct(o, c, h, l) <= _DOJI_RATIO

def _es_marubozu(o, c, h, l) -> bool:
    return (_cuerpo_pct(o, c, h, l) >= _MARUBOZU_MIN and
            _somb_sup_pct(o, c, h, l) < 0.05 and
            _somb_inf_pct(o, c, h, l) < 0.05)


def _analizar_1(o, c, h, l) -> Optional[PatronVela]:
    """Patrones de 1 vela."""
    cuerpo_r = _cuerpo_pct(o, c, h, l)
    somb_s   = _somb_sup_pct(o, c, h, l)
    somb_i   = _somb_inf_pct(o, c, h, l)
    verde    = _es_verde(o, c)

    # Doji estándar
    if cuerpo_r <= _DOJI_RATIO:
        if somb_s > 0.35 and somb_i > 0.35:
            return PatronVela("Long-Legged Doji", None, 0.55,
                              "Cuerpo mínimo, sombras largas arriba y abajo — máxima indecisión.",
                              es_doji=True, fuerza="media")
        if somb_i >= 0.60 and somb_s < 0.10:
            return PatronVela("Dragonfly Doji", "V", 0.65,
                              "Sombra inferior muy larga: compradores rechazaron los mínimos.",
                              es_doji=True, fuerza="alta")
        if somb_s >= 0.60 and somb_i < 0.10:
            return PatronVela("Gravestone Doji", "R", 0.65,
                              "Sombra superior muy larga: vendedores rechazaron los máximos.",
                              es_doji=True, fuerza="alta")
        return PatronVela("Doji Estándar", None, 0.52,
                          "Precio de apertura y cierre casi iguales — sin consenso.", es_doji=True)

    # Hammer / Hanging Man (cuerpo pequeño arriba, sombra inferior larga)
    if somb_i >= _SHADOW_RATIO and cuerpo_r < 0.25 and somb_s < 0.10:
        if verde:
            return PatronVela("Hammer", "V", 0.72,
                              "Compradores absorbieron toda la presión bajista — señal de reversa.",
                              fuerza="alta")
        else:
            return PatronVela("Hanging Man", "R", 0.63,
                              "Aunque verde, la sombra inferior tras subida puede señalar techo.",
                              fuerza="media")

    # Inverted Hammer / Shooting Star (cuerpo pequeño abajo, sombra superior larga)
    if somb_s >= _SHADOW_RATIO and cuerpo_r < 0.25 and somb_i < 0.10:
        if verde:
            return PatronVela("Shooting Star", "R", 0.68,
                              "Intentó subir pero los vendedores devolvieron el precio — techo potencial.",
                              fuerza="alta")
        else:
            return PatronVela("Inverted Hammer", "V", 0.60,
                              "Presión compradora rechazó los máximos — posible suelo.",
                              fuerza="media")

    # Marubozu
    if _es_marubozu(o, c, h, l):
        if verde:
            return PatronVela("Marubozu Verde", "V", 0.78,
                              "Compradores dominaron toda la vela sin sombras — tendencia fuerte.",
                              fuerza="alta")
        else:
            return PatronVela("Marubozu Roja", "R", 0.78,
                              "Vendedores dominaron toda la vela sin sombras — tendencia fuerte.",
                              fuerza="alta")

    return None


def _analizar_2(o1, c1, h1, l1, o2, c2, h2, l2) -> Optional[PatronVela]:
    """Patrones de 2 velas."""
    verde1 = _es_verde(o1, c1)
    verde2 = _es_verde(o2, c2)
    cuerpo1 = _cuerpo(o1, c1)
    cuerpo2 = _cuerpo(o2, c2)

    # Bullish Engulfing
    if not verde1 and verde2:
        if (c2 >= o1 and o2 <= c1 and cuerpo2 >= cuerpo1 * _ENGULF_RATIO):
            confianza = min(0.85, 0.70 + (cuerpo2 / (cuerpo1 + 1e-9) - 1.0) * 0.10)
            return PatronVela("Bullish Engulfing", "V", confianza,
                              "Vela verde engloba completamente la roja anterior — inversión fuerte.",
                              fuerza="alta")

    # Bearish Engulfing
    if verde1 and not verde2:
        if (o2 >= c1 and c2 <= o1 and cuerpo2 >= cuerpo1 * _ENGULF_RATIO):
            confianza = min(0.85, 0.70 + (cuerpo2 / (cuerpo1 + 1e-9) - 1.0) * 0.10)
            return PatronVela("Bearish Engulfing", "R", confianza,
                              "Vela roja engloba completamente la verde anterior — inversión fuerte.",
                              fuerza="alta")

    # Bullish Harami
    if not verde1 and verde2:
        if (o2 >= c1 and c2 <= o1 and cuerpo2 < cuerpo1 * 0.50):
            return PatronVela("Bullish Harami", "V", 0.58,
                              "Vela verde pequeña dentro del cuerpo rojo — posible cambio de dirección.",
                              fuerza="baja")

    # Bearish Harami
    if verde1 and not verde2:
        if (c2 >= o1 and o2 <= c1 and cuerpo2 < cuerpo1 * 0.50):
            return PatronVela("Bearish Harami", "R", 0.58,
                              "Vela roja pequeña dentro del cuerpo verde — posible cambio de dirección.",
                              fuerza="baja")

    # Tweezer Top
    if verde1 and not verde2:
        if abs(h1 - h2) / _rango(max(h1, h2), min(l1, l2)) < 0.03:
            return PatronVela("Tweezer Top", "R", 0.62,
                              "Dos velas con máximos iguales — los vendedores defienden ese nivel.",
                              fuerza="media")

    # Tweezer Bottom
    if not verde1 and verde2:
        if abs(l1 - l2) / _rango(max(h1, h2), min(l1, l2)) < 0.03:
            return PatronVela("Tweezer Bottom", "V", 0.62,
                              "Dos velas con mínimos iguales — los compradores defienden ese nivel.",
                              fuerza="media")

    return None


def _analizar_3(v1, v2, v3) -> Optional[PatronVela]:
    """
    Patrones de 3 velas. Cada vx es (open, close, high, low).
    """
    o1, c1, h1, l1 = v1
    o2, c2, h2, l2 = v2
    o3, c3, h3, l3 = v3
    verde1 = _es_verde(o1, c1)
    verde2 = _es_verde(o2, c2)
    verde3 = _es_verde(o3, c3)

    # Three White Soldiers
    if verde1 and verde2 and verde3:
        if (c1 > c2 or c2 > c3):
            pass  # cierres decrecientes, no es soldiers
        elif c3 > c2 > c1 and o2 > o1 and o3 > o2:
            cuerpo_avg = ((_cuerpo(o1,c1) + _cuerpo(o2,c2) + _cuerpo(o3,c3)) / 3)
            rango_avg  = ((_rango(h1,l1) + _rango(h2,l2) + _rango(h3,l3)) / 3)
            if cuerpo_avg / rango_avg > 0.55:
                return PatronVela("Three White Soldiers", "V", 0.82,
                                  "Tres velas verdes consecutivas con cierres al alza — tendencia alcista poderosa.",
                                  fuerza="alta")

    # Three Black Crows
    if not verde1 and not verde2 and not verde3:
        if c3 < c2 < c1 and o2 < o1 and o3 < o2:
            cuerpo_avg = ((_cuerpo(o1,c1) + _cuerpo(o2,c2) + _cuerpo(o3,c3)) / 3)
            rango_avg  = ((_rango(h1,l1) + _rango(h2,l2) + _rango(h3,l3)) / 3)
            if cuerpo_avg / rango_avg > 0.55:
                return PatronVela("Three Black Crows", "R", 0.82,
                                  "Tres velas rojas consecutivas con cierres a la baja — tendencia bajista poderosa.",
                                  fuerza="alta")

    # Morning Star (R grande, doji/pequeña, V grande)
    if (not verde1 and _cuerpo_pct(o1,c1,h1,l1) > 0.45 and
            _cuerpo_pct(o2,c2,h2,l2) < 0.30 and
            verde3 and _cuerpo_pct(o3,c3,h3,l3) > 0.40 and
            c3 > (o1 + c1) / 2):
        return PatronVela("Morning Star", "V", 0.80,
                          "Vela roja, estrella pequeña, vela verde — inversión clásica desde mínimos.",
                          fuerza="alta")

    # Evening Star (V grande, doji/pequeña, R grande)
    if (verde1 and _cuerpo_pct(o1,c1,h1,l1) > 0.45 and
            _cuerpo_pct(o2,c2,h2,l2) < 0.30 and
            not verde3 and _cuerpo_pct(o3,c3,h3,l3) > 0.40 and
            c3 < (o1 + c1) / 2):
        return PatronVela("Evening Star", "R", 0.80,
                          "Vela verde, estrella pequeña, vela roja — inversión clásica desde máximos.",
                          fuerza="alta")

    return None


# ── Modo sintético (solo serie V/R) ──────────────────────────────────────────

def _analizar_sintetico(sec: list) -> PatronVela:
    """
    Detecta patrones de secuencia cuando no hay datos OHLC reales.
    Trabaja con la serie V/R directamente.
    """
    if len(sec) < 3:
        return _PATRON_NEUTRO

    rec = sec[-10:]  # últimas 10 velas

    # Three White Soldiers / Three Black Crows
    if rec[-3:] == ['V', 'V', 'V']:
        return PatronVela("Three White Soldiers*", "V", 0.68,
                          "Tres velas verdes consecutivas — impulso alcista sostenido.", fuerza="alta")
    if rec[-3:] == ['R', 'R', 'R']:
        return PatronVela("Three Black Crows*", "R", 0.68,
                          "Tres velas rojas consecutivas — impulso bajista sostenido.", fuerza="alta")

    # Engulfing sintético: racha larga en una dirección seguida de vela contraria
    v_ant  = [c for c in rec[-5:-1]]
    ultima = rec[-1]

    racha_r = sum(1 for c in v_ant if c == 'R')
    racha_v = sum(1 for c in v_ant if c == 'V')

    if racha_r >= 3 and ultima == 'V':
        confianza = min(0.75, 0.58 + racha_r * 0.04)
        return PatronVela("Bullish Engulfing*", "V", confianza,
                          f"Tras {racha_r} velas bajistas, aparece una alcista — posible giro.",
                          fuerza="alta" if racha_r >= 4 else "media")

    if racha_v >= 3 and ultima == 'R':
        confianza = min(0.75, 0.58 + racha_v * 0.04)
        return PatronVela("Bearish Engulfing*", "R", confianza,
                          f"Tras {racha_v} velas alcistas, aparece una bajista — posible giro.",
                          fuerza="alta" if racha_v >= 4 else "media")

    # Doji sintético: alternancia alta
    alternancia = sum(1 for i in range(1, len(rec))
                      if rec[i] != rec[i - 1])
    if alternancia >= len(rec) - 2:
        return PatronVela("Doji Estándar*", None, 0.52,
                          "Alta alternancia V/R — mercado indeciso sin tendencia clara.", es_doji=True)

    # Continuación de tendencia
    mayoria = sum(1 for c in rec[-5:] if c == 'V')
    if mayoria >= 4:
        return PatronVela("Impulso Alcista", "V", 0.55,
                          f"Mayoría alcista reciente ({mayoria}/5) — continuación probable.", fuerza="baja")
    if mayoria <= 1:
        return PatronVela("Impulso Bajista", "R", 0.55,
                          f"Mayoría bajista reciente ({5 - mayoria}/5) — continuación probable.", fuerza="baja")

    return _PATRON_NEUTRO


# ── API pública principal ─────────────────────────────────────────────────────

def analizar(sec: list, velas_ohlc: list = None) -> PatronVela:
    """
    Detecta el patrón de velas más relevante en la señal actual.

    Args:
        sec:        Lista de 'V'/'R' (secuencia de velas).
        velas_ohlc: Lista de dicts {'open', 'close', 'high', 'low'} en orden
                    cronológico (la última vela = [-1]). Si None, usa modo sintético.

    Returns:
        PatronVela con nombre, dirección y confianza.
    """
    # Modo sintético si no hay OHLC
    if not velas_ohlc or len(velas_ohlc) < 3:
        return _analizar_sintetico(sec)

    candles = velas_ohlc[-5:]   # máximo 5 velas para los patrones

    try:
        # Extraer OHLC de las últimas velas
        def _ohlc(v):
            return (float(v.get("open",0)), float(v.get("close",0)),
                    float(v.get("high",0)),  float(v.get("low",0)))

        # Intentar patrón de 3 velas primero (más fiable)
        if len(candles) >= 3:
            p3 = _analizar_3(_ohlc(candles[-3]), _ohlc(candles[-2]), _ohlc(candles[-1]))
            if p3:
                return p3

        # Luego 2 velas
        if len(candles) >= 2:
            o1,c1,h1,l1 = _ohlc(candles[-2])
            o2,c2,h2,l2 = _ohlc(candles[-1])
            p2 = _analizar_2(o1,c1,h1,l1, o2,c2,h2,l2)
            if p2:
                return p2

        # Finalmente 1 vela
        o,c,h,l = _ohlc(candles[-1])
        p1 = _analizar_1(o, c, h, l)
        if p1:
            return p1

    except Exception:
        pass

    # Fallback sintético
    return _analizar_sintetico(sec)


def votar(patron: PatronVela, dir_senal: str) -> tuple[bool, float]:
    """
    Compara el patrón detectado con la dirección de la señal principal.

    Returns:
        (confirma: bool, confianza: float)
        confirma=True si el patrón apoya la dirección de la señal.
    """
    if patron.es_doji or patron.direccion is None:
        return False, 0.0
    if not patron.votar:
        return False, 0.0
    confirma = (patron.direccion == dir_senal)
    return confirma, patron.confianza if confirma else 0.0


def descripcion_larga(patron: PatronVela) -> str:
    """Texto explicativo completo del patrón para logs y UI."""
    if patron.direccion is None:
        return f"🟡 {patron.nombre}: {patron.descripcion}"
    ico = "🟢" if patron.direccion == "V" else "🔴"
    nivel = {"baja": "⚡", "media": "⚡⚡", "alta": "⚡⚡⚡"}.get(patron.fuerza, "⚡")
    return f"{ico} {patron.nombre} {nivel}: {patron.descripcion}"

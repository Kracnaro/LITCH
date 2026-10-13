"""
soporte_resistencia.py — Detección automática de Soporte y Resistencia para LITCH.

Detecta niveles clave de precio donde el mercado ha rebotado en el pasado,
y evalúa si la señal actual está en una posición favorable respecto a esos niveles.

Algoritmos implementados:
  1. Pivot Points clásicos (PP, S1-S3, R1-R3)
  2. Niveles por densidad de precio (zonas con más toques = más fuertes)
  3. Máximos y mínimos significativos de las últimas N velas
  4. Fibonacci automático entre el máximo y mínimo recientes

Proporciona:
  · Nivel más cercano al precio actual
  · Distancia en % al nivel
  · Si el precio está en zona de rebote probable
  · Dirección del rebote esperado (del soporte → V, de la resistencia → R)
  · Confianza del nivel según número de toques

Referencia:
  De Mark T. (1994). The New Science of Technical Analysis.
  Fischer R. (1993). Fibonacci Applications and Strategies for Traders.
  Murphy J. (1999). Technical Analysis of the Financial Markets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ── Constantes ────────────────────────────────────────────────────────────────

_ZONA_TOQUES  = 3       # mínimo de toques para que una zona sea "fuerte"
_PROX_PCT     = 0.015   # ≤ 1.5% del precio = "en la zona"
_N_RECIENTES  = 50      # velas recientes a analizar
_FIB_NIVELES  = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000]


# ── Estructura de nivel ───────────────────────────────────────────────────────

@dataclass
class Nivel:
    precio:     float
    tipo:       str     # "soporte" | "resistencia" | "pivot" | "fibonacci"
    toques:     int     = 1
    fuerza:     float   = 0.5   # [0,1] — más toques = más fuerza
    descripcion: str    = ""

    @property
    def es_soporte(self):  return self.tipo in ("soporte", "pivot_s")
    @property
    def es_resistencia(self): return self.tipo in ("resistencia", "pivot_r")


@dataclass
class ResultadoSR:
    nivel_cercano:      Optional[Nivel]     = None
    distancia_pct:      float               = 1.0   # % de distancia al nivel más cercano
    en_zona:            bool                = False
    direccion_rebote:   Optional[str]       = None  # "V" si en soporte, "R" si en resistencia
    confianza:          float               = 0.0
    niveles:            list                = field(default_factory=list)
    texto:              str                 = ""

    @property
    def votar(self) -> bool:
        return self.en_zona and self.confianza >= 0.55


# ── Conversión de datos ───────────────────────────────────────────────────────

def _precio_sintetico(sec: list) -> np.ndarray:
    """Serie V/R → precio sintético acumulado."""
    return np.cumsum([1.0 if c == 'V' else -1.0 for c in sec])


def _ohlc_array(velas: list) -> tuple:
    """Lista de dicts OHLC → arrays numpy."""
    opens  = np.array([float(v.get("open",  0)) for v in velas])
    highs  = np.array([float(v.get("high",  0)) for v in velas])
    lows   = np.array([float(v.get("low",   0)) for v in velas])
    closes = np.array([float(v.get("close", 0)) for v in velas])
    return opens, highs, lows, closes


# ── Algoritmo 1: Pivot Points clásicos ───────────────────────────────────────

def _pivot_points(h, l, c) -> list[Nivel]:
    """Calcula Pivot Points clásicos basados en la vela anterior."""
    pp = (h + l + c) / 3.0
    r1 = 2.0 * pp - l
    r2 = pp + (h - l)
    r3 = h + 2.0 * (pp - l)
    s1 = 2.0 * pp - h
    s2 = pp - (h - l)
    s3 = l - 2.0 * (h - pp)

    return [
        Nivel(pp, "pivot",       toques=2, fuerza=0.60, descripcion=f"Pivot Point {pp:.5f}"),
        Nivel(r1, "pivot_r",     toques=2, fuerza=0.65, descripcion=f"Resistencia R1 {r1:.5f}"),
        Nivel(r2, "pivot_r",     toques=1, fuerza=0.55, descripcion=f"Resistencia R2 {r2:.5f}"),
        Nivel(r3, "pivot_r",     toques=1, fuerza=0.50, descripcion=f"Resistencia R3 {r3:.5f}"),
        Nivel(s1, "pivot_s",     toques=2, fuerza=0.65, descripcion=f"Soporte S1 {s1:.5f}"),
        Nivel(s2, "pivot_s",     toques=1, fuerza=0.55, descripcion=f"Soporte S2 {s2:.5f}"),
        Nivel(s3, "pivot_s",     toques=1, fuerza=0.50, descripcion=f"Soporte S3 {s3:.5f}"),
    ]


# ── Algoritmo 2: Máximos y mínimos significativos ────────────────────────────

def _swing_points(highs: np.ndarray, lows: np.ndarray,
                  closes: np.ndarray, n: int = 3) -> list[Nivel]:
    """
    Detecta swing highs y swing lows significativos.
    Un swing high es un máximo local donde los n puntos a cada lado son menores.
    """
    niveles = []
    m = len(highs)
    if m < 2 * n + 1:
        return niveles

    for i in range(n, m - n):
        # Swing High
        if all(highs[i] >= highs[i-j] for j in range(1, n+1)) and \
           all(highs[i] >= highs[i+j] for j in range(1, n+1)):
            # Contar cuántas veces el precio regresó a este nivel
            toques = sum(1 for k in range(m)
                         if abs(highs[k] - highs[i]) / (highs[i] + 1e-9) < 0.008)
            fuerza = min(0.90, 0.55 + (toques - 1) * 0.08)
            niveles.append(Nivel(
                precio=float(highs[i]),
                tipo="resistencia",
                toques=toques,
                fuerza=fuerza,
                descripcion=f"Resistencia swing {highs[i]:.5f} ({toques} toques)"
            ))

        # Swing Low
        if all(lows[i] <= lows[i-j] for j in range(1, n+1)) and \
           all(lows[i] <= lows[i+j] for j in range(1, n+1)):
            toques = sum(1 for k in range(m)
                         if abs(lows[k] - lows[i]) / (lows[i] + 1e-9) < 0.008)
            fuerza = min(0.90, 0.55 + (toques - 1) * 0.08)
            niveles.append(Nivel(
                precio=float(lows[i]),
                tipo="soporte",
                toques=toques,
                fuerza=fuerza,
                descripcion=f"Soporte swing {lows[i]:.5f} ({toques} toques)"
            ))

    return niveles


# ── Algoritmo 3: Fibonacci automático ────────────────────────────────────────

def _fibonacci(maximo: float, minimo: float,
               tendencia: str = "R") -> list[Nivel]:
    """
    Retracción de Fibonacci entre el swing más reciente (alto y bajo).
    tendencia="R" → rectracciones desde arriba (posibles soportes)
    tendencia="V" → retracción desde abajo (posibles resistencias)
    """
    diff = maximo - minimo
    if diff < 1e-9:
        return []
    niveles = []
    for pct in _FIB_NIVELES:
        if tendencia == "R":
            precio = maximo - diff * pct   # retracción bajista
            tipo   = "soporte" if pct > 0.35 else "resistencia"
        else:
            precio = minimo + diff * pct   # retracción alcista
            tipo   = "resistencia" if pct > 0.35 else "soporte"
        fib_nombre = {0.236:"23.6%", 0.382:"38.2%", 0.500:"50.0%",
                      0.618:"61.8%", 0.786:"78.6%", 1.000:"100%"}.get(pct, f"{pct:.1%}")
        niveles.append(Nivel(
            precio=float(precio),
            tipo=tipo,
            toques=1,
            fuerza=0.72 if pct in (0.382, 0.618) else 0.58,
            descripcion=f"Fibonacci {fib_nombre}: {precio:.5f}"
        ))
    return niveles


# ── Evaluador de proximidad ───────────────────────────────────────────────────

def _nivel_mas_cercano(precio_actual: float,
                       niveles: list[Nivel]) -> tuple[Optional[Nivel], float]:
    """Retorna el nivel más cercano y la distancia en %."""
    if not niveles or precio_actual == 0:
        return None, 1.0

    mejor = min(niveles, key=lambda n: abs(n.precio - precio_actual))
    dist  = abs(mejor.precio - precio_actual) / (abs(precio_actual) + 1e-9)
    return mejor, dist


# ── Modo sintético ────────────────────────────────────────────────────────────

def _analizar_sintetico(sec: list) -> ResultadoSR:
    """
    Cuando no hay datos OHLC reales, trabaja con precio sintético.
    Detecta máximos/mínimos locales en el precio sintético acumulado.
    """
    if len(sec) < 10:
        return ResultadoSR(texto="Serie insuficiente para S/R")

    precios = _precio_sintetico(sec)
    n = len(precios)
    actual = float(precios[-1])

    # Detectar swing highs y lows en la serie sintética
    ventana = 3
    soportes    = []
    resistencias = []

    for i in range(ventana, n - ventana):
        # Swing high → resistencia
        if all(precios[i] >= precios[i-j] for j in range(1, ventana+1)) and \
           all(precios[i] >= precios[i+j] for j in range(1, ventana+1)):
            resistencias.append(float(precios[i]))

        # Swing low → soporte
        if all(precios[i] <= precios[i-j] for j in range(1, ventana+1)) and \
           all(precios[i] <= precios[i+j] for j in range(1, ventana+1)):
            soportes.append(float(precios[i]))

    niveles = []
    for p in soportes[-5:]:
        niveles.append(Nivel(p, "soporte",     toques=1, fuerza=0.55))
    for p in resistencias[-5:]:
        niveles.append(Nivel(p, "resistencia", toques=1, fuerza=0.55))

    nivel, dist = _nivel_mas_cercano(actual, niveles)

    if not nivel or dist > _PROX_PCT * 5:
        return ResultadoSR(
            niveles=niveles,
            texto="Precio en zona neutra (sin S/R cercano)")

    en_zona = dist <= _PROX_PCT * 3
    dir_rebote = "V" if nivel.es_soporte else "R"
    confianza  = min(0.70, nivel.fuerza * (1.0 - dist * 20))

    return ResultadoSR(
        nivel_cercano=nivel,
        distancia_pct=dist,
        en_zona=en_zona,
        direccion_rebote=dir_rebote,
        confianza=confianza,
        niveles=niveles,
        texto=f"{'Soporte' if nivel.es_soporte else 'Resistencia'} sintético "
              f"en {nivel.precio:.2f} (dist {dist:.1%})"
    )


# ── API pública ───────────────────────────────────────────────────────────────

def analizar(sec: list, velas_ohlc: list = None) -> ResultadoSR:
    """
    Analiza soporte y resistencia y evalúa el precio actual.

    Args:
        sec:        Lista V/R de velas.
        velas_ohlc: Lista de dicts {'open','high','low','close'}.
                    Si None, usa modo sintético.

    Returns:
        ResultadoSR con niveles detectados y evaluación de la señal.
    """
    if not velas_ohlc or len(velas_ohlc) < 10:
        return _analizar_sintetico(sec)

    try:
        velas_r = velas_ohlc[-_N_RECIENTES:]
        opens, highs, lows, closes = _ohlc_array(velas_r)

        precio_actual = float(closes[-1])
        if precio_actual == 0:
            return _analizar_sintetico(sec)

        # 1. Pivot Points (basados en la penúltima vela)
        pp_niveles = _pivot_points(float(highs[-2]), float(lows[-2]), float(closes[-2]))

        # 2. Swing points
        swing = _swing_points(highs, lows, closes, n=3)

        # 3. Fibonacci (swing más reciente)
        maximo_rec = float(np.max(highs[-20:]))
        minimo_rec = float(np.min(lows[-20:]))
        # Detectar tendencia reciente
        tend_rec = "V" if closes[-1] > closes[-5] else "R"
        fib = _fibonacci(maximo_rec, minimo_rec, tend_rec)

        # Combinar todos los niveles
        todos = pp_niveles + swing + fib

        # Encontrar el más cercano
        nivel, dist = _nivel_mas_cercano(precio_actual, todos)

        if not nivel:
            return ResultadoSR(
                niveles=todos,
                texto="Sin niveles S/R detectados")

        en_zona    = dist <= _PROX_PCT
        dir_rebote = "V" if nivel.es_soporte else "R"

        # Confianza: nivel.fuerza ajustado por distancia
        # A menor distancia → mayor confianza
        prox_factor = max(0.0, 1.0 - dist / _PROX_PCT)
        confianza   = min(0.90, nivel.fuerza * (0.7 + prox_factor * 0.3))

        texto = (f"{'Soporte' if nivel.es_soporte else 'Resistencia'} "
                 f"en {precio_actual:.5f}±{dist:.2%} — "
                 f"{nivel.descripcion}")

        return ResultadoSR(
            nivel_cercano=nivel,
            distancia_pct=dist,
            en_zona=en_zona,
            direccion_rebote=dir_rebote,
            confianza=confianza,
            niveles=todos,
            texto=texto
        )

    except Exception:
        return _analizar_sintetico(sec)


def votar(res: ResultadoSR, dir_senal: str) -> tuple[bool, float]:
    """
    Compara el análisis S/R con la dirección de la señal.

    Returns:
        (confirma: bool, confianza: float)
    """
    if not res.votar:
        return False, 0.0
    confirma = (res.direccion_rebote == dir_senal)
    return confirma, res.confianza if confirma else 0.0


def niveles_resumen(res: ResultadoSR, top: int = 5) -> str:
    """Texto compacto de los niveles más relevantes para el log."""
    if not res.niveles:
        return "Sin niveles S/R"
    ordenados = sorted(res.niveles, key=lambda n: n.fuerza, reverse=True)
    lineas = [f"  {'S' if n.es_soporte else 'R'} {n.precio:.5f} (fuerza {n.fuerza:.0%})"
              for n in ordenados[:top]]
    return "S/R detectados:\n" + "\n".join(lineas)

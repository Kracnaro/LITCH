"""
periodo_config.py — Estrategia adaptativa por período de vela para LITCH v3.

LITCH detecta automáticamente el timeframe activo y ajusta:
  • Votos mínimos requeridos para operar
  • Fracción Kelly máxima (más corto = más ruido = menos apuesta)
  • Umbral de confianza mínima
  • Ventana de análisis de patrones
  • Nombre descriptivo para logs

Mapa de períodos IQ Option:
  5s   →  ULTRA_SCALP   (ruido extremo)
  10s  →  ULTRA_SCALP
  15s  →  SCALP_RÁPIDO
  30s  →  SCALP
  45s  →  SCALP
  60s  →  1M (estándar)
  120s →  2M
  180s →  3M
  300s →  5M
  600s →  10M
  900s →  15M
  1800s→  30M          (señales muy limpias)
  3600s→  1H
"""

from __future__ import annotations
from typing import NamedTuple


class PeriodoEstrategia(NamedTuple):
    """Parámetros completos de estrategia para un período de vela."""
    nombre:         str    # etiqueta legible (ej: "1M", "30M")
    votos_min_real: int    # votos mínimos en dinero real
    votos_min_demo: int    # votos mínimos en demo/práctica
    kelly_max:      float  # fracción Kelly máxima (0.0 – 0.25)
    conf_minima:    float  # confianza mínima para actuar (0.50 – 0.90)
    ventana_pat:    int    # velas atrás para analizar patrones
    descripcion:    str    # texto para avisar al usuario


# ── Tabla de estrategias por período (segundos) ───────────────────────────────
_TABLA: dict[int, PeriodoEstrategia] = {
    5:    PeriodoEstrategia("5s",   7, 5, 0.06, 0.80, 20,
                            "ultra scalp — máximo ruido, exijo 7/7"),
    10:   PeriodoEstrategia("10s",  7, 5, 0.07, 0.78, 25,
                            "ultra scalp — muy ruidoso, exijo 7/7"),
    15:   PeriodoEstrategia("15s",  6, 5, 0.08, 0.75, 30,
                            "scalp rápido — ruido alto, exijo 6/7"),
    30:   PeriodoEstrategia("30s",  6, 4, 0.09, 0.72, 40,
                            "scalp — ruido moderado-alto, exijo 6/7"),
    45:   PeriodoEstrategia("45s",  5, 4, 0.10, 0.68, 50,
                            "scalp largo — exijo 5/7 votos"),
    60:   PeriodoEstrategia("1M",   4, 3, 0.12, 0.62, 60,
                            "1 minuto — estándar, exijo 4/7"),
    120:  PeriodoEstrategia("2M",   4, 3, 0.13, 0.60, 80,
                            "2 minutos — señales limpias, exijo 4/7"),
    180:  PeriodoEstrategia("3M",   4, 3, 0.14, 0.58, 90,
                            "3 minutos — señales limpias, exijo 4/7"),
    300:  PeriodoEstrategia("5M",   3, 3, 0.16, 0.56, 100,
                            "5 minutos — señales confiables, exijo 3/7"),
    600:  PeriodoEstrategia("10M",  3, 2, 0.18, 0.55, 120,
                            "10 minutos — tendencias, exijo 3/7"),
    900:  PeriodoEstrategia("15M",  3, 2, 0.20, 0.54, 150,
                            "15 minutos — muy confiable, exijo 3/7"),
    1800: PeriodoEstrategia("30M",  3, 2, 0.22, 0.52, 200,
                            "30 minutos — señales premium, exijo 3/7"),
    3600: PeriodoEstrategia("1H",   3, 2, 0.25, 0.50, 300,
                            "1 hora — tendencias grandes, exijo 3/7"),
}

# Valor por defecto si el período no está en la tabla
_DEFAULT = PeriodoEstrategia("?", 4, 3, 0.12, 0.62, 60, "período desconocido")


def obtener(periodo_seg: int) -> PeriodoEstrategia:
    """
    Devuelve la estrategia óptima para el período de vela dado.
    Usa el período más cercano si no hay coincidencia exacta.
    """
    if periodo_seg in _TABLA:
        return _TABLA[periodo_seg]
    # Buscar el más cercano
    claves = sorted(_TABLA.keys())
    mas_cercano = min(claves, key=lambda k: abs(k - periodo_seg))
    return _TABLA[mas_cercano]


def votos_minimos(periodo_seg: int, en_practica: bool = False) -> int:
    """Atajo para obtener el mínimo de votos según período y modo."""
    est = obtener(periodo_seg)
    return est.votos_min_demo if en_practica else est.votos_min_real


def kelly_maximo(periodo_seg: int) -> float:
    """Atajo para obtener el Kelly máximo permitido según período."""
    return obtener(periodo_seg).kelly_max


def confianza_minima(periodo_seg: int) -> float:
    """Atajo para obtener el umbral de confianza mínimo."""
    return obtener(periodo_seg).conf_minima


def cambio_detectado(periodo_anterior: int, periodo_nuevo: int) -> str | None:
    """
    Genera un mensaje informativo cuando el período cambia.
    Retorna None si el cambio no es significativo.
    """
    if periodo_anterior == periodo_nuevo:
        return None
    ant = obtener(periodo_anterior)
    nvo = obtener(periodo_nuevo)
    if abs(periodo_nuevo - periodo_anterior) < 15:
        return None  # diferencia menor de 15s — no avisar
    return (f"Señor, cambié a período {nvo.nombre}. "
            f"{nvo.descripcion}. "
            f"Kelly máximo: {nvo.kelly_max:.0%}.")


# ── Mapa de strings de IQ Option → segundos ──────────────────────────────────
_STR_A_SEGS: dict[str, int] = {
    "5 segundos":  5,  "5s":  5,  "5sec": 5,
    "10 segundos": 10, "10s": 10,
    "15 segundos": 15, "15s": 15,
    "30 segundos": 30, "30s": 30,
    "45 segundos": 45, "45s": 45,
    "1 min":  60,  "1m":  60,  "1 minuto":   60,
    "2 min":  120, "2m":  120, "2 minutos":  120,
    "3 min":  180, "3m":  180, "3 minutos":  180,
    "5 min":  300, "5m":  300, "5 minutos":  300,
    "10 min": 600, "10m": 600,
    "15 min": 900, "15m": 900,
    "30 min": 1800,"30m": 1800,
    "1 hora": 3600,"1h":  3600,
}


def parse_periodo(texto: str) -> int | None:
    """Convierte texto legible (ej: '30 segundos') a segundos. Retorna None si falla."""
    t = texto.strip().lower()
    if t in _STR_A_SEGS:
        return _STR_A_SEGS[t]
    # Intentar extraer número directamente
    import re
    m = re.search(r"(\d+)\s*(s|seg|m|min|h|hora)", t)
    if m:
        n, unidad = int(m.group(1)), m.group(2)
        if unidad in ("s", "seg"):
            return n
        if unidad in ("m", "min"):
            return n * 60
        if unidad in ("h", "hora"):
            return n * 3600
    return None

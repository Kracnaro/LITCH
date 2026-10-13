"""
signal_aggregator.py — Agregador unificado de señales para LITCH v3.

Combina los 7 métodos de votación con pesos dinámicos provenientes del
CalibradorMetodos, produciendo:
  • Puntuación agregada ponderada [-1, +1]
  • Dirección de consenso ("V" | "R" | None)
  • Confianza [0, 1]
  • Descomposición por método para debug/logging
  • Régimen de mercado estimado (trending/ranging/chaotic)

Los pesos se actualizan en tiempo real conforme el calibrador aprende
qué métodos predicen mejor por activo y período.
"""

from __future__ import annotations

import math
from typing import Optional

# ── Pesos base (Brier-Score normalizado) — se sobreescriben con calibrador ────

_PESOS_BASE: dict[str, float] = {
    "markov":      1.0,
    "estadistica": 1.0,
    "red_maestra": 1.4,   # redes tienen ligera ventaja inicial
    "pronostico":  0.9,
    "indicadores": 1.1,
    "rl_agente":   1.2,
    "smc":         1.0,
}

# Umbral mínimo de score ponderado para emitir señal
_SCORE_EMITIR  = 0.35   # equivale aproximadamente a 4/7 métodos + peso
_CONF_MINIMA   = 0.52   # confianza mínima de la señal emitida


def _dir_a_float(d: Optional[str]) -> float:
    """Convierte "V"/"+1"/"R"/"-1"/None a float."""
    if d in ("V", "VERDE", "UP", "CALL", "+"):
        return 1.0
    if d in ("R", "ROJO", "DOWN", "PUT", "-"):
        return -1.0
    return 0.0


class SenalAgregada:
    """
    Resultado de la agregación de señales.

    Attributes
    ----------
    score       : float en [-1, +1]; >0 = VERDE, <0 = ROJO, ~0 = indeciso
    direccion   : "V" | "R" | None
    confianza   : float [0, 1]
    votos_favor : int (métodos que coinciden con la dirección final)
    votos_total : int (métodos con señal no-nula)
    actuar      : bool — True si el score supera el umbral mínimo
    desglose    : dict[str, dict] — aporte de cada método
    regimen     : str ("trending" | "ranging" | "chaotic")
    """

    __slots__ = (
        "score", "direccion", "confianza",
        "votos_favor", "votos_total", "actuar",
        "desglose", "regimen",
    )

    def __init__(self,
                 score: float,
                 direccion: Optional[str],
                 confianza: float,
                 votos_favor: int,
                 votos_total: int,
                 actuar: bool,
                 desglose: dict,
                 regimen: str):
        self.score       = score
        self.direccion   = direccion
        self.confianza   = confianza
        self.votos_favor = votos_favor
        self.votos_total = votos_total
        self.actuar      = actuar
        self.desglose    = desglose
        self.regimen     = regimen

    def resumen(self) -> str:
        if not self.actuar:
            return (f"[Agg] Señal débil score={self.score:+.3f} "
                    f"({self.votos_favor}/{self.votos_total}) → ABSTENERSE")
        return (f"[Agg] {self.direccion} score={self.score:+.3f} "
                f"conf={self.confianza:.2f} "
                f"({self.votos_favor}/{self.votos_total}) "
                f"regimen={self.regimen}")

    def log_desglose(self) -> str:
        partes = []
        for metodo, info in self.desglose.items():
            partes.append(
                f"{metodo[:4]}:{info.get('dir','?')} "
                f"w={info.get('peso',1):.2f} "
                f"aporte={info.get('aporte',0):+.3f}"
            )
        return " | ".join(partes)


class SignalAggregator:
    """
    Agrega los votos de los 7 métodos usando pesos dinámicos del calibrador.

    Uso:
        agg = SignalAggregator(calibrador=self.calibrador)
        senal = agg.agregar(
            markov     = {"direccion": "V", "confianza": 0.72},
            estadistica= {"direccion": "V", "confianza": 0.65},
            red_maestra= {"direccion": "V", "confianza": 0.80},
            pronostico = {"direccion": None, "confianza": 0.40},
            indicadores= {"direccion": "V", "confianza": 0.70},
            rl_agente  = {"direccion": "R", "confianza": 0.55},
            smc        = {"direccion": "V", "confianza": 0.68},
            asset="EURUSD", periodo=60,
        )
        if senal.actuar:
            ejecutar_trade(senal.direccion)
    """

    def __init__(self, calibrador=None):
        self._calibrador = calibrador

    # ── API pública ───────────────────────────────────────────────────────────

    def agregar(self,
                markov:      Optional[dict] = None,
                estadistica: Optional[dict] = None,
                red_maestra: Optional[dict] = None,
                pronostico:  Optional[dict] = None,
                indicadores: Optional[dict] = None,
                rl_agente:   Optional[dict] = None,
                smc:         Optional[dict] = None,
                asset:  str = "",
                periodo: int = 60) -> SenalAgregada:
        """
        Agrega los votos de cada método.

        Cada método debe ser un dict con:
            "direccion": "V" | "R" | None
            "confianza": float [0, 1]

        Si un método no está disponible o pasa None, se omite.
        """
        metodos = {
            "markov":      markov,
            "estadistica": estadistica,
            "red_maestra": red_maestra,
            "pronostico":  pronostico,
            "indicadores": indicadores,
            "rl_agente":   rl_agente,
            "smc":         smc,
        }

        pesos = self._obtener_pesos(asset, periodo)
        desglose: dict[str, dict] = {}
        score_v = 0.0   # suma ponderada hacia VERDE
        score_r = 0.0   # suma ponderada hacia ROJO
        peso_total = 0.0
        votos_v = 0
        votos_r = 0
        votos_validos = 0

        for nombre, dato in metodos.items():
            if dato is None:
                continue
            dir_raw = dato.get("direccion") or dato.get("dir")
            conf    = float(dato.get("confianza", 0.5) or 0.5)
            if conf < 0.30:    # señal demasiado débil — ignorar
                continue
            d_float = _dir_a_float(dir_raw)
            if d_float == 0.0:
                continue       # abstención del método
            peso    = pesos.get(nombre, 1.0)
            aporte  = d_float * conf * peso
            if d_float > 0:
                score_v += conf * peso
                votos_v += 1
            else:
                score_r += conf * peso
                votos_r += 1
            votos_validos += 1
            peso_total    += peso
            desglose[nombre] = {
                "dir":    dir_raw,
                "conf":   round(conf, 3),
                "peso":   round(peso, 3),
                "aporte": round(aporte, 4),
            }

        # ── Calcular score neto normalizado ───────────────────────────────────
        if peso_total < 1e-9:
            return self._senal_vacia(desglose)

        # Score normalizado en [-1, +1]
        score_neto = (score_v - score_r) / peso_total
        votos_favor = votos_v if score_neto >= 0 else votos_r
        dir_final  = "V" if score_neto > 0 else ("R" if score_neto < 0 else None)

        # Confianza: media ponderada de confianzas del lado ganador
        confianza = (score_v if score_neto >= 0 else score_r) / max(peso_total * 0.5, 1e-9)
        confianza = min(1.0, max(0.0, confianza))

        # Penalizar confianza si muy pocos métodos disponibles
        if votos_validos < 3:
            confianza *= 0.70

        actuar = (abs(score_neto) >= _SCORE_EMITIR
                  and confianza >= _CONF_MINIMA
                  and votos_favor >= 3)

        regimen = self._estimar_regimen(indicadores, smc)

        return SenalAgregada(
            score       = round(score_neto, 4),
            direccion   = dir_final,
            confianza   = round(confianza, 4),
            votos_favor = votos_favor,
            votos_total = votos_validos,
            actuar      = actuar,
            desglose    = desglose,
            regimen     = regimen,
        )

    # ── Utilidades internas ───────────────────────────────────────────────────

    def _obtener_pesos(self, asset: str, periodo: int) -> dict[str, float]:
        """Obtiene pesos calibrados del CalibradorMetodos o usa base."""
        pesos = dict(_PESOS_BASE)
        if self._calibrador is None:
            return pesos
        try:
            cal_pesos = self._calibrador.pesos_contexto(asset=asset, periodo=periodo)
            if cal_pesos and isinstance(cal_pesos, dict):
                for k, v in cal_pesos.items():
                    if k in pesos and v > 0:
                        pesos[k] = float(v)
        except Exception:
            pass
        # Normalizar para que la suma sea len(pesos) (para no escalar el score)
        suma = sum(pesos.values())
        if suma > 1e-9:
            factor = len(pesos) / suma
            pesos = {k: v * factor for k, v in pesos.items()}
        return pesos

    def _estimar_regimen(self,
                         indicadores: Optional[dict],
                         smc: Optional[dict]) -> str:
        """Estima el régimen de mercado basándose en indicadores y SMC."""
        if indicadores is None and smc is None:
            return "neutral"
        try:
            # SMC da BOS o CHoCH → trend fuerte
            if smc:
                if smc.get("bos") or smc.get("choch"):
                    return "trending"
                if smc.get("fvg") and smc.get("ob"):
                    return "ranging"
            # Indicadores: ATR alto + Supertrend claro → trending
            if indicadores:
                sup = indicadores.get("supertrend")
                if sup in ("V", "R"):
                    return "trending"
                kelt = indicadores.get("keltner")
                if kelt and isinstance(kelt, tuple) and len(kelt) >= 2:
                    pos = kelt[0]
                    if isinstance(pos, (int, float)):
                        if pos > 0.75 or pos < 0.25:
                            return "trending"
                        return "ranging"
            return "neutral"
        except Exception:
            return "neutral"

    @staticmethod
    def _senal_vacia(desglose: dict) -> SenalAgregada:
        return SenalAgregada(
            score=0.0, direccion=None, confianza=0.0,
            votos_favor=0, votos_total=0, actuar=False,
            desglose=desglose, regimen="neutral",
        )

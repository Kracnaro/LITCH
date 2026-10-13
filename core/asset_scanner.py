"""
asset_scanner.py — Scanner inteligente de activos para LITCH.

LITCH explora el mercado como un trader humano:
  1. Busca cuáles activos están abiertos en IQ Option
  2. Evalúa el payout, tendencia y sentimiento
  3. Cruza con el historial de LITCH (qué activo da mejores resultados)
  4. Recomienda el activo óptimo en tiempo real

También lee los "Ganadores" y "Elección de operadores" que IQ Option
muestra en su panel de mercado (lo que vemos en las capturas: OpenAI 91%, etc.)
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

_HISTORIAL_FILE = os.path.join(
    os.path.dirname(__file__), "..", "memoria_ap", "asset_performance.json")


@dataclass
class EvaluacionActivo:
    simbolo:       str
    nombre:        str
    score:         float    # 0-1, mayor = mejor oportunidad
    payout_pct:    float    # % de ganancia ofrecido
    wr_historico:  float    # win rate histórico de LITCH en este activo
    sentimiento:   float    # % de traders que esperan suba
    tendencia:     str      # 'sube' | 'baja' | 'neutro'
    razon:         str      # por qué se recomienda (texto)
    trades_totales: int     # cuántos trades tiene LITCH en este activo


class AssetScanner:
    """
    Scanner de activos: LITCH elige el mejor activo para operar.

    Funciona en dos modos:
    1. Con IQ Option API conectada: datos en tiempo real
    2. Sin API: usa historial de LITCH + datos visuales de pantalla

    El score final combina:
      - Payout ofrecido por IQ Option (peso 30%)
      - Win rate histórico de LITCH en ese activo (peso 50%)
      - Sentimiento del mercado (peso 20%)
    """

    def __init__(self, app=None):
        self._app       = app
        self._lock      = threading.Lock()
        self._hist      = self._cargar_historial()
        self._cache     = []
        self._cache_ts  = 0.0

    # ── API principal ─────────────────────────────────────────────────────────

    def escanear(self, broker=None) -> List[EvaluacionActivo]:
        """
        Escanea los activos disponibles y los evalúa.

        Si se provee un broker conectado, usa sus datos en tiempo real.
        Retorna lista ordenada por score descendente.
        """
        # Caché de 60 segundos
        if time.time() - self._cache_ts < 60 and self._cache:
            return self._cache

        activos_raw = []
        if broker and getattr(broker, "conectado", False):
            try:
                activos_raw = broker.activos_disponibles()
            except Exception:
                pass

        # Si no hay datos del broker, usar lista de activos conocidos
        if not activos_raw:
            activos_raw = self._activos_conocidos_iq()

        evaluaciones = []
        for a in activos_raw:
            ev = self._evaluar(a.simbolo, a.nombre, a.payout_pct, a.sentimiento)
            evaluaciones.append(ev)

        # Ordenar por score
        evaluaciones.sort(key=lambda e: -e.score)
        with self._lock:
            self._cache    = evaluaciones
            self._cache_ts = time.time()
        return evaluaciones

    def mejor_activo(self, broker=None) -> Optional[EvaluacionActivo]:
        """Retorna el activo con mayor score."""
        evs = self.escanear(broker)
        return evs[0] if evs else None

    def actualizar_resultado(self, simbolo: str, gano: bool) -> None:
        """Registra el resultado de un trade en el activo especificado."""
        with self._lock:
            if simbolo not in self._hist:
                self._hist[simbolo] = {"wins": 0, "losses": 0}
            if gano:
                self._hist[simbolo]["wins"] += 1
            else:
                self._hist[simbolo]["losses"] += 1
        self._guardar_historial_async()

    def resumen_texto(self, top: int = 3) -> str:
        """Texto con los mejores activos actuales."""
        evs = self.escanear()
        if not evs:
            return "[Scanner] Sin datos de activos."
        lineas = ["[Scanner] Mejores activos ahora:"]
        for i, ev in enumerate(evs[:top], 1):
            wr = f"WR={ev.wr_historico:.0%}" if ev.trades_totales >= 5 else "nuevo"
            lineas.append(
                f"  {i}. {ev.nombre}  payout={ev.payout_pct:.0f}%  {wr}  "
                f"score={ev.score:.2f}  — {ev.razon}"
            )
        return "\n".join(lineas)

    def insight_activo(self, simbolo: str) -> str:
        """Análisis específico de un activo."""
        hist = self._hist.get(simbolo, {})
        wins    = hist.get("wins",   0)
        losses  = hist.get("losses", 0)
        total   = wins + losses
        if total == 0:
            return f"{simbolo}: sin historial en LITCH."
        wr = wins / total
        col = "excelente" if wr >= 0.70 else ("bueno" if wr >= 0.55 else "deficiente")
        return (
            f"{simbolo}: {wins}W/{losses}L ({wr:.0%} WR) — rendimiento {col}. "
            f"{'Recomendado.' if wr >= 0.55 else 'Evitar si hay otras opciones.'}"
        )

    # ── Internos ──────────────────────────────────────────────────────────────

    def _evaluar(self, simbolo: str, nombre: str,
                 payout_pct: float, sentimiento: float = 0.5) -> EvaluacionActivo:
        hist  = self._hist.get(simbolo, self._hist.get(nombre, {}))
        wins   = float(hist.get("wins",   0))
        losses = float(hist.get("losses", 0))
        total  = int(wins + losses)

        # WR histórico (con suavizado Laplace si pocos datos)
        if total >= 5:
            wr = (wins + 1) / (total + 2)
        else:
            wr = 0.60   # prior optimista para activos nuevos

        # Tendencia del sentimiento
        tendencia = ("sube" if sentimiento > 0.55 else
                     "baja" if sentimiento < 0.45 else "neutro")

        # Score compuesto
        payout_norm = min(1.0, payout_pct / 95.0)    # 95% = máximo conocido
        claridad    = abs(sentimiento - 0.5) * 2       # 0=neutro, 1=extremo
        score = payout_norm * 0.30 + wr * 0.50 + claridad * 0.20

        # Razón en texto
        if total >= 5:
            razon = f"WR histórico {wr:.0%} con {total} trades"
        else:
            razon = f"activo nuevo — potencial {payout_pct:.0f}% payout"
        if tendencia != "neutro":
            razon += f", mercado tendiendo a {tendencia}"

        return EvaluacionActivo(
            simbolo        = simbolo,
            nombre         = nombre,
            score          = round(score, 4),
            payout_pct     = payout_pct,
            wr_historico   = round(wr, 3),
            sentimiento    = sentimiento,
            tendencia      = tendencia,
            razon          = razon,
            trades_totales = total,
        )

    @staticmethod
    def _activos_conocidos_iq() -> list:
        """
        Lista de activos OTC conocidos de IQ Option con payouts típicos.
        Se usa como fallback cuando no hay API conectada.
        Los payouts varían por día/hora — esto es orientativo.
        """
        from .brokers.base import InfoActivo
        return [
            InfoActivo("EURUSD-OTC",   "EUR/USD (OTC)",   payout_pct=85, sentimiento=0.5),
            InfoActivo("EURAUD-OTC",   "EUR/AUD (OTC)",   payout_pct=85, sentimiento=0.5),
            InfoActivo("GBPUSD-OTC",   "GBP/USD (OTC)",   payout_pct=82, sentimiento=0.5),
            InfoActivo("USDJPY-OTC",   "USD/JPY (OTC)",   payout_pct=84, sentimiento=0.5),
            InfoActivo("EURGBP-OTC",   "EUR/GBP (OTC)",   payout_pct=80, sentimiento=0.5),
            InfoActivo("AUDUSD-OTC",   "AUD/USD (OTC)",   payout_pct=83, sentimiento=0.5),
            InfoActivo("SHIBUSDT-OTC", "SHIB/USD (OTC)",  payout_pct=85, sentimiento=0.5),
        ]

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _cargar_historial(self) -> dict:
        try:
            if os.path.exists(_HISTORIAL_FILE):
                with open(_HISTORIAL_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _guardar_historial(self) -> None:
        try:
            os.makedirs(os.path.dirname(_HISTORIAL_FILE), exist_ok=True)
            with self._lock:
                snap = dict(self._hist)
            with open(_HISTORIAL_FILE, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False)
        except Exception:
            pass

    def _guardar_historial_async(self) -> None:
        threading.Thread(target=self._guardar_historial,
                         daemon=True, name="AssetSave").start()


# ── Singleton ─────────────────────────────────────────────────────────────────

_instancia: Optional[AssetScanner] = None


def obtener(app=None) -> AssetScanner:
    global _instancia
    if _instancia is None:
        _instancia = AssetScanner(app=app)
    return _instancia

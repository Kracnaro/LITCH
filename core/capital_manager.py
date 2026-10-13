"""
capital_manager.py — Gestor de capital en tiempo real para LITCH v3.

Lee del estado del sistema (no de pantalla — evita freezes):
  • Saldo actual de la cuenta
  • Monto de inversión configurado
  • Tiempo de vencimiento (expiry) configurado
  • Relación monto/saldo (risk per trade)

Y calcula en tiempo real:
  • Monto óptimo según Kelly + saldo actual
  • Si el monto configurado es demasiado alto o bajo
  • Alerta si el vencimiento no coincide con el período de vela
  • Cuántas operaciones de pérdida aguanta la cuenta antes de stop

Thread-safe. Persistencia de saldo vía mem["config"].
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from . import periodo_config as _pc


# ── Constantes de gestión de riesgo ──────────────────────────────────────────
_RIESGO_MAX_PCT    = 0.04    # nunca más del 4% del saldo por trade
_RIESGO_IDEAL_PCT  = 0.02    # objetivo: 2% del saldo por trade
_RIESGO_MIN_PCT    = 0.005   # mínimo: 0.5% (para trades de alta confianza)
_SALDO_MINIMO      = 20.0    # stop total si saldo cae de $20
_MONTO_MINIMO      = 1.0     # monto mínimo IQ Option


class CapitalManager:
    """
    Gestor de capital y tamaño de posición para LITCH.

    Integra:
      - Saldo de cuenta (actualizado por el sistema)
      - Monto configurado por el usuario
      - Tiempo de vencimiento vs período de vela
      - Kelly fraccionario desde trading.py

    Uso:
        cm = CapitalManager(app)
        resultado = cm.evaluar(kelly_f=0.08, votos=5, confianza=0.72)
        # resultado.monto_recomendado, resultado.es_seguro, resultado.mensaje
    """

    def __init__(self, app=None):
        self._app   = app
        self._lock  = threading.Lock()
        self._saldo_cache     = 0.0
        self._monto_cache     = 1.0
        self._vencimiento_cache = 60
        self._ultima_alerta   = 0.0
        self._alertas_dadas: set[str] = set()

    # ── API principal ─────────────────────────────────────────────────────────

    def actualizar(self, saldo: float, monto: float,
                   vencimiento_seg: int) -> None:
        """Actualiza los valores leídos de la interfaz / config."""
        with self._lock:
            self._saldo_cache       = max(0.0, float(saldo))
            self._monto_cache       = max(_MONTO_MINIMO, float(monto))
            self._vencimiento_cache = max(5, int(vencimiento_seg))

    def evaluar(self, kelly_f: float = 0.08,
                votos: int = 5,
                confianza: float = 0.65,
                periodo_vela_seg: int = 60) -> "Evaluacion":
        """
        Evalúa si el monto actual es adecuado y calcula el óptimo.

        Retorna un namedtuple Evaluacion con:
          monto_configurado   : monto que el usuario tiene puesto
          monto_recomendado   : monto que recomienda Kelly
          saldo               : saldo actual
          riesgo_pct          : riesgo actual (monto/saldo)
          es_seguro           : bool — el monto es seguro
          mensaje             : str | None — aviso si hay algo relevante
          trades_restantes    : cuántas pérdidas aguanta la cuenta
        """
        with self._lock:
            saldo      = self._saldo_cache
            monto_conf = self._monto_cache
            venc       = self._vencimiento_cache

        # Si saldo es 0 (desconocido) → silencio total, no alertar
        if saldo == 0.0:
            return Evaluacion(
                monto_configurado  = monto_conf,
                monto_recomendado  = monto_conf,
                saldo              = 0.0,
                riesgo_pct         = 0.0,
                es_seguro          = True,
                mensaje            = None,   # ← SILENCIO cuando saldo desconocido
                trades_restantes   = 999,
            )

        if saldo < _SALDO_MINIMO:
            return Evaluacion(
                monto_configurado  = monto_conf,
                monto_recomendado  = 0.0,
                saldo              = saldo,
                riesgo_pct         = 0.0,
                es_seguro          = False,
                mensaje            = (f"Saldo ${saldo:.2f} demasiado bajo. "
                                      f"Stop total recomendado."),
                trades_restantes   = 0,
            )

        # Kelly → monto óptimo
        kelly_cap   = _pc.kelly_maximo(periodo_vela_seg)
        kelly_usado = min(kelly_f, kelly_cap)
        monto_kelly = round(saldo * kelly_usado, 2)

        # Bounds: nunca más del 4% ni menos del 0.5% del saldo
        monto_max    = saldo * _RIESGO_MAX_PCT
        monto_min    = max(_MONTO_MINIMO, saldo * _RIESGO_MIN_PCT)
        monto_optimo = max(monto_min, min(monto_kelly, monto_max))

        # Redondear a múltiplos de $1 (IQ Option lo maneja mejor)
        monto_optimo = max(_MONTO_MINIMO, round(monto_optimo))

        # Riesgo del monto configurado
        riesgo_pct  = monto_conf / saldo if saldo > 0 else 0.0
        es_seguro   = riesgo_pct <= _RIESGO_MAX_PCT

        # Cuántas pérdidas aguanta la cuenta con el monto actual
        trades_rest = int(saldo / monto_conf) if monto_conf > 0 else 999

        # Mensaje de alerta
        mensaje = self._generar_mensaje(
            saldo, monto_conf, monto_optimo, riesgo_pct,
            venc, periodo_vela_seg, votos, confianza)

        return Evaluacion(
            monto_configurado  = monto_conf,
            monto_recomendado  = monto_optimo,
            saldo              = saldo,
            riesgo_pct         = riesgo_pct,
            es_seguro          = es_seguro,
            mensaje            = mensaje,
            trades_restantes   = trades_rest,
        )

    def monto_recomendado_rapido(self, kelly_f: float,
                                 periodo_seg: int = 60) -> float:
        """Atajo rápido que retorna solo el monto recomendado ($)."""
        with self._lock:
            saldo = self._saldo_cache
        if saldo < _SALDO_MINIMO:
            return _MONTO_MINIMO
        kelly_cap = _pc.kelly_maximo(periodo_seg)
        monto = saldo * min(kelly_f, kelly_cap)
        return max(_MONTO_MINIMO, min(round(monto), saldo * _RIESGO_MAX_PCT))

    def estado_texto(self) -> str:
        """Texto compacto para log: saldo, monto, vencimiento, riesgo."""
        with self._lock:
            s = self._saldo_cache
            m = self._monto_cache
            v = self._vencimiento_cache
        pct  = m / s * 100 if s > 0 else 0
        rest = int(s / m) if m > 0 else 999
        venc_txt = _seg_a_texto(v)
        return (f"[Capital] Saldo=${s:.2f} | Monto=${m:.0f} ({pct:.1f}%) | "
                f"Venc={venc_txt} | Aguanta {rest} pérdidas")

    # ── Generador de mensajes ─────────────────────────────────────────────────

    def _generar_mensaje(self, saldo, monto_conf, monto_opt,
                         riesgo_pct, venc, periodo_seg,
                         votos, confianza) -> Optional[str]:
        ahora = time.time()
        mensajes = []

        # 1. Monto excesivo
        if riesgo_pct > _RIESGO_MAX_PCT:
            clave = "monto_alto"
            if clave not in self._alertas_dadas or ahora - self._ultima_alerta > 600:
                self._alertas_dadas.add(clave)
                mensajes.append(
                    f"Señor, ${monto_conf:.0f} es el {riesgo_pct:.1%} del saldo "
                    f"(${saldo:.0f}). Kelly recomienda ${monto_opt:.0f}. "
                    f"Riesgo alto — considera bajar el monto.")

        # 2. Vencimiento vs período de vela: no deberían ser muy distintos
        ratio = venc / max(1, periodo_seg)
        if ratio < 0.5 or ratio > 3.0:
            clave = f"venc_{venc}_{periodo_seg}"
            if clave not in self._alertas_dadas:
                self._alertas_dadas.add(clave)
                venc_txt   = _seg_a_texto(venc)
                per_txt    = _seg_a_texto(periodo_seg)
                if ratio < 0.5:
                    mensajes.append(
                        f"Señor, vencimiento {venc_txt} es más corto que el período "
                        f"de vela {per_txt}. La señal puede cerrarse antes de "
                        f"confirmar — considera aumentar el vencimiento.")
                else:
                    mensajes.append(
                        f"Señor, vencimiento {venc_txt} es mucho más largo que "
                        f"el período de vela {per_txt}. Puede haber más ruido "
                        f"durante la espera.")

        # 3. Saldo bajo pero no crítico
        if saldo < 200 and saldo >= _SALDO_MINIMO:
            clave = "saldo_bajo"
            if clave not in self._alertas_dadas or ahora - self._ultima_alerta > 1800:
                self._alertas_dadas.add(clave)
                mensajes.append(
                    f"Señor, saldo en ${saldo:.0f}. "
                    f"Recomiendo máximo ${monto_opt:.0f} por operación "
                    f"({_RIESGO_IDEAL_PCT:.0%} del capital).")

        # 4. Monto perfectamente calibrado (positivo)
        elif (abs(monto_conf - monto_opt) / max(monto_opt, 1) < 0.15
              and "bien_calibrado" not in self._alertas_dadas):
            self._alertas_dadas.add("bien_calibrado")
            mensajes.append(
                f"Monto ${monto_conf:.0f} bien calibrado para saldo ${saldo:.0f}.")

        if mensajes:
            self._ultima_alerta = ahora
        return " | ".join(mensajes) if mensajes else None


# ── Resultado de evaluación ───────────────────────────────────────────────────

class Evaluacion:
    __slots__ = ("monto_configurado", "monto_recomendado", "saldo",
                 "riesgo_pct", "es_seguro", "mensaje", "trades_restantes")

    def __init__(self, monto_configurado, monto_recomendado, saldo,
                 riesgo_pct, es_seguro, mensaje, trades_restantes):
        self.monto_configurado  = monto_configurado
        self.monto_recomendado  = monto_recomendado
        self.saldo              = saldo
        self.riesgo_pct         = riesgo_pct
        self.es_seguro          = es_seguro
        self.mensaje            = mensaje
        self.trades_restantes   = trades_restantes

    def __repr__(self):
        return (f"Evaluacion(monto=${self.monto_configurado} "
                f"opt=${self.monto_recomendado} "
                f"riesgo={self.riesgo_pct:.1%} "
                f"seguro={self.es_seguro})")


# ── Utilidades ────────────────────────────────────────────────────────────────

def _seg_a_texto(segs: int) -> str:
    if segs < 60:
        return f"{segs}s"
    if segs < 3600:
        return f"{segs // 60}m"
    return f"{segs // 3600}h"

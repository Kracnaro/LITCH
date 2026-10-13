"""
RiskManager — Coordinador central de riesgo para LITCH v3.

Consolida en una sola llamada las tres fuentes de riesgo independientes:
  1. FalloDB        — historia de fallos por patrón, hora y activo
  2. SessionTracker — rendimiento por franja horaria del día
  3. ModoProfesional — drawdown de sesión, Kelly, cooldown

Uso desde trading.py:
    ok, motivo, monto = risk_manager.evaluar(sec, asset, periodo, votos,
                                              capital, pro_activo)
    if not ok:
        a.log(f"[RISK] Bloqueado: {motivo}")
        return

Diseño:
  - Un solo punto de entrada `evaluar()` — cero lógica de riesgo dispersa
  - Cada fuente puede bloquearse independientemente (AND lógico)
  - Retorna monto=0.0 si bloqueado, monto real si autorizado
  - Thread-safe: sin estado mutable (consulta objetos ya thread-safe)
  - Incluye `resumen()` para logging y voz

Compatibilidad hacia atrás:
  - Si risk_manager no está importado, trading.py sigue funcionando con
    los checks inline que ya existen; risk_manager los reemplaza pero no
    los elimina — la migración es gradual.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fallo_db      import FalloDB
    from .session_tracker import SessionTracker
    from .modo_profesional import ModoProfesional


# ── Constantes ────────────────────────────────────────────────────────────────

# FalloDB: mínimo de observaciones para que el filtro hora×votos sea vinculante
_MIN_OBS_HORA = 8

# Confianza mínima para que un voto estadístico bloquee la operación
_CONF_MIN_ESTADIST = 0.56

# Drawdown de sesión que activa advertencia de riesgo elevado (antes del hard stop)
_DD_WARN_PCT = 0.05     # 5% → aviso amarillo
_DD_STOP_PCT = 0.08     # 8% → bloqueo total (ya en ModoProfesional)

# Score mínimo de consenso ponderado para no bloquearse por baja confianza
_SCORE_MIN = 0.30


# ── Resultado de evaluación ───────────────────────────────────────────────────

@dataclass
class ResultadoRiesgo:
    autorizado:  bool    = False
    motivo:      str     = "no evaluado"
    monto:       float   = 0.0
    # Detalles por fuente (para debugging y logs)
    fallo_ok:    bool    = True
    session_ok:  bool    = True
    pro_ok:      bool    = True
    # Métricas útiles para reward shaping del agente RL
    dd_pct:      float   = 0.0     # drawdown actual de sesión [0, 1]
    en_killzone: bool    = False    # True cuando SMC/LWS killzone está activa
    factor_ses:  float   = 1.0     # factor de sesión (overlap > NY > asiática)
    slot_viable: bool    = True     # SessionTracker: slot con WR aceptable
    # Metadatos de auditoría
    ts:          float   = field(default_factory=time.time)


# ── Coordinador ───────────────────────────────────────────────────────────────

class RiskManager:
    """
    Coordinador central de riesgo.

    Se instancia una vez en trading.py.__init__ y se consulta en
    _evaluar_y_loguear() antes de cada operación.

    Parámetros de construcción (opcionales — para modos sin Pro o sin FalloDB):
        fdb            FalloDB instance (puede ser None)
        session_tracker SessionTracker instance (puede ser None)
        modo_pro       ModoProfesional instance (puede ser None)
    """

    def __init__(self,
                 fdb=None,
                 session_tracker=None,
                 modo_pro=None):
        self._fdb = fdb
        self._st  = session_tracker
        self._pro = modo_pro

    # ── API pública ──────────────────────────────────────────────────────────

    def evaluar(self,
                secuencia:   list,
                asset:       str   = "",
                periodo:     int   = 60,
                votos:       int   = 0,
                capital:     float = 0.0,
                pro_activo:  bool  = False,
                en_killzone: bool  = False) -> ResultadoRiesgo:
        """
        Evalúa si la operación está autorizada.

        Devuelve un ResultadoRiesgo con:
          .autorizado  → bool: operar o no
          .motivo      → str:  razón legible para log
          .monto       → float: monto sugerido (0.0 si bloqueado)
          .dd_pct      → float: drawdown actual de sesión [0, 1]
          .en_killzone → bool:  pasado directamente a RL para reward shaping
        """
        res = ResultadoRiesgo(en_killzone=en_killzone)

        hora_h = time.localtime().tm_hour   # hora local del sistema

        # ── 1. FalloDB: hora × votos ─────────────────────────────────────────
        if self._fdb is not None and pro_activo:
            riesgo = self._fdb.riesgo_hora_votos(hora_h, votos)
            if not riesgo.get("ok", True) and riesgo.get("n", 0) >= _MIN_OBS_HORA:
                res.fallo_ok  = False
                res.motivo    = f"FalloDB hora×votos: {riesgo.get('razon', '?')}"
                return self._rechazar(res)

        # ── 2. SessionTracker: slot WR ────────────────────────────────────────
        if self._st is not None:
            viable, motivo_slot = self._st.slot_viable()
            res.slot_viable = viable
            if not viable:
                res.session_ok = False
                res.motivo     = f"SessionTracker: {motivo_slot}"
                return self._rechazar(res)
            # Factor de confianza para el monto
            res.factor_ses = self._st.factor_confianza()

        # ── 3. ModoProfesional: drawdown + cooldown ───────────────────────────
        if self._pro is not None and pro_activo:
            puede, motivo_pro = self._pro.puede_ejecutar()
            if not puede:
                res.pro_ok = False
                res.motivo = f"ModoProfesional: {motivo_pro}"
                # Extraer dd_pct antes de rechazar (útil para RL)
                try:
                    st = self._pro.stats()
                    res.dd_pct = float(st.get("dd_actual", 0.0))
                except Exception:
                    pass
                return self._rechazar(res)

            # Obtener monto y estadísticas de sesión
            try:
                st = self._pro.stats()
                res.dd_pct   = float(st.get("dd_actual", 0.0))
                res.monto    = self._pro.calcular_monto(capital)
            except Exception:
                res.monto  = 0.0
                res.dd_pct = 0.0
        else:
            # Sin modo Pro: usar Kelly básico (1% del capital) como fallback
            res.monto = max(1.0, round(capital * 0.01, 2)) if capital > 0 else 1.0

        # ── 4. Guardia de último recurso: score de confianza mínimo ──────────
        if votos < 4:
            res.motivo = f"votos insuficientes: {votos}/7 < 4"
            return self._rechazar(res)

        # Todo OK
        res.autorizado = True
        res.motivo     = (
            f"OK | votos={votos}/7 "
            f"dd={res.dd_pct:.1%} "
            f"slot_f={res.factor_ses:.2f} "
            f"monto={res.monto:.2f}"
        )
        return res

    def registrar_resultado(self,
                            resultado: str,
                            votos:     int   = 0,
                            dd_pct:    float = 0.0) -> None:
        """
        Actualiza SessionTracker y ModoProfesional tras el cierre de un trade.

        resultado: "win" | "loss"
        """
        if self._st is not None:
            self._st.registrar(resultado=resultado, votos=votos)

        if self._pro is not None:
            ganancia = resultado == "win"
            self._pro.registrar_resultado(ganancia)

    def resumen(self) -> str:
        """Texto legible de métricas de riesgo para log/voz."""
        partes = []

        if self._pro is not None:
            try:
                st = self._pro.stats()
                dd  = st.get("dd_actual", 0.0)
                sha = st.get("sharpe",    0.0)
                fse = st.get("factor_ses", 1.0)
                ses = st.get("sesion",    "?")
                partes.append(
                    f"Pro: DD={dd:.1%} Sharpe={sha:.2f} "
                    f"sesion={ses} factor={fse:.2f}"
                )
            except Exception:
                partes.append("Pro: [error obteniendo stats]")

        if self._st is not None:
            try:
                sf = self._st.stats_completos()
                tot = sf.get("total_slots_con_datos", 0)
                mej = sf.get("mejor_slot_wr", 0.0)
                peo = sf.get("peor_slot_wr",  0.0)
                partes.append(
                    f"Session: {tot} slots conocidos "
                    f"mejor={mej:.1%} peor={peo:.1%}"
                )
            except Exception:
                partes.append("Session: [sin datos]")

        if self._fdb is not None:
            try:
                ast_stats = self._fdb.stats_por_activo(ventana=100)
                if ast_stats:
                    mejor = max(ast_stats.items(), key=lambda x: x[1].get("wr", 0))
                    partes.append(
                        f"FalloDB: mejor activo={mejor[0]} "
                        f"wr={mejor[1].get('wr', 0):.1%}"
                    )
            except Exception:
                partes.append("FalloDB: [sin datos activo]")

        return " | ".join(partes) if partes else "RiskManager: sin fuentes configuradas"

    # ── Interno ──────────────────────────────────────────────────────────────

    @staticmethod
    def _rechazar(res: ResultadoRiesgo) -> ResultadoRiesgo:
        res.autorizado = False
        res.monto      = 0.0
        return res

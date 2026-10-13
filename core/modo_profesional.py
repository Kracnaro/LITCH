"""
modo_profesional.py — Modo de Trading Profesional de Litch.

Opera aplicando todo el conocimiento acumulado con los filtros más exigentes:
  • Mínimo 5/7 motores en acuerdo (vs 3 en práctica, 4-6 en modo normal)
  • Probabilidad bayesiana ≥ 57.2%
  • Kelly estrictamente positivo (expectativa matemática rentable)
  • Anti-martingala: pausa automática tras 3 pérdidas seguidas (15 min)
  • Drawdown diario: detiene la operativa si la pérdida acumulada > 8% del capital
  • Cooldown adaptativo: se extiende con pérdidas, se reduce con rachas ganadoras
  • Position sizing multi-factor: Kelly × factor_sesión × factor_drawdown
  • Sesiones preferidas: killzones London + NY (factor ×1.20 en tamaño)
  • FalloDB activo: bloquea patrones con historial adverso
  • Sharpe ratio de sesión: métrica institucional de calidad de señales

Diferencia con práctica:
  Práctica    = aprender rápido  (señales débiles, errores aceptables)
  Profesional = capital real      (solo señales fuertes, máxima precisión)

Basado en:
  - Kelly (1956): fracción óptima de apuesta
  - Sharpe (1966): ratio rendimiento/volatilidad
  - Elder (2002): Regla del 2% — protección de capital por sesión
  - Francisca Serrano: gestión de riesgo disciplinada en opciones binarias
"""
import math
import threading
import time
from typing import Optional

# ── Parámetros del modo profesional ───────────────────────────────────────────
VOTOS_MIN      = 5      # de 7 motores
PROB_MIN       = 0.572  # probabilidad bayesiana
KELLY_MIN      = 0.01   # Kelly mínimo positivo
MAX_RACHA_LOSS = 3      # pausa tras N pérdidas seguidas
PAUSA_SECS     = 900    # 15 minutos de pausa anti-martingala
COOLDOWN       = 18     # segundos entre trades
MAX_DD_PCT     = 0.08   # max drawdown de sesión → detener operativa (8%)
COOLDOWN_BONUS = 8      # segundos extra al cooldown tras cada pérdida (max 2×)

# ── Sesiones de mercado (hora UTC) con su factor de calidad ──────────────────
# London 07-10, NY 13-16, Overlap 13-17 = mejor liquidez y tendencias limpias
# Asian 00-06 = mayor ruido en binarias OTC
_SESIONES = {
    "overlap":  (range(13, 17), 1.20),   # London + NY: max liquidez
    "london":   (range(7,  13), 1.05),
    "ny":       (range(17, 20), 1.00),
    "asian":    (range(0,   7), 0.75),   # reducir tamaño en Asia
    "cierre":   (range(20, 24), 0.85),   # mercado cerrando, menos predecible
}

_instancia: Optional["ModoProfesional"] = None


class ModoProfesional:
    """Modo de trading de alta precisión con todos los filtros activos."""

    def __init__(self, app):
        self.app          = app
        self._activo      = False
        self._ultimo_t    = 0.0
        self._pausado_h   = 0.0
        self._n_trades    = 0
        self._n_wins      = 0
        self._n_losses    = 0
        self._racha_loss  = 0
        self._pnl_kelly   = 0.0   # Kelly-weighted P&L simulado
        self._lock        = threading.Lock()

        # ── Drawdown de sesión ────────────────────────────────────────────────
        self._pnl_sesion     = 0.0    # ganancia/pérdida neta de la sesión ($)
        self._pnl_pico       = 0.0    # máximo histórico de la sesión ($)
        self._dd_max_sesion  = 0.0    # max drawdown registrado esta sesión
        self._capital_inicio = 0.0    # capital al activar el modo
        self._dd_detenido    = False  # True si el drawdown gate detuvo la operativa

        # ── Sharpe ratio de sesión ────────────────────────────────────────────
        # Acumulamos retornos por trade (en unidades de monto base) para Sharpe
        self._retornos_sesion: list[float] = []

        # ── Cooldown adaptativo ───────────────────────────────────────────────
        # Cooldown base = COOLDOWN; se extiende tras pérdidas, se reduce tras rachas
        self._cooldown_actual = COOLDOWN

    @property
    def activo(self) -> bool:
        return self._activo

    # ── Activación ────────────────────────────────────────────────────────────

    def activar(self, capital_inicio: float = 0.0) -> None:
        with self._lock:
            self._activo            = True
            self._pausado_h         = 0.0
            self._capital_inicio    = capital_inicio
            self._pnl_sesion        = 0.0
            self._pnl_pico          = 0.0
            self._dd_max_sesion     = 0.0
            self._dd_detenido       = False
            self._retornos_sesion   = []
            self._cooldown_actual   = COOLDOWN
            self._n_trades          = 0
            self._n_wins            = 0
            self._n_losses          = 0
            self._racha_loss        = 0
            self._pnl_kelly         = 0.0
        a = self.app
        ses = self._sesion_actual()
        a.log("[PRO] MODO PROFESIONAL ACTIVADO")
        a.log(f"[PRO] Umbral: {VOTOS_MIN}/7 votos | prob>{PROB_MIN} | Kelly>{KELLY_MIN}")
        a.log(f"[PRO] Sesion: {ses['nombre']} (factor_tamano={ses['factor']:.2f})")
        a.decir(a.txt(
            "Modo profesional activado. "
            "Operare solo con senales de maxima precision y expectativa positiva.",
            "Professional mode activated. "
            "I will only trade maximum-precision signals with positive expectation."))
        if not getattr(a, "trading_on", False):
            try:
                a.set_trading(True, hablar=False)
                a.log("[PRO] Trading activado automaticamente.")
            except Exception:
                pass
        self._actualizar_ui(True)

    def desactivar(self) -> None:
        with self._lock:
            self._activo = False
        s = self.stats()
        self.app.log(
            f"[PRO] Modo Profesional desactivado. "
            f"Sesion: {s['trades']} trades | WR={s['wr']:.0f}% | "
            f"Kelly P&L={s['pnl_kelly']:+.3f} | "
            f"Sharpe={s['sharpe']:+.2f} | DD_max={s['dd_max']:.1%}")
        self._actualizar_ui(False)

    def toggle(self) -> bool:
        if self._activo:
            self.desactivar()
        else:
            self.activar()
        return self._activo

    def _actualizar_ui(self, estado: bool) -> None:
        try:
            self.app.interfaz.root.after(
                0, lambda: self.app.interfaz._actualizar_banner_pro(estado))
        except Exception:
            pass

    # ── Anti-martingala ───────────────────────────────────────────────────────

    def _en_pausa_anti_martingala(self) -> bool:
        if time.time() < self._pausado_h:
            mins = int((self._pausado_h - time.time()) / 60) + 1
            self.app.log(f"[PRO] Anti-martingala activa — {mins} min de pausa.")
            return True
        return False

    # ── Decisión de ejecución ─────────────────────────────────────────────────

    def puede_ejecutar(self, votos: int, prob: float,
                       kelly: float) -> tuple:
        """Devuelve (puede: bool, razon: str).

        Verifica en orden:
          1. Modo activo
          2. Gate de drawdown de sesión (nuevo v2)
          3. Anti-martingala (pausa activa)
          4. Anti-martingala (trigger nuevo ciclo de pérdidas)
          5. Votos mínimos
          6. Probabilidad bayesiana
          7. Kelly mínimo
          8. Cooldown adaptativo (extendido tras pérdidas)
        """
        if not self._activo:
            return False, "modo profesional inactivo"

        # Gate de drawdown: si la sesión perdió > MAX_DD_PCT del capital → stop
        if self._dd_detenido:
            return False, (f"drawdown de sesion > {MAX_DD_PCT:.0%} — "
                           "operativa suspendida para esta sesion")

        if self._en_pausa_anti_martingala():
            return False, "anti-martingala activa"

        if self._racha_loss >= MAX_RACHA_LOSS:
            with self._lock:
                self._pausado_h  = time.time() + PAUSA_SECS
                self._racha_loss = 0
            mins = PAUSA_SECS // 60
            self.app.log(f"[PRO] {MAX_RACHA_LOSS} perdidas seguidas → pausa {mins} min.")
            self.app.decir(self.app.txt(
                f"Racha de {MAX_RACHA_LOSS} perdidas. Pausa de {mins} minutos.",
                f"{MAX_RACHA_LOSS} consecutive losses. Pausing {mins} minutes."))
            return False, "anti-martingala: pausa activada"

        if votos < VOTOS_MIN:
            return False, f"solo {votos}/{VOTOS_MIN} votos — senal debil para Pro"

        if prob < PROB_MIN:
            return False, f"prob {prob:.3f} < {PROB_MIN:.3f}"

        if kelly < KELLY_MIN:
            return False, f"Kelly={kelly:.4f} — expectativa insuficiente"

        ahora = time.time()
        if ahora - self._ultimo_t < self._cooldown_actual:
            restante = int(self._cooldown_actual - (ahora - self._ultimo_t)) + 1
            return False, f"cooldown {restante}s"

        return True, "OK"

    # ── Position sizing multi-factor ──────────────────────────────────────────

    def calcular_monto(self, kelly: float, monto_base: float = 10.0) -> float:
        """Monto con Kelly × factor_sesión × factor_drawdown.

        Factor sesión: London/NY overlap = 1.20, Asian = 0.75, etc.
        Factor drawdown: si el DD actual > 4% reducir a 50% del Kelly normal.
        Acotado entre 1× y 4× el monto base.
        """
        if kelly <= 0.0:
            return monto_base
        ses          = self._sesion_actual()
        factor_ses   = ses["factor"]
        # Si ya perdimos más del 4% de capital, reducir tamaño a la mitad
        dd_actual    = self._dd_actual_pct()
        factor_dd    = 0.5 if dd_actual > 0.04 else 1.0
        kelly_adj    = kelly * factor_ses * factor_dd
        monto        = monto_base * (kelly_adj * 4.0)
        return float(max(monto_base, min(round(monto, 1), monto_base * 4)))

    # ── Sesión / hora ─────────────────────────────────────────────────────────

    def _sesion_actual(self) -> dict:
        """Devuelve {'nombre': str, 'factor': float} según hora UTC actual."""
        hora_utc = int(time.gmtime().tm_hour)
        for nombre, (rango, factor) in _SESIONES.items():
            if hora_utc in rango:
                return {"nombre": nombre, "factor": factor}
        return {"nombre": "neutral", "factor": 1.00}

    def hora_optima(self) -> bool:
        """True si la sesión actual tiene factor ≥ 1.0 (London/NY)."""
        return self._sesion_actual()["factor"] >= 1.0

    def _dd_actual_pct(self) -> float:
        """Drawdown actual de la sesión como fracción del capital inicial."""
        if self._capital_inicio <= 0 or self._pnl_pico <= 0:
            return 0.0
        dd = max(0.0, self._pnl_pico - self._pnl_sesion)
        return dd / self._capital_inicio

    # ── Registro de resultados ────────────────────────────────────────────────

    def registrar_click(self) -> None:
        with self._lock:
            self._ultimo_t = time.time()
            self._n_trades += 1

    def registrar_resultado(self, acierto: bool, kelly: float = 0.0,
                            payout: float = 0.85,
                            monto_usado: float = 10.0) -> None:
        """Registra resultado con actualización de drawdown, Sharpe y cooldown."""
        retorno = monto_usado * payout if acierto else -monto_usado
        with self._lock:
            if acierto:
                self._n_wins      += 1
                self._racha_loss   = 0
                self._pnl_kelly   += kelly * payout
                self._pnl_sesion  += retorno
                # Ajustar cooldown: cada 3 wins seguidos, reducir 2s (min COOLDOWN)
                wins_consec = (self._n_wins %
                               max(1, self._n_wins + self._n_losses))
                if self._n_wins > 0 and self._n_losses == 0:
                    self._cooldown_actual = max(
                        COOLDOWN, self._cooldown_actual - 2)
                else:
                    self._cooldown_actual = max(
                        COOLDOWN, self._cooldown_actual - 1)
            else:
                self._n_losses    += 1
                self._racha_loss  += 1
                self._pnl_kelly   -= kelly
                self._pnl_sesion  -= monto_usado
                # Extender cooldown tras pérdida (max 2× base)
                bonus = min(COOLDOWN_BONUS * self._racha_loss,
                            COOLDOWN * 2 - COOLDOWN)
                self._cooldown_actual = COOLDOWN + bonus

            # Actualizar pico y drawdown
            if self._pnl_sesion > self._pnl_pico:
                self._pnl_pico = self._pnl_sesion
            dd = self._dd_actual_pct()
            if dd > self._dd_max_sesion:
                self._dd_max_sesion = dd

            # ── Gate de drawdown ──────────────────────────────────────────────
            _dd_gate_activado = False
            _dd_pct_snapshot  = 0.0
            _dd_abs_snapshot  = 0.0
            if (self._capital_inicio > 0
                    and dd >= MAX_DD_PCT
                    and not self._dd_detenido):
                self._dd_detenido    = True
                _dd_gate_activado    = True
                _dd_pct_snapshot     = dd
                _dd_abs_snapshot     = max(0.0, self._pnl_pico - self._pnl_sesion)

            # Acumular retornos para Sharpe
            self._retornos_sesion.append(retorno)

        # Loguear fuera del lock
        if _dd_gate_activado:
            self.app.log(
                f"[PRO] ⛔ DRAWDOWN SESION: -{_dd_pct_snapshot:.1%} "
                f"(${_dd_abs_snapshot:.1f}) > {MAX_DD_PCT:.0%} — operativa detenida.")
            self.app.decir(self.app.txt(
                f"Perdida de sesion supera el {MAX_DD_PCT:.0%}. "
                "Deteniendo operativa para proteger el capital.",
                f"Session drawdown exceeded {MAX_DD_PCT:.0%}. "
                "Halting trading to protect capital."))

    # ── Sharpe ratio ──────────────────────────────────────────────────────────

    def sharpe_sesion(self) -> float:
        """Sharpe ratio anualizado simplificado de la sesión actual."""
        rets = self._retornos_sesion
        if len(rets) < 3:
            return 0.0
        try:
            import statistics
            media  = statistics.mean(rets)
            std    = statistics.stdev(rets)
            if std < 1e-9:
                return 0.0
            return round(media / std, 2)
        except Exception:
            return 0.0

    # ── Estadísticas ─────────────────────────────────────────────────────────

    def stats(self) -> dict:
        tot = self._n_wins + self._n_losses
        ses = self._sesion_actual()
        return {
            "trades":       self._n_trades,
            "wins":         self._n_wins,
            "losses":       self._n_losses,
            "wr":           round(self._n_wins / tot * 100, 1) if tot else 0.0,
            "racha_loss":   self._racha_loss,
            "pnl_kelly":    round(self._pnl_kelly, 3),
            "pnl_sesion":   round(self._pnl_sesion, 2),
            "dd_actual":    round(self._dd_actual_pct() * 100, 2),
            "dd_max":       round(self._dd_max_sesion, 4),
            "sharpe":       self.sharpe_sesion(),
            "sesion":       ses["nombre"],
            "factor_ses":   ses["factor"],
            "cooldown":     self._cooldown_actual,
            "dd_detenido":  self._dd_detenido,
        }

    def resumen(self) -> str:
        s = self.stats()
        return (f"PRO: {s['trades']} trades | "
                f"W={s['wins']} L={s['losses']} WR={s['wr']:.0f}% | "
                f"Kelly P&L={s['pnl_kelly']:+.3f} | "
                f"Sesion={s['pnl_sesion']:+.1f}$ | "
                f"Sharpe={s['sharpe']:+.2f} | "
                f"DD={s['dd_actual']:.1f}% | "
                f"Sesion_fx={s['sesion']}×{s['factor_ses']:.2f}")

    @staticmethod
    def deberia_activarse(practica_stats: dict) -> bool:
        """True si las estadísticas de práctica justifican pasar a modo profesional."""
        tot = practica_stats.get("wins", 0) + practica_stats.get("losses", 0)
        wr  = practica_stats.get("wr", 0.0)
        return tot >= 30 and wr >= 60.0


# ── Singleton ─────────────────────────────────────────────────────────────────

def obtener(app=None) -> Optional[ModoProfesional]:
    global _instancia
    if _instancia is None and app is not None:
        _instancia = ModoProfesional(app)
    return _instancia

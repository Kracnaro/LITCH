"""
performance_tracker.py — Analítica de rendimiento en tiempo real para LITCH v3.

Registra y analiza el rendimiento operativo de Litch en múltiples dimensiones:
  • Rolling WR (10, 20, 50, 100 trades)
  • Profit factor (bruto ganancias / bruto pérdidas)
  • Max consecutive wins/losses
  • Sharpe ratio simple
  • Calmar ratio (retorno anualizado / max drawdown)
  • Expectativa matemática por trade
  • Rendimiento por franja horaria
  • Rendimiento por activo
  • Rendimiento por régimen de mercado (trending/ranging/chaotic)
  • Análisis de correlación señal→resultado por número de votos

Todo persistido en JSON para sobrevivir reinicios.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ── Constantes ────────────────────────────────────────────────────────────────

_MAX_TRADES   = 2000   # máximo de trades en memoria
_VENTANAS     = (10, 20, 50, 100)  # rolling WR windows
_PERIODOS_DIA = 24     # horas del día para análisis temporal


class PerformanceTracker:
    """
    Rastreador de rendimiento integral de LITCH.

    Uso típico (en trading.py):
        # Instanciar al inicio de sesión
        self._perf = PerformanceTracker(ruta=os.path.join(mem_ap, "perf_tracker.json"))

        # Registrar cada trade
        self._perf.registrar(
            resultado="WIN",
            monto=1.0,
            payout=0.85,
            votos=6,
            asset="EUR/USD",
            regimen="trending",
        )

        # Consultar métricas
        report = self._perf.reporte_completo()
    """

    def __init__(self, ruta: str = None):
        self._lock   = threading.Lock()
        self._trades: deque[dict] = deque(maxlen=_MAX_TRADES)
        self._ruta   = ruta
        # Racha actual
        self._racha_win  = 0
        self._racha_loss = 0
        self._max_racha_win  = 0
        self._max_racha_loss = 0
        # Pico de P&L (para drawdown)
        self._pnl_pico = 0.0
        self._pnl_total = 0.0
        self._max_dd   = 0.0   # max drawdown visto (en $)
        # Carga histórico
        if ruta and os.path.exists(ruta):
            self._cargar()

    # ── Registro ──────────────────────────────────────────────────────────────

    def registrar(self, resultado: str,
                  monto: float     = 1.0,
                  payout: float    = 0.85,
                  votos: int       = 0,
                  asset: str       = "",
                  regimen: str     = "neutral",
                  hora: int | None = None,
                  conciencia_p: float = 0.5) -> None:
        """
        Registra el resultado de un trade.

        resultado: "WIN" | "LOSS"
        monto    : monto apostado
        payout   : multiplicador de ganancia (0.85 = 85%)
        votos    : número de votos del consensus (1-7)
        asset    : activo ("EUR/USD", "BTC/USD", etc.)
        regimen  : régimen del mercado al momento del trade
        hora     : hora UTC del trade (None = automático)
        conciencia_p: probabilidad estimada por Conciencia
        """
        if resultado not in ("WIN", "LOSS"):
            return
        ahora = time.time()
        h     = hora if hora is not None else int(time.gmtime().tm_hour)
        pnl   = monto * payout if resultado == "WIN" else -monto

        with self._lock:
            self._trades.append({
                "ts":      ahora,
                "res":     resultado,
                "monto":   round(monto, 2),
                "payout":  round(payout, 2),
                "pnl":     round(pnl, 4),
                "votos":   votos,
                "asset":   asset,
                "regimen": regimen,
                "hora":    h,
                "p_con":   round(conciencia_p, 3),
            })
            # Rachas
            if resultado == "WIN":
                self._racha_win  += 1
                self._racha_loss  = 0
                self._max_racha_win = max(self._max_racha_win, self._racha_win)
            else:
                self._racha_loss += 1
                self._racha_win   = 0
                self._max_racha_loss = max(self._max_racha_loss, self._racha_loss)
            # P&L acumulado y drawdown
            self._pnl_total += pnl
            if self._pnl_total > self._pnl_pico:
                self._pnl_pico = self._pnl_total
            dd = self._pnl_pico - self._pnl_total
            if dd > self._max_dd:
                self._max_dd = dd

        # Guardar de forma asíncrona
        if self._ruta:
            threading.Thread(target=self._guardar, daemon=True,
                             name="PerfSave").start()

    # ── Métricas individuales ─────────────────────────────────────────────────

    def wr_rolling(self, ventana: int = 20) -> float:
        """Win rate en los últimos `ventana` trades."""
        with self._lock:
            trades = list(self._trades)[-ventana:]
        if not trades:
            return 0.0
        return sum(1 for t in trades if t["res"] == "WIN") / len(trades)

    def profit_factor(self, ventana: int = 100) -> float:
        """Profit Factor = bruto ganancias / bruto pérdidas."""
        with self._lock:
            trades = list(self._trades)[-ventana:]
        ganancias = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        perdidas  = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
        if perdidas < 1e-9:
            return float("inf") if ganancias > 0 else 1.0
        return round(ganancias / perdidas, 3)

    def expectativa(self, ventana: int = 100) -> float:
        """Expectativa matemática por trade en $."""
        with self._lock:
            trades = list(self._trades)[-ventana:]
        if not trades:
            return 0.0
        return round(sum(t["pnl"] for t in trades) / len(trades), 4)

    def sharpe_simple(self, ventana: int = 50) -> float:
        """Sharpe ratio simplificado (retorno medio / desv. estándar de retornos)."""
        with self._lock:
            trades = list(self._trades)[-ventana:]
        if len(trades) < 5:
            return 0.0
        pnls  = [t["pnl"] for t in trades]
        media = sum(pnls) / len(pnls)
        var   = sum((p - media) ** 2 for p in pnls) / max(1, len(pnls) - 1)
        std   = math.sqrt(max(0.0, var))
        if std < 1e-9:
            return 0.0
        return round(media / std, 3)

    def wr_por_votos(self, ventana: int = 200) -> dict[int, dict]:
        """WR agrupado por número de votos (1-7)."""
        with self._lock:
            trades = list(self._trades)[-ventana:]
        mapa: dict[int, dict] = {}
        for t in trades:
            v = t.get("votos", 0)
            if v not in mapa:
                mapa[v] = {"W": 0, "L": 0}
            mapa[v]["W" if t["res"] == "WIN" else "L"] += 1
        resultado = {}
        for v, cnt in sorted(mapa.items()):
            n = cnt["W"] + cnt["L"]
            resultado[v] = {"n": n, "wr": round(cnt["W"] / n * 100, 1)}
        return resultado

    def wr_por_activo(self, ventana: int = 200) -> dict[str, dict]:
        """WR agrupado por activo."""
        with self._lock:
            trades = list(self._trades)[-ventana:]
        mapa: dict[str, dict] = {}
        for t in trades:
            a = t.get("asset", "?") or "?"
            if a not in mapa:
                mapa[a] = {"W": 0, "L": 0}
            mapa[a]["W" if t["res"] == "WIN" else "L"] += 1
        resultado = {}
        for a, cnt in mapa.items():
            n = cnt["W"] + cnt["L"]
            if n >= 5:
                resultado[a] = {"n": n, "wr": round(cnt["W"] / n * 100, 1)}
        return dict(sorted(resultado.items(), key=lambda x: -x[1]["wr"]))

    def wr_por_hora(self, ventana: int = 300) -> dict[int, dict]:
        """WR agrupado por hora UTC del día."""
        with self._lock:
            trades = list(self._trades)[-ventana:]
        mapa: dict[int, dict] = {}
        for t in trades:
            h = t.get("hora", 0)
            if h not in mapa:
                mapa[h] = {"W": 0, "L": 0}
            mapa[h]["W" if t["res"] == "WIN" else "L"] += 1
        resultado = {}
        for h, cnt in sorted(mapa.items()):
            n = cnt["W"] + cnt["L"]
            if n >= 3:
                resultado[h] = {"n": n, "wr": round(cnt["W"] / n * 100, 1)}
        return resultado

    def wr_por_regimen(self, ventana: int = 200) -> dict[str, dict]:
        """WR agrupado por régimen de mercado."""
        with self._lock:
            trades = list(self._trades)[-ventana:]
        mapa: dict[str, dict] = {}
        for t in trades:
            r = t.get("regimen", "neutral") or "neutral"
            if r not in mapa:
                mapa[r] = {"W": 0, "L": 0}
            mapa[r]["W" if t["res"] == "WIN" else "L"] += 1
        resultado = {}
        for r, cnt in mapa.items():
            n = cnt["W"] + cnt["L"]
            if n >= 3:
                resultado[r] = {"n": n, "wr": round(cnt["W"] / n * 100, 1)}
        return resultado

    # ── Reporte completo ──────────────────────────────────────────────────────

    def reporte_completo(self) -> dict:
        """Devuelve todas las métricas en un dict para logging/UI."""
        n_total = len(self._trades)
        with self._lock:
            all_trades = list(self._trades)
        wins   = sum(1 for t in all_trades if t["res"] == "WIN")
        losses = n_total - wins
        return {
            "total_trades":     n_total,
            "wins":             wins,
            "losses":           losses,
            "wr_total":         round(wins / n_total * 100, 1) if n_total else 0,
            "wr_10":            round(self.wr_rolling(10) * 100, 1),
            "wr_20":            round(self.wr_rolling(20) * 100, 1),
            "wr_50":            round(self.wr_rolling(50) * 100, 1),
            "wr_100":           round(self.wr_rolling(100) * 100, 1),
            "profit_factor":    self.profit_factor(100),
            "expectativa":      self.expectativa(100),
            "sharpe_50":        self.sharpe_simple(50),
            "pnl_total":        round(self._pnl_total, 2),
            "max_dd":           round(self._max_dd, 2),
            "max_racha_win":    self._max_racha_win,
            "max_racha_loss":   self._max_racha_loss,
            "racha_win_actual": self._racha_win,
            "racha_loss_actual":self._racha_loss,
            "wr_por_votos":     self.wr_por_votos(200),
            "wr_por_activo":    self.wr_por_activo(200),
            "wr_por_regimen":   self.wr_por_regimen(200),
        }

    def resumen_texto(self, idioma: str = "es") -> str:
        """Resumen hablable de las métricas clave."""
        r = self.reporte_completo()
        if r["total_trades"] == 0:
            if idioma == "en":
                return "No trades registered yet, sir."
            return "No hay trades registrados aún, señor."

        if idioma == "en":
            return (
                f"Performance report: {r['total_trades']} total trades, "
                f"WR {r['wr_total']:.0f}% (last 20: {r['wr_20']:.0f}%). "
                f"Profit factor: {r['profit_factor']:.2f}. "
                f"Expectancy: ${r['expectativa']:.3f}/trade. "
                f"Sharpe: {r['sharpe_50']:.2f}. "
                f"P&L: ${r['pnl_total']:+.2f}. "
                f"Max drawdown: ${r['max_dd']:.2f}. "
                f"Best streak: {r['max_racha_win']} wins. "
                f"Worst streak: {r['max_racha_loss']} losses, sir."
            )
        return (
            f"Reporte de rendimiento: {r['total_trades']} trades totales, "
            f"WR {r['wr_total']:.0f}% (últimos 20: {r['wr_20']:.0f}%). "
            f"Profit factor: {r['profit_factor']:.2f}. "
            f"Expectativa: ${r['expectativa']:.3f}/trade. "
            f"Sharpe: {r['sharpe_50']:.2f}. "
            f"P&L acumulado: ${r['pnl_total']:+.2f}. "
            f"Max drawdown: ${r['max_dd']:.2f}. "
            f"Mejor racha: {r['max_racha_win']} wins. "
            f"Peor racha: {r['max_racha_loss']} pérdidas, señor."
        )

    # Muestra mínima para que un "mejor" signifique algo. Por debajo de esto
    # lo que se mide es suerte, no habilidad: una hora con 2 aciertos da 100%
    # de win rate y no prueba absolutamente nada.
    _MIN_N_MEJOR = 12

    @staticmethod
    def _mejor_fiable(dic: dict, min_n: int) -> tuple:
        """El mejor por WR **entre los que tienen muestra suficiente**.

        Devuelve (clave, stats, suficiente:bool). Si nadie llega al mínimo,
        devuelve el de mayor n para poder decir la verdad: "aún no sé".
        """
        if not dic:
            return None, None, False
        validos = {k: v for k, v in dic.items() if v.get("n", 0) >= min_n}
        if validos:
            k = max(validos.items(), key=lambda x: (x[1]["wr"], x[1]["n"]))[0]
            return k, validos[k], True
        k = max(dic.items(), key=lambda x: x[1].get("n", 0))[0]
        return k, dic[k], False

    def mejor_momento(self) -> str:
        """La mejor franja/activo/régimen, exigiendo muestra estadística.

        Nunca presume de un 100% logrado con tres operaciones.
        """
        horas   = self.wr_por_hora(300)
        activos = self.wr_por_activo(200)
        regs    = self.wr_por_regimen(200)

        if not horas:
            return "Todavía no hay suficientes datos por hora, señor."

        partes = []
        firmes = 0
        tentativos = []

        h, sh, ok_h = self._mejor_fiable(horas, self._MIN_N_MEJOR)
        if h is not None:
            # La hora se guarda en UTC; se la muestro también en su hora
            # local, que es la que usted mira en el reloj.
            try:
                _off = -int(round((time.timezone if not time.daylight
                                   else time.altzone) / 3600))
            except Exception:
                _off = 0
            h_local = (int(h) + _off) % 24
            etiqueta = f"{int(h):02d}h UTC ({h_local:02d}h suya)"
            if ok_h:
                firmes += 1
                partes.append(f"Mejor hora: {etiqueta} "
                              f"WR={sh['wr']:.0f}% en {sh['n']} ops")
            else:
                tentativos.append(f"hora {etiqueta} ({sh['n']} ops)")

        a, sa, ok_a = self._mejor_fiable(activos, self._MIN_N_MEJOR)
        if a is not None:
            if ok_a:
                firmes += 1
                partes.append(f"mejor activo: {a} WR={sa['wr']:.0f}% "
                              f"en {sa['n']} ops")
            else:
                tentativos.append(f"activo {a} ({sa['n']} ops)")

        r, sr, ok_r = self._mejor_fiable(regs, self._MIN_N_MEJOR)
        if r is not None:
            if ok_r:
                firmes += 1
                partes.append(f"mejor régimen: {r} WR={sr['wr']:.0f}% "
                              f"en {sr['n']} ops")
            else:
                tentativos.append(f"régimen {r} ({sr['n']} ops)")

        if not partes:
            return (f"Aún no puedo decirle cuál es su mejor momento, señor: "
                    f"ninguna franja llega a {self._MIN_N_MEJOR} operaciones. "
                    f"Lo que más he visto es " + ", ".join(tentativos[:3]) +
                    ", pero con tan pocos datos eso es suerte, no patrón. "
                    "Prefiero callarme antes que mandarle a operar por una "
                    "casualidad.")

        texto = " | ".join(partes) + ", señor."
        if tentativos:
            texto += (" Sin datos suficientes todavía para: " +
                      ", ".join(tentativos) + ".")
        return texto

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _guardar(self) -> None:
        if not self._ruta:
            return
        try:
            with self._lock:
                snapshot = list(self._trades)[-500:]   # solo últimos 500 para no crecer infinito
                meta = {
                    "max_racha_win":  self._max_racha_win,
                    "max_racha_loss": self._max_racha_loss,
                    "pnl_pico":       self._pnl_pico,
                    "pnl_total":      self._pnl_total,
                    "max_dd":         self._max_dd,
                }
            data = {"trades": snapshot, "meta": meta}
            with open(self._ruta, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _cargar(self) -> None:
        try:
            with open(self._ruta, encoding="utf-8") as f:
                data = json.load(f)
            for t in data.get("trades", []):
                self._trades.append(t)
            meta = data.get("meta", {})
            self._max_racha_win  = int(meta.get("max_racha_win",  0))
            self._max_racha_loss = int(meta.get("max_racha_loss", 0))
            self._pnl_pico       = float(meta.get("pnl_pico",  0.0))
            self._pnl_total      = float(meta.get("pnl_total", 0.0))
            self._max_dd         = float(meta.get("max_dd",    0.0))
        except Exception:
            pass

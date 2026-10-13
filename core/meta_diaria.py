"""
meta_diaria.py — Meta diaria de ganancia y stop automático de pérdidas.

Litch opera hasta alcanzar la meta de ganancia O el stop de pérdidas,
luego hiberna automáticamente diciendo «He terminado mi tarea, señor.»

Características:
  • Meta de ganancia configurable en $
  • Stop de pérdidas configurable en $
  • P&L en $ reales (monto × payout en WIN, −monto en LOSS)
  • Auto-stop de trading al alcanzar cualquier límite
  • Barra de progreso en tiempo real en el banner
  • Historial de sesiones persistente
"""
import os
import json
import threading
import time
from typing import Optional

_instancia: Optional["MetaDiaria"] = None


class MetaDiaria:
    """Controla la meta diaria de ganancias y el stop de pérdidas."""

    def __init__(self, app):
        self.app          = app
        self._lock        = threading.Lock()
        self._activa      = False
        self._meta_gan    = 0.0
        self._stop_perd   = 0.0
        self._pnl         = 0.0
        self._trades      = 0
        self._wins        = 0
        self._losses      = 0
        self._completada  = False
        self._razon_cierre = ""
        self._hora_inicio  = ""
        self._hora_cierre  = ""
        # Alertas de progreso: anunciar al 50% y 80% de la meta
        self._alerta_50_hecha = False
        self._alerta_80_hecha = False

    # ── Estado ────────────────────────────────────────────────────────────────

    @property
    def activa(self) -> bool:
        return self._activa and not self._completada

    @property
    def pnl(self) -> float:
        return self._pnl

    @property
    def completada(self) -> bool:
        return self._completada

    # ── Configuración ─────────────────────────────────────────────────────────

    def configurar(self, meta_ganancia: float, stop_perdida: float) -> None:
        """Activa la meta diaria con objetivo y stop dados."""
        if meta_ganancia <= 0 or stop_perdida <= 0:
            self.app.log("[Meta] Valores inválidos. Usa montos positivos.")
            return
        with self._lock:
            self._meta_gan    = float(meta_ganancia)
            self._stop_perd   = float(stop_perdida)
            self._pnl         = 0.0
            self._trades      = 0
            self._wins        = 0
            self._losses      = 0
            self._completada  = False
            self._razon_cierre = ""
            self._activa      = True
            self._hora_inicio = time.strftime("%H:%M")
            self._hora_cierre = ""

        a = self.app
        # Reset alertas de progreso al iniciar nueva meta
        self._alerta_50_hecha = False
        self._alerta_80_hecha = False
        a.log(f"[Meta] META DIARIA: +${meta_ganancia:.0f} | Stop: -${stop_perdida:.0f}")
        a.decir(a.txt(
            f"Meta diaria configurada, senor. Objetivo: ganar {meta_ganancia:.0f} dolares "
            f"con stop de perdida en {stop_perdida:.0f}. Empezando operativa ahora.",
            f"Daily target set, sir. Goal: earn ${meta_ganancia:.0f} "
            f"with a stop loss at ${stop_perdida:.0f}. Starting operations now."))

        # Activar trading automáticamente si está apagado
        if not getattr(a, "trading_on", False):
            try:
                a.set_trading(True, hablar=False)
                a.log("[Meta] Trading activado automáticamente.")
            except Exception:
                pass

        self._actualizar_ui()

    def desactivar(self) -> None:
        with self._lock:
            self._activa     = False
            self._completada = False
        self.app.log("[Meta] Meta diaria desactivada.")
        self._actualizar_ui()

    # ── Verificación previa al trade ──────────────────────────────────────────

    def puede_tradear(self) -> tuple:
        """(puede: bool, razon: str). Llamar antes de cada trade."""
        if not self._activa:
            return True, "sin meta configurada"
        if self._completada:
            return False, f"meta completada: {self._razon_cierre}"
        if self._pnl >= self._meta_gan:
            return False, f"meta alcanzada: +${self._pnl:.2f}"
        if self._pnl <= -self._stop_perd:
            return False, f"stop de perdida: ${self._pnl:.2f}"
        return True, "OK"

    # ── Registro de resultados ────────────────────────────────────────────────

    def registrar_resultado(self, acierto: bool,
                             monto: float, payout: float = 0.85) -> None:
        """Registra el P&L real del trade y verifica límites."""
        if not self._activa or self._completada:
            return

        with self._lock:
            self._trades += 1
            if acierto:
                self._wins += 1
                self._pnl  += monto * payout
            else:
                self._losses += 1
                self._pnl    -= monto

            pnl_snap = self._pnl

        a = self.app
        signo    = "+" if pnl_snap >= 0 else ""
        progreso = min(100, int(abs(pnl_snap) / max(
            self._meta_gan if pnl_snap >= 0 else self._stop_perd, 0.01) * 100))
        barra    = "█" * (progreso // 10) + "░" * (10 - progreso // 10)

        a.log(f"[Meta] {'WIN' if acierto else 'LOSS'} ${monto:.0f} | "
              f"P&L: {signo}${pnl_snap:.2f} / "
              f"{'${:.0f}'.format(self._meta_gan) if pnl_snap >= 0 else '-${:.0f}'.format(self._stop_perd)} "
              f"[{barra}] {progreso}%")

        self._actualizar_ui()

        # ── Alertas de progreso (50% y 80% de la meta) ───────────────────
        if pnl_snap > 0 and self._meta_gan > 0:
            pct_meta = pnl_snap / self._meta_gan
            if pct_meta >= 0.80 and not self._alerta_80_hecha:
                self._alerta_80_hecha = True
                restante = self._meta_gan - pnl_snap
                a.decir(a.txt(
                    f"Senor, ya llevamos el ochenta por ciento de la meta. "
                    f"Solo faltan {restante:.0f} dolares. Casi llegamos.",
                    f"Sir, we're at 80% of the daily target. "
                    f"Only ${restante:.0f} to go."))
            elif pct_meta >= 0.50 and not self._alerta_50_hecha:
                self._alerta_50_hecha = True
                restante = self._meta_gan - pnl_snap
                a.decir(a.txt(
                    f"Senor, vamos a la mitad de la meta. "
                    f"Restan {restante:.0f} dolares. Buen ritmo.",
                    f"Sir, we're halfway to the daily target. "
                    f"${restante:.0f} remaining. Good pace."))

        # ── Verificar condiciones de parada ───────────────────────────────
        if pnl_snap >= self._meta_gan:
            self._completar("META_ALCANZADA")
        elif pnl_snap <= -self._stop_perd:
            self._completar("STOP_PERDIDA")

    # ── Completar sesión ──────────────────────────────────────────────────────

    def _completar(self, razon: str) -> None:
        with self._lock:
            if self._completada:
                return        # evitar doble disparo
            self._completada   = True
            self._razon_cierre = razon
            self._hora_cierre  = time.strftime("%H:%M")
            pnl_snap   = self._pnl
            wins_snap  = self._wins
            losses_snap = self._losses
            trades_snap = self._trades

        a    = self.app
        sign = "+" if pnl_snap >= 0 else ""
        pnl_str = f"{sign}${pnl_snap:.2f}"

        if razon == "META_ALCANZADA":
            a.log(
                f"[Meta] ✓ META ALCANZADA: {pnl_str} | "
                f"{wins_snap}W/{losses_snap}L en {trades_snap} trades | "
                f"{self._hora_inicio}→{self._hora_cierre}")
            a.decir(a.txt(
                f"Meta diaria alcanzada, senor. {pnl_str} en {trades_snap} trades "
                f"con {wins_snap} aciertos. He terminado con mi tarea. "
                f"Voy a invernar hasta que me asignes una nueva.",
                f"Daily target reached, sir. {pnl_str} in {trades_snap} trades "
                f"with {wins_snap} wins. Task complete. "
                f"Going to hibernate until you assign a new one."))
        else:
            a.log(
                f"[Meta] ✗ STOP DE PERDIDA: {pnl_str} | "
                f"{wins_snap}W/{losses_snap}L en {trades_snap} trades | "
                f"{self._hora_inicio}→{self._hora_cierre}")
            a.decir(a.txt(
                f"Stop de perdida alcanzado: {pnl_str} en {trades_snap} operaciones. "
                f"Suspendiendo trading para proteger el capital. "
                f"Esperando nuevas instrucciones, senor.",
                f"Stop loss reached: {pnl_str} in {trades_snap} trades. "
                f"Suspending trading to protect capital. "
                f"Awaiting new instructions, sir."))

        # Parar trading automáticamente
        try:
            a.set_trading(False, hablar=False)
        except Exception:
            pass

        # Guardar historial de sesión
        self._guardar_sesion(razon, pnl_snap, wins_snap, losses_snap, trades_snap)
        self._actualizar_ui()

        # Registrar sesión en la base de conocimiento de Litch
        try:
            bc = getattr(a, "conocimiento", None)
            if bc:
                activo = getattr(a, "mem", {}).get("config", {}).get("activo", "desconocido")
                modo   = "practica" if getattr(getattr(a, "modo_practica", None), "activo", False) else "real"
                bc.registrar_sesion(
                    trades=trades_snap, wins=wins_snap,
                    pnl=pnl_snap, activo=activo, modo=modo)
        except Exception:
            pass

    def _guardar_sesion(self, razon, pnl, wins, losses, trades):
        try:
            from . import memoria as _mem
            ruta = os.path.join(_mem.ruta_memoria_ap(), "meta_historial.json")
            try:
                with open(ruta, encoding="utf-8") as f:
                    hist = json.load(f)
            except Exception:
                hist = []
            hist.append({
                "fecha":    time.strftime("%Y-%m-%d"),
                "inicio":   self._hora_inicio,
                "cierre":   self._hora_cierre,
                "razon":    razon,
                "meta_gan": self._meta_gan,
                "stop":     self._stop_perd,
                "pnl":      round(pnl, 2),
                "wins":     wins,
                "losses":   losses,
                "trades":   trades,
            })
            if len(hist) > 90:
                hist = hist[-90:]
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(hist, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── UI ────────────────────────────────────────────────────────────────────

    def _actualizar_ui(self) -> None:
        try:
            self.app.interfaz.root.after(
                0, lambda: self.app.interfaz._actualizar_banner_meta())
        except Exception:
            pass

    # ── Estadísticas ─────────────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "activa":      self._activa,
            "completada":  self._completada,
            "razon":       self._razon_cierre,
            "meta_gan":    self._meta_gan,
            "stop_perd":   self._stop_perd,
            "pnl":         round(self._pnl, 2),
            "trades":      self._trades,
            "wins":        self._wins,
            "losses":      self._losses,
            "hora_inicio": self._hora_inicio,
            "hora_cierre": self._hora_cierre,
        }

    def resumen(self) -> str:
        if not self._activa:
            return "Meta: no configurada"
        s   = self.stats()
        sgn = "+" if s["pnl"] >= 0 else ""
        return (f"Meta [{('DONE' if s['completada'] else 'ACTIVA')}] "
                f"{sgn}${s['pnl']:.2f} / ${s['meta_gan']:.0f} | "
                f"{s['wins']}W {s['losses']}L")

    def historial(self, n: int = 10) -> list:
        try:
            from . import memoria as _mem
            ruta = os.path.join(_mem.ruta_memoria_ap(), "meta_historial.json")
            with open(ruta, encoding="utf-8") as f:
                return json.load(f)[-n:]
        except Exception:
            return []

    def recomendar_meta(self) -> dict:
        """Analiza el historial para recomendar meta y stop realistas.

        Usa el percentil 60 del P&L de sesiones ganadoras como meta
        y el percentil 60 del P&L de sesiones perdedoras como stop.
        Retorna {"meta_sugerida": float, "stop_sugerido": float, "sesiones": int,
                 "wr_historico": float, "texto": str}.
        """
        hist = self.historial(30)
        if len(hist) < 5:
            return {"meta_sugerida": 0, "stop_sugerido": 0, "sesiones": len(hist),
                    "wr_historico": 0, "texto": "Historial insuficiente (< 5 sesiones)."}
        ganancias = [s["pnl"] for s in hist if s.get("pnl", 0) > 0]
        perdidas  = [abs(s["pnl"]) for s in hist if s.get("pnl", 0) < 0]
        wins      = sum(1 for s in hist if s.get("razon") == "META_ALCANZADA")
        wr        = wins / len(hist)

        if ganancias:
            ganancias_sorted = sorted(ganancias)
            p60_idx = max(0, int(len(ganancias_sorted) * 0.60) - 1)
            meta_sug = ganancias_sorted[p60_idx]
        else:
            meta_sug = 0.0

        if perdidas:
            perdidas_sorted = sorted(perdidas)
            p60_idx = max(0, int(len(perdidas_sorted) * 0.60) - 1)
            stop_sug = perdidas_sorted[p60_idx]
        else:
            stop_sug = meta_sug * 0.5 if meta_sug else 0.0

        texto = (
            f"Basado en {len(hist)} sesiones con WR={wr:.0%}: "
            f"meta sugerida +${meta_sug:.0f}, "
            f"stop sugerido -${stop_sug:.0f}."
        )
        return {
            "meta_sugerida": round(meta_sug, 2),
            "stop_sugerido": round(stop_sug, 2),
            "sesiones":      len(hist),
            "wr_historico":  round(wr * 100, 1),
            "texto":         texto,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

def obtener(app=None) -> Optional[MetaDiaria]:
    global _instancia
    if _instancia is None and app is not None:
        _instancia = MetaDiaria(app)
    return _instancia

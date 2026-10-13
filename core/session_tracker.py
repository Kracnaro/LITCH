"""
session_tracker.py — Seguimiento de rendimiento por sesión de mercado.

Litch aprende QUÉ FRANJAS HORARIAS son históricamente rentables y ajusta
sus parámetros dinámicamente. El corazón del módulo es una matriz de
win-rates por slot de 30 minutos (48 slots × día).

Funciones principales:
  • Registrar resultado de cada trade con su hora
  • Calcular factor de confianza por franja horaria (0.5 → 1.5)
  • Detectar "horas muertas" (< 45% WR con muestra suficiente) → sugerir pausa
  • Calcular VOTOS_MIN dinámico según la franja actual
  • Serializar a JSON para sobrevivir reinicios

Marcos de sesión (UTC):
  Asian   00:00 – 06:59  (OTC, spread alto, ruido)
  London  07:00 – 12:59  (tendencias limpias, buen volumen)
  Overlap 13:00 – 16:59  (London + NY, máxima liquidez)
  NY      17:00 – 19:59  (NY solo)
  Cierre  20:00 – 23:59  (volatilidad decae)
"""

import json
import os
import threading
import time
from collections import defaultdict


_SLOTS_DIA    = 48          # 24h × 2 slots/hora = 30 min cada slot
_MIN_MUESTRAS = 6           # mínimo trades para calcular factor con confianza
_SLOT_MALO    = 0.44        # WR bajo este umbral → slot "peligroso"
_RUTA_DEFAULT = None        # se asigna al instanciar

# ── Sesiones de mercado ───────────────────────────────────────────────────────
SESIONES = {
    "asian":   list(range(0, 14)),       # slots 0-13  = 00:00-06:59
    "london":  list(range(14, 26)),      # slots 14-25 = 07:00-12:59
    "overlap": list(range(26, 34)),      # slots 26-33 = 13:00-16:59
    "ny":      list(range(34, 40)),      # slots 34-39 = 17:00-19:59
    "cierre":  list(range(40, 48)),      # slots 40-47 = 20:00-23:59
}

# Factor de calidad base por sesión (multiplica el WR esperado)
_FACTOR_SESION = {
    "asian":   0.75,
    "london":  1.05,
    "overlap": 1.20,
    "ny":      1.00,
    "cierre":  0.85,
    "neutral": 1.00,
}


def _slot_actual() -> int:
    """Slot 0-47 según hora UTC actual (cada 30 minutos)."""
    t = time.gmtime()
    return t.tm_hour * 2 + (1 if t.tm_min >= 30 else 0)


def _nombre_sesion(slot: int) -> str:
    for nombre, slots in SESIONES.items():
        if slot in slots:
            return nombre
    return "neutral"


class SessionTracker:
    """
    Rastreador de rendimiento por franja horaria.

    Uso:
        st = SessionTracker(ruta="ruta/session_data.json")
        st.registrar(resultado="WIN", votos=6)
        factor = st.factor_confianza()           # 0.5 – 1.5
        ok, motivo = st.slot_viable()            # ¿buena hora para operar?
        votos_min = st.votos_min_dinamico(base=5)
    """

    def __init__(self, ruta: str):
        self.ruta  = ruta
        self._lock = threading.Lock()
        # stats[slot] = {"W": int, "L": int, "n": int}
        self._stats: dict[int, dict] = defaultdict(lambda: {"W": 0, "L": 0, "n": 0})
        self._cargar()

    # ── API pública ───────────────────────────────────────────────────────────

    def registrar(self, resultado: str, votos: int = 0,
                  slot: int | None = None) -> None:
        """Registra un trade. resultado = 'WIN' o 'LOSS'."""
        s  = slot if slot is not None else _slot_actual()
        es_win = resultado.upper() == "WIN"
        with self._lock:
            d = self._stats[s]
            d["n"] += 1
            if es_win:
                d["W"] += 1
            else:
                d["L"] += 1
        # Guardar de forma asíncrona cada 3 registros (bajo costo I/O)
        self._guardar_async()

    def factor_confianza(self, slot: int | None = None) -> float:
        """
        Factor de confianza del slot actual (0.50 – 1.50).

        1.00 = rendimiento esperado neutro
        > 1.0 = franja históricamente buena
        < 1.0 = franja históricamente mala
        """
        s      = slot if slot is not None else _slot_actual()
        sesion = _nombre_sesion(s)
        base   = _FACTOR_SESION.get(sesion, 1.0)

        with self._lock:
            d = self._stats[s]
            n = d["n"]

        if n < _MIN_MUESTRAS:
            return base  # sin datos suficientes → factor base de la sesión

        wr       = d["W"] / n
        # Factor histórico escalado: WR 0.5 → factor 1.0; WR 0.65 → 1.3
        factor_h = max(0.5, min(1.5, 1.0 + (wr - 0.50) * 2.0))
        # Combinar factor de sesión con factor histórico (70% histórico, 30% base)
        return round(factor_h * 0.7 + base * 0.3, 3)

    def slot_viable(self, slot: int | None = None) -> tuple[bool, str]:
        """
        Devuelve (viable: bool, motivo: str).

        No viable si:
          - WR histórico < _SLOT_MALO con ≥ _MIN_MUESTRAS observaciones
        """
        s = slot if slot is not None else _slot_actual()
        with self._lock:
            d = self._stats[s]
            n = d["n"]

        hora_utc = s // 2
        minutos  = "30" if s % 2 else "00"
        etiq     = f"{hora_utc:02d}:{minutos} UTC ({_nombre_sesion(s)})"

        if n < _MIN_MUESTRAS:
            return True, f"sin datos para {etiq} ({n} obs)"

        wr = d["W"] / n
        if wr < _SLOT_MALO:
            return (False,
                    f"slot {etiq} → WR={wr:.0%} ({n} obs) — historial negativo")
        return (True,
                f"slot {etiq} → WR={wr:.0%} ({n} obs) ✓")

    def votos_min_dinamico(self, base: int = 5, slot: int | None = None) -> int:
        """
        Ajusta el mínimo de votos requeridos según la calidad de la franja.

        Lógica:
          factor ≥ 1.10 → base - 1  (franja buena, relajar un poco)
          factor 0.90-1.09 → base   (franja neutra, mantener)
          factor < 0.90  → base + 1  (franja mala, exigir más)
        Rango: nunca < 4 ni > 7
        """
        f = self.factor_confianza(slot)
        if f >= 1.10:
            return max(4, base - 1)
        if f < 0.90:
            return min(7, base + 1)
        return base

    def stats_completos(self) -> dict:
        """Diccionario completo con WR por slot y por sesión."""
        resumen_sesiones: dict[str, dict] = {}
        for sesion, slots in SESIONES.items():
            total_w = total_l = total_n = 0
            for s in slots:
                d = self._stats.get(s, {"W": 0, "L": 0, "n": 0})
                total_w += d["W"]
                total_l += d["L"]
                total_n += d["n"]
            if total_n >= _MIN_MUESTRAS:
                resumen_sesiones[sesion] = {
                    "n":   total_n,
                    "wr":  round(total_w / total_n * 100, 1),
                    "W":   total_w,
                    "L":   total_l,
                }
        return {
            "slot_actual":   _slot_actual(),
            "sesion_actual": _nombre_sesion(_slot_actual()),
            "factor_actual": self.factor_confianza(),
            "sesiones":      resumen_sesiones,
        }

    def mejores_franjas(self, top: int = 3) -> list[dict]:
        """Devuelve los top N slots con mayor WR (con muestra suficiente)."""
        resultados = []
        with self._lock:
            stats_copia = dict(self._stats)
        for s, d in stats_copia.items():
            if d["n"] >= _MIN_MUESTRAS:
                hora_utc = s // 2
                mins     = "30" if s % 2 else "00"
                resultados.append({
                    "slot":    s,
                    "hora":    f"{hora_utc:02d}:{mins} UTC",
                    "sesion":  _nombre_sesion(s),
                    "wr":      round(d["W"] / d["n"] * 100, 1),
                    "n":       d["n"],
                })
        return sorted(resultados, key=lambda x: -x["wr"])[:top]

    def peores_franjas(self, bottom: int = 3) -> list[dict]:
        """Devuelve los bottom N slots con menor WR (con muestra suficiente)."""
        resultados = []
        with self._lock:
            stats_copia = dict(self._stats)
        for s, d in stats_copia.items():
            if d["n"] >= _MIN_MUESTRAS:
                hora_utc = s // 2
                mins     = "30" if s % 2 else "00"
                resultados.append({
                    "slot":    s,
                    "hora":    f"{hora_utc:02d}:{mins} UTC",
                    "sesion":  _nombre_sesion(s),
                    "wr":      round(d["W"] / d["n"] * 100, 1),
                    "n":       d["n"],
                })
        return sorted(resultados, key=lambda x: x["wr"])[:bottom]

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _cargar(self) -> None:
        if not os.path.exists(self.ruta):
            return
        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            for k, v in datos.items():
                self._stats[int(k)] = v
        except Exception as e:
            print(f"[SessionTracker] Error cargando: {e}")

    def _guardar(self) -> None:
        try:
            with self._lock:
                snapshot = {str(k): v for k, v in self._stats.items()}
            with open(self.ruta, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False)
        except Exception as e:
            print(f"[SessionTracker] Error guardando: {e}")

    def _guardar_async(self) -> None:
        threading.Thread(target=self._guardar, daemon=True,
                         name="SessionSave").start()

    # ── Análisis proactivo de sesión ──────────────────────────────────────────

    def alerta_sesion(self) -> str | None:
        """
        Genera un mensaje de alerta proactivo si hay algo importante que
        el usuario deba saber sobre la sesión actual. Retorna str o None.

        Condiciones que generan alerta:
          1. Slot actual con WR histórico < 44% y ≥ 6 observaciones
          2. Cambio de sesión de mercado en los próximos 5 minutos
          3. Sesión 'asian' con factor < 0.80 (ruido conocido)
          4. Sesión 'overlap' activa (máxima liquidez — positivo)
        """
        slot    = _slot_actual()
        sesion  = _nombre_sesion(slot)
        factor  = self.factor_confianza(slot)
        viable, motivo_slot = self.slot_viable(slot)

        # Alerta 1: slot con mal historial
        if not viable and factor < 0.80:
            with self._lock:
                d = self._stats[slot]
                n = d["n"]
                wr = d["W"] / max(n, 1)
            hora_utc = slot // 2
            mins     = "30" if slot % 2 else "00"
            return (f"Señor, históricamente las {hora_utc:02d}:{mins} UTC "
                    f"no son buena hora para operar: {wr:.0%} de acierto "
                    f"en {n} trades anteriores. Considera pausar o cambiar de activo.")

        # Alerta 2: cambio de sesión en ≤5 min
        mins_actuales = time.gmtime().tm_min
        slot_next = (slot + 1) % _SLOTS_DIA
        sesion_next = _nombre_sesion(slot_next)
        if sesion_next != sesion and mins_actuales >= 25 and mins_actuales <= 30:
            return (f"Señor, en unos minutos cambiamos de sesión {sesion.upper()} → "
                    f"{sesion_next.upper()}. El comportamiento del mercado puede cambiar.")

        # Alerta 3: sesión asiática (ruido)
        if sesion == "asian" and factor < 0.80:
            return ("Señor, estamos en sesión asiática — mayor ruido y spreads altos. "
                    "Si los resultados son inconsistentes, es normal a esta hora.")

        # Alerta 4 (positiva): overlap London-NY
        if sesion == "overlap" and factor > 1.10:
            return ("Señor, entramos en la zona de máxima liquidez: overlap London-NY. "
                    f"Mi historial aquí es de {factor:.0%} sobre el baseline. Buen momento.")

        return None

    def resumen_sesion_texto(self) -> str:
        """Texto compacto con estado actual de sesión para el log de LITCH."""
        slot   = _slot_actual()
        sesion = _nombre_sesion(slot)
        factor = self.factor_confianza(slot)
        viable, motivo = self.slot_viable(slot)
        with self._lock:
            d = self._stats[slot]
        wr_txt = f"WR={d['W']/max(d['n'],1):.0%}({d['n']})" if d["n"] >= 3 else "sin datos"
        icon   = "✓" if viable else "⚠"
        hora_utc = slot // 2
        return (f"[Sesión] {sesion.upper()} {hora_utc:02d}h UTC "
                f"factor={factor:.2f} {wr_txt} {icon}")

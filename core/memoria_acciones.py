"""
memoria_acciones.py — La memoria de Litch para Wall Street.

Litch ya recordaba patrones de opciones binarias (fallo_db). Este módulo le
da la MISMA capacidad de aprendizaje para ACCIONES, que es un juego
distinto: aquí importa el setup completo (activo + tendencia + RSI + hora +
ratio), no solo si la vela siguiente subió.

QUÉ MEMORIZA:
  · Cada operación con su CONTEXTO COMPLETO (setup, indicadores, hora).
  · Los setups que GANAN → los refuerza y los prioriza.
  · Los setups que PIERDEN → los veta para no repetir el error.
  · El resultado en R (múltiplos de riesgo), no solo en dólares.

CÓMO APRENDE (la regla honesta):
  Un setup necesita mínimo 6 observaciones para considerarse "dorado" o
  "peligroso". Con menos, es ruido con apariencia de señal. Y el win rate
  siempre se reporta con su intervalo de confianza.

Se guarda en MEMORIA_AP/memoria_acciones.json y sobrevive reinicios.
"""

from __future__ import annotations

import json
import os
import threading
import time

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA_JSON = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "memoria_acciones.json")

MIN_OBSERVACIONES = 6      # mínimo para juzgar un setup
WR_DORADO         = 0.60   # ≥60% de acierto = setup dorado
WR_PELIGROSO      = 0.35   # ≤35% = setup a evitar
MAX_OPERACIONES   = 2000   # tope de historial


class MemoriaAcciones:
    def __init__(self):
        self._lock = threading.Lock()
        self._ops: list[dict] = []
        self._cargar()

    # ── Registro de operaciones ─────────────────────────────────────────────

    def registrar(self, *, simbolo: str, direccion: str, entrada: float,
                  stop: float, objetivo: float, cantidad: int,
                  contexto: dict = None) -> str:
        """Registra una operación ABIERTA. Devuelve su id."""
        # ID único garantizado: varias operaciones en el mismo segundo NO
        # pueden compartir id (bug detectado en pruebas: se sobreescribían).
        with self._lock:
            self._contador = getattr(self, "_contador", 0) + 1
            _n = self._contador
        op_id = f"{simbolo}-{int(time.time())}-{_n}"
        ctx = dict(contexto or {})
        op = {
            "id": op_id, "simbolo": simbolo, "direccion": direccion,
            "entrada": entrada, "stop": stop, "objetivo": objetivo,
            "cantidad": cantidad,
            "setup": self._clave_setup(simbolo, direccion, ctx),
            "contexto": ctx,
            "abierta": True, "resultado": None, "r_multiplo": 0.0,
            "ts_apertura": time.strftime("%Y-%m-%d %H:%M:%S"),
            "hora_utc": int(time.gmtime().tm_hour),
            "dia_semana": time.localtime().tm_wday,
        }
        with self._lock:
            self._ops.append(op)
            if len(self._ops) > MAX_OPERACIONES:
                del self._ops[:-MAX_OPERACIONES]
        self._guardar()
        return op_id

    def cerrar(self, op_id: str, precio_salida: float,
               motivo: str = "") -> dict | None:
        """Cierra una operación y calcula su resultado en R."""
        with self._lock:
            op = next((o for o in self._ops if o["id"] == op_id), None)
            if op is None or not op["abierta"]:
                return None
            entrada = float(op["entrada"])
            stop    = float(op["stop"])
            riesgo  = abs(entrada - stop) or 1e-9
            if op["direccion"] == "COMPRA":
                ganancia = float(precio_salida) - entrada
            else:
                ganancia = entrada - float(precio_salida)
            r = ganancia / riesgo
            op.update({
                "abierta": False,
                "precio_salida": float(precio_salida),
                "r_multiplo": round(r, 2),
                "resultado": "WIN" if r > 0 else "LOSS",
                "motivo_cierre": motivo,
                "ts_cierre": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
        self._guardar()
        return op

    # ── Aprendizaje: qué gana y qué pierde ──────────────────────────────────

    @staticmethod
    def _clave_setup(simbolo: str, direccion: str, ctx: dict) -> str:
        """Clave del setup: lo que Litch reconocerá la próxima vez.

        Ejemplo: 'SPY|COMPRA|tend_alcista|rsi_bajo|kz_ny'
        """
        partes = [simbolo, direccion]
        tend = ctx.get("tendencia")
        if tend:
            partes.append(f"tend_{tend}")
        rsi = ctx.get("rsi")
        if rsi is not None:
            try:
                r = float(rsi)
                partes.append("rsi_bajo" if r < 35 else
                              "rsi_alto" if r > 65 else "rsi_medio")
            except Exception:
                pass
        if ctx.get("sesion"):
            partes.append(f"ses_{ctx['sesion']}")
        return "|".join(partes)

    def veredicto_setup(self, simbolo: str, direccion: str,
                        contexto: dict = None) -> dict:
        """¿Este setup me ha ganado o perdido antes?

        Devuelve {"tipo": "dorado"|"peligroso"|"neutral", "wr": %,
                  "n": int, "r_medio": float, "mensaje": str}
        """
        clave = self._clave_setup(simbolo, direccion, contexto or {})
        with self._lock:
            iguales = [o for o in self._ops
                       if not o["abierta"] and o.get("setup") == clave]
        n = len(iguales)
        wins = sum(1 for o in iguales if o["resultado"] == "WIN")
        wr = (wins / n) if n else 0.0
        r_medio = (sum(float(o.get("r_multiplo", 0)) for o in iguales) / n
                   if n else 0.0)

        if n < MIN_OBSERVACIONES:
            # Se devuelven las cifras REALES, no ceros.
            #
            # Antes esto devolvía wr=0.0 y r_medio=0.0 como relleno. El
            # mensaje avisaba de la muestra insuficiente, pero cualquier
            # código que leyera solo "wr" mostraría «0% de acierto» en un
            # setup que quizá ganó su única operación. Devolver el dato
            # real y marcar aparte que la muestra es corta es más honesto
            # y no engaña a quien lea mal.
            return {"tipo": "neutral", "wr": round(wr * 100, 1), "n": n,
                    "r_medio": round(r_medio, 2), "suficiente": False,
                    "mensaje": (f"Solo {n} operación(es) con este setup: "
                                f"muestra insuficiente para juzgarlo "
                                f"(mínimo {MIN_OBSERVACIONES}). Lo que "
                                f"lleve hasta ahora es ruido, no señal.")}

        if wr >= WR_DORADO and r_medio > 0:
            return {"tipo": "dorado", "wr": round(wr * 100, 1), "n": n,
                    "r_medio": round(r_medio, 2),
                    "mensaje": (f"★ Setup DORADO: {wr*100:.0f}% de acierto en "
                                f"{n} operaciones, {r_medio:+.2f}R promedio. "
                                f"Lo priorizo.")}
        if wr <= WR_PELIGROSO or r_medio < -0.3:
            return {"tipo": "peligroso", "wr": round(wr * 100, 1), "n": n,
                    "r_medio": round(r_medio, 2),
                    "mensaje": (f"✗ Setup PELIGROSO: {wr*100:.0f}% en {n} "
                                f"operaciones, {r_medio:+.2f}R. Lo evito para "
                                f"no repetir el error.")}
        return {"tipo": "neutral", "wr": round(wr * 100, 1), "n": n,
                "r_medio": round(r_medio, 2),
                "mensaje": (f"Setup neutral: {wr*100:.0f}% en {n} "
                            f"operaciones. Decido con los motores.")}

    def mejores_setups(self, top: int = 5) -> list[dict]:
        """Los setups que más ganan (para priorizarlos)."""
        return self._ranking(mejores=True, top=top)

    def peores_setups(self, top: int = 5) -> list[dict]:
        """Los setups que más pierden (para vetarlos)."""
        return self._ranking(mejores=False, top=top)

    def _ranking(self, mejores: bool, top: int) -> list[dict]:
        with self._lock:
            cerradas = [o for o in self._ops if not o["abierta"]]
        mapa: dict[str, dict] = {}
        for o in cerradas:
            k = o.get("setup", "?")
            d = mapa.setdefault(k, {"setup": k, "n": 0, "wins": 0, "r": 0.0})
            d["n"] += 1
            d["wins"] += 1 if o["resultado"] == "WIN" else 0
            d["r"] += float(o.get("r_multiplo", 0))
        res = []
        for d in mapa.values():
            if d["n"] < MIN_OBSERVACIONES:
                continue
            d["wr"] = round(d["wins"] / d["n"] * 100, 1)
            d["r_medio"] = round(d["r"] / d["n"], 2)
            res.append(d)
        res.sort(key=lambda x: x["r_medio"], reverse=mejores)
        return res[:top]

    # ── Estadísticas honestas ───────────────────────────────────────────────

    def resumen(self, idioma: str = "es") -> str:
        with self._lock:
            cerradas = [o for o in self._ops if not o["abierta"]]
            abiertas = [o for o in self._ops if o["abierta"]]
        n = len(cerradas)
        if n == 0:
            return ("Aún no tengo operaciones de acciones registradas, señor. "
                    "Cuando opere en Wall Street iré memorizando qué setups "
                    "ganan y cuáles pierden.")
        wins = sum(1 for o in cerradas if o["resultado"] == "WIN")
        wr = wins / n
        r_total = sum(float(o.get("r_multiplo", 0)) for o in cerradas)
        # Intervalo de confianza (Manual 13, error B1)
        import math
        se = math.sqrt(max(wr * (1 - wr), 1e-9) / n)
        bajo, alto = max(0, wr - 1.96 * se), min(1, wr + 1.96 * se)

        partes = [
            f"Memoria de acciones: {n} operaciones cerradas "
            f"({len(abiertas)} abiertas).",
            f"Win rate {wr*100:.0f}% (real entre {bajo*100:.0f}% y "
            f"{alto*100:.0f}% — dimensiono sobre el límite inferior).",
            f"Resultado acumulado: {r_total:+.1f}R.",
        ]
        if n < 30:
            partes.append("Menos de 30 operaciones: cualquier conclusión es "
                          "provisional.")
        mej = self.mejores_setups(2)
        if mej:
            partes.append("Mejores setups: " + "; ".join(
                f"{m['setup']} ({m['wr']}%, {m['r_medio']:+.2f}R)" for m in mej))
        peo = self.peores_setups(2)
        if peo:
            partes.append("A evitar: " + "; ".join(
                f"{p['setup']} ({p['wr']}%, {p['r_medio']:+.2f}R)" for p in peo))
        return " ".join(partes)

    # ── Persistencia ────────────────────────────────────────────────────────

    def _cargar(self):
        try:
            with open(_RUTA_JSON, encoding="utf-8") as f:
                self._ops = json.load(f).get("operaciones", [])
        except Exception:
            self._ops = []

    def _guardar(self):
        try:
            os.makedirs(os.path.dirname(_RUTA_JSON), exist_ok=True)
            with self._lock:
                datos = {"operaciones": self._ops,
                         "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")}
            tmp = _RUTA_JSON + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False)
            os.replace(tmp, _RUTA_JSON)
        except Exception:
            pass


# ── Singleton ───────────────────────────────────────────────────────────────

_instancia: MemoriaAcciones | None = None


def obtener() -> MemoriaAcciones:
    global _instancia
    if _instancia is None:
        _instancia = MemoriaAcciones()
    return _instancia

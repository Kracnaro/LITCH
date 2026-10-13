"""
Calibrador de pesos de métodos — Litch pondera sus motores según su precisión reciente.

Problema que resuelve:
  En el consenso de 7 motores, todos contribuyen con peso fijo.
  Pero en la realidad, un motor puede tener 80% de acierto en un activo/período,
  mientras que otro solo alcanza 48%. Darles el mismo voto es un desperdicio.

Solución:
  Ventana deslizante de 60 predicciones por método.
  Cada vez que se registra un resultado, se actualiza el score del método que votó.
  El peso final es proporcional al Brier score (calibración probabilística real).

Mejoras v2:
  • Calibración por contexto (asset × período): EUR/AUD en 60s ≠ SHIB/USD en 5s.
    El calibrador mantiene pesos globales + pesos por contexto (hasta 30 contextos).
    Si el contexto actual tiene ≥ _MIN_OBS_CTX datos, los pesos del contexto pesan
    un 60% y los globales un 40%.
  • Decaimiento configurable por método: métodos rápidos (rl, smc) decaen más
    rápido; métodos lentos (red, pronostico) decaen más despacio.
  • `votar_ponderado(votos_raw, prob_map)` — convierte votos binarios en votos
    ponderados usando los pesos del calibrador, devolviendo un score continuo.

Basado en:
  - Brier (1950): Brier Score para calibración probabilística
  - Gneiting & Raftery (2007): Proper Scoring Rules para ensemble
  - Thomson, Pollock, Jeske (2019): Online recalibration de modelos de trading
"""

import json
import math
import os
import threading


_VENTANA       = 60    # observaciones por método (ventana deslizante)
_VENTANA_CTX   = 30    # ventana más pequeña para contextos específicos
_MIN_OBS       = 8     # mínimo de observaciones para confiar en el peso global
_MIN_OBS_CTX   = 5     # mínimo para usar calibración por contexto
_PESO_BASE     = 1.0   # peso si no hay suficientes datos
_PESO_MIN      = 0.40  # peso mínimo
_PESO_MAX      = 2.50  # peso máximo
_MAX_CONTEXTOS = 40    # máximo de contextos tracked (asset×período)
_MIX_CTX       = 0.60  # 60% contexto + 40% global cuando hay datos de contexto

METODOS = ("markov", "estadist", "red", "pronostico",
           "indicadores", "rl", "smc")

# Tasa de decaimiento por método — rl/smc aprenden rápido (0.93), red/pronostico más lento (0.98)
_DECAY = {
    "markov":      0.96,
    "estadist":    0.97,
    "red":         0.98,
    "pronostico":  0.98,
    "indicadores": 0.96,
    "rl":          0.93,
    "smc":         0.94,
}


class CalibradorMetodos:
    """
    Rastrea la precisión reciente de cada motor y devuelve multiplicadores
    de peso para el consenso de 7 motores de Litch.

    v2: también calibra por contexto (asset × período).
    Thread-safe: usa un Lock interno.
    Persiste en MEMORIA_AP/calibrador_metodos.json.
    """

    def __init__(self, ruta: str = None):
        self._lock  = threading.Lock()
        self._ruta  = ruta
        # Historial global por método: [(acierto: bool, prob: float)]
        self._hist: dict[str, list] = {m: [] for m in METODOS}
        # Historial por contexto: {"EUR/AUD_60": {"markov": [...], ...}}
        self._ctx:  dict[str, dict[str, list]] = {}
        if ruta and os.path.exists(ruta):
            self._cargar()

    # ── Registro ─────────────────────────────────────────────────────────────

    def registrar(self, metodo: str, acierto: bool, prob: float,
                  asset: str = "", periodo: int = 0):
        """
        Registra el resultado de una predicción de un método.

        metodo  : uno de los METODOS
        acierto : True si acertó la dirección
        prob    : probabilidad que asignó el método a su predicción (0..1)
        asset   : activo (p.ej. "EUR/AUD")  — para calibración por contexto
        periodo : período de vela en segundos — para calibración por contexto
        """
        if metodo not in self._hist:
            return
        obs = (bool(acierto), float(prob))
        with self._lock:
            # Historial global
            self._hist[metodo].append(obs)
            if len(self._hist[metodo]) > _VENTANA:
                self._hist[metodo].pop(0)
            # Historial por contexto
            if asset and periodo:
                ctx_key = f"{asset}_{periodo}"
                if ctx_key not in self._ctx:
                    if len(self._ctx) >= _MAX_CONTEXTOS:
                        # Eliminar el contexto con menos muestras
                        peor = min(self._ctx,
                                   key=lambda k: sum(len(v)
                                                     for v in self._ctx[k].values()))
                        del self._ctx[peor]
                    self._ctx[ctx_key] = {m: [] for m in METODOS}
                self._ctx[ctx_key][metodo].append(obs)
                if len(self._ctx[ctx_key][metodo]) > _VENTANA_CTX:
                    self._ctx[ctx_key][metodo].pop(0)
        guardar = (len(self._hist.get(metodo, [])) % 10 == 0)
        if self._ruta and guardar:
            threading.Thread(target=self._guardar, daemon=True,
                             name="CalibSave").start()

    def registrar_batch(self, resultados: dict, acierto: bool,
                        asset: str = "", periodo: int = 0):
        """
        Registra el resultado para múltiples métodos a la vez.
        resultados = {"markov": prob, "red": prob, ...}
        acierto    = True/False
        """
        for metodo, prob in resultados.items():
            if prob is not None:
                self.registrar(metodo, acierto, prob,
                               asset=asset, periodo=periodo)

    # ── Pesos ────────────────────────────────────────────────────────────────

    def pesos_actuales(self, asset: str = "", periodo: int = 0) -> dict:
        """
        Devuelve multiplicadores de peso para cada método.

        Si hay suficientes datos de contexto (asset × período), combina:
          peso_final = _MIX_CTX × peso_contexto + (1 - _MIX_CTX) × peso_global

        Normalizado para que la media sea 1.0.
        """
        with self._lock:
            raw_global = {}
            for m, hist in self._hist.items():
                raw_global[m] = (self._peso_por_brier(hist, m)
                                 if len(hist) >= _MIN_OBS else _PESO_BASE)

            # Intentar combinar con contexto
            ctx_key = f"{asset}_{periodo}" if (asset and periodo) else None
            ctx_data = self._ctx.get(ctx_key, {}) if ctx_key else {}
            raw_ctx = {}
            tiene_ctx = False
            for m in METODOS:
                hist_ctx = ctx_data.get(m, [])
                if len(hist_ctx) >= _MIN_OBS_CTX:
                    raw_ctx[m] = self._peso_por_brier(hist_ctx, m)
                    tiene_ctx  = True
                else:
                    raw_ctx[m] = raw_global[m]

        if tiene_ctx:
            raw = {m: _MIX_CTX * raw_ctx[m] + (1 - _MIX_CTX) * raw_global[m]
                   for m in METODOS}
        else:
            raw = raw_global

        # Normalizar
        media = sum(raw.values()) / len(raw) if raw else 1.0
        if media > 1e-9:
            pesos = {m: max(_PESO_MIN, min(_PESO_MAX, w / media))
                     for m, w in raw.items()}
        else:
            pesos = {m: _PESO_BASE for m in METODOS}
        return pesos

    def votar_ponderado(self, votos_raw: dict, prob_map: dict,
                        asset: str = "", periodo: int = 0) -> float:
        """
        Convierte votos binarios en un score continuo ponderado por calidad.

        votos_raw = {"markov": "V" o "R" o None, ...}
        prob_map  = {"markov": 0.62, ...}  (probabilidad que asignó cada motor)

        Devuelve: score en rango [-7, +7] donde positivo = alcista, negativo = bajista.
        """
        pesos = self.pesos_actuales(asset=asset, periodo=periodo)
        score = 0.0
        for m, voto in votos_raw.items():
            if voto is None:
                continue
            w    = pesos.get(m, 1.0)
            prob = prob_map.get(m, 0.5)
            # Escalar el voto por la confianza probabilística del motor
            confianza = max(0.0, min(1.0, abs(prob - 0.5) * 2.0))
            contrib   = w * (1.0 if voto == "V" else -1.0) * (0.5 + confianza * 0.5)
            score    += contrib
        return round(score, 3)

    @staticmethod
    def _peso_por_brier(hist: list, metodo: str = "") -> float:
        """
        Brier Score ponderado por recencia + win-rate normalizado.

        Usa tasa de decaimiento específica por método (_DECAY).
        WR=65% BS=0.15 → peso≈2.2  |  WR=45% BS=0.35 → peso≈0.40 (mínimo).
        """
        if not hist:
            return _PESO_BASE
        n     = len(hist)
        decay = _DECAY.get(metodo, 0.97)

        pesos_raw = [decay ** (n - 1 - i) for i in range(n)]
        suma_p    = sum(pesos_raw) or 1e-9

        wr_w = sum(w * (1.0 if a else 0.0)
                   for w, (a, _) in zip(pesos_raw, hist)) / suma_p
        bs_w = sum(w * (p - (1.0 if a else 0.0)) ** 2
                   for w, (a, p) in zip(pesos_raw, hist)) / suma_p
        bs_w = max(0.0, min(1.0, bs_w))

        ventaja = max(0.0, wr_w - 0.45) * 2.0
        penaliz = max(0.0, bs_w - 0.20) * 1.5
        calidad = ventaja - penaliz
        peso    = 1.0 + calidad * 3.0
        return float(max(_PESO_MIN, min(_PESO_MAX, peso)))

    def precision_metodo(self, metodo: str) -> float | None:
        """Win rate reciente de un método. None si < _MIN_OBS datos."""
        with self._lock:
            hist = self._hist.get(metodo, [])
        if len(hist) < _MIN_OBS:
            return None
        return sum(1 for a, _ in hist if a) / len(hist)

    def resumen(self) -> str:
        """Texto con el estado de cada método para el log de Litch."""
        pesos = self.pesos_actuales()
        partes = []
        for m in METODOS:
            p      = pesos.get(m, 1.0)
            wr     = self.precision_metodo(m)
            wr_txt = f"{wr*100:.0f}%" if wr is not None else "?"
            n      = len(self._hist.get(m, []))
            partes.append(f"{m}→p={p:.2f}({wr_txt},{n}obs)")
        return " | ".join(partes)

    # ── Persistencia ─────────────────────────────────────────────────────────

    def resumen_contextos(self) -> str:
        """Lista los contextos con más datos para diagnóstico."""
        with self._lock:
            ctx_copia = {k: {m: len(v) for m, v in ctx.items()}
                         for k, ctx in self._ctx.items()}
        if not ctx_copia:
            return "sin datos de contexto aún"
        partes = []
        for ctx_key, m_counts in sorted(
                ctx_copia.items(),
                key=lambda kv: sum(kv[1].values()), reverse=True)[:5]:
            total = sum(m_counts.values())
            partes.append(f"{ctx_key}({total}obs)")
        return " | ".join(partes)

    def _guardar(self):
        if not self._ruta:
            return
        try:
            with self._lock:
                data = {
                    "global": {m: list(self._hist[m]) for m in METODOS},
                    "ctx":    {k: {m: list(v) for m, v in ctx.items()}
                               for k, ctx in self._ctx.items()},
                }
            with open(self._ruta, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _cargar(self):
        try:
            with open(self._ruta, encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                # Compatible con formato antiguo (solo dict de listas) y nuevo
                if "global" in data:
                    glob = data["global"]
                    ctx  = data.get("ctx", {})
                else:
                    glob = data   # formato antiguo
                    ctx  = {}
                for m in METODOS:
                    raw = glob.get(m, [])
                    self._hist[m] = [(bool(a), float(p)) for a, p in raw][-_VENTANA:]
                for ctx_key, ctx_meths in ctx.items():
                    self._ctx[ctx_key] = {}
                    for m in METODOS:
                        raw = ctx_meths.get(m, [])
                        self._ctx[ctx_key][m] = (
                            [(bool(a), float(p)) for a, p in raw][-_VENTANA_CTX:])
        except Exception:
            pass

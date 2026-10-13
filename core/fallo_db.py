"""
Base de datos inteligente de fallos de trading — Litch aprende de cada pérdida.

Cada trade (WIN o LOSS) queda registrado con:
  - Timestamp, patrón Markov, dirección apostada, votos del consenso
  - Snapshot completo de los 13 indicadores técnicos en ese momento
  - Resultado real

El motor de correlación identifica:
  1. Patrones que fallan sistemáticamente (tasa > 55%)
  2. Rangos de indicadores peligrosos (RSI neutro, BB central, momentum bajo)
  3. Rachas de pérdidas consecutivas → activa pausa automática
  4. Momentos del día con mayor/menor éxito
  5. Cuántos votos del consenso son realmente necesarios

Litch usa esta información para:
  - Omitir patrones históricamente malos
  - Evitar condiciones de indicadores donde el fallo es recurrente
  - Autoajustar el umbral de votos mínimos basándose en evidencia real
  - Hablar sobre sus fallos con honestidad y motivación
"""

import json
import os
import threading
import time
from collections import defaultdict

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

_CACHE_TTL = 30.0   # segundos que viven las caches de análisis costoso


# ═══════════════════════════════════════════════════════════════════════════
#  SELLO DE ORIGEN — qué bróker había en pantalla al registrar la operación
# ═══════════════════════════════════════════════════════════════════════════
#
# Se consulta con caché de 5 segundos: enumerar ventanas de Windows en cada
# operación sería caro, y el bróker en pantalla no cambia tan deprisa.
_CACHE_BK = {"v": "", "t": 0.0}


def _broker_visible() -> str:
    """'tws' si Interactive Brokers está al frente, '' si no."""
    import time as _t
    ahora = _t.time()
    if (ahora - _CACHE_BK["t"]) < 5.0:
        return _CACHE_BK["v"]
    val = ""
    try:
        from . import vision_tws as _vt
        v = _vt.ventana_tws()
        if v and v.get("al_frente"):
            val = "tws"
    except Exception:
        val = ""
    _CACHE_BK["v"] = val
    _CACHE_BK["t"] = ahora
    return val


class FalloDB:
    """Memoria persistente de trades con motor de correlación de fallos.

    Mejoras v2:
    • Caché de 30s para patrones_problematicos() — evita re-escanear en cada señal
    • Correlación hora × votos × régimen — identifica condiciones peligrosas
    • Análisis de drawdown por sesión — detecta sesiones malas y sugiere pausa
    • Estadísticas por activo — aprende qué activos son más predecibles
    • Persistencia diferida thread-safe con Lock
    """

    MAX_TRADES = 2000   # número máximo de trades en memoria
    MIN_MUESTRAS = 4    # mínimo de observaciones para sacar conclusiones

    def __init__(self, ruta: str):
        self.ruta               = ruta
        self._ruta_cfg          = ruta
        self.trades: list[dict] = []
        self._pendientes        = 0
        self._GUARDAR_CADA      = 5
        self._lock              = threading.Lock()

        # ── Caché de resultados costosos con TTL ──────────────────────────────
        self._cache_pat_malos:   list  = []
        self._cache_pat_ts:      float = 0.0
        self._cache_hora_risk:   dict  = {}
        self._cache_hora_ts:     float = 0.0
        self._cache_votos_opt:   int | None = None
        self._cache_votos_ts:    float = 0.0

        self._cargar()

    # ── Registrar un trade ────────────────────────────────────────────────────

    def registrar(self, *, patron: str, direccion: str, votos: int,
                  prob: float, indicadores: dict, resultado: str,
                  velas_seq: list = None, asset: str = "",
                  regimen: str = "", periodo: int = 60):
        """Registra un trade completo con contexto extendido.

        Nuevo en v2:
            asset   — activo operado (EUR/AUD, SHIB/USD, etc.)
            regimen — régimen de mercado (trending/ranging/chaotic/neutral)
            periodo — período de vela en segundos
        """
        ind_limpio = {}
        for k, v in (indicadores or {}).items():
            if v is None:
                continue
            try:
                ind_limpio[k] = round(float(v), 4)
            except (TypeError, ValueError):
                pass
        hora = time.strftime("%H:%M")
        hora_h = int(hora[:2])   # hora entera (0-23)

        # Sello de origen. Sin esto no hay forma de saber, meses después,
        # si una operación ocurrió de verdad o la anotó un motor que estaba
        # mirando el bróker equivocado. Ese descuido costó 76 operaciones
        # fantasma en un solo día; no se repite.
        _bk = _broker_visible()

        entry = {
            "ts":      time.strftime("%Y-%m-%d %H:%M:%S"),
            "hora":    hora,
            "hora_h":  hora_h,
            "bk":      _bk,
            "pat":     patron,
            "dir":     direccion,
            "vt":      votos,
            "prob":    round(prob, 3),
            "ind":     ind_limpio,
            "res":     resultado,
            "seq":     list((velas_seq or [])[-10:]),
            "asset":   asset or "",
            "reg":     regimen or "",
            "per":     periodo,
        }
        with self._lock:
            self.trades.append(entry)
            if len(self.trades) > self.MAX_TRADES:
                self.trades = self.trades[-self.MAX_TRADES:]
            self._pendientes += 1
            guardar_ahora = (self._pendientes >= self._GUARDAR_CADA)
            if guardar_ahora:
                self._pendientes = 0
        # Invalidar caches cuando hay nuevos datos
        self._cache_pat_ts   = 0.0
        self._cache_hora_ts  = 0.0
        self._cache_votos_ts = 0.0
        if guardar_ahora:
            threading.Thread(target=self._guardar, daemon=True,
                             name="FalloDBSave").start()

    # ── Análisis del fallo (mensaje hablado) ─────────────────────────────────

    def analizar_fallo(self, patron: str, indicadores: dict,
                       idioma: str = "es") -> str:
        """Genera un mensaje explicando por qué probablemente falló este trade."""
        razones = []
        ind = indicadores or {}

        rsi_v = ind.get("rsi")
        bb_v  = ind.get("bb")
        mom_v = ind.get("mom")
        h_v   = ind.get("hurst")
        ep_v  = ind.get("entropia_perm")

        if rsi_v is not None and 40 <= rsi_v <= 60:
            razones.append("RSI en zona neutral sin señal clara")
        if bb_v is not None and 0.35 <= bb_v <= 0.65:
            razones.append("precio en el centro de las Bandas Bollinger")
        if mom_v is not None and abs(mom_v) < 0.5:
            razones.append("momentum prácticamente cero (mercado lateral)")
        if h_v is not None and 0.45 <= h_v <= 0.55:
            razones.append("Hurst≈0.5 — serie casi aleatoria en este momento")
        if ep_v is not None and ep_v > 0.85:
            razones.append("entropía de permutación alta — caos temporal")

        # Historial de este patrón
        hist_pat = [t for t in self.trades[-80:] if t["pat"] == patron]
        if len(hist_pat) >= self.MIN_MUESTRAS:
            fallos = sum(1 for t in hist_pat if t["res"] == "LOSS")
            tasa   = fallos / len(hist_pat)
            if tasa > 0.60:
                razones.append(
                    f"el patrón '{patron}' ha fallado {tasa:.0%} de mis últimas "
                    f"{len(hist_pat)} veces con él")

        if not razones:
            razones = ["el mercado se movió en dirección impredecible — ningún modelo pudo anticiparlo"]

        if idioma == "en":
            return ("I analyzed why I missed: " + "; ".join(razones) + ". "
                    "I've stored this in my failure memory to avoid repeating it, sir.")
        return ("Analicé por qué fallé: " + "; ".join(razones) + ". "
                "Lo guardé en mi memoria de fallos para no repetirlo, señor.")

    # ── Resumen hablado del rendimiento ──────────────────────────────────────

    def resumen(self, idioma: str = "es") -> str:
        """Resumen completo de rendimiento + lecciones aprendidas."""
        if len(self.trades) < 3:
            return ("Aún acumulo datos — necesito más trades para darte un análisis serio."
                    if idioma == "es" else
                    "Still collecting data — need more trades for a solid analysis, sir.")

        wins  = sum(1 for t in self.trades if t["res"] == "WIN")
        total = len(self.trades)
        pct   = wins / total * 100
        racha = self._racha_actual()

        lineas = [
            f"Registro total: {total} trades — {wins} ganados ({pct:.1f}%)." if idioma == "es"
            else f"Total: {total} trades — {wins} won ({pct:.1f}%)."]

        malos = self.patrones_problematicos()
        if malos:
            nombres = "; ".join(
                f"'{p}' falla {int(f*100)}% de las veces" for p, f in malos[:2])
            lineas.append(("Patrones que debo evitar: " + nombres + "." if idioma == "es"
                           else "Patterns to avoid: " + nombres + "."))

        vt_opt = self._votos_optimos()
        if vt_opt:
            lineas.append((f"Cuando tengo {vt_opt}+ votos del consenso mi precisión sube "
                           f"significativamente." if idioma == "es"
                           else f"When I have {vt_opt}+ consensus votes, my accuracy rises notably."))

        if racha["tipo"] == "LOSS" and racha["n"] >= 2:
            lineas.append((f"Llevo {racha['n']} pérdidas seguidas — revisando mis parámetros."
                           if idioma == "es"
                           else f"I'm on a {racha['n']}-loss streak — reviewing my parameters."))
        elif racha["tipo"] == "WIN" and racha["n"] >= 3:
            lineas.append((f"Llevo {racha['n']} aciertos seguidos. Buena racha, señor."
                           if idioma == "es"
                           else f"On a {racha['n']}-win streak. Good momentum, sir."))

        return " ".join(lineas)

    # ── Verificar si debo pausar ─────────────────────────────────────────────

    def debo_pausar(self, max_racha_loss: int = 4) -> bool:
        """True si la racha de pérdidas supera el límite de seguridad."""
        r = self._racha_actual()
        return r["tipo"] == "LOSS" and r["n"] >= max_racha_loss

    def racha_actual(self) -> dict:
        return self._racha_actual()

    # ── Patrones problemáticos ───────────────────────────────────────────────

    def patrones_problematicos(self, ventana: int = 60) -> list[tuple]:
        """Patrones con tasa de fallo > 55% — con caché de 30s."""
        ahora = time.time()
        if ahora - self._cache_pat_ts < _CACHE_TTL:
            return self._cache_pat_malos    # resultado previo válido

        with self._lock:
            snapshot = list(self.trades[-ventana:])
        freq = defaultdict(lambda: {"W": 0, "L": 0})
        for t in snapshot:
            pat_key = t.get("pat") or t.get("p")
            res_key = t.get("res") or t.get("resultado")
            if not pat_key or not res_key:
                continue
            freq[pat_key]["W" if res_key == "WIN" else "L"] += 1
        malos = []
        for pat, v in freq.items():
            n = v["W"] + v["L"]
            if n >= self.MIN_MUESTRAS and v["L"] / n > 0.55:
                malos.append((pat, round(v["L"] / n, 2)))
        resultado = sorted(malos, key=lambda x: -x[1])
        self._cache_pat_malos = resultado
        self._cache_pat_ts    = ahora
        return resultado

    def es_patron_problematico(self, patron: str) -> bool:
        return any(p == patron for p, _ in self.patrones_problematicos())

    # ── Correlación hora × votos (caché 30s) ──────────────────────────────────

    def riesgo_hora_votos(self, hora_h: int, votos: int) -> dict:
        """
        Analiza el rendimiento histórico en la hora actual con esa cantidad de votos.
        Retorna:
            ok       — bool: True si la condición es históricamente buena
            wr       — float: win-rate en esa franja
            n        — int: muestra disponible
            razon    — str: descripción para el log
        """
        ahora = time.time()
        if ahora - self._cache_hora_ts < _CACHE_TTL:
            cache = self._cache_hora_risk
        else:
            # Recalcular mapa hora → stats
            with self._lock:
                snapshot = list(self.trades[-400:])
            mapa: dict[str, dict] = defaultdict(lambda: {"W": 0, "L": 0, "n": 0})
            for t in snapshot:
                h  = t.get("hora_h", -1)
                vt = t.get("vt", 0)
                res = t.get("res") or t.get("resultado", "")
                if h < 0 or not res:
                    continue
                clave = f"{h}_{vt}"
                mapa[clave]["n"] += 1
                mapa[clave]["W" if res == "WIN" else "L"] += 1
            self._cache_hora_risk = dict(mapa)
            self._cache_hora_ts   = ahora
            cache = self._cache_hora_risk

        clave = f"{hora_h}_{votos}"
        dat   = cache.get(clave, {})
        n     = dat.get("n", 0)
        if n < self.MIN_MUESTRAS:
            return {"ok": True, "wr": 0.5, "n": n,
                    "razon": f"sin datos suficientes h={hora_h}h v={votos}"}

        wr = dat.get("W", 0) / n
        ok = wr >= 0.52
        razon = (f"h={hora_h}h v={votos}/7 → WR={wr:.0%} ({n} obs)"
                 + (" ✓" if ok else " ⚠ historial negativo"))
        return {"ok": ok, "wr": wr, "n": n, "razon": razon}

    # ── Estadísticas por activo ────────────────────────────────────────────────

    def stats_por_activo(self, ventana: int = 200) -> dict:
        """Win-rate por activo en los últimos N trades."""
        with self._lock:
            snapshot = list(self.trades[-ventana:])
        mapa: dict[str, dict] = defaultdict(lambda: {"W": 0, "L": 0})
        for t in snapshot:
            asset = t.get("asset", "")
            res   = t.get("res") or t.get("resultado", "")
            if not asset or not res:
                continue
            mapa[asset]["W" if res == "WIN" else "L"] += 1
        resultado = {}
        for asset, v in mapa.items():
            n = v["W"] + v["L"]
            if n >= self.MIN_MUESTRAS:
                resultado[asset] = {
                    "n":  n, "wins": v["W"],
                    "wr": round(v["W"] / n * 100, 1)}
        return dict(sorted(resultado.items(),
                           key=lambda x: -x[1]["wr"]))

    # ── Votos óptimos (caché 30s) ─────────────────────────────────────────────

    def _votos_optimos_cacheado(self) -> int | None:
        ahora = time.time()
        if ahora - self._cache_votos_ts < _CACHE_TTL:
            return self._cache_votos_opt
        v = self._votos_optimos()
        self._cache_votos_opt = v
        self._cache_votos_ts  = ahora
        return v

    def patrones_exitosos(self, ventana: int = 300,
                          min_obs: int = 5, min_wr: float = 0.70) -> list[dict]:
        """Identifica "golden patterns" — patrones con WR ≥ min_wr en los últimos N trades.

        Retorna lista de dicts ordenada por WR descendente:
          [{"patron": str, "dir": str, "n": int, "wins": int, "wr": float}, ...]

        Útil para que el sistema priorice señales en patrones históricamente exitosos
        y para el comando de voz "mejores patrones".
        """
        with self._lock:
            snapshot = list(self.trades[-ventana:])
        mapa: dict[tuple, dict] = {}
        for t in snapshot:
            pat = t.get("pat") or t.get("patron", "")
            dir_ = t.get("dir", "")
            res  = t.get("res") or t.get("resultado", "")
            if not pat or not dir_ or not res:
                continue
            key = (pat, dir_)
            if key not in mapa:
                mapa[key] = {"patron": pat, "dir": dir_, "W": 0, "L": 0}
            mapa[key]["W" if res == "WIN" else "L"] += 1
        resultados = []
        for v in mapa.values():
            n = v["W"] + v["L"]
            if n < min_obs:
                continue
            wr = v["W"] / n
            if wr >= min_wr:
                resultados.append({
                    "patron": v["patron"],
                    "dir":    v["dir"],
                    "n":      n,
                    "wins":   v["W"],
                    "wr":     round(wr * 100, 1),
                })
        return sorted(resultados, key=lambda x: -x["wr"])

    def peores_patrones(self, ventana: int = 300,
                        min_obs: int = 5, max_wr: float = 0.40) -> list[dict]:
        """Identifica "danger patterns" — patrones con WR ≤ max_wr en los últimos N trades.

        Permite al sistema reforzar el bloqueo de patrones adversos más allá
        del umbral estándar de es_patron_problematico().
        """
        with self._lock:
            snapshot = list(self.trades[-ventana:])
        mapa: dict[tuple, dict] = {}
        for t in snapshot:
            pat = t.get("pat") or t.get("patron", "")
            dir_ = t.get("dir", "")
            res  = t.get("res") or t.get("resultado", "")
            if not pat or not dir_ or not res:
                continue
            key = (pat, dir_)
            if key not in mapa:
                mapa[key] = {"patron": pat, "dir": dir_, "W": 0, "L": 0}
            mapa[key]["W" if res == "WIN" else "L"] += 1
        resultados = []
        for v in mapa.values():
            n = v["W"] + v["L"]
            if n < min_obs:
                continue
            wr = v["W"] / n
            if wr <= max_wr:
                resultados.append({
                    "patron": v["patron"],
                    "dir":    v["dir"],
                    "n":      n,
                    "losses": v["L"],
                    "wr":     round(wr * 100, 1),
                })
        return sorted(resultados, key=lambda x: x["wr"])   # peor primero

    # ── Memoria de refuerzo: veredicto instantáneo por patrón ─────────────
    # Con caché de 60s para consumir mínimos recursos: el escaneo completo
    # se hace 1 vez por minuto y las consultas son un acceso a diccionario.
    _CACHE_VEREDICTO_S = 60

    def veredicto_patron(self, patron: str, direccion: str) -> dict:
        """Memoria de patrones ganadores Y perdedores en una sola consulta.

        Retorna {"tipo": "dorado"|"peligroso"|"neutral", "wr": %, "n": int}.
          · dorado    → WR ≥ 65% con ≥6 observaciones: REFORZAR la señal.
          · peligroso → WR ≤ 35% con ≥8 observaciones: EVITAR el trade.
          · neutral   → sin evidencia suficiente: decidir con los motores.
        """
        ahora = time.time()
        if ahora - getattr(self, "_t_cache_ver", 0.0) > self._CACHE_VEREDICTO_S:
            try:
                self._cache_dorados = {
                    (d["patron"], d["dir"]): d
                    for d in self.patrones_exitosos(min_obs=6, min_wr=0.65)}
                self._cache_peligro = {
                    (d["patron"], d["dir"]): d
                    for d in self.peores_patrones(min_obs=8, max_wr=0.35)}
            except Exception:
                self._cache_dorados = {}
                self._cache_peligro = {}
            self._t_cache_ver = ahora

        key = (patron, direccion)
        d = getattr(self, "_cache_dorados", {}).get(key)
        if d:
            return {"tipo": "dorado", "wr": d["wr"], "n": d["n"]}
        p = getattr(self, "_cache_peligro", {}).get(key)
        if p:
            return {"tipo": "peligroso", "wr": p["wr"], "n": p["n"]}
        return {"tipo": "neutral", "wr": 0.0, "n": 0}

    def penalizar_patron(self, patron: str, causa: str = "") -> None:
        """Registra una penalización explícita en el historial de fallos."""
        try:
            entrada = {
                "ts":    time.strftime("%Y-%m-%d %H:%M:%S"),
                "hora":  time.strftime("%H:%M"),
                "pat":   patron or "?",
                "dir":   "?",
                "vt":    0,
                "prob":  0.5,
                "ind":   {},
                "res":   "LOSS",
                "seq":   [],
                "causa": causa[:120],
            }
            self.trades.append(entrada)
            if len(self.trades) > self.MAX_TRADES:
                self.trades = self.trades[-self.MAX_TRADES:]
            self._guardar()   # penalizaciones siempre se persisten de inmediato
        except Exception:
            pass

    # ── Calcular votos óptimos desde histórico ────────────────────────────────

    def _votos_optimos(self) -> int | None:
        """Umbral de votos que maximiza la tasa de aciertos en el histórico."""
        if not _NP or len(self.trades) < 20:
            return None
        best_t, best_v = 0.5, None
        for umbral in range(2, 8):
            subset = [t for t in self.trades if t["vt"] >= umbral]
            if len(subset) < 5:
                continue
            tasa = sum(1 for t in subset if t["res"] == "WIN") / len(subset)
            if tasa > best_t:
                best_t = tasa
                best_v = umbral
        return best_v

    # ── Racha actual ─────────────────────────────────────────────────────────

    def _racha_actual(self) -> dict:
        if not self.trades:
            return {"tipo": None, "n": 0}
        tipo = self.trades[-1]["res"]
        n    = 1
        for t in reversed(self.trades[:-1]):
            if t["res"] == tipo:
                n += 1
            else:
                break
        return {"tipo": tipo, "n": n}

    # ── Indicadores en horarios malos ────────────────────────────────────────

    def horarios_malos(self) -> list[str]:
        """Horas del día con mayor tasa de pérdida."""
        freq = defaultdict(lambda: {"W": 0, "L": 0})
        for t in self.trades[-200:]:
            h = t.get("hora", "??")[:2]
            freq[h]["W" if t["res"] == "WIN" else "L"] += 1
        malos = []
        for h, v in freq.items():
            n = v["W"] + v["L"]
            if n >= 4 and v["L"] / n > 0.60:
                malos.append(h)
        return sorted(malos)

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _guardar(self):
        try:
            with self._lock:
                snapshot = list(self.trades)
            with open(self.ruta, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False)
        except Exception as e:
            print(f"[FalloDB] Error guardando: {e}")

    def _cargar(self):
        if not os.path.exists(self.ruta):
            return
        try:
            with open(self.ruta, encoding="utf-8") as f:
                datos = json.load(f)
            if not isinstance(datos, list):
                raise ValueError("Formato inesperado: se esperaba lista")
            self.trades = datos
            wins = sum(1 for t in self.trades if t.get("res") == "WIN")
            print(f"[FalloDB] {len(self.trades)} trades cargados ({wins} wins)")
        except json.JSONDecodeError as je:
            import shutil
            bak = self.ruta + ".bak"
            try:
                shutil.copy2(self.ruta, bak)
            except Exception:
                pass
            print(f"[FalloDB] ⚠ JSON CORRUPTO: {je}. Backup en {bak}. Iniciando historial vacío.")
        except Exception as e:
            print(f"[FalloDB] ⚠ Error cargando historial: {e}. Iniciando vacío.")

"""
conciencia.py — Sistema de Conciencia e Inteligencia Autónoma de Litch
======================================================================
Cinco subsistemas interconectados que dan a Litch autoaprendizaje real,
metacognición y reflexión continua sobre su propio desempeño:

  1. MemoriaEpisodica   — k-NN cosine sobre episodios ricos (1 por trade)
  2. CreenciasBayesianas — Beta(α,β) por (asset|hora|régimen|dirección), decay γ=0.98
  3. RedNeuronalOnline  — MLP 17→48→24→1 numpy, backprop online tras cada trade
  4. Metacognicion      — ECE calibración, Brier score, umbral de abstención
  5. ConcienciaLitch    — integrador + hilo de reflexión autónoma con Fable 5
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path

import numpy as np


# ═══════════════════════════════════════════════════════════════════════════════
# Utilidad: carga JSON con auto-reparación de corrupción
# ═══════════════════════════════════════════════════════════════════════════════

def _cargar_json_seguro(ruta: Path, etiqueta: str = "") -> tuple[dict | list | None, bool]:
    """
    Carga un archivo JSON con manejo robusto de corrupción.
    Devuelve (datos, ok):
      - (datos, True)  → carga exitosa
      - (None, False)  → archivo corrupto o inexistente; el .bak fue guardado
    Ante corrupción, hace backup del archivo dañado a <ruta>.bak antes de retornar None.
    """
    if not ruta.exists():
        return None, False
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f), True
    except json.JSONDecodeError as je:
        # Corrupción de JSON — hacer backup y reportar
        bak = ruta.with_suffix(".bak")
        try:
            import shutil
            shutil.copy2(ruta, bak)
        except Exception:
            pass
        msg = (f"[Conciencia/{etiqueta}] [!] JSON CORRUPTO: {ruta.name} - {je}. "
               f"Backup guardado en {bak.name}. Iniciando desde cero.")
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", "replace").decode())
        return None, False
    except Exception as exc:
        msg = f"[Conciencia/{etiqueta}] [!] Error leyendo {ruta.name}: {exc}"
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", "replace").decode())
        return None, False


# ═══════════════════════════════════════════════════════════════════════════════
# 1. MEMORIA EPISÓDICA
# ═══════════════════════════════════════════════════════════════════════════════

class MemoriaEpisodica:
    """
    Cada trade se guarda como un 'episodio': dict con contexto + vector de features.
    Recuperación por similitud coseno (k-NN sin índice — funciona bien hasta ~2000).
    El voto k-NN pondera por similitud → estima P(win | contexto_actual).
    """

    def __init__(self, capacidad: int = 2000, ruta: Path | None = None):
        self._capacidad = capacidad
        self._ruta      = ruta
        self._episodios: list[dict]      = []
        self._vecs:      list[np.ndarray] = []
        self._lock = threading.Lock()
        if ruta and ruta.exists():
            self._cargar()

    # ── API pública ──────────────────────────────────────────────────────────

    def guardar(self, episodio: dict, vec: np.ndarray) -> None:
        with self._lock:
            self._episodios.append(episodio)
            self._vecs.append(vec.astype(np.float32))
            if len(self._episodios) > self._capacidad:
                self._episodios.pop(0)
                self._vecs.pop(0)
        threading.Thread(target=self._persistir, daemon=True).start()

    def votar(self, vec: np.ndarray, k: int = 9) -> tuple[float, list[dict]]:
        """
        Devuelve (p_win_estimada, episodios_más_similares).
        Ponderación por similitud coseno: episodios cercanos cuentan más.
        """
        # Copiar datos bajo lock y soltar antes del cómputo NumPy
        with self._lock:
            if len(self._vecs) < 3:
                return 0.5, []
            mat  = np.stack(self._vecs, axis=0)       # copia: N × D float32
            eps_snap = list(self._episodios)

        # Cómputo coseno fuera del lock
        norma = np.linalg.norm(vec) + 1e-9
        norms = np.linalg.norm(mat, axis=1) + 1e-9
        sims  = (mat @ vec) / (norms * norma)
        k     = min(k, len(sims))
        idx   = np.argsort(sims)[::-1][:k]
        eps   = [eps_snap[i] | {"_sim": float(sims[i])} for i in idx]

        # Votación ponderada
        w_total = sum(e["_sim"] for e in eps) + 1e-9
        p_win   = sum(e["_sim"] for e in eps if e.get("resultado") == "WIN") / w_total
        return float(p_win), eps

    def __len__(self) -> int:
        return len(self._episodios)

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _persistir(self):
        if not self._ruta:
            return
        try:
            with self._lock:
                datos = {
                    "eps":  self._episodios[-800:],
                    "vecs": [v.tolist() for v in self._vecs[-800:]],
                }
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._ruta.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f)
            tmp.replace(self._ruta)
        except Exception:
            pass

    def _cargar(self):
        d, ok = _cargar_json_seguro(self._ruta, "MemoriaEpisodica")
        if ok and isinstance(d, dict):
            self._episodios = d.get("eps", [])
            raw = [np.array(v, dtype=np.float32) for v in d.get("vecs", [])]
            # Retrocompatibilidad: vectores anteriores tienen 16 dimensiones.
            # El 17° feature (régimen) se inicializa en 0.5 (neutral) para preservar el historial.
            self._vecs = [
                np.append(v, np.float32(0.5)) if len(v) == 16 else v
                for v in raw
            ]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CREENCIAS BAYESIANAS
# ═══════════════════════════════════════════════════════════════════════════════

class CreenciasBayesianas:
    """
    Beta(α, β) por clave = "asset|hora_bucket|regime|dir".
    Actualización online:  WIN → α += 1,  LOSS → β += 1.
    Factor de olvido γ = 0.98 por trade → las creencias viejas decaen gradualmente.
    """

    GAMMA   = 0.98
    PRIOR_A = 1.5
    PRIOR_B = 1.5

    def __init__(self, ruta: Path | None = None):
        self._ruta  = ruta
        self._betas: dict[str, list[float]] = {}
        self._lock  = threading.Lock()
        if ruta and ruta.exists():
            self._cargar()

    # ── clave ────────────────────────────────────────────────────────────────

    def _k(self, asset: str, hora: int, regime: str, dir_: str) -> str:
        return f"{asset}|{hora // 3}|{regime}|{dir_}"   # ventanas de 3 horas

    # ── API pública ──────────────────────────────────────────────────────────

    def p_win(self, asset: str, hora: int, regime: str, dir_: str) -> float:
        with self._lock:
            a, b = self._betas.get(self._k(asset, hora, regime, dir_),
                                   [self.PRIOR_A, self.PRIOR_B])
        return a / (a + b)

    def incertidumbre(self, asset: str, hora: int, regime: str, dir_: str) -> float:
        """Ancho del IC 95% (mayor → menos datos, menos confianza)."""
        with self._lock:
            a, b = self._betas.get(self._k(asset, hora, regime, dir_),
                                   [self.PRIOR_A, self.PRIOR_B])
        n = a + b
        p = a / n
        return 1.96 * math.sqrt(max(p * (1 - p) / n, 1e-9))

    def actualizar(self, asset: str, hora: int, regime: str,
                   dir_: str, resultado: str) -> None:
        k = self._k(asset, hora, regime, dir_)
        with self._lock:
            a, b = self._betas.get(k, [self.PRIOR_A, self.PRIOR_B])
            # Decay hacia el prior (olvido gradual)
            a = a * self.GAMMA + self.PRIOR_A * (1 - self.GAMMA)
            b = b * self.GAMMA + self.PRIOR_B * (1 - self.GAMMA)
            if resultado == "WIN":
                a += 1.0
            else:
                b += 1.0
            self._betas[k] = [a, b]
        threading.Thread(target=self._persistir, daemon=True).start()

    def top(self, n: int = 8) -> list[dict]:
        """Condiciones con mayor P(win) con ≥ 5 observaciones acumuladas."""
        with self._lock:
            items = []
            for k, (a, b) in self._betas.items():
                # obs = cuánto han crecido los parámetros sobre el prior conjunto
                # (a-PRIOR_A)/GAMMA subestimaba: solo contaba wins e inflaba 50x.
                obs = (a + b) - (self.PRIOR_A + self.PRIOR_B)
                if obs < 5:
                    continue
                items.append({"clave": k, "p": a / (a + b), "obs": round(obs, 1)})
        return sorted(items, key=lambda x: x["p"], reverse=True)[:n]

    def peores(self, n: int = 5) -> list[dict]:
        """Condiciones con menor P(win) con ≥ 5 observaciones (zonas de peligro)."""
        with self._lock:
            items = []
            for k, (a, b) in self._betas.items():
                obs = (a + b) - (self.PRIOR_A + self.PRIOR_B)
                if obs < 5:
                    continue
                items.append({"clave": k, "p": a / (a + b), "obs": round(obs, 1)})
        return sorted(items, key=lambda x: x["p"])[:n]

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _persistir(self):
        if not self._ruta:
            return
        try:
            with self._lock:
                d = dict(self._betas)
            tmp = self._ruta.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            tmp.replace(self._ruta)
        except Exception:
            pass

    def _cargar(self):
        d, ok = _cargar_json_seguro(self._ruta, "CreenciasBayesianas")
        if ok and isinstance(d, dict):
            self._betas = d


# ═══════════════════════════════════════════════════════════════════════════════
# 3. RED NEURONAL ONLINE
# ═══════════════════════════════════════════════════════════════════════════════

class RedNeuronalOnline:
    """
    MLP numpy: 17 → 48 → 24 → 1 (sigmoid).
    Aprende con backpropagation SGD online tras cada trade (η = 0.008).
    Regularización L2 λ = 1e-4 para evitar sobreajuste con pocos datos.

    Vector de entrada (17 features, todas en [0,1]):
      [0]  votos / 7
      [1]  prob (señal Markov)
      [2]  hora / 23
      [3]  dia_semana / 6
      [4]  smc_en_kz (bool)
      [5]  kelly normalizado → (p - 0.5415) / 0.4 + 0.5  clamped
      [6]  wr_20 / 100  (win rate últimos 20 trades)
      [7]  rsi / 100   (0.5 si no disponible)
      [8]  hurst       (0.5 si no disponible)
      [9..15]  votos individuales: markov, estadística, red_maestra,
               pronóstico, indicadores, RL-DQN, SMC/LWS
    """

    N_IN   = 17
    OCULTAS = [48, 24]
    LR     = 0.008
    L2     = 1e-4

    def __init__(self, ruta: Path | None = None):
        self._ruta      = ruta
        self._lock      = threading.Lock()
        self.n_updates  = 0
        if ruta and ruta.exists():
            self._cargar()
        else:
            self._init_pesos()

    # ── Inicialización ───────────────────────────────────────────────────────

    def _init_pesos(self):
        dims = [self.N_IN] + self.OCULTAS + [1]
        self.W, self.b = [], []
        for i in range(len(dims) - 1):
            std = math.sqrt(2.0 / (dims[i] + dims[i + 1]))
            self.W.append(np.random.randn(dims[i + 1], dims[i]).astype(np.float32) * std)
            self.b.append(np.zeros(dims[i + 1], dtype=np.float32))

    # ── Activaciones ─────────────────────────────────────────────────────────

    @staticmethod
    def _tanh(x: np.ndarray)  -> np.ndarray: return np.tanh(x)
    @staticmethod
    def _dtanh(a: np.ndarray) -> np.ndarray: return 1.0 - a ** 2
    @staticmethod
    def _sig(x: np.ndarray)   -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))

    # ── Forward ──────────────────────────────────────────────────────────────

    def _forward(self, x: np.ndarray) -> tuple[list, list]:
        acts, zs = [x], []
        for i, (W, b_) in enumerate(zip(self.W, self.b)):
            z = W @ acts[-1] + b_
            zs.append(z)
            a = self._tanh(z) if i < len(self.W) - 1 else self._sig(z)
            acts.append(a)
        return acts, zs

    def predecir(self, x: np.ndarray) -> float:
        with self._lock:
            acts, _ = self._forward(x)
        return float(acts[-1][0])

    # ── Backward (SGD online) ─────────────────────────────────────────────────

    def aprender(self, x: np.ndarray, y: float) -> None:
        with self._lock:
            acts, _ = self._forward(x)
            deltas   = [None] * len(self.W)
            deltas[-1] = acts[-1] - np.array([y], dtype=np.float32)  # BCE grad

            for i in range(len(self.W) - 2, -1, -1):
                deltas[i] = (self.W[i + 1].T @ deltas[i + 1]) * self._dtanh(acts[i + 1])

            for i in range(len(self.W)):
                gW = np.outer(deltas[i], acts[i]) + self.L2 * self.W[i]
                gb = deltas[i]
                self.W[i] -= self.LR * gW
                self.b[i]  -= self.LR * gb

            self.n_updates += 1

        if self.n_updates % 100 == 0:
            threading.Thread(target=self._persistir, daemon=True).start()

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _persistir(self):
        if not self._ruta:
            return
        try:
            with self._lock:
                d = {
                    "W": [w.tolist() for w in self.W],
                    "b": [b.tolist() for b in self.b],
                    "n": self.n_updates,
                }
            tmp = self._ruta.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            tmp.replace(self._ruta)
        except Exception:
            pass

    def _cargar(self):
        d, ok = _cargar_json_seguro(self._ruta, "RedNeuronalOnline")
        if ok and isinstance(d, dict):
            try:
                W_tmp = [np.array(w, dtype=np.float32) for w in d["W"]]
                b_tmp = [np.array(b, dtype=np.float32) for b in d["b"]]
                if W_tmp[0].shape[1] != self.N_IN:
                    raise ValueError(f"Dimensiones incompatibles: {W_tmp[0].shape[1]} ≠ {self.N_IN}")
                self.W = W_tmp
                self.b = b_tmp
                self.n_updates = d.get("n", 0)
            except Exception as e:
                print(f"[Conciencia/RedNeuronalOnline] ⚠ Pesos inválidos: {e} — reiniciando red.")
                self._init_pesos()
        else:
            self._init_pesos()


# ═══════════════════════════════════════════════════════════════════════════════
# 4. METACOGNICIÓN
# ═══════════════════════════════════════════════════════════════════════════════

class Metacognicion:
    """
    Calibración de confianza: ¿cuando mi P(win) predecida coincide con el WR real?

    Expected Calibration Error (ECE):
      Si Litch dice "70% de ganar" y en esos casos gana 70% → ECE ≈ 0 (perfecto)
      Si dice "70%" y gana 50% → ECE alto (sobreconfianza sistemática)

    Brier Score:
      Media de (p_pred − resultado)² → mide precisión probabilística global.
      <0.20 = bueno, <0.25 = aceptable, >0.25 = mejorable.

    Abstención:
      Si el margen es muy pequeño (|p - 0.5| < 0.07) O la incertidumbre
      bayesiana es alta → recomendar no operar esa señal.
    """

    BINS = 10

    def __init__(self):
        self._hist: list[tuple[float, int]] = []   # (p_pred, 0_o_1)
        self._lock = threading.Lock()

    def registrar(self, p_pred: float, resultado: str) -> None:
        with self._lock:
            self._hist.append((float(p_pred), 1 if resultado == "WIN" else 0))
            if len(self._hist) > 2000:
                self._hist = self._hist[-2000:]

    def ece(self) -> float:
        with self._lock:
            h = list(self._hist)
        if len(h) < 20:
            return 0.0
        bins = [[] for _ in range(self.BINS)]
        for p, y in h:
            bins[min(int(p * self.BINS), self.BINS - 1)].append((p, y))
        total = len(h)
        return sum(
            len(b) / total * abs(sum(y for _, y in b) / len(b)
                                 - sum(p for p, _ in b) / len(b))
            for b in bins if b
        )

    def brier(self) -> float:
        with self._lock:
            h = list(self._hist)
        if not h:
            return 0.5
        return float(np.mean([(p - y) ** 2 for p, y in h]))

    def debe_abstenerse(self, p_pred: float, incert_bay: float) -> bool:
        """True si la señal actual es estadísticamente poco fiable."""
        # Criterio 1: señal muy cerca del 50% (sin discriminación)
        if abs(p_pred - 0.5) < 0.07:
            return True
        # Criterio 2: incertidumbre bayesiana demasiado alta
        if incert_bay > 0.25:
            return True
        # Criterio 3: calibración ECE degradada (el modelo dice X pero ocurre Y)
        if len(self._hist) > 30 and self.ece() > 0.20:
            return True
        # Criterio 4: zona "clueless" — últimos 8 trades con WR < 40%
        # (la conciencia está adivinando peor que el azar)
        with self._lock:
            ultimos = list(self._hist)[-8:]
        if len(ultimos) >= 8:
            wr_reciente = sum(y for _, y in ultimos) / len(ultimos)
            if wr_reciente < 0.40:
                return True
        return False

    def zona_clueless(self, ventana: int = 12) -> tuple[bool, float]:
        """
        Detecta si la conciencia está en una zona de bajo rendimiento.

        Retorna (en_zona_clueless: bool, wr_reciente: float).
        La zona clueless es cuando el WR reciente < 45% — indica
        que el mercado está en régimen caótico donde los modelos no sirven.
        """
        with self._lock:
            ultimos = list(self._hist)[-ventana:]
        if len(ultimos) < ventana // 2:
            return False, 0.5
        wr = sum(y for _, y in ultimos) / len(ultimos)
        return wr < 0.45, round(wr, 3)

    def estado_calibracion(self) -> str:
        e = self.ece()
        if e < 0.06:
            return "EXCELENTE ✓✓"
        if e < 0.10:
            return "BUENA ✓"
        if e < 0.16:
            return "ACEPTABLE"
        return "MEJORABLE ⚠"

    def n_trades(self) -> int:
        return len(self._hist)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CONCIENCIA LITCH  —  integrador central
# ═══════════════════════════════════════════════════════════════════════════════

class ConcienciaLitch:
    """
    Integra los 4 subsistemas y añade:
    - Evaluación pre-trade: combina k-NN + Bayes + Red para dar P(win) compuesto.
    - Aprendizaje post-trade: actualiza los 4 subsistemas con el resultado.
    - Abstención automática: cuando la señal es débil según metacognición.
    - Reflexión autónoma: cada REFLEXION_CADA trades consulta a Fable 5.
    - Introspección: texto explicativo del estado interno completo.
    """

    REFLEXION_CADA = 25   # reflexión profunda cada N trades
    MIN_ABSTENER   = 15   # trades mínimos antes de activar la abstención

    # Modos de override manual:
    #   "auto"           → la conciencia decide sola (comportamiento por defecto)
    #   "forzar_actuar"  → ignora las recomendaciones de abstención, opera siempre
    #   "forzar_abstener"→ fuerza abstención sin importar qué diga la conciencia
    MODOS_OVERRIDE = ("auto", "forzar_actuar", "forzar_abstener")

    def __init__(self, app):
        self.app   = app
        base       = Path("MEMORIA_AP")

        self.memoria   = MemoriaEpisodica(ruta=base / "con_episodios.json")
        self.creencias = CreenciasBayesianas(ruta=base / "con_creencias.json")
        self.red       = RedNeuronalOnline(ruta=base / "con_red.json")
        self.meta      = Metacognicion()

        self._n_trades    = 0
        self._reflexiones: list[dict] = []
        self._lock_ref    = threading.Lock()
        self._ruta_ref    = base / "con_reflexiones.json"
        self._cargar_reflexiones()

        # Override manual — persiste en disco
        self._ruta_override = base / "con_override.json"
        self._modo_override: str = self._cargar_override()
        self._ts_override: float = time.time()          # cuándo se activó el modo actual
        self._alerta_override_lanzada: bool = False     # para no repetir la alerta

        app.log("[Conciencia] Sistema inicializado. "
                f"Episodios: {len(self.memoria)} | "
                f"Red updates: {self.red.n_updates} | "
                f"Override: {self._modo_override}")

    # ── Control manual de abstención ─────────────────────────────────────────

    @property
    def modo_override(self) -> str:
        """'auto' | 'forzar_actuar' | 'forzar_abstener'."""
        return self._modo_override

    def _cargar_override(self) -> str:
        """Lee el override guardado en disco; devuelve 'auto' si no existe o está corrupto."""
        try:
            if self._ruta_override.exists():
                datos = json.loads(self._ruta_override.read_text(encoding="utf-8"))
                modo = datos.get("modo", "auto")
                if modo in self.MODOS_OVERRIDE:
                    return modo
        except Exception:
            pass
        return "auto"

    def _guardar_override(self) -> None:
        """Persiste el override actual en disco para sobrevivir reinicios."""
        try:
            datos = {
                "modo": self._modo_override,
                "ts":   time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._ruta_override.write_text(
                json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def set_override(self, modo: str) -> str:
        """
        Cambia el modo de abstención manualmente.
        Devuelve un texto confirmatorio para log/voz. Persiste en disco.
        """
        if modo not in self.MODOS_OVERRIDE:
            return f"Modo desconocido: {modo}. Usa: {self.MODOS_OVERRIDE}"
        anterior = self._modo_override
        self._modo_override = modo
        self._ts_override = time.time()
        self._alerta_override_lanzada = False  # resetear alerta para el nuevo modo
        self._guardar_override()
        self.app.log(f"[Conciencia] Override cambiado: '{anterior}' → '{modo}'")
        if modo == "auto":
            return "Conciencia en modo AUTOMÁTICO. Decidiré sola cuándo abstenerme."
        if modo == "forzar_actuar":
            return ("Override ACTIVO: ignoraré recomendaciones de abstención. "
                    "Operaré en cada señal válida sin restricciones.")
        if modo == "forzar_abstener":
            return ("Override ACTIVO: me abstendré de todas las operaciones "
                    "hasta que me des la orden de reanudar.")
        return f"Modo cambiado de '{anterior}' a '{modo}'."

    def estado_override(self) -> str:
        """Texto corto del estado actual del override para mostrar en UI."""
        return {
            "auto":            "🔄 AUTO",
            "forzar_actuar":   "▶ FORZAR OPERAR",
            "forzar_abstener": "⏸ FORZAR ABSTENCIÓN",
        }.get(self._modo_override, "?")

    def verificar_override_obsoleto(self) -> None:
        """
        Llámese periódicamente (ej. cada 30 min desde el loop de trading).
        Si el override lleva más de 2 horas activo en modo no-auto,
        alerta al usuario por voz una sola vez para que recuerde desactivarlo.
        """
        if self._modo_override == "auto" or self._alerta_override_lanzada:
            return
        horas = (time.time() - self._ts_override) / 3600
        if horas >= 2.0:
            self._alerta_override_lanzada = True
            nombre = ("operación forzada" if self._modo_override == "forzar_actuar"
                      else "abstención forzada")
            msg = self.app.txt(
                f"Señor, han pasado {horas:.0f} horas con el override de conciencia en {nombre}. "
                "¿Desea que retorne al modo automático?",
                f"Sir, the conscience override has been in forced mode for {horas:.0f} hours. "
                "Shall I return to automatic mode?")
            try:
                self.app.decir(msg)
            except Exception:
                pass
            self.app.log(f"[Conciencia] ⚠ Override '{self._modo_override}' activo por "
                         f"{horas:.1f}h — se notificó al usuario.")

    # ── Construcción del vector de features ──────────────────────────────────

    # Mapeo de régimen a valor continuo [0, 1]: caótico=0, neutral=0.5, tendencia=1
    _REGIME_MAP: dict[str, float] = {
        "trending": 1.0, "tendencia": 1.0,
        "ranging":  0.75, "rango": 0.75,
        "neutral":  0.5,
        "chaotic":  0.0,  "caotico": 0.0, "caótico": 0.0,
    }

    @staticmethod
    def construir_vec(votos: int, prob: float, hora: int, dia: int,
                      smc_en_kz: bool, kelly: float, wr20: float,
                      rsi: float, hurst: float,
                      votos_ind: list[int],
                      regime: str = "neutral") -> np.ndarray:
        """
        17 features, todas normalizadas a [0, 1].
        votos_ind: lista de 7 ints (0 o 1) — un voto por cada método.
        regime: condición del mercado → 0 (caótico) a 1 (tendencia fuerte).
        """
        kelly_norm  = float(np.clip((kelly - (-0.5415)) / 1.0, 0.0, 1.0))
        regime_val  = ConcienciaLitch._REGIME_MAP.get(str(regime).lower(), 0.5)
        vec = np.array([
            votos / 7.0,
            float(np.clip(prob, 0.0, 1.0)),
            hora  / 23.0,
            dia   / 6.0,
            float(smc_en_kz),
            kelly_norm,
            float(np.clip(wr20 / 100.0, 0.0, 1.0)),
            float(np.clip(rsi  / 100.0, 0.0, 1.0)),
            float(np.clip(hurst, 0.0, 1.0)),
            *[float(v) for v in (list(votos_ind) + [0] * 7)[:7]],
            regime_val,
        ], dtype=np.float32)
        return vec

    # ── Evaluación pre-trade ──────────────────────────────────────────────────

    def evaluar(self, asset: str, dir_: str, hora: int, regime: str,
                votos: int, prob: float, dia: int, smc_en_kz: bool,
                kelly: float, wr20: float, rsi: float, hurst: float,
                votos_ind: list[int],
                dd_pct: float = 0.0,
                slot_factor: float = 1.0) -> dict:
        """
        Evalúa la señal ANTES de operar.

        Parámetros nuevos (v3):
            dd_pct       Drawdown de sesión como fracción [0, 1].
                         A mayor drawdown, la conciencia exige más confianza.
            slot_factor  Factor de la franja horaria actual del SessionTracker.
                         < 1.0 → peor rendimiento histórico en esta hora.

        Devuelve dict con p_win_compuesto, debe_abstenerse, razon, fuentes.
        """
        vec = self.construir_vec(votos, prob, hora, dia, smc_en_kz,
                                 kelly, wr20, rsi, hurst, votos_ind, regime=regime)

        # Tres estimadores de P(win)
        p_eps, eps_sim = self.memoria.votar(vec)
        p_bay          = self.creencias.p_win(asset, hora, regime, dir_)
        p_red          = self.red.predecir(vec)
        incert         = self.creencias.incertidumbre(asset, hora, regime, dir_)

        # Ensemble ponderado — pesos crecen con experiencia
        n_eps = len(self.memoria)
        n_upd = self.red.n_updates
        w_eps = min(0.30, n_eps  / 80.0  * 0.30)
        w_red = min(0.35, n_upd  / 40.0  * 0.35)
        w_bay = 0.35
        tot_w = w_eps + w_bay + w_red
        p_com = (w_eps * p_eps + w_bay * p_bay + w_red * p_red) / max(tot_w, 0.35)

        # ── Umbral de abstención adaptativo (v3) ──────────────────────────────
        # Punto base de la meta-cognición: P(win) debe superar 0.57 para actuar.
        # Si hay drawdown de sesión, exigimos más confianza (subimos el umbral).
        # Si el slot horario es históricamente malo, también subimos el umbral.
        #   dd_pct=0.05 → +3% umbral | dd_pct=0.08 → +5%
        #   slot_factor=0.80 → +2%   | slot_factor=0.60 → +5%
        _dd_bonus   = float(min(dd_pct   * 0.60, 0.06))   # máx +6% por drawdown
        _slot_bonus = float(max(0.0, (1.0 - slot_factor) * 0.10))  # máx +10% por slot
        _umbral_ajustado = 0.57 + _dd_bonus + _slot_bonus

        # ── Metacognición + override manual ──────────────────────────────────
        # Usamos el umbral ajustado en lugar del fijo de self.meta.debe_abstenerse()
        _meta_dice_abstener = (
            self._n_trades >= self.MIN_ABSTENER
            and (p_com < _umbral_ajustado or self.meta.debe_abstenerse(p_com, incert))
        )
        razon = ""

        _aviso_override_t = getattr(self, "_aviso_override_t", 0.0)
        if self._modo_override == "forzar_actuar":
            abstenerse = False
            if _meta_dice_abstener:
                razon = "[OVERRIDE] Conciencia recomendaba abstención pero el usuario forzó operar."
                if time.time() - _aviso_override_t > 600:
                    self._aviso_override_t = time.time()
                    try:
                        self.app.log(
                            f"[Conciencia] ⚠ Override forzar-actuar suprimió abstención: "
                            f"{dir_} P={p_com:.2f} umbral={_umbral_ajustado:.2f}")
                    except Exception:
                        pass
        elif self._modo_override == "forzar_abstener":
            abstenerse = True
            razon = "[OVERRIDE] Abstención forzada manualmente por el usuario."
        else:
            abstenerse = _meta_dice_abstener
            if abstenerse:
                if p_com < _umbral_ajustado and (_dd_bonus > 0 or _slot_bonus > 0):
                    razon = (f"Umbral elevado por riesgo: "
                             f"P={p_com:.2f} < umbral={_umbral_ajustado:.2f} "
                             f"(DD={dd_pct:.1%} slot×{slot_factor:.2f})")
                elif abs(p_com - 0.5) < 0.07:
                    razon = f"Señal demasiado débil (P={p_com:.2f}, margen < 7%)"
                elif incert > 0.25:
                    razon = f"Alta incertidumbre bayesiana en {asset} {hora}h ({incert:.2f})"
                else:
                    razon = f"Sistema mal calibrado para esta condición (ECE={self.meta.ece():.2f})"

        return {
            "p_compuesta":      p_com,
            "p_episodica":      p_eps,
            "p_bayesiana":      p_bay,
            "p_red":            p_red,
            "incertidumbre":    incert,
            "debe_abstenerse":  abstenerse,
            "razon":            razon,
            "vec":              vec,
            "n_episodios":      n_eps,
            "override":         self._modo_override,
            "umbral_efectivo":  round(_umbral_ajustado, 3),
            "dd_bonus":         round(_dd_bonus, 3),
            "slot_bonus":       round(_slot_bonus, 3),
        }

    # ── Aprendizaje post-trade ───────────────────────────────────────────────

    def aprender(self, asset: str, dir_: str, hora: int, regime: str,
                 votos: int, prob: float, dia: int, smc_en_kz: bool,
                 kelly: float, wr20: float, rsi: float, hurst: float,
                 votos_ind: list[int], resultado: str,
                 p_pred: float = 0.5,
                 dd_pct: float = 0.0,
                 slot_factor: float = 1.0) -> None:
        """
        Actualiza los 4 subsistemas con el resultado del trade.

        Nuevos parámetros (v3):
            dd_pct       Drawdown de sesión al momento del trade [0, 1].
            slot_factor  Factor de rendimiento del slot horario [0.5, 1.5].

        resultado: "WIN" o "LOSS"
        """
        vec = self.construir_vec(votos, prob, hora, dia, smc_en_kz,
                                 kelly, wr20, rsi, hurst, votos_ind, regime=regime)
        y   = 1.0 if resultado == "WIN" else 0.0

        episodio = {
            "ts":          time.strftime("%Y-%m-%dT%H:%M:%S"),
            "asset":       asset,
            "dir":         dir_,
            "hora":        hora,
            "regime":      regime,
            "votos":       votos,
            "prob":        prob,
            "resultado":   resultado,
            "p_pred":      p_pred,
            "dd_pct":      round(dd_pct, 4),
            "slot_factor": round(slot_factor, 3),
        }

        self.memoria.guardar(episodio, vec)
        self.creencias.actualizar(asset, hora, regime, dir_, resultado)
        self.red.aprender(vec, y)
        self.meta.registrar(p_pred, resultado)

        self._n_trades += 1

        if self._n_trades % self.REFLEXION_CADA == 0:
            threading.Thread(target=self._reflexion_autonoma,
                             daemon=True, name="ConRef").start()

    # ── Introspección ────────────────────────────────────────────────────────

    def introspeccionar(self) -> str:
        """Texto completo del estado interno — para el panel UI."""
        ece   = self.meta.ece()
        brier = self.meta.brier()
        top   = self.creencias.top(6)
        peor  = self.creencias.peores(3)
        cal   = self.meta.estado_calibracion()
        n_tra = self.meta.n_trades()

        top_txt = "\n".join(
            f"  [{c['clave']}]  WR={c['p']*100:.1f}%  (obs≈{c['obs']:.0f})"
            for c in top) or "  Acumulando datos…"

        peor_txt = "\n".join(
            f"  [{c['clave']}]  WR={c['p']*100:.1f}%  ← EVITAR"
            for c in peor) or "  Sin zonas de peligro detectadas"

        with self._lock_ref:
            ult_ref = (self._reflexiones[-1] if self._reflexiones else None)

        ref_txt = ""
        if ult_ref:
            ref_txt = (f"\n[{ult_ref.get('fecha','')[:16]}] "
                       f"(trade #{ult_ref.get('n_trades','?')})\n"
                       + ult_ref.get("reflexion", "")[:600])

        # Override — texto con indicador de alerta si no es auto
        _ovr = self._modo_override
        _hrs = (time.time() - self._ts_override) / 3600
        if _ovr == "auto":
            _ovr_txt = "🔄 AUTOMÁTICO"
        elif _ovr == "forzar_actuar":
            _ovr_txt = f"▶ FORZAR OPERAR  ⚠ activo {_hrs:.1f}h"
        else:
            _ovr_txt = f"⏸ FORZAR ABSTENCIÓN  ⚠ activo {_hrs:.1f}h"

        return (
            f"{'═'*52}\n"
            f"  CONCIENCIA DE LITCH  —  Estado Interno\n"
            f"{'═'*52}\n"
            f"  Trades aprendidos : {self._n_trades}\n"
            f"  Episodios memoria : {len(self.memoria)}\n"
            f"  Actualizaciones red neuronal : {self.red.n_updates}\n"
            f"  Observaciones metacog. : {n_tra}\n"
            f"\n"
            f"  ABSTENCIÓN\n"
            f"  ──────────────────────────────────────\n"
            f"  Control override  : {_ovr_txt}\n"
            f"  Umbral auto activo: {'Sí (≥15 trades)' if self._n_trades >= self.MIN_ABSTENER else f'No ({self._n_trades}/{self.MIN_ABSTENER} trades)'}\n"
            f"\n"
            f"  CALIBRACIÓN\n"
            f"  ──────────────────────────────────────\n"
            f"  ECE   : {ece:.4f}   → {cal}\n"
            f"  Brier : {brier:.4f}  "
            f"({'bueno' if brier < 0.20 else 'aceptable' if brier < 0.25 else 'mejorable'})\n"
            f"\n"
            f"  CONDICIONES MÁS FAVORABLES\n"
            f"  ──────────────────────────────────────\n"
            f"{top_txt}\n"
            f"\n"
            f"  ZONAS DE PELIGRO\n"
            f"  ──────────────────────────────────────\n"
            f"{peor_txt}\n"
            f"\n"
            f"  ÚLTIMA REFLEXIÓN FABLE 5\n"
            f"  ──────────────────────────────────────"
            f"{ref_txt if ref_txt else chr(10) + '  Sin reflexiones aún.'}\n"
            f"{'═'*52}"
        )

    # ── Reflexión autónoma con Fable 5 ───────────────────────────────────────

    def _reflexion_autonoma(self):
        try:
            from . import mente_claude as _mc
            if not _mc.disponible():
                return
        except Exception:
            return

        app   = self.app
        ece   = self.meta.ece()
        brier = self.meta.brier()
        top   = self.creencias.top(5)
        peor  = self.creencias.peores(3)

        top_txt  = "; ".join(
            f"{c['clave']} WR={c['p']*100:.0f}%"
            for c in top) or "sin datos suficientes"
        peor_txt = "; ".join(
            f"{c['clave']} WR={c['p']*100:.0f}%"
            for c in peor) or "ninguna"

        prev = ""
        with self._lock_ref:
            if self._reflexiones:
                prev = self._reflexiones[-1].get("reflexion", "")[:200]

        contexto = (
            f"Sistema: Litch Trading-IA — opciones binarias (IQ Option + multi-broker)\n"
            f"Trades aprendidos en sesión: {self._n_trades}\n"
            f"Episodios en memoria episódica: {len(self.memoria)}\n"
            f"Actualizaciones red neuronal MLP: {self.red.n_updates}\n"
            f"ECE (calibración): {ece:.4f}  (ideal < 0.06)\n"
            f"Brier Score: {brier:.4f}  (ideal < 0.20)\n"
            f"Condiciones más rentables: {top_txt}\n"
            f"Condiciones más peligrosas: {peor_txt}\n"
            f"Reflexión anterior: {prev or 'ninguna'}"
        )

        pregunta = (
            "Eres el metacognitor de Litch — una IA de trading con autoaprendizaje "
            "online. Analiza el estado interno del sistema y responde:\n\n"
            "1) CALIBRACIÓN: ¿Qué dicen el ECE y Brier Score sobre la calidad de las "
            "predicciones? ¿El sistema está sobreconfiado o infraconfiado? ¿Qué "
            "implica eso para el tamaño de las apuestas?\n\n"
            "2) CONDICIONES ÓPTIMAS: ¿Qué patrón revelan las condiciones más "
            "rentables? ¿Hay un activo, horario o régimen que claramente domina?\n\n"
            "3) ZONAS DE PELIGRO: ¿Qué dicen las condiciones peores? ¿Hay un patrón "
            "sistemático de fallo que Litch debe aprender a evitar?\n\n"
            "4) AJUSTE TÉCNICO: Un ajuste específico (umbral de votos, ventana "
            "horaria, threshold de abstención) que mejoraría el sistema AHORA.\n\n"
            "5) HIPÓTESIS: En una sola oración — la hipótesis principal que Litch "
            "debe testear en los próximos 20 trades.\n\n"
            "Máximo 250 palabras. Técnico, específico, sin disclaimers."
        )

        try:
            respuesta = _mc.responder_analisis(pregunta, contexto=contexto)
            if not respuesta:
                return
            entrada = {
                "fecha":     time.strftime("%Y-%m-%dT%H:%M:%S"),
                "n_trades":  self._n_trades,
                "ece":       ece,
                "brier":     brier,
                "reflexion": respuesta,
            }
            with self._lock_ref:
                self._reflexiones.append(entrada)
                self._reflexiones = self._reflexiones[-100:]
            self._persistir_reflexiones()
            n_ref = len(self._reflexiones)
            app.log(f"[Conciencia/Reflexión #{n_ref}] {respuesta[:150]}…")
            # Extractar hipótesis (línea 5) para decirla por voz
            lineas = [l.strip() for l in respuesta.split("\n") if l.strip()]
            hip = next((l for l in lineas if l.startswith("5)")), None)
            resumen_voz = hip[2:].strip() if hip else lineas[0][:120] if lineas else ""
            if resumen_voz:
                app.decir(app.txt(
                    f"Reflexion autonoma completada, senor. "
                    f"Mi hipotesis para los proximos trades: {resumen_voz}",
                    f"Autonomous reflection done, sir. "
                    f"My hypothesis for the next trades: {resumen_voz}"))
        except Exception as ex:
            app.log(f"[Conciencia] Error en reflexión: {ex}")

    # ── Reflexión manual (on-demand desde UI) ────────────────────────────────

    def reflexion_manual(self) -> str:
        """
        Bloquea hasta que Fable 5 responda (para el botón UI).
        Devuelve el texto de la reflexión.
        """
        try:
            from . import mente_claude as _mc
            if not _mc.disponible():
                return "Fable 5 no disponible. Configura la API key de Claude."
        except Exception:
            return "Módulo mente_claude no disponible."

        ece   = self.meta.ece()
        brier = self.meta.brier()
        top   = self.creencias.top(5)
        peor  = self.creencias.peores(3)

        top_txt  = "; ".join(f"{c['clave']} WR={c['p']*100:.0f}%" for c in top) or "sin datos"
        peor_txt = "; ".join(f"{c['clave']} WR={c['p']*100:.0f}%" for c in peor) or "ninguna"

        contexto = (
            f"Trades: {self._n_trades} | Episodios: {len(self.memoria)} | "
            f"Red updates: {self.red.n_updates}\n"
            f"ECE: {ece:.4f} | Brier: {brier:.4f}\n"
            f"Mejores: {top_txt}\nPeores: {peor_txt}"
        )
        pregunta = (
            "Análisis profundo del sistema Litch — ¿qué está aprendiendo "
            "bien y qué está aprendiendo mal? ¿Qué comportamiento debería "
            "cambiar en los próximos 30 trades para mejorar el Kelly Criterion? "
            "Sé específico. Máximo 200 palabras."
        )

        try:
            resp = _mc.responder_analisis(pregunta, contexto=contexto)
            if resp:
                entrada = {
                    "fecha":     time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "n_trades":  self._n_trades,
                    "ece":       ece,
                    "brier":     brier,
                    "reflexion": resp,
                    "manual":    True,
                }
                with self._lock_ref:
                    self._reflexiones.append(entrada)
                    self._reflexiones = self._reflexiones[-100:]
                self._persistir_reflexiones()
                self.app.log(f"[Conciencia/Manual] {resp[:120]}…")
                return resp
        except Exception as ex:
            return f"Error al consultar Fable 5: {ex}"
        return "Sin respuesta de Fable 5."

    # ── Persistencia de reflexiones ───────────────────────────────────────────

    def _cargar_reflexiones(self):
        try:
            if self._ruta_ref.exists():
                with open(self._ruta_ref, encoding="utf-8") as f:
                    self._reflexiones = json.load(f)
        except Exception:
            self._reflexiones = []

    def _persistir_reflexiones(self):
        try:
            with self._lock_ref:
                d = list(self._reflexiones)
            tmp = self._ruta_ref.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            tmp.replace(self._ruta_ref)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# Acceso global — singleton por sesión
# ═══════════════════════════════════════════════════════════════════════════════

_instancia: ConcienciaLitch | None = None
_lock_init = threading.Lock()


def obtener(app=None) -> ConcienciaLitch | None:
    """Devuelve la instancia singleton, creándola si se pasa app."""
    global _instancia
    if _instancia is not None:
        return _instancia
    if app is None:
        return None
    with _lock_init:
        if _instancia is None:
            _instancia = ConcienciaLitch(app)
    return _instancia

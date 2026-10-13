"""Red neuronal de Litch — MLP profundo con memoria algorítmica y auto-entrenamiento.

Arquitectura mejorada v3:
  Entrada : 20 features por vela (aumentado de 16)
  Capa 1  : 64 neuronas · tanh + dropout simulado vía noise injection
  Capa 2  : 32 neuronas · tanh
  Capa 3  : 16 neuronas · tanh
  Salida  : 1 · sigmoid (P verde)

Nuevos features respecto a v2 (idx 16-19):
  16  Entropía de Shannon de las últimas 20 velas (desorden → menor confianza)
  17  Cruce EWMA corta/larga normalizado (tendencia actual)
  18  Autocorrelación en lag 2 (periodicidad de 2 velas)
  19  Dirección dominante de las últimas 8 velas (sesgo reciente)

Memoria de resultados reales:
  Cada vez que se ejecuta un trade, se guarda el vector de features + dirección.
  Cuando el resultado llega (acierto/fallo), se vincula y se usa para entrenar.
  Todo se persiste en disco → la red nunca olvida, mejora con el tiempo.

Auto-entrenamiento en segundo plano:
  Cada 5 minutos: re-entrena con TODOS los datos acumulados (patrones + outcomes).
  Cada resultado nuevo: micro-actualización online de 50 épocas.
"""
import json
import math
import os
import threading
import time

import numpy as np

from . import memoria as _mem

RUTA_PESOS    = os.path.join(_mem.RUTA_DATA, "red_pesos_v3.npz")
RUTA_OUTCOMES = os.path.join(_mem.RUTA_DATA, "red_outcomes.json")

# ─── Arquitectura ────────────────────────────────────────────────────────────
VENTANA = 14   # velas de contexto binario (ampliado de 12)
N_EXTRA = 6    # features de contexto extra
INP     = VENTANA + N_EXTRA   # 20 features de entrada
OCU1    = 64   # capa 1 (ampliado)
OCU2    = 32   # capa 2
OCU3    = 16   # capa 3 (nueva)

# ─── Hiperparámetros Adam ────────────────────────────────────────────────────
LR_FULL   = 0.003   # learning rate entrenamiento completo
LR_ONLINE = 0.001   # learning rate actualizaciones online (más conservador)
L2        = 1e-4
B1, B2    = 0.9, 0.999
EPS_A     = 1e-8

T_AUTO       = 600   # cada 10 min auto-entrena (reducido de 5 min para ahorrar CPU)
MAX_OUT      = 600   # máximo outcomes guardados en memoria
_PACIENCIA_ES = 15  # épocas sin mejora en val_loss antes de early stopping
_TTL_CACHE   = 3.0  # segundos que dura una predicción cacheada


class RedNeuronal:
    def __init__(self):
        self.ventana   = VENTANA
        self.entrenada = False
        self.ultima_n  = 0
        self._init_pesos()
        self.cargar()
        # Memoria de resultados reales
        self._outcomes = self._cargar_outcomes()
        self._outcome_pendiente: dict | None = None   # predicción sin resultado aún
        # Estadísticas de rendimiento
        self.aciertos_outcomes = 0
        self.total_outcomes    = 0
        # Adam state persistente para actualizaciones online
        self._adam_online = self._nuevo_adam_state()
        self._t_online    = 0
        # Arrancar auto-entrenamiento en segundo plano
        threading.Thread(target=self._bucle_auto,
                         daemon=True, name="LitchRedAuto").start()

    # ─── Inicialización ───────────────────────────────────────────────────────

    def _init_pesos(self):
        rng      = np.random.default_rng(42)
        self.W1  = rng.normal(0, np.sqrt(2.0 / INP),  (INP,  OCU1))
        self.b1  = np.zeros(OCU1)
        self.W2  = rng.normal(0, np.sqrt(2.0 / OCU1), (OCU1, OCU2))
        self.b2  = np.zeros(OCU2)
        self.W3  = rng.normal(0, np.sqrt(2.0 / OCU2), (OCU2, OCU3))
        self.b3  = np.zeros(OCU3)
        self.W4  = rng.normal(0, np.sqrt(2.0 / OCU3), (OCU3, 1))
        self.b4  = np.zeros(1)

    def _nuevo_adam_state(self) -> dict:
        return {
            "mW1": np.zeros((INP, OCU1)),  "vW1": np.zeros((INP, OCU1)),
            "mb1": np.zeros(OCU1),          "vb1": np.zeros(OCU1),
            "mW2": np.zeros((OCU1, OCU2)), "vW2": np.zeros((OCU1, OCU2)),
            "mb2": np.zeros(OCU2),          "vb2": np.zeros(OCU2),
            "mW3": np.zeros((OCU2, OCU3)), "vW3": np.zeros((OCU2, OCU3)),
            "mb3": np.zeros(OCU3),          "vb3": np.zeros(OCU3),
            "mW4": np.zeros((OCU3, 1)),    "vW4": np.zeros((OCU3, 1)),
            "mb4": np.zeros(1),             "vb4": np.zeros(1),
        }

    # ─── Persistencia pesos ──────────────────────────────────────────────────

    def guardar(self):
        try:
            os.makedirs(_mem.RUTA_DATA, exist_ok=True)
            np.savez(RUTA_PESOS,
                     W1=self.W1, b1=self.b1,
                     W2=self.W2, b2=self.b2,
                     W3=self.W3, b3=self.b3,
                     W4=self.W4, b4=self.b4,
                     entrenada=self.entrenada,
                     ultima_n=self.ultima_n)
        except Exception as e:
            print(f"[Red] No se pudo guardar pesos: {e}")

    def cargar(self):
        if not os.path.exists(RUTA_PESOS):
            return
        try:
            d = np.load(RUTA_PESOS, allow_pickle=True)
            if "W4" in d and d["W1"].shape == (INP, OCU1):
                self.W1, self.b1 = d["W1"], d["b1"]
                self.W2, self.b2 = d["W2"], d["b2"]
                self.W3, self.b3 = d["W3"], d["b3"]
                self.W4, self.b4 = d["W4"], d["b4"]
                self.entrenada   = bool(d["entrenada"])
                self.ultima_n    = int(d["ultima_n"])
                print(f"[Red] Pesos v3 cargados (n={self.ultima_n}).")
        except Exception as e:
            print(f"[Red] No se pudo cargar pesos: {e}")

    # ─── Persistencia outcomes ────────────────────────────────────────────────

    def _cargar_outcomes(self) -> list:
        if not os.path.exists(RUTA_OUTCOMES):
            return []
        try:
            with open(RUTA_OUTCOMES, encoding="utf-8") as f:
                data = json.load(f)
            # Recalcular estadísticas
            resueltos = [o for o in data if o.get("resultado") is not None]
            self.aciertos_outcomes = sum(1 for o in resueltos if o["resultado"] == 1)
            self.total_outcomes    = len(resueltos)
            return data
        except Exception:
            return []

    def _guardar_outcomes(self):
        try:
            os.makedirs(_mem.RUTA_DATA, exist_ok=True)
            with open(RUTA_OUTCOMES, "w", encoding="utf-8") as f:
                json.dump(self._outcomes[-MAX_OUT:], f, ensure_ascii=False)
        except Exception as e:
            print(f"[Red] No se pudo guardar outcomes: {e}")

    # ─── Features ────────────────────────────────────────────────────────────

    def _features(self, secuencia, pos=None) -> np.ndarray:
        """Vector de INP=20 features para la posición `pos` (None=última)."""
        if pos is None:
            pos = len(secuencia)
        seg  = list(secuencia[max(0, pos - self.ventana): pos])
        # Cap a 200 velas: EWMA con alpha≤0.30 olvida >99.99% más allá de 100 pasos
        full = list(secuencia[max(0, pos - 200): pos])

        # ── 0-13: 14 velas binarias ──────────────────────────────────────
        candles = [1.0 if c == "V" else 0.0 for c in seg]
        while len(candles) < self.ventana:
            candles.insert(0, 0.5)
        candles = np.array(candles[:self.ventana], dtype=np.float64)

        # ── 14: longitud de racha actual (normalizada) ───────────────────
        ultimo = seg[-1] if seg else "V"
        racha  = 0
        for c in reversed(seg):
            if c == ultimo:
                racha += 1
            else:
                break
        f14 = min(1.0, racha / 10.0)

        # ── 15-17: momentum a 3 escalas ──────────────────────────────────
        def mom(k):
            if len(full) < k:
                return 0.0
            return (sum(1.0 for c in full[-k:] if c == "V") / k - 0.5) * 2.0

        f15, f16, f17 = mom(5), mom(12), mom(25)

        # ── 18: entropía de Shannon de últimas 20 velas (desorden) ───────
        ult20 = full[-20:] if len(full) >= 20 else full
        n20   = len(ult20)
        if n20 < 4:
            h_norm = 1.0
        else:
            cnt_v  = sum(1 for c in ult20 if c == "V")
            p_v    = cnt_v / n20
            p_r    = 1.0 - p_v
            h      = 0.0
            if p_v > 0:
                h -= p_v * math.log2(p_v)
            if p_r > 0:
                h -= p_r * math.log2(p_r)
            h_norm = h  # ya está entre 0 y 1 (H_max=1 para binario)
        f18 = h_norm

        # ── 19: cruce EWMA corta vs larga (señal de tendencia) ───────────
        if len(full) >= 6:
            def ewma(alpha, seq):
                v = 0.5
                for c in seq:
                    v = alpha * (1.0 if c == "V" else 0.0) + (1.0 - alpha) * v
                return v
            diff = ewma(0.30, full) - ewma(0.08, full)
            f19  = max(-1.0, min(1.0, diff * 5.0))  # amplificar y clipar
        else:
            f19 = 0.0

        feat = np.concatenate([candles, [f14, f15, f16, f17, f18, f19]])
        # Sanear NaN/Inf que puedan surgir en historiales cortos o divisiones por cero
        return np.nan_to_num(feat, nan=0.0, posinf=1.0, neginf=-1.0)

    def _dataset(self, secuencia, max_samples: int = 1500):
        n = len(secuencia)
        if n <= self.ventana:
            return np.empty((0, INP)), np.empty((0, 1))
        # Limitar a los últimos max_samples ejemplos para reducir coste O(n²) → O(n)
        start = max(self.ventana, n - max_samples)
        X, y = [], []
        for i in range(start, n):
            X.append(self._features(secuencia, i))
            y.append(1.0 if secuencia[i] == "V" else 0.0)
        return np.array(X, dtype=np.float64), np.array(y, dtype=np.float64).reshape(-1, 1)

    # ─── Forward pass ─────────────────────────────────────────────────────────

    @staticmethod
    def _sig(z):
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))

    def _forward(self, X):
        a1 = np.tanh(X  @ self.W1 + self.b1)
        a2 = np.tanh(a1 @ self.W2 + self.b2)
        a3 = np.tanh(a2 @ self.W3 + self.b3)
        a4 = self._sig(a3 @ self.W4 + self.b4)
        return a1, a2, a3, a4

    # ─── Paso Adam genérico ───────────────────────────────────────────────────

    @staticmethod
    def _adam(w, dw, mw, vw, t, lr):
        mw = B1 * mw + (1 - B1) * dw
        vw = B2 * vw + (1 - B2) * dw ** 2
        mw_ = mw / (1 - B1 ** t)
        vw_ = vw / (1 - B2 ** t)
        return w - lr * mw_ / (np.sqrt(vw_) + EPS_A), mw, vw

    # ─── Entrenamiento completo ───────────────────────────────────────────────

    def entrenar(self, secuencia, epocas=300, lr=LR_FULL,
                 batch=32, extra_X=None, extra_y=None):
        """Reentrena la red con el histórico de velas + outcomes reales.

        extra_X, extra_y: ejemplos adicionales de outcomes reales (opcionales).
        Usa early stopping con 20% de validación para no desperdiciar épocas.
        """
        X, y = self._dataset(secuencia)

        # Outcomes reales pesan 3× más que el histórico sintético
        if extra_X is not None and len(extra_X) > 0:
            X = np.concatenate([X, extra_X, extra_X, extra_X])
            y = np.concatenate([y, extra_y, extra_y, extra_y])

        if len(X) < 24:
            return False

        n   = len(X)
        rng = np.random.default_rng()

        # ── Split 80/20 para early stopping ──────────────────────────────
        perm    = rng.permutation(n)
        n_val   = max(6, int(n * 0.20))
        idx_val = perm[:n_val]
        idx_trn = perm[n_val:]
        X_val, y_val = X[idx_val], y[idx_val]
        X_trn, y_trn = X[idx_trn], y[idx_trn]
        n_trn = len(X_trn)
        idx   = np.arange(n_trn)

        # Adam state fresco para entrenamiento completo
        s = self._nuevo_adam_state()
        t = 0

        mejor_val_loss = float("inf")
        sin_mejora     = 0

        for ep in range(epocas):
            rng.shuffle(idx)
            for start in range(0, n_trn, batch):
                bx = X_trn[idx[start: start + batch]]
                by = y_trn[idx[start: start + batch]]
                nb = max(1, len(bx))
                t += 1
                a1, a2, a3, a4 = self._forward(bx)

                dz4 = (a4 - by) / nb
                dW4 = a3.T @ dz4 + L2 * self.W4
                db4 = dz4.sum(0)

                dz3 = (dz4 @ self.W4.T) * (1 - a3 ** 2)
                dW3 = a2.T @ dz3 + L2 * self.W3
                db3 = dz3.sum(0)

                dz2 = (dz3 @ self.W3.T) * (1 - a2 ** 2)
                dW2 = a1.T @ dz2 + L2 * self.W2
                db2 = dz2.sum(0)

                dz1 = (dz2 @ self.W2.T) * (1 - a1 ** 2)
                dW1 = bx.T @ dz1 + L2 * self.W1
                db1 = dz1.sum(0)

                self.W4, s["mW4"], s["vW4"] = self._adam(self.W4, dW4, s["mW4"], s["vW4"], t, lr)
                self.b4, s["mb4"], s["vb4"] = self._adam(self.b4, db4, s["mb4"], s["vb4"], t, lr)
                self.W3, s["mW3"], s["vW3"] = self._adam(self.W3, dW3, s["mW3"], s["vW3"], t, lr)
                self.b3, s["mb3"], s["vb3"] = self._adam(self.b3, db3, s["mb3"], s["vb3"], t, lr)
                self.W2, s["mW2"], s["vW2"] = self._adam(self.W2, dW2, s["mW2"], s["vW2"], t, lr)
                self.b2, s["mb2"], s["vb2"] = self._adam(self.b2, db2, s["mb2"], s["vb2"], t, lr)
                self.W1, s["mW1"], s["vW1"] = self._adam(self.W1, dW1, s["mW1"], s["vW1"], t, lr)
                self.b1, s["mb1"], s["vb1"] = self._adam(self.b1, db1, s["mb1"], s["vb1"], t, lr)

            # ── Early stopping: val loss por cada época ───────────────────
            _, _, _, pred_val = self._forward(X_val)
            pred_val = np.clip(pred_val, 1e-7, 1.0 - 1e-7)
            val_loss = float(-np.mean(
                y_val * np.log(pred_val) + (1.0 - y_val) * np.log(1.0 - pred_val)))

            if val_loss < mejor_val_loss - 1e-4:
                mejor_val_loss = val_loss
                sin_mejora     = 0
            else:
                sin_mejora += 1
                if sin_mejora >= _PACIENCIA_ES:
                    print(f"[Red] Early stop en época {ep+1}/{epocas} "
                          f"(val_loss={mejor_val_loss:.4f})")
                    break

        self.entrenada = True
        self.ultima_n  = len(secuencia)
        self._limpiar_cache()   # pesos cambiaron — invalidar cache
        self.guardar()
        return True

    def _micro_entrenar(self, X: np.ndarray, y: np.ndarray, epocas: int = 60):
        """Micro-actualización online con los outcomes más recientes."""
        if len(X) < 3:
            return
        n = len(X)
        for _ in range(epocas):
            self._t_online += 1
            t = self._t_online
            s = self._adam_online
            bx, by = X, y

            a1, a2, a3, a4 = self._forward(bx)
            nb = max(1, n)

            dz4 = (a4 - by) / nb
            dW4 = a3.T @ dz4 + L2 * self.W4
            db4 = dz4.sum(0)
            dz3 = (dz4 @ self.W4.T) * (1 - a3 ** 2)
            dW3 = a2.T @ dz3 + L2 * self.W3
            db3 = dz3.sum(0)
            dz2 = (dz3 @ self.W3.T) * (1 - a2 ** 2)
            dW2 = a1.T @ dz2 + L2 * self.W2
            db2 = dz2.sum(0)
            dz1 = (dz2 @ self.W2.T) * (1 - a1 ** 2)
            dW1 = bx.T @ dz1 + L2 * self.W1
            db1 = dz1.sum(0)

            self.W4, s["mW4"], s["vW4"] = self._adam(self.W4, dW4, s["mW4"], s["vW4"], t, LR_ONLINE)
            self.b4, s["mb4"], s["vb4"] = self._adam(self.b4, db4, s["mb4"], s["vb4"], t, LR_ONLINE)
            self.W3, s["mW3"], s["vW3"] = self._adam(self.W3, dW3, s["mW3"], s["vW3"], t, LR_ONLINE)
            self.b3, s["mb3"], s["vb3"] = self._adam(self.b3, db3, s["mb3"], s["vb3"], t, LR_ONLINE)
            self.W2, s["mW2"], s["vW2"] = self._adam(self.W2, dW2, s["mW2"], s["vW2"], t, LR_ONLINE)
            self.b2, s["mb2"], s["vb2"] = self._adam(self.b2, db2, s["mb2"], s["vb2"], t, LR_ONLINE)
            self.W1, s["mW1"], s["vW1"] = self._adam(self.W1, dW1, s["mW1"], s["vW1"], t, LR_ONLINE)
            self.b1, s["mb1"], s["vb1"] = self._adam(self.b1, db1, s["mb1"], s["vb1"], t, LR_ONLINE)

        self._limpiar_cache()   # pesos actualizados — invalidar predicciones cacheadas
        self.guardar()

    # ─── Outcomes: guardar predicción y vincular resultado ────────────────────

    def registrar_prediccion(self, secuencia, direccion: str):
        """Guarda la predicción hecha para vincularla con el resultado futuro."""
        feat = self._features(secuencia).tolist()
        self._outcome_pendiente = {
            "t":         time.time(),
            "features":  feat,
            "direccion": direccion,
            "resultado": None
        }

    def registrar_resultado(self, acerto: bool, secuencia=None):
        """Vincula el resultado con la predicción pendiente y micro-entrena.

        acerto: True si la predicción fue correcta (la vela fue la esperada).
        """
        if self._outcome_pendiente is None:
            return
        self._outcome_pendiente["resultado"]   = 1.0 if acerto else 0.0
        self._outcome_pendiente["t_resultado"] = time.time()

        self._outcomes.append(self._outcome_pendiente)
        self._outcome_pendiente = None
        self._outcomes = self._outcomes[-MAX_OUT:]

        # Actualizar estadísticas
        self.total_outcomes += 1
        if acerto:
            self.aciertos_outcomes += 1
        prec = self.aciertos_outcomes / self.total_outcomes if self.total_outcomes else 0
        print(f"[Red] Resultado registrado. Precisión en outcomes: "
              f"{self.aciertos_outcomes}/{self.total_outcomes} = {prec:.1%}")

        self._guardar_outcomes()

        # Micro-entrenamiento inmediato con los últimos 30 outcomes
        labeled = [o for o in self._outcomes
                   if o.get("resultado") is not None][-30:]
        if len(labeled) >= 5:
            X = np.array([o["features"] for o in labeled], dtype=np.float64)
            y = np.array([o["resultado"] for o in labeled],
                         dtype=np.float64).reshape(-1, 1)
            threading.Thread(
                target=lambda: self._micro_entrenar(X, y, epocas=50),
                daemon=True, name="LitchMicro").start()

    # ─── Auto-entrenamiento en segundo plano ──────────────────────────────────

    def _bucle_auto(self):
        """Cada T_AUTO segundos reentrena con todo lo acumulado."""
        time.sleep(60)   # esperar arranque inicial
        while True:
            time.sleep(T_AUTO)
            try:
                self._auto_entrenar()
            except Exception as e:
                print(f"[Red Auto] Error: {e}")

    def _auto_entrenar(self):
        """Re-entrena usando la secuencia guardada + outcomes reales."""
        from . import memoria as _m
        mem = _m.cargar()
        sec = mem.get("secuencia", [])
        if len(sec) < self.ventana + 24:
            return

        # Outcomes con resultado conocido
        labeled = [o for o in self._outcomes if o.get("resultado") is not None]
        eX, ey = None, None
        if len(labeled) >= 5:
            eX = np.array([o["features"] for o in labeled], dtype=np.float64)
            ey = np.array([o["resultado"] for o in labeled],
                          dtype=np.float64).reshape(-1, 1)

        ok = self.entrenar(sec, epocas=350, extra_X=eX, extra_y=ey)
        if ok:
            prec = self.precision_aprox(sec) or 0
            n_out = len(labeled)
            print(f"[Red Auto] Reentrenado — sec={len(sec)} outcomes={n_out} "
                  f"precisión_histórica={prec:.1%}")

    # ─── Reentrenamiento por trigger ──────────────────────────────────────────

    def quizas_reentrenar(self, secuencia, cada=25):
        """Reentrena cuando han llegado N velas nuevas desde el último entrenamiento."""
        if (len(secuencia) - self.ultima_n >= cada
                and len(secuencia) > self.ventana + 24):
            labeled = [o for o in self._outcomes if o.get("resultado") is not None]
            eX, ey = None, None
            if len(labeled) >= 5:
                eX = np.array([o["features"] for o in labeled], dtype=np.float64)
                ey = np.array([o["resultado"] for o in labeled],
                              dtype=np.float64).reshape(-1, 1)
            # Usar 200 épocas como máximo; early stopping corta antes si converge
            return self.entrenar(secuencia, epocas=200, extra_X=eX, extra_y=ey)
        return False

    # ─── Predicción ───────────────────────────────────────────────────────────

    def predecir(self, secuencia):
        """Devuelve (dirección 'V'/'R'/None, prob_verde 0..1)."""
        if not self.entrenada or len(secuencia) < self.ventana:
            return None, 0.5
        # Cache: misma secuencia reciente → reutilizar resultado sin recalcular
        _key = tuple(secuencia[-self.ventana:])
        _now = time.time()
        _hit = getattr(self, "_pred_cache", {}).get(_key)
        if _hit and _now - _hit[2] < _TTL_CACHE:
            return _hit[0], _hit[1]
        x = self._features(secuencia).reshape(1, -1)
        _, _, _, a4 = self._forward(x)
        p   = float(a4[0, 0])
        dir_ = "V" if p >= 0.5 else "R"
        # Guardar en cache
        if not hasattr(self, "_pred_cache"):
            self._pred_cache = {}
        self._pred_cache[_key] = (dir_, p, _now)
        if len(self._pred_cache) > 64:   # evitar crecimiento infinito
            _oldest = min(self._pred_cache, key=lambda k: self._pred_cache[k][2])
            del self._pred_cache[_oldest]
        return dir_, p

    def predecir_completo(self, secuencia) -> dict:
        """
        Versión extendida usada por el hilo Red Maestra en trading.py.
        Devuelve dict con 'direccion', 'probabilidad', 'entrenada', 'confianza'.
        """
        if not self.entrenada or len(secuencia) < self.ventana:
            return {"entrenada": False, "direccion": None,
                    "probabilidad": 0.5, "confianza": 0.0}
        dir_, prob = self.predecir(secuencia)
        confianza  = abs(prob - 0.5) * 2.0   # 0 = sin confianza, 1 = seguro
        return {
            "entrenada":    True,
            "direccion":    dir_,
            "probabilidad": prob,
            "confianza":    round(confianza, 4),
        }

    def _limpiar_cache(self):
        """Invalida la cache de predicciones (llamar cuando los pesos cambian)."""
        if hasattr(self, "_pred_cache"):
            self._pred_cache.clear()

    def precision_aprox(self, secuencia):
        """Precisión sobre el histórico (referencia informativa)."""
        X, y = self._dataset(secuencia)
        if len(X) < 10 or not self.entrenada:
            return None
        _, _, _, a4 = self._forward(X)
        return float(((a4 >= 0.5).astype(float) == y).mean())

    def resumen(self, secuencia) -> str:
        """Texto de estado de la red para mostrar en la interfaz."""
        if not self.entrenada:
            return "Red neuronal v3: no entrenada aún."
        p = self.precision_aprox(secuencia) or 0
        out_txt = (f" · Outcomes reales: {self.aciertos_outcomes}/{self.total_outcomes}"
                   if self.total_outcomes else "")
        return (f"Red neuronal v3 (3 capas, 20 features, Adam) · "
                f"Precisión histórica: {p:.1%}{out_txt}")

"""
grafo_conocimiento.py — Grafo de Conocimiento para LITCH v3.

Inspirado en el modelo de notas enlazadas de Obsidian:
  cada "concepto" (patrón, hora, régimen, activo, combinación de votos)
  es un NODO, y los resultados de trades son las ARISTAS que los conectan.

Con el tiempo LITCH construye un mapa mental de relaciones no obvias:

  patrón BOS  ──[+85% WR]──→  régimen TRENDING + hora London
  RSI_sobreventa ──[+79%]──→  activo EUR/AUD + lunes
  4_votos  ──[-30% WR]──→  sesión asiática + caótico

El grafo permite RAZONAMIENTO CONTEXTUAL:
  "¿Cuánto confío en esta señal dado TODO el contexto actual?"

100% Python puro, sin dependencias externas.
Persistencia en JSON.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import defaultdict
from typing import Optional


_RUTA_DEFAULT = os.path.join(
    os.path.dirname(__file__), "..", "memoria_ap", "grafo_conocimiento.json")

# Mínimo de observaciones para que un nodo sea confiable
_MIN_OBS = 5

# Decaimiento temporal: los trades más antiguos pesan menos
_DECAY_DIAS = 30.0   # medio tiempo = 30 días


class Nodo:
    """Representa un concepto (patron, hora, activo, régimen…)."""
    __slots__ = ("clave", "wins", "losses", "peso_total",
                 "ultima_vez", "vecinos")

    def __init__(self, clave: str):
        self.clave       = clave
        self.wins        = 0.0
        self.losses      = 0.0
        self.peso_total  = 0.0
        self.ultima_vez  = time.time()
        self.vecinos: dict[str, float] = {}  # clave_vecino → co-ocurrencias WIN

    @property
    def n(self) -> int:
        return int(self.wins + self.losses)

    @property
    def wr(self) -> float:
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.5

    def to_dict(self) -> dict:
        return {
            "wins":       self.wins,
            "losses":     self.losses,
            "peso_total": self.peso_total,
            "ultima_vez": self.ultima_vez,
            "vecinos":    self.vecinos,
        }

    @classmethod
    def from_dict(cls, clave: str, d: dict) -> "Nodo":
        n = cls(clave)
        n.wins       = float(d.get("wins",       0))
        n.losses     = float(d.get("losses",     0))
        n.peso_total = float(d.get("peso_total", 0))
        n.ultima_vez = float(d.get("ultima_vez", time.time()))
        n.vecinos    = dict(d.get("vecinos",     {}))
        return n


class GrafoConocimiento:
    """
    Grafo de conocimiento de trading construido desde la experiencia real.

    Ejemplo de uso:
        gk = GrafoConocimiento()

        # Registrar un trade
        gk.registrar(
            contexto = {
                "patron":  "BOS",
                "regimen": "trending_up",
                "hora":    "17",
                "activo":  "EUR/AUD",
                "votos":   "6",
                "sesion":  "ny",
            },
            gano = True,
        )

        # Consultar probabilidad contextual
        prob = gk.probabilidad_contextual({
            "patron":  "BOS",
            "regimen": "trending_up",
            "hora":    "17",
        })
        # → 0.82 (basado en experiencia histórica)

        # Vecinos más fuertes de un patrón
        relaciones = gk.vecinos_top("patron:BOS", top=5)
        # → [("regimen:trending_up", 0.88), ("hora:17", 0.83), ...]
    """

    def __init__(self, ruta: str = None):
        self._ruta  = ruta or _RUTA_DEFAULT
        self._lock  = threading.Lock()
        self._nodos: dict[str, Nodo] = {}
        self._cargar()

    # ── API pública ───────────────────────────────────────────────────────────

    def registrar(self, contexto: dict, gano: bool,
                  peso: float = 1.0) -> None:
        """
        Registra el resultado de un trade con su contexto completo.

        contexto puede tener cualquier combinación de claves:
          patron, regimen, hora, activo, votos, sesion, dia_semana
        """
        with self._lock:
            claves = self._claves_de(contexto)
            ahora  = time.time()

            # Calcular peso temporal (decaimiento exponencial)
            for clave in claves:
                nodo = self._get_o_crear(clave)
                nodo.ultima_vez = ahora
                if gano:
                    nodo.wins    += peso
                else:
                    nodo.losses  += peso
                nodo.peso_total += peso

            # Actualizar co-ocurrencias (aristas del grafo)
            if gano:
                for i, c1 in enumerate(claves):
                    for c2 in claves[i + 1:]:
                        n1 = self._nodos[c1]
                        n2 = self._nodos[c2]
                        n1.vecinos[c2] = n1.vecinos.get(c2, 0.0) + peso
                        n2.vecinos[c1] = n2.vecinos.get(c1, 0.0) + peso

        # Guardar cada 25 registros
        self._contador_reg = getattr(self, "_contador_reg", 0) + 1
        if self._contador_reg % 25 == 0:
            self._guardar_async()

    def probabilidad_contextual(self, contexto: dict,
                                 min_confianza: float = 0.4) -> float:
        """
        Estima la probabilidad de éxito dado el contexto actual.

        Combina los WR individuales de cada factor con el peso
        de sus co-ocurrencias (nodos conectados en el grafo).

        Retorna un float [0.50 – 0.95].
        """
        with self._lock:
            claves = self._claves_de(contexto)
            pesos  = []
            for clave in claves:
                nodo = self._nodos.get(clave)
                if nodo is None or nodo.n < _MIN_OBS:
                    continue
                # WR con suavizado Laplace
                wr_suav = (nodo.wins + 1) / (nodo.n + 2)
                # Factor de confianza: más observaciones → más peso
                confianza = min(1.0, nodo.n / 50)
                pesos.append((wr_suav, confianza))

            if not pesos:
                return 0.55   # prior neutro con ligero sesgo positivo

            # Media ponderada por confianza
            suma_w = sum(c for _, c in pesos)
            if suma_w < 1e-9:
                return 0.55
            prob = sum(wr * c for wr, c in pesos) / suma_w

            # Bonus por sinergia: co-ocurrencias fuertes entre nodos
            synergy = self._calcular_sinergia(claves)
            prob = prob * 0.80 + synergy * 0.20

            return round(min(0.95, max(0.40, prob)), 4)

    def vecinos_top(self, clave_nodo: str, top: int = 5) -> list[tuple]:
        """
        Devuelve los conceptos más frecuentemente relacionados con este nodo
        cuando resultan en victorias.

        Retorna lista de (clave_vecino, fuerza_relacion [0-1]).
        """
        with self._lock:
            nodo = self._nodos.get(clave_nodo)
            if nodo is None:
                return []
            if not nodo.vecinos:
                return []
            max_v = max(nodo.vecinos.values()) or 1.0
            ordenados = sorted(
                nodo.vecinos.items(),
                key=lambda x: -x[1])[:top]
            return [(k, round(v / max_v, 3)) for k, v in ordenados]

    def insights_contexto(self, contexto: dict) -> str:
        """
        Genera un texto de análisis contextual para LITCH:
        describe qué sabe el grafo sobre este contexto específico.
        """
        with self._lock:
            claves  = self._claves_de(contexto)
            lineas  = []
            for clave in claves[:4]:   # max 4 factores
                nodo = self._nodos.get(clave)
                if nodo is None or nodo.n < _MIN_OBS:
                    continue
                nombre  = clave.split(":", 1)[-1].upper()
                wr_pct  = int(nodo.wr * 100)
                col     = "✓" if nodo.wr >= 0.60 else ("~" if nodo.wr >= 0.45 else "✗")
                lineas.append(
                    f"{nombre}: {wr_pct}% WR ({nodo.n} obs) {col}")

            if not lineas:
                return "Grafo: sin datos suficientes para este contexto."
            prob = self.probabilidad_contextual(contexto)
            return (f"[Grafo] Prob contextual: {prob:.0%} — "
                    + " | ".join(lineas))

    def estadisticas(self) -> dict:
        """Estadísticas globales del grafo."""
        with self._lock:
            total_nodos  = len(self._nodos)
            total_aristas = sum(len(n.vecinos) for n in self._nodos.values()) // 2
            nodo_top = max(self._nodos.values(), key=lambda n: n.wr * min(n.n, 100),
                           default=None)
        return {
            "nodos":         total_nodos,
            "aristas":       total_aristas,
            "nodo_estrella": nodo_top.clave if nodo_top else None,
            "wr_estrella":   round(nodo_top.wr, 3) if nodo_top else 0,
        }

    def resumen_texto(self) -> str:
        st = self.estadisticas()
        return (f"[Grafo] {st['nodos']} conceptos | "
                f"{st['aristas']} relaciones | "
                f"mejor factor: {st['nodo_estrella']} "
                f"WR={st['wr_estrella']:.0%}")

    # ── Internos ──────────────────────────────────────────────────────────────

    def _claves_de(self, contexto: dict) -> list[str]:
        """Convierte un dict de contexto en lista de claves de nodo."""
        claves = []
        mapeo  = {
            "patron":      "pat",
            "regimen":     "reg",
            "hora":        "hora",
            "activo":      "activo",
            "votos":       "votos",
            "sesion":      "sesion",
            "dia_semana":  "dia",
            "asset":       "activo",
        }
        for k, v in contexto.items():
            prefijo = mapeo.get(k)
            if prefijo and v:
                claves.append(f"{prefijo}:{str(v).lower()[:20]}")
        return claves

    def _get_o_crear(self, clave: str) -> Nodo:
        if clave not in self._nodos:
            self._nodos[clave] = Nodo(clave)
        return self._nodos[clave]

    def _calcular_sinergia(self, claves: list[str]) -> float:
        """Co-ocurrencia media entre los nodos activos."""
        if len(claves) < 2:
            return 0.55
        synergies = []
        for i, c1 in enumerate(claves):
            n1 = self._nodos.get(c1)
            if n1 is None:
                continue
            for c2 in claves[i + 1:]:
                if c2 in n1.vecinos:
                    n2 = self._nodos.get(c2)
                    if n2 and n2.n >= _MIN_OBS:
                        # Co-ocurrencia normalizada por el total de victorias
                        total_wins = max(n1.wins, 1)
                        synergy    = min(1.0, n1.vecinos[c2] / total_wins)
                        synergies.append(synergy * n2.wr)
        if not synergies:
            return 0.55
        return float(sum(synergies) / len(synergies))

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _cargar(self) -> None:
        if not os.path.exists(self._ruta):
            return
        try:
            with open(self._ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            for clave, d in datos.items():
                self._nodos[clave] = Nodo.from_dict(clave, d)
        except Exception as e:
            print(f"[Grafo] Error cargando: {e}")

    def _guardar(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._ruta), exist_ok=True)
            with self._lock:
                snapshot = {k: v.to_dict() for k, v in self._nodos.items()}
            with open(self._ruta, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False)
        except Exception as e:
            print(f"[Grafo] Error guardando: {e}")

    def _guardar_async(self) -> None:
        import threading
        threading.Thread(target=self._guardar, daemon=True,
                         name="GrafoSave").start()

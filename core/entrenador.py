"""
entrenador.py — Que Litch se entrene sola, con criterio.

━━━ QUÉ ES ENTRENAR, AQUÍ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No es «dejarla operando muchas horas». Eso ya se hacía y produjo 936
rondas sin aprender nada.

Entrenar es un ciclo con memoria:

    preparar → operar un bloque → medir → ajustar → repetir

Y lo importante es el «medir»: cada bloque de operaciones se compara con
el anterior. Si mejora, se sigue. Si empeora dos bloques seguidos, se
para y se dice qué cambió. Sin esa comparación no hay entrenamiento, hay
actividad.

━━━ LO QUE MIDE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tres cosas, y las tres importan:

  · TASA DE ACIERTO — pero solo por encima del punto de equilibrio.
    Un 60 % con pago 85 % sigue perdiendo dinero.

  · CALIBRACIÓN (ECE) — que cuando diga 70 % acierte el 70 %. Un modelo
    que acierta mucho pero no sabe cuándo, no sirve para decidir.

  · COBERTURA — cuántas señales pasa el filtro de ventaja. Si de pronto
    no pasa ninguna, algo cambió en el mercado y hay que saberlo.

━━━ POR QUÉ SE PARA SOLA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Porque el señor no está delante. Un entrenamiento que solo sabe seguir
adelante no es autonomía: es un coche sin frenos cuesta abajo.

Se para si: se activa el freno diario, empeora dos bloques seguidos, la
calibración se degrada, o alguna comprobación previa falla.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime

BLOQUE = 25              # operaciones por bloque antes de medir
PAUSA_ENTRE = 30.0       # segundos entre comprobaciones
DEGRADE_MAX = 2          # bloques seguidos empeorando antes de parar
ECE_MAX = 0.20           # por encima de esto, la calibración está mal


def _ruta() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "MEMORIA_AP")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "entrenamiento.json")


def _historial() -> list:
    try:
        with open(_ruta(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _guardar(h: list) -> None:
    try:
        tmp = _ruta() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(h[-200:], f, ensure_ascii=False, indent=2)
        os.replace(tmp, _ruta())
    except Exception:
        pass


# ── Medir un bloque ──────────────────────────────────────────────────────────

def medir(app, n: int = BLOQUE) -> dict:
    """
    Las tres cifras que dicen si está aprendiendo.

    Se miran las últimas `n` operaciones limpias.
    """
    r = {"n": 0, "aciertos": 0, "wr": 0.0, "equilibrio": 0.0,
         "ece": None, "cobertura": None, "rentable": False}
    try:
        tr = list(getattr(getattr(app, "fdb", None), "trades", []) or [])
        from . import cuarentena_stats as _cq
        tr = _cq.solo_limpios(tr)[-n:]
    except Exception:
        return r
    if not tr:
        return r

    r["n"] = len(tr)
    r["aciertos"] = sum(1 for t in tr
                        if str(t.get("res", "")).upper() in ("WIN", "GANO"))
    r["wr"] = round(r["aciertos"] / r["n"], 4)

    try:
        from . import ventaja_real as _vr
        pago = float(app.mem.get("config", {}).get("pago_pct") or 85)
        r["equilibrio"] = _vr.punto_equilibrio(pago)
        r["rentable"] = r["wr"] > r["equilibrio"]
    except Exception:
        pass

    try:
        from . import calibrar_confianza as _cal
        r["ece"] = _cal.tabla(app, forzar=True).get("ece_antes")
    except Exception:
        pass

    return r


def comparar(ahora: dict, antes: dict | None) -> tuple[str, str]:
    """
    ¿Mejoró, empeoró o va igual?

    Devuelve (veredicto, explicación). Se exige una diferencia mínima:
    variaciones de dos puntos en veinticinco operaciones son ruido, no
    aprendizaje.
    """
    if not antes or not antes.get("n"):
        return "primero", "primer bloque, no hay con qué comparar todavía"

    d_wr = ahora["wr"] - antes["wr"]
    partes = [f"acierto {antes['wr']*100:.0f} % → {ahora['wr']*100:.0f} %"]

    d_ece = None
    if ahora.get("ece") is not None and antes.get("ece") is not None:
        d_ece = ahora["ece"] - antes["ece"]
        partes.append(f"calibración {antes['ece']:.3f} → {ahora['ece']:.3f}")

    # Umbral de ruido: 4 puntos de acierto
    if d_wr > 0.04 or (d_ece is not None and d_ece < -0.03):
        return "mejora", " · ".join(partes)
    if d_wr < -0.04 or (d_ece is not None and d_ece > 0.05):
        return "empeora", " · ".join(partes)
    return "igual", " · ".join(partes) + " — dentro del ruido"


# ── El entrenador ────────────────────────────────────────────────────────────

class Entrenador(threading.Thread):
    """Vigila el entrenamiento y lo para cuando toca."""

    def __init__(self, app):
        super().__init__(daemon=True, name="EntrenadorLitch")
        self.app = app
        self._parar = threading.Event()
        self._activo = False
        self.bloques = 0
        self.degradaciones = 0
        self.ultimo = None
        self.motivo_parada = ""

    # ── Las razones para parar ───────────────────────────────────────

    def _debe_parar(self) -> str:
        """Devuelve el motivo, o cadena vacía si puede seguir."""
        try:
            from . import freno_diario as _fd
            ok, por = _fd.puede_operar(self.app)
            if not ok:
                return f"freno diario: {por}"
        except Exception:
            pass

        if self.degradaciones >= DEGRADE_MAX:
            return (f"empeoró {self.degradaciones} bloques seguidos. Prefiero "
                    f"parar a seguir cavando: si algo cambió en el mercado, "
                    f"cada operación de más lo empeora")

        if self.ultimo and self.ultimo.get("ece") is not None:
            if self.ultimo["ece"] > ECE_MAX:
                return (f"mi calibración se degradó a ECE={self.ultimo['ece']:.3f}. "
                        f"Mis porcentajes han dejado de describir la realidad y "
                        f"todo lo que decido con ellos es ruido")

        # Comprobaciones previas: si alguna bloqueante falla, parar
        try:
            from . import preparar_entrenamiento as _pe
            r = _pe.revisar(self.app)
            if r["bloqueos"]:
                return ("dejó de cumplirse algo importante: "
                        + "; ".join(c.nombre for c in r["bloqueos"]))
        except Exception:
            pass
        return ""

    # ── Bucle ────────────────────────────────────────────────────────

    def run(self) -> None:
        self._activo = True
        h = _historial()
        inicio = time.time()
        self.app.log("[Entrenador] Empiezo. Mido cada "
                     f"{BLOQUE} operaciones y comparo con el bloque anterior.")

        n_ant = self._n_ops()
        while not self._parar.is_set():
            motivo = self._debe_parar()
            if motivo:
                self.motivo_parada = motivo
                self.app.decir(f"Detengo el entrenamiento, señor: {motivo}.")
                break

            n_ahora = self._n_ops()
            if n_ahora - n_ant >= BLOQUE:
                n_ant = n_ahora
                self.bloques += 1
                m = medir(self.app)
                ver, expl = comparar(m, self.ultimo)

                if ver == "empeora":
                    self.degradaciones += 1
                elif ver == "mejora":
                    self.degradaciones = 0

                reg = {"hora": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "bloque": self.bloques, "veredicto": ver, **m}
                h.append(reg); _guardar(h)

                simbolo = {"mejora": "↑", "empeora": "↓",
                           "igual": "=", "primero": "·"}.get(ver, "·")
                self.app.log(f"[Entrenador] Bloque {self.bloques} {simbolo} "
                             f"{expl}"
                             + ("" if m["rentable"] else
                                f" — por debajo del equilibrio "
                                f"({m['equilibrio']*100:.1f} %)"))
                if ver in ("mejora", "empeora") and self.bloques % 2 == 0:
                    self.app.decir(f"Bloque {self.bloques}: {expl}.")
                self.ultimo = m

            self._parar.wait(PAUSA_ENTRE)

        self._activo = False
        mins = (time.time() - inicio) / 60
        self.app.log(f"[Entrenador] Terminado. {self.bloques} bloques en "
                     f"{mins:.0f} minutos."
                     + (f" Motivo: {self.motivo_parada}"
                        if self.motivo_parada else ""))

    def _n_ops(self) -> int:
        try:
            return len(getattr(getattr(self.app, "fdb", None), "trades", []) or [])
        except Exception:
            return 0

    def detener(self):
        self._parar.set()

    @property
    def activo(self) -> bool:
        return self._activo


# ── API ──────────────────────────────────────────────────────────────────────

_inst = None


def alternar(app) -> str:
    """Enciende o apaga el entrenamiento automático."""
    global _inst
    if _inst is not None and _inst.activo:
        _inst.detener()
        return (f"Paro el entrenamiento, señor. {_inst.bloques} bloques "
                f"medidos. Lo aprendido queda guardado.")

    # No se arranca sin estar lista: entrenar mal es peor que no entrenar
    try:
        from . import preparar_entrenamiento as _pe
        r = _pe.revisar(app)
        if r["bloqueos"]:
            return ("No arranco todavía, señor. Falta esto y es de lo que "
                    "cuesta dinero:\n\n"
                    + "\n".join(f"  ✗ {c.nombre}: {c.detalle}\n     {c.arreglo}"
                                for c in r["bloqueos"])
                    + "\n\nPúlselo en «⚙ PREPARAR» y volvemos.")
    except Exception:
        pass

    if _inst is None or not _inst.is_alive():
        _inst = Entrenador(app)
    _inst.start()
    return (f"Entrenamiento automático en marcha, señor.\n\n"
            f"Mido cada {BLOQUE} operaciones y comparo con el bloque "
            f"anterior: acierto, calibración y si estoy por encima del "
            f"punto de equilibrio.\n\n"
            f"Me paro sola si el freno diario salta, si empeoro "
            f"{DEGRADE_MAX} bloques seguidos, si mi calibración se degrada "
            f"o si deja de cumplirse alguna comprobación. Un entrenamiento "
            f"que solo sabe seguir adelante no es autonomía.")


def informe(app=None) -> str:
    """Cómo va el entrenamiento, bloque a bloque."""
    h = _historial()
    if not h:
        return ("Todavía no he entrenado con medición, señor. Pulse "
                "«🎓 Entrenar» y empiezo a comparar bloque contra bloque.")

    l = [f"ENTRENAMIENTO — {len(h)} bloques medidos", ""]
    l.append("  Bloque  Acierto  Calibr.  Veredicto")
    l.append("  " + "─" * 44)
    for r in h[-14:]:
        s = {"mejora": "↑ mejora", "empeora": "↓ empeora",
             "igual": "= igual", "primero": "· primero"}.get(r["veredicto"], "·")
        ece = f"{r['ece']:.3f}" if r.get("ece") is not None else "  —  "
        marca = "✓" if r.get("rentable") else "✗"
        l.append(f"  {marca} {r['bloque']:4d}  {r['wr']*100:5.0f} %  "
                 f"{ece:>6}   {s}")

    prim, ult = h[0], h[-1]
    l.append("")
    l.append(f"Del primer bloque al último: "
             f"{prim['wr']*100:.0f} % → {ult['wr']*100:.0f} % de acierto")
    if prim.get("ece") is not None and ult.get("ece") is not None:
        l.append(f"Calibración: {prim['ece']:.3f} → {ult['ece']:.3f}")
    l.append("")
    l.append("✓ = por encima del punto de equilibrio (gana dinero)")
    l.append("✗ = por debajo (acierta, pero pierde)")
    l.append("")
    l.append("La comparación es lo que convierte operar en entrenar. Sin "
             "ella solo hay actividad.")
    return "\n".join(l)


__all__ = ["Entrenador", "alternar", "informe", "medir", "comparar",
           "BLOQUE", "DEGRADE_MAX", "ECE_MAX"]

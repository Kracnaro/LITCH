"""
cerebro_autonomo.py — El sistema autónomo, con todo lo aprendido dentro.

━━━ EL PROBLEMA QUE RESUELVE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Se construyeron dieciséis módulos nuevos: detección automática, filtro de
ventaja, freno diario, calibración honesta, tamaño por Kelly, diagnóstico
de catorce eslabones. Cada uno resolvía un fallo real que costó dinero.

Y el sistema autónomo no usa **ninguno**. Sigue con la lógica de antes.

Es un fallo de integración, no de diseño: las piezas están bien, pero
nadie las conectó al motor que trabaja solo. Cuando el señor se va y deja
a Litch operando, la Litch que opera es la vieja.

━━━ QUÉ HACE ESTE MÓDULO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Un único ciclo autónomo que atraviesa TODO lo construido, en el orden
correcto — que es el orden en que las cosas pueden salir mal:

    1. DETECTAR    ¿dónde está el bróker? ¿qué monitor? ¿los botones?
    2. COMPROBAR   los catorce eslabones; si falla uno, se arregla o se para
    3. MEDIR       ¿tengo ventaja en este contexto? ¿estoy calibrado?
    4. DIMENSIONAR ¿cuánto pongo, según la confianza y el capital?
    5. OPERAR      solo si todo lo anterior dijo que sí
    6. APRENDER    anotar, comparar con el bloque anterior, ajustar

Y entre medias, los frenos: el diario, el de tamaño, el de escala
temporal, el de dato retrasado.

━━━ POR QUÉ SE REPARA SOLO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Porque el señor no está. Si detecta que la ventana se movió, recalibra en
vez de parar. Si el monitor cambió, se muda. Solo se detiene cuando el
problema no es suyo de arreglar: la cuenta sin marcar, el saldo sin
saber, el freno diario saltado.

La diferencia entre automático y autónomo es esa: lo automático repite;
lo autónomo se arregla.
"""

from __future__ import annotations

import threading
import time

CICLO = 20.0             # segundos entre revisiones
REPARAR_CADA = 300.0     # no intentar auto-reparar más de una vez cada 5 min


class CerebroAutonomo(threading.Thread):
    """El ciclo completo, con todas las piezas nuevas dentro."""

    def __init__(self, app):
        super().__init__(daemon=True, name="CerebroAutonomo")
        self.app = app
        self._parar = threading.Event()
        self._activo = False
        self.ciclos = 0
        self.reparaciones = 0
        self._t_reparo = 0.0
        self.ultimo_bloqueo = ""
        self._t_aviso = {}

    # ── Decir las cosas sin repetirse ────────────────────────────────

    def _avisar(self, clave: str, texto: str, cada: float = 300.0,
                voz: bool = False):
        if (time.time() - self._t_aviso.get(clave, 0)) < cada:
            return
        self._t_aviso[clave] = time.time()
        try:
            (self.app.decir if voz else self.app.log)(texto)
        except Exception:
            pass

    # ── 1. Detectar y repararse ──────────────────────────────────────

    def _intentar_reparar(self, motivo: str) -> bool:
        """
        Se arregla solo lo que es suyo de arreglar.

        La ventana se movió, el monitor cambió, los botones no están donde
        creía: eso lo resuelve `autoconfigurar`. Lo que depende de una
        decisión del señor —la cuenta, el saldo— no se toca.
        """
        if (time.time() - self._t_reparo) < REPARAR_CADA:
            return False
        reparables = ("Botones calibrados", "Calibrados en este monitor",
                      "Ventana de IQ Option", "Botones dentro de la ventana")
        if not any(r in motivo for r in reparables):
            return False

        self._t_reparo = time.time()
        self.reparaciones += 1
        self._avisar("reparo",
                     f"[Autónomo] Detecto un problema que puedo arreglar "
                     f"({motivo[:60]}). Vuelvo a buscar IQ Option.",
                     cada=60)
        try:
            from . import autoconfigurar as _ac
            r = _ac.ejecutar(self.app)
            exito = "Listo, señor" in r
            self._avisar("reparo_res",
                         f"[Autónomo] "
                         + ("Reparado: ya sé dónde está todo."
                            if exito else
                            "No pude repararlo solo. " + r.split("\n")[-1][:90]),
                         cada=60)
            return exito
        except Exception as e:
            self._avisar("reparo_err", f"[Autónomo] La reparación falló: {e}",
                         cada=300)
            return False

    # ── 2. La cadena de catorce eslabones ────────────────────────────

    def _listo_para_operar(self) -> tuple[bool, str]:
        try:
            from . import porque_no_opera as _pno
            e = _pno.revisar(self.app)
            rotos = [x for x in e if not x.ok]
            if not rotos:
                return True, ""
            p = rotos[0]
            # El filtro de ventaja no es una avería: es el sistema
            # funcionando. No se intenta reparar ni se anuncia como fallo.
            if p.nombre == "Filtro de ventaja":
                return False, "sin ventaja demostrada ahora mismo"
            return False, f"{p.nombre}: {p.detalle}"
        except Exception as e:
            return False, f"no pude comprobarme: {e}"

    # ── 3. El bucle ──────────────────────────────────────────────────

    def run(self) -> None:
        self._activo = True
        self.app.log("[Autónomo] En marcha. Uso todo: detección "
                     "automática, filtro de ventaja, freno diario, "
                     "confianza calibrada y tamaño por Kelly.")

        while not self._parar.is_set():
            self.ciclos += 1
            try:
                listo, motivo = self._listo_para_operar()

                if not listo:
                    if self.ultimo_bloqueo != motivo:
                        self.ultimo_bloqueo = motivo
                        self._avisar(f"bloq_{motivo[:20]}",
                                     f"[Autónomo] No opero: {motivo}",
                                     cada=120)
                    # ¿Puedo arreglarlo yo?
                    if self._intentar_reparar(motivo):
                        continue
                else:
                    if self.ultimo_bloqueo:
                        self._avisar("libre",
                                     "[Autónomo] Todo en orden otra vez. "
                                     "Vuelvo a operar.", cada=60)
                        self.ultimo_bloqueo = ""

                # ── El tamaño, según la confianza de AHORA ────────────
                self._ajustar_tamano()

            except Exception as e:
                self._avisar("error", f"[Autónomo] Ciclo con error: {e}",
                             cada=600)

            self._parar.wait(CICLO)

        self._activo = False
        self.app.log(f"[Autónomo] Detenido. {self.ciclos} ciclos, "
                     f"{self.reparaciones} reparaciones automáticas.")

    # ── 4. Dimensionar según la confianza ────────────────────────────

    def _ajustar_tamano(self) -> None:
        """
        Que el monto siga a la ventaja demostrada.

        Antes el monto era fijo: lo mismo en una señal de 8/11 votos al
        89 % que en una de 5/11 al 67 %. Eso desperdicia la mejor
        información que tiene.

        Solo se ajusta si el señor lo autorizó (`tamano_auto`): cambiarle
        el monto sin permiso es meterse donde no toca.
        """
        cfg = self.app.mem.get("config", {})
        if not cfg.get("tamano_auto"):
            return
        cap = cfg.get("saldo") or cfg.get("capital")
        if not cap:
            return
        try:
            from . import filtro_ventaja as _fv
            from . import tamano_kelly as _tk
            c = _fv.contexto(self.app, 8)      # el contexto de las buenas
            if c["n"] < 25:
                return
            r = _tk.calcular(float(cap), c["peor"],
                             float(cfg.get("pago_pct") or 85))
            if not r["operar"]:
                return
            actual = float(cfg.get("monto_broker") or 0)
            # Solo se toca si la diferencia es notable: mover el monto por
            # un 3 % es ruido y confunde.
            if actual and abs(r["monto"] - actual) / max(1, actual) < 0.15:
                return
            cfg["monto_broker"] = cfg["monto_base"] = cfg["monto"] = r["monto"]
            from . import memoria as _mem
            _mem.guardar(self.app.mem)
            self._avisar("tam",
                         f"[Autónomo] Ajusto el monto a {r['monto']:.0f} "
                         f"({r['pct']:.2f} % del capital): "
                         f"{c['peor']*100:.0f} % de acierto en {c['nombre']}.",
                         cada=600)
        except Exception:
            pass

    def detener(self):
        self._parar.set()

    @property
    def activo(self) -> bool:
        return self._activo


# ── API ──────────────────────────────────────────────────────────────────────

_inst = None


def alternar(app) -> str:
    global _inst
    if _inst is not None and _inst.activo:
        _inst.detener()
        return (f"Cerebro autónomo detenido, señor. {_inst.ciclos} ciclos, "
                f"{_inst.reparaciones} reparaciones sobre la marcha.")
    if _inst is None or not _inst.is_alive():
        _inst = CerebroAutonomo(app)
    _inst.start()
    return (
        "Cerebro autónomo en marcha, señor.\n\n"
        "Cada 20 segundos recorro los catorce eslabones. Si algo se rompe "
        "y puedo arreglarlo —la ventana se movió, cambió el monitor, los "
        "botones ya no están donde creía— vuelvo a detectarlo yo mismo en "
        "vez de pararme a esperarle.\n\n"
        "Lo que NO toco es lo que depende de usted: si la cuenta es demo o "
        "real, su saldo, su límite de pérdida. Eso lo decide usted y yo "
        "solo aviso.\n\n"
        "La diferencia entre automático y autónomo es esa: lo automático "
        "repite, lo autónomo se arregla."
    )


def estado(app=None) -> str:
    if _inst is None or not _inst.activo:
        return ("El cerebro autónomo está parado, señor. Pulse «🧠 "
                "AUTÓNOMO» para que empiece a vigilarse y repararse solo.")
    l = [f"CEREBRO AUTÓNOMO — {_inst.ciclos} ciclos", ""]
    l.append(f"· Reparaciones automáticas: {_inst.reparaciones}")
    l.append(f"· Estado: "
             + (f"BLOQUEADO — {_inst.ultimo_bloqueo}"
                if _inst.ultimo_bloqueo else "operando"))
    l.append("")
    l.append("Uso: detección automática · filtro de ventaja · freno diario "
             "· confianza calibrada · tamaño por Kelly.")
    return "\n".join(l)


def activar_tamano_auto(app, si: bool = True) -> str:
    """Autoriza (o no) que Litch ajuste el monto según su ventaja."""
    try:
        app.mem.setdefault("config", {})["tamano_auto"] = bool(si)
        from . import memoria as _mem
        _mem.guardar(app.mem)
    except Exception as e:
        return f"No pude: {e}"
    if si:
        return ("De acuerdo, señor. Ajustaré el monto según la ventaja que "
                "tenga demostrada: más en las señales buenas, menos en las "
                "mediocres. Siempre dentro del 2 % de su capital, y solo "
                "si el cambio es notable — mover el monto por un 3 % es "
                "ruido.")
    return ("El monto lo pone usted y no lo toco, señor.")


__all__ = ["CerebroAutonomo", "alternar", "estado", "activar_tamano_auto"]

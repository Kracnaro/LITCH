"""
guardian_cierre.py — Que Litch nunca se vaya dejando dinero expuesto.

━━━ LO QUE PASÓ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El registro del señor termina así:

    [Litch] Senal acertada, senor. Patron confirmado y memorizado.
     --- Litch termino. Si hubo un error, aparece arriba. ---

Y arriba no había ningún error. Litch se cerró en silencio con una
operación abierta, y esa operación se perdió sin nadie vigilándola.

Un programa que gestiona dinero no puede desaparecer sin decir por qué.
Cuando se va sin dejar rastro pasan dos cosas malas a la vez: se pierde
la posición y se pierde la información de qué falló, así que no se puede
arreglar.

━━━ QUÉ HACE ESTE MÓDULO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tres cosas, en orden de importancia:

 1. LATIDO. Cada pocos segundos escribe en disco que sigue vivo, junto
    con qué está haciendo y si hay dinero expuesto. Si el proceso muere,
    ese archivo queda como la caja negra de un avión: al arrancar de
    nuevo se lee y se sabe exactamente en qué momento se cayó.

 2. AVISO ANTES DE IRSE. Cualquier cierre —el botón, Ctrl+C, un fallo
    no capturado— pasa por aquí. Si hay una operación abierta, se avisa
    en voz alta y se anota. No se puede impedir que Windows mate el
    proceso, pero sí que el señor se entere.

 3. RECUPERACIÓN. Al arrancar, si el latido anterior estaba «vivo», es
    que la vez pasada no se cerró bien. Litch lo dice y muestra qué
    había abierto en ese momento.

━━━ LO QUE NO PUEDE HACER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ser honesto también es decir los límites: si Windows mata el proceso de
golpe, o se va la luz, no hay código que ejecutar. Por eso la protección
de verdad no está aquí — está en no dejar operaciones sin stop. En
opciones binarias eso significa entender que, una vez abierta, la
operación vive sus 30 segundos pase lo que pase en el ordenador.
"""

from __future__ import annotations

import json
import os
import time
import threading
import traceback

INTERVALO_LATIDO = 5.0        # segundos entre latidos
MARGEN_MUERTO = 25.0          # sin latido más de esto = se cayó


def _ruta(nombre: str) -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "MEMORIA_AP")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, nombre)


RUTA_LATIDO = lambda: _ruta("latido.json")
RUTA_INCIDENTES = lambda: _ruta("incidentes_cierre.json")


# ── 1. Latido ────────────────────────────────────────────────────────────────

class Latido(threading.Thread):
    """Escribe en disco que Litch sigue vivo, y qué tiene entre manos."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LatidoLitch")
        self.app = app
        self._parar = threading.Event()

    def _estado(self) -> dict:
        a = self.app
        d = {
            "t": time.time(),
            "hora": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pid": os.getpid(),
            "vivo": True,
            "activo": bool(getattr(a, "activo", False)),
            "trading": bool(getattr(a, "trading_on", False)),
            "autoclick": bool(getattr(a, "autoclick_on", False)),
            "operacion_abierta": False,
            "detalle": "",
        }
        # ¿Hay dinero expuesto ahora mismo?
        try:
            tr = getattr(a, "trading", None)
            abierta = getattr(tr, "_op_en_curso", None) or \
                      getattr(tr, "_trade_abierto", None)
            if abierta:
                d["operacion_abierta"] = True
                d["detalle"] = str(abierta)[:200]
        except Exception:
            pass
        try:
            cfg = a.mem.get("config", {})
            d["monto"] = cfg.get("monto_broker") or cfg.get("monto_base")
            d["divisa"] = cfg.get("divisa", "")
            d["asset"] = cfg.get("asset", "")
        except Exception:
            pass
        return d

    def run(self):
        while not self._parar.is_set():
            try:
                with open(RUTA_LATIDO(), "w", encoding="utf-8") as f:
                    json.dump(self._estado(), f, ensure_ascii=False)
            except Exception:
                pass
            self._parar.wait(INTERVALO_LATIDO)

    def detener(self, limpio: bool = True):
        """Al parar bien, se marca `vivo: False` — eso distingue el cierre
        ordenado de la caída."""
        self._parar.set()
        try:
            d = self._estado()
            d["vivo"] = not limpio
            d["cierre_limpio"] = limpio
            with open(RUTA_LATIDO(), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
        except Exception:
            pass


# ── 2. Aviso antes de irse ───────────────────────────────────────────────────

def registrar_incidente(motivo: str, detalle: str = "",
                        estado: dict | None = None) -> None:
    """Deja constancia de por qué se cerró. Nunca borra lo anterior."""
    try:
        try:
            with open(RUTA_INCIDENTES(), encoding="utf-8") as f:
                hist = json.load(f)
        except Exception:
            hist = []
        hist.append({
            "hora": time.strftime("%Y-%m-%d %H:%M:%S"),
            "motivo": motivo,
            "detalle": (detalle or "")[:2000],
            "estado": estado or {},
        })
        with open(RUTA_INCIDENTES(), "w", encoding="utf-8") as f:
            json.dump(hist[-200:], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def al_cerrar(app, motivo: str = "cierre normal") -> str:
    """
    Se llama SIEMPRE antes de terminar, venga de donde venga el cierre.

    Si hay dinero expuesto, lo dice claro. No puede rescatar una binaria
    ya abierta —vive sus 30 segundos pase lo que pase— pero sí evitar que
    el señor se entere por el saldo.
    """
    est = {}
    try:
        est = Latido(app)._estado()
    except Exception:
        pass

    aviso = ""
    if est.get("operacion_abierta"):
        aviso = ("⚠ ATENCIÓN, SEÑOR: me cierro con una operación ABIERTA. "
                 "No puedo vigilarla desde aquí. Reviste el bróker.")
        try:
            app.decir(aviso)
        except Exception:
            pass
    registrar_incidente(motivo, aviso, est)
    return aviso or f"Cierre registrado: {motivo}."


def instalar(app) -> Latido | None:
    """
    Engancha el guardián a todas las vías de salida.

    Las tres que existen: el botón de cerrar, una excepción no capturada
    en cualquier hilo, y la salida normal del intérprete.
    """
    lat = None
    try:
        lat = Latido(app)
        lat.start()
        app._latido = lat
    except Exception:
        pass

    # Excepciones que nadie capturó — la causa más probable del cierre
    # silencioso del señor. Sin esto, el error se pierde con el proceso.
    try:
        import sys

        _antes = sys.excepthook

        def _hook(tipo, valor, tb):
            try:
                txt = "".join(traceback.format_exception(tipo, valor, tb))
                registrar_incidente("excepción no capturada", txt)
                app.log(f"[Guardián] FALLO NO CAPTURADO: {valor}")
                al_cerrar(app, f"excepción: {tipo.__name__}")
            except Exception:
                pass
            if _antes:
                _antes(tipo, valor, tb)

        sys.excepthook = _hook

        # Los hilos tienen su propio hook desde Python 3.8. Un hilo que
        # muere en silencio es exactamente lo que deja a Litch a medias
        # sin que nadie se entere.
        def _hook_hilo(args):
            try:
                txt = "".join(traceback.format_exception(
                    args.exc_type, args.exc_value, args.exc_traceback))
                registrar_incidente(
                    f"excepción en hilo {getattr(args.thread,'name','?')}", txt)
                app.log(f"[Guardián] Hilo caído "
                        f"({getattr(args.thread,'name','?')}): {args.exc_value}")
            except Exception:
                pass
        threading.excepthook = _hook_hilo
    except Exception:
        pass

    # Salida normal del intérprete
    try:
        import atexit
        atexit.register(lambda: al_cerrar(app, "salida del programa"))
    except Exception:
        pass

    return lat


# ── 3. Recuperación al arrancar ──────────────────────────────────────────────

def revisar_arranque(app) -> str:
    """
    ¿La vez pasada se cerró bien?

    Si el latido quedó en «vivo», el proceso murió sin pasar por el
    cierre ordenado. Eso es exactamente lo que le pasó al señor, y hasta
    ahora no quedaba constancia de ello.
    """
    try:
        with open(RUTA_LATIDO(), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return ""

    if not d.get("vivo"):
        return ""       # se cerró bien

    hace = time.time() - float(d.get("t", 0))
    msg = [f"⚠ Señor, la sesión anterior NO se cerró bien.",
           f"Último latido: {d.get('hora','?')} "
           f"(hace {hace/60:.0f} minutos)."]
    if d.get("operacion_abierta"):
        msg.append("Y peor: había una OPERACIÓN ABIERTA en ese momento. "
                   "Eso significa que me caí dejando dinero expuesto.")
        if d.get("monto"):
            msg.append(f"Monto en juego: {d.get('divisa','')} {d['monto']} "
                       f"en {d.get('asset','?')}.")
    else:
        msg.append("No había operación abierta — al menos eso.")

    # ¿Quedó registrada la causa?
    try:
        with open(RUTA_INCIDENTES(), encoding="utf-8") as f:
            inc = json.load(f)
        if inc:
            ult = inc[-1]
            msg.append(f"Última causa registrada: {ult.get('motivo','?')}.")
            if ult.get("detalle"):
                msg.append(f"  {ult['detalle'][:220]}")
    except Exception:
        msg.append("No quedó registro de la causa. A partir de ahora sí "
                   "quedará: cualquier fallo se anota antes de morir.")

    try:
        app.log("[Guardián] " + " ".join(msg))
    except Exception:
        pass
    return "\n".join(msg)


def historial(n: int = 10) -> str:
    """Los últimos cierres, para ver si hay un patrón."""
    try:
        with open(RUTA_INCIDENTES(), encoding="utf-8") as f:
            inc = json.load(f)
    except Exception:
        return "No hay incidentes registrados, señor."
    if not inc:
        return "No hay incidentes registrados, señor."
    l = [f"ÚLTIMOS {min(n,len(inc))} CIERRES", ""]
    for x in inc[-n:][::-1]:
        marca = "⚠" if "excepción" in str(x.get("motivo","")) else "·"
        l.append(f"{marca} {x.get('hora','?')} — {x.get('motivo','?')}")
        if x.get("estado", {}).get("operacion_abierta"):
            l.append("    CON OPERACIÓN ABIERTA")
        if x.get("detalle"):
            l.append(f"    {x['detalle'][:160]}")
    return "\n".join(l)


__all__ = ["Latido", "instalar", "al_cerrar", "revisar_arranque",
           "historial", "registrar_incidente"]

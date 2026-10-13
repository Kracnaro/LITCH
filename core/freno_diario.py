"""
freno_diario.py — El límite de pérdida que de verdad para.

━━━ LO QUE ESTABA MAL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Se podía fijar un límite de pérdida diaria. Se guardaba en la
configuración. Y **nadie lo miraba nunca**.

Le dije al señor: «si pierdo eso en un día, me paro y no vuelvo a operar
hasta mañana». No era verdad. El número se escribía en un archivo y ahí
se quedaba.

Es exactamente la clase de mentira silenciosa que hemos estado
persiguiendo toda la sesión, y esta vez la escribí yo. Un freno que no
frena es peor que no tener freno: da una sensación de seguridad que
hace apostar más.

━━━ POR QUÉ ESTE FRENO IMPORTA MÁS QUE LOS OTROS ━━━━━━━━━━━━━━━━━━━━━
Los demás guardias evitan errores puntuales: un dato retrasado, un clic
que no llega, un tamaño temerario. Este evita algo distinto: **la
espiral**.

Una racha mala no avisa. Se pierde una, se sube el tamaño para
recuperar, se pierden dos más. Cuando el señor se levanta de la silla
—o se va a trabajar y deja a Litch sola— no hay nadie que diga basta.

El freno diario es ese «basta» escrito antes, en frío, cuando todavía se
piensa con claridad.

━━━ CÓMO CUENTA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En dinero, no en número de operaciones. Perder 5 de 50 no es lo mismo
que perder 5 de 2.000. Se apunta lo ganado y lo perdido de cada
operación cerrada, y cuando el saldo del día cae por debajo del límite,
se para.

Se reinicia con el día natural. Y se guarda en disco: si Litch se cierra
y vuelve a abrirse, el freno sigue puesto — si no, bastaría reiniciar
para saltárselo, que es justo lo que uno hace cuando va perdiendo.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime


def _ruta() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "MEMORIA_AP")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "freno_diario.json")


def _hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _cargar() -> dict:
    try:
        with open(_ruta(), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("dia") == _hoy():
            return d
    except Exception:
        pass
    return {"dia": _hoy(), "pnl": 0.0, "ops": 0, "wins": 0, "losses": 0,
            "parado": False, "hora_parada": ""}


def _guardar(d: dict) -> None:
    try:
        tmp = _ruta() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _ruta())
    except Exception:
        pass


# ── Registrar lo que pasa ────────────────────────────────────────────────────

def anotar(app, gano: bool, monto: float = 0.0,
           pago_pct: float = 0.0) -> dict:
    """
    Apunta el resultado de una operación cerrada.

    Devuelve el estado del día. Se llama al conocer el resultado, no al
    abrir: una operación abierta todavía no ha costado nada.
    """
    cfg = app.mem.get("config", {}) if hasattr(app, "mem") else {}
    if not monto:
        monto = float(cfg.get("monto_broker") or cfg.get("monto_base") or 0)
    if not pago_pct:
        pago_pct = float(cfg.get("pago_pct") or 85)
    p = pago_pct / 100.0 if pago_pct > 3 else pago_pct

    d = _cargar()
    d["ops"] += 1
    if gano:
        d["wins"] += 1
        d["pnl"] += monto * p
    else:
        d["losses"] += 1
        d["pnl"] -= monto

    lim = cfg.get("perdida_max_dia")
    if lim and d["pnl"] <= -abs(float(lim)) and not d["parado"]:
        d["parado"] = True
        d["hora_parada"] = time.strftime("%H:%M:%S")
        try:
            from . import monto_real as _mr
            div = cfg.get("divisa", "")
            txt = _mr.formatear(abs(d["pnl"]), div)
            ltxt = _mr.formatear(abs(float(lim)), div)
        except Exception:
            txt, ltxt = f"{abs(d['pnl']):.0f}", f"{abs(float(lim)):.0f}"
        try:
            app.decir(f"Señor, me paro. Llevo {txt} de pérdida hoy y su "
                      f"límite era {ltxt}. No vuelvo a operar hasta mañana, "
                      f"aunque las señales parezcan buenas. Ese freno lo "
                      f"puso usted en frío; ahora mismo no me fío de "
                      f"cambiarlo en caliente.")
        except Exception:
            pass
    _guardar(d)
    return d


def estado_dia(app=None) -> dict:
    """Cómo va el día."""
    return _cargar()


def puede_operar(app) -> tuple[bool, str]:
    """
    ¿Se puede abrir una operación ahora?

    Es el portero. Se llama antes de decidir, no después.
    """
    cfg = app.mem.get("config", {}) if hasattr(app, "mem") else {}
    lim = cfg.get("perdida_max_dia")
    d = _cargar()

    if d.get("parado"):
        try:
            from . import monto_real as _mr
            div = cfg.get("divisa", "")
            txt = _mr.formatear(abs(d["pnl"]), div)
        except Exception:
            txt = f"{abs(d['pnl']):.0f}"
        return False, (f"freno diario activo desde las {d.get('hora_parada','?')}: "
                       f"{txt} de pérdida hoy en {d['ops']} operaciones")

    if not lim:
        return True, "sin límite diario puesto"

    try:
        restante = abs(float(lim)) + d["pnl"]      # pnl es negativo si pierde
    except Exception:
        return True, "límite no numérico"

    if restante <= 0:
        return False, "límite diario alcanzado"

    # Aviso cuando queda poco, sin bloquear todavía
    if restante < abs(float(lim)) * 0.25:
        return True, (f"cuidado: solo queda un {restante/abs(float(lim))*100:.0f} % "
                      f"del margen de hoy")
    return True, ""


def reiniciar(app) -> str:
    """
    Levanta el freno a mano. Con advertencia, porque es la decisión
    peligrosa.
    """
    d = _cargar()
    if not d.get("parado"):
        return "El freno no está puesto, señor. No hay nada que levantar."
    perdido = abs(d["pnl"])
    _guardar({"dia": _hoy(), "pnl": 0.0, "ops": 0, "wins": 0, "losses": 0,
              "parado": False, "hora_parada": ""})
    try:
        from . import monto_real as _mr
        txt = _mr.formatear(perdido, app.mem.get("config", {}).get("divisa", ""))
    except Exception:
        txt = f"{perdido:.0f}"
    return (f"Freno levantado, señor. Pero se lo digo igual: hoy llevaba "
            f"{txt} de pérdida y usted mismo puso ese límite en frío. "
            f"Quitarlo en caliente, después de perder, es la decisión que "
            f"convierte un mal día en un mes malo.\n\n"
            f"El contador vuelve a cero. Si quiere que le pare antes, "
            f"póngame un límite más bajo.")


def informe(app) -> str:
    """Cómo va el día, con el margen que queda."""
    cfg = app.mem.get("config", {})
    d = _cargar()
    lim = cfg.get("perdida_max_dia")
    try:
        from . import monto_real as _mr
        div = cfg.get("divisa", "")
        f = lambda v: _mr.formatear(v, div)
    except Exception:
        f = lambda v: f"{v:,.2f}"

    l = [f"EL DÍA DE HOY — {d['dia']}", ""]
    l.append(f"· Operaciones : {d['ops']}  ({d['wins']} aciertos, "
             f"{d['losses']} fallos)")
    if d["ops"]:
        l.append(f"· Acierto     : {d['wins']/d['ops']*100:.0f} %")
    signo = "+" if d["pnl"] >= 0 else ""
    l.append(f"· Resultado   : {signo}{f(d['pnl'])}")

    if lim:
        restante = abs(float(lim)) + d["pnl"]
        l.append(f"· Límite      : {f(abs(float(lim)))}")
        if d.get("parado"):
            l.append(f"· Estado      : PARADO desde las {d['hora_parada']}")
        else:
            pct = restante / abs(float(lim)) * 100
            l.append(f"· Margen      : queda {f(max(0, restante))} "
                     f"({pct:.0f} %)")
    else:
        l.append("· Límite      : ninguno")
        l.append("")
        l.append("Sin límite, una racha mala corre hasta que usted la vea. "
                 "Y si se va a trabajar, puede correr todo el día.")

    if d.get("parado"):
        l.append("")
        l.append("No vuelvo a operar hasta mañana. Si quiere levantarlo, "
                 "dígame «levanta el freno» — pero piénselo: ese límite lo "
                 "puso usted en frío.")
    return "\n".join(l)


__all__ = ["anotar", "puede_operar", "estado_dia", "reiniciar", "informe"]

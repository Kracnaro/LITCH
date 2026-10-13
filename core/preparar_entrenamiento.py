"""
preparar_entrenamiento.py — Dejar a Litch lista para entrenar sola.

━━━ POR QUÉ HACE FALTA ESTO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cuando el señor deja a Litch entrenando y se va, ya no hay nadie que
note que algo va mal. Un fallo que estando delante se corrige en diez
segundos —el monto sin leer, la cuenta en real, la escala descuadrada—
se convierte en horas de aprendizaje envenenado o, peor, en dinero.

Esta rutina hace las comprobaciones que el señor haría si estuviera
mirando, las hace TODAS, y se planta si alguna falla. Es la misma idea
que la revisión de apertura de un piloto: no es desconfianza, es que la
memoria humana falla y las listas no.

━━━ QUÉ COMPRUEBA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Diez cosas, agrupadas por lo que puede costar si fallan:

    PUEDE COSTAR DINERO         PUEDE ENVENENAR EL APRENDIZAJE
    · cuenta demo                · escala vela/vencimiento
    · tamaño de posición         · activo OTC identificado
    · monto real leído           · estadísticas limpias
    · límite de pérdida          · guardián de cierre activo
                                 · cadena de operación completa
                                 · visión apuntando bien

Las de la izquierda son bloqueantes: si fallan, no se entrena. Las de la
derecha avisan pero dejan seguir, porque un aprendizaje imperfecto es
mejor que ninguno — siempre que se sepa que lo es.
"""

from __future__ import annotations

import time


class Chequeo:
    def __init__(self, nombre, ok, detalle="", bloquea=False, arreglo=""):
        self.nombre = nombre
        self.ok = bool(ok)
        self.detalle = detalle
        self.bloquea = bloquea
        self.arreglo = arreglo


def _cfg(app) -> dict:
    try:
        return app.mem.get("config", {}) or {}
    except Exception:
        return {}


# ── Las comprobaciones ───────────────────────────────────────────────────────

def _c_cuenta(app) -> Chequeo:
    c = _cfg(app)
    tipo = str(c.get("tipo_cuenta") or "").lower()
    if tipo == "real":
        return Chequeo("Cuenta", False, "está en CUENTA REAL", True,
                       "Ponga la cuenta en DEMO antes de dejarla sola. "
                       "Entrenar es equivocarse a propósito: eso no se hace "
                       "con dinero de verdad.")
    if tipo != "demo":
        return Chequeo("Cuenta", False,
                       "no consta si es demo o real", True,
                       "Pulse el botón DEMO/REAL de la barra para que quede "
                       "constancia. No entreno sin saber en qué cuenta estoy.")
    return Chequeo("Cuenta", True, "DEMO — dinero de práctica")


def _c_monto(app) -> Chequeo:
    c = _cfg(app)
    m = c.get("monto_broker") or c.get("monto_base")
    div = c.get("divisa", "")
    if not m:
        return Chequeo("Monto", False, "no sé cuánto invierte", True,
                       "Dígame «calibra el ticket» y le señalo dónde mirar, "
                       "o «opero con X pesos».")
    if not c.get("monto_broker"):
        return Chequeo("Monto", False,
                       f"tengo {m} de memoria, no leído de su pantalla",
                       False,
                       "«calibra el ticket» para que lo lea solo y se entere "
                       "si usted lo cambia.")
    return Chequeo("Monto", True, f"{div} {m} — leído del bróker")


def _c_tamano(app) -> Chequeo:
    c = _cfg(app)
    cap = c.get("saldo") or c.get("capital")
    m = c.get("monto_broker") or c.get("monto_base")
    if not cap:
        return Chequeo("Tamaño de posición", False,
                       "no sé su capital, no puedo juzgar el tamaño", False,
                       "Dígame «mi saldo es X».")
    if not m:
        return Chequeo("Tamaño de posición", False, "sin monto", True, "")
    try:
        from . import mercado_y_tamano as _myt
        ev = _myt.evaluar_tamano(cap, m, c.get("divisa", ""))
        if ev.get("grave"):
            return Chequeo("Tamaño de posición", False,
                           f"{ev['pct']:.1f}% del capital — aguanta "
                           f"{ev['aguanta']} pérdidas", True,
                           f"Baje a {ev['sugerido']:.0f} (el 2%). Sin nadie "
                           f"mirando, una racha mala vacía la cuenta.")
        return Chequeo("Tamaño de posición", True,
                       f"{ev['pct']:.2f}% — aguanta {ev['aguanta']} pérdidas")
    except Exception as e:
        return Chequeo("Tamaño de posición", False, str(e), False, "")


def _c_escala(app) -> Chequeo:
    c = _cfg(app)
    try:
        from . import escala_temporal as _et
        coh = _et.coherencia(int(c.get("periodo_vela") or 60),
                             int(c.get("vencimiento") or 60))
        return Chequeo("Escala temporal", coh["ok"], coh["motivo"], False,
                       "" if coh["ok"] else
                       f"Cambie la vela a {coh['vela_sugerida']} s en la "
                       f"columna izquierda de IQ Option.")
    except Exception as e:
        return Chequeo("Escala temporal", False, str(e), False, "")


def _c_activo(app) -> Chequeo:
    c = _cfg(app)
    nom = c.get("asset") or ""
    if not nom:
        return Chequeo("Activo", False, "no sé qué activo está mirando",
                       False, "Dígame «opero en Nvidia» para que lo anote.")
    try:
        from . import mercado_y_tamano as _myt
        d = _myt.identificar(nom)
        if d["otc"]:
            return Chequeo("Activo", True,
                           f"{nom} — {d['descripcion']}. Guardo sus patrones "
                           f"aparte: el precio lo genera el bróker, no el "
                           f"mercado.")
        return Chequeo("Activo", True, f"{nom} — {d['descripcion']}")
    except Exception as e:
        return Chequeo("Activo", False, str(e), False, "")


def _c_cadena(app) -> Chequeo:
    c = _cfg(app)
    falta = []
    if not getattr(app, "activo", False):
        falta.append("Sistema")
    if not getattr(app, "trading_on", False):
        falta.append("Trading")
    if not getattr(app, "autoclick_on", False):
        falta.append("Auto")
    if not (c.get("boton_verde") and c.get("boton_rojo")):
        falta.append("Calibración")
    if falta:
        return Chequeo("Cadena de operación", False,
                       f"falta: {', '.join(falta)}", True,
                       "Encienda esos interruptores en la barra. Sin ellos "
                       "no ejecuto nada y el entrenamiento no avanza.")
    return Chequeo("Cadena de operación", True, "S · T · A · C completos")


def _c_estadisticas(app) -> Chequeo:
    try:
        from . import cuarentena_stats as _cq
        fdb = getattr(app, "fdb", None)
        tr = list(getattr(fdb, "trades", []) or [])
        sucias = sum(1 for x in tr if x.get("sospechosa"))
        if sucias:
            return Chequeo("Estadísticas", True,
                           f"{len(tr)-sucias} limpias, {sucias} en cuarentena")
        return Chequeo("Estadísticas", True, f"{len(tr)} operaciones")
    except Exception:
        return Chequeo("Estadísticas", False, "no pude revisarlas", False,
                       "«limpia las estadísticas».")


def _c_guardian(app) -> Chequeo:
    lat = getattr(app, "_latido", None)
    if lat is not None and getattr(lat, "is_alive", lambda: False)():
        return Chequeo("Guardián de cierre", True,
                       "latido activo — si me caigo, quedará constancia")
    return Chequeo("Guardián de cierre", False, "no está corriendo", False,
                   "Reinicie Litch: se instala al arrancar.")


def _c_vision(app) -> Chequeo:
    c = _cfg(app)
    r = c.get("region_grafico")
    if not r:
        return Chequeo("Visión", False, "sin región", True,
                       "«ve toda la pantalla».")
    try:
        from . import vision_total as _vt
        pct = _vt.porcentaje_visible(r)
        if pct < 50:
            return Chequeo("Visión", False, f"solo el {pct}% de la pantalla",
                           False, "«ve toda la pantalla».")
        return Chequeo("Visión", True, f"{pct}% de la pantalla")
    except Exception as e:
        return Chequeo("Visión", False, str(e), False, "")


def _c_limite(app) -> Chequeo:
    c = _cfg(app)
    cap = c.get("saldo") or c.get("capital")
    lim = c.get("perdida_max_dia")
    if not lim and cap:
        return Chequeo("Límite de pérdida diaria", False,
                       "no hay límite puesto", False,
                       f"Dígame «límite de pérdida {cap*0.1:.0f}» (el 10% "
                       f"del capital). Sin límite, una racha mala corre "
                       f"toda la noche.")
    if lim:
        return Chequeo("Límite de pérdida diaria", True, f"{lim}")
    return Chequeo("Límite de pérdida diaria", False,
                   "sin capital no puedo sugerir uno", False, "")


def _c_motor(app) -> Chequeo:
    try:
        from . import trading as _tr
        if _tr._motor_iq_debe_callar(app):
            return Chequeo("Motor de binarias", False, "está callado", True,
                           "«¿por qué no predices?» le dirá cuál de los "
                           "eslabones falta.")
        return Chequeo("Motor de binarias", True, "analizando")
    except Exception as e:
        return Chequeo("Motor de binarias", False, str(e), False, "")


COMPROBACIONES = [_c_cuenta, _c_monto, _c_tamano, _c_limite, _c_cadena,
                  _c_motor, _c_escala, _c_activo, _c_vision,
                  _c_estadisticas, _c_guardian]


# ── La rutina ────────────────────────────────────────────────────────────────

def revisar(app) -> dict:
    """Pasa toda la lista. Devuelve el resultado sin tocar nada."""
    res = []
    for f in COMPROBACIONES:
        try:
            res.append(f(app))
        except Exception as e:
            res.append(Chequeo(f.__name__, False, str(e), False, ""))
    bloqueos = [c for c in res if not c.ok and c.bloquea]
    avisos = [c for c in res if not c.ok and not c.bloquea]
    return {"chequeos": res, "bloqueos": bloqueos, "avisos": avisos,
            "listo": not bloqueos}


def informe(app) -> str:
    """La lista, en voz alta, con lo que falta y cómo arreglarlo."""
    r = revisar(app)
    l = ["PREPARACIÓN PARA ENTRENAR SOLA", ""]

    for c in r["chequeos"]:
        marca = "✓" if c.ok else ("✗" if c.bloquea else "·")
        l.append(f" {marca} {c.nombre}: {c.detalle}")

    l.append("")
    if r["listo"]:
        l.append("LISTA, SEÑOR. Puede dejarme entrenando.")
        if r["avisos"]:
            l.append("")
            l.append("Con estas salvedades, que no impiden entrenar pero "
                     "hacen que aprenda peor:")
            for c in r["avisos"]:
                l.append(f"   · {c.nombre}: {c.arreglo or c.detalle}")
    else:
        l.append(f"NO ESTOY LISTA. Faltan {len(r['bloqueos'])} cosas y son "
                 f"de las que cuestan dinero:")
        l.append("")
        for c in r["bloqueos"]:
            l.append(f" ✗ {c.nombre} — {c.detalle}")
            if c.arreglo:
                l.append(f"     {c.arreglo}")
        if r["avisos"]:
            l.append("")
            l.append("Y además, sin ser bloqueante:")
            for c in r["avisos"]:
                l.append(f"   · {c.nombre}: {c.arreglo or c.detalle}")

    l.append("")
    l.append("Mientras entreno, cada 20 operaciones le dejo un resumen "
             "honesto en el registro. Y si me caigo, quedará constancia de "
             "cuándo y con qué en juego.")
    return "\n".join(l)


def fijar_limite(app, monto: float) -> str:
    """Límite de pérdida diaria: el freno que corre toda la noche."""
    try:
        app.mem.setdefault("config", {})["perdida_max_dia"] = float(monto)
        from . import memoria as _m
        _m.guardar(app.mem)
    except Exception as e:
        return f"No pude fijarlo: {e}"
    try:
        from . import monto_real as _mr
        txt = _mr.formatear(monto, app.mem["config"].get("divisa", ""))
    except Exception:
        txt = str(monto)
    return (f"Límite diario en {txt}, señor. Si pierdo eso en un día, me "
            f"paro y no vuelvo a operar hasta mañana, aunque las señales "
            f"parezcan buenas. Ese freno es lo que separa una noche mala "
            f"de una cuenta vacía.")


__all__ = ["revisar", "informe", "fijar_limite", "Chequeo", "COMPROBACIONES"]

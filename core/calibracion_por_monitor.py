"""
calibracion_por_monitor.py — Que TODO se mude, no solo la ventana.

━━━ EL PROBLEMA QUE QUEDABA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El botón de cambiar monitor movía la barra y la visión. Pero Litch no
solo mira: **toca**. Y todo lo que toca vive en coordenadas absolutas de
pantalla:

    boton_verde   (1838, 462)     ← el SUBE de IQ Option
    boton_rojo    (1839, 605)     ← el BAJA
    region_grafico, botones del gráfico, campos del ticket…

Esas coordenadas se calibraron mirando el monitor 1. Al pasar al monitor
2 —que empieza en x=2400— siguen apuntando al monitor 1. Litch cree que
pulsa SUBE y pulsa lo que haya en esa parte de la otra pantalla.

Es exactamente el mismo fallo que ya nos costó 86 operaciones fantasma:
**el clic sale, pero no llega donde se cree.**

━━━ POR QUÉ NO BASTA CON SUMAR EL DESPLAZAMIENTO ━━━━━━━━━━━━━━━━━━━━━
La tentación es trasladar: si el monitor 2 empieza en x=2400, sumar 2400
a todo. Funcionaría **solo** si la ventana del bróker estuviera en la
misma posición relativa y el monitor tuviera el mismo tamaño.

En el caso del señor: monitor 1 es 1920×1080 y monitor 2 es 1800×1125.
Ni el ancho ni el alto coinciden. Trasladar dejaría el botón SUBE fuera
de la pantalla por la derecha.

━━━ LA SOLUCIÓN: UNA CALIBRACIÓN POR MONITOR ━━━━━━━━━━━━━━━━━━━━━━━━━
Cada monitor guarda la suya. Al cambiar:

  · Si ya hay calibración para ese monitor → se carga y todo funciona.
  · Si no la hay → Litch lo dice y NO opera hasta que se calibre. No
    inventa coordenadas ni traslada a ciegas.

Y se ofrece el traslado como atajo, con su advertencia: sirve para
empezar, pero hay que comprobarlo.
"""

from __future__ import annotations

# Todo lo que depende de dónde esté la ventana del bróker
#
# OJO: `region_grafico` NO está aquí, y es a propósito. Esa es la región
# que Litch MIRA, y debe seguir siempre al monitor actual. Si se guardara
# por monitor, una calibración vieja secuestraría la visión: el señor
# cambiaría de pantalla y Litch seguiría mirando la anterior.
#
# Aquí solo va lo que Litch TOCA. Dónde mira y dónde pulsa son dos cosas
# distintas y mezclarlas ya nos costó un fallo.
CLAVES = (
    "boton_verde", "boton_rojo",
    "boton_chart_minus", "boton_chart_center", "boton_chart_plus",
    "region_pl", "region_saldo", "region_monto", "region_rollover",
    "zonas_ticket_iq", "campos_ticket_tws", "boton_confirmar_iq",
)


def _cfg(app) -> dict:
    return app.mem.setdefault("config", {})


def _almacen(app) -> dict:
    """Donde viven las calibraciones de cada monitor."""
    return _cfg(app).setdefault("calib_monitores", {})


def guardar_actual(app, n: int) -> int:
    """
    Fotografía la calibración de ahora y la asocia a ese monitor.

    Devuelve cuántas claves guardó. Se llama ANTES de cambiar, para no
    perder lo que ya estaba bien.
    """
    cfg = _cfg(app)
    datos = {k: cfg[k] for k in CLAVES if cfg.get(k) is not None}
    if not datos:
        return 0
    _almacen(app)[str(int(n))] = datos
    try:
        from . import memoria as _mem
        _mem.guardar(app.mem)
    except Exception:
        pass
    return len(datos)


def cargar(app, n: int) -> tuple[bool, int]:
    """
    Aplica la calibración guardada de ese monitor.

    Devuelve (había calibración, cuántas claves se aplicaron).
    """
    guardadas = _almacen(app).get(str(int(n)))
    if not guardadas:
        return False, 0
    cfg = _cfg(app)
    n_ok = 0
    for k, v in guardadas.items():
        cfg[k] = v
        n_ok += 1
    try:
        from . import memoria as _mem
        _mem.guardar(app.mem)
    except Exception:
        pass
    return True, n_ok


def tiene(app, n: int) -> bool:
    """¿Está calibrado ese monitor? Lo mínimo: los dos botones."""
    d = _almacen(app).get(str(int(n))) or {}
    return bool(d.get("boton_verde") and d.get("boton_rojo"))


def trasladar(app, desde: dict, hacia: dict) -> tuple[int, str]:
    """
    Atajo: mover las coordenadas de un monitor a otro proporcionalmente.

    Es una ESTIMACIÓN, no una calibración. Si los monitores tienen
    tamaños distintos, se escala; si la ventana del bróker no está en la
    misma posición relativa, quedará mal. Sirve para no empezar de cero,
    no para operar sin comprobar.
    """
    cfg = _cfg(app)
    ex = hacia["w"] / max(1, desde["w"])
    ey = hacia["h"] / max(1, desde["h"])

    def _px(x, y):
        rx = (x - desde["x"]) / max(1, desde["w"])
        ry = (y - desde["y"]) / max(1, desde["h"])
        return (int(hacia["x"] + rx * hacia["w"]),
                int(hacia["y"] + ry * hacia["h"]))

    n = 0
    for k in CLAVES:
        v = cfg.get(k)
        if not v:
            continue
        try:
            if isinstance(v, (list, tuple)) and len(v) == 2 and \
                    all(isinstance(z, (int, float)) for z in v):
                cfg[k] = list(_px(v[0], v[1])); n += 1
            elif isinstance(v, (list, tuple)) and len(v) == 4 and \
                    all(isinstance(z, (int, float)) for z in v):
                a = _px(v[0], v[1]); b = _px(v[2], v[3])
                cfg[k] = [a[0], a[1], b[0], b[1]]; n += 1
        except Exception:
            continue

    try:
        from . import memoria as _mem
        _mem.guardar(app.mem)
    except Exception:
        pass

    aviso = ""
    if abs(ex - 1) > 0.02 or abs(ey - 1) > 0.02:
        aviso = (f" Los monitores tienen tamaños distintos "
                 f"({desde['w']}×{desde['h']} → {hacia['w']}×{hacia['h']}), "
                 f"así que he escalado. Compruébelo antes de operar.")
    return n, (f"Trasladé {n} coordenadas del monitor {desde.get('n','?')} "
               f"al {hacia.get('n','?')}.{aviso} Es una estimación, no una "
               f"calibración: si algo no cae donde debe, recalibre.")


def al_cambiar(app, desde_n: int, hacia: dict) -> str:
    """
    Se llama al cambiar de monitor. Hace lo correcto en cada caso.

    1. Guarda la calibración del monitor que se deja.
    2. Si el destino ya está calibrado, la carga.
    3. Si no, lo dice claro y deja a Litch sin operar ahí.
    """
    n_guard = guardar_actual(app, desde_n)
    hubo, n_carg = cargar(app, hacia["n"])

    if hubo:
        return (f"Monitor {hacia['n']}: cargué su calibración "
                f"({n_carg} elementos). Todo lo que toco —SUBE, BAJA, el "
                f"gráfico, el ticket— apunta a esta pantalla.")

    return (f"Monitor {hacia['n']}: no tengo calibración para esta "
            f"pantalla, señor.\n\n"
            f"Mis coordenadas de SUBE y BAJA son del monitor {desde_n} y "
            f"aquí no valen: pulsaría en el sitio equivocado. Guardé las "
            f"del {desde_n} ({n_guard} elementos), así que al volver allí "
            f"todo seguirá bien.\n\n"
            f"Dígame «Litch calibra» con el bróker delante en esta "
            f"pantalla, o «traslada la calibración» si la ventana está en "
            f"la misma posición relativa — eso último es una estimación y "
            f"habría que comprobarla.")


def estado(app) -> str:
    """Qué monitores están calibrados y cuáles no."""
    try:
        from . import monitores as _mon
        ms = _mon.listar()
        act = _mon.monitor_de_barra(app)
    except Exception:
        return "No pude leer los monitores."

    l = ["CALIBRACIÓN POR MONITOR", ""]
    for m in ms:
        marca = "►" if m["n"] == act["n"] else " "
        cal = tiene(app, m["n"])
        l.append(f" {marca} Monitor {m['n']} ({m['w']}×{m['h']}): "
                 + ("✓ calibrado" if cal else "✗ SIN calibrar — "
                    "no puedo operar aquí"))
    l.append("")
    l.append("Cada pantalla guarda sus propias coordenadas de SUBE, BAJA, "
             "el gráfico y el ticket. Al cambiar de monitor cargo las que "
             "tocan.")
    l.append("")
    l.append("Sumar el desplazamiento no sirve cuando los monitores tienen "
             "tamaños distintos: el botón acabaría fuera de la pantalla. "
             "Por eso cada uno lleva la suya.")
    return "\n".join(l)


__all__ = ["CLAVES", "guardar_actual", "cargar", "tiene", "trasladar",
           "al_cambiar", "estado"]

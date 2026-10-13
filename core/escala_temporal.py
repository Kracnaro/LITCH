"""
escala_temporal.py — Que la vela, el vencimiento y el zoom cuadren.

━━━ LO QUE EL SEÑOR VIO Y LITCH NO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En IQ Option hay tres cosas que parecen independientes y no lo son:

  1. EL TAMAÑO DE LA VELA   (10s · 30s · 1m · 2m · 5m, a la izquierda)
  2. EL VENCIMIENTO          (30 seg, en el panel derecho)
  3. EL ZOOM DEL GRÁFICO     (los botones [−] [⊹] [+])

Si el señor opera vencimientos de 30 segundos mirando velas de 5
minutos, está pidiendo a Litch que adivine lo que pasará en medio
segundo de vela. Es como preguntar por el minuto siguiente mirando un
calendario mensual: la información está, pero a una escala donde ese
minuto no se ve.

Y al revés: velas de 10 segundos para un vencimiento de 5 minutos son
30 velas de ruido puro para responder a una pregunta que se decide más
arriba.

━━━ LA REGLA QUE FALTABA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    La vela debe medir entre un tercio y una vez el vencimiento.

Con vencimiento de 30 s, la vela útil está entre 10 s y 30 s. Así cada
operación abarca de una a tres velas: suficiente para que el patrón
signifique algo, sin que el resultado dependa de un solo tick.

━━━ Y EL ZOOM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Los tres botoncitos del centro no son decoración:

    [−]  aleja — se ven más velas, se ve la tendencia
    [⊹]  centra — devuelve el precio al medio cuando se ha ido
    [+]  acerca — menos velas, más detalle

Litch necesita entre 40 y 60 velas visibles. Con menos no hay contexto
para medias ni bandas; con más, las velas recientes se aplastan y el
patrón inmediato se pierde. Y el botón del centro hay que pulsarlo
cuando el precio se sale del encuadre — que en Blitz pasa cada pocos
minutos.
"""

from __future__ import annotations

import time

# Velas que IQ Option ofrece, en segundos
VELAS = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]

# Cuántas velas conviene tener a la vista
VELAS_MIN = 40
VELAS_MAX = 60
VELAS_IDEAL = 50

# Relación sana entre vela y vencimiento
RATIO_MIN = 1 / 3.0     # la vela, al menos un tercio del vencimiento
RATIO_MAX = 1.0         # y como mucho, igual que el vencimiento


def vela_ideal(vencimiento_s: int) -> int:
    """
    Qué tamaño de vela conviene para ese vencimiento.

    Se busca la vela real de IQ Option más cercana a la mitad del
    vencimiento, dentro del rango sano.
    """
    try:
        v = int(vencimiento_s)
    except Exception:
        return 60
    if v <= 0:
        return 60
    objetivo = v * 0.5
    validas = [c for c in VELAS if v * RATIO_MIN <= c <= v * RATIO_MAX]
    if not validas:
        # Vencimiento tan corto que ninguna vela encaja: la más pequeña
        return min(VELAS, key=lambda c: abs(c - objetivo))
    return min(validas, key=lambda c: abs(c - objetivo))


def coherencia(vela_s: int, vencimiento_s: int) -> dict:
    """
    ¿La vela y el vencimiento hablan el mismo idioma?

    Devuelve el diagnóstico y qué hacer si no.
    """
    r = {"ok": False, "ratio": 0.0, "vela": vela_s,
         "vencimiento": vencimiento_s, "vela_sugerida": 0, "motivo": ""}
    try:
        vela = int(vela_s); venc = int(vencimiento_s)
    except Exception:
        r["motivo"] = "no tengo los dos valores"
        return r
    if vela <= 0 or venc <= 0:
        r["motivo"] = "falta la vela o el vencimiento"
        return r

    ratio = vela / venc
    r["ratio"] = round(ratio, 3)
    r["vela_sugerida"] = vela_ideal(venc)
    velas_por_op = venc / vela

    if ratio > RATIO_MAX:
        r["motivo"] = (
            f"la vela ({vela} s) dura más que la operación ({venc} s). "
            f"Cada operación es {velas_por_op:.2f} de vela: le estoy "
            f"pidiendo al gráfico que me diga lo que pasa dentro de una "
            f"sola vela, y eso no se ve. Debería bajar a {r['vela_sugerida']} s")
    elif ratio < RATIO_MIN:
        r["motivo"] = (
            f"la vela ({vela} s) es muy pequeña para {venc} s de "
            f"vencimiento: cada operación abarca {velas_por_op:.0f} velas, "
            f"casi todas ruido. Debería subir a {r['vela_sugerida']} s")
    else:
        r["ok"] = True
        r["motivo"] = (f"cuadran: cada operación abarca "
                       f"{velas_por_op:.1f} velas, que es lo sano")
    return r


# ── Los tres botones ─────────────────────────────────────────────────────────

def clics_de_zoom(velas_visibles: int) -> tuple[int, str]:
    """
    Cuántas veces pulsar [−] o [+], y en qué sentido.

    Devuelve (n, "alejar"|"acercar"|"ninguno"). Cada clic cambia el
    número de velas visibles en torno a un 25 %.
    """
    try:
        v = int(velas_visibles)
    except Exception:
        return 0, "ninguno"
    if v <= 0:
        return 0, "ninguno"
    if VELAS_MIN <= v <= VELAS_MAX:
        return 0, "ninguno"

    n = 0
    if v < VELAS_MIN:
        while v < VELAS_IDEAL and n < 6:
            v = int(v * 1.25); n += 1
        return n, "alejar"
    while v > VELAS_IDEAL and n < 6:
        v = int(v / 1.25); n += 1
    return n, "acercar"


def necesita_centrar(precio_y: float, alto: float,
                     margen: float = 0.22) -> bool:
    """
    ¿Se ha ido el precio del encuadre?

    Si la línea de precio está en el 22 % de arriba o de abajo del
    gráfico, ya no se ve bien hacia dónde puede moverse. Ahí toca [⊹].
    """
    try:
        y = float(precio_y); h = float(alto)
        if h <= 0:
            return False
        rel = y / h
        return rel < margen or rel > (1.0 - margen)
    except Exception:
        return False


def ajustar(app, ejecutar: bool = True) -> str:
    """
    Deja el gráfico listo para analizar: escala coherente y bien encuadrado.

    Primero centra (para partir de un encuadre limpio), luego ajusta el
    zoom hasta ver el número de velas que hace falta. Cada acción se
    comprueba: si pulsar no cambia nada, se dice en vez de darlo por hecho.
    """
    from . import chart_controls as _cc

    cfg = app.mem.get("config", {})
    vela = int(cfg.get("periodo_vela") or 60)
    venc = int(cfg.get("vencimiento") or vela)
    region = cfg.get("region_grafico")

    lineas = [f"AJUSTE DEL GRÁFICO — vela {vela} s · vencimiento {venc} s", ""]

    # 1. ¿Cuadran vela y vencimiento?
    c = coherencia(vela, venc)
    lineas.append(("✓ " if c["ok"] else "⚠ ") + c["motivo"] + ".")
    if not c["ok"]:
        lineas.append(f"   Cambie la vela a {c['vela_sugerida']} s en la "
                      f"columna izquierda de IQ Option. Eso lo hace usted: "
                      f"no toco su configuración sin permiso.")

    if not ejecutar:
        return "\n".join(lineas)

    # 2. Centrar
    try:
        ok_c = _cc.centrar(region, cfg)
        lineas.append("✓ Centrado el gráfico." if ok_c
                      else "· No pude centrar (botón no alcanzable).")
        time.sleep(0.35)
    except Exception as e:
        lineas.append(f"· Fallo al centrar: {e}")

    # 3. Zoom según el periodo
    try:
        ok_z = _cc.zoom_optimo(region, cfg, periodo_seg=vela)
        lineas.append(f"✓ Zoom ajustado para velas de {vela} s "
                      f"(busco entre {VELAS_MIN} y {VELAS_MAX} velas a la "
                      f"vista)." if ok_z
                      else "· No pude ajustar el zoom.")
    except Exception as e:
        lineas.append(f"· Fallo en el zoom: {e}")

    lineas.append("")
    lineas.append("Con menos de 40 velas no tengo contexto para las medias "
                  "ni las bandas. Con más de 60, las velas recientes se "
                  "aplastan y pierdo el patrón inmediato.")
    return "\n".join(lineas)


def explicar(app=None) -> str:
    """Lo que Litch ha entendido de la escala temporal."""
    cfg = (app.mem.get("config", {}) if app else {})
    vela = int(cfg.get("periodo_vela") or 60)
    venc = int(cfg.get("vencimiento") or vela)
    c = coherencia(vela, venc)

    return (
        "LA ESCALA TEMPORAL — lo que he entendido\n"
        "\n"
        "En IQ Option hay tres cosas que parecen sueltas y no lo son: el "
        "tamaño de la vela, el vencimiento y el zoom.\n"
        "\n"
        "LA REGLA: la vela debe medir entre un tercio y una vez el "
        "vencimiento. Así cada operación abarca de una a tres velas — "
        "suficiente para que el patrón signifique algo, sin que el "
        "resultado dependa de un solo tick.\n"
        "\n"
        f"AHORA MISMO: vela {vela} s, vencimiento {venc} s. "
        f"{'Cuadran' if c['ok'] else 'NO cuadran'} — {c['motivo']}.\n"
        "\n"
        "Si opero vencimientos de 30 segundos mirando velas de 5 minutos, "
        "le estoy pidiendo al gráfico que me diga lo que pasa en medio "
        "segundo de vela. Es como preguntar por el minuto siguiente "
        "mirando un calendario mensual: la información está, pero a una "
        "escala donde ese minuto no se ve.\n"
        "\n"
        "LOS TRES BOTONES del centro no son decoración:\n"
        "  [−] alejar  — más velas, se ve la tendencia\n"
        "  [⊹] centrar — devuelve el precio al medio cuando se ha ido\n"
        "  [+] acercar — menos velas, más detalle\n"
        "\n"
        f"Necesito entre {VELAS_MIN} y {VELAS_MAX} velas a la vista. Y el "
        "botón del centro hay que pulsarlo cuando el precio se sale del "
        "encuadre, que en Blitz pasa cada pocos minutos.\n"
        "\n"
        "Dígame «ajusta el gráfico» y lo dejo listo."
    )


__all__ = ["VELAS", "VELAS_MIN", "VELAS_MAX", "vela_ideal", "coherencia",
           "clics_de_zoom", "necesita_centrar", "ajustar", "explicar"]

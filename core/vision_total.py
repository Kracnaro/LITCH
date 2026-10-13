"""
vision_total.py — Que Litch vea TODA la pantalla, no un recorte.

━━━ EL PROBLEMA QUE RESUELVE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
La visión de Litch estaba atada a `region_grafico`, una región calibrada
para IQ Option: un rectángulo pequeño donde vivían las velas binarias.
En Interactive Brokers eso no sirve. TWS no es un gráfico: es un tablero
entero. La Entrada de Órdenes está arriba a la izquierda, el escáner de
mercado a la derecha, las posiciones abajo, la cuenta en el título. Mirar
solo el gráfico es como leer un periódico por el agujero de una moneda.

Con la región vieja ([454,120]→[1439,949]) Litch veía el 39 % de la
pantalla. No veía el ticket que iba a rellenar, ni el aviso de datos
retrasados, ni un diálogo que se abriera en una esquina.

━━━ CÓMO SE RESUELVE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
La región pasa a ser la pantalla entera, con una sola resta: la franja
que ocupa la propia barra de Litch. No por capricho — si Litch se mira a
sí misma, se lee sus propios letreros y los confunde con el mercado. Por
eso el botón de plegar la barra importa: plegada mide 28 px en vez de
104, y Litch recupera 76 px de mercado real.

Con la barra plegada en una pantalla de 1920×1080, Litch ve el 97,4 %.
Es todo lo que se puede ver sin que se vea a sí misma.
"""

from __future__ import annotations

# La región de IQ Option se guarda aparte antes de pisarla, para poder
# volver a las binarias sin tener que recalibrar desde cero.
CLAVE_RESPALDO = "region_grafico_iq"


def tamano_pantalla() -> tuple[int, int]:
    """Resolución física del monitor principal."""
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        u = ctypes.windll.user32
        w, h = int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1))
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return 1920, 1080


def alto_barra(app) -> int:
    """Cuánto ocupa la barra de Litch ahora mismo. Medido, no supuesto."""
    try:
        v = getattr(app.interfaz, "_barra_win", None)
        if v is not None and v.winfo_exists():
            v.update_idletasks()
            h = int(v.winfo_height())
            if 10 <= h <= 400:
                return h
            h = int(v.winfo_geometry().split("+")[0].split("x")[1])
            if 10 <= h <= 400:
                return h
    except Exception:
        pass
    try:
        if app.mem["config"].get("ribbon_plegado"):
            return 28
    except Exception:
        pass
    return 104


def region_completa(app=None) -> list[int]:
    """
    La pantalla entera. De borde a borde. Sin restar nada.

    Antes esta función restaba la franja de la barra de Litch, para que
    Litch no se leyera a sí misma. Era una decisión mía y estaba mal
    tomarla sin preguntar: el señor quiere que vea la pantalla completa,
    y la pantalla completa es de (0,0) a (ancho,alto).

    El problema de verse a sí misma sigue existiendo, pero se resuelve
    donde toca: al analizar, saltándose la franja propia (ver
    `franja_propia`), no recortando lo que Litch alcanza a ver. Una cosa
    es el campo de visión y otra dónde presta atención.
    """
    # Con varios monitores, «la pantalla» ya no empieza en (0,0). El
    # monitor 2 puede empezar en x=1920, o en x=-1920 si está a la
    # izquierda. Se pregunta cuál toca en vez de suponer el principal.
    if app is not None:
        try:
            from . import monitores as _mon
            m = _mon.elegido(app)
            return [m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"]]
        except Exception:
            pass
    sw, sh = tamano_pantalla()
    return [0, 0, sw, sh]


def franja_propia(app) -> list[int] | None:
    """
    Dónde está la barra de Litch dentro de la pantalla.

    No recorta la visión: solo señala qué trozo de lo que Litch ve es
    ella misma, para que al analizar no confunda sus propios letreros
    con datos del mercado.

    Devuelve [x1, y1, x2, y2] o None si no se puede determinar.
    """
    try:
        sw, sh = tamano_pantalla()
        b = alto_barra(app)
        dock = app.mem["config"].get("barra_dock", "arriba")
        if dock == "abajo":
            y2 = max(0, sh - 48)
            return [0, max(0, y2 - b), sw, y2]
        return [0, 0, sw, b]
    except Exception:
        return None


def porcentaje_visible(region, sw: int = 0, sh: int = 0) -> float:
    """Qué fracción de la pantalla abarca esa región, en porcentaje."""
    if not region:
        return 0.0
    if not sw or not sh:
        sw, sh = tamano_pantalla()
    x1, y1, x2, y2 = region[:4]
    area = max(0, x2 - x1) * max(0, y2 - y1)
    total = max(1, sw * sh)
    return round(area / total * 100.0, 1)


def activar(app, avisar: bool = True) -> str:
    """
    Pone la visión de Litch en pantalla completa.

    Guarda antes la región de IQ Option, para poder volver.
    """
    from . import memoria as _mem

    cfg = app.mem.setdefault("config", {})
    anterior = cfg.get("region_grafico")

    # Solo se respalda la región de IQ la primera vez. Si se activa dos
    # veces seguidas, no se debe respaldar la región de pantalla completa
    # encima del respaldo bueno.
    if anterior and not cfg.get(CLAVE_RESPALDO):
        sw, sh = tamano_pantalla()
        if porcentaje_visible(anterior, sw, sh) < 85.0:
            cfg[CLAVE_RESPALDO] = list(anterior)

    nueva = region_completa(app)
    cfg["region_grafico"] = nueva
    cfg["vision_total"] = True
    try:
        _mem.guardar(app.mem)
    except Exception:
        pass

    sw, sh = tamano_pantalla()
    pct = porcentaje_visible(nueva, sw, sh)
    fp = franja_propia(app)

    msg = (f"Visión en pantalla completa, señor: {nueva[2]-nueva[0]}×"
           f"{nueva[3]-nueva[1]} píxeles, de esquina a esquina. "
           f"El {pct} % de la pantalla — todo.")
    if fp:
        msg += (f" Sé que los píxeles {fp[1]} a {fp[3]} de arriba son mi "
                f"propia barra: los veo, pero no los confundo con mercado.")

    try:
        _sincronizar_overlay(app, nueva)
    except Exception:
        pass
    if avisar:
        try:
            app.log("[Visión] " + msg)
        except Exception:
            pass
    return msg


def restaurar_iq(app) -> str:
    """Devuelve la visión a la región calibrada de IQ Option."""
    from . import memoria as _mem

    cfg = app.mem.setdefault("config", {})
    guardada = cfg.get(CLAVE_RESPALDO)
    if not guardada:
        return ("No tengo guardada una región de IQ Option, señor. "
                "Calíbrela con «Litch calibra» y la recuerdo.")
    cfg["region_grafico"] = list(guardada)
    cfg["vision_total"] = False
    try:
        _mem.guardar(app.mem)
        _sincronizar_overlay(app, cfg["region_grafico"])
    except Exception:
        pass
    return f"Visión devuelta a la región de IQ Option: {guardada}."


def refrescar(app) -> None:
    """
    Reajusta la región si ya está en pantalla completa.

    Se llama al plegar o desplegar la barra: al cambiar la altura de la
    barra cambia cuánta pantalla queda libre, y la visión debe seguirla.
    """
    try:
        if not app.mem["config"].get("vision_total"):
            return
        nueva = region_completa(app)
        if nueva != app.mem["config"].get("region_grafico"):
            app.mem["config"]["region_grafico"] = nueva
            from . import memoria as _mem
            _mem.guardar(app.mem)
            _sincronizar_overlay(app, nueva)
    except Exception:
        pass


def _sincronizar_overlay(app, region) -> None:
    """Que el marco verde se mueva a la vez que la visión."""
    ovl = getattr(app, "overlay", None)
    if ovl is not None:
        ovl.set_region(region)


def estado(app) -> str:
    """Qué está viendo Litch, dicho en una frase."""
    cfg = app.mem.get("config", {})
    r = cfg.get("region_grafico")
    if not r:
        return "No tengo región de visión calibrada, señor."
    sw, sh = tamano_pantalla()
    pct = porcentaje_visible(r, sw, sh)
    ancho, alto = r[2] - r[0], r[3] - r[1]
    modo = ("pantalla completa" if cfg.get("vision_total")
            else "región calibrada")
    linea = (f"Estoy viendo {ancho}×{alto} píxeles desde ({r[0]},{r[1]}) "
             f"hasta ({r[2]},{r[3]}) — el {pct} % de la pantalla ({modo}).")
    if pct < 60:
        linea += (" Es poco para Interactive Brokers: no alcanzo a ver el "
                  "ticket de órdenes ni los avisos. Dígame «ve toda la "
                  "pantalla» y lo amplío.")
    return linea



def proteger(app, clave: str, valor):
    """
    Portero de la región de visión.

    La autocalibración de IQ Option escribe `region_grafico` cada vez que
    cree haber encontrado el gráfico. Con la visión en pantalla completa
    eso la encoge sin avisar: el señor la pone en 1920×1080 y minutos
    después vuelve a ser un recorte, sin que nadie haya tocado nada.

    Devuelve True si el cambio se permite, False si hay que ignorarlo.
    """
    if clave != "region_grafico":
        return True
    try:
        if not app.mem["config"].get("vision_total"):
            return True
    except Exception:
        return True
    # Está en pantalla completa: solo se acepta algo que también lo sea.
    try:
        if porcentaje_visible(valor) >= 95.0:
            return True
    except Exception:
        pass
    return False


__all__ = ["tamano_pantalla", "alto_barra", "region_completa",
           "porcentaje_visible", "activar", "restaurar_iq", "refrescar",
           "estado", "proteger", "CLAVE_RESPALDO"]

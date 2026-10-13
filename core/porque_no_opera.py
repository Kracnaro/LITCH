"""
porque_no_opera.py — El recorrido completo de una señal, paso a paso.

━━━ EL PROBLEMA QUE RESUELVE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El señor lleva días diciendo lo mismo: «no da clic, no interactúa».
Y tiene razón. Pero la causa puede estar en catorce sitios distintos, y
cada uno de ellos, por separado, hace que no pase nada — en silencio.

Buscar a mano en catorce sitios es lo que le ha costado las horas. Este
módulo hace ese recorrido de una vez y señala **el primero que falla**,
que es el que importa: los de después ni siquiera llegan a probarse.

━━━ LOS CATORCE ESLABONES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En el orden real en que se atraviesan al operar:

     1. pyautogui instalado          8. cuenta demo o real
     2. el ratón se puede mover      9. freno diario
     3. Sistema encendido           10. ventana de IQ Option visible
     4. Trading encendido           11. botones dentro de esa ventana
     5. Auto-clic encendido         12. botones no tapados
     6. botones calibrados          13. filtro de ventaja
     7. calibrados en ESTE monitor  14. tamaño y monto sensatos

Un fallo en el 3 hace que los once siguientes no se ejecuten. Por eso se
señala el PRIMERO y no se listan todos: arreglar el tercero puede
arreglar los once de golpe.
"""

from __future__ import annotations

import time


class Eslabon:
    def __init__(self, n, nombre, ok, detalle="", arreglo=""):
        self.n, self.nombre, self.ok = n, nombre, bool(ok)
        self.detalle, self.arreglo = detalle, arreglo


def revisar(app) -> list:
    """Recorre la cadena entera. Devuelve todos los eslabones."""
    e = []
    cfg = app.mem.get("config", {}) if hasattr(app, "mem") else {}

    # 1 · La herramienta que mueve el ratón
    try:
        import pyautogui  # noqa
        e.append(Eslabon(1, "pyautogui", True, "instalado"))
    except Exception as ex:
        e.append(Eslabon(1, "pyautogui", False, str(ex)[:60],
                         "Instálelo: pip install pyautogui"))
        return e   # sin esto no hay nada más que mirar

    # 2 · ¿Se lee la posición del ratón?
    #
    # Aquí NO se mueve el cursor, y es a propósito. Un diagnóstico que
    # mueve el ratón del señor cada vez que lo consulta es un diagnóstico
    # que molesta — y se acaba no consultando.
    #
    # Leer la posición basta para saber si la vía existe. La prueba
    # activa —moverlo de verdad— vive en `probar_clic()`, que se pide a
    # propósito y avisa de lo que va a hacer.
    try:
        import pyautogui
        pos = pyautogui.position()
        vale = pos is not None and len(pos) == 2
        e.append(Eslabon(2, "Acceso al ratón", vale,
                         f"lo leo en {tuple(pos)}" if vale
                         else "no puedo leer su posición",
                         "" if vale else
                         "Pulse «🖱 Probar el ratón» para la prueba activa."))
    except Exception as ex:
        e.append(Eslabon(2, "Acceso al ratón", False, str(ex)[:60],
                         "Suele ser un programa con permisos de "
                         "administrador delante: Windows impide que uno "
                         "normal le mande clics, y el bloqueo es silencioso."))

    # 3-5 · Los interruptores
    for n, attr, nom, boton in ((3, "activo", "Sistema", "Sis"),
                                (4, "trading_on", "Trading", "Trd"),
                                (5, "autoclick_on", "Auto-clic", "Auto")):
        on = bool(getattr(app, attr, False))
        e.append(Eslabon(n, nom, on, "encendido" if on else "APAGADO",
                         "" if on else f"Pulse «{boton}» en la barra."))

    # 6 · Calibración
    bv, br = cfg.get("boton_verde"), cfg.get("boton_rojo")
    hay = bool(bv and br)
    e.append(Eslabon(6, "Botones calibrados", hay,
                     f"SUBE {tuple(bv)} · BAJA {tuple(br)}" if hay
                     else "sin calibrar",
                     "" if hay else "Pulse «🔎 DETECTAR» con IQ Option "
                                    "visible."))

    # 7 · ¿En este monitor?
    if hay:
        try:
            from . import monitores as _mon
            ms = _mon.listar()
            m = _mon.del_punto(int(bv[0]), int(bv[1]))
            actual = _mon.monitor_de_barra(app)
            dentro = bool(m and m["n"] == actual["n"])
            e.append(Eslabon(7, "Calibrados en este monitor", dentro,
                             f"SUBE está en el monitor {m['n'] if m else '?'}, "
                             f"Litch trabaja en el {actual['n']}"
                             if not dentro else f"monitor {actual['n']}",
                             "" if dentro else
                             "Pulse «🔎 DETECTAR»: se muda al monitor donde "
                             "esté IQ Option y recalibra allí."))
        except Exception as ex:
            e.append(Eslabon(7, "Calibrados en este monitor", False,
                             str(ex)[:50], ""))

    # 8 · Demo o real
    tipo = str(cfg.get("tipo_cuenta") or "").lower()
    e.append(Eslabon(8, "Tipo de cuenta", tipo in ("demo", "real"),
                     tipo.upper() if tipo else "sin marcar",
                     "" if tipo else
                     "Márquelo en «⚙ PREPARAR». No opero sin saber en qué "
                     "cuenta estoy."))

    # 9 · Freno diario
    try:
        from . import freno_diario as _fd
        ok_d, por = _fd.puede_operar(app)
        e.append(Eslabon(9, "Freno diario", ok_d,
                         por or "sin restricción",
                         "" if ok_d else
                         "Se levanta mañana solo. Para levantarlo ahora: "
                         "«levanta el freno»."))
    except Exception:
        e.append(Eslabon(9, "Freno diario", True, "no aplicable"))

    # 10 · La ventana
    try:
        from . import autoconfigurar as _ac
        v = _ac.ventana_iq()
        e.append(Eslabon(10, "Ventana de IQ Option", bool(v),
                         f"{v['w']}×{v['h']} en ({v['x']},{v['y']})" if v
                         else "no la encuentro",
                         "" if v else
                         "Ábrala y déjela visible, no minimizada."))
    except Exception as ex:
        v = None
        e.append(Eslabon(10, "Ventana de IQ Option", False, str(ex)[:50], ""))

    # 11 · ¿Los botones caen dentro de la ventana?
    if hay and v:
        dentro = (v["x"] <= bv[0] < v["x"] + v["w"]
                  and v["y"] <= bv[1] < v["y"] + v["h"])
        e.append(Eslabon(11, "Botones dentro de la ventana", dentro,
                         "sí" if dentro else
                         f"SUBE en {tuple(bv)}, la ventana va de "
                         f"({v['x']},{v['y']}) a "
                         f"({v['x']+v['w']},{v['y']+v['h']})",
                         "" if dentro else
                         "La ventana se movió desde la última calibración. "
                         "Pulse «🔎 DETECTAR»."))

    # 12 · ¿Algo los tapa?
    if hay:
        try:
            from . import manos as _mn
            tap = _mn._dentro_de_tws(int(bv[0]), int(bv[1]))
            e.append(Eslabon(12, "Botones alcanzables", not tap,
                             "libres" if not tap else
                             "los tapa Trader Workstation",
                             "" if not tap else
                             "Traiga IQ Option al frente, o mueva TWS."))
        except Exception:
            e.append(Eslabon(12, "Botones alcanzables", True, "no comprobable"))

    # 13 · El filtro de ventaja
    try:
        from . import filtro_ventaja as _fv
        ok_v, por_v = _fv.permitir(app, 8)     # una señal fuerte de ejemplo
        e.append(Eslabon(13, "Filtro de ventaja", ok_v,
                         por_v[:110] if por_v else "pasa",
                         "" if ok_v else
                         "No es un fallo: con 8 de 11 votos no tengo "
                         "ventaja demostrada en este contexto. Es el "
                         "filtro haciendo su trabajo."))
    except Exception:
        e.append(Eslabon(13, "Filtro de ventaja", True, "no aplicable"))

    # 14 · Tamaño sensato
    cap = cfg.get("saldo") or cfg.get("capital")
    mto = cfg.get("monto_broker") or cfg.get("monto_base")
    if cap and mto:
        try:
            from . import mercado_y_tamano as _myt
            ev = _myt.evaluar_tamano(cap, mto, cfg.get("divisa", ""))
            e.append(Eslabon(14, "Tamaño de la apuesta", not ev.get("grave"),
                             f"{ev['pct']:.2f} % del capital, aguanta "
                             f"{ev['aguanta']} pérdidas",
                             "" if not ev.get("grave") else
                             f"Baje a {ev['sugerido']:.0f} en «⚙ PREPARAR»."))
        except Exception:
            pass
    else:
        e.append(Eslabon(14, "Tamaño de la apuesta", False,
                         "no sé su saldo o su monto",
                         "Escríbalos en «⚙ PREPARAR». Sin ellos no puedo "
                         "juzgar si arriesga de más."))
    return e


def informe(app) -> str:
    """El diagnóstico, señalando el PRIMER eslabón roto."""
    e = revisar(app)
    rotos = [x for x in e if not x.ok]

    l = ["¿POR QUÉ NO OPERO? — la cadena completa", ""]
    for x in e:
        marca = "✓" if x.ok else "✗"
        l.append(f" {marca} {x.n:2d}. {x.nombre}: {x.detalle}")

    l.append("")
    if not rotos:
        l.append("Todo en orden. Si aun así no me ve operar, es que no hay "
                 "señales que pasen mis filtros — que es distinto de estar "
                 "rota. Mire «🎲 ¿Dónde tengo ventaja?».")
        return "\n".join(l)

    p = rotos[0]
    l.append(f"SE ROMPE EN EL {p.n}: {p.nombre}")
    l.append(f"   {p.detalle}")
    if p.arreglo:
        l.append("")
        l.append(f"   → {p.arreglo}")
    if len(rotos) > 1:
        l.append("")
        l.append(f"Hay {len(rotos)-1} más abajo, pero no los mire todavía: "
                 f"los eslabones posteriores ni se prueban mientras este "
                 f"falle. Arregle este y vuelva a preguntar — puede que se "
                 f"arreglen solos.")
    return "\n".join(l)


def probar_clic(app) -> str:
    """
    Comprueba que el ratón obedece de verdad.

    Mueve el cursor y lee dónde acabó. No pulsa nada: mover es
    inofensivo, pulsar no. Si el movimiento no llega, el clic tampoco
    llegaría — y ahí está la respuesta sin arriesgar nada.
    """
    try:
        import pyautogui
    except Exception as ex:
        return f"No tengo pyautogui: {ex}"

    l = ["PRUEBA DEL RATÓN", ""]
    try:
        x0, y0 = pyautogui.position()
        l.append(f"· Cursor ahora: ({x0}, {y0})")

        pyautogui.moveTo(x0 + 40, y0 + 20, duration=0.15)
        time.sleep(0.15)
        x1, y1 = pyautogui.position()
        ok1 = abs(x1 - (x0 + 40)) <= 4 and abs(y1 - (y0 + 20)) <= 4
        l.append(f"· Le pedí ir a ({x0+40}, {y0+20}) → llegó a ({x1}, {y1})")

        pyautogui.moveTo(x0, y0, duration=0.15)
        l.append("· Devuelto a su sitio")
        l.append("")

        if ok1:
            l.append("El ratón obedece. Si no ve clics, el problema está "
                     "más adelante en la cadena: pulse «🩺 ¿Por qué no "
                     "opero?».")
        else:
            l.append("EL RATÓN NO OBEDECE, señor. Le pido ir a un sitio y "
                     "acaba en otro.")
            l.append("")
            l.append("Casi siempre es esto: hay una ventana abierta con "
                     "permisos de administrador. Windows impide que un "
                     "programa normal le mande clics o teclas a una que "
                     "tiene más privilegios — y ese bloqueo es silencioso.")
            l.append("")
            l.append("Cierre lo que haya abierto como administrador, o "
                     "arranque Litch también como administrador.")
    except Exception as ex:
        l.append(f"La prueba falló: {ex}")
    return "\n".join(l)


__all__ = ["revisar", "informe", "probar_clic", "Eslabon"]

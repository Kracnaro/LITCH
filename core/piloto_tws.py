"""
piloto_tws.py — Litch OPERA Trader Workstation con sus propias manos.

Litch ya sabe mover el mouse y hacer clics (así opera IQ Option). Este
módulo le enseña a hacerlo en TWS: escribir el símbolo, poner la cantidad,
elegir el tipo de orden y pulsar los botones.

═══ SEGURIDAD (innegociable) ═══════════════════════════════════════════
Antes de CUALQUIER interacción, Litch verifica:
  1. Que la ventana sea TWS y esté al frente.
  2. Que la cuenta sea PAPER (título con DU / "simulada"). Si detecta
     cuenta REAL, se detiene y avisa. Sin excepciones.
  3. Que el modo autónomo esté activo (el usuario dio permiso explícito).
Si algo falla, NO toca nada.

Además: por defecto trabaja en modo ENSAYO (dry_run) — mueve el mouse y
te muestra qué haría, pero NO pulsa ENVIAR. Para que ejecute de verdad
hay que pedirlo explícitamente.
"""

from __future__ import annotations

import time

try:
    import pyautogui as _pg
    _pg.FAILSAFE = True     # mover el mouse a una esquina aborta todo
    _PG_OK = True
except Exception:
    _PG_OK = False


# Proporciones del panel "ENTRADA DE ÓRDENES" dentro de la ventana de TWS
# (layout Mosaico). Se calibran solas con la ventana detectada.
CAMPOS = {
    "simbolo":   {"x": 0.055, "y": 0.115},   # casilla del ticker
    "comprar":   {"x": 0.033, "y": 0.245},   # botón COMPRAR
    "vender":    {"x": 0.075, "y": 0.245},   # botón VENDER
    "cantidad":  {"x": 0.265, "y": 0.245},   # CANT.
    "tipo":      {"x": 0.315, "y": 0.245},   # LMT / MKT
    "precio":    {"x": 0.380, "y": 0.245},   # PRECIO LÍM.
    "enviar":    {"x": 0.645, "y": 0.245},   # botón ENVIAR
}


def _campos_de(app) -> dict:
    """Proporciones a usar: las calibradas por el usuario si existen.

    Las de CAMPOS son ESTIMACIONES. En cuanto el usuario calibra con
    'calibra el ticket de TWS', se usan las reales y todo se vuelve exacto.
    """
    try:
        guardadas = app.mem["config"].get("tws_campos")
        if isinstance(guardadas, dict) and guardadas:
            base = dict(CAMPOS)
            for k, v in guardadas.items():
                if k in base and isinstance(v, dict) and "x" in v and "y" in v:
                    base[k] = {"x": float(v["x"]), "y": float(v["y"])}
            return base
    except Exception:
        pass
    return CAMPOS


def esta_calibrado(app) -> bool:
    """¿El usuario ya midió los campos reales, o seguimos con estimaciones?"""
    try:
        g = app.mem["config"].get("tws_campos")
        return isinstance(g, dict) and len(g) >= len(CAMPOS)
    except Exception:
        return False


def _coord(ventana: dict, campo: str, app=None) -> tuple[int, int]:
    """Convierte la proporción de un campo a coordenadas de pantalla.

    SEGURIDAD: el resultado se recorta SIEMPRE al interior de la ventana de
    TWS. Litch no puede hacer clic fuera de TWS por un error de cálculo.
    """
    campos = _campos_de(app) if app is not None else CAMPOS
    c = campos.get(campo, CAMPOS[campo])
    x = int(ventana["x"] + ventana["w"] * c["x"])
    y = int(ventana["y"] + ventana["h"] * c["y"])
    # Recorte duro a los límites de la ventana (margen de 2 px)
    x = max(ventana["x"] + 2, min(x, ventana["x"] + ventana["w"] - 2))
    y = max(ventana["y"] + 2, min(y, ventana["y"] + ventana["h"] - 2))
    return x, y


# ═══════════════════════════════════════════════════════════════════════════
#  Verificación de seguridad
# ═══════════════════════════════════════════════════════════════════════════

def verificar_seguro(app) -> dict:
    """¿Es seguro que Litch toque TWS ahora mismo?"""
    from . import vision_tws as _vt

    r = {"seguro": False, "motivo": "", "ventana": None}

    if not _PG_OK:
        r["motivo"] = "No tengo control de mouse (falta pyautogui)."
        return r

    est = _vt.leer_estado_tws(app)
    if not est.get("tws_abierta"):
        r["motivo"] = "No veo Trader Workstation abierto."
        return r

    # SEGURIDAD 1: cuenta paper obligatoria
    if est.get("es_paper") is False:
        r["motivo"] = ("⛔ La cuenta es REAL. No toco TWS con dinero "
                       "verdadero. Cambie a la cuenta simulada (DU).")
        return r
    if est.get("es_paper") is None:
        r["motivo"] = ("No confirmo que la cuenta sea simulada. Por "
                       "seguridad no toco nada. El título de TWS debe "
                       "mostrar DU o 'negociación simulada'.")
        return r

    # SEGURIDAD 2: modo autónomo activo (permiso del usuario)
    if not (getattr(app, "autoclick_on", False)
            and getattr(app, "modo_autonomo", False)):
        r["motivo"] = ("El modo autónomo está apagado. Pulse AUTO para "
                       "autorizarme a mover el mouse.")
        return r

    v = _vt.ventana_tws()
    if not v:
        r["motivo"] = "Perdí la ventana de TWS."
        return r

    # SEGURIDAD 4: nada puede estar tapando TWS.
    # Un diálogo modal encima ("¿confirma?", un aviso de riesgo) hace que
    # las coordenadas sigan calculándose bien pero los clics acaben en
    # otro sitio. Es la trampa clásica: mejor detenerse.
    try:
        from . import conciencia_pantalla as _cp
        d = _cp.detectar_dialogo(app)
        if d.get("hay"):
            r["motivo"] = d["mensaje"]
            return r
    except Exception:
        pass      # si el detector falla, no bloqueo las demás protecciones

    r.update({"seguro": True, "ventana": v,
              "motivo": f"Cuenta simulada {est.get('cuenta','DU')} "
                        f"verificada. Autorizado."})
    return r


# ═══════════════════════════════════════════════════════════════════════════
#  CALIBRACIÓN REAL — el usuario le enseña a Litch dónde está cada campo
# ═══════════════════════════════════════════════════════════════════════════

# Guion de calibración: campo → cómo pedírselo al usuario
_GUION_CAL = [
    ("simbolo",  "la casilla donde se ESCRIBE EL SÍMBOLO (donde dice SPY o "
                 "el nombre del activo)"),
    ("comprar",  "el botón COMPRAR (normalmente azul)"),
    ("vender",   "el botón VENDER (normalmente rojo)"),
    ("cantidad", "la casilla CANT. (la cantidad de acciones)"),
    ("tipo",     "la casilla TIPO (donde dice LMT o MKT)"),
    ("precio",   "la casilla PRECIO (el precio límite)"),
    ("enviar",   "el botón ENVIAR"),
]

SEG_POR_CAMPO = 6      # segundos que Litch espera en cada campo


def calibrar_ticket(app, segundos: int = SEG_POR_CAMPO) -> str:
    """Litch aprende las posiciones REALES del ticket de TWS.

    El usuario pone el mouse sobre cada campo y Litch anota dónde está.
    Esto convierte las estimaciones en medidas exactas de SU pantalla.
    Se ejecuta en segundo plano para no congelar la interfaz.
    """
    if not _PG_OK:
        return "No tengo control de mouse (falta pyautogui), señor."

    from . import vision_tws as _vt
    v = _vt.ventana_tws()
    if not v:
        return ("No veo Trader Workstation, señor. Ábralo, deje visible el "
                "panel de ENTRADA DE ÓRDENES y vuelva a pedírmelo.")

    import threading

    def _tarea():
        medidos = {}
        try:
            app.decir("Vamos a calibrar el ticket de órdenes. Le iré pidiendo "
                      "que ponga el mouse sobre cada campo. No haga clic, "
                      "solo déjelo encima.")
            time.sleep(2.5)

            for campo, descripcion in _GUION_CAL:
                msg = f"Ponga el mouse sobre {descripcion}."
                app.log(f"[Calibrar TWS] {msg}")
                app.decir(msg)
                # Cuenta regresiva audible en los últimos segundos
                for restante in range(segundos, 0, -1):
                    if restante == 3:
                        app.decir("Tres.")
                    elif restante == 2:
                        app.decir("Dos.")
                    elif restante == 1:
                        app.decir("Uno.")
                    time.sleep(1)

                px, py = _pg.position()
                # Reconfirmar la ventana por si la movieron
                vv = _vt.ventana_tws() or v
                if not (vv["x"] <= px <= vv["x"] + vv["w"]
                        and vv["y"] <= py <= vv["y"] + vv["h"]):
                    app.log(f"[Calibrar TWS] ⚠ {campo}: el mouse estaba FUERA "
                            f"de TWS ({px},{py}). Conservo la estimación.")
                    app.decir(f"El mouse estaba fuera de la ventana. "
                              f"Conservo mi estimación para {campo}.")
                    continue

                prop_x = round((px - vv["x"]) / max(1, vv["w"]), 4)
                prop_y = round((py - vv["y"]) / max(1, vv["h"]), 4)
                medidos[campo] = {"x": prop_x, "y": prop_y}
                app.log(f"[Calibrar TWS] ✓ {campo} = ({px},{py}) "
                        f"→ proporción ({prop_x}, {prop_y})")
                app.decir("Anotado.")
                time.sleep(0.6)

            if medidos:
                cfg = app.mem["config"]
                previos = cfg.get("tws_campos") or {}
                if not isinstance(previos, dict):
                    previos = {}
                previos.update(medidos)
                cfg["tws_campos"] = previos
                cfg["tws_campos_fecha"] = time.strftime("%Y-%m-%d %H:%M")
                try:
                    from . import memoria
                    memoria.guardar(app.mem)
                except Exception:
                    pass
                faltan = [c for c, _ in _GUION_CAL if c not in previos]
                final = (f"Calibración guardada, señor. Aprendí "
                         f"{len(medidos)} campos de su pantalla.")
                if faltan:
                    final += (" Todavía me faltan: " + ", ".join(faltan) +
                              ". Repita la calibración cuando quiera.")
                else:
                    final += (" Ya tengo el ticket completo. Ahora sé "
                              "exactamente dónde está cada cosa en SU TWS.")
                app.log("[Calibrar TWS] " + final)
                app.decir(final)
            else:
                app.decir("No pude medir ningún campo, señor. "
                          "Intentémoslo otra vez con TWS al frente.")
        except Exception as e:
            try:
                app.log(f"[Calibrar TWS] Error: {e}")
            except Exception:
                pass

    threading.Thread(target=_tarea, daemon=True,
                     name="LitchCalibrarTWS").start()

    return (f"Empecemos, señor. Le pediré {len(_GUION_CAL)} campos, "
            f"{segundos} segundos cada uno. Ponga el mouse encima de lo que "
            f"le diga y NO haga clic. Escuche mis instrucciones.")


def estado_calibracion(app) -> str:
    """Cuenta qué campos tiene medidos y cuáles son estimación."""
    try:
        g = app.mem["config"].get("tws_campos") or {}
    except Exception:
        g = {}
    medidos = [c for c, _ in _GUION_CAL if c in g]
    faltan = [c for c, _ in _GUION_CAL if c not in g]
    if not medidos:
        return ("Aún no he calibrado el ticket de TWS, señor. Estoy usando "
                "ESTIMACIONES, que pueden estar corridas en su pantalla. "
                "Dígame 'calibra el ticket de TWS' y en un minuto quedo "
                "exacto. Mientras tanto solo trabajo en modo ensayo.")
    txt = (f"Tengo {len(medidos)} de {len(_GUION_CAL)} campos medidos en su "
           f"pantalla ({', '.join(medidos)})")
    fecha = None
    try:
        fecha = app.mem["config"].get("tws_campos_fecha")
    except Exception:
        pass
    if fecha:
        txt += f", calibrados el {fecha}"
    if faltan:
        txt += f". Me faltan por medir: {', '.join(faltan)}."
    else:
        txt += ". Ticket completo ✓"
    return txt


# ═══════════════════════════════════════════════════════════════════════════
#  Operar TWS
# ═══════════════════════════════════════════════════════════════════════════

def poner_simbolo(app, simbolo: str, ensayo: bool = True) -> str:
    """Escribe el símbolo en la casilla de TWS (ej. SPY)."""
    chk = verificar_seguro(app)
    if not chk["seguro"]:
        return chk["motivo"]
    v = chk["ventana"]
    x, y = _coord(v, "simbolo", app)

    # SEGURIDAD 3: sin calibración real, jamás se hace clic de verdad
    if not ensayo and not esta_calibrado(app):
        return ("No he calibrado el ticket de TWS todavía, señor, y no pienso "
                "hacer clic a ciegas con coordenadas estimadas. Dígame "
                "'calibra el ticket de TWS' (toma un minuto) y después sí "
                "opero exacto. Por ahora hago el ensayo.")

    if ensayo:
        try:
            _pg.moveTo(x, y, duration=0.4)
        except Exception:
            pass
        return (f"[ENSAYO] Escribiría «{simbolo}» en la casilla del símbolo "
                f"({x},{y}). Muevo el mouse ahí para que lo vea, sin tocar.")

    try:
        _pg.tripleClick(x, y)            # selecciona lo que haya
        time.sleep(0.15)
        _pg.typewrite(simbolo.upper(), interval=0.06)
        _pg.press("enter")
        time.sleep(0.8)
        app.log(f"[PilotoTWS] Símbolo cambiado a {simbolo.upper()}")
        return f"Símbolo {simbolo.upper()} cargado en TWS, señor."
    except Exception as e:
        return f"No pude escribir el símbolo: {e}"


def preparar_orden(app, simbolo: str, accion: str, cantidad: int,
                   precio: float = None, ensayo: bool = True) -> str:
    """Llena el ticket de orden en TWS. NUNCA pulsa ENVIAR en modo ensayo.

    accion: 'COMPRAR' o 'VENDER'
    """
    chk = verificar_seguro(app)
    if not chk["seguro"]:
        return chk["motivo"]
    v = chk["ventana"]
    accion = accion.upper()
    if accion not in ("COMPRAR", "VENDER"):
        return "La acción debe ser COMPRAR o VENDER."
    try:
        cantidad = int(cantidad)
    except Exception:
        return "La cantidad debe ser un número entero de acciones."
    if cantidad <= 0:
        return "La cantidad debe ser mayor que cero, señor."

    # SEGURIDAD 3: sin calibración real, jamás se hace clic de verdad
    if not ensayo and not esta_calibrado(app):
        return ("No he calibrado el ticket de TWS, señor. No lleno un "
                "formulario de órdenes con coordenadas adivinadas. Dígame "
                "'calibra el ticket de TWS' primero.")

    pasos = []

    if ensayo:
        # Recorrido guiado: mueve el mouse por cada campo para enseñar
        for campo in ("simbolo", "cantidad", "tipo", "precio",
                      "comprar" if accion == "COMPRAR" else "vender"):
            x, y = _coord(v, campo, app)
            try:
                _pg.moveTo(x, y, duration=0.5)
                time.sleep(0.3)
            except Exception:
                pass
            pasos.append(f"{campo} ({x},{y})")
        aviso = ("" if esta_calibrado(app) else
                 " OJO: estoy usando posiciones ESTIMADAS, por eso solo "
                 "ensayo. Calibre con 'calibra el ticket de TWS' para que "
                 "pueda operar de verdad.")
        return (f"[ENSAYO] Recorrí el ticket de orden mostrándole cada campo: "
                f"{' → '.join(pasos)}. Pondría {accion} {cantidad}x "
                f"{simbolo.upper()}"
                + (f" a {precio}" if precio else " a mercado")
                + ". NO pulsé ENVIAR." + aviso)

    # ── Ejecución real (solo en paper verificado y calibrado) ───────────────
    try:
        # 1) Símbolo
        x, y = _coord(v, "simbolo", app)
        _pg.tripleClick(x, y); time.sleep(0.15)
        _pg.typewrite(simbolo.upper(), interval=0.05)
        _pg.press("enter"); time.sleep(1.0)

        # 2) Cantidad
        x, y = _coord(v, "cantidad", app)
        _pg.tripleClick(x, y); time.sleep(0.15)
        _pg.typewrite(str(cantidad), interval=0.05)

        # 3) Precio límite (si se indicó)
        if precio:
            x, y = _coord(v, "precio", app)
            _pg.tripleClick(x, y); time.sleep(0.15)
            _pg.typewrite(f"{float(precio):.2f}", interval=0.05)

        # 4) Lado de la orden
        x, y = _coord(v, "comprar" if accion == "COMPRAR" else "vender", app)
        _pg.click(x, y); time.sleep(0.3)

        # Deja constancia del ticket armado: sin esto no se puede ENVIAR
        global _TICKET
        _TICKET = {"ts": time.time(), "simbolo": simbolo.upper(),
                   "accion": accion, "cantidad": cantidad, "precio": precio}

        app.log(f"[PilotoTWS] Ticket preparado: {accion} {cantidad}x "
                f"{simbolo.upper()}" + (f" @ {precio}" if precio else ""))
        return (f"Ticket listo en TWS: {accion} {cantidad}x "
                f"{simbolo.upper()}"
                + (f" a {precio}" if precio else "")
                + ". Revíselo con sus propios ojos y pulse ENVIAR usted, o "
                  "dígame 'confirma el envío' si quiere que lo pulse yo.")
    except Exception as e:
        return f"Error preparando la orden: {e}"


# Último ticket que Litch armó de verdad. ENVIAR exige que exista y sea
# reciente: así nunca se pulsa el botón "por su cuenta" ni sobre un
# formulario que ya cambió.
_TICKET: dict | None = None
VIGENCIA_TICKET = 120      # segundos


def pulsar_enviar(app) -> str:
    """Pulsa ENVIAR en TWS. Solo en cuenta paper, calibrada y con ticket."""
    global _TICKET
    chk = verificar_seguro(app)
    if not chk["seguro"]:
        return chk["motivo"]

    if not esta_calibrado(app):
        return ("No pulso ENVIAR con coordenadas estimadas, señor. Ese botón "
                "es el que mueve la orden. Calibre primero con 'calibra el "
                "ticket de TWS'.")

    if not _TICKET:
        return ("No he armado ningún ticket, así que no sé qué estaría "
                "enviando. Primero dígame 'prepara la orden en TWS' y "
                "revísela usted antes de que yo pulse nada.")

    edad = time.time() - _TICKET.get("ts", 0)
    if edad > VIGENCIA_TICKET:
        _TICKET = None
        return (f"El ticket que armé tiene {int(edad)} segundos y ya no me "
                f"fío de que siga igual en pantalla. Vuelva a prepararlo, "
                f"señor.")

    t = _TICKET
    v = chk["ventana"]
    try:
        x, y = _coord(v, "enviar", app)
        _pg.click(x, y)
        app.log(f"[PilotoTWS] ENVIAR pulsado (simulada): {t['accion']} "
                f"{t['cantidad']}x {t['simbolo']}")
        _TICKET = None      # un ticket, un envío
        return (f"Enviada en la cuenta simulada: {t['accion']} "
                f"{t['cantidad']}x {t['simbolo']}"
                + (f" a {t['precio']}" if t.get("precio") else "")
                + ". Revise la pestaña Órdenes para ver si se ejecutó.")
    except Exception as e:
        return f"No pude pulsar ENVIAR: {e}"


def leccion_guiada(app, simbolo: str = "SPY") -> str:
    """Recorrido educativo: Litch muestra dónde está cada cosa en TWS.

    Mueve el mouse por cada campo explicando para qué sirve. No toca nada.
    """
    chk = verificar_seguro(app)
    if not chk["seguro"]:
        return chk["motivo"]
    v = chk["ventana"]

    guion = [
        ("simbolo",  "Aquí va el SÍMBOLO del activo, por ejemplo SPY."),
        ("comprar",  "Este es COMPRAR: abre una posición larga."),
        ("vender",   "Este es VENDER: cierra o abre una posición corta."),
        ("cantidad", "Aquí la CANTIDAD de acciones."),
        ("tipo",     "Aquí el TIPO: LMT (límite, controla el precio) o MKT."),
        ("precio",   "Aquí el PRECIO LÍMITE al que acepta comprar."),
        ("enviar",   "Y este es ENVIAR. Solo se pulsa con el plan completo."),
    ]
    if not esta_calibrado(app):
        app.log("[Lección TWS] Aviso: posiciones estimadas, no calibradas.")
        app.decir("Aviso: todavía no he calibrado su pantalla, así que puedo "
                  "señalar un poco corrido. Al terminar, pídame calibrar el "
                  "ticket y quedaré exacto.")
        time.sleep(1.5)

    for campo, explicacion in guion:
        x, y = _coord(v, campo, app)
        try:
            _pg.moveTo(x, y, duration=0.7)
            app.log(f"[Lección TWS] {explicacion}  ({x},{y})")
            app.decir(explicacion)
            time.sleep(1.2)
        except Exception:
            pass
    return ("Fin del recorrido, señor. Le mostré los 7 campos del ticket de "
            "orden. Así es como opero yo también: símbolo, cantidad, tipo, "
            "precio, lado y enviar.")

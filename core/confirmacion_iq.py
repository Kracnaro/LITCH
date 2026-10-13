"""
confirmacion_iq.py — El diálogo de confirmación de IQ Option.

━━━ QUÉ ES Y POR QUÉ IMPORTA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cuando se pulsa SUBE o BAJA en IQ Option, la operación NO se abre todavía.
Aparece antes un cuadro de CONFIRMACIÓN que muestra:

    Precio de apertura   223.1660
    Invers               CO$ 2,000
    Vencimiento          30 seg
    [ CONFIRMAR "SUBE" ]
    [ ] Comprar en un click

Hasta que no se pulsa CONFIRMAR, no hay operación. Ni dinero movido, ni
posición abierta, ni resultado.

━━━ EL PELIGRO QUE ESTO ESCONDE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Es exactamente la misma trampa que ya nos costó 86 operaciones fantasma
en Interactive Brokers: Litch pulsa, da la operación por hecha, espera el
resultado leyendo píxeles, y anota un acierto o un fallo que nunca
ocurrió. Solo que aquí el clic SÍ llega — lo que no llega es la orden.

Un motor que no distingue «pulsé el botón» de «la operación existe»
aprende de datos inventados. Y un modelo entrenado con datos inventados
da consejos inventados con toda la seguridad del mundo.

━━━ LA REGLA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Una operación NO existe hasta que se confirma y se comprueba.

Y hay una distinción que el señor pidió expresamente:

  · MODO PROFESIONAL — él está delante, mirando. El diálogo se queda
    abierto y CONFIRMA ÉL. Litch prepara, muestra y espera. Ese cuadro
    deja de ser un estorbo y pasa a ser lo que es: el último filtro
    humano antes de que se mueva el dinero.

  · MODO AUTÓNOMO — nadie está mirando. Litch confirma sola, pero
    comprueba después que el diálogo se cerró de verdad. Si sigue
    abierto, la operación no salió y no se anota nada.

La casilla «Comprar en un click» quita el diálogo. Litch NO la marca por
su cuenta: es la única barrera que le queda al señor entre una decisión
y su dinero, y quitarla es decisión suya.
"""

from __future__ import annotations

import time

# Textos del diálogo, en los idiomas en que IQ Option lo pinta
TITULOS = ("confirmación", "confirmacion", "confirmation")
BOTON_CONFIRMAR = ("confirmar", "confirm")
CASILLA_UN_CLIC = ("comprar en un click", "comprar en un clic",
                   "buy in one click", "one click")

# Cuánto se espera a que el diálogo aparezca tras pulsar SUBE/BAJA
ESPERA_APARECER = 1.2
# Cuánto se espera a que desaparezca tras confirmar
ESPERA_CERRAR = 1.6


def _plano(t: str) -> str:
    t = (t or "").lower()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u")):
        t = t.replace(a, b)
    return t


# ── Detección ────────────────────────────────────────────────────────────────

def hay_dialogo(app) -> dict:
    """
    ¿Está abierto el cuadro de confirmación?

    Devuelve {"hay": bool, "boton": (x,y)|None, "texto": str}.

    Se busca por el botón CONFIRMAR, que es lo único imprescindible: si
    está, hay diálogo; si no, no lo hay. Buscar el título sería más
    frágil porque cambia con el idioma y con la versión.
    """
    r = {"hay": False, "boton": None, "texto": ""}
    try:
        import pyautogui
        for txt in BOTON_CONFIRMAR:
            try:
                caja = pyautogui.locateOnScreen(txt, confidence=0.75)
                if caja:
                    r["hay"] = True
                    r["boton"] = pyautogui.center(caja)
                    r["texto"] = txt
                    return r
            except Exception:
                continue
    except Exception:
        pass

    # Vía de respaldo: la posición aprendida en sesiones anteriores.
    # Menos fiable que ver el botón, pero mejor que rendirse.
    try:
        pos = app.mem.get("config", {}).get("boton_confirmar_iq")
        if pos and len(pos) >= 2:
            r["hay"] = None      # «no lo sé»: hay posición, no certeza
            r["boton"] = (int(pos[0]), int(pos[1]))
            r["texto"] = "posición recordada"
    except Exception:
        pass
    return r


def aprender_posicion(app, x: int, y: int) -> str:
    """Recuerda dónde estaba el botón CONFIRMAR."""
    try:
        app.mem.setdefault("config", {})["boton_confirmar_iq"] = [int(x), int(y)]
        from . import memoria as _m
        _m.guardar(app.mem)
        return f"Apuntado: el botón CONFIRMAR está en ({x},{y})."
    except Exception as e:
        return f"No pude recordarlo: {e}"


# ── Qué hacer con el diálogo ─────────────────────────────────────────────────

def modo_del_usuario(app) -> str:
    """
    ¿Quién confirma: el señor o Litch?

    'usuario'  — está delante y confirma él (modo profesional)
    'litch'    — nadie mira; Litch confirma y comprueba
    """
    try:
        pro = getattr(app, "modo_profesional", None)
        if pro is not None and getattr(pro, "activo", False):
            return "usuario"
    except Exception:
        pass
    try:
        if app.mem.get("config", {}).get("confirmar_yo") is True:
            return "usuario"
    except Exception:
        pass
    return "litch"


def gestionar(app, direccion: str = "") -> dict:
    """
    Se llama JUSTO DESPUÉS de pulsar SUBE o BAJA.

    Devuelve:
        {"operacion_existe": bool, "confirmada_por": str, "mensaje": str}

    `operacion_existe` es la respuesta que importa. Si es False, el motor
    NO debe anotar resultado: no hubo operación que puntuar.
    """
    r = {"operacion_existe": False, "confirmada_por": "", "mensaje": ""}

    time.sleep(ESPERA_APARECER)
    d = hay_dialogo(app)

    if d["hay"] is False:
        # No hay diálogo. Dos posibilidades honestas, y hay que decir
        # cuál: o la casilla «un click» está marcada y la operación ya
        # salió, o el clic no llegó a ningún sitio.
        r["operacion_existe"] = True
        r["confirmada_por"] = "un_click"
        r["mensaje"] = ("No apareció cuadro de confirmación. Doy la "
                        "operación por abierta porque la casilla «Comprar "
                        "en un click» debe estar marcada.")
        return r

    modo = modo_del_usuario(app)

    if modo == "usuario":
        # ── El señor está delante ──────────────────────────────────────
        r["operacion_existe"] = False
        r["confirmada_por"] = "pendiente_usuario"
        r["mensaje"] = (
            f"Cuadro de confirmación abierto"
            + (f" para {direccion}" if direccion else "") +
            ". Está usted delante, así que no lo toco: confirme o cierre "
            "usted. Hasta que no pulse CONFIRMAR no hay operación, y no "
            "anotaré ningún resultado.")
        return r

    # ── Modo autónomo: Litch confirma, pero comprueba ──────────────────
    if not d["boton"]:
        r["mensaje"] = ("Veo el cuadro de confirmación pero no localizo el "
                        "botón CONFIRMAR. No toco nada a ciegas.")
        return r

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.click(d["boton"][0], d["boton"][1])
        aprender_posicion(app, d["boton"][0], d["boton"][1])
    except Exception as e:
        r["mensaje"] = f"No pude pulsar CONFIRMAR: {e}"
        return r

    # LA COMPROBACIÓN. Sin esto todo lo anterior es fe, no certeza.
    time.sleep(ESPERA_CERRAR)
    d2 = hay_dialogo(app)
    if d2["hay"] is True:
        r["operacion_existe"] = False
        r["confirmada_por"] = "fallida"
        r["mensaje"] = ("Pulsé CONFIRMAR pero el cuadro sigue abierto: la "
                        "operación NO salió. No anoto resultado — no "
                        "aprendo de algo que no ocurrió.")
        return r

    r["operacion_existe"] = True
    r["confirmada_por"] = "litch"
    r["mensaje"] = "Confirmado y comprobado: el cuadro se cerró, la operación existe."
    return r


# ── Lo que Litch sabe de este entorno ────────────────────────────────────────

def explicar() -> str:
    """Lo que Litch ha entendido del entorno de IQ Option."""
    return (
        "EL CUADRO DE CONFIRMACIÓN DE IQ OPTION — lo que he entendido\n"
        "\n"
        "Cuando pulso SUBE o BAJA la operación todavía NO existe. Aparece "
        "un cuadro que muestra el precio de apertura, la inversión y el "
        "vencimiento, y hasta que no se pulsa CONFIRMAR no hay nada: ni "
        "dinero movido, ni posición, ni resultado.\n"
        "\n"
        "Esto importa más de lo que parece. Si yo diera por hecha la "
        "operación al pulsar el botón, estaría anotando aciertos y fallos "
        "de operaciones que nunca ocurrieron — es lo mismo que ya pasó en "
        "Interactive Brokers y costó 86 registros falsos. Un modelo "
        "entrenado con datos inventados da consejos inventados, y los da "
        "con toda la seguridad del mundo.\n"
        "\n"
        "Por eso:\n"
        "  · EN MODO PROFESIONAL usted está delante. No toco el cuadro: "
        "confirma usted. Ese cuadro no es un estorbo, es su último filtro "
        "antes de que se mueva el dinero.\n"
        "  · EN MODO AUTÓNOMO confirmo yo, pero después compruebo que el "
        "cuadro se cerró. Si sigue abierto, la operación no salió y no "
        "anoto nada.\n"
        "\n"
        "La casilla «Comprar en un click» quita este paso. No la marco por "
        "mi cuenta: es la única barrera que le queda entre una decisión y "
        "su dinero, y quitarla la decide usted."
    )


__all__ = ["hay_dialogo", "gestionar", "modo_del_usuario", "explicar",
           "aprender_posicion", "TITULOS", "BOTON_CONFIRMAR", "CASILLA_UN_CLIC"]

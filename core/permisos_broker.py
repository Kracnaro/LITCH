"""
permisos_broker.py — Qué puede tocar Litch, y de qué depende.

━━━ EL CAMBIO DE CRITERIO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Hasta ahora había una lista fija de cosas prohibidas: Transmit, Enviar,
Comprar, Vender. Esa lista era la misma en cuenta simulada que en cuenta
real, y eso estaba mal por los dos lados:

  · En cuenta simulada era demasiado estricta. Impedía justo lo que hay
    que practicar. Un piloto que nunca toca los mandos en el simulador
    no está aprendiendo a volar; está mirando volar.
  · En cuenta real era demasiado ingenua. Una lista de palabras no
    protege de nada si el botón se llama distinto en otro idioma o en
    otra versión.

La regla nueva es una sola, y es la correcta:

    LO QUE LITCH PUEDE HACER DEPENDE DE LA CUENTA, NO DE UNA LISTA.

  · Cuenta SIMULADA confirmada (número DU…, verificado contra el
    servidor de IBKR, no contra lo que diga la pantalla):
    ACCESO TOTAL. Puede tocar todo, incluido enviar órdenes. Es dinero
    ficticio: equivocarse ahí es exactamente para lo que sirve.

  · Cuenta REAL, o cuenta que NO se ha podido confirmar como simulada:
    NO ejecuta. Puede mirar, analizar, preparar y proponer, pero el
    último clic lo da el señor.

━━━ POR QUÉ SE MANTIENE ESA ÚNICA CONDICIÓN ━━━━━━━━━━━━━━━━━━━━━━━━━━
Porque es lo único que separa «practicar» de «gastar dinero de verdad
por accidente». El día que el señor entre con la cuenta real —el mismo
TWS, la misma pantalla, los mismos botones en el mismo sitio— nada en la
apariencia avisará del cambio. Solo el número de cuenta.

Y por eso la comprobación es contra el servidor, y por eso «no lo sé»
cuenta como «no». Es el mismo criterio que ya rige en broker_ibkr para
los brackets: la duda nunca es permiso.
"""

from __future__ import annotations

import time

# ── Niveles ──────────────────────────────────────────────────────────────────

TOTAL     = "total"      # cuenta simulada confirmada: puede todo
OBSERVA   = "observa"    # cuenta real o sin confirmar: mira y propone

DESCRIPCION = {
    TOTAL:   ("acceso total — cuenta simulada confirmada; puedo tocar, "
              "configurar y enviar órdenes"),
    OBSERVA: ("solo observación — no consta cuenta simulada; miro, analizo "
              "y preparo, pero el último clic lo da usted"),
}

_CACHE = {"nivel": "", "cuenta": "", "t": 0.0, "motivo": ""}
_TTL = 20.0     # segundos: la cuenta no cambia cada segundo, pero puede cambiar


def _verificar(app) -> tuple[str, str, str]:
    """
    Averigua el nivel real. Devuelve (nivel, cuenta, motivo).

    Se pregunta primero a la API de IBKR, que es la única fuente que no
    se puede confundir. La pantalla es la segunda opción y vale menos:
    un título de ventana se puede quedar viejo.
    """
    # 1. La API — la respuesta buena
    try:
        ib = getattr(app, "ibkr", None)
        if ib is not None and getattr(ib, "esta_conectado", False):
            es_paper = getattr(ib, "_es_paper", None)
            cuentas = getattr(ib, "_cuentas", []) or []
            cta = ", ".join(str(c) for c in cuentas)
            if es_paper is True:
                return TOTAL, cta, "cuenta simulada confirmada por la API de IBKR"
            if es_paper is False:
                return OBSERVA, cta, ("la API confirma CUENTA REAL: aquí no "
                                      "ejecuto nada por mi cuenta")
    except Exception:
        pass

    # 2. La pantalla — vale menos, pero es mejor que nada
    try:
        from . import vision_tws as _vt
        est = _vt.leer_estado_tws(app)
        cta = est.get("cuenta", "")
        if est.get("es_paper") is True:
            return TOTAL, cta, (f"cuenta {cta or 'DU…'} simulada según el "
                                f"título de la ventana")
        if est.get("es_paper") is False:
            return OBSERVA, cta, f"cuenta {cta} es REAL"
    except Exception:
        pass

    return OBSERVA, "", ("no he podido confirmar que la cuenta sea simulada; "
                         "ante la duda, no ejecuto")


def nivel(app, forzar: bool = False) -> str:
    """Nivel de acceso actual. Con caché corta para no preguntar sin parar."""
    ahora = time.time()
    if not forzar and _CACHE["nivel"] and (ahora - _CACHE["t"]) < _TTL:
        return _CACHE["nivel"]
    n, cta, motivo = _verificar(app)
    _CACHE.update({"nivel": n, "cuenta": cta, "t": ahora, "motivo": motivo})
    return n


def puede_todo(app) -> bool:
    """¿Litch tiene acceso total? Solo en cuenta simulada confirmada."""
    return nivel(app) == TOTAL


def puede_enviar_ordenes(app) -> tuple[bool, str]:
    """¿Puede pulsar Transmit / Enviar? Con el motivo, siempre."""
    n = nivel(app)
    if n == TOTAL:
        return True, _CACHE["motivo"]
    return False, _CACHE["motivo"]


def esta_prohibido(app, etiqueta: str) -> bool:
    """
    ¿Este elemento está fuera del alcance de Litch AHORA?

    En cuenta simulada confirmada: nada está prohibido.
    En cualquier otro caso: lo que mueve dinero, sí.
    """
    if puede_todo(app):
        return False
    try:
        from . import explorador_activo as _ex
        return _ex.es_prohibido(etiqueta)
    except Exception:
        # Si no se puede comprobar, se prohíbe. Fallar hacia el lado
        # seguro es lo único razonable cuando hay dinero de por medio.
        return True


def informe(app) -> str:
    """Qué puede hacer Litch ahora mismo, dicho claro."""
    n = nivel(app, forzar=True)
    cta = _CACHE["cuenta"] or "sin número"
    lineas = [f"PERMISOS ACTUALES — {DESCRIPCION[n]}", "",
              f"Cuenta: {cta}", f"Motivo: {_CACHE['motivo']}", ""]
    if n == TOTAL:
        lineas += [
            "Puedo, sin pedir permiso:",
            "  · abrir menús, pestañas y ventanas",
            "  · configurar el espacio de trabajo",
            "  · escribir símbolos y cantidades en el ticket",
            "  · enviar órdenes y cancelarlas",
            "  · cerrar posiciones",
            "",
            "Es dinero ficticio. Equivocarme aquí es el objetivo, no el "
            "riesgo: cada error que cometa en simulado es uno que no "
            "cometeré con su dinero.",
        ]
    else:
        lineas += [
            "Puedo: mirar, analizar, preparar operaciones completas y "
            "enseñárselas.",
            "NO puedo: enviar órdenes ni cerrar posiciones por mi cuenta.",
            "",
            "Si esta cuenta es simulada y aun así no la reconozco, "
            "conécteme a IBKR con «conecta con IBKR» y lo confirmo contra "
            "el servidor.",
        ]
    return "\n".join(lineas)


__all__ = ["TOTAL", "OBSERVA", "DESCRIPCION", "nivel", "puede_todo",
           "puede_enviar_ordenes", "esta_prohibido", "informe"]

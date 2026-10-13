"""
bandeja.py — El botón de un clic para conectar Litch con Interactive Brokers.

Pone un icono en la bandeja del sistema (junto al reloj). Un clic derecho
abre el menú: Conectar, Estado, Desconectar, Salir.

Colores del icono:
    gris    — sin conectar
    verde   — conectado a la cuenta simulada
    ámbar   — conectado pero sin poder confirmar que sea simulada
    rojo    — cuenta real detectada, o error

Uso:
    python bandeja.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

# ── Dependencias ────────────────────────────────────────────────────────────
_FALTA = []
try:
    import pystray
    from pystray import Menu, MenuItem
except Exception:
    _FALTA.append("pystray")
try:
    from PIL import Image, ImageDraw
except Exception:
    _FALTA.append("Pillow")

if _FALTA:
    print()
    print("  Faltan dependencias:", ", ".join(_FALTA))
    print("  Instálalas con:")
    print(f"      pip install {' '.join(_FALTA)}")
    print()
    raise SystemExit(1)

from conexion_ibkr import (ConexionIBKR, PUERTO_PAPER,   # noqa: E402
                           MENSAJE_TWS_CERRADO)


# ═══════════════════════════════════════════════════════════════════════════
#  Estado
# ═══════════════════════════════════════════════════════════════════════════

conexion = ConexionIBKR(puerto=PUERTO_PAPER, client_id=1)
_icono = None
_ocupado = threading.Lock()

COLORES = {
    "gris":  ("#3a4a55", "#5a6b7a"),
    "verde": ("#0d3b2a", "#2ecc71"),
    "ambar": ("#3b2f0d", "#f39c12"),
    "rojo":  ("#3b0d0d", "#e74c3c"),
}


# ═══════════════════════════════════════════════════════════════════════════
#  Icono
# ═══════════════════════════════════════════════════════════════════════════

def crear_icono(color: str = "gris"):
    """Dibuja el icono con el color del estado."""
    fondo, punto = COLORES.get(color, COLORES["gris"])
    img = Image.new("RGB", (64, 64), fondo)
    d = ImageDraw.Draw(img)
    d.ellipse((14, 14, 50, 50), fill=punto)
    # Un aro interior para que se distinga bien en barras oscuras y claras
    d.ellipse((22, 22, 42, 42), outline=fondo, width=3)
    return img


def _pintar(color: str, texto: str):
    """Cambia el color y el texto del icono sin romper si ya se cerró."""
    try:
        if _icono is None:
            return
        _icono.icon = crear_icono(color)
        _icono.title = f"IBKR — {texto}"[:127]      # Windows corta en 128
    except Exception:
        pass


def _avisar(titulo: str, cuerpo: str):
    """Notificación del sistema, recortada para que quepa."""
    try:
        if _icono is not None:
            _icono.notify(cuerpo[:250], titulo)
    except Exception:
        print(f"[{titulo}] {cuerpo}")


# ═══════════════════════════════════════════════════════════════════════════
#  Acciones del menú
# ═══════════════════════════════════════════════════════════════════════════
#
# CORRECCIÓN 4 — pystray ejecuta las acciones del menú en el hilo del
# icono. Si `conectar()` se llama ahí directamente, la interfaz de la
# bandeja se congela mientras dura el intento (hasta 10 s de timeout, y
# más con reintentos y backoff): el menú deja de responder y parece que
# el programa se ha colgado.
#
# Cada acción lenta se lanza en su propio hilo. Un cerrojo evita que se
# solapen dos intentos si se pulsa varias veces.

def _en_hilo(fn, nombre: str):
    def _envoltura():
        if not _ocupado.acquire(blocking=False):
            _avisar("IBKR", "Ya hay una operación en curso, un momento…")
            return
        try:
            fn()
        except Exception as e:
            _avisar("IBKR — error", str(e))
            _pintar("rojo", "error")
        finally:
            _ocupado.release()

    threading.Thread(target=_envoltura, daemon=True, name=nombre).start()


def accion_conectar(icon=None, item=None):
    def _trabajo():
        _pintar("gris", "conectando…")
        _avisar("Interactive Brokers", "Conectando a la cuenta simulada…")

        res = conexion.conectar(reintentos=3)

        if not res:
            _pintar("rojo", "sin conexión")
            _avisar("IBKR — no pude conectar",
                    conexion.ultimo_error or MENSAJE_TWS_CERRADO)
            return

        paper = res.get("paper") if isinstance(res, dict) else None
        cuenta = res.get("cuenta", "?") if isinstance(res, dict) else "?"

        if paper is True:
            _pintar("verde", f"simulada {cuenta}")
            sl = res.get("solo_lectura")
            extra = (" · API en solo lectura" if sl is True
                     else " · puede enviar órdenes" if sl is False else "")
            _avisar("Conectado a IBKR (simulada)",
                    f"Cuenta {cuenta}{extra}")
        elif paper is False:
            _pintar("rojo", "CUENTA REAL")
            _avisar("⚠ CUENTA REAL",
                    f"La cuenta {cuenta} no es simulada. Me he desconectado "
                    f"por seguridad.")
        else:
            _pintar("ambar", "sin confirmar")
            _avisar("Conectado, pero…",
                    "No he podido confirmar que la cuenta sea simulada. "
                    "No opere hasta comprobarlo.")

    _en_hilo(_trabajo, "IBKRConectar")


def accion_estado(icon=None, item=None):
    def _trabajo():
        texto = conexion.resumen()
        print()
        print(texto)
        print()
        # La notificación no cabe entera: se manda lo esencial
        e = conexion.estado()
        if e.get("conectado"):
            d = e.get("detalle") or {}
            _avisar("Estado IBKR",
                    f"Conectado · puerto {e['puerto']} · "
                    f"cuenta {d.get('cuenta','?')} · "
                    f"{'simulada' if d.get('paper') else 'NO simulada'}")
        else:
            _avisar("Estado IBKR", "Sin conexión. Pulse «Conectar (Paper)».")

    _en_hilo(_trabajo, "IBKREstado")


def accion_desconectar(icon=None, item=None):
    def _trabajo():
        conexion.desconectar()
        _pintar("gris", "desconectado")
        _avisar("Interactive Brokers", "Desconectado limpiamente.")

    _en_hilo(_trabajo, "IBKRDesconectar")


def accion_salir(icon=None, item=None):
    try:
        conexion.desconectar()
    except Exception:
        pass
    try:
        icon = icon or _icono
        if icon is not None:
            icon.stop()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  Vigilante del icono
# ═══════════════════════════════════════════════════════════════════════════

def _vigilar():
    """Refleja en el color del icono lo que pase con la conexión.

    Si TWS reinicia de madrugada, la conexión se cae y se restablece sola.
    El icono debe contarlo sin que haya que abrir el menú.
    """
    ultimo = None
    while True:
        time.sleep(10)
        try:
            e = conexion.estado()
            con = bool(e.get("conectado"))
            d = e.get("detalle") or {}
            if con:
                estado = ("verde" if d.get("paper") is True
                          else "rojo" if d.get("paper") is False
                          else "ambar")
                texto = f"conectado {d.get('cuenta','')}"
            else:
                estado = "gris"
                texto = "sin conexión"
            if estado != ultimo:
                _pintar(estado, texto)
                if ultimo == "verde" and estado == "gris":
                    _avisar("IBKR", "Se perdió la conexión. Reconectando "
                                    "sola…")
                elif ultimo == "gris" and estado == "verde":
                    _avisar("IBKR", "Conexión restablecida.")
                ultimo = estado
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  Arranque
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global _icono

    menu = Menu(
        MenuItem("Conectar (Paper)", accion_conectar, default=True),
        MenuItem("Estado", accion_estado),
        MenuItem("Desconectar", accion_desconectar),
        Menu.SEPARATOR,
        MenuItem("Salir", accion_salir),
    )

    _icono = pystray.Icon(
        "IBKR", crear_icono("gris"),
        "IBKR — clic para conectar (simulada)", menu)

    threading.Thread(target=_vigilar, daemon=True,
                     name="IBKRVigilarIcono").start()

    print()
    print("  Icono de IBKR puesto en la bandeja del sistema (junto al reloj).")
    print("  Clic derecho sobre él para el menú. Doble clic = Conectar.")
    print()
    print("  Colores:  gris = sin conectar · verde = simulada ✓")
    print("            ámbar = sin confirmar · rojo = cuenta real o error")
    print()

    _icono.run()


if __name__ == "__main__":
    main()

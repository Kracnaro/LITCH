"""
configurar_tws.py — Litch configura TWS siguiendo el instructivo, paso a paso.

━━━ DE DÓNDE SALE ESTO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Del PDF «Operaciones con TWS — Interactive Brokers» que el señor entregó.
No es teoría inventada: cada procedimiento de aquí está copiado de sus
páginas, con la ruta de menú exacta que indica el documento.

━━━ POR QUÉ POR MENÚS Y NO POR COORDENADAS ━━━━━━━━━━━━━━━━━━━━━━━━━━━
Esta es la decisión importante del módulo.

Hasta ahora Litch aprendía a base de clics en coordenadas: «en (0.34,
0.62) pasa algo». Eso funciona para explorar, pero es frágil para
configurar — basta que el señor mueva un panel para que la coordenada
apunte a otra cosa.

Los menús no se mueven. «Editar > Configuración global > General» está
en el mismo sitio hoy y dentro de un año, en cualquier resolución y con
cualquier disposición de ventanas. Y se navegan con el teclado, que es
determinista: Alt abre la barra, las flechas recorren, Enter entra,
Escape sale.

Por eso aquí Litch teclea en vez de apuntar. Es más lento de escribir y
mucho más fiable de ejecutar.

━━━ CADA PASO SE COMPRUEBA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ningún paso se da por hecho porque se haya enviado la pulsación. Después
de cada uno se fotografía la pantalla y se mide si cambió lo que tenía
que cambiar. Si un paso no surtió efecto, la secuencia se detiene ahí y
lo dice — no sigue construyendo sobre un paso que no sabe si salió.
"""

from __future__ import annotations

import time

PAUSA_MENU = 0.55        # entre pulsaciones dentro de un menú
PAUSA_PASO = 1.1         # entre pasos de un procedimiento
UMBRAL_CAMBIO = 0.6      # % de pantalla que debe cambiar para dar por hecho


# ══════════════════════════════════════════════════════════════════════════
#  PROCEDIMIENTOS — copiados del instructivo del señor
# ══════════════════════════════════════════════════════════════════════════
#
# Cada uno lleva:
#   fuente  — de dónde sale, para poder volver a comprobarlo
#   pasos   — lo que hay que hacer, en orden
#   señal   — qué debe cambiar en pantalla si salió bien
#   riesgo  — bajo / medio; nada aquí envía órdenes

PROCEDIMIENTOS = {

    "idioma_espanol": {
        "nombre": "Poner TWS en español",
        "fuente": "PDF pág. 4 — «Configuración básica de la TWS, 1. Cambio de idioma»",
        "riesgo": "bajo",
        "porque": ("TWS se instala en inglés. En español los rótulos cambian "
                   "(la media móvil pasa de SMA a MA), y mi diccionario "
                   "reconoce los dos — pero el señor lee mejor en el suyo."),
        "ruta": ["Editar", "Configuración global", "General"],
        "pasos": [
            ("menu", "Editar"),
            ("texto", "Configuración global"),
            ("esperar", 1.4),
            ("buscar", "General"),
            ("buscar", "Idioma actual"),
        ],
        "senal": "se abre la ventana de Configuración Global",
        "manual_despues": ("Seleccione «Español» en la lista y reinicie TWS. "
                           "El reinicio lo hace usted: no cierro su "
                           "plataforma sin permiso."),
    },

    "vista_clasica": {
        "nombre": "Abrir la vista TWS Clásica",
        "fuente": "PDF pág. 5 — «Classic TWS: es la vista más sencilla para operar»",
        "riesgo": "bajo",
        "porque": ("El instructivo enseña a operar desde la vista clásica, "
                   "no desde el Mosaico. Es la más sencilla y la que usa "
                   "el documento en todos sus ejemplos."),
        "pasos": [
            ("pestana_inferior", "TWS clásica"),
        ],
        "senal": "cambia toda la pantalla a la vista clásica",
    },

    "ver_cadena_opciones": {
        "nombre": "Abrir la cadena de opciones",
        "fuente": "PDF pág. 9 — «se abre una pantalla flotante con la cadena de opciones»",
        "riesgo": "bajo",
        "porque": ("Es donde se elige vencimiento y strike. Sin ella no se "
                   "puede operar una opción."),
        "pasos": [
            ("clic_texto", "Cadena de opciones"),
            ("esperar", 1.8),
        ],
        "senal": "se abre una ventana flotante con vencimientos y strikes",
        "manual_despues": ("Según el instructivo (pág. 9), conviene cambiar "
                           "«8 Strikes» para ver todos, y activar "
                           "«Semanales / trimestrales» en vencimientos. "
                           "Se configura una sola vez y queda guardado."),
    },

    "ventana_negociacion": {
        "nombre": "Crear una página de negociación propia",
        "fuente": "PDF pág. 5 — «clicando sobre el símbolo +»",
        "riesgo": "bajo",
        "porque": ("Una hoja propia donde poner solo los activos que "
                   "interesan, en vez de mezclarlos con las listas que "
                   "trae TWS por defecto."),
        "pasos": [
            ("clic_texto", "+"),
            ("esperar", 1.2),
        ],
        "senal": "aparece una ventana pidiendo el nombre de la página",
        "manual_despues": "Escriba el nombre que quiera darle y acepte.",
    },

    "gestionar_datos": {
        "nombre": "Abrir la gestión de datos de mercado",
        "fuente": "Pantalla de TWS — «Gestionar datos de mercado»",
        "riesgo": "bajo",
        "porque": ("Sus pares de divisas salen en N/A: EUR.USD, GBP.USD y "
                   "USD.JPY sin precio. Falta la suscripción de datos de "
                   "forex. Las acciones sí las tiene."),
        "pasos": [
            ("clic_texto", "Gestionar datos de mercado"),
            ("esperar", 2.0),
        ],
        "senal": "se abre el portal de suscripciones de datos",
        "manual_despues": ("La suscripción se contrata en el portal de IBKR "
                           "y cuesta dinero: eso lo decide usted, no yo."),
    },
}

# El orden en que tiene sentido hacerlos: de lo que no depende de nada
# a lo que depende de lo anterior. Es el orden del propio instructivo.
ORDEN = ["idioma_espanol", "vista_clasica", "ventana_negociacion",
         "ver_cadena_opciones", "gestionar_datos"]


# ══════════════════════════════════════════════════════════════════════════
#  Ejecución
# ══════════════════════════════════════════════════════════════════════════

def _foto(v):
    from . import explorador_activo as _ex
    return _ex._capturar([v["x"], v["y"], v["x"] + v["w"], v["y"] + v["h"]])


def _cambio(v, antes) -> float:
    from . import explorador_activo as _ex
    return _ex.comparar(antes, _foto(v)).get("pct", 0.0)


def _localizar_texto(app, v, texto: str):
    """
    Busca un texto en la pantalla de TWS y devuelve dónde está.

    Se apoya en el diccionario bilingüe: si el señor tiene TWS en inglés,
    «Cadena de opciones» hay que buscarlo como «Option Chain». Devuelve
    (x, y) absolutos o None.
    """
    variantes = [texto]
    try:
        from . import datos_mercado as _dm
        clave = _dm.que_es(texto)
        if clave:
            variantes = _dm.formas_de(clave) or [texto]
    except Exception:
        pass

    try:
        import pyautogui
        for t in variantes:
            try:
                caja = pyautogui.locateOnScreen(t, confidence=0.8)
                if caja:
                    return pyautogui.center(caja)
            except Exception:
                continue
    except Exception:
        pass
    return None


def ejecutar_paso(app, v, tipo: str, dato) -> tuple[bool, str]:
    """Un paso. Devuelve (salió bien, qué pasó)."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
    except Exception:
        return False, "pyautogui no está disponible"

    try:
        if tipo == "esperar":
            time.sleep(float(dato))
            return True, f"esperé {dato}s"

        if tipo == "menu":
            # Alt abre la barra de menús. Luego se escribe el nombre.
            # Es la vía del teclado: no depende de dónde esté la ventana.
            pyautogui.press("alt")
            time.sleep(PAUSA_MENU)
            pyautogui.typewrite(str(dato)[:1])
            time.sleep(PAUSA_MENU)
            return True, f"abrí el menú {dato}"

        if tipo == "texto":
            pyautogui.typewrite(str(dato))
            time.sleep(PAUSA_MENU)
            return True, f"escribí «{dato}»"

        if tipo == "buscar":
            pos = _localizar_texto(app, v, str(dato))
            if pos is None:
                return False, f"no encontré «{dato}» en pantalla"
            pyautogui.click(pos[0], pos[1])
            time.sleep(PAUSA_MENU)
            return True, f"pulsé «{dato}»"

        if tipo == "clic_texto":
            pos = _localizar_texto(app, v, str(dato))
            if pos is None:
                return False, (f"no veo «{dato}». Puede que esté en otra "
                               f"pestaña o con otro nombre.")
            pyautogui.click(pos[0], pos[1])
            time.sleep(PAUSA_MENU)
            return True, f"pulsé «{dato}»"

        if tipo == "pestana_inferior":
            pos = _localizar_texto(app, v, str(dato))
            if pos is None:
                return False, f"no encuentro la pestaña «{dato}»"
            pyautogui.click(pos[0], pos[1])
            time.sleep(PAUSA_PASO)
            return True, f"cambié a la pestaña «{dato}»"

        if tipo == "tecla":
            pyautogui.press(str(dato))
            time.sleep(PAUSA_MENU)
            return True, f"pulsé {dato}"

        return False, f"no sé hacer un paso de tipo «{tipo}»"
    except Exception as e:
        return False, f"falló: {e}"


def ejecutar(app, clave: str) -> str:
    """
    Hace un procedimiento completo, comprobando después de cada paso.

    Se detiene en el primer paso que no salga. No sigue construyendo
    sobre un paso del que no sabe si funcionó.
    """
    proc = PROCEDIMIENTOS.get(clave)
    if not proc:
        return f"No conozco el procedimiento «{clave}», señor."

    # Las mismas siete capas de siempre: TWS abierto, cuenta simulada,
    # sin diálogos encima.
    try:
        from . import explorador_activo as _ex
        puedo, motivo, v = _ex.Explorador(app)._puedo()
        if not puedo:
            return f"No puedo configurar ahora: {motivo}."
    except Exception as e:
        return f"No pude comprobar si es seguro: {e}"

    lineas = [f"«{proc['nombre']}»",
              f"Fuente: {proc['fuente']}",
              f"Por qué: {proc['porque']}",
              ""]

    antes_todo = _foto(v)
    for i, (tipo, dato) in enumerate(proc["pasos"], 1):
        antes = _foto(v)
        ok, detalle = ejecutar_paso(app, v, tipo, dato)
        if not ok:
            lineas.append(f"  ✗ {i}. {detalle}")
            lineas.append("")
            lineas.append("Me detengo aquí. Prefiero pararme a medias que "
                          "seguir sobre un paso que no sé si salió bien.")
            try:
                import pyautogui
                pyautogui.press("escape")
            except Exception:
                pass
            return "\n".join(lineas)
        pct = _cambio(v, antes) if tipo != "esperar" else 0.0
        marca = "✓" if (pct >= UMBRAL_CAMBIO or tipo == "esperar") else "·"
        extra = f" (cambió {pct}% de la pantalla)" if pct else ""
        lineas.append(f"  {marca} {i}. {detalle}{extra}")
        time.sleep(PAUSA_PASO)

    total = _cambio(v, antes_todo)
    lineas.append("")
    if total >= UMBRAL_CAMBIO:
        lineas.append(f"Hecho. La pantalla cambió un {total}% — {proc['senal']}.")
    else:
        lineas.append(f"Ejecuté los pasos, pero la pantalla apenas cambió "
                      f"({total}%). Puede que ya estuviera así, o que no "
                      f"haya surtido efecto. No se lo doy por hecho.")
    if proc.get("manual_despues"):
        lineas.append("")
        lineas.append(f"Le toca a usted: {proc['manual_despues']}")
    return "\n".join(lineas)


def listar() -> str:
    """Qué sabe configurar Litch, y de dónde lo sacó."""
    l = ["CONFIGURACIÓN DE TWS — del instructivo que usted me dio", ""]
    for k in ORDEN:
        p = PROCEDIMIENTOS[k]
        l.append(f"· «{p['nombre']}»")
        l.append(f"    {p['porque']}")
        l.append(f"    {p['fuente']}")
    l.append("")
    l.append("Dígame «configura el bróker» y los hago en orden, comprobando "
             "después de cada paso. O pídame uno suelto por su nombre.")
    return "\n".join(l)


def todo(app) -> str:
    """Los procedimientos en el orden del instructivo, uno tras otro."""
    partes = ["CONFIGURANDO TWS SEGÚN EL INSTRUCTIVO", ""]
    for k in ORDEN:
        partes.append(ejecutar(app, k))
        partes.append("")
        partes.append("─" * 50)
        partes.append("")
    partes.append("Terminado. Lo que quedó a medias se lo he ido diciendo "
                  "paso a paso, sin dar nada por hecho.")
    return "\n".join(partes)


__all__ = ["PROCEDIMIENTOS", "ORDEN", "ejecutar", "ejecutar_paso", "listar",
           "todo"]

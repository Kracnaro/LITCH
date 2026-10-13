"""
conciencia_pantalla.py — Litch VE TODA la pantalla y entiende qué hay en ella.

Hasta ahora Litch miraba por una rendija: la región del gráfico. Este módulo
le da conciencia completa de lo que ocurre en el monitor.

QUÉ APORTA, Y POR QUÉ CADA COSA IMPORTA
───────────────────────────────────────
  1. INVENTARIO DE VENTANAS — sabe qué programas están abiertos, cuál está
     al frente y cuál tapa a cuál.

  2. DETECCIÓN DE DIÁLOGOS — la causa nº1 de que una automatización falle es
     un cuadro de diálogo que aparece encima ("¿Confirma la orden?", un aviso
     de riesgo, una actualización). Si Litch no lo ve, hace clic al vacío o,
     peor, sobre un botón que no esperaba. Aquí lo detecta y SE DETIENE.

  3. MAPA DE PANELES DE TWS — divide la ventana en sus zonas reales
     (gráfico, cartera, órdenes, watchlist, ticket) y analiza cada una.

  4. SEGUNDA CONFIRMACIÓN DE CUENTA SIMULADA — el título dice DU..., pero
     el título se puede leer mal. La franja de color de "negociación
     simulada" es una prueba visual independiente. Dos confirmaciones que
     no dependen entre sí valen mucho más que una repetida.

  5. MEMORIA VISUAL — recuerda cómo se veía la pantalla y detecta qué
     cambió. Aprende qué zonas son estables (menús) y cuáles vivas (precios).

FILOSOFÍA HONESTA SOBRE LOS NÚMEROS
───────────────────────────────────
La visión sirve para entender la DISPOSICIÓN: qué hay, dónde, si algo
estorba. Para los NÚMEROS (precio, saldo, posiciones) la fuente correcta es
la API de IBKR, que los da exactos. Leer cifras de píxeles es adivinar con
estilo. Litch usa cada herramienta para lo que sirve.
"""

from __future__ import annotations

import json
import os
import time

try:
    import numpy as np
    _NP_OK = True
except Exception:
    _NP_OK = False

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA_MAPA = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "mapa_pantalla.json")


# ═══════════════════════════════════════════════════════════════════════════
#  1. INVENTARIO DE VENTANAS
# ═══════════════════════════════════════════════════════════════════════════

# Programas que a Litch le interesa reconocer por nombre
_CONOCIDOS = {
    "trader workstation": "Interactive Brokers TWS",
    "interactive brokers": "Interactive Brokers",
    "ib gateway": "IB Gateway",
    "iq option": "IQ Option",
    "chrome": "Google Chrome",
    "firefox": "Firefox",
    "edge": "Microsoft Edge",
    "excel": "Excel",
    "notepad": "Bloc de notas",
    "litch": "Litch (yo mismo)",
    "tradingview": "TradingView",
}


def listar_ventanas(min_area: int = 40_000) -> list[dict]:
    """Todas las ventanas visibles con su posición, tamaño y orden.

    El orden de EnumWindows va de la de más al frente hacia atrás, así que
    el índice indica quién tapa a quién.
    """
    ventanas: list[dict] = []
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        try:
            frente = u32.GetForegroundWindow()
        except Exception:
            frente = None

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _lp):
            try:
                if not u32.IsWindowVisible(hwnd):
                    return True
                n = u32.GetWindowTextLengthW(hwnd)
                if n == 0:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, buf, n + 1)
                titulo = (buf.value or "").strip()
                if not titulo:
                    return True
                rect = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w <= 0 or h <= 0 or w * h < min_area:
                    return True
                tl = titulo.lower()
                app = next((v for k, v in _CONOCIDOS.items() if k in tl), None)
                ventanas.append({
                    "titulo": titulo[:120],
                    "programa": app,
                    "x": rect.left, "y": rect.top, "w": w, "h": h,
                    "area": w * h,
                    "al_frente": (hwnd == frente),
                    "orden": len(ventanas),
                })
            except Exception:
                pass
            return True

        u32.EnumWindows(_cb, 0)
    except Exception:
        pass
    return ventanas


def tamano_pantalla() -> tuple[int, int]:
    """Resolución del monitor principal."""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        return int(u32.GetSystemMetrics(0)), int(u32.GetSystemMetrics(1))
    except Exception:
        return 1920, 1080


# ═══════════════════════════════════════════════════════════════════════════
#  2. DETECCIÓN DE DIÁLOGOS QUE ESTORBAN
# ═══════════════════════════════════════════════════════════════════════════

# Palabras que delatan un cuadro de diálogo (español e inglés)
_PISTAS_DIALOGO = (
    "confirm", "confirmar", "confirmación", "warning", "advertencia",
    "aviso", "alert", "alerta", "error", "atención", "attention",
    "precaución", "caution", "risk", "riesgo", "acepta", "accept",
    "terms", "términos", "update", "actualiz", "login", "iniciar sesión",
    "password", "contraseña", "authenticat", "verif", "message", "mensaje",
    "order confirmation", "confirmación de orden", "disclaimer",
)


def detectar_dialogo(app=None) -> dict:
    """¿Hay un cuadro de diálogo encima de TWS?

    Un diálogo modal es la trampa clásica de la automatización: la ventana
    principal sigue ahí, las coordenadas siguen calculándose bien, pero los
    clics van a parar a un sitio que ya no hace lo que se espera.

    Devuelve {"hay": bool, "ventanas": [...], "mensaje": str}
    """
    from . import vision_tws as _vt

    r = {"hay": False, "ventanas": [], "mensaje": ""}
    tws = _vt.ventana_tws()
    if not tws:
        r["mensaje"] = "No veo TWS abierto."
        return r

    area_tws = max(1, tws["w"] * tws["h"])
    sospechosas = []

    for v in listar_ventanas(min_area=15_000):
        tl = v["titulo"].lower()
        # La propia TWS no cuenta
        if any(k in tl for k in ("trader workstation", "interactive brokers")) \
                and v["area"] > area_tws * 0.5:
            continue
        if v["programa"] == "Litch (yo mismo)":
            continue

        # ¿Se solapa con TWS?
        sx = max(0, min(v["x"] + v["w"], tws["x"] + tws["w"]) - max(v["x"], tws["x"]))
        sy = max(0, min(v["y"] + v["h"], tws["y"] + tws["h"]) - max(v["y"], tws["y"]))
        solape = sx * sy
        if solape <= 0:
            continue

        pct = solape / max(1, v["area"])
        pequena = v["area"] < area_tws * 0.55      # típico de un diálogo
        por_texto = any(p in tl for p in _PISTAS_DIALOGO)

        # Un diálogo: encima de TWS, más pequeño, y al frente o con
        # palabras delatoras en el título.
        if pct > 0.55 and pequena and (v["al_frente"] or por_texto):
            v["motivo"] = ("título de aviso" if por_texto
                           else "ventana pequeña al frente sobre TWS")
            sospechosas.append(v)

    if sospechosas:
        r["hay"] = True
        r["ventanas"] = sospechosas
        nombres = "; ".join(f"«{s['titulo'][:60]}»" for s in sospechosas[:3])
        r["mensaje"] = (
            f"⚠ Hay {len(sospechosas)} ventana(s) encima de TWS: {nombres}. "
            f"No voy a hacer clic con algo de por medio: podría pulsar lo que "
            f"no es. Ciérrela o respóndala usted y volvemos.")
    else:
        r["mensaje"] = "Nada estorba encima de TWS. Camino libre."
    return r


# ═══════════════════════════════════════════════════════════════════════════
#  3. MAPA DE PANELES DE TWS
# ═══════════════════════════════════════════════════════════════════════════

# Zonas del layout Mosaico, en proporciones de la ventana.
# Son un punto de partida: se afinan con lo que Litch observa.
PANELES = {
    "barra_titulo":  {"r": (0.00, 0.00, 1.00, 0.05),
                      "que": "Título y cuenta. Aquí leo si es DU (simulada)."},
    "menu":          {"r": (0.00, 0.05, 1.00, 0.10),
                      "que": "Menús: Archivo, Editar, Cuenta, Operaciones."},
    "watchlist":     {"r": (0.00, 0.10, 0.22, 0.72),
                      "que": "Lista de activos vigilados con sus precios."},
    "ticket":        {"r": (0.00, 0.10, 0.22, 0.30),
                      "que": "Entrada de órdenes: símbolo, cantidad, enviar."},
    "grafico":       {"r": (0.23, 0.28, 0.64, 0.72),
                      "que": "El gráfico de velas. Aquí leo la tendencia."},
    "profundidad":   {"r": (0.65, 0.10, 1.00, 0.45),
                      "que": "Libro de órdenes y profundidad de mercado."},
    "noticias":      {"r": (0.65, 0.45, 1.00, 0.72),
                      "que": "Noticias y datos del activo."},
    "cartera":       {"r": (0.00, 0.72, 0.60, 0.93),
                      "que": "Sus posiciones abiertas y el resultado de cada una."},
    "ordenes":       {"r": (0.60, 0.72, 1.00, 0.93),
                      "que": "Órdenes activas y ejecutadas."},
    "pie":           {"r": (0.00, 0.93, 1.00, 1.00),
                      "que": "Barra de estado: conexión, hora del servidor."},
}


def region_panel(ventana: dict, nombre: str) -> list | None:
    """Coordenadas de pantalla de un panel de TWS."""
    p = PANELES.get(nombre)
    if not p or not ventana:
        return None
    x1, y1, x2, y2 = p["r"]
    return [int(ventana["x"] + ventana["w"] * x1),
            int(ventana["y"] + ventana["h"] * y1),
            int(ventana["x"] + ventana["w"] * x2),
            int(ventana["y"] + ventana["h"] * y2)]


def analizar_panel(region: list) -> dict:
    """Estadísticas visuales de un panel: brillo, color, densidad.

    No lee texto: describe el CARÁCTER de la zona. Con eso Litch distingue
    un panel vacío de uno lleno, una zona quieta de una que cambia, y una
    región con predominio verde (ganancia) o rojo (pérdida).
    """
    from . import vision as _vis

    res = {"ok": False, "brillo": 0.0, "verde": 0.0, "rojo": 0.0,
           "densidad": 0.0, "vacio": True}
    if not _NP_OK or not region:
        return res
    img = _vis.capturar(region)
    if img is None or img.size == 0:
        return res
    try:
        arr = img.astype("float32")
        b, g, r = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        total = max(1, arr.shape[0] * arr.shape[1])

        res["brillo"] = round(float(arr.mean()) / 255.0, 3)
        # Verde/rojo dominantes: sirven para P&L y velas
        m_verde = (g > b + 25) & (g > r + 25)
        m_rojo = (r > g + 25) & (r > b + 15)
        res["verde"] = round(float(m_verde.sum()) / total, 4)
        res["rojo"] = round(float(m_rojo.sum()) / total, 4)
        # Densidad: cuánta variación hay (texto y bordes la suben)
        gris = arr.mean(axis=2)
        res["densidad"] = round(float(gris.std()) / 128.0, 3)
        res["vacio"] = res["densidad"] < 0.06
        res["ok"] = True
    except Exception:
        pass
    return res


def franja_simulada(ventana: dict) -> dict:
    """Busca la franja de color que TWS muestra en negociación simulada.

    SEGUNDA CONFIRMACIÓN, independiente del título. Que dos pruebas que no
    dependen la una de la otra digan lo mismo es mucho más fiable que
    repetir la misma prueba dos veces.

    Es evidencia corroborante, NO prueba por sí sola: los colores dependen
    del tema visual que use TWS. Por eso su ausencia no afirma nada.
    """
    r = {"detectada": False, "confianza": 0.0, "nota": ""}
    if not _NP_OK or not ventana:
        return r
    from . import vision as _vis

    banda = [ventana["x"],
             ventana["y"],
             ventana["x"] + ventana["w"],
             ventana["y"] + int(ventana["h"] * 0.075)]
    img = _vis.capturar(banda)
    if img is None or img.size == 0:
        return r
    try:
        arr = img.astype("float32")
        b, g, rr = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        total = max(1, arr.shape[0] * arr.shape[1])
        # TWS simulada usa tonos cálidos saturados (rojo/ámbar)
        calido = ((rr > 110) & (rr > b + 45) & (g < rr - 20))
        frac = float(calido.sum()) / total
        r["confianza"] = round(frac, 3)
        if frac > 0.22:
            r["detectada"] = True
            r["nota"] = ("Veo la franja cálida típica de negociación "
                         "simulada en la parte superior.")
        else:
            r["nota"] = ("No distingo la franja de simulación. Puede ser el "
                         "tema visual de TWS: no concluyo nada por esto solo.")
    except Exception:
        pass
    return r


# ═══════════════════════════════════════════════════════════════════════════
#  4. LEER TODA LA PANTALLA Y CONTARLO
# ═══════════════════════════════════════════════════════════════════════════

def leer_pantalla(app) -> dict:
    """Radiografía completa de lo que hay en el monitor ahora mismo."""
    from . import vision_tws as _vt

    info = {"ts": time.time(), "ventanas": [], "tws": None, "paneles": {},
            "dialogo": None, "franja": None, "resolucion": tamano_pantalla()}

    info["ventanas"] = listar_ventanas()
    tws = _vt.ventana_tws()
    info["tws"] = tws
    if not tws:
        return info

    info["dialogo"] = detectar_dialogo(app)
    info["franja"] = franja_simulada(tws)

    for nombre in PANELES:
        reg = region_panel(tws, nombre)
        if reg:
            a = analizar_panel(reg)
            a["region"] = reg
            info["paneles"][nombre] = a
    return info


def describir_pantalla(app) -> str:
    """Litch cuenta en voz alta qué está viendo. En castellano llano."""
    info = leer_pantalla(app)
    w, h = info["resolucion"]
    partes = [f"Veo su pantalla completa, {w}×{h}."]

    # Ventanas abiertas
    conocidas = [v for v in info["ventanas"] if v.get("programa")]
    if conocidas:
        nombres = []
        for v in conocidas[:6]:
            nombres.append(v["programa"] + (" (al frente)" if v["al_frente"] else ""))
        partes.append("Programas que reconozco: " + ", ".join(nombres) + ".")
    partes.append(f"En total hay {len(info['ventanas'])} ventanas visibles.")

    tws = info["tws"]
    if not tws:
        partes.append("No veo Trader Workstation. Sin él no puedo trabajar "
                      "en Interactive Brokers.")
        return " ".join(partes)

    partes.append(f"Trader Workstation ocupa {tws['w']}×{tws['h']} píxeles y "
                  + ("está al frente." if tws.get("al_frente")
                     else "está detrás de otra ventana."))

    # Diálogos: lo más importante
    d = info.get("dialogo") or {}
    if d.get("hay"):
        partes.append(d["mensaje"])
    else:
        partes.append("No hay diálogos encima estorbando.")

    # Paneles
    pl = info["paneles"]
    vivos = [n for n, a in pl.items() if a.get("ok") and not a.get("vacio")]
    vacios = [n for n, a in pl.items() if a.get("ok") and a.get("vacio")]
    if vivos:
        partes.append("Paneles con contenido: " + ", ".join(vivos) + ".")
    if vacios:
        partes.append("Paneles que veo vacíos: " + ", ".join(vacios) +
                      " — puede que su distribución sea distinta a la que "
                      "supongo, dígame 'aprende mi distribución de TWS'.")

    # Cartera en verde o rojo: la lectura que más le importa al usuario
    cart = pl.get("cartera") or {}
    if cart.get("ok") and not cart.get("vacio"):
        v, r = cart.get("verde", 0), cart.get("rojo", 0)
        if v > r * 1.6 and v > 0.01:
            partes.append("En su cartera domina el verde: parece que hay más "
                          "ganancia que pérdida ahora mismo.")
        elif r > v * 1.6 and r > 0.01:
            partes.append("En su cartera domina el rojo: parece que hay más "
                          "pérdida que ganancia ahora mismo.")
        partes.append("Eso lo digo por el color; para la cifra exacta "
                      "consulto la API, que no se equivoca.")

    # Confirmación visual de cuenta simulada
    f = info.get("franja") or {}
    if f.get("detectada"):
        partes.append(f["nota"])

    return " ".join(partes)


# ═══════════════════════════════════════════════════════════════════════════
#  5. MEMORIA VISUAL: qué cambia y qué no
# ═══════════════════════════════════════════════════════════════════════════

def _cargar_mapa() -> dict:
    try:
        with open(_RUTA_MAPA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"observaciones": 0, "paneles": {}, "actualizado": ""}


def _guardar_mapa(mapa: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_RUTA_MAPA), exist_ok=True)
        mapa["actualizado"] = time.strftime("%Y-%m-%d %H:%M:%S")
        tmp = _RUTA_MAPA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mapa, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _RUTA_MAPA)
    except Exception:
        pass


def observar_y_aprender(app) -> str:
    """Una observación: mide cada panel y actualiza lo que Litch sabe.

    Con el tiempo aprende qué zonas están vivas (precios que cambian) y
    cuáles quietas (menús). Eso le dice dónde mirar cuando tenga prisa.
    """
    info = leer_pantalla(app)
    if not info["tws"]:
        return "No veo TWS abierto, señor. Sin ventana no hay nada que aprender."

    mapa = _cargar_mapa()
    mapa["observaciones"] = int(mapa.get("observaciones", 0)) + 1
    pmap = mapa.setdefault("paneles", {})

    cambios = []
    for nombre, a in info["paneles"].items():
        if not a.get("ok"):
            continue
        p = pmap.setdefault(nombre, {"n": 0, "brillo": [], "densidad": [],
                                     "vacio_veces": 0, "que": PANELES[nombre]["que"]})
        p["n"] += 1
        # Media móvil corta: recordar sin acumular basura
        for clave in ("brillo", "densidad"):
            serie = p.setdefault(clave, [])
            serie.append(a.get(clave, 0.0))
            if len(serie) > 40:
                del serie[:-40]
        if a.get("vacio"):
            p["vacio_veces"] = p.get("vacio_veces", 0) + 1

        # ¿Esta zona cambia o está quieta?
        serie = p.get("densidad", [])
        if len(serie) >= 8:
            try:
                m = sum(serie) / len(serie)
                var = sum((x - m) ** 2 for x in serie) / len(serie)
                p["actividad"] = round(var ** 0.5, 4)
                p["tipo"] = "viva" if p["actividad"] > 0.012 else "quieta"
            except Exception:
                pass

    # Detectar paneles que siempre salen vacíos: la distribución no coincide
    sospechosos = [n for n, p in pmap.items()
                   if p.get("n", 0) >= 6
                   and p.get("vacio_veces", 0) / max(1, p["n"]) > 0.85]
    if sospechosos:
        mapa["paneles_dudosos"] = sospechosos
        cambios.append("paneles que nunca tienen contenido: " +
                       ", ".join(sospechosos))

    _guardar_mapa(mapa)

    n = mapa["observaciones"]
    vivas = [x for x, p in pmap.items() if p.get("tipo") == "viva"]
    txt = f"Observación {n} registrada."
    if vivas:
        txt += (" Zonas donde detecto movimiento constante: " +
                ", ".join(vivas) + " — ahí es donde vale la pena mirar.")
    if cambios:
        txt += " Aviso: " + "; ".join(cambios) + "."
    if n < 10:
        txt += (f" Llevo {n} de 10 observaciones para tener una idea firme "
                f"de su distribución.")
    return txt


def resumen_aprendido() -> str:
    """Lo que Litch ha aprendido mirando la pantalla."""
    mapa = _cargar_mapa()
    n = mapa.get("observaciones", 0)
    if not n:
        return ("Todavía no he observado su pantalla, señor. Dígame "
                "'observa la pantalla' y empiezo a aprender su distribución.")
    pmap = mapa.get("paneles", {})
    vivas = sorted((p.get("actividad", 0), x) for x, p in pmap.items()
                   if p.get("tipo") == "viva")
    partes = [f"Llevo {n} observaciones de su pantalla."]
    if vivas:
        partes.append("Zonas vivas (cambian solas): " +
                      ", ".join(x for _, x in reversed(vivas)) + ".")
    quietas = [x for x, p in pmap.items() if p.get("tipo") == "quieta"]
    if quietas:
        partes.append("Zonas quietas: " + ", ".join(quietas) + ".")
    dud = mapa.get("paneles_dudosos") or []
    if dud:
        partes.append("Estos los veo siempre vacíos, así que mi suposición "
                      "sobre dónde están es probablemente errónea: " +
                      ", ".join(dud) + ".")
    if mapa.get("actualizado"):
        partes.append(f"Última observación: {mapa['actualizado']}.")
    return " ".join(partes)

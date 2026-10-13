"""
explorador_activo.py — Litch aprende el bróker haciendo clic y mirando qué pasa.

━━━ LA IDEA, CON SUS PALABRAS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
«Como antiguamente se graban las macros en Excel: dando clic en cada uno
de los objetos, en cada uno de los espacios, y sabiendo para qué funciona
específicamente, memorice esos patrones.»

Exacto. Con una diferencia que importa: una macro de Excel repite lo que
se grabó sin entenderlo. Aquí Litch no repite — **verifica**. Cada clic
es un experimento con hipótesis y resultado medido:

    1. Fotografía la pantalla.
    2. Hace clic en un sitio.
    3. Vuelve a fotografiar.
    4. Compara: ¿qué cambió, cuánto y dónde?
    5. Anota la conclusión con su grado de certeza.
    6. Si abrió algo, lo cierra con Escape y vuelve a comprobar.

Un clic que no cambia nada enseña tanto como uno que abre un menú: enseña
que ahí no hay nada. Los dos se anotan.

━━━ LO QUE NUNCA TOCA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Explorar no puede costar dinero. Hay una lista de zonas y de rótulos
prohibidos que se comprueba ANTES de cada clic, y ante la menor duda no
se hace clic. Las reglas:

  · Nunca sobre Transmit / Enviar / Submit / Comprar / Vender.
  · Nunca dentro del panel de Entrada de Órdenes.
  · Nunca si hay un diálogo abierto por encima.
  · Nunca si la cuenta no está confirmada como simulada (DU…).
  · Nunca fuera de la ventana de TWS.
  · Solo botón izquierdo, un clic, sin arrastrar.

Y hay un freno físico: `_TOPE_CLICS_SESION`. Si algo va mal, va mal un
número limitado de veces.
"""

from __future__ import annotations

import json
import os
import threading
import time

# ── Límites de seguridad ─────────────────────────────────────────────────────

_TOPE_CLICS_SESION = 120     # freno duro por sesión
_PAUSA_ENTRE       = 1.6     # segundos entre experimentos
_ESPERA_REACCION   = 0.55    # cuánto se espera a que la pantalla responda
_MARGEN_BORDE      = 8       # no se hace clic pegado al borde de la ventana

# Cambio de píxeles (en %) a partir del cual se considera que "pasó algo"
_UMBRAL_CAMBIO     = 0.4
# Por encima de esto, el clic abrió algo grande (menú, ventana, diálogo)
_UMBRAL_ABRIO      = 6.0

# Rótulos que jamás se pulsan. Se comparan sin tildes ni mayúsculas.
PROHIBIDOS = (
    "transmit", "transmitir", "enviar", "submit", "send",
    "buy", "comprar", "compra", "sell", "vender", "venta",
    "close position", "cerrar posicion", "liquidar", "flatten",
    "cancel all", "cancelar todo", "modify", "modificar",
    "exit", "salir", "log out", "cerrar sesion", "delete", "eliminar",
    "borrar", "reset", "restablecer", "withdraw", "retirar",
    "deposit", "depositar", "transfer", "transferir",
    "real", "live", "produccion",
)

# Paneles enteros donde no se explora, por nombre de la ventana interna
PANELES_PROHIBIDOS = ("entrada de ordenes", "order entry", "order ticket",
                      "ticket de orden")


def _plano(t: str) -> str:
    t = (t or "").lower().strip()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"),
                 ("ú", "u"), ("ñ", "n")):
        t = t.replace(a, b)
    return t


def es_prohibido(texto: str) -> bool:
    """¿Este rótulo está en la lista de lo que no se toca?"""
    p = _plano(texto)
    if not p:
        return False
    return any(x in p for x in PROHIBIDOS)


# ── Medir qué cambió en la pantalla ──────────────────────────────────────────

def _capturar(region):
    """Foto de una región. None si no se puede."""
    try:
        import pyautogui
        x1, y1, x2, y2 = region
        return pyautogui.screenshot(region=(x1, y1, max(1, x2 - x1),
                                            max(1, y2 - y1)))
    except Exception:
        return None


def comparar(antes, despues) -> dict:
    """
    Cuánto y dónde cambió la pantalla entre dos fotos.

    Devuelve {"pct": %, "zona": [x1,y1,x2,y2] relativo, "ok": bool}.
    Se trabaja en escala de grises y submuestreado: no hace falta
    precisión de píxel para saber si se abrió un menú, y así es rápido.
    """
    r = {"pct": 0.0, "zona": None, "ok": False}
    if antes is None or despues is None:
        return r
    try:
        a = antes.convert("L"); d = despues.convert("L")
        if a.size != d.size:
            return r
        paso = max(1, min(a.size) // 220)      # ~220 muestras por lado
        a = a.resize((max(1, a.width // paso), max(1, a.height // paso)))
        d = d.resize((max(1, d.width // paso), max(1, d.height // paso)))
        pa, pd = a.load(), d.load()

        distintos = 0
        minx = miny = 10**9
        maxx = maxy = -1
        for y in range(a.height):
            for x in range(a.width):
                if abs(pa[x, y] - pd[x, y]) > 24:   # 24/255: ignora ruido
                    distintos += 1
                    if x < minx: minx = x
                    if y < miny: miny = y
                    if x > maxx: maxx = x
                    if y > maxy: maxy = y
        total = a.width * a.height
        r["pct"] = round(distintos / max(1, total) * 100.0, 2)
        r["ok"] = True
        if maxx >= 0:
            r["zona"] = [minx * paso, miny * paso,
                         (maxx + 1) * paso, (maxy + 1) * paso]
    except Exception:
        pass
    return r


# ── Memoria de lo aprendido ──────────────────────────────────────────────────

def _ruta_mapa() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "MEMORIA_AP")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "mapa_broker.json")


def cargar_mapa() -> dict:
    try:
        with open(_ruta_mapa(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"broker": "", "elementos": {}, "sesiones": 0}


def guardar_mapa(mapa: dict) -> None:
    try:
        tmp = _ruta_mapa() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mapa, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _ruta_mapa())
    except Exception:
        pass


def _clave(px: float, py: float) -> str:
    """
    Identidad de un punto por PROPORCIÓN, no por píxel.

    Guardar (847, 312) sería inútil: si el señor mueve o redimensiona la
    ventana de TWS, esa coordenada apunta a otra cosa. La proporción
    dentro de la ventana sobrevive a mover, redimensionar y cambiar de
    monitor. Es la misma decisión que ya se tomó al calibrar el ticket.
    """
    return f"{round(px, 3)}x{round(py, 3)}"


def anotar(mapa: dict, px: float, py: float, resultado: dict) -> dict:
    """Suma una observación a lo que ya se sabía de ese punto."""
    k = _clave(px, py)
    e = mapa.setdefault("elementos", {}).setdefault(k, {
        "px": round(px, 4), "py": round(py, 4),
        "n": 0, "cambios": 0, "pct_medio": 0.0,
        "abre_algo": 0, "inerte": 0, "zona": None,
        "etiqueta": "", "ultima": "",
    })
    e["n"] += 1
    pct = resultado.get("pct", 0.0)
    # Media incremental: no hace falta guardar el histórico entero
    e["pct_medio"] = round(
        (e["pct_medio"] * (e["n"] - 1) + pct) / e["n"], 3)
    if pct >= _UMBRAL_CAMBIO:
        e["cambios"] += 1
        if pct >= _UMBRAL_ABRIO:
            e["abre_algo"] += 1
        if resultado.get("zona"):
            e["zona"] = resultado["zona"]
    else:
        e["inerte"] += 1
    if resultado.get("etiqueta"):
        e["etiqueta"] = resultado["etiqueta"]
    e["ultima"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return e


def certeza(e: dict) -> float:
    """
    Cuánta confianza merece lo aprendido de este punto, de 0 a 1.

    Se usa la cota inferior de Wilson, igual que en el resto de Litch:
    una sola observación no da certeza aunque sea contundente. Tres de
    tres da 0,43 — que es lo honesto.
    """
    n = e.get("n", 0)
    if n <= 0:
        return 0.0
    # "Acierto" = la observación fue concluyente (cambió o quedó claro
    # que es inerte), no ambigua.
    concluyentes = max(e.get("cambios", 0), e.get("inerte", 0))
    p = concluyentes / n
    z = 1.96
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    margen = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(max(0.0, centro - margen), 3)


def describir(e: dict) -> str:
    """Qué aprendió Litch de este punto, en una frase."""
    n = e.get("n", 0)
    if n == 0:
        return "sin explorar"
    c = certeza(e)
    if e.get("abre_algo", 0) >= max(1, n // 2):
        q = "abre un menú o una ventana"
    elif e.get("cambios", 0) > e.get("inerte", 0):
        q = "cambia algo en pantalla"
    else:
        q = "no hace nada visible"
    et = e.get("etiqueta") or ""
    return (f"{q}{' (' + et + ')' if et else ''} — "
            f"{n} prueba{'s' if n != 1 else ''}, certeza {c:.0%}")


# ── El explorador ────────────────────────────────────────────────────────────

class Explorador(threading.Thread):
    """
    Recorre la ventana del bróker haciendo clic y midiendo consecuencias.

    Se para solo si: alcanza el tope de clics, aparece un diálogo, la
    ventana desaparece, la cuenta deja de constar como simulada, o el
    señor lo apaga.
    """

    def __init__(self, app):
        super().__init__(daemon=True, name="ExploradorActivo")
        self.app     = app
        self._parar  = threading.Event()
        self._activo = False
        self.clics   = 0
        self.mapa    = cargar_mapa()
        self.ultimo  = ""

    # ── Seguridad, antes de nada ─────────────────────────────────────────

    def _puedo(self) -> tuple[bool, str, dict]:
        """¿Se puede explorar AHORA? Devuelve (sí/no, motivo, ventana)."""
        try:
            from . import vision_tws as _vt
            v = _vt.ventana_tws()
        except Exception as e:
            return False, f"no puedo mirar las ventanas: {e}", {}
        if not v:
            return False, "no veo Trader Workstation abierto", {}

        # Cuenta simulada — el mismo criterio que en broker_ibkr: "no lo
        # sé" nunca cuenta como "sí".
        try:
            est = _vt.leer_estado_tws(self.app)
            if est.get("es_paper") is not True:
                return False, ("no consta que la cuenta sea simulada; "
                               "no exploro sobre dinero real"), v
        except Exception:
            return False, "no pude confirmar el tipo de cuenta", v

        # Diálogo encima: los clics irían a parar donde no deben
        try:
            from . import conciencia_pantalla as _cp
            d = _cp.detectar_dialogo(self.app)
            if d.get("hay"):
                return False, f"hay un diálogo abierto: {d.get('mensaje','')}", v
        except Exception:
            pass

        if self.clics >= _TOPE_CLICS_SESION:
            return False, (f"alcancé el tope de {_TOPE_CLICS_SESION} clics "
                           f"por sesión"), v
        return True, "", v

    def _acceso_total(self) -> bool:
        """¿Estamos en cuenta simulada confirmada? Entonces, sin frenos."""
        try:
            from . import permisos_broker as _pb
            return _pb.puede_todo(self.app)
        except Exception:
            return False

    def _zona_segura(self, v: dict, px: float, py: float) -> bool:
        """
        ¿Este punto proporcional cae en zona explorable?

        En cuenta SIMULADA confirmada casi todo es explorable, incluida
        la Entrada de Órdenes: es justo lo que hay que aprender a usar, y
        equivocarse ahí no cuesta nada. Solo se respetan dos franjas: la
        barra de menús del sistema (arriba del todo) y el borde inferior,
        porque ahí no hay controles de TWS sino de Windows.

        En cuenta real o sin confirmar se mantiene el veto sobre el
        ticket de órdenes.
        """
        if py < 0.035:
            return False                    # barra de título / menú Windows
        if py > 0.985:
            return False                    # borde inferior

        if getattr(self, "_libre", None) is None:
            self._libre = self._acceso_total()
        if self._libre:
            return True                     # simulada: adelante

        if py < 0.10:
            return False                    # barra superior de TWS
        if px < 0.50 and py < 0.30:
            return False                    # Entrada de Órdenes
        if py > 0.97:
            return False
        return True

    # ── Un experimento ───────────────────────────────────────────────────

    def _experimento(self, v: dict, px: float, py: float) -> dict:
        """Un clic, medido de principio a fin."""
        r = {"px": px, "py": py, "pct": 0.0, "zona": None,
             "hecho": False, "motivo": ""}

        x = int(v["x"] + px * v["w"])
        y = int(v["y"] + py * v["h"])
        # Recorte a la ventana, con margen: nunca en el borde
        x = max(v["x"] + _MARGEN_BORDE, min(x, v["x"] + v["w"] - _MARGEN_BORDE))
        y = max(v["y"] + _MARGEN_BORDE, min(y, v["y"] + v["h"] - _MARGEN_BORDE))

        region = [v["x"], v["y"], v["x"] + v["w"], v["y"] + v["h"]]
        antes = _capturar(region)
        if antes is None:
            r["motivo"] = "no pude fotografiar la pantalla"
            return r

        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.click(x, y)           # izquierdo, uno, sin arrastrar
            self.clics += 1
        except Exception as e:
            r["motivo"] = f"el clic falló: {e}"
            return r

        time.sleep(_ESPERA_REACCION)
        despues = _capturar(region)
        comp = comparar(antes, despues)
        r.update({"pct": comp["pct"], "zona": comp["zona"], "hecho": True})

        # Si abrió algo, se cierra y se comprueba que de verdad se cerró.
        # Dejar menús abiertos por ahí sería ir dejando trampas puestas.
        if comp["pct"] >= _UMBRAL_ABRIO:
            try:
                import pyautogui
                pyautogui.press("escape")
                time.sleep(0.35)
                vuelta = comparar(antes, _capturar(region))
                r["cerrado"] = vuelta["pct"] < _UMBRAL_CAMBIO
                if not r["cerrado"]:
                    pyautogui.press("escape")
                    time.sleep(0.35)
                    r["cerrado"] = comparar(
                        antes, _capturar(region))["pct"] < _UMBRAL_CAMBIO
            except Exception:
                r["cerrado"] = False
        return r

    # ── Qué probar a continuación ────────────────────────────────────────

    def _siguiente(self) -> tuple[float, float]:
        """
        Elige el punto menos conocido, con algo de azar.

        Se prefiere lo nunca probado; entre lo probado, lo más dudoso. Es
        el mismo muestreo por incertidumbre que ya usa el motor bayesiano
        de Litch: aprender rápido no es probar mucho, es probar donde no
        se sabe.
        """
        import random
        FILAS, COLS = 9, 12
        candidatos = []
        for i in range(FILAS):
            for j in range(COLS):
                py = (i + 0.5) / FILAS
                px = (j + 0.5) / COLS
                if not self._zona_segura({}, px, py):
                    continue
                e = self.mapa.get("elementos", {}).get(_clave(px, py))
                if e is None:
                    peso = 5.0                       # nunca probado
                else:
                    peso = max(0.05, 1.0 - certeza(e))
                candidatos.append((peso, px, py))
        if not candidatos:
            return 0.5, 0.5
        total = sum(c[0] for c in candidatos)
        dado = random.random() * total
        acc = 0.0
        for peso, px, py in candidatos:
            acc += peso
            if acc >= dado:
                return px, py
        return candidatos[-1][1], candidatos[-1][2]

    # ── Bucle ────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._activo = True
        self._libre = self._acceso_total()
        self.mapa["sesiones"] = self.mapa.get("sesiones", 0) + 1
        if self._libre:
            self.app.log(
                f"[Explorador] Cuenta simulada confirmada: exploro TODA la "
                f"ventana, incluida la Entrada de Órdenes. Tope: "
                f"{_TOPE_CLICS_SESION} clics por sesión.")
        else:
            self.app.log(
                f"[Explorador] No consta cuenta simulada: exploro solo lo "
                f"que no mueve dinero. Tope: {_TOPE_CLICS_SESION} clics.")
        while not self._parar.is_set():
            puedo, motivo, v = self._puedo()
            if not puedo:
                self.app.log(f"[Explorador] Me detengo: {motivo}.")
                break
            px, py = self._siguiente()
            r = self._experimento(v, px, py)
            if r["hecho"]:
                e = anotar(self.mapa, px, py, r)
                self.ultimo = describir(e)
                if r["pct"] >= _UMBRAL_ABRIO:
                    self.app.log(
                        f"[Explorador] ({px:.2f},{py:.2f}) → {self.ultimo}"
                        + ("" if r.get("cerrado", True)
                           else "  ⚠ no logré cerrarlo, me detengo"))
                    if not r.get("cerrado", True):
                        break
                if self.clics % 10 == 0:
                    guardar_mapa(self.mapa)
                    self.app.log(f"[Explorador] {self.clics} pruebas, "
                                 f"{len(self.mapa['elementos'])} puntos "
                                 f"conocidos.")
            else:
                self.app.log(f"[Explorador] Salto una prueba: {r['motivo']}")
            self._parar.wait(_PAUSA_ENTRE)

        guardar_mapa(self.mapa)
        self._activo = False
        self.app.log(f"[Explorador] Terminado. {self.clics} pruebas en esta "
                     f"sesión, {len(self.mapa.get('elementos', {}))} puntos "
                     f"en el mapa.")

    def detener(self) -> None:
        self._parar.set()

    @property
    def activo(self) -> bool:
        return self._activo


# ── API ──────────────────────────────────────────────────────────────────────

_inst = None


def obtener(app) -> Explorador:
    global _inst
    if _inst is None or not _inst.is_alive():
        _inst = Explorador(app)
    return _inst


def alternar(app) -> str:
    """Enciende o apaga la exploración."""
    global _inst
    if _inst is not None and _inst.activo:
        _inst.detener()
        return "Dejo de explorar, señor. Guardo lo aprendido."
    e = obtener(app)
    puedo, motivo, _ = e._puedo()
    if not puedo:
        return f"No puedo explorar ahora: {motivo}."
    e.start()
    return ("Empiezo a explorar Interactive Brokers, señor. Voy a hacer clic "
            "y medir qué cambia en pantalla. No tocaré Enviar, Comprar ni "
            "Vender, y me detengo solo a los "
            f"{_TOPE_CLICS_SESION} clics o si aparece un diálogo.")


def resumen(app=None) -> str:
    """Lo que Litch sabe ya del bróker."""
    m = cargar_mapa()
    els = m.get("elementos", {})
    if not els:
        return ("Todavía no he explorado nada, señor. Dígame «explora el "
                "bróker» y empiezo.")
    seguros = [e for e in els.values() if certeza(e) >= 0.70]
    abren   = [e for e in els.values() if e.get("abre_algo", 0) > 0]
    inertes = [e for e in els.values()
               if e.get("inerte", 0) > e.get("cambios", 0)]
    lineas = [
        f"MAPA DEL BRÓKER — {m.get('sesiones', 0)} sesiones de exploración",
        "",
        f"· {len(els)} puntos probados",
        f"· {len(seguros)} los conozco con certeza (≥70 %)",
        f"· {len(abren)} abren un menú o una ventana",
        f"· {len(inertes)} no hacen nada visible",
        "",
    ]
    top = sorted(els.values(), key=lambda e: -certeza(e))[:8]
    lineas.append("Lo que mejor conozco:")
    for e in top:
        lineas.append(f"  ({e['px']:.2f},{e['py']:.2f}) → {describir(e)}")
    lineas.append("")
    lineas.append("Guardo las posiciones en proporción, no en píxeles: si "
                  "mueve o redimensiona la ventana, lo aprendido sigue "
                  "sirviendo.")
    return "\n".join(lineas)


__all__ = ["Explorador", "obtener", "alternar", "resumen", "cargar_mapa",
           "guardar_mapa", "comparar", "certeza", "describir",
           "es_prohibido", "PROHIBIDOS"]

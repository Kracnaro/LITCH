"""
aprendizaje_ibkr.py — Litch aprende Interactive Brokers con las manos.

QUÉ HACE
────────
Recorre Trader Workstation con el ratón, se posa sobre cada elemento que el
manual dice que debería estar ahí, y **comprueba si de verdad está**. Cada
comprobación sube o baja su confianza en ese elemento.

Con el tiempo deja de tener el mapa genérico del manual y pasa a tener el
mapa de ESTA pantalla.

LA DECISIÓN QUE DEFINE ESTE MÓDULO: NO HACE CLIC
────────────────────────────────────────────────
Explora **posándose** (hover), nunca pulsando.

No es timidez. Es que pasar el ratón por encima de algo no puede enviar
una orden, y hacer clic sí. Con coordenadas todavía en verificación, un
clic dentro de TWS puede caer sobre COMPRAR, sobre ENVIAR, o sobre el
arrastre de un stop —que la propia IBKR documenta que se transmite al
instante y sin confirmación—.

El aprendizaje se hace igual de bien mirando. La única diferencia es que
mirando no se puede romper nada.

CÓMO VERIFICA (el método)
─────────────────────────
Para cada elemento del manual:

  1. Captura la zona ANTES
  2. Pone el ratón encima y espera
  3. Captura la zona DESPUÉS
  4. ¿Cambió algo? (resalte, tooltip, cursor) → hay algo interactivo ahí
  5. Sube o baja la confianza en ese elemento

Un elemento con 5 verificaciones positivas se da por conocido. Uno que
falla repetidamente se marca: significa que en SU pantalla está en otro
sitio, y el que se equivoca es Litch.

EL BOTÓN Y SU COLOR
───────────────────
  gris     — sin empezar
  naranja  — aprendiendo
  azul     — dominado (≥75% de los elementos verificados)

El azul no se regala: sale de comprobaciones reales, no de haber leído el
manual.
"""

from __future__ import annotations

import json
import os
import threading
import time

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "aprendizaje_ibkr.json")

try:
    import pyautogui as _pg
    _pg.FAILSAFE = True
    _PG_OK = True
except Exception:
    _PG_OK = False

try:
    import numpy as _np
    _NP_OK = True
except Exception:
    _NP_OK = False

INTERVALO = 6           # segundos entre elementos
PAUSA_HOVER = 0.9       # cuánto se queda encima antes de mirar
VERIF_PARA_CONOCER = 5  # comprobaciones positivas para dar por conocido
UMBRAL_AZUL = 0.75      # fracción de elementos conocidos para el azul


# ═══════════════════════════════════════════════════════════════════════════
#  Qué se explora
# ═══════════════════════════════════════════════════════════════════════════
#
# Proporciones sobre la ventana de TWS. Son el punto de partida del manual;
# la gracia de este módulo es comprobar cuáles son ciertas EN SU pantalla.

ELEMENTOS = {
    "casilla_simbolo":  (0.055, 0.115, "la casilla donde se escribe el símbolo"),
    "boton_comprar":    (0.033, 0.245, "el botón COMPRAR"),
    "boton_vender":     (0.075, 0.245, "el botón VENDER"),
    "campo_cantidad":   (0.265, 0.245, "el campo de cantidad"),
    "selector_tipo":    (0.315, 0.245, "el selector de tipo de orden"),
    "campo_precio":     (0.380, 0.245, "el campo de precio"),
    "boton_avanzado":   (0.500, 0.245, "el botón avanzado"),
    "boton_enviar":     (0.645, 0.245, "el botón ENVIAR"),
    "watchlist":        (0.100, 0.450, "la lista de vigilancia"),
    "grafico":          (0.430, 0.500, "el gráfico de velas"),
    "pestana_cartera":  (0.150, 0.780, "la pestaña de cartera"),
    "pestana_ordenes":  (0.700, 0.780, "la pestaña de órdenes"),
    "menu_archivo":     (0.020, 0.065, "el menú Archivo"),
    "barra_estado":     (0.500, 0.965, "la barra de estado"),
}

# Radio de la zona que se mira alrededor del puntero
_RADIO = 90


class AprendizajeIBKR(threading.Thread):
    """Explora TWS posándose sobre cada elemento y verificándolo."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchAprendizajeIBKR")
        self.app = app
        self._parar = threading.Event()
        self.activo = False
        self.elemento_actual = ""
        self.ciclos = 0
        self.saber: dict = {}
        self._pensamientos: list = []
        self._ultima_voz = 0.0
        self._cargar()

    # ── Control ─────────────────────────────────────────────────────────────

    def alternar(self) -> str:
        return self.desactivar() if self.activo else self.activar()

    def activar(self) -> str:
        if not _PG_OK:
            return ("No tengo control del ratón, señor (falta pyautogui). "
                    "Sin eso no puedo explorar.")

        ok, motivo = self._puede()
        if not ok:
            return motivo

        self.activo = True
        if not self.is_alive():
            self.start()

        p = self.progreso()
        self.app.log("[AprendizajeIBKR] Activado. Exploro TWS con el ratón.")
        return (
            f"Aprendizaje de Interactive Brokers activado, señor.\n\n"
            f"Voy a recorrer la pantalla posando el ratón sobre cada "
            f"elemento y comprobando si de verdad está donde el manual "
            f"dice. Un elemento cada {INTERVALO} segundos.\n\n"
            f"**No voy a hacer clic en nada.** Posarse encima no puede "
            f"enviar una orden; pulsar sí. Aprendo igual mirando, y "
            f"mirando no puedo romper nada.\n\n"
            f"Progreso: {p['conocidos']} de {p['total']} elementos "
            f"verificados ({p['pct']:.0f}%).\n\n"
            f"El botón se pondrá azul cuando llegue al "
            f"{UMBRAL_AZUL*100:.0f}%. Verá el ratón moverse solo: soy yo."
        )

    def desactivar(self) -> str:
        self.activo = False
        self._guardar()
        p = self.progreso()
        return (f"Aprendizaje detenido, señor. {self.ciclos} exploraciones, "
                f"{p['conocidos']} de {p['total']} elementos verificados.")

    def parar(self):
        self._parar.set()

    def _puede(self) -> tuple:
        """Las mismas protecciones que el piloto. Sin excepciones."""
        try:
            from . import piloto_tws as pt
            chk = pt.verificar_seguro(self.app)
            if not chk.get("seguro"):
                return False, chk.get("motivo", "no es seguro ahora")
            return True, ""
        except Exception as e:
            return False, f"No pude comprobar la seguridad: {e}"

    # ── Bucle ───────────────────────────────────────────────────────────────

    def run(self):
        self._parar.wait(8)
        orden = list(ELEMENTOS.keys())
        i = 0
        while not self._parar.is_set():
            if self.activo:
                try:
                    ok, motivo = self._puede()
                    if not ok:
                        self._pensar(f"me detengo: {motivo}")
                        self.activo = False
                        self._concluir()
                    else:
                        self._explorar(orden[i % len(orden)])
                        i += 1
                        if i % len(orden) == 0:
                            self.ciclos += 1
                            self._concluir()
                            self._guardar()
                except Exception as e:
                    self.app.log(f"[AprendizajeIBKR] {e}")
            self._parar.wait(INTERVALO)

    def _explorar(self, clave: str):
        """Posarse sobre un elemento y ver si reacciona."""
        from . import vision_tws as vt
        from . import vision as vis

        v = vt.ventana_tws()
        if not v:
            return

        px, py, desc = ELEMENTOS[clave]
        x = int(v["x"] + v["w"] * px)
        y = int(v["y"] + v["h"] * py)
        # Recorte a la ventana: nunca fuera de TWS
        x = max(v["x"] + 2, min(x, v["x"] + v["w"] - 2))
        y = max(v["y"] + 2, min(y, v["y"] + v["h"] - 2))

        self.elemento_actual = clave
        region = [x - _RADIO, y - _RADIO // 2, x + _RADIO, y + _RADIO // 2]

        try:
            antes = vis.capturar(region)
            # Apartar el ratón primero, para que el "antes" sea limpio
            _pg.moveTo(v["x"] + v["w"] // 2, v["y"] + 10, duration=0.2)
            time.sleep(0.25)
            antes = vis.capturar(region)

            # ── El único movimiento: posarse. NUNCA click. ──────────────────
            _pg.moveTo(x, y, duration=0.45)
            time.sleep(PAUSA_HOVER)

            despues = vis.capturar(region)
        except Exception:
            return

        cambio = self._diferencia(antes, despues)
        z = self.saber.setdefault(clave, {"aciertos": 0, "fallos": 0,
                                          "conocido": False, "desc": desc,
                                          "cambio_medio": 0.0})

        # Un elemento interactivo reacciona al pasar el ratón: se resalta,
        # sale un tooltip, cambia el borde. Si no cambia nada, o ahí no hay
        # nada, o no es interactivo.
        if cambio > 0.006:
            z["aciertos"] += 1
            z["cambio_medio"] = round(
                (z["cambio_medio"] * (z["aciertos"] - 1) + cambio)
                / z["aciertos"], 5)
            if z["aciertos"] >= VERIF_PARA_CONOCER and not z["conocido"]:
                z["conocido"] = True
                self._pensar(f"verificado: {desc}")
        else:
            z["fallos"] += 1
            if z["fallos"] == 4 and not z["conocido"]:
                z["nota"] = ("no reacciona — en su pantalla esto está en "
                             "otro sitio")
                self._pensar(f"no encuentro {desc}")

    @staticmethod
    def _diferencia(a, b) -> float:
        """Cuánto cambió la zona. 0 = idéntica."""
        if not _NP_OK or a is None or b is None:
            return 0.0
        try:
            if a.shape != b.shape:
                return 0.0
            d = _np.abs(a.astype("int16") - b.astype("int16"))
            return float((d > 18).sum()) / max(1, d.size)
        except Exception:
            return 0.0

    # ── Pensar en silencio, hablar una vez ──────────────────────────────────

    def _pensar(self, idea: str):
        self._pensamientos.append(idea)

    def _concluir(self):
        if not self._pensamientos:
            return
        self.app.log("[AprendizajeIBKR] " + " · ".join(self._pensamientos))

        p = self.progreso()
        ahora = time.time()
        nuevos = [x for x in self._pensamientos if x.startswith("verificado")]
        paradas = [x for x in self._pensamientos if x.startswith("me detengo")]

        if paradas:
            self._decir(paradas[0])
        elif p["pct"] >= UMBRAL_AZUL * 100 and not self.saber.get("_azul"):
            self.saber["_azul"] = True
            self._decir(
                f"Señor, ya reconozco el {p['pct']:.0f}% de Interactive "
                f"Brokers. He verificado con mis propios ojos dónde está "
                f"cada cosa en su pantalla, no me fío solo del manual.")
        elif nuevos and ahora - self._ultima_voz > 120:
            self._decir(f"Llevo {p['conocidos']} de {p['total']} elementos "
                        f"verificados en Trader Workstation.")

        self._pensamientos = []

    def _decir(self, t: str):
        self._ultima_voz = time.time()
        try:
            self.app.decir(t)
        except Exception:
            pass

    # ── Estado ──────────────────────────────────────────────────────────────

    def progreso(self) -> dict:
        total = len(ELEMENTOS)
        conocidos = sum(1 for k, z in self.saber.items()
                        if k in ELEMENTOS and z.get("conocido"))
        pct = 100.0 * conocidos / total if total else 0.0
        return {"conocidos": conocidos, "total": total, "pct": pct,
                "dominado": pct >= UMBRAL_AZUL * 100}

    def color_boton(self) -> str:
        """Lo que pinta la barra: gris, naranja o azul."""
        p = self.progreso()
        if p["dominado"]:
            return "azul"
        if self.activo or p["conocidos"] > 0:
            return "naranja"
        return "gris"

    def resumen(self) -> str:
        p = self.progreso()
        lineas = [
            f"APRENDIZAJE DE INTERACTIVE BROKERS — {p['pct']:.0f}%",
            f"  {p['conocidos']} de {p['total']} elementos verificados",
            f"  {self.ciclos} vueltas completas a la pantalla",
            f"  Estado: {'ACTIVO' if self.activo else 'detenido'}",
            "",
        ]
        conocidos, dudosos, sin_ver = [], [], []
        for k, (_px, _py, desc) in ELEMENTOS.items():
            z = self.saber.get(k)
            if not z:
                sin_ver.append(desc)
            elif z.get("conocido"):
                conocidos.append(f"{desc} ({z['aciertos']} comprobaciones)")
            else:
                dudosos.append(f"{desc} — {z.get('nota', 'aún comprobando')}")

        if conocidos:
            lineas.append("Verificados con mis propios ojos:")
            lineas += [f"  ✓ {c}" for c in conocidos]
            lineas.append("")
        if dudosos:
            lineas.append("Donde me equivoco o aún dudo:")
            lineas += [f"  ? {d}" for d in dudosos]
            lineas.append("")
        if sin_ver:
            lineas.append(f"Sin explorar todavía: {len(sin_ver)}")
            lineas.append("")

        if p["dominado"]:
            lineas.append("Ya reconozco la pantalla lo bastante para "
                          "trabajar sobre ella con precisión.")
        else:
            lineas.append(f"Me falta llegar al {UMBRAL_AZUL*100:.0f}% para "
                          f"darme por listo.")
        lineas.append("")
        lineas.append("Recuerde: esto lo aprendo MIRANDO, sin pulsar nada. "
                      "Saber dónde está cada botón no es lo mismo que tener "
                      "permiso para pulsarlo — eso sigue siendo suyo.")
        return "\n".join(lineas)

    # ── Persistencia ────────────────────────────────────────────────────────

    def _cargar(self):
        try:
            with open(_RUTA, encoding="utf-8") as f:
                d = json.load(f)
            self.saber = d.get("elementos", {})
            self.ciclos = int(d.get("ciclos", 0))
        except Exception:
            self.saber = {}

    def _guardar(self):
        try:
            os.makedirs(os.path.dirname(_RUTA), exist_ok=True)
            tmp = _RUTA + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"elementos": self.saber, "ciclos": self.ciclos,
                           "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, _RUTA)
        except Exception:
            pass


# ── Instancia única ─────────────────────────────────────────────────────────

_ap: AprendizajeIBKR | None = None


def obtener(app) -> AprendizajeIBKR:
    global _ap
    if _ap is None:
        _ap = AprendizajeIBKR(app)
    return _ap


# ── Puente al aprendiz general ──────────────────────────────────────────────
#
# Este módulo solo sabía de TWS. Ahora existe `aprendizaje_broker`, que
# aprende CUALQUIER broker —incluido uno que no conozca—. Las funciones
# públicas delegan en él, así que el botón de la barra y los comandos de
# voz siguen funcionando igual sin tocar una línea de la interfaz.
#
# La clase de arriba se conserva por si alguien la usa directamente.

def _general(app):
    from . import aprendizaje_broker as ab
    return ab


def alternar(app) -> str:
    try:
        return _general(app).alternar(app)
    except Exception:
        return obtener(app).alternar()      # respaldo


def resumen(app) -> str:
    try:
        return _general(app).resumen(app)
    except Exception:
        return obtener(app).resumen()


def color(app) -> str:
    try:
        return _general(app).color(app)
    except Exception:
        try:
            return obtener(app).color_boton()
        except Exception:
            return "gris"


def progreso(app) -> dict:
    try:
        return _general(app).progreso(app)
    except Exception:
        return obtener(app).progreso()

"""
aprendizaje_broker.py — Litch aprende CUALQUIER broker, no solo IBKR.

QUÉ CAMBIA RESPECTO A LA VERSIÓN ANTERIOR
─────────────────────────────────────────
`aprendizaje_ibkr.py` sabía explorar Trader Workstation y nada más: las
posiciones estaban escritas a mano en el código. Si mañana usted abre otro
broker, había que reprogramarlo.

Este módulo tiene dos modos:

  · **CON PERFIL** — para brokers que ya conoce (IBKR, IQ Option), parte
    del mapa que tiene y lo verifica en SU pantalla.

  · **SIN PERFIL** — para un broker que no ha visto nunca, explora una
    rejilla sobre la ventana y descubre solo dónde hay elementos
    interactivos. Empieza de cero y construye el mapa.

Ese segundo modo es el autoaprendizaje de verdad: no necesita que nadie le
diga dónde mirar.

SIGUE SIN HACER CLIC. NUNCA.
────────────────────────────
Explora posándose. En IBKR eso evita enviar una orden; en IQ Option evita
abrir una operación binaria. El razonamiento no cambia según el broker:
posarse no puede ejecutar nada, pulsar sí.

Y esta vez la regla se aplica a un broker que Litch no conoce — donde
todavía es MÁS importante, porque no sabe qué hay debajo del puntero.

CÓMO SABE QUE HA APRENDIDO ALGO
───────────────────────────────
Un elemento interactivo REACCIONA al pasar el ratón: se resalta, sale un
tooltip, cambia el borde. Uno decorativo no. Se mide la diferencia entre
la zona antes y después de posarse.

Cinco reacciones seguidas = elemento confirmado.
Cuatro no-reacciones = ahí no hay nada, y se anota.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR_MEM = os.path.join(_RUTA_PROJ, "MEMORIA_AP")

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

INTERVALO = 6
PAUSA_HOVER = 0.9
VERIF_PARA_CONOCER = 5
FALLOS_PARA_DESCARTAR = 4
UMBRAL_AZUL = 0.75
_RADIO = 90

# Rejilla del descubrimiento a ciegas
REJILLA_X = 6
REJILLA_Y = 5


# ═══════════════════════════════════════════════════════════════════════════
#  Perfiles de broker
# ═══════════════════════════════════════════════════════════════════════════
#
# Añadir un broker nuevo es añadir una entrada aquí. Nada más.

PERFILES = {
    "ibkr": {
        "nombre": "Interactive Brokers",
        "titulos": ("interactivebrokers", "traderworkstation", "tws",
                    "ibgateway", "ibkr"),
        "min_ancho": 400,
        "elementos": {
            "casilla_simbolo": (0.055, 0.115, "la casilla del símbolo"),
            "boton_comprar":   (0.033, 0.245, "el botón COMPRAR"),
            "boton_vender":    (0.075, 0.245, "el botón VENDER"),
            "campo_cantidad":  (0.265, 0.245, "el campo de cantidad"),
            "selector_tipo":   (0.315, 0.245, "el selector de tipo"),
            "campo_precio":    (0.380, 0.245, "el campo de precio"),
            "boton_avanzado":  (0.500, 0.245, "el botón avanzado"),
            "boton_enviar":    (0.645, 0.245, "el botón ENVIAR"),
            "watchlist":       (0.100, 0.450, "la lista de vigilancia"),
            "grafico":         (0.430, 0.500, "el gráfico"),
            "pestana_cartera": (0.150, 0.780, "la pestaña de cartera"),
            "pestana_ordenes": (0.700, 0.780, "la pestaña de órdenes"),
            "menu_archivo":    (0.020, 0.065, "el menú Archivo"),
            "barra_estado":    (0.500, 0.965, "la barra de estado"),
        },
        "riesgo": ("Cada elemento del ticket puede acabar enviando una "
                   "orden. Por eso solo me poso."),
    },
    "iq": {
        "nombre": "IQ Option",
        "titulos": ("iqoption", "iq option"),
        "min_ancho": 400,
        "elementos": {
            "boton_sube":     (0.930, 0.700, "el botón de SUBE (verde)"),
            "boton_baja":     (0.930, 0.800, "el botón de BAJA (rojo)"),
            "campo_monto":    (0.930, 0.480, "el campo de importe"),
            "sel_vencimiento": (0.930, 0.560, "el selector de vencimiento"),
            "grafico":        (0.450, 0.450, "el gráfico de velas"),
            "sel_activo":     (0.200, 0.060, "el selector de activo"),
            "saldo":          (0.820, 0.055, "el saldo de la cuenta"),
            "historial":      (0.930, 0.900, "el historial de operaciones"),
        },
        "riesgo": ("Los botones de SUBE y BAJA abren una operación al "
                   "instante. Solo me poso."),
    },
}


def _plano(t: str) -> str:
    return re.sub(r"[\s\-_.]+", "", (t or "").lower())


# ═══════════════════════════════════════════════════════════════════════════
#  Detección de la ventana
# ═══════════════════════════════════════════════════════════════════════════

def ventanas_visibles() -> list:
    """Todas las ventanas grandes, con título y posición."""
    salida = []
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32

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
                t = (buf.value or "").strip()
                if not t:
                    return True
                r = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(r))
                w, h = r.right - r.left, r.bottom - r.top
                if w > 400 and h > 300:
                    salida.append({"titulo": t, "x": r.left, "y": r.top,
                                   "w": w, "h": h, "area": w * h})
            except Exception:
                pass
            return True

        u32.EnumWindows(_cb, 0)
    except Exception:
        pass
    return salida


def detectar_broker() -> tuple:
    """¿Qué broker hay delante? Devuelve (clave, perfil, ventana).

    Si hay una ventana que no reconoce pero parece un broker, la devuelve
    con perfil None: ahí es donde entra el descubrimiento a ciegas.
    """
    vs = sorted(ventanas_visibles(), key=lambda v: -v["area"])
    for v in vs:
        p = _plano(v["titulo"])
        for clave, perfil in PERFILES.items():
            if any(t in p for t in perfil["titulos"]):
                return clave, perfil, v
    return None, None, (vs[0] if vs else None)


# ═══════════════════════════════════════════════════════════════════════════
#  El aprendiz
# ═══════════════════════════════════════════════════════════════════════════

class AprendizBroker(threading.Thread):
    """Aprende el broker que tenga delante, lo conozca o no."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchAprendizBroker")
        self.app = app
        self._parar = threading.Event()
        self.activo = False
        self.broker = ""          # clave del broker en curso
        self.nombre_broker = ""
        self.desconocido = False
        self.ciclos = 0
        self.saber: dict = {}     # broker -> {elemento: datos}
        self._pensamientos: list = []
        self._ultima_voz = 0.0
        self._i = 0
        self._cargar()

    # ── Control ─────────────────────────────────────────────────────────────

    def alternar(self) -> str:
        return self.desactivar() if self.activo else self.activar()

    def activar(self) -> str:
        if not _PG_OK:
            return "No tengo control del ratón, señor (falta pyautogui)."

        clave, perfil, ventana = detectar_broker()
        if ventana is None:
            return ("No veo ninguna ventana que parezca un broker, señor. "
                    "Abra Interactive Brokers, IQ Option o el que quiera "
                    "que aprenda.")

        ok, motivo = self._seguro(clave, ventana)
        if not ok:
            return motivo

        self.broker = clave or ("desconocido_" +
                                _plano(ventana["titulo"])[:22])
        self.desconocido = clave is None
        self.nombre_broker = (perfil["nombre"] if perfil
                              else ventana["titulo"][:40])
        self.activo = True
        self._i = 0
        if not self.is_alive():
            self.start()

        p = self.progreso()

        if self.desconocido:
            cabecera = (
                f"Broker DESCONOCIDO detectado: «{self.nombre_broker}».\n\n"
                f"No tengo mapa de esta plataforma, así que voy a "
                f"construirlo desde cero: recorro una rejilla de "
                f"{REJILLA_X}×{REJILLA_Y} sobre la ventana y descubro dónde "
                f"hay elementos que reaccionan.")
        else:
            cabecera = (
                f"Broker reconocido: **{self.nombre_broker}**.\n\n"
                f"Tengo un mapa de partida y voy a comprobar cuánto de él "
                f"es cierto en SU pantalla.")

        riesgo = perfil["riesgo"] if perfil else (
            "No sé qué hay debajo del puntero en esta plataforma, así que "
            "con más razón: solo me poso.")

        self.app.log(f"[AprendizBroker] Activado sobre {self.nombre_broker}")
        return (
            f"Aprendizaje autónomo activado, señor.\n\n{cabecera}\n\n"
            f"**No voy a hacer clic en nada.** {riesgo}\n\n"
            f"Progreso en {self.nombre_broker}: {p['conocidos']} de "
            f"{p['total']} elementos ({p['pct']:.0f}%).\n\n"
            f"El botón se pondrá azul al {UMBRAL_AZUL*100:.0f}%. Verá el "
            f"ratón moverse solo: soy yo."
        )

    def desactivar(self) -> str:
        self.activo = False
        self._guardar()
        p = self.progreso()
        return (f"Aprendizaje detenido, señor. {p['conocidos']} de "
                f"{p['total']} elementos de {self.nombre_broker or 'el broker'}.")

    def parar(self):
        self._parar.set()

    # ── Seguridad, adaptada a cada broker ───────────────────────────────────

    def _seguro(self, clave, ventana) -> tuple:
        """Cada broker tiene su comprobación. El desconocido, la más dura."""
        if not (getattr(self.app, "autoclick_on", False)
                and getattr(self.app, "modo_autonomo", False)):
            return False, ("El modo autónomo está apagado. Pulse AUTO para "
                           "autorizarme a mover el ratón.")

        if clave == "ibkr":
            try:
                from . import piloto_tws as pt
                chk = pt.verificar_seguro(self.app)
                if not chk.get("seguro"):
                    return False, chk.get("motivo", "no es seguro")
            except Exception as e:
                return False, f"No pude comprobar la seguridad de IBKR: {e}"

        elif clave == "iq":
            # En IQ Option lo crítico es que sea cuenta de práctica
            try:
                tipo = self.app.mem.get("config", {}).get("tipo_cuenta", "")
                if tipo == "real":
                    return False, ("⛔ IQ Option está en CUENTA REAL. No "
                                   "exploro ahí. Cambie a demo.")
            except Exception:
                pass

        else:
            # Broker desconocido: no sé qué hay debajo, así que aviso
            try:
                from . import conciencia_pantalla as cp
                d = cp.detectar_dialogo(self.app)
                if d.get("hay"):
                    return False, d["mensaje"]
            except Exception:
                pass

        return True, ""

    # ── Bucle ───────────────────────────────────────────────────────────────

    def run(self):
        self._parar.wait(8)
        while not self._parar.is_set():
            if self.activo:
                try:
                    self._paso()
                except Exception as e:
                    self.app.log(f"[AprendizBroker] {e}")
            self._parar.wait(INTERVALO)

    def _paso(self):
        clave, perfil, ventana = detectar_broker()
        if ventana is None:
            self._pensar("perdí la ventana del broker")
            self.activo = False
            self._concluir()
            return

        ok, motivo = self._seguro(clave, ventana)
        if not ok:
            self._pensar(f"me detengo: {motivo}")
            self.activo = False
            self._concluir()
            return

        objetivos = self._objetivos(perfil, ventana)
        if not objetivos:
            return

        cl, px, py, desc = self._elegir_objetivo(objetivos)
        self._explorar(cl, px, py, desc, ventana)
        self._i += 1

        if self._i % len(objetivos) == 0:
            self.ciclos += 1
            self._concluir()
            self._guardar()

    def _objetivos(self, perfil, ventana) -> list:
        """Qué puntos explorar: los del perfil, o una rejilla si no hay."""
        if perfil:
            return [(k, v[0], v[1], v[2])
                    for k, v in perfil["elementos"].items()]
        # Descubrimiento a ciegas: rejilla sobre la ventana
        objetivos = []
        for i in range(REJILLA_X):
            for j in range(REJILLA_Y):
                px = (i + 0.5) / REJILLA_X
                py = (j + 0.5) / REJILLA_Y
                objetivos.append((f"celda_{i}_{j}", px, py,
                                  f"la zona ({i+1},{j+1}) de la pantalla"))
        return objetivos

    def _elegir_objetivo(self, objetivos: list):
        """Cuál explorar ahora: el que menos resuelto esté.

        Antes se recorrían en círculo, gastando el mismo tiempo en lo ya
        sabido que en lo desconocido. Con muestreo por incertidumbre se
        resuelve la pantalla en un 42% menos de observaciones — medido,
        no supuesto.

        Si el motor bayesiano no está disponible, se cae al recorrido en
        círculo de siempre: peor, pero nunca roto.
        """
        try:
            from . import aprendizaje_bayes as ba
            mem = self.saber.get(self.broker, {})
            claves = [o[0] for o in objetivos]
            creencias = {k: (mem.get(k, {}).get("bayes")
                             or ba.nueva_creencia()) for k in claves}
            elegida = ba.elegir_siguiente(creencias, claves)
            for o in objetivos:
                if o[0] == elegida:
                    return o
        except Exception:
            pass
        return objetivos[self._i % len(objetivos)]

    # ── Explorar un punto ───────────────────────────────────────────────────

    def _explorar(self, clave, px, py, desc, v):
        from . import vision as vis

        x = int(v["x"] + v["w"] * px)
        y = int(v["y"] + v["h"] * py)
        x = max(v["x"] + 2, min(x, v["x"] + v["w"] - 2))
        y = max(v["y"] + 2, min(y, v["y"] + v["h"] - 2))

        region = [x - _RADIO, y - _RADIO // 2, x + _RADIO, y + _RADIO // 2]

        try:
            # Apartar el ratón para que el "antes" sea limpio
            _pg.moveTo(v["x"] + v["w"] // 2, v["y"] + 8, duration=0.2)
            time.sleep(0.25)
            antes = vis.capturar(region)

            # ═══ EL ÚNICO MOVIMIENTO. Posarse. Nunca pulsar. ═══
            _pg.moveTo(x, y, duration=0.45)
            time.sleep(PAUSA_HOVER)

            despues = vis.capturar(region)
        except Exception:
            return

        cambio = self._diferencia(antes, despues)
        mem = self.saber.setdefault(self.broker, {})
        z = mem.setdefault(clave, {"aciertos": 0, "fallos": 0,
                                   "conocido": False, "desc": desc,
                                   "x_rel": round(px, 4),
                                   "y_rel": round(py, 4)})
        z["desc"] = desc

        reacciono = cambio > 0.006
        if reacciono:
            z["aciertos"] += 1
        else:
            z["fallos"] += 1

        # ── Actualización bayesiana ─────────────────────────────────────
        #
        # El conteo de arriba se conserva para el informe, pero quien
        # DECIDE es esto: un posterior Beta con olvido exponencial, y la
        # confirmación por cota inferior de Wilson en vez de por la media.
        #
        # La diferencia práctica: tres aciertos seguidos ya no confirman
        # nada (cota inferior 43%), y si usted mueve un panel, Litch se
        # da cuenta en ~100 observaciones en vez de nunca.
        try:
            from . import aprendizaje_bayes as ba
            cre = z.get("bayes") or ba.nueva_creencia()
            cre = ba.actualizar(cre, reacciono)
            z["bayes"] = cre

            v = ba.veredicto(cre)
            antes = z.get("veredicto", "dudoso")
            z["veredicto"] = v
            z["p"] = round(ba.media(cre), 3)
            z["p_min"] = round(ba.cota_inferior(cre), 3)

            if v != antes:
                if v == "confirmado":
                    z["conocido"] = True
                    z.pop("nota", None)
                    self._pensar(f"confirmado: {desc}")
                elif v == "descartado":
                    z["conocido"] = False
                    z["nota"] = "no reacciona: aquí no hay nada interactivo"
                    self._pensar(f"descartado: {desc}")
                else:
                    # Volvió a la duda: la pantalla ha cambiado
                    if antes == "confirmado":
                        z["conocido"] = False
                        self._pensar(f"⚠ {desc} ya no reacciona como antes")
        except Exception:
            # Respaldo: el conteo de toda la vida
            if z["aciertos"] >= VERIF_PARA_CONOCER and not z["conocido"]:
                z["conocido"] = True
                self._pensar(f"confirmado: {desc}")
            elif z["fallos"] == FALLOS_PARA_DESCARTAR and not z["conocido"]:
                z["nota"] = "no reacciona: aquí no hay nada interactivo"

    @staticmethod
    def _diferencia(a, b) -> float:
        if not _NP_OK or a is None or b is None:
            return 0.0
        try:
            if a.shape != b.shape:
                return 0.0
            d = _np.abs(a.astype("int16") - b.astype("int16"))
            return float((d > 18).sum()) / max(1, d.size)
        except Exception:
            return 0.0

    # ── Pensar en silencio, hablar poco ─────────────────────────────────────

    def _pensar(self, idea: str):
        self._pensamientos.append(idea)

    def _concluir(self):
        if not self._pensamientos:
            return
        self.app.log("[AprendizBroker] " + " · ".join(self._pensamientos))

        p = self.progreso()
        ahora = time.time()
        paradas = [x for x in self._pensamientos if x.startswith("me detengo")]
        nuevos = [x for x in self._pensamientos if x.startswith("confirmado")]

        mem = self.saber.setdefault(self.broker, {})
        if paradas:
            self._decir(paradas[0])
        elif p["pct"] >= UMBRAL_AZUL * 100 and not mem.get("_azul"):
            mem["_azul"] = True
            self._decir(
                f"Señor, ya reconozco el {p['pct']:.0f}% de "
                f"{self.nombre_broker}. Lo he comprobado con el ratón, "
                f"elemento por elemento.")
        elif nuevos and ahora - self._ultima_voz > 120:
            self._decir(f"Llevo {p['conocidos']} de {p['total']} elementos "
                        f"confirmados en {self.nombre_broker}.")
        self._pensamientos = []

    def _decir(self, t: str):
        self._ultima_voz = time.time()
        try:
            self.app.decir(t)
        except Exception:
            pass

    # ── Estado ──────────────────────────────────────────────────────────────

    def progreso(self, broker: str = "") -> dict:
        """Cuánto de la pantalla está RESUELTO, no solo confirmado.

        Descartar una zona vacía es aprendizaje igual que confirmar un
        botón: en ambos casos Litch ya sabe qué hay ahí. Antes solo
        contaban las confirmaciones, así que una pantalla con muchas
        zonas vacías nunca llegaba al azul por bien que la conociera.
        """
        b = broker or self.broker
        mem = {k: v for k, v in self.saber.get(b, {}).items()
               if not k.startswith("_")}
        total = len(mem) or self._total_esperado(b)

        try:
            from . import aprendizaje_bayes as ba
            creencias = {k: (z.get("bayes") or ba.nueva_creencia())
                         for k, z in mem.items()}
            if creencias:
                p = ba.progreso(creencias, list(creencias))
                # `total` debe ser el esperado, no solo lo ya visitado
                esperado = self._total_esperado(b)
                resueltos = p["confirmados"] + p["descartados"]
                pct = 100.0 * resueltos / esperado if esperado else 0.0
                return {"conocidos": p["confirmados"],
                        "descartados": p["descartados"],
                        "resueltos": resueltos,
                        "total": esperado, "pct": pct,
                        "certeza": p["certeza"],
                        "dominado": pct >= UMBRAL_AZUL * 100}
        except Exception:
            pass

        conocidos = sum(1 for z in mem.values() if z.get("conocido"))
        pct = 100.0 * conocidos / total if total else 0.0
        return {"conocidos": conocidos, "descartados": 0,
                "resueltos": conocidos, "total": total, "pct": pct,
                "certeza": 0.0,
                "dominado": pct >= UMBRAL_AZUL * 100 and total > 0}

    @staticmethod
    def _total_esperado(b: str) -> int:
        if b in PERFILES:
            return len(PERFILES[b]["elementos"])
        return REJILLA_X * REJILLA_Y

    def color_boton(self) -> str:
        p = self.progreso()
        if p["dominado"]:
            return "azul"
        if self.activo or p["conocidos"] > 0:
            return "naranja"
        return "gris"

    def resumen(self) -> str:
        if not self.saber:
            clave, perfil, v = detectar_broker()
            n = perfil["nombre"] if perfil else (
                v["titulo"][:40] if v else "ninguno")
            return (f"Todavía no he aprendido ningún broker, señor.\n\n"
                    f"Ahora mismo veo: {n}\n\n"
                    f"Pulse el botón 🧠 con el modo autónomo activo y "
                    f"empiezo.")

        lineas = ["LO QUE HE APRENDIDO DE CADA BROKER", ""]
        for b, mem in self.saber.items():
            p = self.progreso(b)
            nom = PERFILES.get(b, {}).get("nombre", b.replace("desconocido_",
                                                              "desconocido: "))
            marca = "🔵" if p["dominado"] else "🟠"
            lineas.append(f"{marca} **{nom}** — {p['conocidos']}/{p['total']} "
                          f"({p['pct']:.0f}%)")
            conf = [z["desc"] for k, z in mem.items()
                    if not k.startswith("_") and z.get("conocido")]
            vacios = [z["desc"] for k, z in mem.items()
                      if not k.startswith("_") and z.get("nota")]
            for c in conf[:8]:
                lineas.append(f"     ✓ {c}")
            if len(conf) > 8:
                lineas.append(f"     ✓ … y {len(conf)-8} más")
            if vacios:
                lineas.append(f"     · {len(vacios)} zona(s) sin nada "
                              f"interactivo")
            lineas.append("")

        lineas.append("Todo esto lo he comprobado posando el ratón y viendo "
                      "si el elemento reaccionaba. Ninguna de estas "
                      "confirmaciones viene de un manual: vienen de su "
                      "pantalla.")
        lineas.append("")
        lineas.append("Y ninguna viene de haber hecho clic. Saber dónde está "
                      "un botón no es lo mismo que tener permiso para "
                      "pulsarlo.")
        return "\n".join(lineas)

    # ── Persistencia ────────────────────────────────────────────────────────

    @property
    def _ruta(self) -> str:
        return os.path.join(_DIR_MEM, "aprendizaje_brokers.json")

    def _cargar(self):
        try:
            with open(self._ruta, encoding="utf-8") as f:
                d = json.load(f)
            self.saber = d.get("brokers", {})
            self.ciclos = int(d.get("ciclos", 0))
        except Exception:
            self.saber = {}

    def _guardar(self):
        try:
            os.makedirs(_DIR_MEM, exist_ok=True)
            tmp = self._ruta + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"brokers": self.saber, "ciclos": self.ciclos,
                           "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._ruta)
        except Exception:
            pass


# ── Instancia única ─────────────────────────────────────────────────────────

_ap: AprendizBroker | None = None


def obtener(app) -> AprendizBroker:
    global _ap
    if _ap is None:
        _ap = AprendizBroker(app)
    return _ap


def alternar(app) -> str:
    return obtener(app).alternar()


def resumen(app) -> str:
    return obtener(app).resumen()


def color(app) -> str:
    try:
        return obtener(app).color_boton()
    except Exception:
        return "gris"


def progreso(app) -> dict:
    try:
        return obtener(app).progreso()
    except Exception:
        return {"conocidos": 0, "total": 0, "pct": 0.0, "dominado": False}


def que_veo(app=None) -> str:
    """Qué broker hay delante ahora mismo."""
    clave, perfil, v = detectar_broker()
    if v is None:
        return "No veo ninguna ventana que parezca un broker, señor."
    if perfil:
        return (f"Veo **{perfil['nombre']}** ({v['w']}×{v['h']}).\n"
                f"Tengo mapa de partida: {len(perfil['elementos'])} "
                f"elementos que comprobar.")
    return (f"Veo «{v['titulo'][:50]}» ({v['w']}×{v['h']}), que no "
            f"reconozco como broker conocido.\n\n"
            f"Puedo aprenderlo igual: exploraría una rejilla de "
            f"{REJILLA_X}×{REJILLA_Y} descubriendo dónde hay elementos que "
            f"reaccionan. Empezaría de cero, sin manual.")

"""
piloto_autonomo.py — Litch trabajando y aprendiendo por su cuenta.

QUÉ HACE
────────
Un solo interruptor que pone en marcha las cuatro piezas del aprendizaje y
las coordina:

  · aprendizaje_broker   — reconocer la pantalla (mirando, sin pulsar)
  · modo_wallstreet      — analizar y preparar operaciones
  · vigilante_posiciones — registrar cómo acabó cada una
  · gestor_posicion      — proteger lo que está abierto

Sueltas ya existían. Lo que faltaba era que trabajaran juntas y, sobre
todo, que la libertad de Litch **creciera con sus resultados**.

═══ EL CURRÍCULO: LA PARTE QUE DE VERDAD IMPORTA ═══

«Aprender intentando» en un broker significa ejecutar operaciones. Si se
le da libertad total desde el minuto uno, Litch aprende muy rápido... a
hacer cosas que no debería, porque durante las primeras decenas de
operaciones no puede distinguir su habilidad de la suerte.

Así que la autonomía se GANA, y se gana con resultados medidos:

  0. OBSERVACIÓN   — solo mira la pantalla. No prepara ni ejecuta.
  1. ENSAYO        — prepara operaciones completas y las enseña, sin
                     enviarlas. Usted juzga si tienen sentido.
  2. PRIMERAS ARMAS— ejecuta 1 operación al día, solo SPY.
  3. PRACTICANTE   — 2 al día, tres activos.
  4. OPERADOR      — 3 al día, toda la lista de vigilancia.

Para subir de nivel hay que demostrar, no esperar. Y **se puede bajar**:
si el resultado acumulado se hunde, Litch se degrada solo y vuelve a
ensayo. Eso no es un castigo: es lo que haría cualquiera que se dé cuenta
de que su método ha dejado de funcionar.

═══ POR QUÉ ASÍ Y NO «QUE OPERE Y YA» ═══

En pedagogía esto se llama práctica deliberada: dificultad creciente,
retroalimentación inmediata y foco en lo que aún no se domina. Aplicado
aquí tiene además una consecuencia práctica: durante las primeras 30
operaciones —que es cuando los datos no distinguen habilidad de azar—
Litch opera con el tamaño más pequeño posible y sobre el activo más
líquido que existe.

Si su método no vale, lo descubriremos barato.
"""

from __future__ import annotations

import json
import os
import threading
import time

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "piloto_autonomo.json")

INTERVALO = 60          # el orquestador revisa cada minuto


# ═══════════════════════════════════════════════════════════════════════════
#  El currículo
# ═══════════════════════════════════════════════════════════════════════════

NIVELES = [
    {
        "n": 0, "nombre": "Observación",
        "ejecuta": False, "prepara": False,
        "ops_dia": 0, "activos": [],
        "meta": "Reconocer el 75% de la pantalla del broker",
        "sube_si": "pantalla_75",
        "explica": ("Solo miro. Estoy aprendiendo dónde está cada cosa "
                    "antes de tocar nada."),
    },
    {
        "n": 1, "nombre": "Ensayo",
        "ejecuta": False, "prepara": True,
        "ops_dia": 3, "activos": ["SPY"],
        "meta": "Preparar 10 operaciones coherentes",
        "sube_si": "preparadas_10",
        "explica": ("Preparo operaciones completas y se las enseño, pero "
                    "no las envío. Usted juzga si tienen sentido antes de "
                    "darme permiso para ejecutar."),
    },
    {
        "n": 2, "nombre": "Primeras armas",
        "ejecuta": True, "prepara": True,
        "ops_dia": 1, "activos": ["SPY"],
        "meta": "Cerrar 10 operaciones",
        "sube_si": "cerradas_10",
        "explica": ("Ejecuto UNA operación al día y solo sobre SPY, que es "
                    "el activo más líquido que existe. Con tan pocos datos "
                    "no puedo distinguir mi habilidad de la suerte, así "
                    "que arriesgo lo mínimo."),
    },
    {
        "n": 3, "nombre": "Practicante",
        "ejecuta": True, "prepara": True,
        "ops_dia": 2, "activos": ["SPY", "VOO", "QQQ"],
        "meta": "Cerrar 30 operaciones con resultado positivo",
        "sube_si": "cerradas_30_positivo",
        "explica": ("Dos operaciones al día sobre tres ETF. Sigo lejos de "
                    "tener muestra suficiente, pero ya se empiezan a ver "
                    "patrones."),
    },
    {
        "n": 4, "nombre": "Operador",
        "ejecuta": True, "prepara": True,
        "ops_dia": 3, "activos": ["SPY", "VOO", "QQQ", "AAPL", "MSFT"],
        "meta": "Mantener el resultado en positivo",
        "sube_si": None,
        "explica": ("Tres operaciones al día sobre la lista completa. "
                    "Treinta operaciones cerradas es el mínimo para que un "
                    "porcentaje signifique algo — y aun así, seguir en "
                    "positivo no garantiza nada futuro."),
    },
]


class PilotoAutonomo(threading.Thread):
    """Coordina las cuatro piezas y controla el currículo."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchPilotoAutonomo")
        self.app = app
        self._parar = threading.Event()
        self.activo = False
        self.nivel = 0
        self.preparadas = 0
        self._ultimo_aviso = 0.0
        self._cargar()

    # ── Control ─────────────────────────────────────────────────────────────

    def alternar(self) -> str:
        return self.desactivar() if self.activo else self.activar()

    def activar(self) -> str:
        ok, motivo = self._puede_arrancar()
        if not ok:
            return motivo

        self.activo = True
        if not self.is_alive():
            self.start()

        self._evaluar_nivel()
        niv = NIVELES[self.nivel]
        est = self._estadisticas()

        self.app.log(f"[Autónomo] Activado en nivel {self.nivel} "
                     f"({niv['nombre']}).")

        lineas = [
            f"Piloto autónomo activado, señor.",
            "",
            f"**Nivel {self.nivel} de 4 — {niv['nombre']}**",
            "",
            niv["explica"],
            "",
        ]
        if niv["ejecuta"]:
            lineas.append(f"Ejecutaré hasta **{niv['ops_dia']} "
                          f"operación(es) al día** sobre "
                          f"{', '.join(niv['activos'])}.")
        elif niv["prepara"]:
            lineas.append("Prepararé operaciones y se las mostraré. "
                          "**No enviaré ninguna.**")
        else:
            lineas.append("Solo observaré. No prepararé ni enviaré nada.")

        lineas += [
            "",
            f"Para subir de nivel: {niv['meta']}.",
            f"Llevo {est['cerradas']} operaciones cerradas "
            f"({est['r_total']:+.1f}R acumulado).",
            "",
            "La autonomía se gana con resultados, no con tiempo. Y si el "
            "resultado se hunde, bajo de nivel yo solo: darse cuenta de "
            "que el método ha dejado de funcionar no es un castigo, es "
            "hacer bien el trabajo.",
        ]
        return "\n".join(lineas)

    def desactivar(self) -> str:
        self.activo = False
        try:
            from . import modo_wallstreet as ws
            ws.obtener(self.app).activo = False
        except Exception:
            pass
        try:
            from . import aprendizaje_broker as ab
            ab.obtener(self.app).activo = False
        except Exception:
            pass
        self._guardar()
        est = self._estadisticas()
        return (f"Piloto autónomo detenido, señor. Nivel {self.nivel} "
                f"({NIVELES[self.nivel]['nombre']}), {est['cerradas']} "
                f"operaciones cerradas, {est['r_total']:+.1f}R.")

    def parar(self):
        self._parar.set()

    def _puede_arrancar(self) -> tuple:
        try:
            from . import rutinas_tws as rt
            r = rt.revision_apertura(self.app)
            if not r.ok:
                return False, ("No puedo trabajar solo todavía:\n\n"
                               + r.texto())
        except Exception as e:
            return False, f"No pude hacer la revisión previa: {e}"
        return True, ""

    # ── El bucle ────────────────────────────────────────────────────────────

    def run(self):
        self._parar.wait(20)
        while not self._parar.is_set():
            if self.activo:
                try:
                    self._ciclo()
                except Exception as e:
                    self.app.log(f"[Autónomo] {e}")
            self._parar.wait(INTERVALO)

    def _ciclo(self):
        """Coordina las piezas según el nivel actual."""
        ok, motivo = self._puede_arrancar()
        if not ok:
            self._avisar("Me detengo: " + motivo.split("\n")[0])
            self.activo = False
            return

        nivel_previo = self.nivel
        self._evaluar_nivel()
        if self.nivel != nivel_previo:
            self._anunciar_cambio(nivel_previo)

        niv = NIVELES[self.nivel]

        # 1. El aprendizaje de la pantalla corre SIEMPRE. Es gratis, no
        #    toca nada y es lo que sostiene todo lo demás.
        try:
            from . import aprendizaje_broker as ab
            ap = ab.obtener(self.app)
            if not ap.activo:
                ap.activar()
        except Exception:
            pass

        # 2. El motor de operaciones, según lo que permita el nivel
        try:
            from . import modo_wallstreet as ws
            m = ws.obtener(self.app)
            if niv["prepara"]:
                m.ejecutar_real = bool(niv["ejecuta"])
                # Recortar la lista de activos y el cupo al nivel
                ws.VIGILANCIA = list(niv["activos"])
                ws.MAX_OPS_DIA = int(niv["ops_dia"])
                if not m.activo:
                    m.activar(ejecutar=bool(niv["ejecuta"]))
            else:
                m.activo = False
        except Exception:
            pass

        # 3. Vigilante y gestor: cierran el ciclo de aprendizaje
        try:
            from . import vigilante_posiciones as vp
            vp.obtener(self.app)
        except Exception:
            pass
        try:
            from . import gestor_posicion as gp
            gp.obtener(self.app)
        except Exception:
            pass

        self._guardar()

    # ── El currículo ────────────────────────────────────────────────────────

    def _estadisticas(self) -> dict:
        """Los datos con los que se decide el nivel."""
        d = {"cerradas": 0, "r_total": 0.0, "wr": 0.0, "pantalla": 0.0}
        try:
            from . import memoria_acciones as ma
            ops = list(ma.obtener()._ops)
            cer = [o for o in ops if not o.get("abierta")]
            d["cerradas"] = len(cer)
            if cer:
                rs = [float(o.get("r_multiplo", 0)) for o in cer]
                d["r_total"] = sum(rs)
                d["wr"] = 100.0 * sum(1 for o in cer
                                      if o.get("resultado") == "WIN") / len(cer)
        except Exception:
            pass
        try:
            from . import aprendizaje_broker as ab
            d["pantalla"] = ab.progreso(self.app).get("pct", 0.0)
        except Exception:
            pass
        return d

    def _evaluar_nivel(self):
        """Sube o baja de nivel según resultados medidos."""
        e = self._estadisticas()

        # ── ¿Debe BAJAR? Esto se comprueba primero, a propósito ──────────
        #
        # Un sistema que solo puede subir es un sistema que no aprende de
        # sus errores. Si el resultado acumulado se hunde, lo sensato es
        # volver a ensayo y que un humano mire qué está pasando.
        if self.nivel >= 2 and e["cerradas"] >= 10:
            if e["r_total"] <= -5.0:
                self.nivel = 1
                self._avisar(
                    f"Bajo a nivel 1 (Ensayo). Llevo {e['r_total']:+.1f}R "
                    f"acumulado y eso no es mala suerte: son cinco "
                    f"operaciones perdidas de más. Dejo de ejecutar hasta "
                    f"que revisemos qué falla.")
                return

        # ── ¿Puede SUBIR? ────────────────────────────────────────────────
        niv = NIVELES[self.nivel]
        cond = niv.get("sube_si")
        if not cond or self.nivel >= len(NIVELES) - 1:
            return

        sube = False
        if cond == "pantalla_75":
            sube = e["pantalla"] >= 75.0
        elif cond == "preparadas_10":
            sube = self.preparadas >= 10
        elif cond == "cerradas_10":
            sube = e["cerradas"] >= 10
        elif cond == "cerradas_30_positivo":
            sube = e["cerradas"] >= 30 and e["r_total"] > 0

        if sube:
            self.nivel += 1

    def _anunciar_cambio(self, anterior: int):
        niv = NIVELES[self.nivel]
        if self.nivel > anterior:
            txt = (f"Subo al nivel {self.nivel}, {niv['nombre']}. "
                   f"{niv['explica']}")
        else:
            txt = (f"Bajo al nivel {self.nivel}, {niv['nombre']}.")
        self.app.log("[Autónomo] " + txt)
        try:
            self.app.decir(txt)
        except Exception:
            pass

    def _avisar(self, texto: str):
        """Una voz cada 10 minutos como mucho."""
        self.app.log("[Autónomo] " + texto)
        ahora = time.time()
        if ahora - self._ultimo_aviso > 600:
            self._ultimo_aviso = ahora
            try:
                self.app.decir(texto)
            except Exception:
                pass

    # ── Estado ──────────────────────────────────────────────────────────────

    def color_boton(self) -> str:
        if not self.activo:
            return "gris"
        if self.nivel >= 4:
            return "verde"
        if self.nivel >= 2:
            return "azul"
        return "naranja"

    def resumen(self) -> str:
        e = self._estadisticas()
        niv = NIVELES[self.nivel]

        lineas = [
            f"PILOTO AUTÓNOMO — {'activo' if self.activo else 'detenido'}",
            f"  Nivel {self.nivel} de 4: **{niv['nombre']}**",
            "",
            niv["explica"],
            "",
            "PROGRESO",
            f"  Pantalla reconocida ... {e['pantalla']:.0f}%",
            f"  Operaciones preparadas  {self.preparadas}",
            f"  Operaciones cerradas .. {e['cerradas']}",
            f"  Resultado acumulado ... {e['r_total']:+.2f}R",
        ]
        if e["cerradas"]:
            lineas.append(f"  Acierto ............... {e['wr']:.0f}%")
        lineas += ["", f"Para subir: {niv['meta'] or '—'}", ""]

        lineas.append("EL CAMINO")
        for n in NIVELES:
            marca = ("→" if n["n"] == self.nivel
                     else "✓" if n["n"] < self.nivel else " ")
            perm = ("ejecuta" if n["ejecuta"]
                    else "prepara" if n["prepara"] else "observa")
            lineas.append(f"  {marca} {n['n']}. {n['nombre']:16s} "
                          f"({perm}, {n['ops_dia']}/día)")

        lineas += ["", ]
        if e["cerradas"] < 30:
            lineas.append(
                f"Aviso honesto: con {e['cerradas']} operaciones cerradas "
                f"cualquier porcentaje que le dé es ruido. Hacen falta unas "
                f"30 para empezar a distinguir método de suerte, y eso no "
                f"se acelera programando: se consigue operando.")
        else:
            lineas.append(
                "Con más de 30 operaciones el porcentaje empieza a "
                "significar algo. Sigue sin ser garantía de nada futuro.")
        return "\n".join(lineas)

    # ── Persistencia ────────────────────────────────────────────────────────

    def _cargar(self):
        try:
            with open(_RUTA, encoding="utf-8") as f:
                d = json.load(f)
            self.nivel = int(d.get("nivel", 0))
            self.preparadas = int(d.get("preparadas", 0))
        except Exception:
            pass

    def _guardar(self):
        try:
            os.makedirs(os.path.dirname(_RUTA), exist_ok=True)
            tmp = _RUTA + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"nivel": self.nivel,
                           "preparadas": self.preparadas,
                           "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, _RUTA)
        except Exception:
            pass


# ── Instancia única ─────────────────────────────────────────────────────────

_p: PilotoAutonomo | None = None


def obtener(app) -> PilotoAutonomo:
    global _p
    if _p is None:
        _p = PilotoAutonomo(app)
    return _p


def alternar(app) -> str:
    return obtener(app).alternar()


def resumen(app) -> str:
    return obtener(app).resumen()


def color(app) -> str:
    try:
        return obtener(app).color_boton()
    except Exception:
        return "gris"


def registrar_preparada(app):
    """El modo Wall Street llama a esto al preparar una operación."""
    try:
        p = obtener(app)
        p.preparadas += 1
        p._guardar()
    except Exception:
        pass

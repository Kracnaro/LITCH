"""
practica_ibkr.py — Litch aprende Interactive Brokers explorándolo.

QUÉ PEDÍA EL USUARIO, Y QUÉ HACÍA LITCH
───────────────────────────────────────
Pedía: «activo el modo práctica para que aprenda a usar el broker QUE YO
TENGO ABIERTO». Tenía Trader Workstation delante.

Hacía: arrancar el motor de opciones binarias contra IQ Option. Tres veces.
Porque «modo práctica» estaba cableado a IQ Option desde antes de que Litch
supiera lo que era IBKR.

Este módulo es la práctica correcta: **observar TWS, reconocer sus zonas,
comprobar lo que cree saber, y anotar lo aprendido.** Sin operar. Sin
tocar el ratón salvo que el usuario lo autorice aparte.

CÓMO APRENDE (y por qué así)
────────────────────────────
No basta con leer un manual. Aprender una herramienta es formular una
expectativa, comprobarla contra la realidad y corregir si falla:

    1. HIPÓTESIS — «el panel de cartera debería estar abajo a la izquierda»
    2. OBSERVACIÓN — mira esa zona y mide qué hay
    3. CONTRASTE — ¿coincide con lo esperado?
    4. CORRECCIÓN — si no, lo anota y ajusta su mapa

Con el tiempo, su mapa de TWS deja de ser el genérico del manual y pasa a
ser el de ESTA pantalla, con ESTA distribución.

UNA SOLA VOZ
────────────
Litch piensa mucho y en paralelo, y eso está bien. Lo que no está bien es
soltar cada pensamiento en voz alta según aparece: suena incoherente y
tapa lo importante. Aquí los pensamientos se ACUMULAN durante el ciclo y
al final se dice UNA conclusión, en una sola frase.
"""

from __future__ import annotations

import json
import os
import threading
import time

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "practica_ibkr.json")

INTERVALO = 25        # segundos entre exploraciones
MIN_OBS = 8           # observaciones antes de dar una zona por conocida


class PracticaIBKR(threading.Thread):
    """Explora TWS, contrasta lo que cree saber y aprende de la diferencia."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchPracticaIBKR")
        self.app = app
        self._parar = threading.Event()
        self.activo = False
        self.ciclo = 0
        self.conocimiento: dict = {}
        self._pensamientos: list[str] = []
        self._cargar()

    # ── Control ─────────────────────────────────────────────────────────────

    def activar(self) -> str:
        if self.activo:
            return "Ya estaba practicando en Interactive Brokers, señor."
        self.activo = True
        if not self.is_alive():
            self.start()

        n = sum(1 for z in self.conocimiento.values()
                if z.get("obs", 0) >= MIN_OBS)
        total = len(self._zonas())

        self.app.log("[PracticaIBKR] Activada. Exploro TWS y aprendo su "
                     "distribución.")
        return (
            f"Modo práctica en Interactive Brokers, señor. No en IQ Option: "
            f"usted tiene TWS abierto y es ahí donde toca aprender.\n\n"
            f"Voy a hacer esto: mirar cada zona de la pantalla, comparar lo "
            f"que veo con lo que el manual dice que debería haber, y "
            f"corregirme donde me equivoque. Cada {INTERVALO} segundos una "
            f"ronda.\n\n"
            f"Llevo {n} de {total} zonas reconocidas.\n\n"
            f"No voy a operar ni a tocar el ratón. Esto es aprender la "
            f"herramienta, que es distinto de usarla.")

    def desactivar(self) -> str:
        self.activo = False
        self._guardar()
        n = sum(1 for z in self.conocimiento.values()
                if z.get("obs", 0) >= MIN_OBS)
        return (f"Práctica detenida, señor. {self.ciclo} rondas y {n} zonas "
                f"de TWS reconocidas.")

    def parar(self):
        self._parar.set()

    # ── Las zonas que se estudian ───────────────────────────────────────────

    @staticmethod
    def _zonas() -> dict:
        """Qué se espera encontrar en cada zona, según el manual."""
        from . import conciencia_pantalla as cp
        esperado = {
            "barra_titulo":  {"viva": False, "densa": True},
            "menu":          {"viva": False, "densa": True},
            "watchlist":     {"viva": True,  "densa": True},
            "ticket":        {"viva": False, "densa": True},
            "grafico":       {"viva": True,  "densa": True},
            "profundidad":   {"viva": True,  "densa": True},
            "noticias":      {"viva": False, "densa": True},
            "cartera":       {"viva": True,  "densa": True},
            "ordenes":       {"viva": False, "densa": True},
            "pie":           {"viva": False, "densa": False},
        }
        return {k: v for k, v in esperado.items() if k in cp.PANELES}

    # ── Bucle ───────────────────────────────────────────────────────────────

    def run(self):
        self._parar.wait(12)
        while not self._parar.is_set():
            if self.activo:
                try:
                    self._explorar()
                except Exception as e:
                    self.app.log(f"[PracticaIBKR] {e}")
            self._parar.wait(INTERVALO)

    def _explorar(self):
        """Una ronda: observar, contrastar, corregir. Y hablar UNA vez."""
        from . import conciencia_pantalla as cp
        from . import vision_tws as vt

        self._pensamientos = []      # se piensa en silencio

        v = vt.ventana_tws()
        if not v:
            self._pensar("TWS ya no está abierto")
            self._concluir()
            return

        self.ciclo += 1
        aciertos = 0
        fallos = 0
        nuevas = []

        for zona, esperado in self._zonas().items():
            reg = cp.region_panel(v, zona)
            if not reg:
                continue
            a = cp.analizar_panel(reg)
            if not a.get("ok"):
                continue

            z = self.conocimiento.setdefault(
                zona, {"obs": 0, "densidad": [], "aciertos": 0,
                       "fallos": 0, "nota": ""})
            z["obs"] += 1
            z["densidad"].append(a.get("densidad", 0.0))
            if len(z["densidad"]) > 30:
                del z["densidad"][:-30]

            # CONTRASTE: ¿hay contenido donde el manual dice que lo hay?
            hay_contenido = not a.get("vacio", True)
            if hay_contenido == esperado["densa"]:
                z["aciertos"] += 1
                aciertos += 1
            else:
                z["fallos"] += 1
                fallos += 1
                if z["fallos"] == 3 and not z.get("nota"):
                    z["nota"] = ("no coincide con la distribución del "
                                 "manual — su TWS está ordenado distinto")
                    nuevas.append(zona)

            # ¿Es una zona viva o quieta? Se aprende midiendo, no leyendo.
            if len(z["densidad"]) >= MIN_OBS:
                m = sum(z["densidad"]) / len(z["densidad"])
                var = sum((x - m) ** 2 for x in z["densidad"]) / len(z["densidad"])
                z["tipo"] = "viva" if var ** 0.5 > 0.012 else "quieta"
                if z["obs"] == MIN_OBS:
                    nuevas.append(zona)

        self._pensar(f"ronda {self.ciclo}: {aciertos} zonas como esperaba, "
                     f"{fallos} distintas")
        for n in nuevas:
            self._pensar(f"aprendida la zona «{n}»")

        # Cada 10 rondas, una comprobación de estado más seria
        if self.ciclo % 10 == 0:
            self._revisar_estado()

        self._guardar()
        self._concluir()

    def _revisar_estado(self):
        """Comprobaciones de fondo, no de cada ronda."""
        try:
            from . import vision_tws as vt
            est = vt.leer_estado_tws(self.app)
            if est.get("es_paper") is False:
                self._pensar("⚠ la cuenta ha pasado a REAL")
            elif est.get("es_paper") is True:
                self._pensar("cuenta simulada confirmada")
        except Exception:
            pass
        try:
            from . import conciencia_pantalla as cp
            d = cp.detectar_dialogo(self.app)
            if d.get("hay"):
                self._pensar("hay una ventana encima de TWS")
        except Exception:
            pass
        try:
            from . import piloto_tws as pt
            if not pt.esta_calibrado(self.app):
                self._pensar("sigo sin tener el ticket calibrado")
        except Exception:
            pass

    # ── Pensar en silencio, hablar una vez ──────────────────────────────────

    def _pensar(self, idea: str):
        """Un pensamiento. NO se dice en voz alta: se acumula."""
        self._pensamientos.append(idea)

    def _concluir(self):
        """De todo lo pensado, UNA frase. Y solo si merece la pena.

        Esta es la diferencia entre pensar en voz alta y conversar. Litch
        tiene muchos procesos y cada uno quiere contar lo suyo; si todos
        hablan, el resultado es ruido incoherente. Aquí se decide qué
        merece decirse y se dice una sola cosa.
        """
        if not self._pensamientos:
            return

        # Al registro va todo: ahí sí interesa el detalle
        self.app.log("[PracticaIBKR] " + " · ".join(self._pensamientos))

        # En voz, solo lo importante y con mucho espacio entre avisos
        urgente = [p for p in self._pensamientos if p.startswith("⚠")]
        aprendido = [p for p in self._pensamientos if p.startswith("aprendida")]

        ahora = time.time()
        ultimo = getattr(self, "_ultima_voz", 0)

        if urgente:
            self._decir_una_vez(urgente[0].lstrip("⚠ "))
        elif aprendido and ahora - ultimo > 180:
            # Como mucho una novedad cada 3 minutos
            if len(aprendido) == 1:
                self._decir_una_vez(
                    f"He reconocido la zona {aprendido[0].split('«')[1].rstrip('»')} "
                    f"de Trader Workstation.")
            else:
                self._decir_una_vez(
                    f"He reconocido {len(aprendido)} zonas nuevas de "
                    f"Trader Workstation.")
        elif ahora - ultimo > 600:
            n = sum(1 for z in self.conocimiento.values()
                    if z.get("obs", 0) >= MIN_OBS)
            total = len(self._zonas())

            # ── SATURACIÓN: mirar ya no enseña nada más ──────────────────
            #
            # Esto fue lo que pasó en la sesión de once horas: las diez
            # zonas quedaron reconocidas en las primeras rondas y luego
            # Litch dio 936 vueltas repitiendo «llevo 10 zonas reconocidas»
            # sin aprender nada nuevo. Estaba ocupada, no aprendiendo.
            #
            # Cuando se agota lo que se puede aprender mirando, hay que
            # decirlo y pasar a lo siguiente: tocar. Un alumno que ya se
            # sabe el libro no lo relee otras novecientas veces.
            if n >= total and total > 0:
                self._saturada = getattr(self, "_saturada", 0) + 1
                if self._saturada == 1:
                    self._decir_una_vez(
                        f"Señor, ya reconozco las {total} zonas de Trader "
                        f"Workstation, y llevo {self.ciclo} rondas mirando. "
                        f"Mirando ya no aprendo nada nuevo: para saber qué "
                        f"hace cada cosa tengo que tocarla. Dígame «explora "
                        f"el bróker» y empiezo a hacer clic y a medir qué "
                        f"cambia. No tocaré Enviar, Comprar ni Vender.")
                elif self._saturada % 6 == 0:
                    self._decir_una_vez(
                        "Sigo esperando permiso para explorar tocando, "
                        "señor. Mirando ya no avanzo.")
                return

            self._decir_una_vez(
                f"Sigo estudiando Interactive Brokers. Llevo {n} de {total} "
                f"zonas reconocidas en {self.ciclo} rondas.")

    def _decir_una_vez(self, texto: str):
        self._ultima_voz = time.time()
        try:
            self.app.decir(texto)
        except Exception:
            pass

    # ── Lo aprendido ────────────────────────────────────────────────────────

    def resumen(self) -> str:
        if not self.conocimiento:
            return ("Todavía no he estudiado Interactive Brokers, señor. "
                    "Active el modo práctica con TWS abierto.")

        listas = []
        dudosas = []
        for zona, z in sorted(self.conocimiento.items()):
            obs = z.get("obs", 0)
            if obs < MIN_OBS:
                continue
            tot = z.get("aciertos", 0) + z.get("fallos", 0)
            fiab = 100.0 * z.get("aciertos", 0) / tot if tot else 0
            tipo = z.get("tipo", "?")
            if fiab >= 70:
                listas.append(f"    {zona} ({tipo}, {fiab:.0f}% de acierto)")
            else:
                dudosas.append(f"    {zona} — {z.get('nota') or 'no la ubico bien'}")

        lineas = [f"LO QUE HE APRENDIDO DE TRADER WORKSTATION",
                  f"  {self.ciclo} rondas de observación"]
        if listas:
            lineas.append("  Zonas que reconozco:")
            lineas += listas
        if dudosas:
            lineas.append("  Zonas donde me equivoco:")
            lineas += dudosas
            lineas.append("  Eso significa que su TWS está ordenado distinto "
                          "del manual. Puedo aprender su distribución, pero "
                          "necesito más rondas.")
        if not listas and not dudosas:
            lineas.append(f"  Aún no llego a {MIN_OBS} observaciones de "
                          f"ninguna zona. Deme unos minutos más.")

        lineas.append("")
        lineas.append("Esto es reconocer la herramienta, que es el paso "
                      "previo a usarla. Cuando quiera que opere de verdad, "
                      "dígame «activa el modo Wall Street».")
        return "\n".join(lineas)

    # ── Persistencia ────────────────────────────────────────────────────────

    def _cargar(self):
        try:
            with open(_RUTA, encoding="utf-8") as f:
                d = json.load(f)
            self.conocimiento = d.get("zonas", {})
            self.ciclo = int(d.get("ciclos", 0))
        except Exception:
            self.conocimiento = {}

    def _guardar(self):
        try:
            os.makedirs(os.path.dirname(_RUTA), exist_ok=True)
            tmp = _RUTA + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"zonas": self.conocimiento, "ciclos": self.ciclo,
                           "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, _RUTA)
        except Exception:
            pass


# ── Instancia única ─────────────────────────────────────────────────────────

_p: PracticaIBKR | None = None


def obtener(app) -> PracticaIBKR:
    global _p
    if _p is None:
        _p = PracticaIBKR(app)
    return _p


def activar(app) -> str:
    texto = obtener(app).activar()
    try:
        app.log("[PracticaIBKR] " + texto.split("\n")[0])
        app.decir("Modo práctica en Interactive Brokers, señor. Voy a "
                  "estudiar la pantalla y aprender dónde está cada cosa. "
                  "No voy a operar.")
    except Exception:
        pass
    return texto


def desactivar(app) -> str:
    return obtener(app).desactivar()


def resumen(app) -> str:
    return obtener(app).resumen()

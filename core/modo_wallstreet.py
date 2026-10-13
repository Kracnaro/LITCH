"""
modo_wallstreet.py — Litch operando Interactive Brokers por su cuenta.

Es el equivalente al modo autónomo de IQ Option, pero para acciones. Y es
DISTINTO por dentro, porque el juego es distinto:

    IQ Option (binarias)          Wall Street (acciones)
    ────────────────────          ──────────────────────
    ¿sube o baja la vela?         ¿hay una tendencia que aprovechar?
    vencimiento fijo              usted decide cuándo sale
    pierde el 100% al fallar      pierde lo que marque el stop
    decenas de operaciones/día    unas pocas por semana
    velocidad                     paciencia

Copiar el motor de binarias a acciones sería el error clásico: operar
mucho, sin stop y sin plan de salida. Aquí se opera POCO y con las tres
decisiones tomadas de antemano.

EL CICLO (cada 3 minutos, con el mercado abierto)
─────────────────────────────────────────────────
  1. Comprobar que se puede operar (cuenta simulada, riesgo, horario).
  2. Recorrer la lista de vigilancia.
  3. Analizar cada activo con datos reales suyos.
  4. Si hay consenso Y la memoria no lo desaconseja → preparar bracket.
  5. Verificar el bracket antes de mandarlo.
  6. Mandarlo por API (entra atómico) y comprobar que fue aceptado.
  7. Anotar todo para aprender del resultado.

LÍMITES QUE NO SE SALTAN
────────────────────────
  · Solo cuenta simulada verificada por la API (empieza por DU).
  · Máximo de operaciones por día.
  · Una posición por símbolo: nada de doblar apuestas.
  · Riesgo por operación limitado por el cortacircuito.
  · Nunca en los primeros ni últimos minutos de sesión.
  · Si algo no se puede verificar, no se opera. La duda no es permiso.
"""

from __future__ import annotations

import threading
import time

# ── Parámetros del modo ─────────────────────────────────────────────────────

INTERVALO_CICLO = 180          # segundos entre revisiones (3 minutos)
MAX_OPS_DIA = 3                # operaciones nuevas por día como máximo
MAX_POSICIONES = 3             # posiciones abiertas a la vez
MIN_MIN_TRAS_APERTURA = 30     # no operar los primeros 30 min
MIN_MIN_ANTES_CIERRE = 30      # ni los últimos 30

VIGILANCIA = ["SPY", "VOO", "QQQ", "AAPL", "MSFT"]


class ModoWallStreet(threading.Thread):
    """El piloto automático de Litch para acciones."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchWallStreet")
        self.app = app
        self._parar = threading.Event()
        self.activo = False
        self.ejecutar_real = False      # False = solo prepara y avisa
        self.ops_hoy = 0
        self._dia = time.strftime("%Y-%m-%d")
        self._ultimo_aviso = {}
        self.historial: list[dict] = []

    # ── Encendido y apagado ─────────────────────────────────────────────────

    def activar(self, ejecutar: bool = False) -> str:
        """Enciende el modo. Por defecto solo AVISA, no ejecuta."""
        listo, motivo = self._puede_arrancar()
        if not listo:
            return motivo

        self.ejecutar_real = bool(ejecutar)
        self.activo = True
        if not self.is_alive():
            self.start()

        modo = ("EJECUTANDO operaciones reales en la cuenta simulada"
                if ejecutar else
                "solo AVISANDO: le preparo cada operación y usted decide")
        self.app.log(f"[WallStreet] Modo activado — {modo}")

        return (f"Modo Wall Street activado, señor. Estoy {modo}.\n\n"
                f"Vigilo {', '.join(VIGILANCIA)} cada "
                f"{INTERVALO_CICLO // 60} minutos.\n"
                f"Máximo {MAX_OPS_DIA} operaciones al día y "
                f"{MAX_POSICIONES} posiciones a la vez.\n"
                f"No opero en los primeros ni últimos "
                f"{MIN_MIN_TRAS_APERTURA} minutos de sesión: ahí el precio "
                f"se mueve por motivos que no sé leer.\n\n"
                f"Aquí se opera poco y bien. Si algún día no le doy ninguna "
                f"señal, no es que esté roto: es que no había nada claro.")

    def desactivar(self) -> str:
        self.activo = False
        self.app.log("[WallStreet] Modo desactivado.")
        return (f"Modo Wall Street apagado, señor. Hoy preparé "
                f"{self.ops_hoy} operación(es).")

    def parar(self):
        self._parar.set()

    # ── ¿Se puede arrancar? ─────────────────────────────────────────────────

    def _puede_arrancar(self) -> tuple[bool, str]:
        """Las condiciones mínimas. Sin ellas ni se enciende."""
        try:
            from . import rutinas_tws as rt
            r = rt.revision_apertura(self.app)
            if not r.ok:
                return False, ("No puedo arrancar todavía:\n\n" + r.texto())
        except Exception as e:
            return False, f"No pude hacer la revisión previa: {e}"
        return True, ""

    # ── El ciclo ────────────────────────────────────────────────────────────

    def run(self):
        self._parar.wait(20)      # margen para que Litch termine de arrancar
        while not self._parar.is_set():
            if self.activo:
                try:
                    self._ciclo()
                except Exception as e:
                    self.app.log(f"[WallStreet] Error en el ciclo: {e}")
            self._parar.wait(INTERVALO_CICLO)

    def _ciclo(self):
        from . import motor_acciones as ma

        # Día nuevo, cuenta a cero
        hoy = time.strftime("%Y-%m-%d")
        if hoy != self._dia:
            self._dia = hoy
            self.ops_hoy = 0
            self._ultimo_aviso.clear()
            self.app.log("[WallStreet] Día nuevo. Contador de operaciones "
                         "a cero.")

        # 1) Horario, con los márgenes de apertura y cierre
        abierto, detalle = ma.mercado_abierto()
        if not abierto:
            self._avisar_una_vez("cerrado", f"Mercado cerrado. {detalle}")
            return

        try:
            ny = ma._ahora_ny()
            minutos = ny.hour * 60 + ny.minute
        except Exception:
            minutos = 700

        if minutos < 570 + MIN_MIN_TRAS_APERTURA:
            self._avisar_una_vez(
                "apertura",
                f"Primeros {MIN_MIN_TRAS_APERTURA} minutos de sesión: "
                f"observo pero no opero. Aquí el precio se mueve por "
                f"órdenes acumuladas de la noche, no por nada que yo "
                f"pueda leer.")
            return
        if minutos > 960 - MIN_MIN_ANTES_CIERRE:
            self._avisar_una_vez(
                "cierre",
                f"Últimos {MIN_MIN_ANTES_CIERRE} minutos: no abro nada "
                f"nuevo. Entrar aquí es heredar el riesgo de toda la noche "
                f"sin tiempo de reaccionar.")
            return

        # 2) Cupo diario
        if self.ops_hoy >= MAX_OPS_DIA:
            self._avisar_una_vez(
                "cupo",
                f"Ya preparé {self.ops_hoy} operaciones hoy, que es mi "
                f"límite. El límite no está para castigarle: está para que "
                f"un mal día no se convierta en un día terrible.")
            return

        # 3) Cortacircuito de riesgo
        try:
            from . import guardias_riesgo as gr
            cc = gr.cortacircuito(self.app)
            if cc.get("nivel") == "ROJO":
                self._avisar_una_vez(
                    "rojo",
                    f"Cortacircuito en ROJO: {cc.get('motivo','')}. "
                    f"Hoy no opero más.")
                return
        except Exception:
            pass

        # 3.5) Regla PDT — con cuenta pequeña, 4 day trades en 5 días
        #      hábiles bloquean la cuenta 90 días. Y un bracket que salta
        #      el mismo día cuenta como uno, sin pretenderlo.
        try:
            from . import guardia_pdt as pdt
            v = pdt.puede_operar(self.app)
            if not v.get("ok"):
                self._avisar_una_vez("pdt", v.get("mensaje", ""), cada=7200)
                return
            if v.get("mensaje", "").startswith("⚠"):
                self._avisar_una_vez("pdt_aviso", v["mensaje"], cada=7200)
        except Exception:
            pass

        # 4) Posiciones ya abiertas
        abiertas = self._posiciones_abiertas()
        if len(abiertas) >= MAX_POSICIONES:
            self._avisar_una_vez(
                "llenas",
                f"Tengo {len(abiertas)} posiciones abiertas, que es el "
                f"máximo. No abro más hasta que se cierre alguna.")
            return

        # 5) Recorrer la lista de vigilancia
        for simbolo in VIGILANCIA:
            if not self.activo or self._parar.is_set():
                return
            if self.ops_hoy >= MAX_OPS_DIA:
                return
            if simbolo in abiertas:
                continue      # ya estamos dentro: no se dobla
            try:
                self._revisar(simbolo)
            except Exception as e:
                self.app.log(f"[WallStreet] {simbolo}: {e}")
            time.sleep(2)     # respeto al ritmo de peticiones

    # ── Revisar un símbolo ──────────────────────────────────────────────────

    def _revisar(self, simbolo: str):
        from . import rutinas_tws as rt

        r = rt.preparar_operacion_verificada(self.app, simbolo,
                                             ejecutar=False)
        if not r.ok:
            # Abstenerse es normal y no merece ruido
            return

        plan = getattr(r, "plan", {})
        an = plan.get("analisis", {})
        accion = "COMPRA" if an.get("direccion") == "COMPRA" else "VENTA"

        aviso = (
            f"Señor, encontré una operación en {simbolo}.\n"
            f"{accion} {plan.get('cantidad')} acciones.\n"
            f"Entrada {plan.get('entrada')} | stop {plan.get('stop')} | "
            f"objetivo {plan.get('objetivo')}.\n"
            f"Arriesga {plan.get('riesgo_dolares')} dólares para ganar "
            f"aproximadamente el doble.\n"
            f"Razones: {'; '.join(an.get('razones', [])[:3])}")

        self.app.log("[WallStreet] " + aviso.replace("\n", " "))
        try:
            self.app.decir(f"Señor, tengo una operación en {simbolo}. "
                           f"{accion} de {plan.get('cantidad')} acciones, "
                           f"con stop en {plan.get('stop')}.")
        except Exception:
            pass

        self.historial.append({"ts": time.strftime("%H:%M"),
                               "simbolo": simbolo, "plan": plan})
        self.ops_hoy += 1

        # El piloto autónomo lleva la cuenta: preparar 10 operaciones
        # coherentes es lo que hace falta para pasar de Ensayo a ejecutar.
        try:
            from . import piloto_autonomo as _pa
            _pa.registrar_preparada(self.app)
        except Exception:
            pass

        if not self.ejecutar_real:
            self.app.log("[WallStreet] Solo aviso: no ejecuto. Para que "
                         "opere de verdad dígame «modo Wall Street "
                         "ejecutando».")
            return

        # Ejecución: por API, con verificación posterior
        r2 = rt.preparar_operacion_verificada(self.app, simbolo,
                                              ejecutar=True)
        self.app.log("[WallStreet] " + r2.texto().replace("\n", " | "))
        if r2.ok:
            try:
                self.app.decir(f"Operación enviada en {simbolo}, con su "
                               f"stop y su objetivo puestos.")
            except Exception:
                pass
            self._recordar(simbolo, plan, an)

    # ── Memoria ─────────────────────────────────────────────────────────────

    def _recordar(self, simbolo, plan, an):
        """Anota la operación para poder aprender del resultado."""
        try:
            from . import memoria_acciones as mem
            # El método es `registrar` (comprobado en memoria_acciones.py),
            # y solo acepta argumentos por nombre.
            op_id = mem.obtener().registrar(
                simbolo=simbolo,
                direccion=an.get("direccion", "COMPRA"),
                entrada=float(plan.get("entrada") or 0),
                stop=float(plan.get("stop") or 0),
                objetivo=float(plan.get("objetivo") or 0),
                cantidad=int(plan.get("cantidad") or 0),
                contexto=plan.get("contexto_setup", {}))
            self.app.log(f"[WallStreet] Operación anotada en memoria "
                         f"({op_id}). Cuando se cierre aprenderé de ella.")
        except Exception as e:
            self.app.log(f"[WallStreet] No pude anotar la operación: {e}")

    # ── Utilidades ──────────────────────────────────────────────────────────

    def _posiciones_abiertas(self) -> set:
        br = getattr(self.app, "broker_ibkr", None)
        if br is None or not getattr(br, "esta_conectado", False):
            return set()
        try:
            return {p.get("simbolo") for p in (br.posiciones() or [])
                    if p.get("cantidad")}
        except Exception:
            return set()

    def _avisar_una_vez(self, clave: str, texto: str, cada: int = 1800):
        """Evita repetir el mismo aviso cada tres minutos."""
        ahora = time.time()
        if ahora - self._ultimo_aviso.get(clave, 0) < cada:
            return
        self._ultimo_aviso[clave] = ahora
        self.app.log("[WallStreet] " + texto)

    # ── Informe ─────────────────────────────────────────────────────────────

    def estado(self) -> str:
        if not self.activo:
            return ("Modo Wall Street apagado, señor. Dígame «activa el "
                    "modo Wall Street» y me pongo a vigilar.")
        from . import motor_acciones as ma
        _, horario = ma.mercado_abierto()
        abiertas = self._posiciones_abiertas()

        lineas = [
            "MODO WALL STREET — activo",
            f"  Ejecuto: {'sí, en cuenta simulada' if self.ejecutar_real else 'no, solo aviso'}",
            f"  Vigilo: {', '.join(VIGILANCIA)}",
            f"  Operaciones hoy: {self.ops_hoy} de {MAX_OPS_DIA}",
            f"  Posiciones abiertas: {len(abiertas)} de {MAX_POSICIONES}"
            + (f" ({', '.join(sorted(abiertas))})" if abiertas else ""),
            f"  Mercado: {horario}",
        ]
        if self.historial:
            lineas.append("  Últimas señales:")
            for h in self.historial[-3:]:
                p = h["plan"]
                lineas.append(f"    {h['ts']} {h['simbolo']}: "
                              f"entrada {p.get('entrada')}, "
                              f"stop {p.get('stop')}")
        else:
            lineas.append("  Sin señales todavía. Eso es normal: aquí se "
                          "opera poco.")
        return "\n".join(lineas)


# ── Instancia única ─────────────────────────────────────────────────────────

_modo: ModoWallStreet | None = None


def obtener(app) -> ModoWallStreet:
    global _modo
    if _modo is None:
        _modo = ModoWallStreet(app)
    return _modo


def activar(app, ejecutar: bool = False) -> str:
    return obtener(app).activar(ejecutar)


def desactivar(app) -> str:
    return obtener(app).desactivar()


def estado(app) -> str:
    return obtener(app).estado()

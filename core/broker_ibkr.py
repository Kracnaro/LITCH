"""
Interactive Brokers (IBKR) — integración programática completa.

Litch se conecta a TWS (Trader Workstation) o IB Gateway y opera
acciones, forex, futuros y opciones REALES vía la API oficial de IBKR.

━━━ CONFIGURACIÓN (una sola vez) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1. Descargar TWS (Trader Workstation) o IB Gateway desde ibkr.com
 2. Abrir TWS → Configuración Global → API → Habilitar API Socket
 3. Puerto live: 7496 | papel (paper): 7497
    IB Gateway live: 4001 | papel: 4002
 4. Activar "Allow connections from localhost only" (seguridad)
 5. pip install ib_insync

━━━ DIFERENCIAS vs IQ Option ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 • IQ Option: opciones binarias  → ganas/pierdes monto fijo en 60s
 • IBKR:      acciones reales    → compras/vendes a precio de mercado
 • Rentabilidad no garantizada:  P&L depende de movimiento del precio
 • Sin vencimiento automático:   debes cerrar la posición tú mismo
 • Riesgo real de pérdida total: usa stop-loss siempre

━━━ ÓRDENES DISPONIBLES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 • MARKET      — ejecuta al precio actual (más rápido, posible slippage)
 • LIMIT       — ejecuta solo al precio indicado o mejor
 • STOP        — activa al alcanzar el stop; convierte en MARKET
 • STOP_LIMIT  — activa al stop; ejecuta solo al límite indicado
 • TRAILING    — stop que sigue al precio a distancia fija

━━━ GESTIÓN DE RIESGO OBLIGATORIA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 • Nunca operar más del 1-2% del capital por trade
 • Siempre acompañar orden de entrada con stop-loss
 • En papel (paper) primero — solo pasar a live tras 3 meses de práctica
"""

import json
import os
import threading
import time
from typing import Optional

from . import memoria as mem_mod
from . import datos_mercado as _dm

# ── Dependencia opcional: ib_insync ─────────────────────────────────────────
# NOTA: ib_insync (vía eventkit) pide un event loop al importarse. En Python
# 3.12+ eso está deprecado y en 3.14 lanza RuntimeError, tumbando el arranque.
# Solución: crear el loop ANTES de importar y capturar CUALQUIER excepción
# (no solo ImportError) para que Litch arranque siempre.
try:
    import asyncio as _asyncio_ib
    try:
        _asyncio_ib.get_event_loop()
    except Exception:
        # No hay loop en este hilo: crear uno para que eventkit no falle
        _asyncio_ib.set_event_loop(_asyncio_ib.new_event_loop())
except Exception:
    pass

# Se prefiere ib_async sobre ib_insync.
#
# POR QUÉ, Y ES IMPORTANTE: ib_insync ya no está mantenido (su autor
# falleció en 2024) y se rompe en Python 3.12+ por el asunto del bucle de
# eventos. ib_async es la continuación mantenida por la comunidad, con la
# misma API. Se intenta primero, y si no está, se cae a ib_insync para no
# dejar sin funcionar a quien todavía lo tenga instalado.
_LIB_IB = ""
try:
    from ib_async import (IB, Stock, Forex, Future, Option,
                          MarketOrder, LimitOrder, StopOrder,
                          StopLimitOrder, Order, Contract,
                          util as _ib_util)
    _IB_OK = True
    _LIB_IB = "ib_async"
except Exception:
    try:
        from ib_insync import (IB, Stock, Forex, Future, Option,
                               MarketOrder, LimitOrder, StopOrder,
                               StopLimitOrder, Order, Contract,
                               util as _ib_util)
        _IB_OK = True
        _LIB_IB = "ib_insync (obsoleta — instale ib_async)"
    except Exception:
        # Incluye ImportError y RuntimeError (incompatibilidad Python 3.14)
        _IB_OK = False
        _LIB_IB = ""
        # Stubs mínimos para que el resto del código no explote al importar
        class _Stub:
            def __init__(self, *a, **kw): pass
        IB = Stock = Forex = Future = Option = _Stub
        MarketOrder = LimitOrder = StopOrder = StopLimitOrder = Order = Contract = _Stub

# ── Constantes ───────────────────────────────────────────────────────────────
_PUERTOS = {
    # Puertos OFICIALES de IBKR (corregidos — antes estaban desfasados):
    #   TWS real = 7496 · TWS paper = 7497
    #   Gateway real = 4001 · Gateway paper = 4002
    "tws_live":     7496,
    "tws_paper":    7497,
    "gateway_live": 4001,
    "gateway_paper":4002,
}

_EXCHANGES_DEFAULT = {
    # Acciones US
    "AAPL": "SMART", "MSFT": "SMART", "TSLA": "SMART", "NVDA": "SMART",
    "AMZN": "SMART", "GOOGL": "SMART", "META": "SMART", "AMD": "SMART",
    "NFLX": "SMART", "SPY": "SMART",  "QQQ": "SMART",  "IWM": "SMART",
    "BABA": "SMART", "COIN": "SMART", "PLTR": "SMART", "SOFI": "SMART",
    # ETFs índice
    "VTI": "SMART", "VOO": "SMART", "SCHD": "SMART", "VXUS": "SMART",
    # Futuros (CME)
    "/ES": "CME", "/NQ": "CME", "/YM": "CBOT", "/RTY": "CME",
    "/GC": "COMEX", "/SI": "COMEX", "/CL": "NYMEX", "/NG": "NYMEX",
}

_FOREX_PARES = {
    "EUR/USD": ("EUR", "USD"), "GBP/USD": ("GBP", "USD"),
    "USD/JPY": ("USD", "JPY"), "AUD/USD": ("AUD", "USD"),
    "USD/CAD": ("USD", "CAD"), "USD/CHF": ("USD", "CHF"),
    "NZD/USD": ("NZD", "USD"), "EUR/GBP": ("EUR", "GBP"),
    "XAU/USD": ("XAU", "USD"),  # oro spot
}

# Guía de tipos de activo para educar a Litch
GUIA_ACTIVOS = {
    "acciones":  "Partes de propiedad de una empresa. Suben cuando la empresa crece.",
    "etfs":      "Canasta de acciones que cotiza como una sola. Diversificación automática.",
    "opciones":  "Derecho (no obligación) de comprar/vender a precio fijo. Alto riesgo/beneficio.",
    "futuros":   "Contrato de compra/venta futura a precio acordado. Usado en commodities.",
    "forex":     "Intercambio de divisas (EUR/USD, etc.). Muy líquido, 24/5.",
}

GUIA_GESTION_RIESGO = {
    "regla_1pct": "Nunca arriesgar más del 1% del capital en un solo trade.",
    "stop_loss":  "Orden automática que cierra la posición si el precio cae X%.",
    "take_profit":"Orden que cierra en ganancia cuando el precio sube X%.",
    "ratio":      "Ratio riesgo/beneficio mínimo recomendado: 1:2 (arriesgas 1 para ganar 2).",
    "diversif":   "No concentrar todo en un solo activo ni sector.",
    "apalancam":  "El apalancamiento multiplica ganancias Y pérdidas. Usarlo con cuidado extremo.",
}


class BrokerIBKR:
    """
    Cliente completo de Interactive Brokers para Litch.

    Flujo normal:
        ibkr = BrokerIBKR(app)
        ibkr.conectar(modo="paper")          # práctica sin riesgo
        ibkr.comprar("AAPL", 1)             # compra 1 acción de Apple a mercado
        ibkr.vender("AAPL", 1, precio=195)  # venta límite a $195
        ibkr.posiciones()                    # qué tengo ahora
        ibkr.desconectar()
    """

    def __init__(self, app):
        self.app  = app
        self._ib  = IB() if _IB_OK else None
        self._lock          = threading.Lock()
        self._conectado     = False
        self._modo          = "paper"     # "paper" o "live"
        self._client_id     = 10          # ID único por sesión
        self._ultimo_order_id = 0
        # Verificación real de la cuenta, rellenada al conectar.
        # None = todavía no lo sé, y "no lo sé" nunca cuenta como "es segura".
        self._cuentas: list = []
        self._es_paper = None

        # ── Reconexión automática ───────────────────────────────────────────
        # TWS corta la API una vez al día en su reinicio nocturno. Sin esto,
        # Litch amanece desconectado y con posiciones abiertas que nadie
        # vigila — que es justo el escenario que hay que evitar.
        #
        # El manejador NO llama a conectar() directamente: eso provocaría
        # recursión infinita si la reconexión falla (el evento se vuelve a
        # emitir y se llama otra vez). Va en otro hilo, con cerrojo.
        self._reconectando = False
        self._quiere_conexion = False
        self._reconexiones = 0
        self._eventos_puestos = False
        self._historial: list[dict] = []  # historial de órdenes
        self._ruta_historial = os.path.join(
            mem_mod.ruta_memoria_ap(), "ibkr_historial.json")
        self._cargar_historial()

    # ── Conexión ─────────────────────────────────────────────────────────────

    def conectar(self, modo: str = "paper",
                 host: str = "127.0.0.1",
                 client_id: int = None) -> bool:
        """
        Conecta a TWS o IB Gateway.

        modo : "paper" (práctica, sin riesgo real)
               "live"  (cuenta real — solo tras largo período de práctica)
        """
        if not _IB_OK:
            self.app.log("[IBKR] ib_insync no instalado. Ejecuta: pip install ib_insync")
            return False

        self._modo = modo
        puerto = _PUERTOS["tws_paper" if modo == "paper" else "tws_live"]
        if client_id:
            self._client_id = client_id

        self._quiere_conexion = True
        try:
            self.app.log(f"[IBKR] Conectando a TWS/{modo.upper()} en "
                         f"{host}:{puerto} con {_LIB_IB}...")
            # ⛔ NUNCA llamar aquí a _ib_util.startLoop().
            #
            # startLoop() aplica nest_asyncio, que PARCHEA asyncio de forma
            # GLOBAL para permitir bucles anidados. Está pensado para
            # Jupyter. En Litch destroza cualquier otro código async del
            # proceso — en concreto la voz (edge_tts usa asyncio.run), que
            # empezaba a fallar con «Timeout should be used inside a task».
            #
            # Se hizo evidente en el registro del usuario: el mismo error
            # aparecía en la conexión a IBKR y en el TTS. Era el mismo
            # parche rompiendo las dos cosas.
            #
            # En su lugar, este hilo tiene su PROPIO bucle de eventos,
            # aislado del resto del programa.
            self._asegurar_loop()
            self._ib.connect(host, puerto, clientId=self._client_id, timeout=10)
            self._conectado = True
            self._poner_eventos()
            cuentas = list(self._ib.wrapper.accounts or [])
            self.app.log(f"[IBKR] ✓ Conectado. Cuentas: {cuentas}")

            # ── VERIFICACIÓN DE CUENTA ──────────────────────────────────────
            # No basta con que nos hayan pedido modo "paper": hay que
            # comprobar con la propia cuenta que devuelve el servidor. Las
            # simuladas de IBKR empiezan por DU; las reales por U. Si pedimos
            # práctica y aparece una real, nos desconectamos en el acto.
            self._cuentas = cuentas
            self._es_paper = None
            if cuentas:
                self._es_paper = all(str(c).upper().startswith("DU")
                                     for c in cuentas)

            if modo == "paper":
                if self._es_paper is False:
                    reales = [c for c in cuentas
                              if not str(c).upper().startswith("DU")]
                    self.app.log(f"[IBKR] ⛔ Pedí cuenta de práctica pero TWS "
                                 f"responde con cuenta REAL: {reales}. "
                                 f"Me desconecto.")
                    self.app.decir("Alto. Pedí la cuenta simulada y el "
                                   "servidor responde con una cuenta real. "
                                   "Me desconecto por seguridad. Revise en "
                                   "qué cuenta inició sesión en TWS.")
                    self.desconectar()
                    return False
                if self._es_paper is None:
                    self.app.log("[IBKR] ⚠ Conectado pero TWS no me dice el "
                                 "número de cuenta. No puedo confirmar que "
                                 "sea simulada: trataré todo como delicado.")
                else:
                    self.app.log(f"[IBKR] ✓ Cuenta {cuentas[0]} verificada "
                                 f"como SIMULADA. Ningún trade es real.")
            else:
                self.app.log("[IBKR] ⚠ MODO LIVE — operaciones con dinero REAL.")
                self.app.decir("Atención. Conectado a Interactive Brokers en modo real. "
                               "Cada orden usa dinero verdadero.")
            return True
        except Exception as e:
            self._conectado = False
            self.app.log(f"[IBKR] Error al conectar: {e}")
            self.app.log(self._diagnostico_conexion(e, host, puerto))
            return False

    # ── Diagnóstico honesto de por qué no conecta ────────────────────────────

    @staticmethod
    def _diagnostico_conexion(error, host: str, puerto: int) -> str:
        """Traduce el fallo a algo accionable.

        "TimeoutError" no le dice nada a nadie. Estas son las cuatro causas
        reales, en el orden en que ocurren de verdad.
        """
        e = str(error).lower()
        pasos = [f"[IBKR] No pude conectar a {host}:{puerto}. Repase esto:"]

        if "timeout" in e or "timed out" in e:
            pasos += [
                "  1. ¿Está TWS abierto y con la sesión iniciada? La API no "
                "responde en la pantalla de login.",
                "  2. En TWS: File → Global Configuration → API → Settings, "
                "marque «Enable ActiveX and Socket Clients».",
                f"  3. En esa misma pantalla, «Socket port» debe ser {puerto} "
                f"({'simulada' if puerto == 7497 else 'REAL'}).",
                "  4. En «Trusted IPs» añada 127.0.0.1.",
            ]
        elif "refused" in e or "10061" in e:
            pasos += [
                f"  · El puerto {puerto} está cerrado: TWS no escucha ahí.",
                "  · Casi siempre es que «Enable ActiveX and Socket Clients» "
                "está desmarcado, o que TWS aún no terminó de arrancar.",
                "  · Si inició sesión en la cuenta REAL, el puerto sería el "
                "7496, no el 7497.",
            ]
        elif "client id" in e or "clientid" in e or "326" in e:
            pasos += [
                "  · Ese client ID ya está en uso. Otro programa (o una "
                "instancia mía anterior) sigue conectado.",
                "  · Cierre lo demás o pruebe con otro ID.",
            ]
        else:
            pasos += [
                "  1. TWS abierto y con sesión iniciada.",
                "  2. API habilitada en Global Configuration → API → Settings.",
                f"  3. Puerto {puerto}.",
                "  4. 127.0.0.1 en Trusted IPs.",
            ]
        return "\n".join(pasos)

    def verificar_cuenta(self) -> dict:
        """¿Con qué cuenta estoy hablando de verdad? Consulta directa.

        Esta es la fuente de verdad: no el título de la ventana, no lo que
        pidió el usuario, sino lo que responde el servidor de IBKR.
        """
        r = {"conectado": False, "cuentas": [], "es_paper": None,
             "mensaje": ""}
        if not self.esta_conectado:
            r["mensaje"] = ("No estoy conectado a Interactive Brokers, señor. "
                            "Dígame 'conecta con IBKR'.")
            return r
        try:
            cuentas = list(self._ib.wrapper.accounts or [])
        except Exception as e:
            r["mensaje"] = f"Conectado, pero no pude leer las cuentas: {e}"
            return r

        r["conectado"] = True
        r["cuentas"] = cuentas
        if not cuentas:
            r["mensaje"] = ("Conectado, pero TWS no me devuelve ninguna "
                            "cuenta. Sin eso no confirmo si es simulada.")
            return r

        r["es_paper"] = all(str(c).upper().startswith("DU") for c in cuentas)
        if r["es_paper"]:
            r["mensaje"] = (f"Conectado a la cuenta {cuentas[0]}, que es "
                            f"SIMULADA (empieza por DU). Aquí no hay dinero "
                            f"real: es el sitio correcto para practicar.")
        else:
            r["mensaje"] = (f"⚠ Conectado a {', '.join(cuentas)}. Esto NO es "
                            f"una cuenta simulada: las de práctica empiezan "
                            f"por DU. Cada orden movería dinero de verdad.")
        return r

    # ── Bucle de eventos propio ──────────────────────────────────────────────

    @staticmethod
    def _asegurar_loop() -> None:
        """Da a ESTE hilo su propio bucle de eventos, sin tocar los demás.

        ib_async necesita un bucle en el hilo desde el que se conecta. Si se
        parchea el global (startLoop / nest_asyncio) se rompe todo lo demás
        que use asyncio en el proceso — la voz, por ejemplo.
        """
        try:
            import asyncio
            try:
                bucle = asyncio.get_event_loop_policy().get_event_loop()
                if bucle.is_closed():
                    raise RuntimeError("cerrado")
            except Exception:
                asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:
            pass

    # ── Reconexión automática ────────────────────────────────────────────────

    def _poner_eventos(self) -> None:
        """Engancha el manejador de desconexión (una sola vez)."""
        if self._eventos_puestos or not self._ib:
            return
        try:
            self._ib.disconnectedEvent += self._al_desconectar
            self._eventos_puestos = True
        except Exception as e:
            self.app.log(f"[IBKR] No pude registrar el evento de "
                         f"desconexión: {e}")

    def _al_desconectar(self) -> None:
        """TWS se ha ido. Si no fui yo quien cortó, reconecto."""
        if not self._quiere_conexion:
            return          # la desconexión la pedí yo
        if self._reconectando:
            return
        self._conectado = False
        self.app.log("[IBKR] ⚠ Conexión perdida (¿reinicio nocturno de "
                     "TWS?). Reconectando en segundo plano…")
        threading.Thread(target=self._reconectar, daemon=True,
                         name="LitchIBKRReconectar").start()

    def _reconectar(self) -> None:
        """Reintentos con espera creciente, fuera del bucle de eventos."""
        with self._lock:
            if self._reconectando:
                return
            self._reconectando = True
        try:
            time.sleep(5)      # dejar que TWS termine de reiniciar
            espera = 5
            for intento in range(1, 13):      # ~10 minutos de insistencia
                if not self._quiere_conexion:
                    return
                try:
                    if self.conectar(modo=self._modo):
                        self._reconexiones += 1
                        self.app.log(f"[IBKR] ✓ Reconectado (intento "
                                     f"{intento}). Reconexiones hoy: "
                                     f"{self._reconexiones}.")
                        try:
                            self.app.decir("Se restableció la conexión con "
                                           "Interactive Brokers, señor.")
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
                time.sleep(espera)
                espera = min(espera * 2, 120)      # hasta 2 minutos

            self.app.log("[IBKR] ✗ No pude reconectar tras 12 intentos. "
                         "Si tiene posiciones abiertas, revíselas a mano en "
                         "TWS: sus brackets siguen puestos en el servidor de "
                         "IBKR aunque yo no esté conectado.")
            try:
                self.app.decir("No consigo reconectar con Interactive "
                               "Brokers. Sus órdenes de stop siguen puestas "
                               "en el servidor, pero yo ya no las vigilo. "
                               "Conviene que lo mire.")
            except Exception:
                pass
        finally:
            self._reconectando = False

    def desconectar(self) -> None:
        # Desconexión pedida: NO debe disparar la reconexión automática
        self._quiere_conexion = False
        if self._ib and self._conectado:
            try:
                self._ib.disconnect()
            except Exception:
                pass
        self._conectado = False
        self.app.log("[IBKR] Desconectado de TWS.")

    @property
    def esta_conectado(self) -> bool:
        if not _IB_OK or not self._ib:
            return False
        try:
            return self._ib.isConnected()
        except Exception:
            return False

    # ── Contratos ─────────────────────────────────────────────────────────────

    def _contrato(self, simbolo: str) -> Optional[object]:
        """
        Crea el Contract correcto según el símbolo.
        Soporta acciones (AAPL), forex (EUR/USD) y futuros (/ES).
        """
        if not _IB_OK:
            return None
        s = simbolo.upper().strip()
        if "/" in s and s in _FOREX_PARES:
            base, quote = _FOREX_PARES[s]
            return Forex(base + quote)
        if s.startswith("/"):
            sym = s[1:]
            ex  = _EXCHANGES_DEFAULT.get(s, "CME")
            return Future(sym, exchange=ex)
        ex = _EXCHANGES_DEFAULT.get(s, "SMART")
        return Stock(s, ex, "USD")

    # ── Cotización ────────────────────────────────────────────────────────────

    def cotizacion(self, simbolo: str) -> Optional[dict]:
        """
        Devuelve precio actual, bid, ask y volumen del símbolo.
        Requiere suscripción de datos de mercado en TWS.
        """
        if not self.esta_conectado:
            self.app.log("[IBKR] No conectado. Llama conectar() primero.")
            return None
        contrato = self._contrato(simbolo)
        if not contrato:
            return None
        ticker = None
        try:
            # Se pide dato EN VIVO explícitamente. Si la cuenta no tiene
            # suscripción, TWS no protesta: manda NaN. Por eso después se
            # audita el resultado en vez de confiar en la petición.
            _dm.pedir_tipo(self._ib, _dm.EN_VIVO)

            ticker = self._ib.reqMktData(contrato, "", False, False)
            # Medio segundo no alcanza en símbolos poco líquidos. Se espera
            # hasta 3 s pero se sale en cuanto llega un precio real.
            espera = 0.0
            while espera < 3.0:
                self._ib.sleep(0.25)
                espera += 0.25
                if _dm.primer_valido(getattr(ticker, "last", None),
                                     getattr(ticker, "close", None)) is not None:
                    break

            a = _dm.auditar_ticker(ticker, _dm.leer_tipo(self._ib))
            if not a["hay_precio"]:
                self.app.log(f"[IBKR] {simbolo}: {a['motivo']}")
                return None
            if not a["ejecutable"]:
                # Se devuelve el dato — sirve para mirar — pero marcado,
                # para que quien vaya a ejecutar sepa que no puede.
                self.app.log(f"[IBKR] Aviso {simbolo}: {a['motivo']}")

            return {
                "simbolo":    simbolo,
                "precio":     a["precio"],
                "bid":        a["bid"],
                "ask":        a["ask"],
                "volumen":    a["volumen"],
                "spread":     a["spread"],
                "tipo_dato":  a["tipo"],
                "en_vivo":    a["ejecutable"],
                "aviso":      a["motivo"],
                "ts":         time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            self.app.log(f"[IBKR] Error cotización {simbolo}: {e}")
            return None
        finally:
            # IBKR limita a ~100 suscripciones simultáneas. Sin este
            # cancelMktData, Litch se queda sin líneas tras 100 consultas
            # y deja de ver precios sin dar ningún error.
            if ticker is not None:
                try:
                    self._ib.cancelMktData(contrato)
                except Exception:
                    pass

    # ── Órdenes ───────────────────────────────────────────────────────────────

    def comprar(self, simbolo: str, cantidad: float,
                precio: float = None,
                stop: float = None,
                tipo: str = "MARKET") -> Optional[dict]:
        """
        Coloca orden de compra.

        simbolo  : "AAPL", "EUR/USD", "/ES", etc.
        cantidad : número de acciones / contratos / unidades forex
        precio   : precio límite (solo para LIMIT o STOP_LIMIT)
        stop     : precio de stop-loss automático (muy recomendado)
        tipo     : "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT"

        Ejemplo:
            ibkr.comprar("AAPL", 1, stop=185.0)  # compra 1, stop en $185
        """
        return self._orden("BUY", simbolo, cantidad, precio, stop, tipo)

    def vender(self, simbolo: str, cantidad: float,
               precio: float = None,
               stop: float = None,
               tipo: str = "MARKET") -> Optional[dict]:
        """
        Coloca orden de venta.

        Si no tienes la posición abierta, esto abre una venta en corto
        (short selling — IBKR lo permite con margen suficiente).
        """
        return self._orden("SELL", simbolo, cantidad, precio, stop, tipo)

    @staticmethod
    def _redondear_precio(precio):
        """Redondea el precio a los decimales que IBKR acepta.

        Regla del exchange (hallazgo del auditor): 2 decimales si el
        precio es >= 1 USD; 4 decimales si es < 1 USD. Enviar más
        decimales = rechazo instantáneo de la orden.
        """
        if precio is None:
            return None
        try:
            p = float(precio)
            return round(p, 2) if p >= 1.0 else round(p, 4)
        except Exception:
            return precio

    @staticmethod
    def _riesgo_orden_mercado() -> str:
        """Avisa si este es un mal momento para una orden a mercado.

        Una orden a mercado acepta el precio que haya. Cuando el mercado
        está cerrado o en los minutos de apertura y cierre, ese precio
        puede estar mucho más lejos de lo que se ve en pantalla.
        """
        try:
            from . import motor_acciones as _ma
            abierto, _ = _ma.mercado_abierto()
            ny = _ma._ahora_ny()
            minutos = ny.hour * 60 + ny.minute
        except Exception:
            return ""

        if not abierto:
            return ("Orden a mercado con el mercado cerrado: el precio de "
                    "ejecución puede alejarse mucho del que ve. Una orden "
                    "límite sería más segura.")
        if minutos < 585:        # primeros 15 minutos
            return ("Orden a mercado en los primeros minutos de la sesión: "
                    "es cuando más se separa el precio de ejecución del "
                    "que aparece en pantalla.")
        if minutos >= 945:       # últimos 15 minutos
            return ("Orden a mercado cerca del cierre: la horquilla se "
                    "abre y puede pagar bastante más de lo previsto.")
        return ""

    def _orden(self, accion: str, simbolo: str, cantidad: float,
               precio: float = None, stop: float = None,
               tipo: str = "MARKET") -> Optional[dict]:
        """Construye y envía la orden a IBKR."""
        if not self.esta_conectado:
            self.app.log("[IBKR] No conectado.")
            return None
        contrato = self._contrato(simbolo)
        if not contrato:
            self.app.log(f"[IBKR] Símbolo no reconocido: {simbolo}")
            return None

        # ── Calidad del dato de mercado ───────────────────────────────────
        # Un stop calculado sobre un precio de hace 15 minutos nace inválido.
        # En cuenta REAL esto bloquea; en papel solo avisa, porque las cuentas
        # de práctica normalmente no traen suscripción de datos y bloquear
        # ahí impediría practicar, que es justo para lo que sirven.
        try:
            _ok_dato, _por_que = _dm.puede_ejecutar(self._ib)
            if not _ok_dato:
                if self._modo == "paper":
                    self.app.log(f"[IBKR] Aviso de dato: {_por_que}")
                else:
                    self.app.log(f"[IBKR] Orden BLOQUEADA — {_por_que}")
                    return None
        except Exception:
            pass

        # Redondeo obligatorio: precios sin redondear = orden rechazada
        precio = self._redondear_precio(precio)
        stop   = self._redondear_precio(stop)

        tipo_u = tipo.upper()

        # Un tipo de orden mal formado NO puede degradarse en silencio a una
        # orden a mercado. Pedir "límite a X" y acabar comprando a cualquier
        # precio es la clase de fallo silencioso que arruina cuentas.
        if tipo_u in ("LIMIT", "STOP") and not precio:
            self.app.log(f"[IBKR] ✗ Orden {tipo_u} sin precio. NO la convierto "
                         f"en orden a mercado: eso ejecutaría a cualquier "
                         f"precio. Indique el precio.")
            return None
        if tipo_u == "STOP_LIMIT" and not (precio and stop):
            self.app.log("[IBKR] ✗ STOP_LIMIT necesita precio y stop. "
                         "No la envío incompleta.")
            return None
        if tipo_u not in ("MARKET", "LIMIT", "STOP", "STOP_LIMIT"):
            self.app.log(f"[IBKR] ✗ Tipo de orden desconocido: «{tipo}». "
                         f"No adivino. Use MARKET, LIMIT, STOP o STOP_LIMIT.")
            return None

        if tipo_u == "MARKET":
            # Aviso honesto: la orden a mercado es la que más daño hace en
            # los momentos de poca liquidez, y el usuario merece saberlo.
            aviso = self._riesgo_orden_mercado()
            if aviso:
                self.app.log("[IBKR] ⚠ " + aviso)
                try:
                    self.app.decir(aviso)
                except Exception:
                    pass
            orden = MarketOrder(accion, cantidad)
        elif tipo_u == "LIMIT":
            orden = LimitOrder(accion, cantidad, precio)
        elif tipo_u == "STOP":
            orden = StopOrder(accion, cantidad, precio)
        else:
            orden = StopLimitOrder(accion, cantidad, precio, stop)

        # Añadir condición de stop-loss si se proporcionó
        registros = []
        try:
            trade = self._ib.placeOrder(contrato, orden)
            self._ib.sleep(0.3)
            self._ultimo_order_id = trade.order.orderId
            r = {
                "id":       trade.order.orderId,
                "accion":   accion,
                "simbolo":  simbolo,
                "cantidad": cantidad,
                "tipo":     tipo_u,
                "precio":   precio,
                "stop":     stop,
                "estado":   trade.orderStatus.status,
                "ts":       time.strftime("%Y-%m-%d %H:%M:%S"),
                "modo":     self._modo,
            }
            self.app.log(
                f"[IBKR] {'🟢' if accion == 'BUY' else '🔴'} "
                f"{accion} {cantidad}x {simbolo} | "
                f"tipo={tipo_u}" +
                (f" @{precio}" if precio else " @MARKET") +
                (f" stop={stop}" if stop else "") +
                f" | #{r['id']} {r['estado']}")
            self._historial.append(r)
            self._guardar_historial()

            # Si había stop-loss, colocar orden bracket
            if stop and tipo_u == "MARKET":
                stop_ord = StopOrder(
                    "SELL" if accion == "BUY" else "BUY",
                    cantidad, stop)
                stop_ord.parentId = self._ultimo_order_id
                self._ib.placeOrder(contrato, stop_ord)
                self.app.log(f"[IBKR] Stop-loss automático colocado en {stop}")

            return r
        except Exception as e:
            self.app.log(f"[IBKR] Error al colocar orden {accion} {simbolo}: {e}")
            return None

    # ── BRACKET COMPLETO (entrada + stop + objetivo con OCA) ────────────────

    def bracket(self, simbolo: str, accion: str, cantidad: float,
                entrada: float, stop: float, objetivo: float,
                dry_run: bool = True) -> dict:
        """Coloca un BRACKET profesional: entrada LÍMITE + stop-loss +
        take-profit, enlazados con OCA (si uno se ejecuta, el otro se cancela).

        Es la forma correcta de operar acciones: el plan completo se envía de
        una vez, así el riesgo queda definido ANTES de entrar y no depende de
        que alguien esté mirando la pantalla.

        dry_run=True (por defecto) SOLO devuelve el plan sin enviar nada.
        Para enviar de verdad hay que pasar dry_run=False explícitamente.
        """
        # Redondeo obligatorio al tick (IBKR rechaza precios con más decimales)
        entrada  = self._redondear_precio(entrada)
        stop     = self._redondear_precio(stop)
        objetivo = self._redondear_precio(objetivo)
        accion   = accion.upper()
        contraria = "SELL" if accion == "BUY" else "BUY"

        # Validación de coherencia (evita brackets imposibles)
        if accion == "BUY" and not (stop < entrada < objetivo):
            return {"ok": False, "msg": "Bracket incoherente para COMPRA: "
                    "debe cumplirse stop < entrada < objetivo."}
        if accion == "SELL" and not (objetivo < entrada < stop):
            return {"ok": False, "msg": "Bracket incoherente para VENTA: "
                    "debe cumplirse objetivo < entrada < stop."}

        riesgo   = abs(entrada - stop)
        ganancia = abs(objetivo - entrada)
        ratio    = round(ganancia / riesgo, 2) if riesgo else 0
        if ratio < 1.5:
            return {"ok": False, "msg": f"Ratio {ratio}:1 insuficiente. "
                    "Mínimo 1.5:1 (Manual 13). No envío la orden."}

        plan = {
            "ok": True, "simbolo": simbolo, "accion": accion,
            "cantidad": cantidad, "entrada": entrada, "stop": stop,
            "objetivo": objetivo, "ratio": ratio,
            "riesgo_por_accion": round(riesgo, 4),
            "modo": self._modo,
            "msg": (f"BRACKET {accion} {cantidad}x {simbolo} | "
                    f"entrada {entrada} | stop {stop} | objetivo {objetivo} "
                    f"| ratio {ratio}:1"),
        }

        if dry_run:
            plan["enviado"] = False
            plan["msg"] += "  [SIMULACIÓN — no enviado]"
            self.app.log("[IBKR] " + plan["msg"])
            return plan

        # ── Envío real (solo si dry_run=False) ──────────────────────────────
        if not self.esta_conectado:
            return {"ok": False, "msg": "No conectado a IBKR."}
        if self._modo != "paper":
            return {"ok": False, "msg": "Por seguridad solo envío brackets "
                    "en cuenta PAPER desde este método."}

        # La comprobación que de verdad manda: no lo que se pidió, sino la
        # cuenta que el servidor de IBKR confirma. Y "no lo sé" NO es "sí".
        if self._es_paper is not True:
            razon = ("es una cuenta REAL" if self._es_paper is False
                     else "no he podido confirmar que sea simulada")
            return {"ok": False,
                    "msg": (f"No envío el bracket: {razon} "
                            f"({', '.join(self._cuentas) or 'sin número'}). "
                            f"Las cuentas de práctica empiezan por DU.")}

        # AGENTE.md B.4 — los cinco datos, antes de transmitir nada.
        # Atrapa el cero de más, el decimal mal puesto, el corto sin
        # querer y el colchón de margen agotado.
        try:
            from . import protocolo_agente as _pa
            _v = _pa.verificar_cinco_datos(
                self.app, simbolo, accion, cantidad, "LMT", entrada)
            self.app.log("[IBKR] " + _v["informe"])
            if not _v["ok"]:
                return {"ok": False,
                        "msg": ("Los cinco datos no cuadran:\n" +
                                "\n".join(f"· {b}" for b in _v["bloqueos"])),
                        "informe": _v["informe"]}
            for _av in _v.get("avisos", []):
                self.app.log("[IBKR] ⚠ " + _av)
        except Exception as _e5:
            self.app.log(f"[IBKR] No pude verificar los cinco datos: {_e5}")
        try:
            contrato = self._contrato(simbolo)
            if not contrato:
                return {"ok": False, "msg": f"Símbolo no reconocido: {simbolo}"}

            # 1) Orden padre: entrada LÍMITE (no se transmite todavía)
            padre = LimitOrder(accion, cantidad, entrada)
            padre.transmit = False

            # 2) Take-profit (hija)
            tp = LimitOrder(contraria, cantidad, objetivo)
            tp.parentId = None      # se asigna tras conocer el id del padre
            tp.transmit = False

            # 3) Stop-loss (hija) — al transmitirse esta, se envía todo
            sl = StopOrder(contraria, cantidad, stop)
            sl.parentId = None
            sl.transmit = True

            trade_padre = self._ib.placeOrder(contrato, padre)
            self._ib.sleep(0.3)
            pid = trade_padre.order.orderId
            tp.parentId = pid
            sl.parentId = pid
            # OCA: si una hija se ejecuta, la otra se cancela
            grupo = f"OCA_{pid}"
            tp.ocaGroup = sl.ocaGroup = grupo
            tp.ocaType = sl.ocaType = 1

            trade_tp = self._ib.placeOrder(contrato, tp)
            trade_sl = self._ib.placeOrder(contrato, sl)
            self._ib.sleep(1.2)      # dar tiempo a que TWS responda

            # ── VERIFICACIÓN POSTERIOR ──────────────────────────────────────
            # Enviar no es lo mismo que ser aceptado. Si IBKR rechaza el
            # stop y nadie lo mira, usted cree tener protección y no la
            # tiene: dinero expuesto sin red. Esto es lo peor que puede
            # pasar en una operación, así que se comprueba explícitamente.
            RECHAZADOS = ("Cancelled", "ApiCancelled", "Inactive")

            def _estado(t):
                try:
                    return str(t.orderStatus.status or "?")
                except Exception:
                    return "?"

            e_padre, e_tp, e_sl = (_estado(trade_padre), _estado(trade_tp),
                                   _estado(trade_sl))
            plan["estados"] = {"entrada": e_padre, "objetivo": e_tp,
                               "stop": e_sl}

            malos = [n for n, e in (("entrada", e_padre), ("objetivo", e_tp),
                                    ("stop", e_sl)) if e in RECHAZADOS]

            if malos:
                # Si algo se cayó, se intenta deshacer TODO. Mejor sin
                # posición que con una posición a medio proteger.
                self.app.log(f"[IBKR] ⛔ Bracket incompleto: rechazado(s) "
                             f"{', '.join(malos)}. Cancelo el resto.")
                for t in (trade_sl, trade_tp, trade_padre):
                    try:
                        self._ib.cancelOrder(t.order)
                    except Exception:
                        pass
                self._ib.sleep(0.6)
                try:
                    self.app.decir("Atención. El bracket no entró completo, "
                                   "así que lo he cancelado entero. Prefiero "
                                   "quedarme sin operación que con una "
                                   "posición sin stop.")
                except Exception:
                    pass
                return {"ok": False,
                        "msg": (f"Bracket rechazado en: {', '.join(malos)}. "
                                f"Estados — entrada {e_padre}, objetivo "
                                f"{e_tp}, stop {e_sl}. Lo cancelé todo: "
                                f"prefiero ninguna posición a una sin stop."),
                        "estados": plan["estados"]}

            plan["enviado"] = True
            plan["id_padre"] = pid
            plan["msg"] += (f"  [ENVIADO #{pid}, OCA {grupo} | entrada "
                            f"{e_padre}, objetivo {e_tp}, stop {e_sl}]")
            self.app.log("[IBKR] " + plan["msg"])
            self._historial.append(plan)
            self._guardar_historial()
            return plan
        except Exception as e:
            return {"ok": False, "msg": f"Error al enviar el bracket: {e}"}

    def cerrar_posicion(self, simbolo: str) -> bool:
        """Cierra completamente la posición abierta de un símbolo."""
        posiciones = self.posiciones()
        for pos in posiciones:
            if pos.get("simbolo", "").upper() == simbolo.upper():
                cant = abs(pos.get("cantidad", 0))
                if cant == 0:
                    return False
                accion = "SELL" if pos.get("cantidad", 0) > 0 else "BUY"
                r = self._orden(accion, simbolo, cant)
                return r is not None
        self.app.log(f"[IBKR] No hay posición abierta en {simbolo}.")
        return False

    def cancelar_orden(self, orden_id: int) -> bool:
        """Cancela una orden pendiente por su ID."""
        if not self.esta_conectado:
            return False
        try:
            ordenes = self._ib.orders()
            for o in ordenes:
                if o.orderId == orden_id:
                    self._ib.cancelOrder(o)
                    self.app.log(f"[IBKR] Orden #{orden_id} cancelada.")
                    return True
            self.app.log(f"[IBKR] Orden #{orden_id} no encontrada.")
            return False
        except Exception as e:
            self.app.log(f"[IBKR] Error cancelando orden: {e}")
            return False

    # ── Cuenta y posiciones ───────────────────────────────────────────────────

    def posiciones(self) -> list[dict]:
        """Devuelve todas las posiciones abiertas."""
        if not self.esta_conectado:
            return []
        try:
            poss = self._ib.positions()
            return [
                {
                    "simbolo":  p.contract.symbol,
                    "cantidad": p.position,
                    "costo":    p.avgCost,
                    "pnl":      None,  # requiere reqPnL
                }
                for p in poss
            ]
        except Exception as e:
            self.app.log(f"[IBKR] Error obteniendo posiciones: {e}")
            return []

    def balance_cuenta(self) -> dict:
        """Devuelve balance, poder de compra y equity de la cuenta."""
        if not self.esta_conectado:
            return {}
        try:
            vals = {v.tag: v.value for v in self._ib.accountValues()
                    if v.currency == "USD"}
            return {
                "cash":          float(vals.get("CashBalance",     0)),
                "equity":        float(vals.get("NetLiquidation",  0)),
                "buying_power":  float(vals.get("BuyingPower",     0)),
                "pnl_dia":       float(vals.get("DayTradesRemaining", 0)),
                "modo":          self._modo,
            }
        except Exception as e:
            self.app.log(f"[IBKR] Error balance: {e}")
            return {}

    def ordenes_abiertas(self) -> list[dict]:
        """Lista de órdenes pendientes de ejecutar."""
        if not self.esta_conectado:
            return []
        try:
            return [
                {
                    "id":       t.order.orderId,
                    "simbolo":  t.contract.symbol,
                    "accion":   t.order.action,
                    "cantidad": t.order.totalQuantity,
                    "tipo":     t.order.orderType,
                    "estado":   t.orderStatus.status,
                }
                for t in self._ib.trades()
                if t.orderStatus.status not in ("Filled", "Cancelled")
            ]
        except Exception as e:
            self.app.log(f"[IBKR] Error ordenes_abiertas: {e}")
            return []

    # ── Resumen para Litch ────────────────────────────────────────────────────

    def resumen(self) -> str:
        """Texto de estado para el log de Litch."""
        if not self.esta_conectado:
            return f"IBKR: desconectado (instala ib_insync y abre TWS)"
        bal = self.balance_cuenta()
        poss = self.posiciones()
        return (f"IBKR/{self._modo.upper()} | "
                f"equity=${bal.get('equity', 0):.2f} | "
                f"cash=${bal.get('cash', 0):.2f} | "
                f"{len(poss)} posiciones abiertas")

    # ── Conocimiento del broker (para que Litch responda preguntas) ───────────

    CONOCIMIENTO = {
        "que_es": (
            "Interactive Brokers (IBKR) es el broker más completo del mundo. "
            "Fundado en 1977. Regulado por SEC, FINRA, FCA y más de 10 reguladores globales. "
            "Opera en 150+ mercados de 33 países. Es el favorito de traders profesionales "
            "latinoamericanos que quieren acceso a NYSE, NASDAQ, forex, futuros y opciones."
        ),
        "ventajas": (
            "• Comisiones ultra-bajas: desde $0.005/acción (mínimo $1/orden). "
            "• Acceso a mercados globales: NYSE, NASDAQ, LSE, Euronext, Tokyo, Hong Kong y más. "
            "• Margen bajo: hasta 50% menos que la competencia. "
            "• Tecnología profesional: SMART routing, algoritmos, API completa. "
            "• Papel trading (demo) idéntico al real — practica sin riesgo. "
            "• Sin cargo por inactividad si tienes $100k+ en la cuenta."
        ),
        "desventajas": (
            "• Interfaz de TWS es compleja para principiantes. "
            "• Cargo de $10/mes si el capital es menor a $100k. "
            "• Mínimo de cuenta: $0 (antes era $10k). "
            "• Soporte al cliente no siempre es rápido."
        ),
        "como_abrir_cuenta": (
            "1. Ve a ibkr.com → Abrir cuenta. "
            "2. Completa el formulario (necesitas pasaporte/DNI y comprobante de residencia). "
            "3. Fondea la cuenta (mínimo recomendado: $2,000). "
            "4. Descarga TWS desde ibkr.com/tws. "
            "5. Habilita la API: TWS → Configuración Global → API → Enable ActiveX and Socket Clients. "
            "6. Empieza SIEMPRE con la cuenta de papel (PAPER) para practicar."
        ),
        "ordenes": (
            "• MARKET: ejecución inmediata al precio de mercado. Usa para activos muy líquidos. "
            "• LIMIT: ejecuta solo a tu precio o mejor. SIEMPRE úsalo en acciones pequeñas. "
            "• STOP: activa cuando el precio toca tu stop y convierte en MARKET. Para stop-loss. "
            "• STOP LIMIT: igual al STOP pero ejecuta solo dentro del límite. Riesgo de no llenarse. "
            "• TRAILING STOP: el stop sube junto con el precio pero no baja. Protege ganancias."
        ),
        "horarios": (
            "Acciones US: "
            "• Pre-market: 04:00–09:30 ET (menor liquidez, spreads amplios). "
            "• Mercado regular: 09:30–16:00 ET (mayor liquidez — USA aquí). "
            "• After-hours: 16:00–20:00 ET. "
            "Forex: 24 horas de domingo 17:00 ET a viernes 17:00 ET. "
            "Futuros: casi 24/5 (pausa de 1h/día por mantenimiento)."
        ),
        "gestion_riesgo": (
            "REGLAS DE ORO para no perder tu capital:\n"
            "1. Nunca arriesgar más del 1% del capital por trade.\n"
            "2. Siempre colocar stop-loss ANTES de entrar al trade.\n"
            "3. Ratio mínimo riesgo/beneficio: 1:2 (arriesgo $100 para ganar $200).\n"
            "4. Nunca promediar hacia abajo (agregar a posición perdedora).\n"
            "5. Máximo 3 trades abiertos simultáneos al comenzar.\n"
            "6. No operar en noticias de alto impacto (FOMC, NFP, CPI).\n"
            "7. Diario: si pierdes 3% del capital, para de operar ese día."
        ),
        "api_python": (
            # Este texto tenía el puerto 7498, que NO EXISTE. Quien lo
            # siguiera se pasaría la tarde buscando por qué no conecta.
            # Los puertos reales son 7497 (paper) y 7496 (real).
            "Para conectar Litch a IBKR vía Python:\n"
            "pip install ib_async      # sucesor mantenido de ib_insync\n\n"
            "from ib_async import IB, Stock, LimitOrder\n"
            "ib = IB()\n"
            "ib.connect('127.0.0.1', 7497, clientId=1)  # 7497 = PAPER\n"
            "#                        ^^^^ 7496 seria la cuenta REAL\n"
            "contract = Stock('SPY', 'SMART', 'USD')\n"
            "ib.qualifyContracts(contract)\n"
            "# Limite, no mercado: usted decide el precio\n"
            "order = LimitOrder('BUY', 1, 600.00)\n"
            "trade = ib.placeOrder(contract, order)\n"
            "print(trade.orderStatus.status)"
        ),
    }

    # ── Persistencia de historial ─────────────────────────────────────────────

    def _cargar_historial(self):
        if os.path.exists(self._ruta_historial):
            try:
                with open(self._ruta_historial, "r", encoding="utf-8") as f:
                    self._historial = json.load(f)
            except Exception:
                self._historial = []

    def _guardar_historial(self):
        try:
            os.makedirs(os.path.dirname(self._ruta_historial), exist_ok=True)
            with open(self._ruta_historial, "w", encoding="utf-8") as f:
                json.dump(self._historial[-500:], f, ensure_ascii=False, indent=1)
        except Exception:
            pass

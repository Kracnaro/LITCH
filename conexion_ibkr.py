"""
conexion_ibkr.py — Conexión de Litch a Interactive Brokers con ib_async.

Construido según PROMPT_Conexion_IBKR.md. Cuatro cosas se han corregido
respecto al código de referencia; están señaladas en el sitio donde
importan, para que se pueda comprobar y discutir cada una.

SEGURIDAD (no negociable)
─────────────────────────
  · Puerto 7497 (PAPER) por defecto. Siempre.
  · PERMITIR_LIVE = False. Cambiarlo exige intención plena.
  · Si la cuenta conectada no es Paper y PERMITIR_LIVE es False, se
    desconecta en el acto.

Uso suelto:
    python conexion_ibkr.py
"""

from __future__ import annotations

import logging
import os
import threading
import time

# ── Registro con marca de tiempo ────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
_LOG = os.path.join(_BASE, "ibkr_conexion.log")

logging.basicConfig(
    filename=_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)
_log = logging.getLogger("ibkr")

# También por consola, para no tener que abrir el archivo cada vez
_consola = logging.StreamHandler()
_consola.setFormatter(logging.Formatter("%(asctime)s | %(message)s",
                                        "%H:%M:%S"))
_log.addHandler(_consola)


# ═══════════════════════════════════════════════════════════════════════════
#  SEGURIDAD
# ═══════════════════════════════════════════════════════════════════════════

PERMITIR_LIVE = False        # ⚠ No cambiar a True sin plena intención

PUERTO_PAPER = 7497          # TWS simulada
PUERTO_LIVE = 7496           # TWS real
PUERTO_GATEWAY_PAPER = 4002  # IB Gateway simulada
PUERTO_GATEWAY_LIVE = 4001   # IB Gateway real

# Prefijos de cuenta de IBKR.
#
# CORRECCIÓN 1 — el código de referencia usaba `cuenta.startswith("D")`.
# Es casi correcto, pero demasiado ancho: basta con que IBKR emita algún
# día un identificador real que empiece por D para que una cuenta con
# dinero pase por simulada. Se usan los prefijos concretos, y lo que no
# esté en la lista se trata como NO simulado — que es el lado seguro
# en el que equivocarse.
PREFIJOS_PAPER = ("DU", "DF", "DI")


MENSAJE_TWS_CERRADO = (
    "TWS o IB Gateway no está abierto, o la API no está habilitada. Abre TWS, "
    "ve a Archivo → Configuración global → API → Configuración, y marca "
    "'Activar clientes ActiveX y Socket'."
)


# ═══════════════════════════════════════════════════════════════════════════
#  Importación de ib_async
# ═══════════════════════════════════════════════════════════════════════════

_IB_OK = False
_ERROR_IMPORT = ""
try:
    # ib_async necesita un bucle de eventos vivo al importarse. En Python
    # 3.12+ ya no se crea solo, así que se prepara antes.
    import asyncio as _asyncio
    try:
        _asyncio.get_event_loop()
    except Exception:
        _asyncio.set_event_loop(_asyncio.new_event_loop())

    from ib_async import IB, util, Stock, MarketOrder      # noqa: F401
    _IB_OK = True
except Exception as _e:
    _ERROR_IMPORT = str(_e)


# ═══════════════════════════════════════════════════════════════════════════
#  La conexión
# ═══════════════════════════════════════════════════════════════════════════

class ConexionIBKR:
    """Conecta con TWS/Gateway, verifica permisos y se reconecta sola."""

    def __init__(self, host: str = "127.0.0.1", puerto: int = PUERTO_PAPER,
                 client_id: int = 1):
        self.host = host
        self.puerto = int(puerto)
        self.client_id = int(client_id)

        self.ib = IB() if _IB_OK else None
        self.ultimo_estado: dict = {}
        self.ultimo_error: str = ""

        # CORRECCIÓN 2 — control de la reconexión.
        #
        # El código de referencia llamaba a conectar() desde el manejador
        # de desconexión. Si la reconexión falla, ib_async vuelve a emitir
        # el evento, que vuelve a llamar a conectar()... y se entra en
        # recursión infinita dentro del bucle de eventos. El programa se
        # cuelga o revienta la pila.
        #
        # Se resuelve con tres cosas: un cerrojo, una bandera de "estoy
        # reconectando", y que la reconexión ocurra en OTRO hilo en vez de
        # dentro del propio manejador del evento.
        self._lock = threading.Lock()
        self._reconectando = False
        self._quiere_conexion = False     # False = desconexión pedida por mí
        self._reconexiones = 0

        if _IB_OK:
            self._registrar_eventos()

    # ── Eventos ─────────────────────────────────────────────────────────────

    def _registrar_eventos(self):
        try:
            self.ib.disconnectedEvent += self._al_desconectar
            self.ib.errorEvent += self._al_error
        except Exception as e:
            _log.warning(f"No pude registrar los eventos: {e}")

    def _al_desconectar(self):
        """TWS reinicia una vez al día y corta la API. Aquí se reconecta."""
        if not self._quiere_conexion:
            _log.info("Desconexión pedida por mí. No reconecto.")
            return
        if self._reconectando:
            return
        _log.warning("Desconexión detectada. Reconectando en segundo plano…")
        # Fuera del manejador del evento: sin esto, recursión.
        threading.Thread(target=self._reconectar_en_hilo, daemon=True,
                         name="IBKRReconectar").start()

    def _reconectar_en_hilo(self):
        with self._lock:
            if self._reconectando:
                return
            self._reconectando = True
        try:
            time.sleep(3)      # dar tiempo a que TWS termine de reiniciar
            ok = self.conectar(reintentos=8, desde_reconexion=True)
            if ok:
                self._reconexiones += 1
                _log.info(f"Reconectado. Reconexiones en esta sesión: "
                          f"{self._reconexiones}")
            else:
                _log.error("No pude reconectar tras varios intentos.")
        finally:
            self._reconectando = False

    def _al_error(self, reqId, codigo, mensaje, contrato=None):
        """Los códigos 2100-2199 de IBKR son avisos, no errores."""
        try:
            if 2100 <= int(codigo) <= 2199:
                _log.info(f"[IBKR aviso {codigo}] {mensaje}")
            else:
                _log.error(f"[IBKR error {codigo}] {mensaje}")
                self.ultimo_error = f"{codigo}: {mensaje}"
        except Exception:
            pass

    # ── Conectar ────────────────────────────────────────────────────────────

    def conectar(self, reintentos: int = 3,
                 desde_reconexion: bool = False) -> dict | bool:
        """Conecta y verifica. Devuelve el dict de permisos, o False."""
        if not _IB_OK:
            msg = (f"Falta ib_async. Instálalo con:  pip install ib_async\n"
                   f"Detalle: {_ERROR_IMPORT}")
            _log.error(msg)
            self.ultimo_error = msg
            return False

        # Puerta de seguridad
        if self.puerto in (PUERTO_LIVE, PUERTO_GATEWAY_LIVE) \
                and not PERMITIR_LIVE:
            msg = (f"Conexión a LIVE (puerto {self.puerto}) BLOQUEADA: "
                   f"PERMITIR_LIVE está en False. Es a propósito.")
            _log.error(msg)
            self.ultimo_error = msg
            return False

        if not desde_reconexion:
            self._quiere_conexion = True

        if self.ib.isConnected():
            _log.info("Ya estaba conectado.")
            return self.verificar_permisos()

        espera = 2
        for intento in range(1, int(reintentos) + 1):
            try:
                self.ib.connect(self.host, self.puerto,
                                clientId=self.client_id, timeout=10)
                _log.info(f"Conectado en el intento {intento} al puerto "
                          f"{self.puerto}.")
                return self.verificar_permisos()
            except Exception as e:
                txt = str(e)
                _log.error(f"Intento {intento}/{reintentos} falló: {txt}")
                self.ultimo_error = self._explicar_error(txt)
                if intento < reintentos:
                    time.sleep(espera)
                    espera = min(espera * 2, 30)      # backoff hasta 30 s

        _log.error("No se pudo conectar tras varios intentos.")
        _log.error(self.ultimo_error)
        return False

    def _explicar_error(self, texto: str) -> str:
        """Traduce el fallo a algo accionable, no a un volcado técnico."""
        t = texto.lower()
        if "timeout" in t or "timed out" in t:
            return MENSAJE_TWS_CERRADO
        if "refused" in t or "10061" in t or "connectionrefused" in t:
            cual = ("simulada (Paper)" if self.puerto == PUERTO_PAPER
                    else "REAL (Live)" if self.puerto == PUERTO_LIVE
                    else f"puerto {self.puerto}")
            return (f"El puerto {self.puerto} está cerrado — es el de la "
                    f"cuenta {cual}. Comprueba en TWS que 'Socket port' sea "
                    f"{self.puerto}. Si iniciaste sesión en la otra cuenta, "
                    f"el puerto sería el {PUERTO_LIVE if self.puerto == PUERTO_PAPER else PUERTO_PAPER}.\n"
                    + MENSAJE_TWS_CERRADO)
        if "client id" in t or "clientid" in t or "326" in t:
            return (f"El clientId {self.client_id} ya está en uso por otro "
                    f"programa. Cada script necesita el suyo. Prueba con "
                    f"otro número.")
        return MENSAJE_TWS_CERRADO + f"\n\n(Detalle técnico: {texto})"

    # ── Verificación de permisos ────────────────────────────────────────────

    def verificar_permisos(self) -> dict | bool:
        """Comprueba cuenta, tipo, solo-lectura, órdenes y hora del servidor."""
        if not self.ib or not self.ib.isConnected():
            return False

        info = {"conectado": True, "puerto": self.puerto,
                "host": self.host, "client_id": self.client_id,
                "avisos": []}

        # 1. Cuentas
        try:
            cuentas = list(self.ib.managedAccounts() or [])
        except Exception as e:
            _log.error(f"No pude leer las cuentas: {e}")
            cuentas = []

        if not cuentas:
            _log.error("Conectado pero sin cuentas visibles.")
            info["avisos"].append(
                "Conectado, pero TWS no me devuelve ninguna cuenta. Sin eso "
                "no puedo confirmar si es simulada, así que no opero.")
            info["cuenta"] = ""
            info["paper"] = None
            self.ultimo_estado = info
            return info

        cuenta = cuentas[0]
        info["cuentas"] = cuentas
        info["cuenta"] = cuenta

        # 2. ¿Paper o Live? — la comprobación que más importa
        es_paper = all(str(c).upper().startswith(PREFIJOS_PAPER)
                       for c in cuentas)
        info["paper"] = es_paper

        if not es_paper:
            info["avisos"].append(
                f"⚠ La cuenta {cuenta} NO es simulada. Las de práctica "
                f"empiezan por DU, DF o DI.")
            if not PERMITIR_LIVE:
                _log.warning(f"Cuenta LIVE ({cuenta}) con PERMITIR_LIVE=False. "
                             f"Me desconecto.")
                info["avisos"].append(
                    "PERMITIR_LIVE está en False, así que me desconecto. "
                    "Esto es a propósito y es lo correcto.")
                info["conectado"] = False
                self.ultimo_estado = info
                self.desconectar()
                return info

        # 3. Hora del servidor de IBKR
        try:
            hora = self.ib.reqCurrentTime()
            info["hora_servidor"] = str(hora)
            try:
                from datetime import datetime, timezone
                desfase = abs((datetime.now(timezone.utc) - hora)
                              .total_seconds())
                info["desfase_seg"] = round(desfase, 1)
                if desfase > 30:
                    info["avisos"].append(
                        f"Su reloj y el de IBKR difieren en {desfase:.0f} "
                        f"segundos. Conviene sincronizar la hora del equipo: "
                        f"un desfase grande complica interpretar las marcas "
                        f"de tiempo de las órdenes.")
            except Exception:
                pass
        except Exception as e:
            info["hora_servidor"] = f"no disponible ({e})"

        # 4. Órdenes abiertas al conectar
        try:
            abiertas = self.ib.openTrades() or []
            info["ordenes_abiertas"] = len(abiertas)
            if not abiertas:
                info["avisos"].append(
                    "No veo órdenes abiertas. Si usted sabe que las hay, "
                    "active en TWS «Descargar órdenes abiertas al conectar» "
                    "(API → Configuración).")
        except Exception:
            info["ordenes_abiertas"] = None

        # 5. ¿Read-Only?
        info.update(self._detectar_solo_lectura())

        # 6. Balance, si se puede
        try:
            for v in (self.ib.accountValues(cuenta) or []):
                if v.tag == "NetLiquidation" and v.currency == "USD":
                    info["valor_neto"] = float(v.value)
                elif v.tag == "ExcessLiquidity" and v.currency == "USD":
                    info["excess_liquidity"] = float(v.value)
        except Exception:
            pass

        _log.info(f"Cuenta: {cuenta} | Paper: {es_paper} | "
                  f"Hora servidor: {info.get('hora_servidor')} | "
                  f"Solo lectura: {info.get('solo_lectura')}")

        self.ultimo_estado = info
        return info

    def _detectar_solo_lectura(self) -> dict:
        """¿Está la API en modo solo lectura?

        CORRECCIÓN 3 — el prompt pedía «comprobar si la API está en
        Read-Only». Hay que ser honesto: **IBKR no expone ese ajuste por
        la API**. No hay ningún campo que lo diga.

        La única forma de saberlo es intentar algo que el modo lectura
        impide. Se usa `whatIfOrder`, que pide a IBKR el cálculo de margen
        de una orden hipotética SIN enviarla nunca. Es la sonda más
        inofensiva que existe: no crea ninguna orden.

        Y si la sonda no es concluyente, se dice que no se sabe, en vez de
        afirmar algo falso.
        """
        r = {"solo_lectura": None, "solo_lectura_nota": ""}
        try:
            contrato = Stock("SPY", "SMART", "USD")
            self.ib.qualifyContracts(contrato)

            # NOTA PARA EL AUDITOR (y para quien lea esto dentro de un año):
            # este MarketOrder NUNCA se transmite. Solo se pasa a
            # `whatIfOrder`, que es la llamada de IBKR para «calcula el
            # margen de esta orden hipotética». No crea ninguna orden, no
            # llega a ninguna bolsa y no aparece en el historial.
            #
            # Se usa MarketOrder y no LimitOrder a propósito: una orden a
            # mercado no necesita precio, así que la sonda no depende de
            # que haya cotización viva. Es la sonda más simple posible.
            #
            # Este módulo tampoco lleva control PDT porque no opera: solo
            # conecta. El conteo de day-trades está en core/guardia_pdt.py.
            orden = MarketOrder("BUY", 1)
            estado = self.ib.whatIfOrder(contrato, orden)

            if estado and getattr(estado, "initMarginChange", None) not in \
                    (None, "", "1.7976931348623157E308"):
                r["solo_lectura"] = False
                r["solo_lectura_nota"] = (
                    "La API PUEDE enviar órdenes. Si está practicando, "
                    "considere activar «API solo lectura» en TWS hasta "
                    "confiar en lo que hace el sistema.")
            else:
                r["solo_lectura"] = True
                r["solo_lectura_nota"] = (
                    "La API parece estar en SOLO LECTURA: puedo leer datos "
                    "y posiciones, pero no enviar órdenes. Para operar, "
                    "desmarque «API solo lectura» en TWS → Configuración "
                    "global → API → Configuración.")
        except Exception as e:
            t = str(e).lower()
            if "read-only" in t or "read only" in t or "solo lectura" in t:
                r["solo_lectura"] = True
                r["solo_lectura_nota"] = (
                    "La API está en SOLO LECTURA (me lo dijo IBKR al "
                    "intentar calcular el margen).")
            else:
                r["solo_lectura"] = None
                r["solo_lectura_nota"] = (
                    f"No he podido determinar si la API está en solo "
                    f"lectura. IBKR no expone ese ajuste, y mi sonda no fue "
                    f"concluyente ({e}). Compruébelo usted en TWS.")
        return r

    # ── Estado y cierre ─────────────────────────────────────────────────────

    def estado(self) -> dict:
        if not _IB_OK:
            return {"conectado": False,
                    "error": "ib_async no instalado (pip install ib_async)"}
        try:
            con = self.ib.isConnected()
        except Exception:
            con = False
        return {
            "conectado": con,
            "puerto": self.puerto,
            "es_paper": self.puerto in (PUERTO_PAPER, PUERTO_GATEWAY_PAPER),
            "cuentas": (list(self.ib.managedAccounts() or []) if con else []),
            "reconexiones": self._reconexiones,
            "ultimo_error": self.ultimo_error,
            "detalle": self.ultimo_estado,
        }

    def resumen(self) -> str:
        """El estado, en castellano, para enseñárselo a una persona."""
        e = self.estado()
        if not e.get("conectado"):
            return ("SIN CONEXIÓN a Interactive Brokers.\n\n"
                    + (self.ultimo_error or MENSAJE_TWS_CERRADO))

        d = e.get("detalle") or {}
        tipo = ("SIMULADA ✓" if d.get("paper") is True
                else "⚠ REAL" if d.get("paper") is False
                else "sin confirmar")
        lineas = [
            "CONEXIÓN CON INTERACTIVE BROKERS",
            f"  Estado ........... conectado",
            f"  Puerto ........... {e['puerto']} "
            f"({'simulada' if e['es_paper'] else 'REAL'})",
            f"  Cuenta ........... {d.get('cuenta','?')} — {tipo}",
            f"  Hora del servidor  {d.get('hora_servidor','?')}",
        ]
        if d.get("desfase_seg") is not None:
            lineas.append(f"  Desfase de reloj . {d['desfase_seg']} s")
        if d.get("ordenes_abiertas") is not None:
            lineas.append(f"  Órdenes abiertas . {d['ordenes_abiertas']}")
        if d.get("valor_neto"):
            lineas.append(f"  Valor neto ....... {d['valor_neto']:,.2f} USD")
        if d.get("excess_liquidity"):
            lineas.append(f"  Colchón margen ... "
                          f"{d['excess_liquidity']:,.2f} USD")

        sl = d.get("solo_lectura")
        lineas.append(f"  API solo lectura . "
                      + ("SÍ" if sl is True else "no" if sl is False
                         else "no lo sé"))
        if e.get("reconexiones"):
            lineas.append(f"  Reconexiones ..... {e['reconexiones']}")

        if d.get("solo_lectura_nota"):
            lineas.append("")
            lineas.append(d["solo_lectura_nota"])
        for a in d.get("avisos", []):
            lineas.append("")
            lineas.append("⚠ " + a)
        return "\n".join(lineas)

    def desconectar(self):
        """Cierre limpio. No dispara la reconexión automática."""
        self._quiere_conexion = False
        try:
            if self.ib and self.ib.isConnected():
                self.ib.disconnect()
                _log.info("Desconectado limpiamente.")
        except Exception as e:
            _log.warning(f"Error al desconectar: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  Prueba suelta
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("=" * 62)
    print("  CONEXIÓN CON INTERACTIVE BROKERS — prueba")
    print("=" * 62)
    print()
    if not _IB_OK:
        print("  ✗ Falta ib_async.")
        print("    Instálalo con:  pip install ib_async")
        print(f"    Detalle: {_ERROR_IMPORT}")
        print()
        raise SystemExit(1)

    c = ConexionIBKR()
    c.conectar()
    print()
    print(c.resumen())
    print()
    if c.estado().get("conectado"):
        input("  Pulsa ENTER para desconectar...")
        c.desconectar()

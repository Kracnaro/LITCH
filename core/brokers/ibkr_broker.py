"""
ibkr_broker.py — Conector Interactive Brokers para LITCH.

Usa la API oficial de IBKR (ibapi).
Requisitos:
  1. Tener instalado TWS (Trader Workstation) o IB Gateway
  2. Activar "Enable ActiveX and Socket Clients" en TWS
  3. py -m pip install ibapi

Interactive Brokers ofrece:
  - Acciones (NYSE, NASDAQ, etc.)
  - Forex
  - Opciones, Futuros
  - Criptomonedas
  - Mercados globales (60+ países)

Modelo de trading aquí: forex y acciones (no opciones binarias).
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import List, Optional

from .base import BrokerBase, InfoActivo, ResultadoTrade

_CONF_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "memoria_ap", "ibkr_config.json")

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    _IBAPI_OK = True
except ImportError:
    _IBAPI_OK = False
    EClient = object
    EWrapper = object


class _IBWrapper(EWrapper if _IBAPI_OK else object):
    """Receptor de eventos de la API de IBKR."""

    def __init__(self):
        if _IBAPI_OK:
            super().__init__()
        self._saldo       = 0.0
        self._precios     = {}
        self._ordenes     = {}
        self._posiciones  = []
        self._error_msgs  = []
        self._lock        = threading.Lock()
        self._eventos     = threading.Event()

    def nextValidId(self, orderId: int):
        self._next_id = orderId
        self._eventos.set()

    def accountSummary(self, reqId, account, tag, value, currency):
        if tag == "NetLiquidation":
            with self._lock:
                self._saldo = float(value)

    def tickPrice(self, reqId, tickType, price, attrib):
        with self._lock:
            self._precios[reqId] = float(price)

    def historicalData(self, reqId, bar):
        with self._lock:
            if reqId not in self._ordenes:
                self._ordenes[reqId] = []
            self._ordenes[reqId].append({
                "time":   bar.date,
                "open":   float(bar.open),
                "high":   float(bar.high),
                "low":    float(bar.low),
                "close":  float(bar.close),
                "volume": float(bar.volume),
            })

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        with self._lock:
            self._ordenes[str(orderId)] = {
                "status": status,
                "filled": filled,
                "precio": avgFillPrice,
            }

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        if errorCode not in (2104, 2106, 2158):  # ignorar avisos de conexión
            with self._lock:
                self._error_msgs.append(f"[{errorCode}] {errorString}")


class IBKRBroker(BrokerBase):
    """
    Conector a Interactive Brokers via TWS API.

    Instrucciones de configuración:
    1. Abre TWS o IB Gateway
    2. Ve a File → Global Configuration → API → Settings
    3. Marca "Enable ActiveX and Socket Clients"
    4. Puertos: 7497 (TWS PAPER — el seguro, predeterminado de Litch),
       7496 (TWS real), 4002 (Gateway paper), 4001 (Gateway real)
    5. En LITCH, di: 'conectar interactive brokers'
    """

    nombre      = "Interactive Brokers"
    descripcion = "Acciones, Forex, Opciones, Futuros — 60+ mercados globales"

    # Activos de forex populares para trading (pares principales)
    _FOREX_POPULARES = [
        "EUR.USD", "GBP.USD", "USD.JPY", "USD.CHF",
        "AUD.USD", "USD.CAD", "NZD.USD", "EUR.GBP",
    ]

    # SEGURIDAD: el puerto por defecto es 7497 = cuenta PAPER (simulada).
    # Para operar en real hay que pedirlo explícitamente (port=7496).
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        self._host       = host
        self._port       = port
        self._client_id  = client_id
        self._wrapper    = None
        self._client     = None
        self._conectado  = False
        self._modo       = "paper"   # IBKR usa cuentas separadas paper/real
        self._thread     = None
        self._req_id     = 1

    @staticmethod
    def disponible() -> bool:
        """True si ibapi está instalado."""
        return _IBAPI_OK

    @staticmethod
    def _app_log(msg: str) -> None:
        """Log seguro (esta clase no guarda referencia a la app)."""
        try:
            print(msg)
        except Exception:
            pass

    # ── Conexión ──────────────────────────────────────────────────────────────

    def conectar(self, credenciales: dict = None) -> tuple[bool, str]:
        if not _IBAPI_OK:
            return False, (
                "ibapi no instalado. Instala TWS y ejecuta:\n"
                "py -m pip install ibapi\n"
                "Luego abre TWS y activa la API en:\n"
                "File → Global Configuration → API → Settings"
            )

        cfg = credenciales or self._cargar_config()
        host = cfg.get("host", self._host)
        port = int(cfg.get("port", self._port))

        try:
            class _Client(EClient, _IBWrapper):
                def __init__(self_):
                    _IBWrapper.__init__(self_)
                    EClient.__init__(self_, self_)

            self._client = _Client()
            self._client.connect(host, port, clientId=self._client_id)

            self._thread = threading.Thread(
                target=self._client.run,
                daemon=True,
                name="IBKR-API",
            )
            self._thread.start()

            # Esperar confirmación de conexión (máx 5s)
            if self._client._eventos.wait(timeout=5.0):
                self._conectado = True
                return True, f"Conectado a Interactive Brokers ({host}:{port})"
            else:
                return False, "Timeout esperando TWS. ¿Está TWS abierto con API activada?"
        except Exception as e:
            return False, f"Error conexión IBKR: {e}"

    def desconectar(self) -> None:
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
        self._conectado = False

    @property
    def conectado(self) -> bool:
        return self._conectado

    # ── Cuenta ────────────────────────────────────────────────────────────────

    def saldo(self, modo: str = None) -> float:
        if not self.conectado:
            return 0.0
        try:
            req_id = self._next_req()
            self._client.reqAccountSummary(req_id, "All", "NetLiquidation")
            time.sleep(1)
            return self._client._saldo
        except Exception:
            return 0.0

    def modo_cuenta(self) -> str:
        return self._modo

    def cambiar_modo(self, modo: str) -> bool:
        """IBKR usa cuentas separadas — no se puede cambiar desde la API."""
        self._modo = modo
        return True

    # ── Activos ───────────────────────────────────────────────────────────────

    def activos_disponibles(self, tipo: str = "forex") -> List[InfoActivo]:
        activos = []
        for par in self._FOREX_POPULARES:
            simbolo, moneda = par.split(".")
            activos.append(InfoActivo(
                simbolo    = par,
                nombre     = f"{simbolo}/{moneda}",
                payout_pct = 0.0,   # IBKR cobra comisión, no payout fijo
                disponible = True,
            ))
        return activos

    def velas(self, activo: str, periodo_seg: int, n: int = 200) -> list:
        if not self.conectado:
            return []
        try:
            contrato = self._forex_contract(activo)
            duracion = self._duracion_ibkr(n, periodo_seg)
            barra    = self._barra_ibkr(periodo_seg)
            req_id   = self._next_req()
            self._client._ordenes[req_id] = []
            self._client.reqHistoricalData(
                req_id, contrato,
                endDateTime="",
                durationStr=duracion,
                barSizeSetting=barra,
                whatToShow="MIDPOINT",
                useRTH=1, formatDate=1, keepUpToDate=False, chartOptions=[],
            )
            time.sleep(2)
            return self._client._ordenes.get(req_id, [])
        except Exception:
            return []

    def ejecutar_trade(self, activo: str, direccion: str,
                       monto: float, venc_seg: int) -> ResultadoTrade:
        if not self.conectado:
            return ResultadoTrade(False, mensaje="No conectado a Interactive Brokers")
        try:
            contrato = self._forex_contract(activo)
            orden    = Order()
            orden.action    = "BUY" if direccion == "V" else "SELL"
            orden.orderType = "MKT"
            # Cantidad redondeada (auditor): IBKR rechaza cantidades con
            # precisión excesiva. 4 decimales cubre fracciones permitidas.
            orden.totalQuantity = round(float(monto), 4)
            # Nota PDT (auditor): con margen <$25k, máx 3 day-trades/5 días.
            # El control PDT completo vive en broker_ibkr.py; aquí avisamos.
            self._app_log(f"[IBKR] Orden MKT {orden.action} {activo} "
                          f"x{orden.totalQuantity} — recuerde la regla PDT "
                          f"si la cuenta es de margen pequeña.")

            orden_id = getattr(self._client, "_next_id", 1)
            self._client.placeOrder(orden_id, contrato, orden)

            return ResultadoTrade(
                exito    = True,
                id_trade = str(orden_id),
                activo   = activo,
                direccion = direccion,
                monto    = monto,
                mensaje  = f"Orden {orden.action} enviada a IBKR para {activo}",
            )
        except Exception as e:
            return ResultadoTrade(False, mensaje=f"Error IBKR: {e}")

    # ── Internos ──────────────────────────────────────────────────────────────

    def _next_req(self) -> int:
        self._req_id += 1
        return self._req_id

    @staticmethod
    def _forex_contract(par: str) -> "Contract":
        c = Contract()
        c.secType = "CASH"
        partes    = par.replace("/", ".").split(".")
        c.symbol   = partes[0]
        c.currency = partes[1] if len(partes) > 1 else "USD"
        c.exchange = "IDEALPRO"
        return c

    @staticmethod
    def _duracion_ibkr(n: int, periodo_seg: int) -> str:
        total_seg = n * periodo_seg
        if total_seg < 86400:      return f"{max(1, total_seg // 3600 + 1)} H"
        if total_seg < 86400 * 30: return f"{total_seg // 86400 + 1} D"
        return "1 M"

    @staticmethod
    def _barra_ibkr(periodo_seg: int) -> str:
        map_ = {
            5: "5 secs", 10: "10 secs", 15: "15 secs", 30: "30 secs",
            60: "1 min", 120: "2 mins", 300: "5 mins",
            900: "15 mins", 1800: "30 mins", 3600: "1 hour", 86400: "1 day",
        }
        return map_.get(periodo_seg, "1 min")

    def _cargar_config(self) -> dict:
        try:
            if os.path.exists(_CONF_FILE):
                with open(_CONF_FILE) as f:
                    return json.load(f)
        except Exception:
            pass
        return {"host": "127.0.0.1", "port": 7497}   # 7497 = PAPER (seguro)

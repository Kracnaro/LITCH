"""
schwab_broker.py — Conector Charles Schwab para LITCH.

Usa la API oficial de Charles Schwab (REST/OAuth 2.0).
Schwab absorbió TD Ameritrade en 2020 y tiene una de las mejores APIs
del mundo para trading programático.

Requisitos:
  1. Cuenta en Charles Schwab International (o US)
  2. Registrar una "app" en developer.schwab.com
  3. Obtener Client ID y Client Secret
  4. En LITCH, di: 'conectar schwab'

Charles Schwab ofrece:
  - Acciones (NYSE, NASDAQ, internacionales)
  - ETFs, Fondos mutuos
  - Opciones americanas y europeas
  - Forex
  - Futuros
  - Comisiones $0 en acciones y ETFs en EEUU
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import webbrowser
from typing import List, Optional
from urllib.parse import urlencode, urlparse, parse_qs

from .base import BrokerBase, InfoActivo, ResultadoTrade

try:
    import requests as _req
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

_CONF_FILE  = os.path.join(
    os.path.dirname(__file__), "..", "..", "memoria_ap", "schwab_config.json")
_TOKEN_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "memoria_ap", "schwab_tokens.json")

_BASE_URL    = "https://api.schwabapi.com/marketdata/v1"
_TRADER_URL  = "https://api.schwabapi.com/trader/v1"
_AUTH_URL    = "https://api.schwabapi.com/v1/oauth/authorize"
_TOKEN_URL   = "https://api.schwabapi.com/v1/oauth/token"


class SchwabBroker(BrokerBase):
    """
    Conector a Charles Schwab via REST API oficial.

    Instrucciones de configuración:
    1. Ve a developer.schwab.com
    2. Crea una nueva aplicación (App)
    3. Anota el App Key (Client ID) y App Secret
    4. En LITCH, di: 'configurar schwab KEY:SECRET'
    5. Se abrirá el navegador para autorizar — pega la URL de retorno
    """

    nombre      = "Charles Schwab"
    descripcion = "Acciones, ETFs, Opciones, Forex — Comisión $0 en EEUU"

    def __init__(self):
        self._client_id     = ""
        self._client_secret = ""
        self._access_token  = ""
        self._refresh_token = ""
        self._token_expiry  = 0.0
        self._conectado     = False
        self._cuenta_id     = ""
        self._lock          = threading.Lock()

    @staticmethod
    def disponible() -> bool:
        return _REQ_OK

    # ── Configuración ─────────────────────────────────────────────────────────

    def configurar(self, client_id: str, client_secret: str) -> None:
        """Guarda las credenciales de la app Schwab."""
        self._client_id     = client_id
        self._client_secret = client_secret
        os.makedirs(os.path.dirname(_CONF_FILE), exist_ok=True)
        with open(_CONF_FILE, "w") as f:
            json.dump({
                "client_id":     client_id,
                "client_secret": client_secret,
            }, f)

    def _cargar_config(self) -> bool:
        try:
            if os.path.exists(_CONF_FILE):
                with open(_CONF_FILE) as f:
                    cfg = json.load(f)
                self._client_id     = cfg.get("client_id", "")
                self._client_secret = cfg.get("client_secret", "")
                return bool(self._client_id)
        except Exception:
            pass
        return False

    def _cargar_tokens(self) -> bool:
        try:
            if os.path.exists(_TOKEN_FILE):
                with open(_TOKEN_FILE) as f:
                    tk = json.load(f)
                self._access_token  = tk.get("access_token", "")
                self._refresh_token = tk.get("refresh_token", "")
                self._token_expiry  = float(tk.get("expiry", 0))
                self._cuenta_id     = tk.get("cuenta_id", "")
                return bool(self._access_token)
        except Exception:
            pass
        return False

    def _guardar_tokens(self) -> None:
        with open(_TOKEN_FILE, "w") as f:
            json.dump({
                "access_token":  self._access_token,
                "refresh_token": self._refresh_token,
                "expiry":        self._token_expiry,
                "cuenta_id":     self._cuenta_id,
            }, f)

    # ── Conexión ──────────────────────────────────────────────────────────────

    def conectar(self, credenciales: dict = None) -> tuple[bool, str]:
        if not _REQ_OK:
            return False, "requests no disponible. Ejecuta: py -m pip install requests"

        if credenciales:
            self.configurar(
                credenciales.get("client_id", ""),
                credenciales.get("client_secret", ""),
            )
        else:
            if not self._cargar_config():
                return False, (
                    "Sin configuración Schwab. Di:\n"
                    "'configurar schwab TUCLIENTEID:TUCLIENTSECRET'\n"
                    "Obtén las credenciales en developer.schwab.com"
                )

        # Intentar con refresh token primero
        if self._cargar_tokens():
            if self._token_expiry > time.time() + 60:
                self._conectado = True
                return True, "Reconectado a Schwab con token existente"
            elif self._refresh_token:
                ok, msg = self._renovar_token()
                if ok:
                    self._conectado = True
                    return True, "Token Schwab renovado"

        # Flujo OAuth completo
        return self._auth_flow()

    def _auth_flow(self) -> tuple[bool, str]:
        """Inicia el flujo OAuth abriendo el navegador."""
        params = {
            "client_id":     self._client_id,
            "redirect_uri":  "https://127.0.0.1",
            "response_type": "code",
            "scope":         "readonly",
        }
        url = f"{_AUTH_URL}?{urlencode(params)}"
        webbrowser.open(url)
        return False, (
            "Se abrió el navegador para autorizar Schwab.\n"
            "Después de autorizar, di:\n"
            "'código schwab URL_DE_RETORNO'\n"
            "(pega la URL completa que te redirigió)"
        )

    def procesar_codigo_auth(self, redirect_url: str) -> tuple[bool, str]:
        """Procesa el código de autorización del flujo OAuth."""
        try:
            parsed = urlparse(redirect_url)
            codigo = parse_qs(parsed.query).get("code", [None])[0]
            if not codigo:
                return False, "URL de retorno no contiene código de autorización"

            creds = base64.b64encode(
                f"{self._client_id}:{self._client_secret}".encode()
            ).decode()

            resp = _req.post(_TOKEN_URL, headers={
                "Authorization": f"Basic {creds}",
                "Content-Type":  "application/x-www-form-urlencoded",
            }, data={
                "grant_type":   "authorization_code",
                "code":         codigo,
                "redirect_uri": "https://127.0.0.1",
            }, timeout=10)

            if resp.status_code == 200:
                tk = resp.json()
                self._access_token  = tk["access_token"]
                self._refresh_token = tk.get("refresh_token", "")
                self._token_expiry  = time.time() + tk.get("expires_in", 1800)
                self._guardar_tokens()
                self._conectado = True
                return True, "Schwab autorizado exitosamente"
            else:
                return False, f"Error OAuth Schwab: {resp.status_code}"
        except Exception as e:
            return False, f"Error procesando código: {e}"

    def _renovar_token(self) -> tuple[bool, str]:
        try:
            creds = base64.b64encode(
                f"{self._client_id}:{self._client_secret}".encode()
            ).decode()
            resp = _req.post(_TOKEN_URL, headers={
                "Authorization": f"Basic {creds}",
                "Content-Type":  "application/x-www-form-urlencoded",
            }, data={
                "grant_type":    "refresh_token",
                "refresh_token": self._refresh_token,
            }, timeout=10)
            if resp.status_code == 200:
                tk = resp.json()
                self._access_token = tk["access_token"]
                self._token_expiry = time.time() + tk.get("expires_in", 1800)
                self._guardar_tokens()
                return True, "Token renovado"
            return False, f"Error renovar token: {resp.status_code}"
        except Exception as e:
            return False, f"Error: {e}"

    def desconectar(self) -> None:
        self._conectado = False

    @property
    def conectado(self) -> bool:
        return self._conectado

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    # ── Cuenta ────────────────────────────────────────────────────────────────

    def saldo(self, modo: str = None) -> float:
        if not self.conectado:
            return 0.0
        try:
            resp = _req.get(f"{_TRADER_URL}/accounts",
                            headers=self._headers(), timeout=5)
            if resp.status_code == 200:
                cuentas = resp.json()
                if cuentas:
                    self._cuenta_id = cuentas[0].get("accountNumber", "")
                    return float(
                        cuentas[0].get("aggregatedBalance", {})
                        .get("liquidationValue", 0)
                    )
        except Exception:
            pass
        return 0.0

    def modo_cuenta(self) -> str:
        return "real"   # Schwab no tiene modo demo integrado

    def cambiar_modo(self, modo: str) -> bool:
        return False   # Schwab usa cuentas separadas paper/real

    # ── Activos ───────────────────────────────────────────────────────────────

    def activos_disponibles(self, tipo: str = "acciones") -> List[InfoActivo]:
        """Retorna lista de activos populares con datos en tiempo real."""
        if not self.conectado:
            return []
        # Lista predefinida de símbolos populares
        simbolos = {
            "acciones": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"],
            "etf":      ["SPY", "QQQ", "IWM", "GLD", "SLV", "USO"],
            "cripto":   ["BTC/USD", "ETH/USD"],
        }.get(tipo, ["AAPL", "MSFT", "GOOGL"])

        activos = []
        try:
            syms = ",".join(simbolos)
            resp = _req.get(f"{_BASE_URL}/quotes",
                            headers=self._headers(),
                            params={"symbols": syms, "fields": "quote"},
                            timeout=10)
            if resp.status_code == 200:
                datos = resp.json()
                for sym, info in datos.items():
                    q = info.get("quote", {})
                    activos.append(InfoActivo(
                        simbolo     = sym,
                        nombre      = sym,
                        payout_pct  = 0.0,
                        precio      = float(q.get("lastPrice", 0)),
                        tendencia   = ("sube" if q.get("netChange", 0) > 0 else "baja"),
                        disponible  = True,
                    ))
        except Exception:
            pass
        return activos

    def velas(self, activo: str, periodo_seg: int, n: int = 200) -> list:
        if not self.conectado:
            return []
        try:
            freq_type = "minute" if periodo_seg < 3600 else "daily"
            freq      = max(1, periodo_seg // 60) if periodo_seg < 3600 else 1
            resp = _req.get(
                f"{_BASE_URL}/pricehistory",
                headers=self._headers(),
                params={
                    "symbol":           activo,
                    "periodType":       "day",
                    "period":           1,
                    "frequencyType":    freq_type,
                    "frequency":        freq,
                    "needExtendedHoursData": False,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                candles = resp.json().get("candles", [])
                return [{
                    "time":   c.get("datetime", 0) / 1000,
                    "open":   float(c.get("open",   0)),
                    "high":   float(c.get("high",   0)),
                    "low":    float(c.get("low",    0)),
                    "close":  float(c.get("close",  0)),
                    "volume": float(c.get("volume", 0)),
                } for c in candles[-n:]]
        except Exception:
            pass
        return []

    def ejecutar_trade(self, activo: str, direccion: str,
                       monto: float, venc_seg: int) -> ResultadoTrade:
        if not self.conectado or not self._cuenta_id:
            return ResultadoTrade(False, mensaje="No conectado a Schwab o sin cuenta")
        try:
            accion = "BUY" if direccion == "V" else "SELL"
            orden = {
                "orderType":  "MARKET",
                "session":    "NORMAL",
                "duration":   "DAY",
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [{
                    "instruction": accion,
                    "quantity":    monto,
                    "instrument":  {"symbol": activo, "assetType": "EQUITY"},
                }],
            }
            resp = _req.post(
                f"{_TRADER_URL}/accounts/{self._cuenta_id}/orders",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=orden,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                return ResultadoTrade(
                    exito     = True,
                    activo    = activo,
                    direccion = direccion,
                    monto     = monto,
                    mensaje   = f"Orden {accion} enviada a Schwab para {activo}",
                )
            else:
                return ResultadoTrade(False, mensaje=f"Schwab rechazó: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            return ResultadoTrade(False, mensaje=f"Error Schwab: {e}")

    def cotizacion(self, simbolo: str) -> dict:
        """Precio actual y datos de la cotización."""
        if not self.conectado:
            return {}
        try:
            resp = _req.get(f"{_BASE_URL}/quotes",
                            headers=self._headers(),
                            params={"symbols": simbolo},
                            timeout=5)
            if resp.status_code == 200:
                return resp.json().get(simbolo, {}).get("quote", {})
        except Exception:
            pass
        return {}

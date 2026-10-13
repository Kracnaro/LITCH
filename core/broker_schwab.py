"""
Charles Schwab — integración programática completa.

Schwab es el mayor broker retail de EEUU por activos ($9 trillones AUM).
En 2020 adquirió TD Ameritrade e integró la plataforma Thinkorswim (TOS).
Su API usa OAuth2 moderno — más seguro que claves simples.

━━━ CONFIGURACIÓN (una sola vez) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1. Abre cuenta en schwab.com (GRATIS, sin mínimo de saldo)
 2. Ve a developer.schwab.com → Create App
 3. Copia App Key (client_id) y App Secret (client_secret)
 4. Redirige a: https://127.0.0.1  (para uso local)
 5. pip install requests

━━━ FLUJO DE AUTENTICACIÓN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 OAuth2 con refresh_token persistente:
   Primera vez  → Abre navegador → usuario autoriza → guarda tokens
   Siguientes   → Usa refresh_token (válido 7 días) → renueva automático

━━━ DIFERENCIAS vs IQ Option ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 • Acciones reales (ownership) — no expiran, no hay payout fijo
 • P&L depende del precio de mercado — puedes perder más de lo invertido
 • Comisiones: $0 en acciones/ETFs US — opciones: $0.65/contrato
 • Horario: 09:30–16:00 ET (extended 07:00–20:00 con menos liquidez)

━━━ ÓRDENES SCHWAB ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Tipos:  MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP
 Sesión: NORMAL (09:30-16:00), AM, PM, SEAMLESS (extended hours)
 Duración: DAY, GOOD_TILL_CANCEL, FILL_OR_KILL, IMMEDIATE_OR_CANCEL
"""

import base64
import json
import os
import threading
import time
import webbrowser
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

from . import memoria as mem_mod

try:
    import requests
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

# ── Constantes de la API ─────────────────────────────────────────────────────
_BASE_URL    = "https://api.schwabapi.com/trader/v1"
_AUTH_URL    = "https://api.schwabapi.com/v1/oauth/authorize"
_TOKEN_URL   = "https://api.schwabapi.com/v1/oauth/token"
_MARKET_URL  = "https://api.schwabapi.com/marketdata/v1"

_TOKEN_FICHERO = "schwab_tokens.json"


class BrokerSchwab:
    """
    Cliente completo de Charles Schwab para Litch.

    Flujo rápido:
        schwab = BrokerSchwab(app, client_id="XXXX", client_secret="YYYY")
        schwab.autenticar()          # abre navegador primera vez
        schwab.comprar("AAPL", 1)   # compra 1 acción a precio de mercado
        schwab.cotizacion("AAPL")   # precio actual
        schwab.posiciones()         # lo que tienes ahora
    """

    def __init__(self, app,
                 client_id: str = None,
                 client_secret: str = None,
                 redirect_uri: str = "https://127.0.0.1"):
        self.app           = app
        self._client_id    = client_id    or self._leer_cfg("schwab_client_id")
        self._client_secret= client_secret or self._leer_cfg("schwab_client_secret")
        self._redirect_uri = redirect_uri
        self._access_token : Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expira : float = 0.0
        self._lock         = threading.Lock()
        self._ruta_tokens  = os.path.join(mem_mod.ruta_memoria_ap(), _TOKEN_FICHERO)
        self._historial: list[dict] = []
        self._cargar_tokens()

    # ── Configuración ─────────────────────────────────────────────────────────

    def _leer_cfg(self, clave: str) -> str:
        """Lee clave de client_id/secret guardada en config."""
        try:
            return self.app.mem["config"].get(clave, "")
        except Exception:
            return ""

    def guardar_credenciales(self, client_id: str, client_secret: str) -> None:
        """
        Guarda las credenciales del desarrollador en la memoria de Litch.
        Solo necesitas hacerlo una vez.
        """
        cfg = self.app.mem["config"]
        cfg["schwab_client_id"]     = client_id
        cfg["schwab_client_secret"] = client_secret
        self._client_id     = client_id
        self._client_secret = client_secret
        mem_mod.guardar(self.app.mem)
        self.app.log("[Schwab] Credenciales guardadas en memoria.")

    # ── OAuth2 ────────────────────────────────────────────────────────────────

    def autenticar(self) -> bool:
        """
        Inicia el flujo OAuth2. La primera vez abre el navegador.
        Las veces siguientes usa el refresh_token guardado.
        """
        if not _REQ_OK:
            self.app.log("[Schwab] requests no instalado. Ejecuta: pip install requests")
            return False
        if not self._client_id or not self._client_secret:
            self.app.log("[Schwab] Falta client_id o client_secret. "
                         "Usa schwab.guardar_credenciales(id, secret).")
            return False

        # Si tenemos refresh_token válido, renovar silenciosamente
        if self._refresh_token and time.time() < self._token_expira - 60:
            return True
        if self._refresh_token:
            return self._renovar_token()

        # Primera vez: flujo de autorización completo
        return self._flujo_autorizacion()

    def _flujo_autorizacion(self) -> bool:
        """Abre el navegador para que el usuario autorice a Litch."""
        params = {
            "response_type": "code",
            "client_id":     self._client_id,
            "redirect_uri":  self._redirect_uri,
            "scope":         "api",
        }
        url = f"{_AUTH_URL}?{urlencode(params)}"
        self.app.log(f"[Schwab] Abre este URL en tu navegador para autorizar:\n{url}")
        self.app.decir("Para conectar Schwab, necesito que abras el enlace que "
                       "dejé en el registro y pegues la URL de respuesta aquí.")
        # NO abrimos el navegador automáticamente: Litch nunca debe tomar el
        # control de tus aplicaciones por su cuenta. El enlace queda en el log
        # y TÚ decides si lo abres. (Config «schwab_abrir_navegador»: true
        # para restaurar el comportamiento anterior.)
        try:
            if self.app.mem["config"].get("schwab_abrir_navegador", False):
                webbrowser.open(url)
        except Exception:
            pass
        # El usuario debe pegar la URL de redirección con el code
        # Esto lo maneja cerebro.py cuando el usuario dice "el código es XYZ"
        return False  # pending user action

    def completar_autorizacion(self, redirect_url: str) -> bool:
        """
        Completa el flujo OAuth2 con la URL que el usuario pegó.
        Llamar desde cerebro.py cuando el usuario entrega la URL.
        """
        try:
            parsed = urlparse(redirect_url)
            code   = parse_qs(parsed.query).get("code", [None])[0]
            if not code:
                self.app.log("[Schwab] No encontré 'code' en la URL.")
                return False
            return self._canjear_code(code)
        except Exception as e:
            self.app.log(f"[Schwab] Error al parsear URL: {e}")
            return False

    def _canjear_code(self, code: str) -> bool:
        credenciales = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()).decode()
        try:
            r = requests.post(_TOKEN_URL, headers={
                "Authorization": f"Basic {credenciales}",
                "Content-Type":  "application/x-www-form-urlencoded",
            }, data={
                "grant_type":   "authorization_code",
                "code":          code,
                "redirect_uri":  self._redirect_uri,
            }, timeout=15)
            r.raise_for_status()
            self._guardar_tokens(r.json())
            self.app.log("[Schwab] ✓ Autenticación completada.")
            return True
        except Exception as e:
            self.app.log(f"[Schwab] Error canjeando code: {e}")
            return False

    def _renovar_token(self) -> bool:
        """Renueva el access_token usando el refresh_token."""
        credenciales = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()).decode()
        try:
            r = requests.post(_TOKEN_URL, headers={
                "Authorization": f"Basic {credenciales}",
                "Content-Type":  "application/x-www-form-urlencoded",
            }, data={
                "grant_type":    "refresh_token",
                "refresh_token": self._refresh_token,
            }, timeout=15)
            r.raise_for_status()
            self._guardar_tokens(r.json())
            return True
        except Exception as e:
            self.app.log(f"[Schwab] Error renovando token: {e}")
            self._refresh_token = None  # token expirado, re-autorizar
            return False

    def _guardar_tokens(self, datos: dict) -> None:
        self._access_token  = datos.get("access_token")
        self._refresh_token = datos.get("refresh_token", self._refresh_token)
        expires_in          = datos.get("expires_in", 1800)
        self._token_expira  = time.time() + expires_in
        try:
            os.makedirs(os.path.dirname(self._ruta_tokens), exist_ok=True)
            with open(self._ruta_tokens, "w", encoding="utf-8") as f:
                json.dump({
                    "access_token":  self._access_token,
                    "refresh_token": self._refresh_token,
                    "expira":        self._token_expira,
                }, f)
        except Exception:
            pass

    def _cargar_tokens(self) -> None:
        if not os.path.exists(self._ruta_tokens):
            return
        try:
            with open(self._ruta_tokens, "r", encoding="utf-8") as f:
                t = json.load(f)
            self._access_token  = t.get("access_token")
            self._refresh_token = t.get("refresh_token")
            self._token_expira  = t.get("expira", 0.0)
        except Exception:
            pass

    # ── HTTP helper ───────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        if not self._asegurar_token():
            return None
        try:
            r = requests.get(
                f"{_BASE_URL}{endpoint}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params=params or {},
                timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            self.app.log(f"[Schwab] HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None
        except Exception as e:
            self.app.log(f"[Schwab] Error GET {endpoint}: {e}")
            return None

    def _post(self, endpoint: str, body: dict) -> Optional[dict]:
        if not self._asegurar_token():
            return None
        try:
            r = requests.post(
                f"{_BASE_URL}{endpoint}",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type":  "application/json",
                },
                json=body,
                timeout=15)
            r.raise_for_status()
            return r.json() if r.text else {"ok": True}
        except requests.exceptions.HTTPError as e:
            self.app.log(f"[Schwab] HTTP {e.response.status_code}: {e.response.text[:300]}")
            return None
        except Exception as e:
            self.app.log(f"[Schwab] Error POST {endpoint}: {e}")
            return None

    def _asegurar_token(self) -> bool:
        with self._lock:
            if time.time() >= self._token_expira - 60:
                return self._renovar_token()
            return bool(self._access_token)

    # ── Cotizaciones ──────────────────────────────────────────────────────────

    def cotizacion(self, simbolo: str) -> Optional[dict]:
        """Precio en tiempo real (o con delay de 15 min para cuentas sin datos premium)."""
        if not _REQ_OK:
            return None
        try:
            r = requests.get(
                f"{_MARKET_URL}/quotes",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params={"symbols": simbolo.upper(), "fields": "quote,fundamental"},
                timeout=10)
            r.raise_for_status()
            data = r.json().get(simbolo.upper(), {})
            q    = data.get("quote", {})
            return {
                "simbolo":    simbolo.upper(),
                "precio":     q.get("lastPrice") or q.get("mark", 0),
                "bid":        q.get("bidPrice", 0),
                "ask":        q.get("askPrice", 0),
                "apertura":   q.get("openPrice", 0),
                "alto":       q.get("highPrice", 0),
                "bajo":       q.get("lowPrice", 0),
                "volumen":    q.get("totalVolume", 0),
                "cambio_pct": q.get("netPercentChangeInDouble", 0),
                "ts":         time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            self.app.log(f"[Schwab] Error cotización {simbolo}: {e}")
            return None

    # ── Cuenta ────────────────────────────────────────────────────────────────

    def cuentas(self) -> list[dict]:
        """Lista de cuentas asociadas al usuario."""
        data = self._get("/accounts")
        if not data:
            return []
        return [
            {
                "numero":  c.get("securitiesAccount", {}).get("accountNumber"),
                "tipo":    c.get("securitiesAccount", {}).get("type"),
                "efectivo": c.get("securitiesAccount", {})
                             .get("currentBalances", {})
                             .get("cashBalance", 0),
                "equity":  c.get("securitiesAccount", {})
                            .get("currentBalances", {})
                            .get("liquidationValue", 0),
            }
            for c in (data if isinstance(data, list) else [])
        ]

    def primera_cuenta(self) -> Optional[str]:
        """Número de la primera cuenta (la más usada en órdenes)."""
        cuentas = self.cuentas()
        return cuentas[0]["numero"] if cuentas else None

    def posiciones(self, numero_cuenta: str = None) -> list[dict]:
        """Posiciones actuales de la cuenta."""
        cuenta = numero_cuenta or self.primera_cuenta()
        if not cuenta:
            return []
        data = self._get(f"/accounts/{cuenta}", params={"fields": "positions"})
        if not data:
            return []
        pos_raw = (data.get("securitiesAccount", {})
                       .get("positions", []))
        return [
            {
                "simbolo":    p.get("instrument", {}).get("symbol"),
                "cantidad":   p.get("longQuantity", 0) - p.get("shortQuantity", 0),
                "costo":      p.get("averagePrice", 0),
                "valor":      p.get("marketValue", 0),
                "pnl":        p.get("currentDayProfitLoss", 0),
                "pnl_pct":    p.get("currentDayProfitLossPercentage", 0),
            }
            for p in pos_raw
        ]

    # ── Órdenes ───────────────────────────────────────────────────────────────

    def comprar(self, simbolo: str, cantidad: float,
                precio: float = None,
                stop: float = None,
                duracion: str = "DAY",
                cuenta: str = None) -> Optional[dict]:
        """
        Compra acciones/ETFs en Schwab.

        simbolo  : ticker (AAPL, SPY, QQQ, etc.)
        cantidad : número de acciones (puede ser fraccionario para acciones caras)
        precio   : si None → MARKET; si se da → LIMIT
        stop     : precio de stop-loss (crea orden bracket automática)
        duracion : DAY | GOOD_TILL_CANCEL | FILL_OR_KILL
        """
        return self._orden("BUY", simbolo, cantidad, precio, stop, duracion, cuenta)

    def vender(self, simbolo: str, cantidad: float,
               precio: float = None,
               stop: float = None,
               duracion: str = "DAY",
               cuenta: str = None) -> Optional[dict]:
        """Vende acciones. Si no tienes la posición, abre un short."""
        return self._orden("SELL", simbolo, cantidad, precio, stop, duracion, cuenta)

    def _orden(self, instruccion: str, simbolo: str, cantidad: float,
               precio: float = None, stop: float = None,
               duracion: str = "DAY", cuenta: str = None) -> Optional[dict]:
        num_cuenta = cuenta or self.primera_cuenta()
        if not num_cuenta:
            self.app.log("[Schwab] No hay cuenta disponible.")
            return None

        tipo = "LIMIT" if precio else "MARKET"
        leg  = {
            "instruction":  instruccion,
            "quantity":     cantidad,
            "instrument": {
                "symbol":    simbolo.upper(),
                "assetType": "EQUITY",
            },
        }
        body: dict = {
            "orderType":          tipo,
            "session":            "NORMAL",
            "duration":           duracion,
            "orderStrategyType":  "SINGLE",
            "orderLegCollection": [leg],
        }
        if precio:
            body["price"] = round(precio, 2)

        # Orden bracket (entry + stop-loss) si se proporciona stop
        if stop and tipo == "MARKET":
            stop_leg = {
                "instruction":  "SELL" if instruccion == "BUY" else "BUY",
                "quantity":     cantidad,
                "instrument":   leg["instrument"].copy(),
            }
            body = {
                "orderStrategyType":  "TRIGGER",
                "session":            "NORMAL",
                "duration":           "GOOD_TILL_CANCEL",
                "orderLegCollection": [leg],
                "childOrderStrategies": [{
                    "orderType":          "STOP",
                    "session":            "NORMAL",
                    "duration":           "GOOD_TILL_CANCEL",
                    "stopPrice":          round(stop, 2),
                    "orderStrategyType":  "SINGLE",
                    "orderLegCollection": [stop_leg],
                }],
            }

        resultado = self._post(f"/accounts/{num_cuenta}/orders", body)
        if resultado is not None:
            r = {
                "instruccion": instruccion,
                "simbolo":     simbolo.upper(),
                "cantidad":    cantidad,
                "tipo":        tipo,
                "precio":      precio,
                "stop":        stop,
                "cuenta":      num_cuenta,
                "ts":          time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._historial.append(r)
            signo = "🟢" if instruccion == "BUY" else "🔴"
            self.app.log(
                f"[Schwab] {signo} {instruccion} {cantidad}x {simbolo.upper()} | "
                f"tipo={tipo}" +
                (f" @{precio}" if precio else " @MARKET") +
                (f" stop={stop}" if stop else ""))
            return r
        return None

    def cancelar_orden(self, numero_cuenta: str, orden_id: str) -> bool:
        """Cancela una orden pendiente."""
        try:
            r = requests.delete(
                f"{_BASE_URL}/accounts/{numero_cuenta}/orders/{orden_id}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=10)
            r.raise_for_status()
            self.app.log(f"[Schwab] Orden {orden_id} cancelada.")
            return True
        except Exception as e:
            self.app.log(f"[Schwab] Error cancelando {orden_id}: {e}")
            return False

    def ordenes_abiertas(self, cuenta: str = None) -> list[dict]:
        """Lista de órdenes pendientes."""
        num = cuenta or self.primera_cuenta()
        if not num:
            return []
        data = self._get(f"/accounts/{num}/orders",
                         params={"status": "WORKING"})
        if not isinstance(data, list):
            return []
        return [
            {
                "id":       o.get("orderId"),
                "simbolo":  o.get("orderLegCollection", [{}])[0]
                             .get("instrument", {}).get("symbol"),
                "instruccion": o.get("orderLegCollection", [{}])[0]
                               .get("instruction"),
                "cantidad": o.get("quantity"),
                "tipo":     o.get("orderType"),
                "precio":   o.get("price"),
                "estado":   o.get("status"),
            }
            for o in data
        ]

    # ── Resumen ───────────────────────────────────────────────────────────────

    def resumen(self) -> str:
        if not self._access_token:
            return "Schwab: no autenticado (llama autenticar())"
        cuentas = self.cuentas()
        if not cuentas:
            return "Schwab: autenticado pero sin cuentas disponibles"
        c = cuentas[0]
        return (f"Schwab | cuenta={c['numero']} | "
                f"cash=${c['efectivo']:.2f} | equity=${c['equity']:.2f}")

    # ── Conocimiento del broker ───────────────────────────────────────────────

    CONOCIMIENTO = {
        "que_es": (
            "Charles Schwab es el mayor broker retail de los Estados Unidos "
            "con más de $9 TRILLONES en activos de clientes. Fundado en 1971 en San Francisco. "
            "En 2020 adquirió TD Ameritrade (plataforma Thinkorswim). "
            "Regulado por FINRA y SEC. Ofrece acciones, ETFs, opciones, futuros, "
            "bonos, fondos mutuos y asesoramiento automatizado (Schwab Intelligent Portfolios)."
        ),
        "ventajas": (
            "• $0 comisiones en acciones y ETFs US (desde 2019). "
            "• Sin mínimo de saldo para abrir cuenta. "
            "• Plataforma Thinkorswim (TOS) de nivel profesional — la mejor del mercado. "
            "• Acciones fraccionarias desde $5 (Schwab Stock Slices). "
            "• Cuenta de paper trading incluida en TOS. "
            "• Soporte 24/7 por teléfono y chat. "
            "• SIPC protección hasta $500,000."
        ),
        "desventajas": (
            "• No disponible para cuentas fuera de EEUU directamente. "
            "• API más restrictiva que IBKR (require aprobación de desarrollador). "
            "• Opciones cobran $0.65 por contrato. "
            "• Sin acceso a mercados internacionales (solo US principalmente)."
        ),
        "thinkorswim": (
            "Thinkorswim (TOS) es la plataforma avanzada de Schwab (heredada de TD Ameritrade). "
            "Características:\n"
            "• Gráficos avanzados con +200 indicadores técnicos.\n"
            "• Análisis de opciones (cadena de opciones, griegas, volatilidad implícita).\n"
            "• Paper trading integrado — practicar sin riesgo real.\n"
            "• Scanner de acciones personalizable.\n"
            "• ThinkScript — lenguaje propio para crear indicadores personalizados.\n"
            "• Alertas de precios en tiempo real.\n"
            "• Paper trading: menú superior → el menú que dice 'Live trading' → Paper Money"
        ),
        "como_abrir_cuenta": (
            "1. Ve a schwab.com → Abrir cuenta (15-20 minutos).\n"
            "2. Escoge: Individual brokerage account (cuenta individual).\n"
            "3. Necesitas: SSN (si eres residente EEUU) o ITIN (para extranjeros).\n"
            "4. Fondea la cuenta con ACH desde tu banco (mínimo recomendado: $500).\n"
            "5. Descarga Thinkorswim desde schwab.com/thinkorswim.\n"
            "6. Para API: registra tu app en developer.schwab.com.\n"
            "⚠ Si estás fuera de EEUU: abre cuenta en corredora local que use Schwab "
            "como custodio, o prueba Interactive Brokers (disponible globalmente)."
        ),
        "api": (
            "Schwab Individual Trader API:\n"
            "Base URL: https://api.schwabapi.com/trader/v1\n"
            "Auth: OAuth2 (Authorization Code Flow)\n"
            "Endpoints principales:\n"
            "  GET /accounts                       → tus cuentas\n"
            "  GET /accounts/{num}/positions       → posiciones abiertas\n"
            "  POST /accounts/{num}/orders         → colocar orden\n"
            "  DELETE /accounts/{num}/orders/{id}  → cancelar orden\n"
            "  GET /marketdata/v1/quotes?symbols=AAPL → cotización\n"
            "Tokens: access_token (30 min) + refresh_token (7 días)\n"
            "pip install requests"
        ),
        "ordenes": (
            "Tipos de orden en Schwab:\n"
            "• MARKET:      ejecución inmediata al precio actual.\n"
            "• LIMIT:       ejecuta solo al precio indicado o mejor.\n"
            "• STOP:        stop-loss/stop-entry (convierte en MARKET al activar).\n"
            "• STOP_LIMIT:  como STOP pero con límite de precio.\n"
            "• TRAILING_STOP: stop que sigue al precio a distancia fija (% o $).\n\n"
            "Sesiones:\n"
            "• NORMAL:      09:30–16:00 ET (máxima liquidez).\n"
            "• AM:          07:00–09:30 ET (pre-market).\n"
            "• PM:          16:00–20:00 ET (after-hours).\n"
            "• SEAMLESS:    combina todas las sesiones (usar con cuidado).\n\n"
            "Duración:\n"
            "• DAY:              expira al cierre del mercado de hoy.\n"
            "• GOOD_TILL_CANCEL: permanece hasta que se ejecute o canceles.\n"
            "• FILL_OR_KILL:     ejecuta todo o cancela todo inmediatamente."
        ),
        "instrumentos": (
            "Instrumentos disponibles en Schwab:\n"
            "• EQUITY:     acciones de empresas (AAPL, MSFT, TSLA, etc.)\n"
            "• ETF:        fondos cotizados (SPY, QQQ, VTI, SCHD, etc.)\n"
            "• OPTION:     opciones call/put (requiere aprobación de opciones)\n"
            "• MUTUAL_FUND: fondos mutuos (mínimo $1 en muchos casos)\n"
            "• FIXED_INCOME: bonos (Treasuries, corporativos, municipales)\n"
            "• CASH_EQUIVALENT: ETFs de mercado monetario (SNSXX, etc.)\n\n"
            "ETFs más operados por traders latinoamericanos:\n"
            "• SPY  — S&P 500 (el mercado general de EEUU)\n"
            "• QQQ  — NASDAQ 100 (tecnológicas como AAPL, MSFT, NVDA)\n"
            "• IWM  — Russell 2000 (pequeñas empresas)\n"
            "• SCHD — dividendos de alta calidad (ingreso pasivo)\n"
            "• VTI  — todo el mercado US en un ETF (Vanguard)"
        ),
        "gestion_riesgo": (
            "Gestión de riesgo profesional en Schwab:\n"
            "1. REGLA DEL 1%: Nunca arriesgar más del 1% del capital por trade.\n"
            "   Ejemplo: $10,000 en cuenta → máximo $100 de riesgo por operación.\n"
            "2. STOP-LOSS OBLIGATORIO: Coloca siempre stop-loss antes de entrar.\n"
            "   Usa orden bracket (entry + stop) para no olvidarlo.\n"
            "3. RATIO R:R mínimo 1:2: Si arriesgas $100, el objetivo debe ser $200+.\n"
            "4. DIVERSIFICACIÓN: Máximo 20-25% en un solo sector.\n"
            "5. POSITION SIZING: Calculado sobre el riesgo en $, no sobre el capital total.\n"
            "   Fórmula: Cantidad = Riesgo_$  /  (Entrada - Stop_Loss)\n"
            "6. DIARIO: Si pierdes 3% del capital en un día, cierra todo y para.\n"
            "7. SEMANAL: Si pierdes 5% en la semana, tómate la semana siguiente libre."
        ),
    }

    def _cargar_historial(self):
        ruta = os.path.join(mem_mod.ruta_memoria_ap(), "schwab_historial.json")
        if os.path.exists(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    self._historial = json.load(f)
            except Exception:
                self._historial = []

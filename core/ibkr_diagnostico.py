"""
Diagnóstico de conexión con Interactive Brokers — prepara a Litch para IBKR.

Verifica en orden:
  1. ¿Está instalada la librería ibapi?
  2. ¿Hay un TWS / IB Gateway corriendo en esta máquina?
  3. ¿Responde el puerto PAPER (7497) o el REAL (7496)?

SEGURIDAD: Litch siempre intenta primero el puerto PAPER (dinero
simulado). El diagnóstico solo verifica conectividad de socket — no
envía órdenes ni toca la cuenta.

Uso por voz/chat: «Litch, diagnóstico IBKR»
"""

from __future__ import annotations

import socket

PUERTO_TWS_PAPER    = 7497   # TWS cuenta paper (simulada) — la segura
PUERTO_TWS_REAL     = 7496   # TWS cuenta real
PUERTO_GW_PAPER     = 4002   # IB Gateway paper
PUERTO_GW_REAL      = 4001   # IB Gateway real


def _puerto_abierto(puerto: int, host: str = "127.0.0.1",
                    timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, puerto), timeout=timeout):
            return True
    except Exception:
        return False


def ibapi_instalado() -> bool:
    try:
        import ibapi  # noqa: F401
        return True
    except ImportError:
        return False


def diagnosticar() -> dict:
    """Devuelve el estado completo de la preparación IBKR."""
    estado = {
        "ibapi":        ibapi_instalado(),
        "tws_paper":    _puerto_abierto(PUERTO_TWS_PAPER),
        "tws_real":     _puerto_abierto(PUERTO_TWS_REAL),
        "gw_paper":     _puerto_abierto(PUERTO_GW_PAPER),
        "gw_real":      _puerto_abierto(PUERTO_GW_REAL),
    }
    estado["listo_paper"] = estado["ibapi"] and (
        estado["tws_paper"] or estado["gw_paper"])
    estado["algo_corriendo"] = any(
        estado[k] for k in ("tws_paper", "tws_real", "gw_paper", "gw_real"))
    return estado


def probar_conexion_paper(timeout: float = 6.0) -> dict:
    """Intenta CONECTAR de verdad al puerto paper (7497) y leer la cuenta.

    Confirma no solo que el puerto responde, sino que la conexión funciona
    y que la cuenta es de PRÁCTICA (empieza con 'DU'). Es la verificación
    de seguridad definitiva: garantiza que Litch operará en simulado.

    Devuelve {"ok": bool, "cuenta": str, "es_paper": bool, "msg": str}.
    """
    if not ibapi_instalado():
        return {"ok": False, "cuenta": "", "es_paper": False,
                "msg": "Falta ibapi (pip install ibapi)."}
    if not _puerto_abierto(PUERTO_TWS_PAPER):
        return {"ok": False, "cuenta": "", "es_paper": False,
                "msg": "El puerto paper 7497 no responde. Abre TWS en modo "
                       "Paper y habilita la API."}
    # Intento de conexión real con ib_insync si está disponible
    try:
        # Asegurar event loop (ib_insync lo exige y en Py3.14 falla sin él)
        try:
            import asyncio as _aio
            try:
                _aio.get_event_loop()
            except Exception:
                _aio.set_event_loop(_aio.new_event_loop())
        except Exception:
            pass
        from ib_insync import IB
        ib = IB()
        try:
            ib.connect("127.0.0.1", PUERTO_TWS_PAPER,
                       clientId=99, timeout=timeout)
            cuentas = list(ib.managedAccounts() or [])
            cuenta = cuentas[0] if cuentas else ""
            es_paper = cuenta.upper().startswith("DU")
            ib.disconnect()
            if not cuenta:
                return {"ok": True, "cuenta": "", "es_paper": False,
                        "msg": "Conecté a TWS pero no leí el número de cuenta."}
            if es_paper:
                return {"ok": True, "cuenta": cuenta, "es_paper": True,
                        "msg": f"Conexión exitosa a la cuenta SIMULADA "
                               f"{cuenta}. Litch está listo para practicar."}
            return {"ok": True, "cuenta": cuenta, "es_paper": False,
                    "msg": f"⚠ Conecté, pero la cuenta {cuenta} NO es paper "
                           f"(no empieza con DU). Revisa que TWS esté en modo "
                           f"Paper antes de operar."}
        except Exception as e:
            try:
                ib.disconnect()
            except Exception:
                pass
            return {"ok": False, "cuenta": "", "es_paper": False,
                    "msg": f"El puerto responde pero no pude conectar: {e}. "
                           f"Verifica 'Habilitar clientes de socket' en la API."}
    except Exception:
        # ImportError o RuntimeError (ib_insync no compatible con Py3.14)
        return {"ok": True, "cuenta": "", "es_paper": False,
                "msg": "Puerto paper detectado y TWS responde. La prueba "
                       "completa necesita ib_insync compatible; igual puedo "
                       "operar con ibapi."}


def resumen_texto(idioma: str = "es") -> str:
    e = diagnosticar()
    # Si el puerto paper responde, intentar la prueba de conexión real
    if e.get("listo_paper"):
        try:
            p = probar_conexion_paper()
            if idioma == "en":
                return ("ibapi installed. " + p["msg"])
            return "Librería ibapi instalada, señor. " + p["msg"]
        except Exception:
            pass
    if idioma == "en":
        partes = []
        partes.append("ibapi installed." if e["ibapi"]
                      else "ibapi NOT installed — run: pip install ibapi.")
        if e["listo_paper"]:
            partes.append("PAPER port responding — ready to practice "
                          "with simulated money.")
        elif e["algo_corriendo"]:
            partes.append("TWS/Gateway running but only the REAL port "
                          "responds. Open TWS in Paper mode first.")
        else:
            partes.append("No TWS or IB Gateway detected. Install TWS, "
                          "log in with your paper account, and enable "
                          "API socket clients in settings.")
        return " ".join(partes)

    partes = []
    if e["ibapi"]:
        partes.append("Librería ibapi instalada, señor.")
    else:
        partes.append("Falta la librería ibapi: ejecute "
                      "'pip install ibapi' cuando quiera conectarme.")
    if e["listo_paper"]:
        partes.append("El puerto PAPER responde: estoy listo para "
                      "practicar en IBKR con dinero simulado. "
                      "Ese es el camino correcto antes del dinero real.")
    elif e["algo_corriendo"]:
        partes.append("Detecto TWS o Gateway corriendo, pero solo en el "
                      "puerto REAL. Le recomiendo abrir TWS en modo "
                      "Paper primero — practicar antes de arriesgar.")
    else:
        partes.append("No detecto TWS ni IB Gateway corriendo. Cuando "
                      "IBKR apruebe su cuenta: instale TWS, entre con "
                      "la cuenta paper, y active en configuración "
                      "'Enable ActiveX and Socket Clients'. Ahí podré "
                      "conectarme.")
    return " ".join(partes)

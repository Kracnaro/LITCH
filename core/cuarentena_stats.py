"""
cuarentena_stats.py — Separar lo medido de lo inventado.

━━━ QUÉ PASÓ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Durante un tiempo el motor de opciones binarias siguió decidiendo y
"ejecutando" con Interactive Brokers en pantalla. Los clics se
bloqueaban — eso funcionó — pero el motor no se enteraba del bloqueo:
daba la operación por enviada, esperaba el resultado leyendo píxeles de
TWS, y anotaba acierto o fallo.

Ninguna de esas operaciones existió. Ni el dinero, ni la entrada, ni el
resultado. Y sin embargo entraron en la memoria de aprendizaje como si
fueran reales, hasta producir un «87 % de aciertos sobre 13 068 trades».

Un número así no es solo inútil: es peligroso, porque invita a confiar.

━━━ QUÉ HACE ESTE MÓDULO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NO borra nada. Borrar sería destruir evidencia y además irreversible.
Lo que hace es marcar: cada operación sospechosa recibe el sello
`sospechosa: True` con el motivo, y las estadísticas se calculan solo
sobre las limpias.

Una operación es sospechosa si se cumple cualquiera de estas:
  · la visión estaba en TWS cuando se registró
  · el clic quedó bloqueado
  · el activo dice IQ Option pero la ventana al frente era TWS

Todo lo demás se respeta. Prefiero quedarme corto marcando que borrar de
más: si una operación buena se marca por error, se puede desmarcar; una
operación borrada no vuelve.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime

SELLO = "sospechosa"
MOTIVO = "motivo_sospecha"


# ── Detección ────────────────────────────────────────────────────────────────

# Días en los que consta, por el registro de actividad, que Interactive
# Brokers estuvo en pantalla mientras el motor binario seguía operando.
# El registro de esas sesiones está lleno de «⛔ Clic bloqueado: cae dentro
# de Interactive Brokers» — cada uno de esos bloqueos es una operación que
# el motor dio por hecha y anotó igual.
#
# Se marcan por fecha porque las operaciones antiguas no guardaban de qué
# bróker venían. A partir de ahora sí lo guardan (campo `bk`), así que
# esta lista no tendrá que crecer.
DIAS_CONTAMINADOS = {"2026-08-02", "2026-08-03"}


def motivo_sospecha(trade: dict) -> str:
    """Devuelve por qué esta operación no es de fiar, o '' si lo es."""
    if not isinstance(trade, dict):
        return ""

    # Sello de origen (operaciones nuevas)
    bk = str(trade.get("bk") or "").lower()
    if bk in ("tws", "ibkr"):
        return "registrada con la visión en Interactive Brokers"

    # Por fecha (operaciones antiguas, que no guardaban el origen)
    dia = str(trade.get("ts", ""))[:10]
    if dia in DIAS_CONTAMINADOS and not bk:
        return (f"del {dia}: ese día el motor binario operó con "
                f"Interactive Brokers en pantalla")

    if trade.get("clic_bloqueado") or trade.get("bloqueado"):
        return "el clic quedó bloqueado: la orden nunca salió"

    bv = str(trade.get("broker_visual") or trade.get("broker") or "").lower()
    if "tws" in bv or "ibkr" in bv or "interactive" in bv:
        return "registrada con la visión en Interactive Brokers"

    if trade.get("ventana_frente_tws"):
        return "TWS estaba al frente: los píxeles leídos no eran de IQ Option"

    return ""


# ── Marcado ──────────────────────────────────────────────────────────────────

def _respaldar(ruta: str) -> str:
    """Copia de seguridad con fecha. Sin esto no se toca nada."""
    destino = f"{ruta}.antes-cuarentena-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy(ruta, destino)
    return destino


def _lista_de_trades(datos):
    """Encuentra la lista de operaciones dentro del JSON, sea cual sea."""
    if isinstance(datos, list):
        return datos, None
    if isinstance(datos, dict):
        for clave in ("trades", "operaciones", "historial", "registros"):
            v = datos.get(clave)
            if isinstance(v, list):
                return v, clave
    return None, None


def marcar_archivo(ruta: str, respaldar: bool = True) -> dict:
    """
    Sella las operaciones sospechosas de un archivo. No borra ninguna.

    Devuelve {"total", "marcadas", "limpias", "respaldo", "motivos"}
    """
    r = {"archivo": os.path.basename(ruta), "total": 0, "marcadas": 0,
         "limpias": 0, "respaldo": "", "motivos": {}, "error": ""}
    if not os.path.exists(ruta):
        r["error"] = "no existe"
        return r
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except Exception as e:
        r["error"] = f"no se pudo leer: {e}"
        return r

    trades, _ = _lista_de_trades(datos)
    if trades is None:
        r["error"] = "no encontré lista de operaciones"
        return r

    r["total"] = len(trades)
    cambios = 0
    for t in trades:
        if not isinstance(t, dict):
            continue
        m = motivo_sospecha(t)
        if m:
            if not t.get(SELLO):
                cambios += 1
            t[SELLO] = True
            t[MOTIVO] = m
            r["marcadas"] += 1
            r["motivos"][m] = r["motivos"].get(m, 0) + 1
        else:
            r["limpias"] += 1

    if cambios:
        if respaldar:
            try:
                r["respaldo"] = os.path.basename(_respaldar(ruta))
            except Exception:
                pass
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)     # atómico: o se escribe entero o nada
    return r


# ── Estadística honesta ──────────────────────────────────────────────────────

def es_limpio(trade: dict) -> bool:
    """True si esta operación cuenta para las estadísticas."""
    return isinstance(trade, dict) and not trade.get(SELLO)


def solo_limpios(trades) -> list:
    """Filtra la lista dejando únicamente lo que de verdad ocurrió."""
    return [t for t in (trades or []) if es_limpio(t)]


def winrate_honesto(trades, minimo: int = 30) -> dict:
    """
    Tasa de acierto sobre operaciones reales, con su intervalo.

    Si hay menos de `minimo` operaciones limpias, NO devuelve porcentaje.
    Un 100 % de tres operaciones no es un 100 %: es no saber. Decir «no
    sé» es más útil que decir un número bonito que no significa nada.
    """
    limpios = solo_limpios(trades)
    n = len(limpios)
    res = {"n": n, "descartadas": len(trades or []) - n,
           "wr": None, "lo": None, "hi": None, "suficiente": n >= minimo}
    if n == 0:
        res["texto"] = "No queda ninguna operación de fiar."
        return res

    def _gano(t):
        v = t.get("resultado", t.get("res", t.get("win")))
        if isinstance(v, bool):
            return v
        return str(v).upper() in ("WIN", "GANO", "GANÓ", "ACIERTO", "1", "TRUE")

    ganadas = sum(1 for t in limpios if _gano(t))
    p = ganadas / n

    # Intervalo de Wilson al 95 %: honesto con muestras pequeñas
    z = 1.96
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    margen = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    res["wr"] = round(p * 100, 1)
    res["lo"] = round(max(0.0, centro - margen) * 100, 1)
    res["hi"] = round(min(1.0, centro + margen) * 100, 1)

    if not res["suficiente"]:
        res["texto"] = (f"{ganadas} de {n} operaciones reales. Son muy "
                        f"pocas para dar un porcentaje con cara seria "
                        f"(hacen falta {minimo}).")
    else:
        res["texto"] = (f"{res['wr']} % sobre {n} operaciones reales "
                        f"(entre {res['lo']} % y {res['hi']} % con 95 % "
                        f"de confianza).")
    if res["descartadas"]:
        res["texto"] += f" Descarté {res['descartadas']} que no ocurrieron."
    return res


# ── Barrido completo ─────────────────────────────────────────────────────────

ARCHIVOS = ("fallos.json", "trades.json", "historial.json",
            "memoria_acciones.json", "estadisticas.json",
            "fallo_db.json", "operaciones.json")


def limpiar_todo(app=None, carpeta: str = "") -> str:
    """Pasa la cuarentena por toda la memoria y cuenta lo que encontró."""
    if not carpeta:
        try:
            from . import memoria as _mem
            carpeta = _mem.ruta_memoria_ap()
        except Exception:
            carpeta = "MEMORIA_AP"

    lineas = ["CUARENTENA DE ESTADÍSTICAS", ""]
    total_m = total_l = 0
    tocados = 0

    for nombre in os.listdir(carpeta) if os.path.isdir(carpeta) else []:
        if not nombre.endswith(".json") or ".antes-cuarentena-" in nombre:
            continue
        if nombre not in ARCHIVOS and "trade" not in nombre and "fallo" not in nombre:
            continue
        r = marcar_archivo(os.path.join(carpeta, nombre))
        if r["error"] or r["total"] == 0:
            continue
        tocados += 1
        total_m += r["marcadas"]
        total_l += r["limpias"]
        lineas.append(f"· {r['archivo']}: {r['total']} operaciones — "
                      f"{r['marcadas']} en cuarentena, {r['limpias']} limpias")
        for m, c in sorted(r["motivos"].items(), key=lambda x: -x[1]):
            lineas.append(f"    {c} × {m}")
        if r["respaldo"]:
            lineas.append(f"    respaldo: {r['respaldo']}")

    if not tocados:
        return ("No encontré archivos de operaciones que revisar, señor. "
                "Puede que la memoria esté en otro sitio.")

    lineas.append("")
    lineas.append(f"TOTAL: {total_m} operaciones marcadas como no ocurridas, "
                  f"{total_l} limpias.")
    lineas.append("")
    lineas.append("No he borrado nada. Las sospechosas quedan marcadas y "
                  "fuera de las estadísticas, pero siguen en el archivo por "
                  "si hay que revisarlas.")
    texto = "\n".join(lineas)
    if app is not None:
        try:
            app.log("[Cuarentena] " + texto.replace("\n", " | ")[:300])
        except Exception:
            pass
    return texto


__all__ = ["motivo_sospecha", "marcar_archivo", "es_limpio", "solo_limpios",
           "winrate_honesto", "limpiar_todo", "SELLO", "MOTIVO"]

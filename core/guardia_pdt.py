"""
guardia_pdt.py — Protección contra la regla Pattern Day Trader.

QUÉ ES Y POR QUÉ LE AFECTA A USTED EN CONCRETO
──────────────────────────────────────────────
En Estados Unidos, FINRA considera «day trade» comprar y vender el MISMO
valor el MISMO día. Si una cuenta con menos de 25.000 dólares hace
4 o más day trades en 5 días hábiles, queda marcada como Pattern Day
Trader y el broker **la restringe durante 90 días**.

Noventa días sin poder operar. No es una multa: es la cuenta congelada.

Y aquí está la trampa que casi nadie ve venir: **un bracket que alcanza su
objetivo o su stop el mismo día en que se abrió ES un day trade.** Entrar
por la mañana y que salte el stop por la tarde cuenta. No hace falta
intención de hacer day trading para acabar marcado.

Con tres operaciones al día, en dos días se puede llegar al límite sin
haberlo pretendido jamás.

CÓMO LO EVITA LITCH
───────────────────
Lleva la cuenta de los day trades reales de los últimos 5 días hábiles y
avisa al llegar a 2. Al llegar a 3, deja de abrir operaciones nuevas que
puedan cerrarse el mismo día.

El límite propio es 3, no 4, a propósito: dejar un margen de uno es lo
que evita que un cierre inesperado le cruce la línea.

NOTA HONESTA SOBRE LA CUENTA SIMULADA
─────────────────────────────────────
En paper trading esto no le va a pasar: IBKR no restringe cuentas
simuladas por PDT. Pero el hábito se construye ahora. Si Litch le deja
hacer seis day trades diarios en la simulación, usted va a llevar ese
ritmo al dinero real y la cuenta se le bloqueará la primera semana.

Se practica como se juega.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "day_trades.json")

LIMITE_FINRA = 4          # a partir de aquí, FINRA marca la cuenta
LIMITE_PROPIO = 3         # Litch se detiene antes, con margen
DIAS_VENTANA = 5          # días hábiles que mira la regla
UMBRAL_CAPITAL = 25000.0  # por encima de esto, la regla no aplica


# ── Persistencia ────────────────────────────────────────────────────────────

def _cargar() -> list:
    try:
        with open(_RUTA, encoding="utf-8") as f:
            return json.load(f).get("day_trades", [])
    except Exception:
        return []


def _guardar(lista: list) -> None:
    try:
        os.makedirs(os.path.dirname(_RUTA), exist_ok=True)
        tmp = _RUTA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"day_trades": lista,
                       "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")},
                      f, ensure_ascii=False, indent=1)
        os.replace(tmp, _RUTA)
    except Exception:
        pass


# ── Días hábiles ────────────────────────────────────────────────────────────

def _dias_habiles_atras(n: int) -> str:
    """La fecha de hace N días hábiles (sin contar fines de semana).

    La ventana de FINRA son días DE MERCADO, no días naturales. Contar
    naturales dejaría fuera operaciones que sí cuentan, y avisaría tarde.
    """
    d = datetime.now()
    contados = 0
    while contados < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            contados += 1
    return d.strftime("%Y-%m-%d")


# ── Registro ────────────────────────────────────────────────────────────────

def registrar_day_trade(simbolo: str, motivo: str = "") -> int:
    """Anota un day trade. Devuelve cuántos hay en la ventana."""
    lista = _cargar()
    lista.append({"fecha": time.strftime("%Y-%m-%d"),
                  "hora": time.strftime("%H:%M"),
                  "simbolo": simbolo, "motivo": motivo})
    # No dejar crecer el archivo sin fin
    if len(lista) > 200:
        del lista[:-200]
    _guardar(lista)
    return len(en_ventana(lista))


def en_ventana(lista: list | None = None) -> list:
    """Los day trades dentro de los últimos 5 días hábiles."""
    lista = lista if lista is not None else _cargar()
    desde = _dias_habiles_atras(DIAS_VENTANA)
    return [d for d in lista if d.get("fecha", "") >= desde]


def es_day_trade(op: dict) -> bool:
    """¿Esta operación se abrió y cerró el mismo día?"""
    try:
        ap = str(op.get("ts_apertura", ""))[:10]
        ci = str(op.get("ts_cierre", ""))[:10]
        return bool(ap and ci and ap == ci)
    except Exception:
        return False


# ── La comprobación ─────────────────────────────────────────────────────────

def puede_operar(app) -> dict:
    """¿Es seguro abrir una operación nueva hoy?

    Devuelve {"ok": bool, "n": int, "mensaje": str, "aplica": bool}
    """
    r = {"ok": True, "n": 0, "aplica": True, "mensaje": ""}

    # ¿Le aplica la regla? Solo por debajo de 25.000 dólares.
    capital = 0.0
    try:
        br = getattr(app, "broker_ibkr", None)
        if br is not None and getattr(br, "esta_conectado", False):
            bal = br.balance_cuenta() or {}
            capital = float(bal.get("liquidez") or bal.get("valor_neto")
                            or bal.get("efectivo") or 0)
    except Exception:
        pass

    if capital >= UMBRAL_CAPITAL:
        r["aplica"] = False
        r["mensaje"] = (f"Con {capital:,.0f} dólares la regla PDT no le "
                        f"aplica: puede hacer day trading sin límite.")
        return r

    dts = en_ventana()
    n = len(dts)
    r["n"] = n

    if n >= LIMITE_PROPIO:
        r["ok"] = False
        r["mensaje"] = (
            f"⛔ Llevo {n} day trades en los últimos {DIAS_VENTANA} días "
            f"hábiles. No abro más operaciones que puedan cerrarse hoy.\n\n"
            f"Al cuarto, FINRA marca la cuenta como Pattern Day Trader y el "
            f"broker la restringe 90 días. Me detengo en {LIMITE_PROPIO} "
            f"para dejar margen: un stop que salte inesperadamente no puede "
            f"cruzar esa línea si ya estamos parados.\n\n"
            f"Mañana o pasado vuelven a salir de la ventana y seguimos.")
        return r

    if n == LIMITE_PROPIO - 1:
        r["mensaje"] = (
            f"⚠ Aviso: llevo {n} day trades en {DIAS_VENTANA} días hábiles. "
            f"Uno más y me detengo. El límite de FINRA es {LIMITE_FINRA} y "
            f"cruzarlo bloquea la cuenta 90 días.")
    elif n:
        r["mensaje"] = (f"{n} day trade(s) en la ventana de "
                        f"{DIAS_VENTANA} días. Margen suficiente.")
    else:
        r["mensaje"] = "Sin day trades en la ventana. Vía libre."
    return r


def revisar_cierres(app) -> int:
    """Recorre las operaciones cerradas y anota las que fueron day trades.

    Se llama después de cada cierre. Solo cuenta cada operación una vez.
    """
    try:
        from . import memoria_acciones as mem_mod
        ops = list(mem_mod.obtener()._ops)
    except Exception:
        return 0

    lista = _cargar()
    ya = {f"{d.get('fecha')}|{d.get('simbolo')}|{d.get('op_id','')}"
          for d in lista}

    nuevos = 0
    for op in ops:
        if op.get("abierta") or not es_day_trade(op):
            continue
        clave = (f"{str(op.get('ts_cierre',''))[:10]}|"
                 f"{op.get('simbolo')}|{op.get('id')}")
        if clave in ya:
            continue
        lista.append({"fecha": str(op.get("ts_cierre", ""))[:10],
                      "hora": str(op.get("ts_cierre", ""))[11:16],
                      "simbolo": op.get("simbolo"),
                      "op_id": op.get("id"),
                      "motivo": op.get("motivo_cierre", "")})
        ya.add(clave)
        nuevos += 1

    if nuevos:
        if len(lista) > 200:
            del lista[:-200]
        _guardar(lista)
        n = len(en_ventana(lista))
        try:
            app.log(f"[PDT] {nuevos} day trade(s) nuevo(s). Van {n} en "
                    f"{DIAS_VENTANA} días hábiles (límite propio "
                    f"{LIMITE_PROPIO}, de FINRA {LIMITE_FINRA}).")
        except Exception:
            pass
    return nuevos


def estado(app) -> str:
    """Informe legible del estado PDT."""
    v = puede_operar(app)
    if not v.get("aplica"):
        return v["mensaje"]

    dts = en_ventana()
    lineas = [f"REGLA PDT — {len(dts)} day trade(s) en "
              f"{DIAS_VENTANA} días hábiles",
              f"  Mi límite: {LIMITE_PROPIO}  ·  Límite de FINRA: "
              f"{LIMITE_FINRA} (bloqueo de 90 días)"]
    for d in dts[-5:]:
        lineas.append(f"    {d.get('fecha')} {d.get('hora','')} "
                      f"{d.get('simbolo')} — {d.get('motivo','')}")
    lineas.append("")
    lineas.append(v["mensaje"])
    lineas.append("")
    lineas.append("Un day trade es comprar y vender lo mismo el mismo día. "
                  "Un bracket cuyo stop salta la misma tarde en que entró "
                  "cuenta como uno, aunque usted no pretendiera hacer day "
                  "trading.")
    return "\n".join(lineas)

"""
protocolo_agente.py — Litch cumple el protocolo de AGENTE.md.

Implementa dos exigencias del documento raíz que faltaban en el código:

  · B.4 — VERIFICACIÓN DE LOS CINCO DATOS antes de que una orden se
    transmita: cuenta, símbolo, acción, cantidad, tipo y precio.

  · D.5 — VIGILANCIA DE EXCESS LIQUIDITY: el colchón sobre el margen
    exigido. Si se acerca a cero, IBKR liquida posiciones POR LA FUERZA,
    al precio que haya, eligiendo ella qué cerrar.

POR QUÉ LOS CINCO DATOS, UNO POR UNO
────────────────────────────────────
No es burocracia. Cada uno de los cinco corresponde a un error real que
arruina cuentas, y son errores de DEDO, no de estrategia:

  1. CUENTA — creer que estás en simulada y estar en real. El más caro
     de todos, y ocurre porque las dos ventanas se parecen.
  2. SÍMBOLO — comprar GOOG en vez de GOOGL, o un ticker parecido de
     otro mercado. El autocompletado de TWS ayuda y a la vez engaña.
  3. ACCIÓN — pulsar VENDER sobre algo que no posees abre un CORTO. En
     IBKR no hay botón separado para eso: es el mismo VENDER. Una venta
     en corto tiene pérdida teóricamente ilimitada.
  4. CANTIDAD — el cero de más. 1000 acciones en vez de 100. Es el error
     que más veces ha aparecido en las noticias.
  5. TIPO Y PRECIO — una orden a mercado creyendo que era límite, o un
     precio límite absurdo frente al NBBO por haber movido un decimal.

Litch los enuncia en voz alta y por escrito antes de cada envío. Si algo
no cuadra, no envía.

SOBRE EXCESS LIQUIDITY
──────────────────────
Es la cifra más importante de la ventana de cuenta y casi nadie la mira.
Net Liquidation dice cuánto tienes; Excess Liquidity dice cuánto margen
te queda antes de que el broker intervenga.

Cuando llega a cero no recibes una llamada ni un email: IBKR cierra
posiciones automáticamente, al precio de mercado del momento, y decide
ella cuáles. Suele ocurrir en el peor momento posible, porque justamente
lo que hace caer el Excess Liquidity es que el mercado vaya en contra.
"""

from __future__ import annotations

import time

# Umbrales del colchón de margen, en fracción del valor neto
UMBRAL_ROJO = 0.10        # menos del 10% → peligro de liquidación forzosa
UMBRAL_AMBAR = 0.25       # menos del 25% → estrechándose
UMBRAL_VERDE = 0.40       # por encima → cómodo


# ═══════════════════════════════════════════════════════════════════════════
#  B.4 — VERIFICACIÓN DE LOS CINCO DATOS
# ═══════════════════════════════════════════════════════════════════════════

def verificar_cinco_datos(app, simbolo: str, accion: str, cantidad,
                          tipo: str, precio=None,
                          corto_autorizado: bool = False) -> dict:
    """Los cinco datos, uno por uno, antes de transmitir nada.

    corto_autorizado: hay que pasarlo en True adrede para permitir abrir
    una posición corta. Por defecto se bloquea, porque un corto abierto
    sin querer tiene pérdida teóricamente ilimitada y es exactamente el
    tipo de error que arruina a alguien que empieza.

    Devuelve {"ok": bool, "informe": str, "avisos": [str], "bloqueos": [str]}
    """
    r = {"ok": True, "informe": "", "avisos": [], "bloqueos": []}
    lineas = ["VERIFICACIÓN DE LOS CINCO DATOS (AGENTE.md B.4)"]

    br = getattr(app, "broker_ibkr", None)

    # ── 1. CUENTA ───────────────────────────────────────────────────────────
    cuenta_txt = "no confirmada"
    es_paper = None
    try:
        if br is not None and getattr(br, "esta_conectado", False):
            es_paper = getattr(br, "_es_paper", None)
            cuentas = getattr(br, "_cuentas", []) or []
            cuenta_txt = ", ".join(cuentas) if cuentas else "sin número"
    except Exception:
        pass

    if es_paper is True:
        lineas.append(f"  1. CUENTA ....... {cuenta_txt} — SIMULADA ✓")
    elif es_paper is False:
        lineas.append(f"  1. CUENTA ....... {cuenta_txt} — ⛔ REAL")
        r["bloqueos"].append("La cuenta es REAL. No transmito.")
    else:
        lineas.append("  1. CUENTA ....... ⛔ NO CONFIRMADA")
        r["bloqueos"].append("No puedo confirmar la cuenta. La duda no es "
                             "permiso: no transmito.")

    # ── 2. SÍMBOLO ──────────────────────────────────────────────────────────
    sim = (simbolo or "").upper().strip()
    if not sim:
        lineas.append("  2. SÍMBOLO ...... ⛔ vacío")
        r["bloqueos"].append("Sin símbolo no hay orden.")
    else:
        lineas.append(f"  2. SÍMBOLO ...... {sim}")

        # Se avisa del ticker PELIGROSO, no del seguro.
        #
        # Mi primera versión avisaba «SPY se confunde con SPXL» en cada
        # orden de SPY. Un aviso que salta siempre se ignora, y un aviso
        # ignorado es peor que ninguno: enseña a no leerlos. Así que solo
        # se avisa cuando el símbolo escrito ES el arriesgado.
        APALANCADOS = {
            "TQQQ": "Nasdaq ×3 al alza", "SQQQ": "Nasdaq ×3 a la baja",
            "SPXL": "S&P ×3 al alza", "SPXS": "S&P ×3 a la baja",
            "UPRO": "S&P ×3 al alza", "SPXU": "S&P ×3 a la baja",
            "UDOW": "Dow ×3", "SDOW": "Dow ×3 inverso",
            "SOXL": "semiconductores ×3", "SOXS": "semiconductores ×3 inverso",
            "TNA": "small caps ×3", "TZA": "small caps ×3 inverso",
            "TMF": "bonos ×3", "TMV": "bonos ×3 inverso",
            "UVXY": "volatilidad ×1.5", "VXX": "futuros de volatilidad",
        }
        CLASES = {
            "GOOG": "GOOGL", "GOOGL": "GOOG",
            "BRK.A": "BRK.B", "BRK.B": "BRK.A",
        }

        if sim in APALANCADOS:
            r["avisos"].append(
                f"⚠ {sim} es un producto APALANCADO ({APALANCADOS[sim]}). "
                f"Multiplica el movimiento diario, y por cómo se recomponen "
                f"cada día, mantenerlo semanas suele perder valor incluso "
                f"si el índice acaba donde empezó. No es una versión "
                f"«potente» del índice: es otro producto. Con capital "
                f"pequeño puede vaciar la cuenta muy rápido.")
        elif sim in CLASES:
            r["avisos"].append(
                f"{sim} y {CLASES[sim]} son clases distintas de la misma "
                f"empresa, con precio y derechos diferentes. Confirme cuál "
                f"quiere.")

    # ── 3. ACCIÓN ───────────────────────────────────────────────────────────
    acc = (accion or "").upper().strip()
    acc = {"COMPRA": "BUY", "COMPRAR": "BUY",
           "VENTA": "SELL", "VENDER": "SELL"}.get(acc, acc)

    if acc not in ("BUY", "SELL"):
        lineas.append(f"  3. ACCIÓN ....... ⛔ «{accion}» no es BUY ni SELL")
        r["bloqueos"].append("La acción debe ser BUY o SELL.")
    else:
        lineas.append(f"  3. ACCIÓN ....... {acc}")
        # ¿Es una venta en corto sin querer?
        if acc == "SELL":
            tiene = _cantidad_en_cartera(br, sim)
            aviso_corto = (
                f"No tiene {sim} en cartera, así que este SELL abre una "
                f"posición CORTA. En IBKR no hay botón aparte para eso: es "
                f"el mismo VENDER, y por eso se abre sin querer con "
                f"facilidad. Una posición corta tiene pérdida teóricamente "
                f"ILIMITADA: una acción puede subir sin techo, y su pérdida "
                f"sube con ella. Si de verdad quiere ponerse corto, dígamelo "
                f"explícitamente.")
            if tiene <= 0:
                lineas.append("                    ⛔ VENTA EN CORTO")
                if corto_autorizado:
                    r["avisos"].append("Corto autorizado por usted. " +
                                       aviso_corto)
                else:
                    r["bloqueos"].append(aviso_corto)
            elif int(cantidad or 0) > tiene:
                falta = int(cantidad or 0) - tiene
                lineas.append(f"                    ⚠ tiene {tiene}, "
                              f"vende {cantidad}")
                msg = (f"Tiene {tiene} de {sim} y quiere vender {cantidad}: "
                       f"las {falta} de diferencia se abrirían en CORTO, con "
                       f"pérdida potencialmente ilimitada.")
                if corto_autorizado:
                    r["avisos"].append(msg)
                else:
                    r["bloqueos"].append(msg)

    # ── 4. CANTIDAD ─────────────────────────────────────────────────────────
    try:
        cant = int(cantidad)
    except Exception:
        cant = -1
    if cant <= 0:
        lineas.append(f"  4. CANTIDAD ..... ⛔ «{cantidad}» no es válida")
        r["bloqueos"].append("La cantidad debe ser un entero mayor que cero.")
    else:
        lineas.append(f"  4. CANTIDAD ..... {cant} acciones")

        # El cero de más: solo tiene sentido si la orden CONSUME capital.
        #
        # Vender acciones que ya se tienen no gasta dinero: lo libera. Mi
        # primera versión bloqueaba «vender 10 SPY» porque 10×679 supera
        # una cuenta de 3.000 — un sinsentido. Y una protección que
        # estorba en lo normal es una protección que se acaba desactivando,
        # así que hay que acertar en cuándo salta.
        tiene_ya = _cantidad_en_cartera(br, sim) if sim else 0
        cierra_posicion = (acc == "SELL" and tiene_ya > 0)
        cant_expuesta = (max(0, cant - tiene_ya) if acc == "SELL" else cant)

        valor = cant_expuesta * float(precio or 0)
        neto = _valor_neto(br)

        if cierra_posicion and cant <= tiene_ya:
            lineas.append(f"                    cierra posición de "
                          f"{tiene_ya} — no consume capital")
        elif neto > 0 and valor > 0:
            pct = 100.0 * valor / neto
            etiq = ("expone" if acc == "BUY" else "abre en corto")
            lineas.append(f"                    {etiq} ≈ {valor:,.0f} USD "
                          f"({pct:.0f}% de la cuenta)")
            if pct > 100:
                r["bloqueos"].append(
                    f"Esa orden {etiq} {valor:,.0f} USD y su cuenta son "
                    f"{neto:,.0f}. No cabe. Revise si sobra un cero.")
            elif pct > 50:
                r["avisos"].append(
                    f"Esa orden pone el {pct:.0f}% de su cuenta en un solo "
                    f"activo. Concentrar así convierte cualquier sorpresa "
                    f"en un problema grave.")

    # ── 5. TIPO Y PRECIO ────────────────────────────────────────────────────
    tp = (tipo or "").upper().strip()
    if tp in ("MARKET", "MKT"):
        lineas.append("  5. TIPO ......... MKT (a mercado) ⚠")
        r["avisos"].append(
            "Orden a mercado: acepta el precio que haya. Sin garantía de "
            "precio. AGENTE.md D.3 recomienda LMT por defecto.")
    elif tp in ("LIMIT", "LMT"):
        if not precio or float(precio) <= 0:
            lineas.append("  5. TIPO ......... ⛔ LMT sin precio")
            r["bloqueos"].append("Una orden límite sin precio no es una "
                                 "orden límite.")
        else:
            lineas.append(f"  5. TIPO ......... LMT a {float(precio):,.2f}")
            # ¿El precio es razonable frente al mercado?
            ref = _precio_mercado(br, sim)
            if ref > 0:
                desv = 100.0 * abs(float(precio) - ref) / ref
                lineas.append(f"                    mercado {ref:,.2f} "
                              f"(desviación {desv:.1f}%)")
                if desv > 20:
                    r["bloqueos"].append(
                        f"Su precio límite está un {desv:.0f}% fuera del "
                        f"mercado ({ref:,.2f}). Eso casi siempre es un "
                        f"decimal mal puesto.")
                elif desv > 5:
                    r["avisos"].append(
                        f"El límite está un {desv:.0f}% del precio actual. "
                        f"Puede que no se ejecute nunca.")
    else:
        lineas.append(f"  5. TIPO ......... {tp or '(sin especificar)'}")
        if not tp:
            r["bloqueos"].append("Falta el tipo de orden.")

    # ── Colchón de margen (D.5) ─────────────────────────────────────────────
    liq = estado_liquidez(app)
    if liq.get("nivel") == "ROJO":
        r["bloqueos"].append(liq["mensaje"])
        lineas.append(f"  + MARGEN ........ ⛔ {liq['resumen']}")
    elif liq.get("nivel") == "AMBAR":
        r["avisos"].append(liq["mensaje"])
        lineas.append(f"  + MARGEN ........ ⚠ {liq['resumen']}")
    elif liq.get("nivel") == "VERDE":
        lineas.append(f"  + MARGEN ........ {liq['resumen']} ✓")

    # ── Veredicto ───────────────────────────────────────────────────────────
    r["ok"] = not r["bloqueos"]
    lineas.append("")
    if r["bloqueos"]:
        lineas.append("NO TRANSMITO. Motivos:")
        for b in r["bloqueos"]:
            lineas.append(f"  ⛔ {b}")
    else:
        lineas.append("Los cinco datos cuadran.")
    if r["avisos"]:
        lineas.append("")
        lineas.append("Avisos que debe leer antes de decidir:")
        for a in r["avisos"]:
            lineas.append(f"  ⚠ {a}")
    if r["ok"]:
        lineas.append("")
        lineas.append("Confirme usted para transmitir. Yo no lo hago solo.")

    r["informe"] = "\n".join(lineas)
    return r


# ═══════════════════════════════════════════════════════════════════════════
#  D.5 — VIGILANCIA DE EXCESS LIQUIDITY
# ═══════════════════════════════════════════════════════════════════════════

def estado_liquidez(app) -> dict:
    """El colchón sobre el margen exigido.

    Es la cifra más importante de la cuenta y casi nadie la mira. Cuando
    llega a cero, IBKR no avisa: cierra posiciones por su cuenta, al precio
    del momento, y elige ella cuáles.
    """
    r = {"nivel": None, "excess": 0.0, "neto": 0.0, "fraccion": 0.0,
         "resumen": "sin datos", "mensaje": ""}

    br = getattr(app, "broker_ibkr", None)
    if br is None or not getattr(br, "esta_conectado", False):
        r["resumen"] = "sin conexión a IBKR"
        return r

    try:
        bal = br.balance_cuenta() or {}
    except Exception:
        r["resumen"] = "no pude leer la cuenta"
        return r

    def _num(*claves):
        for c in claves:
            v = bal.get(c)
            if v not in (None, ""):
                try:
                    return float(v)
                except Exception:
                    continue
        return 0.0

    excess = _num("excess_liquidity", "ExcessLiquidity", "liquidez_excedente",
                  "excedente")
    neto = _num("valor_neto", "NetLiquidation", "net_liquidation",
                "liquidez", "efectivo")

    r["excess"] = excess
    r["neto"] = neto

    if neto <= 0:
        r["resumen"] = "valor neto no disponible"
        return r
    if excess <= 0 and "excess_liquidity" not in bal \
            and "ExcessLiquidity" not in bal:
        # El conector no expone el dato; no se inventa un nivel.
        r["resumen"] = (f"neto {neto:,.0f} USD (el conector no me da el "
                        f"Excess Liquidity)")
        r["mensaje"] = ("No puedo leer el Excess Liquidity desde la API. "
                        "Mírelo usted en la ventana de Cuenta de TWS: es la "
                        "cifra que dice cuánto margen le queda antes de que "
                        "IBKR cierre posiciones por su cuenta.")
        return r

    frac = excess / neto
    r["fraccion"] = frac
    r["resumen"] = (f"colchón {excess:,.0f} de {neto:,.0f} USD "
                    f"({frac*100:.0f}%)")

    if frac < UMBRAL_ROJO:
        r["nivel"] = "ROJO"
        r["mensaje"] = (
            f"⛔ PELIGRO DE LIQUIDACIÓN FORZOSA. Su colchón de margen es "
            f"{excess:,.0f} USD, un {frac*100:.0f}% del valor de la cuenta. "
            f"Cuando esto llega a cero, IBKR no le llama ni le escribe: "
            f"cierra posiciones automáticamente, al precio que haya en ese "
            f"momento, y elige ella cuáles. No abro nada nuevo. Lo sensato "
            f"ahora es reducir exposición, no añadirla.")
    elif frac < UMBRAL_AMBAR:
        r["nivel"] = "AMBAR"
        r["mensaje"] = (
            f"⚠ Su colchón de margen se está estrechando: {excess:,.0f} USD "
            f"({frac*100:.0f}% de la cuenta). Todavía hay sitio, pero si el "
            f"mercado va en contra puede acercarse rápido al punto en que "
            f"IBKR liquida por su cuenta.")
    else:
        r["nivel"] = "VERDE"
        r["mensaje"] = (f"Colchón de margen cómodo: {excess:,.0f} USD "
                        f"({frac*100:.0f}%).")
    return r


def informe_liquidez(app) -> str:
    """Para «Litch, ¿cómo está mi margen?»"""
    liq = estado_liquidez(app)
    if liq.get("nivel") is None:
        return (liq.get("mensaje") or
                f"No tengo el dato ahora mismo, señor: {liq['resumen']}.")
    lineas = [f"COLCHÓN DE MARGEN (Excess Liquidity) — {liq['nivel']}",
              f"  {liq['resumen']}",
              "",
              liq["mensaje"],
              "",
              "Esta es la cifra que decide si el broker puede intervenir su "
              "cuenta. Net Liquidation dice cuánto tiene; Excess Liquidity "
              "dice cuánto margen le queda antes de que IBKR cierre "
              "posiciones sin preguntarle."]
    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  Ayudantes
# ═══════════════════════════════════════════════════════════════════════════

def _cantidad_en_cartera(br, simbolo: str) -> int:
    try:
        for p in (br.posiciones() or []):
            if str(p.get("simbolo", "")).upper() == simbolo:
                return int(float(p.get("cantidad") or 0))
    except Exception:
        pass
    return 0


def _valor_neto(br) -> float:
    try:
        bal = br.balance_cuenta() or {}
        for c in ("valor_neto", "NetLiquidation", "liquidez", "efectivo"):
            if bal.get(c):
                return float(bal[c])
    except Exception:
        pass
    return 0.0


def _precio_mercado(br, simbolo: str) -> float:
    try:
        cot = br.cotizacion(simbolo) or {}
        p = float(cot.get("precio") or 0)
        if p > 0:
            return p
        bid = float(cot.get("bid") or 0)
        ask = float(cot.get("ask") or 0)
        return (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
    except Exception:
        return 0.0

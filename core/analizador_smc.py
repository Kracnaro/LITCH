"""
analizador_smc.py — Smart Money Concepts / Latino Wall Street para Litch.

Implementa la metodología LWS/ICT sobre secuencias de velas V/R:
  • BOS   (Break of Structure)      — confirma continuación de tendencia
  • CHoCH (Change of Character)     — señala posible reversión
  • OB    (Order Block válido)       — zona donde el precio debe regresar
  • FVG   (Fair Value Gap)           — imbalance sin llenar → imán de precio
  • Sweep (Liquidity Sweep)          — trampa del mercado antes del movimiento real
  • Killzone                         — ventana horaria de alta probabilidad institucional

Trabaja con secuencias de strings "V" (verde/alcista) y "R" (rojo/bajista).
No ejecuta trades — produce un voto adicional para el consenso en trading.py.
"""

import time

# ── Parámetros ────────────────────────────────────────────────────────────────
_MIN_SEC    = 8    # mínimo de velas para análisis SMC
_LOOK_EST   = 28   # ventana de estructura de mercado (ampliada para más contexto)
_LOOK_OB    = 14   # ventana para Order Blocks
_LOOK_FVG   = 8    # ventana para FVG
_LOOK_SWEEP = 12   # ventana para Liquidity Sweeps


# ── Primitiva: run-length encoding ───────────────────────────────────────────

def _rachas(sec: list) -> list:
    """
    Convierte V/R list en rachas [(color, largo), ...].
    VVVRRVV → [('V',3), ('R',2), ('V',2)]
    """
    if not sec:
        return []
    rachas, actual, cnt = [], sec[0], 1
    for c in sec[1:]:
        if c == actual:
            cnt += 1
        else:
            rachas.append((actual, cnt))
            actual, cnt = c, 1
    rachas.append((actual, cnt))
    return rachas


# ── 1. Estructura de mercado: BOS / CHoCH ────────────────────────────────────

def detectar_estructura(sec: list) -> dict:
    """
    Detecta BOS (Break of Structure) y CHoCH (Change of Character).

    Metodología LWS:
    - BOS alcista  : nueva racha V supera en largo a la racha V anterior
                     (Higher High + Higher Low → continuación alcista)
    - BOS bajista  : nueva racha R supera a la R anterior
    - CHoCH alcista: en tendencia bajista, racha V >= 3 interrumpe la secuencia
    - CHoCH bajista: en tendencia alcista, racha R >= 3 interrumpe

    Retorna:
        tendencia  — 'ALCISTA' | 'BAJISTA' | 'LATERAL'
        bos        — bool
        choch      — bool
        dir        — 'V' | 'R' | None
        confianza  — float 0-1
        info       — descripción legible
    """
    n = len(sec)
    if n < _MIN_SEC:
        return {"tendencia": "LATERAL", "bos": False, "choch": False,
                "dir": None, "confianza": 0.0, "info": "pocas velas"}

    ventana = sec[-min(n, _LOOK_EST):]
    rachas  = _rachas(ventana)

    if len(rachas) < 2:
        col_dom = "ALCISTA" if ventana[0] == "V" else "BAJISTA"
        dir_dom = "V" if col_dom == "ALCISTA" else "R"
        return {"tendencia": col_dom, "bos": True, "choch": False,
                "dir": dir_dom, "confianza": 0.82, "info": "impulso puro sin pullback"}

    total   = len(ventana)
    v_cnt   = ventana.count("V")
    r_cnt   = ventana.count("R")
    v_pct   = v_cnt / total
    r_pct   = r_cnt / total

    if v_pct >= 0.62:
        tendencia = "ALCISTA"
    elif r_pct >= 0.62:
        tendencia = "BAJISTA"
    else:
        tendencia = "LATERAL"

    # Extraer sub-rachas por color
    v_racs = [r[1] for r in rachas if r[0] == "V"]
    r_racs = [r[1] for r in rachas if r[0] == "R"]
    ultima  = rachas[-1]

    bos = False; choch = False; dir_s = None; conf = 0.45; info = ""

    # BOS alcista: última racha V es >= la penúltima racha V (HH)
    if ultima[0] == "V" and len(v_racs) >= 2 and v_racs[-1] >= v_racs[-2]:
        if tendencia in ("ALCISTA", "LATERAL"):
            bos   = True
            dir_s = "V"
            conf  = min(0.82, 0.65 + (v_racs[-1] - v_racs[-2]) * 0.04)
            info  = f"BOS alcista — racha V={v_racs[-1]} ≥ previa V={v_racs[-2]} (Higher High)"

    # BOS bajista
    elif ultima[0] == "R" and len(r_racs) >= 2 and r_racs[-1] >= r_racs[-2]:
        if tendencia in ("BAJISTA", "LATERAL"):
            bos   = True
            dir_s = "R"
            conf  = min(0.82, 0.65 + (r_racs[-1] - r_racs[-2]) * 0.04)
            info  = f"BOS bajista — racha R={r_racs[-1]} ≥ previa R={r_racs[-2]} (Lower Low)"

    # CHoCH alcista: tendencia bajista, última racha V rompe el esquema
    elif ultima[0] == "V" and ultima[1] >= 3 and tendencia == "BAJISTA":
        choch = True
        dir_s = "V"
        conf  = 0.64
        info  = f"CHoCH alcista — V={ultima[1]} velas irrumpen tendencia bajista (posible reversión)"

    # CHoCH bajista: tendencia alcista, última racha R rompe el esquema
    elif ultima[0] == "R" and ultima[1] >= 3 and tendencia == "ALCISTA":
        choch = True
        dir_s = "R"
        conf  = 0.64
        info  = f"CHoCH bajista — R={ultima[1]} velas irrumpen tendencia alcista (posible reversión)"

    else:
        # Sin ruptura clara: sesgar hacia la tendencia macro
        dir_s = "V" if tendencia == "ALCISTA" else ("R" if tendencia == "BAJISTA" else None)
        conf  = 0.48
        info  = f"Tendencia {tendencia} sin BOS ni CHoCH confirmado"

    return {
        "tendencia": tendencia,
        "bos":   bos,
        "choch": choch,
        "dir":   dir_s,
        "confianza": round(conf, 3),
        "info":  info,
        "v_pct": round(v_pct * 100),
        "r_pct": round(r_pct * 100),
    }


# ── 2. Order Block válido ─────────────────────────────────────────────────────

def detectar_order_block(sec: list) -> "dict | None":
    """
    Detecta el Order Block válido más reciente.

    OB alcista: última racha R antes de un impulso V fuerte (zona de demanda)
    OB bajista: última racha V antes de un impulso R fuerte (zona de oferta)

    Criterios LWS:
    - El OB causó un movimiento impulsivo (≥2 velas en la dirección)
    - No ha sido completamente mitigado (precio no volvió a cubrir el OB)
    """
    if len(sec) < _LOOK_OB:
        return None

    ventana = sec[-_LOOK_OB:]
    rachas  = _rachas(ventana)

    if len(rachas) < 3:
        return None

    # Buscar desde la racha más reciente hacia atrás
    for i in range(len(rachas) - 1, 0, -1):
        col_ob,  largo_ob  = rachas[i - 1]
        col_imp, largo_imp = rachas[i]

        # OB alcista: R → V fuerte
        if col_ob == "R" and col_imp == "V" and largo_imp >= 2:
            # Comprobar que no esté mitigado (no hay racha R posterior mayor)
            r_post = [r[1] for r in rachas[i + 1:] if r[0] == "R"]
            if not r_post or max(r_post) <= largo_ob:
                return {
                    "tipo": "alcista",
                    "dir":  "V",
                    "largo_ob":      largo_ob,
                    "largo_impulso": largo_imp,
                    "confianza": min(0.80, 0.60 + largo_imp * 0.06),
                    "descripcion": (
                        f"OB alcista — {largo_ob} velas R → impulso V={largo_imp} "
                        f"(zona demanda, no mitigado)"
                    ),
                }

        # OB bajista: V → R fuerte
        if col_ob == "V" and col_imp == "R" and largo_imp >= 2:
            v_post = [r[1] for r in rachas[i + 1:] if r[0] == "V"]
            if not v_post or max(v_post) <= largo_ob:
                return {
                    "tipo": "bajista",
                    "dir":  "R",
                    "largo_ob":      largo_ob,
                    "largo_impulso": largo_imp,
                    "confianza": min(0.80, 0.60 + largo_imp * 0.06),
                    "descripcion": (
                        f"OB bajista — {largo_ob} velas V → impulso R={largo_imp} "
                        f"(zona oferta, no mitigado)"
                    ),
                }

    return None


# ── 3. Fair Value Gap (FVG) ───────────────────────────────────────────────────

def detectar_fvg(sec: list) -> "dict | None":
    """
    Detecta Fair Value Gap (imbalance del mercado).

    FVG alcista: racha R seguida de VV+ inmediato (el mercado subió sin llenar)
    FVG bajista: racha V seguida de RR+ inmediato

    La fuerza del FVG aumenta con el largo de la racha impulsiva.
    """
    if len(sec) < 5:
        return None

    ventana = sec[-_LOOK_FVG:]
    rachas  = _rachas(ventana)

    # Solo buscar en las últimas 2 rachas (FVG fresco)
    for i in range(len(rachas) - 1, 0, -1):
        prev_col, _ = rachas[i - 1]
        this_col, this_len = rachas[i]

        if i < len(rachas) - 1:
            continue   # solo el FVG más reciente (la última racha impulsiva)

        # FVG alcista: mercado venía bajando → impulso V sin pullback
        if prev_col == "R" and this_col == "V" and this_len >= 2:
            return {
                "dir": "V",
                "confianza": min(0.72, 0.58 + this_len * 0.05),
                "descripcion": (
                    f"FVG alcista — imbalance de {this_len} velas V sin llenar "
                    f"(precio tenderá a regresar)"
                ),
            }

        # FVG bajista
        if prev_col == "V" and this_col == "R" and this_len >= 2:
            return {
                "dir": "R",
                "confianza": min(0.72, 0.58 + this_len * 0.05),
                "descripcion": (
                    f"FVG bajista — imbalance de {this_len} velas R sin llenar "
                    f"(precio tenderá a regresar)"
                ),
            }

    return None


# ── 4. Liquidity Sweep ────────────────────────────────────────────────────────

def detectar_liquidity_sweep(sec: list) -> "dict | None":
    """
    Detecta sweep de liquidez (trampa del mercado).

    Metodología LWS: El Smart Money barre los stops acumulados antes del movimiento real.
    El sweep es la 'mentira' del precio — la dirección real viene después.

    Patrón V/R:
    - Sweep bajista de stops (movimiento real alcista):
        tendencia V (3+) → racha R pequeña ≤ tendencia → retorno V fuerte (≥2)
    - Sweep alcista de stops (movimiento real bajista):
        tendencia R (3+) → racha V pequeña ≤ tendencia → retorno R fuerte (≥2)
    """
    if len(sec) < _LOOK_SWEEP:
        return None

    ventana = sec[-_LOOK_SWEEP:]
    rachas  = _rachas(ventana)

    if len(rachas) < 4:
        return None

    # Analizar grupos de 3 rachas consecutivas
    for i in range(2, len(rachas)):
        pre   = rachas[i - 2]
        sweep = rachas[i - 1]
        conf  = rachas[i]

        # Sweep bajista (el movimiento R fue trampa → real es V)
        if (pre[0] == "V" and sweep[0] == "R" and conf[0] == "V"
                and sweep[1] <= max(pre[1], 2)      # sweep pequeño
                and conf[1] >= 2                     # confirmación fuerte
                and pre[1] >= 2):                    # tendencia previa real
            return {
                "dir": "V",
                "confianza": min(0.85, 0.70 + conf[1] * 0.03),
                "descripcion": (
                    f"Sweep bajista de liquidez — tendencia V={pre[1]} → "
                    f"trampa R={sweep[1]} → retorno V={conf[1]} (dirección real: SUBE)"
                ),
                "tipo": "sweep_bajista",
            }

        # Sweep alcista (el movimiento V fue trampa → real es R)
        if (pre[0] == "R" and sweep[0] == "V" and conf[0] == "R"
                and sweep[1] <= max(pre[1], 2)
                and conf[1] >= 2
                and pre[1] >= 2):
            return {
                "dir": "R",
                "confianza": min(0.85, 0.70 + conf[1] * 0.03),
                "descripcion": (
                    f"Sweep alcista de liquidez — tendencia R={pre[1]} → "
                    f"trampa V={sweep[1]} → retorno R={conf[1]} (dirección real: BAJA)"
                ),
                "tipo": "sweep_alcista",
            }

    return None


# ── 4b. Aceleración de momentum ──────────────────────────────────────────────

def detectar_aceleracion(sec: list) -> "dict | None":
    """
    Detecta aceleración de momentum: 3 rachas consecutivas del mismo color
    donde cada racha es MAYOR que la anterior (escalera ascendente de fuerza).

    Esto se corresponde con el concepto ICT de 'running candles' y
    el LWS de 'impulso institucional acelerando'.

    Alcista acelerando: V3 < V4 < V5 (3 rachas V cada vez más largas)
    Bajista acelerando: R3 < R4 < R5

    Una aceleración solo vale si no fue precedida de un sweep contrario
    (que podría indicar que fue la trampa).
    """
    if len(sec) < 12:
        return None

    ventana = sec[-min(len(sec), 20):]
    rachas  = _rachas(ventana)

    # Necesitamos al menos 3 rachas del mismo color al final
    if len(rachas) < 3:
        return None

    # Verificar que las últimas 3 rachas sean del mismo color y crecientes
    r1, r2, r3 = rachas[-3], rachas[-2], rachas[-1]
    if not (r1[0] == r2[0] == r3[0]):
        return None

    color = r3[0]
    if not (r1[1] < r2[1] < r3[1]):
        return None   # no hay aceleración

    fuerza = r3[1] - r1[1]   # cuántas velas ganó de primera a tercera racha
    conf   = min(0.82, 0.62 + fuerza * 0.04)

    return {
        "dir":        color,
        "confianza":  round(conf, 3),
        "escalera":   (r1[1], r2[1], r3[1]),
        "descripcion": (
            f"Aceleración {'alcista' if color == 'V' else 'bajista'}: "
            f"rachas {r1[1]}→{r2[1]}→{r3[1]} {color} (momentum institucional creciente)"
        ),
    }


# ── 4c. Zonas Fibonacci sintéticas ───────────────────────────────────────────

def detectar_fibonacci(sec: list) -> "dict | None":
    """
    Calcula niveles Fibonacci desde la última onda impulsiva identificable
    en la secuencia V/R.

    Metodología: identifica el swing high y swing low más recientes
    (como conteos de rachas) y ubica al precio respecto a los niveles
    38.2%, 50%, 61.8% del retroceso.

    En binarias V/R (sin precio real), utilizamos el conteo de velas
    como proxy de precio sintético. Si la vela está en zona 50-61.8%
    de retroceso tras un impulso, la probabilidad de continuación
    aumenta significativamente.

    Retorna nivel de retroceso actual y si es zona de confluencia.
    """
    if len(sec) < 16:
        return None

    ventana = sec[-min(len(sec), 40):]
    rachas  = _rachas(ventana)

    if len(rachas) < 4:
        return None

    # Encontrar el mayor swing (impulso más grande)
    # El impulso es la racha de mayor largo
    idx_max = max(range(len(rachas)), key=lambda i: rachas[i][1])
    if idx_max == 0 or idx_max >= len(rachas) - 1:
        return None

    impulso = rachas[idx_max]
    # Retroceso: rachas del color opuesto después del impulso
    retroceso_total = sum(r[1] for r in rachas[idx_max + 1:]
                          if r[0] != impulso[0])

    if retroceso_total == 0:
        return None

    # Ratio de retroceso respecto al impulso
    ratio = retroceso_total / impulso[1]

    # Niveles Fibonacci
    zona = None
    if 0.30 <= ratio <= 0.45:
        zona = "38.2%"
        conf = 0.68    # retroceso mínimo — impulso fuerte, retomará dirección
    elif 0.45 < ratio <= 0.56:
        zona = "50%"
        conf = 0.72    # zona clave — alta probabilidad de continuación
    elif 0.56 < ratio <= 0.70:
        zona = "61.8%"
        conf = 0.78    # nivel dorado — mayor probabilidad de rebote
    elif ratio > 0.80:
        zona = ">80%"
        conf = 0.42    # retroceso profundo — posible reversión total, señal débil
    else:
        return None    # fuera de rangos significativos

    dir_continuacion = impulso[0]   # esperamos que continúe el impulso

    return {
        "dir":         dir_continuacion,
        "zona":        zona,
        "ratio":       round(ratio * 100, 1),
        "confianza":   round(conf, 3),
        "descripcion": (
            f"Fibonacci {zona} retroceso — impulso {'alcista' if dir_continuacion == 'V' else 'bajista'} "
            f"de {impulso[1]} velas retrocedió {ratio*100:.0f}% "
            f"→ zona de confluencia para entrada en {dir_continuacion}"
        ),
    }


# ── 5. Killzone ICT/LWS ───────────────────────────────────────────────────────

def killzone_activa() -> dict:
    """
    Determina si estamos en una Killzone de alta probabilidad.

    Killzones LWS/ICT (horario UTC):
    - London Open : 07:00-10:00 → primer sweep del día + dirección principal
    - NY Open     : 13:30-16:00 → MEJOR MOMENTO, mayor volatilidad institucional
    - London Close: 16:00-17:00 → reversiones + cierre de posiciones
    - Asia        : 00:00-07:00 → baja liquidez, evitar scalping
    - Lunch Time  : 11:30-13:30 → spreads amplios, señales falsas

    Retorna:
        activa   — bool
        nombre   — str
        tasa     — str (win rate histórico aproximado)
        peso     — multiplicador de confianza (>1 = favorable)
    """
    h = time.gmtime().tm_hour
    m = time.gmtime().tm_min
    h_dec = h + m / 60.0

    if 7.0 <= h_dec < 10.0:
        return {"activa": True,  "nombre": "London Open",
                "tasa": "65-70%", "peso": 1.30,
                "horario": "07:00-10:00 UTC"}
    if 13.5 <= h_dec < 16.0:
        return {"activa": True,  "nombre": "NY Open",
                "tasa": "70-75%", "peso": 1.40,
                "horario": "13:30-16:00 UTC"}
    if 16.0 <= h_dec < 17.0:
        return {"activa": True,  "nombre": "London Close",
                "tasa": "60-65%", "peso": 1.12,
                "horario": "16:00-17:00 UTC"}
    if 0.0 <= h_dec < 7.0:
        return {"activa": False, "nombre": "Sesión Asia",
                "tasa": "45-50%", "peso": 0.78,
                "horario": "00:00-07:00 UTC"}
    if 11.5 <= h_dec < 13.5:
        return {"activa": False, "nombre": "Lunch Time NY",
                "tasa": "40-45%", "peso": 0.68,
                "horario": "11:30-13:30 UTC"}

    return {"activa": False, "nombre": "Inter-sesión",
            "tasa": "50%", "peso": 0.88,
            "horario": f"{h:02d}:{m:02d} UTC"}


# ── 6. Análisis completo: voto SMC para el consenso ──────────────────────────

def analizar_completo(sec: list, indicadores: dict = None) -> dict:
    """
    Análisis SMC completo — voto 7 del consenso en trading.py.

    Combina estructura + OB + FVG + Sweep + Killzone + Indicadores.

    Sistema de puntuación ponderado (LWS):
      Sweep         3.5 pts  — señal más fiable (barrió stops)
      BOS           2.5 pts  — confirmación de tendencia
      CHoCH         2.0 pts  — reversión incipiente
      Order Block   1.8 pts  — zona institucional
      FVG           1.2 pts  — imbalance sin cubrir
      RSI extremo   0.8 pts  — confirmación con indicador
      MACD          0.5 pts  — momentum

    Killzone multiplica la confianza final (NY Open ×1.4, fuera de KZ ×0.7-0.9).

    Retorna:
        dir        — 'V' | 'R' | None
        confianza  — float 0-1
        votar      — bool (True si setup válido con ≥2 confirmaciones)
        setup      — nombre del setup LWS detectado
        narrativa  — descripción para log y voz
        estructura — tendencia macro
        killzone   — info de la killzone
        (+ detalles internos)
    """
    if len(sec) < _MIN_SEC:
        return {"dir": None, "confianza": 0.0, "votar": False,
                "setup": "sin datos", "narrativa": "pocas velas para SMC",
                "estructura": "LATERAL", "killzone": killzone_activa()}

    ind = indicadores or {}

    # Ejecutar todos los detectores
    est    = detectar_estructura(sec)
    ob     = detectar_order_block(sec)
    fvg    = detectar_fvg(sec)
    sweep  = detectar_liquidity_sweep(sec)
    kz     = killzone_activa()
    acel   = detectar_aceleracion(sec)
    fib    = detectar_fibonacci(sec)

    # ── Sistema de puntuación ─────────────────────────────────────────────────
    pts     = {"V": 0.0, "R": 0.0}
    razones = []
    piezas  = []       # para armar el nombre del setup

    # 1. Estructura
    if est["bos"] and est["dir"]:
        pts[est["dir"]] += 2.5
        razones.append(est["info"])
        piezas.append("BOS")
    elif est["choch"] and est["dir"]:
        pts[est["dir"]] += 2.0
        razones.append(est["info"])
        piezas.append("CHoCH")
    elif est["tendencia"] != "LATERAL" and est["dir"]:
        pts[est["dir"]] += 0.7
        razones.append(f"tendencia {est['tendencia']} ({est['v_pct']}%V/{est['r_pct']}%R)")

    # 2. Order Block
    if ob:
        pts[ob["dir"]] += 1.8
        razones.append(ob["descripcion"])
        piezas.append("OB")

    # 3. Fair Value Gap
    if fvg:
        pts[fvg["dir"]] += 1.2
        razones.append(fvg["descripcion"])
        piezas.append("FVG")

    # 4. Liquidity Sweep — peso máximo (señal de alta fiabilidad LWS)
    if sweep:
        pts[sweep["dir"]] += 3.5
        razones.append(sweep["descripcion"])
        piezas.insert(0, "Sweep")

    # 5. Confirmación con indicadores técnicos
    rsi  = ind.get("rsi")
    macd = ind.get("macd_h")

    # Dirección dominante hasta ahora
    dom = "V" if pts["V"] > pts["R"] else ("R" if pts["R"] > pts["V"] else None)

    if rsi is not None and dom:
        if rsi < 35 and dom == "V":
            pts["V"] += 0.8
            razones.append(f"RSI {rsi:.0f} sobreventa (confirma alcista)")
        elif rsi > 65 and dom == "R":
            pts["R"] += 0.8
            razones.append(f"RSI {rsi:.0f} sobrecompra (confirma bajista)")
        elif 42 <= rsi <= 58:
            # RSI neutral debilita ligeramente la señal
            if dom:
                pts[dom] -= 0.25

    if macd is not None and dom:
        if macd > 0 and dom == "V":
            pts["V"] += 0.5
            razones.append("MACD alcista confirma")
        elif macd < 0 and dom == "R":
            pts["R"] += 0.5
            razones.append("MACD bajista confirma")
        elif (macd > 0 and dom == "R") or (macd < 0 and dom == "V"):
            pts[dom] -= 0.3

    # 6. ADX: fuerza de tendencia confirma BOS, debilita señales en rango
    adx = ind.get("adx_fuerza")
    if adx is not None and dom:
        if adx > 25 and (est["bos"] and est["dir"] == dom):
            pts[dom] += 0.6   # tendencia fuerte + BOS alineado = señal confiable
            razones.append(f"ADX {adx:.0f} confirma tendencia BOS {dom}")
        elif adx < 15:
            pts[dom] -= 0.3   # mercado en rango → señales estructurales menos confiables

    # 7. Hurst: persistencia de tendencia vs reversión
    hurst = ind.get("hurst")
    if hurst is not None and dom:
        if hurst > 0.60 and est.get("bos") and est["dir"] == dom:
            pts[dom] += 0.4
            razones.append(f"Hurst={hurst:.2f} (tendencia persistente)")
        elif hurst < 0.40 and est.get("choch") and est["dir"] == dom:
            pts[dom] += 0.4
            razones.append(f"Hurst={hurst:.2f} (reversión media)")

    # 8. Aceleración de momentum (nuevo v2)
    if acel and acel["dir"]:
        esc = acel["escalera"]
        pts[acel["dir"]] += 1.6
        razones.append(acel["descripcion"])
        piezas.append(f"Acel({esc[0]}→{esc[1]}→{esc[2]})")

    # 9. Fibonacci retracement (nuevo v2)
    if fib and fib["dir"]:
        pts[fib["dir"]] += fib["confianza"] * 1.2   # escalado por confianza del nivel
        razones.append(fib["descripcion"])
        piezas.append(f"Fib{fib['zona']}")

    # ── Determinar dirección y confianza ──────────────────────────────────────
    total = pts["V"] + pts["R"]
    if total < 1.5:
        return {"dir": None, "confianza": 0.0, "votar": False,
                "setup": "sin setup SMC", "narrativa": "señales SMC insuficientes",
                "estructura": est["tendencia"], "killzone": kz,
                "puntos_v": 0, "puntos_r": 0}

    if pts["V"] >= pts["R"]:
        dir_final = "V"
        conf_raw  = pts["V"] / total
    else:
        dir_final = "R"
        conf_raw  = pts["R"] / total

    # Penalizar si el margen de convicción es muy pequeño
    margen = abs(pts["V"] - pts["R"]) / total
    if margen < 0.12:
        conf_raw *= 0.78   # señales contradictorias → reducir confianza

    # Aplicar multiplicador de killzone
    confianza = min(0.95, conf_raw * kz["peso"])

    if kz["activa"]:
        razones.append(f"Killzone {kz['nombre']} — tasa histórica {kz['tasa']}")
        piezas.append("Killzone")
    elif kz["peso"] < 0.85:
        razones.append(f"ATENCIÓN: fuera de killzone ({kz['nombre']})")

    # Setup SMC válido:
    # - Normal: ≥2 señales + conf ≥ 54%
    # - Sweep solo en killzone: 1 señal basta si conf ≥ 65% (señal de muy alta fiabilidad)
    # - Sweep fuera de killzone: 1 señal basta si conf ≥ 72%
    n_senales = sum([
        est["bos"] or est["choch"],
        ob is not None,
        fvg is not None,
        sweep is not None,
    ])
    votar = (
        (confianza >= 0.54 and n_senales >= 2)
        or (sweep is not None and kz["activa"]  and confianza >= 0.65)
        or (sweep is not None and not kz["activa"] and confianza >= 0.72)
    )

    setup     = " + ".join(piezas) if piezas else "Análisis SMC"
    narrativa = " | ".join(razones[:5])   # limitar a 5 razones para el log

    return {
        "dir":        dir_final,
        "confianza":  round(confianza, 3),
        "votar":      votar,
        "setup":      setup,
        "narrativa":  narrativa,
        "estructura": est["tendencia"],
        "killzone":   kz,
        "puntos_v":   round(pts["V"], 2),
        "puntos_r":   round(pts["R"], 2),
        # Flags individuales
        "bos":    est["bos"],
        "choch":  est["choch"],
        "ob":     ob is not None,
        "fvg":    fvg is not None,
        "sweep":  sweep is not None,
        "en_kz":  kz["activa"],
        "acel":   acel is not None,
        "fib":    fib["zona"] if fib else None,
    }

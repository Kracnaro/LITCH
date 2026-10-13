"""
aprendizaje_bayes.py — La matemática del aprendizaje de Litch.

QUÉ ESTABA MAL Y POR QUÉ IMPORTA
────────────────────────────────
El aprendizaje contaba aciertos a palotes: cinco reacciones seguidas y el
elemento se daba por «conocido». Ese método tiene cuatro fallos serios:

  1. **No mide la incertidumbre.** 5 de 5 y 50 de 50 se trataban igual,
     cuando el segundo es muchísimo más fiable.
  2. **No olvida.** Si usted reorganiza TWS, las cien confirmaciones
     viejas siguen pesando y Litch tarda una eternidad en darse cuenta.
  3. **Explora en círculos.** Recorría los elementos en orden fijo,
     gastando el mismo tiempo en lo que ya sabía de sobra que en lo que
     no tenía ni idea.
  4. **Se cree lo que ve.** Una racha de suerte de 5 aciertos lo daba por
     cierto sin más.

Aquí está la versión matemáticamente correcta.

LAS TRES PIEZAS
───────────────

**1. Beta-Bernoulli conjugado.** Cada elemento tiene una distribución
Beta(α, β) sobre la probabilidad de que ahí haya algo interactivo. Cada
observación actualiza el posterior:

        acierto → α += 1        fallo → β += 1

Empieza en Beta(1,1), que es la ignorancia total (uniforme en [0,1]).
La media es α/(α+β) y la varianza baja sola conforme llegan datos. Es la
forma canónica de aprender una probabilidad binaria, y tiene solución
cerrada: no hace falta ni entrenar ni iterar.

**2. Cota inferior de Wilson para confirmar.** Un elemento se da por
conocido cuando el LÍMITE INFERIOR de su intervalo de confianza supera el
umbral, no cuando su media lo supera. La diferencia:

        3 de 3  → media 100%, cota inferior 44%  → NO confirmado
       28 de 30 → media  93%, cota inferior 79%  → confirmado

Es la misma idea que ya usamos para no fiarnos de un setup con tres
operaciones. Aquí evita confirmar por una racha de suerte.

**3. Muestreo de Thompson para decidir dónde mirar.** En vez de recorrer
en orden, se saca una muestra aleatoria del posterior de cada elemento y
se explora el de muestra más alta.

El efecto es que dedica tiempo a lo INCIERTO: un elemento con Beta(1,1)
tiene muestras muy dispersas y sale elegido a menudo; uno con Beta(50,2)
da muestras siempre cerca de 0.96 y deja de necesitar atención. Es el
método estándar del problema del bandido y converge mucho más rápido que
recorrer en círculo.

**4. Olvido exponencial.** En cada actualización, α y β se multiplican por
un factor λ<1 antes de sumar. Eso hace que la evidencia vieja pese menos:
la memoria efectiva es ~1/(1-λ) observaciones. Si usted mueve un panel,
Litch se readapta en decenas de observaciones en vez de en miles.

TODO ESTO SIN NUMPY NI SCIPY
────────────────────────────
Son cuatro fórmulas y un generador aleatorio. Se implementan con la
librería estándar para que funcionen aunque falte cualquier dependencia.
"""

from __future__ import annotations

import math
import random

# ── Parámetros del modelo ───────────────────────────────────────────────────

ALFA_INICIAL = 1.0      # Beta(1,1) = no sé nada
BETA_INICIAL = 1.0

OLVIDO = 0.985          # λ: memoria efectiva ≈ 1/(1-λ) ≈ 67 observaciones
UMBRAL_CONFIRMAR = 0.70  # probabilidad mínima para dar algo por conocido
UMBRAL_DESCARTAR = 0.25  # por debajo de esto, ahí no hay nada
Z = 1.96                # 95% de confianza


# ═══════════════════════════════════════════════════════════════════════════
#  Creencia sobre un elemento
# ═══════════════════════════════════════════════════════════════════════════

def nueva_creencia() -> dict:
    """El estado de partida: ignorancia total."""
    return {"a": ALFA_INICIAL, "b": BETA_INICIAL, "n": 0}


def actualizar(cre: dict, acierto: bool, olvido: float = OLVIDO) -> dict:
    """Una observación. Actualiza el posterior con olvido exponencial.

    El olvido se aplica ANTES de sumar la observación nueva, así lo
    reciente siempre pesa más que lo antiguo. Sin esto, un cambio de
    distribución en la pantalla tardaría cientos de observaciones en
    reflejarse.
    """
    a = cre.get("a", ALFA_INICIAL) * olvido
    b = cre.get("b", BETA_INICIAL) * olvido

    # Nunca por debajo del prior: si no, el olvido acabaría borrando la
    # distribución entera y aparecerían divisiones por cero.
    a = max(a, ALFA_INICIAL)
    b = max(b, BETA_INICIAL)

    if acierto:
        a += 1.0
    else:
        b += 1.0

    return {"a": a, "b": b, "n": int(cre.get("n", 0)) + 1}


def media(cre: dict) -> float:
    """Probabilidad esperada de que ahí haya algo interactivo."""
    a = cre.get("a", ALFA_INICIAL)
    b = cre.get("b", BETA_INICIAL)
    return a / (a + b) if (a + b) > 0 else 0.5


def varianza(cre: dict) -> float:
    """Cuánta incertidumbre queda. Baja sola con los datos."""
    a = cre.get("a", ALFA_INICIAL)
    b = cre.get("b", BETA_INICIAL)
    s = a + b
    if s <= 1:
        return 0.25
    return (a * b) / (s * s * (s + 1))


def cota_inferior(cre: dict, z: float = Z) -> float:
    """Cota inferior de Wilson: lo MENOS que puede valer, con 95%.

    Es lo que se usa para confirmar, no la media. Confirmar por la media
    es lo que hace que tres aciertos seguidos parezcan una certeza.
    """
    a = cre.get("a", ALFA_INICIAL)
    b = cre.get("b", BETA_INICIAL)
    n = (a + b) - (ALFA_INICIAL + BETA_INICIAL)      # observaciones reales
    if n <= 0:
        return 0.0
    p = (a - ALFA_INICIAL) / n
    d = 1 + z * z / n
    centro = p + z * z / (2 * n)
    margen = z * math.sqrt(max(0.0, p * (1 - p) / n + z * z / (4 * n * n)))
    return max(0.0, (centro - margen) / d)


def cota_superior(cre: dict, z: float = Z) -> float:
    """Cota superior de Wilson: lo MÁS que puede valer."""
    a = cre.get("a", ALFA_INICIAL)
    b = cre.get("b", BETA_INICIAL)
    n = (a + b) - (ALFA_INICIAL + BETA_INICIAL)
    if n <= 0:
        return 1.0
    p = (a - ALFA_INICIAL) / n
    d = 1 + z * z / n
    centro = p + z * z / (2 * n)
    margen = z * math.sqrt(max(0.0, p * (1 - p) / n + z * z / (4 * n * n)))
    return min(1.0, (centro + margen) / d)


def veredicto(cre: dict) -> str:
    """confirmado / descartado / dudoso — con honestidad estadística."""
    if cota_inferior(cre) >= UMBRAL_CONFIRMAR:
        return "confirmado"
    if cota_superior(cre) <= UMBRAL_DESCARTAR:
        return "descartado"
    return "dudoso"


# ═══════════════════════════════════════════════════════════════════════════
#  Muestreo de Thompson: dónde mirar ahora
# ═══════════════════════════════════════════════════════════════════════════

def _muestra_gamma(k: float) -> float:
    """Una muestra de Gamma(k, 1). Método de Marsaglia-Tsang.

    Hace falta porque una Beta(a,b) se obtiene como X/(X+Y) con
    X~Gamma(a), Y~Gamma(b). Python trae random.gammavariate, así que se
    usa esa y esto queda como respaldo por si algún día no está.
    """
    try:
        return random.gammavariate(max(k, 1e-9), 1.0)
    except Exception:
        # Aproximación pobre pero suficiente para no romper nada
        return max(1e-9, sum(random.random() for _ in range(max(1, int(k)))))


def muestrear(cre: dict) -> float:
    """Una muestra del posterior Beta. El corazón de Thompson."""
    a = max(cre.get("a", ALFA_INICIAL), 1e-9)
    b = max(cre.get("b", BETA_INICIAL), 1e-9)
    try:
        return random.betavariate(a, b)
    except Exception:
        x = _muestra_gamma(a)
        y = _muestra_gamma(b)
        return x / (x + y) if (x + y) > 0 else 0.5


def elegir_siguiente(creencias: dict, claves: list) -> str:
    """Qué elemento explorar ahora: el que MENOS resuelto esté.

    ═══ POR QUÉ NO SE USA THOMPSON SAMPLING ═══

    La primera versión usaba muestreo de Thompson, que es EL algoritmo del
    problema del bandido y aparece en todos los manuales. Al medirlo
    resultó ser PEOR que recorrer los elementos en círculo: necesitaba más
    del doble de observaciones para resolver lo mismo.

    Y el motivo es que Thompson resuelve OTRO problema. Está diseñado para
    *encontrar la mejor opción y explotarla*, así que deliberadamente deja
    de mirar lo que cree malo — tiene todo el sentido si busca el brazo
    más rentable de una máquina tragaperras.

    Pero aquí no busco el mejor elemento: **busco clasificarlos todos**.
    Saber que en una zona NO hay nada vale exactamente lo mismo que saber
    que sí. Con Thompson, las zonas vacías nunca se visitaban lo bastante
    para poder descartarlas con confianza.

    El problema correcto se llama *aprendizaje activo*, y su criterio es
    muestreo por incertidumbre: mirar donde la duda es mayor.

    ═══ EL CRITERIO ═══

    Se puntúa cada elemento por lo lejos que está de estar resuelto:

      · ancho del intervalo de credibilidad — cuanta más duda, más urgente
      · distancia a la frontera de decisión — un 0.5 es lo peor de todo,
        porque no se puede ni confirmar ni descartar
      · penalización a los ya resueltos — no gastar tiempo en lo sabido

    Y se elige por ruleta, no por el máximo, para no quedarse enganchado
    en un elemento imposible de resolver.
    """
    if not claves:
        return ""

    pesos = []
    for k in claves:
        cre = creencias.get(k) or nueva_creencia()
        lo, hi = cota_inferior(cre), cota_superior(cre)
        m = media(cre)

        # 1. Amplitud del intervalo: la duda pura
        duda = hi - lo

        # 2. Cercanía a la frontera. Un elemento en 0.5 no se puede
        #    clasificar de ninguna manera, así que urge mirarlo.
        frontera = (UMBRAL_CONFIRMAR + UMBRAL_DESCARTAR) / 2.0
        cerca_frontera = 1.0 - min(1.0, abs(m - frontera) * 2.5)

        # 3. Lo ya resuelto casi no se toca: solo lo justo para detectar
        #    si la pantalla cambia bajo nuestros pies.
        v = veredicto(cre)
        factor = 0.06 if v in ("confirmado", "descartado") else 1.0

        # 4. Y lo nunca visto va primero de todo
        nunca = 3.0 if cre.get("n", 0) == 0 else 0.0

        peso = (duda * 2.0 + cerca_frontera * 0.6) * factor + nunca
        pesos.append(max(peso, 0.001))

    # Ruleta proporcional al peso: evita atascarse en un elemento que
    # nunca terminará de resolverse (uno que reaccione al 50% real).
    total = sum(pesos)
    r = random.random() * total
    acumulado = 0.0
    for k, p in zip(claves, pesos):
        acumulado += p
        if r <= acumulado:
            return k
    return claves[-1]


# ═══════════════════════════════════════════════════════════════════════════
#  ¿Ha aprendido ya bastante?
# ═══════════════════════════════════════════════════════════════════════════

def progreso(creencias: dict, claves: list) -> dict:
    """Cuánto sabe, con qué certeza, y si ya puede parar."""
    if not claves:
        return {"confirmados": 0, "descartados": 0, "dudosos": 0,
                "total": 0, "pct": 0.0, "certeza": 0.0, "converge": False}

    conf = desc = dud = 0
    suma_var = 0.0
    for k in claves:
        cre = creencias.get(k) or nueva_creencia()
        v = veredicto(cre)
        if v == "confirmado":
            conf += 1
        elif v == "descartado":
            desc += 1
        else:
            dud += 1
        suma_var += varianza(cre)

    total = len(claves)
    # «Resuelto» = confirmado o descartado. Saber que algo NO está también
    # es saber: descartar es aprendizaje, no fracaso.
    resueltos = conf + desc
    pct = 100.0 * resueltos / total

    # Certeza media: 1 - varianza normalizada
    certeza = max(0.0, 1.0 - (suma_var / total) * 4.0)

    # Converge cuando queda poca incertidumbre y casi todo está resuelto
    converge = (pct >= 85.0 and certeza >= 0.80)

    return {"confirmados": conf, "descartados": desc, "dudosos": dud,
            "total": total, "pct": pct, "certeza": certeza * 100,
            "converge": converge}


def explicar(cre: dict, nombre: str = "") -> str:
    """La creencia sobre un elemento, en castellano."""
    m = media(cre) * 100
    lo = cota_inferior(cre) * 100
    hi = cota_superior(cre) * 100
    n = cre.get("n", 0)
    v = veredicto(cre)

    etq = {"confirmado": "✓ confirmado",
           "descartado": "· descartado (ahí no hay nada)",
           "dudoso": "? aún dudo"}[v]

    txt = (f"{nombre + ': ' if nombre else ''}{etq} — "
           f"{m:.0f}% (entre {lo:.0f}% y {hi:.0f}%) en {n} observaciones")

    if v == "dudoso" and n >= 12:
        txt += ". Con tantas observaciones y sin decidirme, puede que ahí "
        txt += "haya algo que solo reacciona a veces."
    elif v == "dudoso" and n < 5:
        txt += ". Todavía muy poco visto."
    return txt

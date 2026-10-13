"""
boveda_obsidian.py — La memoria de Litch, escrita para que usted la lea.

EL PROBLEMA QUE RESUELVE
────────────────────────
Litch guarda todo en JSON: setups, operaciones, lecciones, zonas de la
pantalla. Es rápido y compacto, y es completamente opaco. Usted no puede
abrir `memoria_acciones.json` y entender qué ha aprendido, y sobre todo no
puede CORREGIRLO cuando aprenda algo mal.

Esa segunda parte es la importante. Una IA que aprende sola y cuyo
aprendizaje nadie puede revisar acumula errores en silencio.

Este módulo escribe lo mismo como notas de Obsidian: markdown enlazado.
Usted abre la bóveda, ve el grafo, lee lo que Litch cree saber, y si algo
está mal lo edita a mano.

QUÉ APORTA OBSIDIAN QUE EL JSON NO
──────────────────────────────────
  · **Enlaces [[wiki]]** — una operación enlaza con su setup, que enlaza
    con las herramientas que usó. El conocimiento deja de ser una lista y
    pasa a ser una red.
  · **Grafo visual** — se ve de un vistazo qué setups tienen muchas
    operaciones detrás y cuáles solo una. La muestra insuficiente deja de
    ser un número y se vuelve evidente.
  · **Etiquetas** — #ganada #perdida #dorado #peligroso #riesgo-alto.
  · **Búsqueda** — encontrar todas las operaciones donde saltó el stop.
  · **Editable** — usted corrige, Litch respeta lo corregido.

CÓMO SE ESCRIBE (y qué NO se toca)
──────────────────────────────────
Todo lo que Litch genera va entre marcas. Lo que usted escriba fuera de
ellas **no se sobrescribe nunca**. Si añade una nota suya al final de un
setup, seguirá ahí después de veinte actualizaciones.
"""

from __future__ import annotations

import os
import re
import time

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOVEDA = os.path.join(_BASE, "BOVEDA_LITCH")

# Estructura tomada del método que Giancarlo compartió (francisco.carosia),
# adaptada de creación de contenido a trading.
#
# Las tres últimas son las que faltaban y las que más aportan:
#   Decisiones — POR QUÉ se hizo algo, no solo qué pasó
#   Inbox      — lo capturado que aún no se ha procesado
#   Plantillas — para que las notas salgan siempre iguales
CARPETAS = ("Herramientas", "Setups", "Operaciones", "Aprendizajes",
            "Diario", "Decisiones", "Inbox", "Plantillas")

# Todo lo que Litch escribe va aquí dentro. Lo de fuera es del usuario.
INI = "<!-- LITCH:INICIO — no edite dentro de estas marcas -->"
FIN = "<!-- LITCH:FIN — debajo puede escribir usted, no lo tocaré -->"


# ═══════════════════════════════════════════════════════════════════════════
#  Utilidades
# ═══════════════════════════════════════════════════════════════════════════

def _preparar() -> None:
    for c in ("",) + CARPETAS:
        try:
            os.makedirs(os.path.join(BOVEDA, c), exist_ok=True)
        except Exception:
            pass


def _limpiar(nombre: str) -> str:
    """Nombre de archivo válido en Windows, legible en Obsidian."""
    n = re.sub(r'[<>:"/\\|?*\[\]#^]', "-", str(nombre))
    return n.strip()[:80] or "sin-nombre"


def _escribir(carpeta: str, titulo: str, cuerpo: str,
              etiquetas: list | None = None) -> str:
    """Escribe una nota respetando lo que el usuario haya añadido."""
    _preparar()
    ruta = os.path.join(BOVEDA, carpeta, _limpiar(titulo) + ".md")

    # Rescatar lo escrito por el usuario debajo de la marca FIN
    suyo = ""
    try:
        if os.path.exists(ruta):
            previo = open(ruta, encoding="utf-8").read()
            if FIN in previo:
                suyo = previo.split(FIN, 1)[1]
    except Exception:
        pass

    tags = " ".join(f"#{t}" for t in (etiquetas or []))

    # El bloque de propiedades (---) TIENE que ser lo primero del archivo.
    # Lo tenía después de la marca LITCH:INICIO y Obsidian no lo reconocía
    # como metadato: pintaba «generado-por: Litch» como si fuera un título.
    # Se vio en cuanto abrimos la bóveda de verdad.
    texto = (
        f"---\n"
        f"actualizado: {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"generado_por: Litch\n"
        + (f"tags: [{', '.join(etiquetas)}]\n" if etiquetas else "")
        + f"---\n\n"
        f"{INI}\n\n"
        f"# {titulo}\n\n"
        + (f"{tags}\n\n" if tags else "")
        + cuerpo.rstrip() + "\n\n"
        f"{FIN}\n"
        + (suyo if suyo.strip() else
           "\n## Mis notas\n\n*(Escriba aquí lo que quiera. Litch no borra "
           "nada de esta parte.)*\n")
    )
    try:
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(tmp, ruta)
        return ruta
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════
#  Exportadores
# ═══════════════════════════════════════════════════════════════════════════

def exportar_herramientas(app=None) -> int:
    """Una nota por herramienta de IBKR, con su nivel y su riesgo."""
    try:
        from . import escuela_ibkr as ei
    except Exception:
        return 0

    n = 0
    for clave, h in ei.HERRAMIENTAS.items():
        nivel = {1: "imprescindible", 2: "útil pronto",
                 3: "avanzada"}.get(h.get("nivel", 3), "?")
        riesgo = h.get("riesgo", "bajo")
        tags = ["ibkr", "herramienta", f"nivel-{h.get('nivel',3)}",
                f"riesgo-{riesgo}"]

        cuerpo = (
            f"> **{nivel.capitalize()}** · Riesgo **{riesgo}**\n\n"
            f"## Qué hace\n\n{h.get('que','')}\n\n"
            f"## Dónde está\n\n{h.get('donde','')}\n\n"
            f"## Por qué le importa\n\n{h.get('porque','')}\n\n"
            f"---\n\n"
            f"Parte de [[00 Índice|la bóveda de Litch]] · "
            f"ver también [[Escuela de IBKR]]"
        )
        if _escribir("Herramientas", h.get("nombre", clave), cuerpo, tags):
            n += 1

    # Nota índice de la escuela, con el plan de lecciones enlazado
    lineas = ["El plan de estudios que sigo, en orden. El orden importa: "
              "las primeras evitan pérdidas de dedo.\n"]
    for i, (clave, titulo) in enumerate(ei.LECCIONES, 1):
        h = ei.HERRAMIENTAS.get(clave, {})
        nombre = h.get("nombre", clave)
        aviso = " ⚠" if h.get("riesgo") == "alto" else ""
        lineas.append(f"{i}. [[{_limpiar(nombre)}|{titulo}]]{aviso}")
    _escribir("Herramientas", "Escuela de IBKR", "\n".join(lineas),
              ["ibkr", "escuela", "indice"])
    return n


def exportar_setups(app=None) -> int:
    """Una nota por patrón de entrada, con sus estadísticas reales."""
    try:
        from . import memoria_acciones as ma
        ops = list(ma.obtener()._ops)
    except Exception:
        return 0

    # Agrupar por setup
    grupos: dict = {}
    for o in ops:
        s = o.get("setup")
        if s:
            grupos.setdefault(s, []).append(o)

    n = 0
    for setup, lista in grupos.items():
        cerradas = [o for o in lista if not o.get("abierta")]
        wins = [o for o in cerradas if o.get("resultado") == "WIN"]
        rs = [float(o.get("r_multiplo", 0)) for o in cerradas]

        if cerradas:
            wr = 100.0 * len(wins) / len(cerradas)
            r_medio = sum(rs) / len(cerradas)
        else:
            wr = r_medio = 0.0

        suficiente = len(cerradas) >= 6
        if not suficiente:
            veredicto, tag = "muestra insuficiente", "sin-datos"
        elif wr >= 60 and r_medio > 0:
            veredicto, tag = "DORADO", "dorado"
        elif wr <= 35 or r_medio < -0.3:
            veredicto, tag = "PELIGROSO", "peligroso"
        else:
            veredicto, tag = "neutral", "neutral"

        cuerpo = [
            f"> **{veredicto}** — {len(cerradas)} operaciones cerradas",
            "",
            "| Métrica | Valor |",
            "|---|---|",
            f"| Operaciones cerradas | {len(cerradas)} |",
            f"| Acierto | {wr:.0f}% |",
            f"| Resultado medio | {r_medio:+.2f}R |",
            f"| Abiertas ahora | {len(lista) - len(cerradas)} |",
            "",
        ]
        if not suficiente:
            cuerpo.append(
                "> ⚠ Con menos de 6 operaciones esto **no significa nada**. "
                "Lo que se ve aquí es ruido, no un patrón.\n")
        cuerpo.append("## Operaciones de este setup\n")
        for o in lista[-15:]:
            marca = ("🟢" if o.get("resultado") == "WIN"
                     else "🔴" if o.get("resultado") == "LOSS" else "⏳")
            cuerpo.append(
                f"- {marca} [[{_limpiar(o.get('id','?'))}|"
                f"{o.get('simbolo')} {o.get('ts_apertura','')[:16]}]] "
                f"— {o.get('r_multiplo', 0):+.2f}R")
        cuerpo.append("\n---\n\nVer [[00 Índice]]")

        if _escribir("Setups", setup, "\n".join(cuerpo),
                     ["setup", tag, "acciones"]):
            n += 1
    return n


def exportar_operaciones(app=None, limite: int = 120) -> int:
    """Una nota por operación, enlazada con su setup."""
    try:
        from . import memoria_acciones as ma
        ops = list(ma.obtener()._ops)[-limite:]
    except Exception:
        return 0

    n = 0
    for o in ops:
        abierta = o.get("abierta")
        res = o.get("resultado")
        tag = ("abierta" if abierta else
               "ganada" if res == "WIN" else "perdida")
        r = float(o.get("r_multiplo", 0))

        cuerpo = [
            f"> {o.get('direccion','?')} **{o.get('simbolo','?')}** · "
            + ("**abierta**" if abierta else
               f"cerrada en **{r:+.2f}R**"),
            "",
            "| | |",
            "|---|---|",
            f"| Entrada | {o.get('entrada')} |",
            f"| Stop | {o.get('stop')} |",
            f"| Objetivo | {o.get('objetivo')} |",
            f"| Cantidad | {o.get('cantidad')} |",
            f"| Abierta | {o.get('ts_apertura','')} |",
        ]
        if not abierta:
            cuerpo += [
                f"| Cerrada | {o.get('ts_cierre','')} |",
                f"| Salida | {o.get('precio_salida')} |",
                f"| Motivo | {o.get('motivo_cierre','')} |",
            ]
        if o.get("stop_original") and o["stop_original"] != o.get("stop"):
            cuerpo.append(f"| Stop original | {o['stop_original']} "
                          f"(movido a favor) |")
        cuerpo.append("")
        if o.get("setup"):
            cuerpo.append(f"Setup: [[{_limpiar(o['setup'])}]]")
        cuerpo.append("\nVer [[00 Índice]]")

        if _escribir("Operaciones", o.get("id", "op"), "\n".join(cuerpo),
                     [tag, "operacion", str(o.get("simbolo", "")).lower()]):
            n += 1
    return n


def exportar_aprendizajes(app=None) -> int:
    """Lo que Litch ha averiguado explorando TWS por su cuenta."""
    try:
        from . import practica_ibkr as pi
        c = pi.obtener(app).conocimiento
        ciclos = pi.obtener(app).ciclo
    except Exception:
        return 0
    if not c:
        return 0

    filas = ["| Zona | Observaciones | Acierto | Tipo | Nota |",
             "|---|---|---|---|---|"]
    for zona, z in sorted(c.items()):
        tot = z.get("aciertos", 0) + z.get("fallos", 0)
        fiab = 100.0 * z.get("aciertos", 0) / tot if tot else 0
        filas.append(f"| {zona} | {z.get('obs',0)} | {fiab:.0f}% | "
                     f"{z.get('tipo','?')} | {z.get('nota','')} |")

    cuerpo = (
        f"> {ciclos} rondas de observación de Trader Workstation\n\n"
        "Cada ronda comparo lo que veo con lo que el manual dice que "
        "debería haber. Donde falla mucho, es que su TWS está ordenado "
        "distinto — y entonces el que se equivoca soy yo, no usted.\n\n"
        + "\n".join(filas) +
        "\n\n## Cómo leer esto\n\n"
        "- **viva** = la zona cambia sola (precios, velas)\n"
        "- **quieta** = no cambia (menús, títulos)\n"
        "- Acierto bajo = ahí no está lo que yo creía\n\n"
        "Ver [[00 Índice]] · [[Escuela de IBKR]]"
    )
    _escribir("Aprendizajes", "Mapa de Trader Workstation", cuerpo,
              ["ibkr", "exploracion", "aprendizaje"])
    return 1


def escribir_diario(app=None) -> str:
    """La nota del día: qué pasó y qué se aprendió."""
    hoy = time.strftime("%Y-%m-%d")
    partes = [f"> Sesión del {hoy}\n"]

    try:
        from . import memoria_acciones as ma
        ops = [o for o in ma.obtener()._ops
               if str(o.get("ts_cierre", ""))[:10] == hoy
               or str(o.get("ts_apertura", ""))[:10] == hoy]
        if ops:
            partes.append("## Operaciones de hoy\n")
            for o in ops:
                marca = ("🟢" if o.get("resultado") == "WIN"
                         else "🔴" if o.get("resultado") == "LOSS" else "⏳")
                partes.append(f"- {marca} [[{_limpiar(o.get('id','?'))}|"
                              f"{o.get('simbolo')}]] "
                              f"{o.get('r_multiplo', 0):+.2f}R")
            cerr = [o for o in ops if not o.get("abierta")]
            if cerr:
                tot = sum(float(o.get("r_multiplo", 0)) for o in cerr)
                partes.append(f"\n**Resultado del día: {tot:+.2f}R** en "
                              f"{len(cerr)} operaciones cerradas.")
                if len(cerr) < 5:
                    partes.append("\n> Un día no dice nada. Lo que cuenta "
                                  "es la serie.")
        else:
            partes.append("Sin operaciones hoy.\n\n> No operar también es "
                          "operar. Un día sin señales claras es un día bien "
                          "gestionado.")
    except Exception:
        pass

    try:
        from . import guardia_pdt as pdt
        dts = pdt.en_ventana()
        if dts:
            partes.append(f"\n## Regla PDT\n\n{len(dts)} day trades en la "
                          f"ventana de 5 días hábiles (límite propio: 3).")
    except Exception:
        pass

    partes.append("\n---\n\nVer [[00 Índice]]")
    _escribir("Diario", hoy, "\n".join(partes), ["diario", "sesion"])
    return hoy


def escribir_indice(app=None) -> None:
    """La puerta de entrada de la bóveda."""
    try:
        from . import escuela_ibkr as ei
        n_h = len(ei.HERRAMIENTAS)
    except Exception:
        n_h = 0
    try:
        from . import memoria_acciones as ma
        ops = list(ma.obtener()._ops)
        n_o = len(ops)
        n_c = len([o for o in ops if not o.get("abierta")])
    except Exception:
        n_o = n_c = 0

    cuerpo = f"""Esta es mi memoria, escrita para que usted pueda leerla.

Todo lo que hay aquí lo he generado yo, salvo lo que usted escriba bajo
«Mis notas» en cada página: **eso no lo toco nunca**.

Si ve algo que he aprendido mal, corríjalo. Prefiero que me enmiende a
seguir equivocado en silencio.

## Por dónde empezar

- [[Escuela de IBKR]] — el plan de {n_h} lecciones, en orden
- [[Mapa de Trader Workstation]] — lo que he averiguado explorando

## Carpetas

| Carpeta | Qué hay |
|---|---|
| **Herramientas** | Una ficha por función de IBKR, con su riesgo |
| **Setups** | Patrones de entrada y cómo me han ido |
| **Operaciones** | {n_o} operaciones ({n_c} cerradas) |
| **Aprendizajes** | Lo que descubro explorando por mi cuenta |
| **Diario** | Una nota por sesión |

## Etiquetas útiles

`#dorado` setups que funcionan · `#peligroso` los que evito ·
`#sin-datos` muestra insuficiente · `#riesgo-alto` funciones que pueden
costarle dinero · `#ganada` `#perdida` operaciones

## El grafo

Pulse el icono del grafo (arriba a la izquierda). Verá las operaciones
colgando de sus setups. **Un setup con un solo punto colgando no es un
patrón: es una casualidad.** Eso se ve mejor en el grafo que en cualquier
tabla.

---

*Actualizado el {time.strftime('%Y-%m-%d a las %H:%M')} · «Litch,
actualiza la bóveda» para refrescarla.*
"""
    _escribir("", "00 Índice", cuerpo, ["indice", "litch"])


# ═══════════════════════════════════════════════════════════════════════════
#  Punto de entrada
# ═══════════════════════════════════════════════════════════════════════════

def escribir_claude_md(app=None) -> None:
    """El archivo raíz que cualquier IA lee al abrir esta carpeta.

    POR QUÉ AHORRA TOKENS, que es lo que pedía Giancarlo:

    Sin este archivo, una IA que abre la bóveda tiene que leerlo todo para
    saber qué hay — cientos de notas, decenas de miles de tokens, cada vez.

    Con él, lee UNA página que dice qué hay en cada sitio y va directa a lo
    que necesita. Es la diferencia entre leerse la biblioteca entera y
    mirar el fichero.

    Es el mismo mecanismo del CLAUDE.md que se ve en el método original.
    """
    try:
        from . import escuela_ibkr as ei
        n_h = len(ei.HERRAMIENTAS)
    except Exception:
        n_h = 0
    try:
        from . import memoria_acciones as ma
        ops = list(ma.obtener()._ops)
        n_o, n_c = len(ops), len([o for o in ops if not o.get("abierta")])
    except Exception:
        n_o = n_c = 0

    texto = f"""# Bóveda de Litch — instrucciones para la IA

Esta carpeta es la memoria de **Litch**, una IA local de trading que opera
acciones de EE.UU. a través de Interactive Brokers. Su dueño es Giancarlo
González Guerrero, que está aprendiendo a operar y usa cuenta simulada.

**Lea esta página antes de buscar nada.** Le dice dónde está cada cosa,
para que no tenga que recorrer la bóveda entera.

## Qué hay en cada carpeta

| Carpeta | Contenido | Cuándo mirarla |
|---|---|---|
| `Herramientas/` | {n_h} fichas de funciones de IBKR, con nivel y riesgo | Preguntas sobre cómo se usa TWS |
| `Setups/` | Patrones de entrada con sus estadísticas reales | «¿este setup funciona?» |
| `Operaciones/` | {n_o} operaciones ({n_c} cerradas) | Historial concreto |
| `Decisiones/` | **Por qué** se tomó cada decisión | «¿por qué hiciste esto?» |
| `Aprendizajes/` | Lo descubierto explorando TWS | Distribución de la pantalla |
| `Diario/` | Una nota por sesión | «¿qué pasó el martes?» |
| `Inbox/` | Capturado sin procesar | Ideas pendientes |
| `Plantillas/` | Formatos de nota | Al crear notas nuevas |

## Reglas de esta bóveda

1. **Lo que hay entre `<!-- LITCH:INICIO -->` y `<!-- LITCH:FIN -->` lo
   genera Litch y se sobrescribe.** No lo edite: se perderá.
2. **Todo lo que hay debajo de `LITCH:FIN` es de Giancarlo y NO se toca
   jamás.** Ahí escribe sus correcciones.
3. **Ante un desacuerdo entre lo que dice Litch y lo que escribió
   Giancarlo, gana Giancarlo.** Litch ha visto números; él ha visto el
   mercado.

## Cómo interpretar los números

- Los resultados se miden en **R** (múltiplos de riesgo), no en dólares.
  1R = lo que se estaba dispuesto a perder. Así se comparan operaciones
  de distinto tamaño.
- **Menos de 6 operaciones en un setup no significa nada.** Menos de 30
  en el total tampoco. Si ve un porcentaje alto con muestra corta, es
  ruido, y decirlo es más útil que celebrarlo.
- Los resultados de cuenta simulada son **optimistas por construcción**:
  IBKR documenta que las ejecuciones se simulan desde el tope del libro,
  así que siempre hay contrapartida. En real no será así.

## Lo que Litch NO hace

- No opera en cuenta real. Solo simulada verificada (prefijo DU).
- No mueve un stop en contra. Nunca. Está impedido por código.
- No abre posiciones cortas sin permiso explícito.
- No promete rentabilidad ni predice precios.

## Contexto que importa

- Capital pequeño → le aplica la regla **PDT**: con menos de 25.000 USD,
  4 operaciones de ida y vuelta el mismo día en 5 días hábiles bloquean
  la cuenta 90 días. Litch se detiene en 3.
- Cuenta simulada: **DUR328203**. Puerto 7497.
- Riesgo por operación: **1% del capital**.

---

*Generado por Litch el {time.strftime('%Y-%m-%d %H:%M')}. Empiece por
[[00 Índice]].*
"""
    try:
        _preparar()
        with open(os.path.join(BOVEDA, "CLAUDE.md"), "w",
                  encoding="utf-8") as f:
            f.write(texto)
    except Exception:
        pass


def escribir_plantillas(app=None) -> int:
    """Formatos fijos para que las notas nuevas salgan coherentes."""
    n = 0
    plantillas = {
        "Plantilla — Decisión": """> Fecha: {{date}}

## Qué decidí

## Por qué

## Qué esperaba que pasara

## Qué pasó de verdad

*(rellenar después)*

## Qué aprendo

*(rellenar después)*

---
Etiquetas: #decision
""",
        "Plantilla — Operación revisada": """> {{date}} · Símbolo:

## El plan
- Entrada:
- Stop:
- Objetivo:
- Riesgo en R: 1R

## Por qué entré

## Cómo salió

## ¿Seguí mi plan?

*Esta es la pregunta que importa. Una operación puede perder dinero y
estar bien hecha, y puede ganar dinero y estar mal hecha. Lo que se
repite es el proceso, no el resultado.*

---
Etiquetas: #operacion #revision
""",
        "Plantilla — Idea suelta": """> Capturado el {{date}}

## La idea

## De dónde salió

## ¿Merece la pena probarla?

---
Etiquetas: #inbox
""",
    }
    for titulo, cuerpo in plantillas.items():
        if _escribir("Plantillas", titulo, cuerpo, ["plantilla"]):
            n += 1
    return n


def registrar_decision(app, titulo: str, que: str, porque: str,
                       esperaba: str = "") -> str:
    """Anota una decisión CON su razonamiento.

    Litch guardaba el resultado de cada operación pero no el razonamiento
    que la motivó. Y el razonamiento es lo único que se puede corregir:
    un resultado ya pasó, un criterio se puede cambiar.
    """
    cuerpo = (f"> {time.strftime('%Y-%m-%d %H:%M')}\n\n"
              f"## Qué decidí\n\n{que}\n\n"
              f"## Por qué\n\n{porque}\n\n")
    if esperaba:
        cuerpo += f"## Qué esperaba\n\n{esperaba}\n\n"
    cuerpo += ("## Qué pasó de verdad\n\n*(por rellenar)*\n\n"
               "---\n\nVer [[00 Índice]]")
    ruta = _escribir("Decisiones",
                     f"{time.strftime('%Y-%m-%d %H%M')} — {titulo}",
                     cuerpo, ["decision"])
    return ruta


def actualizar(app=None) -> str:
    """Vuelca toda la memoria de Litch a la bóveda."""
    _preparar()
    h = exportar_herramientas(app)
    s = exportar_setups(app)
    o = exportar_operaciones(app)
    a = exportar_aprendizajes(app)
    p = escribir_plantillas(app)
    dia = escribir_diario(app)
    escribir_indice(app)
    escribir_claude_md(app)

    return (
        f"Bóveda actualizada, señor.\n\n"
        f"  {h} herramientas de IBKR\n"
        f"  {s} setups con sus estadísticas\n"
        f"  {o} operaciones\n"
        f"  {a} mapa(s) de exploración\n"
        f"  {p} plantillas\n"
        f"  diario de {dia}\n"
        f"  CLAUDE.md en la raíz\n\n"
        f"Ese CLAUDE.md es la pieza que ahorra trabajo: cualquier IA que "
        f"abra esta carpeta lee UNA página y ya sabe dónde está todo, en "
        f"vez de recorrerse las {h + s + o} notas para enterarse.\n\n"
        f"Está en BOVEDA_LITCH. En Obsidian: «Abrir carpeta como bóveda», "
        f"y empiece por «00 Índice».\n\n"
        f"Lo que escriba usted bajo «Mis notas» no lo sobrescribo nunca."
    )


def ruta_boveda() -> str:
    return BOVEDA

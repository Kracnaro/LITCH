"""Verificador de Litch — compila todos los módulos y reporta errores.

Uso:  python verificar.py   (o doble clic en verificar.bat)
"""
import glob
import os
import py_compile
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

errores = 0
archivos = ["litch.py"] + sorted(glob.glob("core/*.py"))
for f in archivos:
    try:
        py_compile.compile(f, doraise=True)
        print(f"  OK   {f}")
    except Exception as e:
        errores += 1
        print(f"  [X]  {f}  ->  {e}")

print()
if errores:
    print(f"  RESULTADO: {errores} archivo(s) con errores. NO inicies Litch aun.")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════
#  COMPROBACION DE LA RED DE SEGURIDAD
# ═══════════════════════════════════════════════════════════════════════════
# Compilar solo dice que el codigo es Python valido. Esto comprueba que las
# protecciones siguen ahi: es facil desactivar una sin querer al editar, y
# nadie se entera hasta que ya paso algo.

print("  --- Red de seguridad ---")
fallos = []


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


CONTROLES = [
    ("core/piloto_tws.py", 'es_paper") is False',
     "el piloto se detiene si la cuenta es REAL"),
    ("core/piloto_tws.py", "esta_calibrado",
     "el piloto exige calibracion antes de hacer clic"),
    ("core/piloto_tws.py", "detectar_dialogo",
     "el piloto detecta ventanas que tapan TWS"),
    ("core/piloto_tws.py", "min(x, ventana",
     "las coordenadas se recortan al interior de TWS"),
    ("core/broker_ibkr.py", "_es_paper is not True",
     "el bracket exige cuenta simulada verificada"),
    ("core/broker_ibkr.py", "NO la convierto",
     "una orden limite sin precio no se degrada a mercado"),
    ("core/motor_acciones.py", "America/New_York",
     "el horario usa la hora real de Nueva York"),
    ("core/motor_acciones.py", "FESTIVOS_NYSE",
     "conoce los festivos de Wall Street"),
    ("core/piloto_autonomo.py", "self.nivel = 1",
     "el piloto BAJA de nivel solo si el resultado se hunde"),
    ("core/piloto_autonomo.py", "NIVELES",
     "la autonomia se gana por niveles, no se regala"),
    ("core/interfaz.py", "autonomo_confirmado",
     "pide permiso explicito antes de operar solo por primera vez"),
    ("core/rutinas_tws.py", "def revisar_margen",
     "revisa el margen antes de transmitir (paso d del manual de TWS)"),
    ("core/escuela_ibkr.py", "cinco_pasos",
     "conoce los cinco pasos de toda operacion en TWS"),
    ("LIBROS/17_PROCEDIMIENTOS_TWS.md", "de forma inmediata",
     "manual de procedimientos de TWS"),
    ("core/interfaz.py", "def _plegar_ribbon",
     "la barra se puede plegar para que LITCH vea mas pantalla"),
    ("core/aprendizaje_bayes.py", "def cota_inferior",
     "confirma por cota de Wilson, no por la media (no confia en rachas)"),
    ("core/aprendizaje_bayes.py", "OLVIDO",
     "olvida lo viejo: se readapta si cambia la pantalla"),
    ("core/aprendizaje_broker.py", "aprendizaje_bayes",
     "el aprendizaje usa el motor bayesiano"),
    ("core/aprendizaje_broker.py", "PERFILES",
     "el aprendizaje sirve para cualquier broker, no solo IBKR"),
    ("core/aprendizaje_broker.py", "REJILLA_X",
     "puede aprender un broker que no conoce, explorando de cero"),
    ("servidor_litch.py", "127.0.0.1",
     "el servidor local escucha SOLO en su equipo"),
    ("servidor_litch.py", "/v1/models",
     "el servidor expone /v1/models (sin el, los plugins no conectan)"),
    ("core/aprendizaje_ibkr.py", "verificar_seguro",
     "el aprendizaje activo pasa por las mismas protecciones que el piloto"),
    ("core/mapa_codigo.py", "def generar",
     "documenta el codigo fuente en la boveda"),
    ("core/consulta_boveda.py", "def responder",
     "Litch LEE su boveda, no solo la escribe"),
    ("core/consulta_boveda.py", "NOTA SUYA",
     "las correcciones del usuario se leen antes que el analisis de Litch"),
    ("core/boveda_obsidian.py", "LITCH:FIN",
     "la boveda respeta lo que escriba el usuario"),
    ("core/modo_practica.py", "_broker_del_usuario",
     "la practica va al broker que el usuario tiene abierto"),
    ("core/practica_ibkr.py", "def _concluir",
     "piensa en silencio y dice UNA sola conclusion"),
    ("core/voz.py", "_sintetizar_seguro",
     "la voz usa su propio bucle: nadie puede romperla desde fuera"),
    ("core/broker_ibkr.py", "def _reconectar",
     "el conector que OPERA se reconecta solo tras el reinicio de TWS"),
    ("core/broker_ibkr.py", "from ib_async",
     "prefiere ib_async (mantenida) sobre ib_insync"),
    ("conexion_ibkr.py", "PERMITIR_LIVE = False",
     "la conexion de un clic arranca bloqueada para Live"),
    ("conexion_ibkr.py", "PREFIJOS_PAPER",
     "detecta la cuenta simulada por prefijo exacto, no solo por la D"),
    ("conexion_ibkr.py", "_reconectando",
     "la reconexion no se llama a si misma (evita recursion infinita)"),
    ("bandeja.py", "def _en_hilo",
     "la bandeja no se congela al conectar"),
    ("core/protocolo_agente.py", "def verificar_cinco_datos",
     "verifica los cinco datos antes de cada orden (AGENTE.md B.4)"),
    ("core/protocolo_agente.py", "corto_autorizado",
     "no abre posiciones cortas sin permiso explicito"),
    ("core/protocolo_agente.py", "UMBRAL_ROJO",
     "vigila el colchon de margen (AGENTE.md D.5)"),
    ("core/broker_ibkr.py", "verificar_cinco_datos",
     "el bracket pasa por los cinco datos"),
    ("core/escuela_ibkr.py", "paper_vs_real",
     "explica por que la simulada da mejores numeros que la real"),
    ("core/escuela_ibkr.py", "\"presets\"",
     "avisa de los presets (la cantidad por defecto)"),
    ("core/escuela_ibkr.py", "orden_watchlist",
     "avisa de que un clic en el precio abre un ticket"),
    # Marcador en ASCII puro: los acentos en este archivo dieron un falso
    # negativo porque verificar.py se guarda sin tildes a proposito.
    ("LIBROS/16_CURSO_IBKR_DESKTOP_LECCIONES.md", "100 shares",
     "curso IBKR Desktop leccion por leccion"),
    ("LIBROS/15_SERIE_TUTORIALES_IBKR.md", "tope del libro",
     "manual de la serie oficial de tutoriales de IBKR"),
    ("LIBROS/00_AGENTE_CEREBRO_RAIZ.md", "REGLAS INVIOLABLES",
     "el cerebro raiz AGENTE.md esta instalado"),
    ("core/guardia_pdt.py", "LIMITE_PROPIO",
     "protege de la regla PDT (bloqueo de 90 dias)"),
    ("core/modo_wallstreet.py", "guardia_pdt",
     "el modo autonomo consulta la regla PDT"),
    ("core/gestor_posicion.py", "if nuevo <= actual",
     "el stop NUNCA se puede ampliar (solo se mueve a favor)"),
    ("core/gestor_posicion.py", "R_EQUILIBRIO",
     "mueve el stop a punto de equilibrio a +1R"),
    ("core/manos.py", "def _dentro_de_tws",
     "los clics de IQ Option no pueden caer dentro de TWS"),
    ("core/broker_iq.py", "_fuera_de_tws",
     "broker_iq comprueba antes de cada clic"),
    ("core/chart_controls.py", "def _seguro",
     "los botones del grafico tampoco tocan TWS"),
    ("core/vigilante_posiciones.py", "self._arrancado",
     "el vigilante cierra operaciones y aprende de ellas"),
    ("core/memoria_acciones.py", "suficiente",
     "no muestra 0% de acierto con muestra corta"),
    ("core/broker_ibkr.py", "Bracket incompleto",
     "cancela todo si el bracket no entra entero"),
    ("core/modo_wallstreet.py", "MIN_MIN_TRAS_APERTURA",
     "no opera en los primeros ni ultimos minutos"),
    ("litch.py", "def _preparar_ibkr",
     "prepara IBKR al arrancar"),
    ("core/rutinas_tws.py", "r.detenida_en",
     "las rutinas se detienen si un paso falla"),
    ("core/escuela_ibkr.py", "Rapid Transmit",
     "avisa del modo sin boton ENVIAR"),
    ("LIBROS/14_MANUAL_TWS_OFICIAL.md", "Attach Stop Loss/Profit Taker",
     "manual oficial de TWS con la ruta real del bracket"),
    ("core/vision_tws.py", "interactivebrokers",
     "reconoce InteractiveBrokers escrito sin espacio"),
    ("core/trading.py", 'broker_visual") == "tws"',
     "no predice velas binarias sobre acciones"),
    ("core/motor_acciones.py", "def velas_de",
     "analiza el simbolo pedido, no el activo de IQ Option"),
    ("core/motor_acciones.py", "acuerdo * cobertura",
     "la confianza pondera acuerdo y evidencia"),
    ("core/performance_tracker.py", "_MIN_N_MEJOR",
     "no recomienda horas con muestra insuficiente"),
    ("core/guardias_riesgo.py", "cortacircuito",
     "el cortacircuito de riesgo sigue presente"),
]

# Control NEGATIVO: el aprendizaje activo NO puede hacer clic.
#
# Es el modulo que mueve el raton dentro de TWS. Posarse encima de algo no
# puede enviar una orden; pulsar si. Si algun dia alguien anade un click
# aqui, esto lo detecta antes de que llegue a la cuenta.
_apr = _leer("core/aprendizaje_ibkr.py") + _leer("core/aprendizaje_broker.py")
_apr_codigo = "\n".join(l for l in _apr.split("\n")
                        if not l.strip().startswith("#"))
if not _apr:
    fallos.append("falta core/aprendizaje_ibkr.py")
    print("  [X]  aprendizaje activo  ->  no encuentro el archivo")
elif (".click(" in _apr_codigo or ".doubleClick(" in _apr_codigo
        or ".tripleClick(" in _apr_codigo or ".mouseDown(" in _apr_codigo):
    fallos.append("el aprendizaje activo hace CLIC (solo debe posarse)")
    print("  [X]  el aprendizaje NO hace clic  ->  AHORA SI HACE CLIC")
elif "moveTo" not in _apr_codigo:
    fallos.append("el aprendizaje no mueve el raton")
    print("  [X]  el aprendizaje explora con el raton  ->  no lo mueve")
else:
    print("  OK   el aprendizaje activo se posa pero NUNCA hace clic")

# Control especial: el arranque NO debe encender el modo de operar.
# Esto es una comprobacion NEGATIVA — verifica que algo NO esta ahi.
_arranque = _leer("litch.py")
_i = _arranque.find("def _preparar_ibkr")
_cuerpo = _arranque[_i:_i + 3500] if _i >= 0 else ""
if _i < 0:
    fallos.append("no encuentro la preparacion de IBKR al arrancar")
    print("  [X]  arranque automatico de IBKR  ->  no existe")
elif ("modo_wallstreet" in _cuerpo or "activar(" in _cuerpo
        or "autoclick_on = True" in _cuerpo):
    fallos.append("el arranque enciende el modo de operar")
    print("  [X]  el arranque NO abre operaciones solo  ->  AHORA SI LAS ABRE")
else:
    print("  OK   el arranque prepara IBKR pero NO abre operaciones solo")

for ruta, marca, descripcion in CONTROLES:
    contenido = _leer(ruta)
    if not contenido:
        fallos.append(f"falta el archivo {ruta}")
        print(f"  [X]  {descripcion}  ->  no encuentro {ruta}")
    elif marca in contenido:
        print(f"  OK   {descripcion}")
    else:
        fallos.append(descripcion)
        print(f"  [X]  {descripcion}  ->  PROTECCION AUSENTE")

# Los comandos de voz deben seguir conectados al cerebro.
# La comparacion ignora acentos: "leccion" debe encontrar "lección".
import unicodedata


def _plano(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower())
                   if unicodedata.category(c) != "Mn")


cerebro_plano = _plano(_leer("core/cerebro.py"))
COMANDOS = ["calibra el ticket", "ensename tws", "panel sencillo",
            "siguiente leccion", "describe la pantalla", "verifica la cuenta"]
sin_conectar = [c for c in COMANDOS if _plano(c) not in cerebro_plano]
if sin_conectar:
    fallos.append("comandos sin conectar: " + ", ".join(sin_conectar))
    print(f"  [X]  comandos de voz  ->  faltan: {', '.join(sin_conectar)}")
else:
    print(f"  OK   los {len(COMANDOS)} comandos principales estan conectados")

print()
if fallos:
    print(f"  RESULTADO: compila, pero hay {len(fallos)} proteccion(es) que")
    print("  ya no estan. Revisalo antes de operar:")
    for f in fallos:
        print(f"    - {f}")
    sys.exit(2)

print("  RESULTADO: todo correcto y la red de seguridad esta intacta.")
print("  Puedes iniciar Litch.")

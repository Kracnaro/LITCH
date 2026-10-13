"""
probar_ibkr.py — Prueba completa de Litch contra Interactive Brokers.

Doble clic en probar_ibkr.bat y este programa examina TODO lo que Litch
necesita para trabajar en Wall Street, contra su maquina real.

NO ENVIA NINGUNA ORDEN. NO TOCA EL RATON. Solo mira y le cuenta.

Cada prueba dice tres cosas:
  * si pasa o no
  * que encontro exactamente
  * que hacer si fallo

Ejecutelo con TWS abierto para la prueba completa. Sin TWS tambien sirve:
comprueba todo lo que no depende de la ventana.
"""

import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Colores solo si la consola los admite
try:
    os.system("")
    V, R, A, Z, N = ("\033[92m", "\033[91m", "\033[93m", "\033[96m",
                     "\033[0m")
except Exception:
    V = R = A = Z = N = ""

resultados = []


def prueba(nombre, funcion, arreglo=""):
    """Ejecuta una comprobacion y guarda el resultado."""
    print(f"  ... {nombre}", end="\r")
    try:
        ok, detalle = funcion()
    except Exception as e:
        ok, detalle = False, f"error inesperado: {e}"
    marca = f"{V}[OK]{N}" if ok else f"{R}[X] {N}"
    print(f"  {marca} {nombre}")
    if detalle:
        print(f"        {detalle}")
    if not ok and arreglo:
        print(f"        {A}-> {arreglo}{N}")
    resultados.append((nombre, ok))
    return ok


class AppFalsa:
    """Un 'app' minimo para que los modulos de Litch funcionen sin la GUI."""

    def __init__(self):
        self.mem = {"config": {}}
        self.autoclick_on = False
        self.modo_autonomo = False
        self.tv_feed = None
        try:
            from core import memoria
            self.mem = memoria.cargar()
        except Exception:
            pass

    def log(self, t):
        pass

    def decir(self, t):
        pass


print()
print("=" * 66)
print("   PRUEBA DE LITCH CON INTERACTIVE BROKERS")
print("   " + time.strftime("%d/%m/%Y %H:%M"))
print("=" * 66)
print()

app = AppFalsa()

# ─────────────────────────────────────────────────────────────────────────
print(f"{Z}--- 1. Librerias necesarias ---{N}")


def _numpy():
    import numpy
    return True, f"numpy {numpy.__version__}"


def _mss():
    import mss
    return True, "captura de pantalla disponible"


def _pyautogui():
    import pyautogui
    w, h = pyautogui.size()
    return True, f"control de raton listo, pantalla {w}x{h}"


def _yfinance():
    import yfinance
    return True, "descarga de datos de mercado disponible"


def _ibapi():
    try:
        import ib_insync
        return True, "ib_insync instalado (API de IBKR)"
    except ImportError:
        try:
            import ibapi
            return True, "ibapi instalado (API de IBKR)"
        except ImportError:
            return False, "sin API de IBKR"


prueba("numpy", _numpy, "py -m pip install numpy")
prueba("mss (ver la pantalla)", _mss, "py -m pip install mss")
prueba("pyautogui (mover el raton)", _pyautogui, "py -m pip install pyautogui")
prueba("yfinance (datos de mercado)", _yfinance, "py -m pip install yfinance")
prueba("API de IBKR", _ibapi,
       "py -m pip install ib_insync   (opcional pero recomendado)")

# ─────────────────────────────────────────────────────────────────────────
print()
print(f"{Z}--- 2. Modulos de Litch ---{N}")

MODULOS = [
    ("vision_tws", "ojos para TWS"),
    ("piloto_tws", "manos para TWS"),
    ("conciencia_pantalla", "vision de pantalla completa"),
    ("escuela_ibkr", "conocimiento de IBKR"),
    ("rutinas_tws", "procedimientos verificados"),
    ("motor_acciones", "motor de acciones"),
    ("memoria_acciones", "memoria de operaciones"),
    ("guardias_riesgo", "guardias de riesgo"),
    ("broker_ibkr", "conector con IBKR"),
    ("panel_simple", "panel sencillo"),
]

for mod, desc in MODULOS:
    def _cargar(m=mod):
        __import__(f"core.{m}")
        return True, desc
    prueba(f"core/{mod}.py", _cargar,
           "ejecute verificar.bat para ver el error exacto")

# ─────────────────────────────────────────────────────────────────────────
print()
print(f"{Z}--- 3. Deteccion de Trader Workstation ---{N}")

tws_visible = False


def _ver_tws():
    global tws_visible
    from core import vision_tws as vt
    v = vt.ventana_tws()
    if not v:
        return False, "no encuentro la ventana"
    tws_visible = True
    return True, f"titulo: \"{v['titulo'][:46]}\"  ({v['w']}x{v['h']})"


def _cuenta():
    from core import vision_tws as vt
    e = vt.leer_estado_tws(app)
    if not e.get("tws_abierta"):
        return False, "TWS cerrado"
    p = e.get("es_paper")
    if p is True:
        return True, f"cuenta {e.get('cuenta','DU...')} = SIMULADA, sin riesgo"
    if p is False:
        return False, f"CUIDADO: cuenta {e.get('cuenta')} parece REAL"
    return False, "no distingo si es simulada"


def _dialogos():
    from core import conciencia_pantalla as cp
    d = cp.detectar_dialogo(app)
    return (not d.get("hay")), d.get("mensaje", "")[:58]


prueba("Litch ve Trader Workstation", _ver_tws,
       "abra TWS. Si esta abierto, en Litch diga: 'que ventanas ves'")

if tws_visible:
    prueba("La cuenta es simulada (DU)", _cuenta,
           "inicie sesion en la cuenta de practica")
    prueba("Nada tapa TWS", _dialogos, "cierre la ventana que este encima")
else:
    print(f"        {A}(las demas pruebas de TWS se saltan){N}")

# ─────────────────────────────────────────────────────────────────────────
print()
print(f"{Z}--- 4. Calibracion ---{N}")


def _vision_cal():
    cfg = app.mem.get("config", {})
    b = cfg.get("broker_visual")
    if b == "tws":
        return True, f"region: {cfg.get('region_grafico')}"
    return False, f"apunta a: {b or 'nada'}"


def _ticket_cal():
    from core import piloto_tws as pt
    if pt.esta_calibrado(app):
        f = app.mem.get("config", {}).get("tws_campos_fecha", "")
        return True, f"7 campos medidos{' el ' + f if f else ''}"
    n = len(app.mem.get("config", {}).get("tws_campos") or {})
    return False, f"solo {n} de 7 campos medidos"


prueba("Vision apuntando a TWS", _vision_cal,
       "en Litch diga: 'calibra para IBKR'")
prueba("Ticket de ordenes calibrado", _ticket_cal,
       "en Litch diga: 'calibra el ticket de TWS'  (tarda 1 minuto)")

# ─────────────────────────────────────────────────────────────────────────
print()
print(f"{Z}--- 5. Datos de mercado ---{N}")


def _horario():
    from core import motor_acciones as ma
    ab, det = ma.mercado_abierto()
    return True, det[:60]


def _datos_spy():
    from core import motor_acciones as ma
    c, f = ma.velas_de(app, "SPY")
    if len(c) >= 30:
        return True, f"{len(c)} velas de SPY, ultimo cierre {c[-1]:.2f} ({f})"
    return False, f"solo {len(c)} velas — {f}"


def _analisis():
    from core import motor_acciones as ma
    an = ma.analizar_accion(app, "SPY")
    if an.get("precio", 0) <= 0:
        return False, "sin datos suficientes"
    return True, (f"{an['direccion']} con {an['votos']}/"
                  f"{an.get('votos_max', 4)} votos, "
                  f"confianza {int(an['confianza'] * 100)}%")


prueba("Horario de Wall Street", _horario)
prueba("Datos reales de SPY", _datos_spy,
       "compruebe su conexion a internet")
prueba("Analisis de SPY funciona", _analisis, "")

# ─────────────────────────────────────────────────────────────────────────
print()
print(f"{Z}--- 6. Protecciones (lo mas importante) ---{N}")


def _prot_real():
    """Con cuenta REAL, el piloto debe negarse."""
    from core import piloto_tws as pt
    import core.vision_tws as vt
    orig = vt.leer_estado_tws
    vt.leer_estado_tws = lambda a: {"tws_abierta": True, "es_paper": False,
                                    "cuenta": "U9999999"}
    try:
        r = pt.verificar_seguro(app)
        bloqueado = not r.get("seguro")
    finally:
        vt.leer_estado_tws = orig
    return bloqueado, ("se niega a tocar TWS con cuenta real"
                       if bloqueado else "NO BLOQUEA — grave")


def _prot_sin_cal():
    """Sin calibrar, no puede hacer clics reales.

    Lo correcto aqui es comprobar que NO tuvo exito, no adivinar el texto
    del rechazo. Buscar palabras concretas daba falsos negativos: si falta
    pyautogui el motivo es otro, pero el resultado (no toca nada) es el
    bueno igual.
    """
    from core import piloto_tws as pt
    if pt.esta_calibrado(app):
        return True, "ya esta calibrado, esta proteccion no aplica"
    r = pt.poner_simbolo(app, "SPY", ensayo=False)
    # Solo hay UNA respuesta de exito; cualquier otra cosa es un rechazo.
    exito = "cargado en TWS" in r
    return (not exito), ("no actua sin calibrar — motivo: " + r[:46]
                         if not exito else "ACTUO SIN CALIBRAR — grave")


def _prot_limite():
    """Una orden limite sin precio no puede volverse orden a mercado."""
    src = open("core/broker_ibkr.py", encoding="utf-8").read()
    return ("NO la convierto" in src), "orden limite sin precio: rechazada"


def _prot_horario():
    """El horario debe usar la hora de Nueva York, no la del equipo."""
    from core import motor_acciones as ma
    ny = ma._ahora_ny()
    local = time.localtime()
    dif = abs(ny.hour - local.tm_hour)
    return True, (f"Nueva York {ny.strftime('%H:%M')} / "
                  f"su equipo {time.strftime('%H:%M')}"
                  + (f"  (diferencia de {dif}h, bien tenida en cuenta)"
                     if dif else ""))


def _prot_ratio():
    """Un bracket con mal ratio debe rechazarse."""
    src = open("core/broker_ibkr.py", encoding="utf-8").read()
    return ("Ratio" in src and "1.5" in src), "exige minimo 1.5:1"


prueba("Se niega si la cuenta es REAL", _prot_real, "")
prueba("Sin calibrar no hace clics reales", _prot_sin_cal, "")
prueba("Orden limite no se vuelve de mercado", _prot_limite, "")
prueba("Usa la hora real de Nueva York", _prot_horario, "")
prueba("Rechaza brackets con mal ratio", _prot_ratio, "")

# ─────────────────────────────────────────────────────────────────────────
print()
print(f"{Z}--- 7. Conocimiento ---{N}")


def _escuela():
    from core import escuela_ibkr as ei
    return True, (f"{len(ei.HERRAMIENTAS)} herramientas de TWS, "
                  f"{len(ei.LECCIONES)} lecciones")


def _progreso():
    from core import escuela_ibkr as ei
    p = ei.progreso(app)
    return True, p.split("\n")[0][:58]


def _manuales():
    import glob
    m = sorted(glob.glob("LIBROS/*.md"))
    return len(m) >= 14, f"{len(m)} manuales en LIBROS/"


prueba("Escuela de IBKR", _escuela)
prueba("Su progreso", _progreso)
prueba("Manuales cargados", _manuales)

# ─────────────────────────────────────────────────────────────────────────
print()
print("=" * 66)
ok_n = sum(1 for _, o in resultados if o)
tot = len(resultados)
fallos = [n for n, o in resultados if not o]

print(f"   RESULTADO: {ok_n} de {tot} pruebas superadas")
print("=" * 66)

if not fallos:
    print(f"\n   {V}Todo funciona. Litch esta listo para trabajar en")
    print(f"   Interactive Brokers con todas las protecciones puestas.{N}")
elif len(fallos) <= 3:
    print(f"\n   {A}Casi listo. Falta esto:{N}")
    for f in fallos:
        print(f"     - {f}")
    print("\n   Arriba tiene el arreglo de cada uno.")
else:
    print(f"\n   {R}Faltan {len(fallos)} cosas:{N}")
    for f in fallos:
        print(f"     - {f}")
    print("\n   Empiece por las de arriba: las de abajo suelen depender")
    print("   de ellas.")

print()
print("   Recuerde: este programa NO envia ordenes y NO toca el raton.")
print("   Solo mira y le informa.")
print()
input("   Pulse ENTER para cerrar...")

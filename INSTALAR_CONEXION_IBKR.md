# Conexión de un clic con Interactive Brokers

Dos archivos nuevos, construidos según tu `PROMPT_Conexion_IBKR.md`:

- **`conexion_ibkr.py`** — la clase `ConexionIBKR`: conectar, verificar
  permisos, estado, desconectar y reconexión automática.
- **`bandeja.py`** — el icono en la bandeja del sistema, junto al reloj.

---

## Instalación (cinco minutos)

### 1. Instalar las dependencias

Abre una consola en la carpeta del proyecto y ejecuta:

```
C:\Users\G\AppData\Local\Python\bin\python.exe -m pip install ib_async pystray Pillow
```

Uso la ruta completa de tu Python porque es la que funciona en tu equipo —
la misma que usan `iniciar.bat` y `verificar.bat`.

### 2. Comprobar que quedó bien

```
C:\Users\G\AppData\Local\Python\bin\python.exe -c "import ib_async; print('ib_async', ib_async.__version__)"
```

### 3. Configurar TWS (una sola vez)

En TWS: **Archivo → Configuración global → API → Configuración**

- ✅ Activar clientes ActiveX y Socket
- Socket Port = **7497**
- ✅ **API solo lectura** ← déjalo marcado las primeras semanas
- IP de confianza: añade **127.0.0.1**
- Aplicar → Aceptar

### 4. Probar la conexión sola

Con TWS abierto en la cuenta simulada:

```
C:\Users\G\AppData\Local\Python\bin\python.exe conexion_ibkr.py
```

Debe salir tu cuenta `DUR328203`, la hora del servidor y si la API está en
solo lectura.

### 5. Lanzar el botón de bandeja

```
C:\Users\G\AppData\Local\Python\bin\python.exe bandeja.py
```

Aparece un icono junto al reloj. **Clic derecho** para el menú, **doble clic**
para conectar directamente.

---

## Los colores del icono

| Color | Significa |
|-------|-----------|
| **Gris** | Sin conectar |
| **Verde** | Conectado a la cuenta simulada ✓ |
| **Ámbar** | Conectado, pero no confirmo que sea simulada |
| **Rojo** | Cuenta REAL detectada, o error |

El icono se actualiza solo cada diez segundos. Si TWS reinicia de madrugada y
la conexión se cae, lo verás pasar de verde a gris y volver a verde cuando se
restablezca — sin tener que abrir nada.

---

## Cuatro correcciones al código de referencia

Tu documento traía un esqueleto muy bueno. Cambié cuatro cosas, y quiero que
sepas cuáles y por qué, para que puedas discutírmelas.

### 1. `startswith("D")` era demasiado ancho

El original detectaba la cuenta simulada con `cuenta.startswith("D")`. Funciona
con tu `DUR328203`, pero basta con que IBKR emita algún día un identificador
real que empiece por D para que **una cuenta con dinero pase por simulada**.

Ahora comprueba los prefijos concretos (`DU`, `DF`, `DI`), y **lo que no esté
en la lista se trata como NO simulado**. Es el lado seguro en el que
equivocarse.

### 2. La reconexión se llamaba a sí misma — esto colgaba el programa

Este es el importante. El original hacía:

```
disconnectedEvent → _al_desconectar() → conectar()
```

Si la reconexión falla, ib_async **vuelve a emitir el evento de desconexión**,
que vuelve a llamar a `conectar()`, que vuelve a fallar... Recursión infinita
dentro del bucle de eventos. El programa se cuelga o revienta la pila.

Y ocurriría justo cuando más falta hace: de madrugada, cuando TWS reinicia y
todavía no acepta conexiones.

Ahora hay tres protecciones: un cerrojo, una bandera de «ya estoy
reconectando», y la reconexión ocurre **en otro hilo**, no dentro del
manejador del evento. Además, si eres tú quien desconecta, no reconecta —
antes lo habría hecho.

### 3. Lo de «Read-Only» no se puede leer, hay que sondearlo

El prompt pedía comprobar si la API está en modo solo lectura. Tengo que ser
honesta: **IBKR no expone ese ajuste por la API.** No existe ningún campo que
lo diga.

La única forma de saberlo es intentar algo que ese modo impide. Uso
`whatIfOrder`, que pide a IBKR el cálculo de margen de una orden **hipotética,
sin enviarla nunca**. Es la sonda más inofensiva que existe.

Y si la sonda no es concluyente, Litch dice **«no lo sé»** en vez de afirmar
algo falso. Prefiero que dudes a que confíes en un dato inventado.

### 4. La bandeja se congelaba al conectar

`pystray` ejecuta las acciones del menú **en el hilo del icono**. Llamar a
`conectar()` ahí directamente congela la bandeja durante todo el intento —
hasta 10 segundos de espera, más los reintentos con backoff. El menú deja de
responder y parece que el programa se colgó.

Ahora cada acción lenta corre en su propio hilo, con un cerrojo para que
pulsar dos veces no lance dos conexiones a la vez.

---

## Recomendaciones de tu documento que suscribo

**IB Gateway en vez de TWS para trabajar desatendido.** Misma conexión, sin la
interfaz gráfica pesada. Puertos: 4002 simulada, 4001 real. Ya están definidos
en `conexion_ibkr.py`.

**Read-Only durante semanas.** Deja que Litch lea tu cuenta y posiciones sin
poder enviar órdenes. Verifica que todo lo que reporta es correcto **antes** de
darle permiso de ejecución. Un error de lectura es gratis; uno de ejecución
cuesta dinero.

**Un clientId por programa.** `bandeja.py` usa el 1 y el conector interno de
Litch usa el 10, así que no se pisan.

**Subir la memoria de TWS a 4096 MB.** Configuración → Memory Allocation.

---

## Una nota sobre tu Python 3.14

`ib_insync` (el antecesor) se rompe en Python 3.12+ porque exige un bucle de
eventos al importarse y ya no se crea solo. `ib_async` está mantenido y lo
maneja mejor, pero por si acaso `conexion_ibkr.py` **prepara el bucle antes de
importar**. Si aun así falla, dímelo con el mensaje exacto.

---

## Y lo que dice tu propio documento, que es lo más importante

> *Tener la conexión de un clic no te acerca a la rentabilidad, solo te da
> acceso.*

Suscribo cada palabra. La conexión es la parte fácil. Todo lo del `AGENTE.md`
sigue vigente: simulada primero, verificar con datos que hay un edge real, y
nada de dinero real hasta que la matemática lo confirme.

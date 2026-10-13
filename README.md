# Litch — Asistente personal de IA (IQ Option DEMO)

Litch es un asistente personal en **español e inglés**, con voz suave estilo Jarvis, que observa tu pantalla, aprende patrones de velas en el **modo demo de IQ Option**, busca información en internet, te pone recordatorios y cuida de tu ritmo de trabajo. Se vuelve más preciso con cada sesión.

## Instalación

1. Instala Python 3.10+ desde python.org (marca "Add Python to PATH").
2. Doble click en `instalar.bat`.
3. Doble click en `iniciar.bat` (o `python litch.py` desde VS Code).
4. Opcional: `crear_acceso_directo.bat` pone "Litch Trading-IA" en tu escritorio con su ícono.

## El orbe (núcleo visual estilo Jarvis)

En la parte superior del panel late el **orbe de Litch**: un globo de líneas verdes (meridianos y paralelos) con un núcleo central y tres electrones que orbitan en elipses inclinadas, como un átomo. Cuando Litch habla o escucha, el orbe se intensifica y pulsa al ritmo de su voz. Está hecho en `orbe.py` con tkinter puro, sin imágenes externas.

## Voz e idioma

Habla con voz cálida y serena en español (es-ES-Álvaro) e inglés (en-GB-Ryan, acento británico tipo Jarvis). Cambia de idioma al vuelo: dile «Litch, speak English» o «habla español». El micrófono reconoce ambos idiomas y la palabra de activación es «Litch».

## Trading en el demo

Calibra con **🎯 Calibrar** (esquinas del gráfico + botones verde/rojo + duración de vela). Usa **👁 Probar visión** para confirmar que ve bien las velas. Activa **Trading** y Litch leerá cada vela al cierre, memorizará patrones de 3 velas (cadena de Markov de orden 3) y te avisará por voz cuando un patrón tenga estadística suficiente.

## Llave maestra y modo autónomo

El **auto-click** (pulsar compra/venta automáticamente en el demo) y la **auto-mejora** (Litch ajusta sus propios umbrales según su precisión real) solo funcionan con el **modo autónomo** activo, y este se desbloquea con un código **TOTP de Google Authenticator**:

1. Pulsa **🔐 Llave** → "Generar llave y mostrar QR".
2. Escanéalo con Google Authenticator (+ → Escanear código QR).
3. Escribe el código de 6 dígitos para confirmar el registro.
4. Luego, para activar la autonomía, ingresa el código vigente.

Activar la autonomía exige el código; **desactivarla es siempre libre** (apagar el control nunca debe tener barreras). El secreto se guarda en `data/llave_maestra.json`.

## Respaldo en varias cuentas de nube tuyas

Con **☁ Nube** registras varios de tus correos y la carpeta que sincroniza cada app oficial (TeraBox, Drive, Dropbox). Litch copia su memoria a **todas** tus cuentas en cada respaldo y, cuando una se acerca a su límite, la marca como llena y sigue con las demás avisándote por voz que registres otra. Puedes respaldar manualmente o activar el respaldo automático cada 30 minutos. No se piden ni guardan contraseñas: solo la ruta de la carpeta que la app oficial ya mantiene sincronizada.

## Consejero proactivo

Litch te habla por iniciativa propia mientras trabajas (`consejero.py`): te recomienda calibrar si falta, te ofrece activar el análisis cuando está ocioso, detecta rachas de fallos («yo le recomendaría pausar…») o de aciertos («no aumente el ritmo por euforia…») y comparte consejos de disciplina con tono profesional. Sin ser pesado: máximo un consejo espontáneo cada ~9 minutos, y los eventos importantes tienen prioridad. Se controla con el botón **Consejos** del panel o por voz («Litch, aconséjame», «apaga los consejos»).

## Motor de inferencia bayesiana (la decisión maestra)

Sobre los tres motores, `inferencia.py` aplica la capa final de decisión: **teorema de Bayes** (cada método pesa según su precisión histórica real), **ley de los grandes números** (con poca muestra, Litch reduce su certeza automáticamente), **teorema del límite central** (intervalos de confianza del 95% sobre lo observado) y **ley de Littlewood** (no se deja impresionar por rachas que el azar produce normalmente). El auto-click solo dispara si hay consenso de métodos **y** la fusión bayesiana aprueba. Pregúntale: «Litch, análisis bayesiano».

## Dos motores de decisión

Además de la cadena de Markov de orden 3 (`analisis.py`), Litch tiene un **segundo motor estadístico** (`estadistica.py`) que combina Markov multi-orden, prueba chi-cuadrado y test de rachas, y vota entre los tres. El auto-click solo se ejecuta cuando **ambos motores coinciden** (decisión rápida y asertiva); si discrepan, Litch se abstiene. Pídele «Litch, ¿qué opinas del mercado?» para oír el consenso.

El **motor matemático** (`matematica.py`) detecta la regla exacta de una secuencia y predice el siguiente valor: sucesiones aritméticas y geométricas, regresión lineal (tendencia), autorregresión AR tipo ARIMA, cadenas de Markov y clustering k-means. Dile «Litch, predice la siguiente: 2 4 8 16».

## Cerebro propio: red neuronal + mente local

Litch tiene su **propia red neuronal** (`red_neuronal.py`), un perceptrón multicapa en NumPy que aprende SOLA en tu PC: se reentrena con retropropagación cada vez que junta velas nuevas y guarda sus pesos en `data/red_pesos.npz`. Es el **tercer voto** de las decisiones de trading, junto al Markov y al ensemble estadístico; el auto-click solo dispara con consenso de al menos 2 de los 3. Pregúntale «Litch, ¿qué predice la red neuronal?».

Para conversar con libertad sobre cualquier tema **sin nube ni API de pago**, Litch puede usar una **mente local** (`mente.py`) vía [Ollama](https://ollama.com): instálalo, descarga un modelo (`ollama pull llama3.2`) y, cuando las reglas no entienden algo, Litch razona con ese modelo corriendo 100% en tu equipo. Si Ollama no está, sigue con su cerebro de reglas. Todo es independiente y local.

## Control de mouse inteligente

El módulo `manos.py` mueve el puntero con trayectoria curva y aceleración humana (no robótica), hace clicks precisos devolviendo el cursor a su sitio, y puede intentar cerrar propagandas. El FAILSAFE de pyautogui (mover el ratón a una esquina) aborta cualquier acción al instante.

## Otras funciones

Búsqueda online sin servidor (Wikipedia/DuckDuckGo): «Litch, busca…» o «¿qué es…?». Clima: «clima en Bogotá». Recordatorios: «recuérdame X en 10 minutos». Reportes: «Litch, estado». Lotería: módulo **🎰** con frecuencias, calientes, fríos, atrasados y combinación sugerida. Cada 90 minutos te recomienda una pausa.

## Cómo aprende y dónde guarda

Todo (patrones, estadísticas, conversaciones, configuración) se guarda en `data/memoria.json`, así que cada sesión parte de lo aprendido. La memoria vive en tu computadora, bajo tu control.

## Advertencias importantes

Funciona únicamente con la cuenta **demo**. Las señales son estadística del pasado: **no garantizan resultados futuros**. Las opciones binarias tienen ventaja matemática para el bróker. En la lotería, cada sorteo es independiente. Litch nunca operará dinero real por ti. Litch es un programa de reglas y estadística: el "modo autónomo" amplía sus permisos de acción, no crea consciencia ni libre albedrío reales.

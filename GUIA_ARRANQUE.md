# Cómo arrancar Litch (paso a paso)

El error "Python was not found" significa una sola cosa: **falta instalar Python**. Litch está completo; solo necesita su motor. Sigue esto una vez y quedará funcionando para siempre.

## 1. Instalar Python (lo más importante)

1. Entra a https://www.python.org/downloads/
2. Pulsa el botón amarillo grande "Download Python 3.12".
3. Abre el instalador descargado.
4. En la PRIMERA pantalla, abajo, marca la casilla:
   - ☑ **Add python.exe to PATH**  ← sin esto, nada funciona
5. Pulsa "Install Now" y espera a que diga "Setup was successful".
6. **Cierra y vuelve a abrir** cualquier ventana del explorador o VS Code (para que reconozca Python).

## 2. Desactivar el "Python falso" de Windows (si hace falta)

Windows trae un atajo que abre la tienda en vez de Python. Si tras instalar te sigue fallando:

1. Configuración → Aplicaciones → Configuración avanzada de aplicaciones → **Alias de ejecución de aplicaciones**.
2. Apaga los dos interruptores que digan **python.exe** y **python3.exe**.

## 3. Diagnóstico automático

Si algo falla, haz doble clic en **diagnostico.bat**. Genera un archivo `diagnostico.txt`.
El resultado queda guardado para revisar el error exacto.

## 4. Instalar las librerías de Litch

Doble clic en **instalar.bat**. Tarda unos minutos (descarga voz, visión, red neuronal). Debe terminar con "Instalacion terminada".

## 5. Arrancar Litch

Doble clic en **iniciar.bat**. Debe aparecer el panel con el orbe verde y Litch saludándote con voz.

Si la ventana se cierra sola, abre `data/error_arranque.txt`: ahí queda escrito el error exacto.

## Arrancar desde VS Code (alternativa)

1. Abre VS Code → Archivo → Abrir carpeta → elige `Trading-IA IQ_Option`.
2. Si te pide instalar la extensión de Python, acéptala.
3. Abre `litch.py` y pulsa el botón ▶ (Run) arriba a la derecha, o abre la terminal (Ctrl+Ñ) y escribe:
   ```
   python litch.py
   ```
4. Si dice que no encuentra módulos, primero ejecuta en la terminal:
   ```
   python -m pip install -r requirements.txt
   ```

## El módulo de lotería y el teorema

Abre el panel de lotería (botón 🎰 o di "Litch, lotería"). Pega tus sorteos (uno por línea). Tienes dos botones:

- **📊 Frecuencias**: números calientes, fríos, atrasados y una combinación estadística.
- **🔬 Auditar teorema**: prueba científica de si el sorteo tiene sesgo real (chi-cuadrado), el "peso imaginario" de cada número, repeticiones consecutivas y un **backtest** que mide si un método supera al azar. Si tras muchos sorteos el sesgo es estable y el backtest gana, habría evidencia real; si no, el sorteo es justo. Las dos respuestas son resultados científicos válidos.

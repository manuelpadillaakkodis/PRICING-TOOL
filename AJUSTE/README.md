# 📘 Guía Completa: Herramienta de Ajuste de Coeficientes de Pricing

¡Bienvenido! Si es la primera vez que te enfrentas a esta herramienta, no te preocupes. Esta guía está diseñada para explicarte desde cero qué hace este programa, por qué es necesario y cómo utilizarlo paso a paso.

---

## 🧠 1. Conceptos Básicos: ¿Para qué sirve esta herramienta?

Imagina que tu empresa repara o fabrica piezas basándose en unos manuales llamados **Service Bulletins (SBs)**. 
Cada vez que se hace un SB, se cobra un "precio" o "peso" en puntos. 

Pero, ¿cómo sabemos cuánto cobrar por un SB en concreto? La respuesta está en **contar qué cosas hay dentro de ese SB**. A estas "cosas" las llamamos **Contadores (C01 al C15)**.
Por ejemplo:
* **C01** = Número de palabras.
* **C02** = Número de ilustraciones.
* **C04** = Número de tareas.
* **C11 a C15** = Temas de logística y repuestos.

El problema es que sabemos cuántas palabras o ilustraciones tiene un SB (porque lo leemos de su archivo informático XML o ZIP), y sabemos el **precio final** que nos han pagado por él, **¡pero no sabemos a cuánto se cobra cada palabra o cada ilustración!**

A ese valor desconocido (el "precio unitario" de cada contador) lo llamamos **Coeficiente**.

👉 **El objetivo de esta aplicación es jugar a los detectives:** Coge cientos de SBs, mira qué contadores tienen dentro, mira a qué precio total se han facturado, y **calcula mediante matemáticas cuál debe ser el coeficiente (precio unitario) perfecto para cada uno de los 15 contadores.**

---

## 🚀 2. Cómo Iniciar la Aplicación

Para abrir la interfaz gráfica del programa, abre una consola de comandos (Terminal o PowerShell), ve a la carpeta principal del proyecto (`CODIGO_PRICING`) y escribe:

```bash
python -m AJUSTE.app
```

> 💡 **Nota:** El programa ya no depende de cómo lo lances ni de cómo se llame la carpeta. Funciona igual de las tres formas: como módulo (`python -m AJUSTE.app`), como script suelto desde dentro de la carpeta (`python app.py`) o como ejecutable compilado (`app.exe`). Puedes renombrar la carpeta `AJUSTE` a lo que quieras (siempre que el nombre sea válido para Python: letras, números y guiones bajos, sin empezar por número).

Se abrirá una ventana con tres botones grandes. Cada botón es un "Flujo de Trabajo" distinto. Vamos a ver cuándo usar cada uno.

---

## 📊 3. Flujo 1: Cálculo Completo desde Cero (Primer Disparo)

**¿Cuándo usarlo?**
Cuando estás empezando un nuevo año o un nuevo gran contrato y quieres calcular todos los coeficientes desde la nada. No tienes referencias previas.

**¿Qué necesitas tener preparado?**
1. **Un Excel:** Con una lista de los SBs y los puntos/precio total que se ha fijado para cada uno. (Opcionalmente, puedes marcar con una 'X' en la tercera columna los SBs que son "prioritarios" o formato S1000D).
2. **Una Carpeta:** Que contenga los archivos físicos de esos SBs (los `.xml` antiguos o los `.zip` nuevos).

**¿Qué hace el programa paso a paso?**
1. **Filtra la basura:** Lee tu Excel y descarta todo lo que no sea el avión objetivo (A400M, 295, etc.) o versiones que no sean la "-00".
2. **Cuenta cosas:** Abre la carpeta, busca los archivos `.xml` o `.zip` y cuenta cuántas palabras, ilustraciones, tareas, etc., tiene cada uno.
3. **Calcula (La Magia):** Utiliza un algoritmo de **Mínimos Cuadrados e IRLS** (ver sección 6) para encontrar los precios perfectos.
4. **Agrupa (Parameter Tying):** El programa fuerza a que los temas de referencias cruzadas (C07, C08, C09) tengan siempre el mismo precio, o que toda la logística (C11, C13, C14, C15) valga lo mismo.
5. **Te da un Excel:** Al terminar, te ofrece guardar un reporte completísimo donde te dice: *"Oye, si usas estos coeficientes, vas a acertar el precio de este SB con un 99% de precisión"*.

---

## 🔄 4. Flujo 2: Reajuste con Jerarquía (Actualización Inteligente)

**¿Cuándo usarlo?**
Imagina que ya calculaste los precios hace 6 meses y a todo el mundo le pareció bien que una "Tarea (C04)" valiera más que una "Subtarea (C05)". 
Pero hoy te llega un nuevo Excel con 500 SBs nuevos y precios ligeramente distintos. Quieres recalcular los precios para encajar los datos nuevos, **PERO no quieres que se vuelva loco y cambie el orden de las cosas.** Quieres que la Tarea siga siendo más cara que la Subtarea.

**¿Qué necesitas tener preparado?**
1. **El Excel de Ajuste Previo:** El reporte que guardaste hace 6 meses.
2. **Un Nuevo Excel:** Una lista con los nuevos SBs y sus nuevos puntos.
3. **La Carpeta de XMLs.**

**¿Qué hace el programa paso a paso?**
1. **Recicla:** Solo lee de la carpeta los XML que sean totalmente nuevos (lo viejo lo saca del reporte anterior para ir más rápido).
2. **Aprende de la Historia:** Anota el ranking antiguo (ej. C04 era el rey y C01 el más barato).
3. **Calcula con cuidado (SLSQP):** Ajusta los precios usando un algoritmo llamado **SLSQP** (ver sección 6). Si al intentar cuadrar el precio intenta hacer que C01 valga más que C04, el algoritmo se lo prohíbe (es una barrera inquebrantable). 
4. **El dilema del equilibrista (El papel de Lambda $\lambda$):** 
   El programa tiene ahora dos misiones que chocan entre sí:
   * **Misión A:** Encontrar precios matemáticamente perfectos con la nueva factura.
   * **Misión B:** Mantener exactamente las proporciones de hace 6 meses (Si C04 valía el doble que C05, debe seguir valiendo el doble).

   Tú le dices al programa a qué misión darle más importancia usando el valor **Lambda ($\lambda$)**:
   * **$\lambda = 0$**: *"Olvida las proporciones antiguas"*. Solo mantendrá el orden (ranking) pero destruirá las proporciones para conseguir el mejor cálculo matemático posible.
   * **$\lambda = 1$**: Busca el equilibrio. *"Intenta cuadrar los precios nuevos, pero penalízate si te desvías mucho de las proporciones antiguas"*.
   * **$\lambda = 100$**: *"Las proporciones antiguas son sagradas"*. Las mantendrá intactas, aunque el cálculo final tenga más error respecto a tu nuevo Excel.

---

## ✏️ 5. Flujo 3: Ajuste Manual (El "Toque Humano")

**¿Cuándo usarlo?**
Las matemáticas a veces son frías. Imagina que el programa (Flujo 1) te dice que la "Configuración (C10)" debe valer 200 puntos. Se lo presentas a tu jefe y te dice: *"Me parece muy caro, bájamelo un 10% a mano. Pero claro, si lo bajas, tienes que subir otra cosa para compensar"*.

**¿Qué necesitas tener preparado?**
Solo necesitas el **Reporte Excel** que te dio el programa en el Flujo 1.

**¿Qué hace el programa paso a paso?**
1. Cargas el Excel en la ventana.
2. Le dices: *"Quiero reducir el contador C10 un 10%"*.
3. El programa te pregunta: *"Vale, ¿qué otros contadores quieres que suban para absorber esa pérdida?"*.
4. Tú marcas las casillas correspondientes (por ejemplo, C04 y C05).
5. El programa recalcula matemáticamente repartiendo el peso perdido de la forma más eficiente posible entre las casillas que marcaste.

---

## 🧮 6. Los Algoritmos Matemáticos (Explicados para mortales)

Por debajo del capó, la aplicación utiliza 3 "cerebros matemáticos" distintos dependiendo de lo que estés haciendo. Aquí te explicamos qué hace cada uno:

### 1. Mínimos Cuadrados (`lsq_linear`)
* **Dónde se usa:** Como base de casi todo (Primer disparo y Ajuste Manual).
* **Cómo funciona:** Imagina que tiras un montón de puntos en un papel e intentas dibujar una línea recta que pase lo más cerca posible de todos ellos a la vez. El algoritmo va probando precios (1€ la palabra, 2€ la palabra...) hasta que el "error" (la distancia entre tu línea y los puntos reales) es la mínima posible al sumar todo. 

### 2. IRLS (Mínimos Cuadrados Re-ponderados Iterativamente)
* **Dónde se usa:** En el "Primer Disparo" (Flujo 1) y opcionalmente en el Reajuste.
* **El Problema:** El algoritmo de Mínimos Cuadrados normal se vuelve **completamente loco** si en tu Excel hay un "Outlier" (por ejemplo, un SB que es rarísimo y en vez de 100 puntos le han puesto 5.000 puntos por error o por un tema político). Para intentar que la línea pase cerca de ese SB gigante de 5.000 puntos, va a destrozar los precios de los otros 400 SBs normales.
* **La Solución (IRLS):** Es el "detector de mentiras". El programa hace un primer cálculo. Luego mira los resultados y dice: *"Oye, el SB número 45 tiene un error gigante, huele raro"*. Entonces le **quita peso o importancia** a ese SB, y vuelve a calcular todo. Luego lo mira otra vez y le quita más peso. **Lo repite cientos de veces** hasta que los SBs raros quedan "silenciados" y los precios se ajustan perfectamente a los SBs normales.

### 3. SLSQP (Optimización Secuencial por Cuadrados Mínimos)
* **Dónde se usa:** Exclusivamente en el **Reajuste con Jerarquía** (Flujo 2).
* **El Problema:** Mínimos Cuadrados normal solo sabe buscar el menor error. Pero en el Reajuste, le hemos puesto reglas estrictas: *"Prohibido que C01 sea mayor que C04"*. Si Mínimos Cuadrados intenta hacer eso, se bloquea y falla.
* **La Solución (SLSQP):** Es como hacer un cubo de Rubik pero con unas esposas puestas. Este algoritmo intenta minimizar el error paso a paso (secuencialmente), pero antes de dar el siguiente paso mira a su alrededor para ver si va a chocar contra una de nuestras reglas (ej: va a romper la jerarquía o se va a saltar el castigo del valor $\lambda$). Si ve que va a chocar, cambia de dirección y busca un camino matemático alternativo. Es mucho más lento y complejo, pero garantiza que **jamás se romperá el orden de tus coeficientes**.

---

## 📈 7. ¿Cómo entender si el programa lo ha hecho bien? (Métricas)

Al final de cualquier cálculo, el programa te dará unos numeritos. Aquí tienes la traducción:

* **R² (R-Cuadrado):** Es la nota del examen de 0 a 1. 
  * Si sale `0.99`, significa que los coeficientes son perfectos y explican el 99% de los precios del Excel. 
  * Si baja de `0.70`, significa que los SBs tienen precios "a boleo" que no tienen relación matemática con lo que hay dentro de sus XMLs.
* **MAE (Error Absoluto Medio):** Si el MAE es 100, significa que, de media, usando estos coeficientes te vas a equivocar por unos 100 puntos en el precio de cada SB.
* **RMSE:** Parecido al MAE, pero castiga mucho más los fallos gigantes. Si el RMSE es mucho más grande que el MAE, significa que el programa acierta en casi todos los SBs, pero en unos poquitos está fallando por miles de puntos.
* **Bias (Sesgo):** 
  * Si es un número **positivo**, significa que en general los precios calculados tiran por lo alto.
  * Si es **negativo**, tiran por lo bajo.
  * ¡Lo ideal es que sea exactamente `0.0000`!

---

## 📁 8. Para los más técnicos: Organización del código

Si en el futuro alguien tiene que modificar el código, está organizado en la carpeta `AJUSTE/`:

* `app.py`: Interfaz visual principal.
* `carga_datos.py`: Lectura y filtrado de Excels.
* `procesamiento_xml.py`: Extracción de contadores desde archivos `.zip` y `.xml`.
* `optimizacion.py`: Ecuaciones matemáticas (IRLS, SLSQP, matrices).
* `metricas.py`: Evaluación (R², MAE) y generación de reportes Excel.
* `ajuste_manual.py`: Código exclusivo de la ventana del Flujo 3.
## 📦 9. Cómo convertir esta herramienta en un Ejecutable (.exe)

Si necesitas compartir esta aplicación con un compañero que no tiene Python instalado, puedes transformar todo el paquete `AJUSTE` en un único archivo ejecutable `.exe`. Como hemos aislado todas sus dependencias (incluyendo los lectores de XML) en su propia carpeta, el proceso será muy limpio.

**Instrucciones:**
1. Asegúrate de tener instalada la librería `pyinstaller` en tu entorno:
   ```bash
   pip install pyinstaller
   ```
2. Abre la consola de comandos en la carpeta padre (`CODIGO_PRICING`).
3. Ejecuta el siguiente comando para generar un ejecutable de un solo archivo, sin consola negra de fondo (modo ventana):
   ```bash
   pyinstaller --noconfirm --onedir --windowed --add-data "AJUSTE;AJUSTE/" "AJUSTE/app.py"
   ```
   *(Nota: Se usa `--onedir` con `--add-data` para asegurarse de que todos los subpaquetes y dependencias como Pandas o SciPy se empaquetan correctamente en la carpeta `dist/app`).*

4. Al terminar, ve a la nueva carpeta `dist/app/` que se habrá creado. Allí encontrarás tu `app.exe` listo para funcionar de manera totalmente independiente.

> 💡 **Nota:** Gracias a que todas las importaciones internas son relativas, el ejecutable resultante es autocontenido y no depende del nombre de la carpeta original. El parámetro `--add-data "AJUSTE;AJUSTE/"` simplemente empaqueta físicamente todos los módulos del paquete dentro del `.exe`. Si renombras la carpeta del proyecto, recuerda actualizar ese nombre tanto en `--add-data` como en la ruta del script final.

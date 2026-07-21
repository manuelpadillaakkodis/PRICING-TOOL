# Documentación del código MAIN — Herramienta de Pesado de Service Bulletins (S1000D)

Este documento explica en detalle el funcionamiento de la herramienta principal de *pricing*, cuyo punto de entrada es `main.py`. La herramienta **cuenta** los elementos relevantes de un Service Bulletin (SB) en formato XML/ZIP, **los multiplica por unos coeficientes** y devuelve un **peso total en puntos** (el "precio") del boletín, exportado a Excel.

> **Idea de una frase:** dado un conjunto de coeficientes ya conocidos (uno por contador, C01–C15), MAIN aplica esos coeficientes a los SB y calcula cuánto "pesa" cada uno. El módulo `AJUSTE` (documentado aparte) hace lo contrario: *calcula* esos coeficientes a partir de precios ya facturados.

---

## 1. Qué hace la herramienta

Un Service Bulletin se entrega como un fichero (XML antiguo, o ZIP que contiene varios XML en esquema S1000D). Dentro hay "cosas" que cuestan trabajo: palabras, ilustraciones, tablas, tareas, pasos, referencias, repuestos, herramientas, configuraciones… La herramienta agrupa todo eso en **15 contadores** llamados `C01` … `C15`.

El cálculo del peso es lineal y muy simple:

```
peso(SB) = Σ  (cantidad_de_Ci) × (coeficiente_de_Ci)      para i = 1..15
```

Lo verdaderamente complejo no es la multiplicación, sino **contar bien** cada `Ci` dentro del XML, y hacerlo de dos maneras distintas:

- **Modo NEW (recuento total):** se cuenta *todo* lo que hay en el SB. Se usa cuando el boletín es nuevo y se factura completo.
- **Modo REVISED / Dummy (recuento diferencial):** se comparan dos versiones del SB (original vs. revisado) y solo se cuenta **lo que se ha añadido o cambiado** respecto al original. Se usa cuando el boletín es una revisión y solo se factura el trabajo incremental.

---

## 2. Mapa de archivos del proyecto

No todos los ficheros forman parte del flujo de MAIN. Conviene distinguirlos:

| Archivo | Rol en MAIN | ¿Lo usa `main.py`? |
| :--- | :--- | :--- |
| **`main.py`** | Interfaz gráfica (GUI) y orquestación. Punto de entrada. | — (es el propio main) |
| **`funcionespesado.py`** | **Lógica de negocio.** Calcula los 15 contadores y los pesos; gestiona ZIPs y emparejamiento. | ✅ Sí (importa `revisiones_y_originales` y `comparar_zips`) |
| **`metodosrecuento.py`** | **Motor de conteo S1000D.** Clase con un método de extracción por contador. | ✅ Sí (indirectamente, vía `funcionespesado`) |
| `metodosrecuento_legacy.py` | Motor de conteo equivalente para el **esquema XML antiguo (AMSB)**. Misma interfaz de métodos. | ⚠️ No directamente en el flujo de MAIN actual (el motor activo es el S1000D) |
| `funciones_legacy.py` | Equivalente a `funcionespesado` para el esquema antiguo (`weightlegacyxml`). | ⚠️ No en MAIN; sí en el módulo AJUSTE |
| `extraerlistas.py` | Script **independiente**: consolida SBs y pesos del A400M leyendo varios Excel de una carpeta. | ❌ Utilidad suelta |
| `extraer_listas_lta.py` | Script **independiente**: igual que el anterior, pero para SBs de la familia LTA (295/235/212), con transformación de identificadores. | ❌ Utilidad suelta |
| `explicacion.md` | Documento de referencia con la lógica de cada contador. | 📄 Documentación |
| `equivalencias_xml_antiguo_nuevo.md` | Tabla de mapeo entre el esquema antiguo (AMSB) y el nuevo (S1000D). | 📄 Documentación |
| `main.spec` | Configuración de PyInstaller para compilar `main.py` a `.exe`. | 🛠️ Empaquetado |
| `AJUSTE/` | **Otra aplicación distinta** (cálculo de coeficientes). Ver su propio README. | 🚫 Independiente |

**Dependencias externas:** `pandas` (DataFrames y escritura de Excel), `tkinter` (GUI, viene con Python), y para el motor de conteo `xml.etree.ElementTree` (estándar), `re` y `tabulate`.

### Relación entre las tres piezas centrales

```
main.py  ──llama──▶  funcionespesado.py  ──instancia──▶  metodosrecuento.py
 (GUI)              (pesos y contadores)               (parseo del XML)
   │                                                          │
   │  coeficientes (de coeficients.csv / tabla)               │  un método por contador
   ▼                                                          ▼
 Excel de salida  ◀──────── dict {counters, weights, total_weight}
```

---

## 3. Cómo se ejecuta

Modo desarrollo:

```bash
python main.py
```

Modo compilado (tras `pyinstaller main.spec`): se genera un `main.exe`. Según `main.spec`, el ejecutable es de tipo **consola** (`console=True`) y de un solo fichero, con compresión UPX.

Al arrancar, `main.py` crea la ventana `App` (subclase de `tk.Tk`), de 850×550, titulada *"Application settings"*, con un **Notebook de dos pestañas**:

1. **"NEW/REVISED mode"** — pesado por carpeta (procesamiento por lotes).
2. **"Dummy"** — comparación de dos ZIP concretos (original vs. revisado).

---

## 4. La interfaz gráfica (`main.py`)

`main.py` es esencialmente **GUI + glue code**: no contiene lógica de conteo. Todo el peso del cálculo lo delega en `funcionespesado.py`. Sus responsabilidades son:

1. Recoger rutas y coeficientes desde la pantalla.
2. Llamar a la función de negocio adecuada.
3. Transformar el resultado en un DataFrame y escribir el Excel.
4. Avisar al usuario con `messagebox`.

### 4.1. La tabla de coeficientes (compartida por ambas pestañas)

El corazón de la configuración es una tabla (`ttk.Treeview`) con dos columnas: **Counter** y **Coefficient**. Se rellena de tres formas:

- **Carga automática al arrancar:** `_load_default_coefficients_csv()` busca un fichero llamado **`coeficients.csv`** junto al script (o junto al `.exe` si está compilado — lo resuelve `_get_default_coefficients_path()` usando `sys.frozen`). Si existe, lo carga; si no, deja la tabla vacía.
- **Import…** (`import_coefficients_from_csv`): abre un diálogo para elegir un CSV. El lector (`_load_coefficients_from_csv`) usa `csv.Sniffer` para autodetectar el delimitador, ignora una cabecera opcional (si la primera fila contiene "counter"/"coef") y vuelca cada par en la tabla.
- **Export…** (`export_to_csv`): guarda la tabla actual a CSV con delimitador `;`.

La fecha de validez de los coeficientes aparece como rótulo informativo: *"Coefficients (Validity date: 2017-11-20)"*.

El método clave que conecta la tabla con la lógica es:

```python
def obtener_coeficientes(self):
    # Devuelve {counter: coefficient} con lo que haya en la tabla, p.ej.
    # {'C01': '0.1', 'C02': '5', ...}
```

Este diccionario se pasa tal cual a las funciones de negocio. **Importante:** los valores son cadenas; la conversión a número (admitiendo coma decimal) la hace `funcionespesado` internamente.

### 4.2. Pestaña "NEW/REVISED mode" — pesado por carpeta

Construida en `_build_new_tab()`. Contiene:

- **"XML to weight route":** carpeta de entrada con los ZIP a pesar.
- **"Where to save the reports":** carpeta donde se escribirá el Excel.
- La tabla de coeficientes con sus botones Import/Export.
- Botón **"Weight XML files"** → dispara `on_weight_xml_files()`.

`on_weight_xml_files()` hace lo siguiente:

1. Valida que ambas carpetas existan.
2. Lee los coeficientes de la tabla (`obtener_coeficientes`).
3. Llama a **`revisiones_y_originales(xml_path, coeficientes)`** (en `funcionespesado.py`). Esta función recorre la carpeta, decide por sí misma qué SB es NEW y cuál es REVISED, y devuelve una lista de resultados.
4. Recorre los resultados y construye dos tablas (DataFrames):
   - **Resumen** — una fila por ZIP: Nombre, Modo (NEW/REVISED) y Total de puntos.
   - **Detalle** — una fila por (ZIP, módulo, contador): cantidad, coeficiente y peso, **incluyendo los contadores con valor 0** para que el informe sea completo. Tras cada ZIP añade una fila "TOTAL NUEVO" o "TOTAL DIFERENCIAS" y una fila vacía de separación.
5. Escribe ambas hojas en `reporte_pesos.xlsx` dentro de la carpeta de informes.

### 4.3. Pestaña "Dummy" — comparación de dos ZIP

Construida en `_build_revised_tab()`. Contiene dos selectores de fichero ZIP (**Original** y **Revised/Dummy**) y un botón **"Run comparison"** → `on_run_revised()`.

`on_run_revised()`:

1. Verifica que se han elegido los dos ZIP.
2. Pide al usuario dónde guardar el Excel (`reporte_comparacion.xlsx` por defecto).
3. Lee los coeficientes de la tabla.
4. Llama a **`comparar_zips(zip_original, zip_revised, coeficientes)`**.
5. Genera el mismo Excel de dos hojas (Resumen + Detalle) que el flujo por lotes, pero con un único SB.

> En la práctica, las dos pestañas escriben **exactamente el mismo formato de Excel**; cambia únicamente la fuente de datos (una carpeta completa frente a un par concreto de ZIP).

---

## 5. La lógica de negocio (`funcionespesado.py`)

Este módulo contiene cinco funciones públicas. Dos calculan contadores y pesos; tres gestionan ficheros y orquestación.

### 5.1. `weightnewxml(ruta_xml, coeficientes=None)` — recuento total

Recibe un XML (ruta o un objeto `BytesIO` en memoria) y devuelve un diccionario:

```python
{
  "counters":     {"C01": 1234, "C02": 12, ..., "C15": 3},
  "weights":      {"C01": {"count": 1234.0, "coefficient": 0.1, "weight": 123.4}, ...},
  "total_weight": 987.6
}
```

Internamente instancia `metodosrecuento(ruta_xml)` y, para cada contador, llama al método de extracción correspondiente y se queda con el tamaño/longitud del resultado. **Cada contador va envuelto en su propio `try/except`**: si la extracción falla (por ejemplo, el XML no tiene ese tipo de elemento), ese contador queda en `0` y el resto del cálculo continúa. Esto hace la herramienta muy tolerante a XML incompletos o con estructuras inesperadas.

El bloque final calcula los pesos: para cada `Ci`, convierte el coeficiente a `float` (reemplazando `,` por `.`), multiplica por la cantidad y acumula el total. Si `coeficientes is None`, devuelve solo los contadores (esto lo aprovecha `AJUSTE`, que únicamente necesita las cantidades).

### 5.2. `weightrevisedxml(ruta_xml_original, ruta_xml_nuevo, coeficientes=None)` — recuento diferencial

Misma firma de salida que la anterior, pero **comparando dos XML**. La regla general es: *contar solo lo que aparece en el nuevo y no estaba en el original*. La implementación varía según el contador (ver §6), pero apoya en tres ayudantes internos:

- `_to_float(valor)` — conversión robusta de coeficiente a número.
- `_safe_unique(valores)` — convierte una columna en un conjunto, descartando vacíos y `"N/A"`.
- `_diff_new_only(new, old)` — `len(set(new) - set(old))`, el patrón "solo lo nuevo" usado en la mayoría de contadores.

Para casos especiales emplea **multiconjuntos** (`collections.Counter`): por ejemplo, en C01 (palabras) y C03 (entradas de tabla) descuenta del nuevo las apariciones ya presentes en el original, de forma que solo cuenta los excedentes.

### 5.3. `get_xml_content(zip_path, keyword)` — extracción de un módulo del ZIP

Abre el ZIP **en memoria** (`zipfile` + `io.BytesIO`), busca los `.xml` cuyo nombre **contenga** `keyword` y devuelve el primero como flujo de bytes (no descomprime a disco). Es la pieza que permite trabajar sin extraer ficheros temporales.

> **Sobre los módulos `930` y `933`:** la herramienta solo procesa los XML de un SB cuyo nombre contiene `930` o `933`. Son los dos módulos de contenido de un Service Bulletin en S1000D (el descriptivo y el procedimental). Todo el conteo de un ZIP es la **suma** de lo extraído de esos dos módulos.

### 5.4. `comparar_zips(zip_old, zip_new, coeficientes=None)` — comparación de un par

Para cada uno de los módulos `930` y `933`:

- Si el módulo existe en **ambos** ZIP → llama a `weightrevisedxml` (diferencial).
- Si existe **solo en el nuevo** → llama a `weightnewxml` (se cuenta como contenido nuevo).

Acumula el peso total y devuelve:

```python
{"Zip": <nombre revisado>, "Type": "REVISED (vs <original>)", "Total Weight": <suma>, "Details": {930: ..., 933: ...}}
```

### 5.5. `revisiones_y_originales(folder_path, coeficientes=None)` — procesamiento por lotes

Es la función que invoca el botón "Weight XML files". Su trabajo es **decidir, dentro de una carpeta, qué SB es NEW y cuál es una REVISIÓN**, agrupando por nombre:

1. Lista todos los `.zip` de la carpeta.
2. Los agrupa con la expresión regular `^(.*)-(\d{2})\.zip$`: el nombre base es el grupo 1 y el **sufijo de dos dígitos** (`-00`, `-01`, …) es la "versión". Los ZIP sin ese patrón se tratan como grupo único.
3. Para cada grupo:
   - Si hay **dos o más** ficheros → es una **REVISIÓN**. Ordena por sufijo y toma los dos últimos: el **penúltimo como original** y el **último como revisado**, y llama a `comparar_zips`.
   - Si hay **uno solo** → es **NEW**. Pesa los módulos 930/933 con `weightnewxml`.
4. Devuelve la lista de resultados (un dict por SB) que `main.py` convierte en Excel.

> **Convención de nombres importante:** el emparejamiento automático depende del sufijo `-NN`. Por ejemplo, `A400M-53-7176-00.zip` y `A400M-53-7176-01.zip` se emparejan automáticamente (00 = original, 01 = revisado). Un fichero suelto sin pareja se pesa como NEW.

---

## 6. Los 15 contadores (C01–C15)

Esta es la parte funcionalmente más importante. Para cada contador hay **dos lógicas**: la del modo NEW (en `weightnewxml`) y la del modo REVISED (en `weightrevisedxml`). La tabla resume ambas; el detalle fino está en `explicacion.md`.

| Cont. | Concepto | Modo NEW (total) | Modo REVISED (diferencial) |
| :--- | :--- | :--- | :--- |
| **C01** | Palabras (texto plano) | Cuenta todas las palabras dentro de `<para>`, `<notePara>` y `<warningAndCautionPara>`. | "Bolsa de palabras" (multiconjunto): solo cuenta las palabras del nuevo que exceden las del original. Ignora mayúsculas (`casefold`). |
| **C02** | Gráficos | Nº de etiquetas `<graphic>`. | ICN (`infoEntityIdent`) presentes en el nuevo y no en el original; *fallback* al atributo `id`. |
| **C03** | Tablas | Suma de `<entry>` con texto. | Comparación por contenido: por título de tabla cuando existe, o contra todo el documento si no hay título. Diferencia de multiconjuntos. |
| **C04** | Task Sets | Títulos únicos de Task Set en `<techName>`, normalizando código `nnn-nnn-nnn` e `infoName`. | Cuenta el Task Set si **su código es nuevo Y su `infoName` no existe** en el original. |
| **C05** | Subtareas | Nombres únicos de subtareas (`Task …`), normalizando código y nombre. | Cuenta la subtarea si **su código y su nombre son nuevos** respecto al original. |
| **C06** | Pasos | Nº de nodos de la estructura jerárquica de `proceduralStep` por subtarea (rutas tipo `0/1/0`). | Por subtarea, cuenta las rutas de pasos presentes en el nuevo y no en el viejo (cubre subtareas nuevas y modificadas). |
| **C07** | Refs. internas | Nº de `<internalRef>`. | `internalRefId` nuevos vs. original. |
| **C08** | Refs. a Data Modules | Nº de `<dmRef>` en subtareas. | IDs de `dmRef` nuevos vs. original. |
| **C09** | Refs. externas | Nº de `<externalPubRef>` en subtareas. | IDs de `externalPubRef` nuevos vs. original. |
| **C10** | Configuraciones | Nº de filas de configuración (MSN × definición). | Tuplas `(nombre, rango MSN, texto)` nuevas vs. original. |
| **C11** | Repuestos | `sbIndividualSpare` únicos (por su colección completa de atributos). | Atributos de repuesto nuevos vs. original. |
| **C12** | Sets de repuestos | Nombres únicos de `sbSpareSet`, recortando los últimos 3 caracteres (sufijo de versión tipo `R00`). | Nombres de set normalizados nuevos vs. original. |
| **C13** | Repuestos retirados | `sbIndividualRemovedSpare` únicos por atributos. | Atributos nuevos vs. original. |
| **C14** | Herramientas | `sbIndividualSupportEquip` únicos por atributos. | Atributos nuevos vs. original. |
| **C15** | Consumibles | `sbIndividualSupply` únicos por atributos. | Atributos nuevos vs. original. |

**Criterios de normalización comunes:**

- Texto (C01): se compara en minúsculas (`casefold`).
- Títulos/nombres (C04, C05): se colapsan espacios y se separa el código numérico de la descripción.
- Sets (C12): se eliminan los **últimos 3 caracteres** del nombre para agrupar revisiones del mismo set.
- Repuestos/herramientas/consumibles (C11, C13–C15): la identidad de cada elemento es **la lista completa y ordenada de sus atributos XML**. Dos elementos con los mismos atributos se consideran el mismo.

---

## 7. El motor de conteo (`metodosrecuento.py`)

Es una clase, `metodosrecuento`, que envuelve el árbol XML (`ET.parse`) y expone **un método de extracción por contador**. Cada método recorre el árbol, ignora los *namespaces* (parte la etiqueta por `}` y se queda con el nombre local) y devuelve normalmente un `DataFrame` de `pandas` o una tupla `(lista, total)`. `funcionespesado` solo necesita el **número de filas** de cada resultado (o el `len` de un conjunto de atributos, según el contador).

Métodos principales y el contador que alimentan:

| Método | Alimenta |
| :--- | :--- |
| `extraer_palabras_texto_plano()` | C01 |
| `extraer_graphic_refs()` | C02 |
| `extraer_contenido_tablas_por_titulo()` | C03 |
| `contar_y_extraer_taskset_en_techname()` | C04 |
| `extraer_subtareas()` | C05 |
| `extraer_estructura_pasos_por_subtarea()` + `_traverse_step_structure()` | C06 |
| `matriz_referencias_internas()` | C07 |
| `extraer_dm_refs_con_subtareas()` | C08 |
| `extraer_externalPub_refs_con_subtareas()` | C09 |
| `extraer_configuraciones()` | C10 |
| `extraer_sbIndividualSpare_con_sbSpareSet()` | C11 y C12 |
| `extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet()` | C13 |
| `extraer_tools_con_sbSupportEquipSet()` | C14 |
| `extraer_supplies_con_sbSupplySet()` | C15 |

(Existen además métodos auxiliares como `extraer_tablas_con_entradas`, `extraer_diccionario_entradas_tabla`, `extraer_pasos_con_texto` y `matriz_subtareas_pasos`, que aportan vistas alternativas o intermedias.)

### Cómo se cuenta la estructura de pasos (C06), el caso más sutil

`extraer_estructura_pasos_por_subtarea()` identifica cada subtarea por su título (`Task <código> <nombre>`) y, mediante la función recursiva `_traverse_step_structure()`, genera un **conjunto de "rutas"** que codifican la jerarquía de pasos anidados. Una ruta como `"0/1/0"` significa "primer sub-paso del segundo paso del primer paso". Contar pasos es contar rutas; comparar versiones (modo REVISED) es restar conjuntos de rutas por subtarea. Esto permite detectar pasos añadidos sin depender de IDs.

---

## 8. Esquema antiguo (Legacy / AMSB) vs. nuevo (S1000D)

El proyecto conserva un **motor paralelo** para el esquema XML antiguo (`amsb`):

- `metodosrecuento_legacy.py` → clase `metodosrecuento_legacy`, con **la misma interfaz de métodos** que el motor S1000D, pero leyendo las etiquetas del esquema viejo (por ejemplo, gráficos = `<sheet>` dentro de `<figure>`, pasos = `<listitem>`, etc.).
- `funciones_legacy.py` → función `weightlegacyxml`, gemela de `weightnewxml`.

El mapeo exacto entre ambos esquemas está documentado en `equivalencias_xml_antiguo_nuevo.md`. En el flujo actual de `main.py`, el motor activo es el **S1000D** (los SB nuevos llegan como ZIP con módulos 930/933). El motor legacy se mantiene por compatibilidad y es el que aprovecha el módulo `AJUSTE` para procesar SB antiguos en formato `.xml`.

---

## 9. Formato del Excel de salida

Ambas pestañas producen un Excel con **dos hojas**:

**Hoja "Resumen"** — una fila por SB:

| Nombre | Modo | Total de puntos |
| :--- | :--- | :--- |
| `A400M-53-7176-01.zip` | REVISED (vs …-00) | 412.5 |

**Hoja "Detalle"** — una fila por (SB, módulo, contador), con todos los contadores aunque valgan 0, y filas de total/separación:

| Archivo ZIP | Tipo | Módulo | Contador | Cantidad | Coeficiente | Peso |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `…-01.zip` | REVISED | 930 | C01 | 240 | 0.1 | 24.0 |
| `…-01.zip` | REVISED | 930 | C02 | 3 | 5 | 15.0 |
| … | | | | | | |
| `…-01.zip` | REVISED | **TOTAL DIFERENCIAS** | | | | 412.5 |

El nombre del fichero es `reporte_pesos.xlsx` (lotes) o el que elija el usuario, por defecto `reporte_comparacion.xlsx` (Dummy).

---

## 10. Scripts auxiliares (no forman parte del flujo principal)

- **`extraerlistas.py`** — herramienta de consola con un pequeño diálogo de carpeta. Recorre varios Excel y extrae los identificadores de SB del A400M (regex `A400M[\w\d-]*\d`) junto con su peso, consolidándolos en un único fichero. Sirve para **preparar la lista de entrada** que luego consume el módulo AJUSTE.
- **`extraer_listas_lta.py`** — equivalente para la familia LTA (aviones 295/235/212). Además **transforma los identificadores** al formato requerido (p. ej. `SB-295-71-0007-01-Sp` → `SB295-71-0007-01-E`) y filtra por códigos de avión permitidos y por idioma (sufijos Sp→E, En→I, Fr→F).

Son utilidades independientes: no las importa `main.py` ni intervienen en el pesado.

---

## 11. Empaquetado y rutas

- **`main.spec`** compila `main.py` con PyInstaller a un ejecutable de consola, un solo fichero, con UPX activado.
- La resolución de `coeficients.csv` distingue entre ejecución normal y compilada mediante `getattr(sys, "frozen", False)`: en `.exe` busca el CSV junto al ejecutable; en desarrollo, junto al `.py`. Esto permite **distribuir el `.exe` con su CSV de coeficientes al lado** y que se cargue automáticamente.

---

## 12. Notas, supuestos y puntos a vigilar

- **Tolerancia a errores:** cada contador está aislado en `try/except`; un XML problemático no rompe el informe, simplemente deja contadores a 0. La contrapartida es que **un error silencioso puede pasar desapercibido** (aparece como un 0 legítimo).
- **Dependencia del nombre de fichero:** el emparejamiento NEW/REVISED por lotes se basa en el sufijo `-NN`. Nombres que no sigan ese patrón se tratan como NEW aunque tengan pareja conceptual.
- **Solo módulos 930/933:** el resto de XML dentro del ZIP se ignoran a efectos de conteo.
- **Coeficientes como texto:** se aceptan con coma o punto decimal; un valor no numérico se interpreta como `0`.
- **Validez temporal:** los coeficientes tienen fecha de validez (rótulo "2017-11-20"); el cálculo es solo tan bueno como los coeficientes cargados. De ahí la existencia del módulo `AJUSTE`, que los recalibra cuando cambian los datos de facturación.

---

### Resumen ejecutivo

`main.py` es la **capa de presentación**; `funcionespesado.py` la **lógica de pesado** (contadores NEW y REVISED, gestión de ZIP y emparejamiento); `metodosrecuento.py` el **parser** que sabe leer cada elemento del S1000D. El usuario carga unos coeficientes, elige una carpeta o un par de ZIP, pulsa un botón y obtiene un Excel con el peso (precio en puntos) de cada Service Bulletin, desglosado contador a contador.

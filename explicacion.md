# Explicación de Contadores (S1000D)

Este documento detalla la lógica aplicada para cada uno de los 15 contadores (C01-C15) en la herramienta de pricing, diferenciando entre el modo **Nuevo** (recuento total) y el modo **Revisado** (comparación diferencial).

## Lógica de Recuento por Contador

### C01 - Palabras (Texto Plano)
*   **Modo Nuevo:** Se realiza un conteo total de todas las palabras contenidas dentro de las etiquetas `<para>`, `<notePara>` y `<warningAndCautionPara>`.
*   **Modo Revisado:** Se utiliza una comparación de "bolsa de palabras" (multiset). El sistema cuenta la frecuencia de cada palabra en el documento original y en el nuevo. Se contabilizan como nuevas aquellas palabras del documento nuevo que exceden la cantidad de veces que aparecían en el original (o que no aparecían). Esto permite detectar texto añadido incluso si se ha movido de lugar.

### C02 - Gráficos
*   **Modo Nuevo:** Se cuenta el número total de etiquetas `<graphic>` presentes en el archivo.
*   **Modo Revisado:** Se comparan los conjuntos de identificadores de entidad de información (`infoEntityIdent` o ICN). Se contabilizan aquellos gráficos cuyo ICN aparece en el documento nuevo pero no existía en el original. Si no disponen de ICN, se utiliza el atributo `id` como criterio de respaldo.

### C03 - Tablas
*   **Modo Nuevo:** Se suman todas las entradas (`<entry>`) que contienen texto dentro de todas las tablas del documento.
*   **Modo Revisado:** La comparación se basa en el contenido de texto de las entradas, no en sus IDs.
    *   Para tablas que tienen título en el nuevo XML, se busca una tabla con el mismo título en el original y se comparan los textos de sus entradas. Se cuentan las entradas cuyo contenido es nuevo o adicional.
    *   Para tablas sin título, se busca si el texto de sus entradas existe en cualquier parte del documento original. Se cuentan aquellas entradas cuyo texto no aparece en el original.

### C04 - Task Sets
*   **Modo Nuevo:** Se cuenta el número de títulos únicos de Task Sets encontrados en la etiqueta `<techName>`. Los títulos se normalizan (se eliminan espacios sobrantes) y se ignora el código numérico.
*   **Modo Revisado:** Se calcula la diferencia de conjuntos de los títulos normalizados. Se contabiliza un Task Set si su título (normalizado) aparece en el nuevo documento pero no estaba presente en el original.REVISAR--> lo que vamos a hacer es que <techName>Task set XX7XXX-831-801-001</techName>
<infoName>Modification</infoName> : coincida el codigo 831-801-001 o el aplicable y ademas coincida el infoname

### C05 - Subtareas
*   **Modo Nuevo:** Se cuenta el número de nombres únicos de subtareas (identificadas por `Task ...` en el título). Al igual que en C04, se normaliza el nombre y se ignora el código.
*   **Modo Revisado:** Se calcula la diferencia de conjuntos de los nombres normalizados. Una subtarea cuenta si su nombre aparece en el nuevo documento y no en el antiguo.

### C06 - Pasos
*   **Modo Nuevo:** Se analiza la estructura jerárquica de pasos (`proceduralStep`) dentro de cada subtarea. Se cuenta el número total de "rutas" o nodos estructurales (pasos y sub-pasos) existentes.
*   **Modo Revisado:** Se realiza una comparación estructural por subtarea.
    *   Si una subtarea es nueva (su nombre no existía), se cuentan todos sus pasos.
    *   Si la subtarea ya existía, se compara la estructura de sus pasos con la versión anterior y solo se contabilizan las rutas de pasos que se han añadido en la nueva versión.

### C07 - Referencias Internas
*   **Modo Nuevo:** Se cuenta el total de etiquetas `<internalRef>`.
*   **Modo Revisado:** Se comparan los conjuntos de `internalRefId`. Se contabilizan aquellas referencias cuyo ID aparece en el nuevo documento pero no en el original.

### C08 - Referencias a Módulos de Datos (DM)
*   **Modo Nuevo:** Se cuenta el total de etiquetas `<dmRef>` encontradas dentro de las subtareas.
*   **Modo Revisado:** Se comparan los conjuntos de IDs de las referencias. Se cuenta si el ID de la referencia aparece en el nuevo documento y no en el viejo.

### C09 - Referencias Externas
*   **Modo Nuevo:** Se cuenta el total de etiquetas `<externalPubRef>` dentro de las subtareas.
*   **Modo Revisado:** Al igual que con C08, se comparan los conjuntos de IDs y se cuentan las referencias nuevas.

### C10 - Configuraciones
*   **Modo Nuevo:** Se cuenta el número total de filas de configuración, formadas por la combinación de la tabla de MSN y la definición de configuración.
*   **Modo Revisado:** Se comparan las filas completas como tuplas de valores (nombre, rango, texto de definición). Se contabiliza una configuración si esa combinación exacta de datos aparece en el nuevo documento y no en el original.

### C11 - Repuestos (Spares)
*   **Modo Nuevo:** Se cuentan los elementos `sbIndividualSpare` únicos. La unicidad se determina por la colección completa de todos sus atributos XML.
*   **Modo Revisado:** Se calcula la diferencia de conjuntos de atributos. Se cuenta un repuesto si aparece uno con esa combinación exacta de atributos en el nuevo documento que no existía en el original.

### C12 - Sets de Repuestos
*   **Modo Nuevo:** Se cuenta el número de nombres únicos de `sbSpareSet`. Los nombres se normalizan eliminando espacios y recortando los últimos 3 caracteres (para ignorar sufijos de versión como "R00").
*   **Modo Revisado:** Se comparan los conjuntos de nombres normalizados. Se cuenta si un nombre de set (normalizado) es nuevo.

### C13 - Repuestos Retirados
*   **Modo Nuevo:** Se cuentan los elementos `sbIndividualRemovedSpare` únicos, basándose en todos sus atributos.
*   **Modo Revisado:** Diferencia de conjuntos de atributos, similar a C11.

### C14 - Herramientas
*   **Modo Nuevo:** Se cuentan los elementos `sbIndividualSupportEquip` únicos, basándose en todos sus atributos.
*   **Modo Revisado:** Diferencia de conjuntos de atributos, similar a C11.

### C15 - Consumibles
*   **Modo Nuevo:** Se cuentan los elementos `sbIndividualSupply` únicos, basándose en todos sus atributos.
*   **Modo Revisado:** Diferencia de conjuntos de atributos, similar a C11.

## Detalles de Normalización General

*   **Texto (C01):** Se ignoran mayúsculas y minúsculas (`casefold`) para la comparación.
*   **Títulos y Nombres (C04, C05):** Se eliminan espacios en blanco sobrantes al inicio, final y entre palabras. Se ignoran los códigos numéricos asociados, centrando la comparación en la descripción textual.
*   **Sets (C12):** Se aplica un recorte específico eliminando los últimos 3 caracteres del nombre para agrupar revisiones del mismo set.
*   **Atributos (C11, C13, C14, C15):** La identidad de estos elementos se define estrictamente por la lista ordenada de todos sus atributos y valores en el XML.

 Vamos a redefinir la jerarquia de importancia en funcion del grupo de cosas que se cuenten y del numero de veces que aparezca. Este sera el orde de menor a mayor

1er grupo: Palabras: habra muchas por lo que su coeficiente debera ser pequeño aunque > 0,05 
2º Referencias: son las segundas que mas aparecen por lo que su peso sera el segundo mas pequeño e igual (diferencia menor al 5%) para todos los tipos de referencias 
3º Pasos: aparecen bastante por lo que seran el 3º mas pequeño 
4º Tabla: peso similar al de los pasos (pero no tiene porque ser igual)
5º Respuestos: cada repuesto individual sea del tipo que sea: cosnumibles. tools, desmontado, nuevo... 
6º Kits (spareset): la creación de un kit: aunque aparece poco la creación de un kit conlleva un trabajo que en parte ya esta recogido por los repuestos, por lo que su peso sera similar al de los pasos--> Aqui no los contamos
7º Ilus: llevan un trabajo bastante grande 
8º Subtareas y tareas: son el 5 que menoss aparecen por lo que tendran un peso significativo. Siendo el peso de las subtareas menor que el de las tareas (max diferencia 9º 9ºConfiguracion: cada configuracion practicamene duplica el trabajo del boletin por lo que su peso sera muy grande
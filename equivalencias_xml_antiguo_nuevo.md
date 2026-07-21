# Equivalencias de Contadores: XML Antiguo (AMSB) vs Nuevo (S1000D)

Este documento define el mapeo entre los contadores del nuevo sistema de pricing (basado en S1000D) y las etiquetas del esquema XML antiguo (`amsb`), utilizando como referencia el archivo `XML SB A400M99-7096-01.xml`.

## Tabla de Mapeo

| Contador Nuevo (S1000D) | Descripción | Etiqueta/Lógica en XML Antiguo (`amsb`) | XPath / Detalles |
| :--- | :--- | :--- | :--- |
| **C01** | **Palabras (Texto)** | `<para>` | Contar palabras dentro de todos los elementos `<para>`. Estos aparecen en descripciones, razones, subtareas, notas, warnings y cautions. |
| **C02** | **Gráficos** | `<sheet>` | Contar elementos `<sheet>` dentro de `<figures>/<figure>`. Cada sheet es una lámina de ilustración. |
| **C03** | **Tablas** | `<entry>` (en `<table>`) | Contar elementos `<entry>` dentro de tablas genéricas `<table>` que aparezcan en el contenido (ej. dentro de `<subtask>`). No confundir con `tech_tables`. |
| **C04** | **Task Sets** | `<task>` | Cada elemento `<task>` en el contenido equivale a un Task Set. <br> `//content/procedure_content/task` |
| **C05** | **Subtareas** | `<subtask>` | Cada elemento `<subtask>` dentro de una tarea. <br> `//task/topic/configuration_ref/subtask` |
| **C06** | **Pasos** | `<listitem>` | Cada elemento `<listitem>` dentro de las listas de instrucciones de una subtarea. <br> `//subtask/list/listitem` |
| **C07** | **Ref. Internas** | `<ref_figure>`, `<ref_part>`, `<ref_tool>`, `<ref_cons>` | Referencias en el texto apuntando a figuras o elementos de tablas técnicas (partes, herramientas, consumibles). |
| **C08** | **Ref. a DM** | `<ref_document>` (DMC) | Referencias en el texto (`<subtask>`) cuyo `ref_id` apunta a una entrada en `reference_document_tables` que contiene un código DMC (ej. `DMC-AJ...`). |
| **C09** | **Ref. Externas** | `<ref_document>` (Otros) | Referencias en el texto (`<subtask>`) cuyo `ref_id` apunta a una entrada en `reference_document_tables` que **NO** es un DMC (ej. SB, SIL, CMM). |
| **C10** | **Configuraciones** | `<configuration>` | Elementos `<configuration>` definidos en la sección de configuraciones. <br> `//configurations/configuration` |
| **C11** | **Repuestos** | `<component>` (Kits) | Componentes listados dentro de `<kits>/<kit>/<components>`. |
| **C12** | **Sets Repuestos** | `<kit>` | Elementos `<kit>` definidos en `<tech_tables>/<kits>`. |
| **C13** | **Rep. Retirados** | `<component>` (Removed) | Componentes dentro de `<parts_removed_by_operator>`. |
| **C14** | **Herramientas** | `<tool>` | Herramientas en `<special_tools>` y `<standard_tools>`. |
| **C15** | **Consumibles** | `<consumable>` | Elementos en `<consumable_materials>`. |

## Análisis Detallado

### 1. Estructura de Tareas (C04, C05, C06)
En el esquema `amsb`, la jerarquía es explícita:
*   **C04 (Task Set):** Se mapea directamente a `<task>`. Ejemplo: `<task number="997096-831-801-001" ...>`.
*   **C05 (Subtarea):** Se mapea a `<subtask>`. Ejemplo: `<subtask number="997096-910-001-001">`.
*   **C06 (Pasos):** Se mapea a los ítems de lista `<listitem>` dentro de la subtarea. A diferencia de S1000D que usa `proceduralStep`, `amsb` usa listas anidadas. Se deben contar todos los `listitem` que representen acciones.

### 2. Referencias Documentales (C08 vs C09)
En `amsb`, las referencias documentales en el texto usan la etiqueta `<ref_document ref_id="ID">`. Para distinguir entre C08 (DM) y C09 (Externa):
1.  Obtener el `ref_id` de la etiqueta `<ref_document>`.
2.  Buscar ese ID en la sección `<tech_tables>/<references_document_tables>`.
3.  Leer el contenido de `<doc_reference>` asociado.
    *   Si contiene "DMC-", es **C08**.
    *   En caso contrario (ej. "A400M...", "SIL-...", "PMC-..."), es **C09**.

### 3. Materiales y Recursos (C11 - C15)
El XML antiguo centraliza estos recursos en `<tech_tables>`, lo que facilita la extracción directa:
*   **C11/C12 (Kits):** Iterar sobre `<kits>/configuration_ref/kit`.
*   **C13 (Removed):** Iterar sobre `<parts_removed_by_operator>/configuration_ref/components/component`.
*   **C14 (Tools):** Iterar sobre `<special_tools>` y `<standard_tools>`.
*   **C15 (Consumibles):** Iterar sobre `<consumable_materials>/configuration_ref/consumable_material_list/consumable`.

### 4. Texto Plano (C01)
Se deben extraer textos de:
*   `<para>`: Párrafos estándar.
*   `<notePara>`: Párrafos en notas (si existen en la versión específica de `amsb`, a veces son `<nota><para>`).
*   `<warningAndCautionPara>`: (Similar, a veces `<warning><para>`).
*   **Estrategia:** Buscar recursivamente todos los tags `<para>` en el documento, ya que en `amsb` casi todo el texto narrativo reside ahí.
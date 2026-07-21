import xml.etree.ElementTree as ET
import re
import pandas as pd
from tabulate import tabulate
import tkinter as tk
from tkinter import ttk
import warnings
import re
####AMBOS######
class metodosrecuento:
    def __init__(self,ruta_xml):
        self.ruta_xml = ruta_xml
        self.tree = ET.parse(self.ruta_xml)
        self.mode = self._detect_mode()
        
        if self.mode == "error_english":
            self.patron_c04 = re.compile(r"task\s+(.*)", re.IGNORECASE)
            self.patron_c05 = re.compile(r"\s*(?:Subtask)\s+([\w-]+)\s+(.+?)\s*$", re.IGNORECASE)
        else:
            self.patron_c04 = re.compile(r"(?:task\s*set|tarea)\s+(.*)", re.IGNORECASE)
            self.patron_c05 = re.compile(r"\s*(?:Task|Subtarea)\s+([\w-]+)\s+(.+?)\s*$", re.IGNORECASE)

    def _detect_mode(self):
        root = self.tree.getroot()
        has_subtask_title = False
        for elem in root.iter():
            tag = elem.tag.split('}', 1)[-1]
            if tag == "proceduralStep":
                for child in elem:
                    ctag = child.tag.split('}', 1)[-1]
                    if ctag == "title" and child.text:
                        if re.search(r'\bSubtask\b', child.text, re.IGNORECASE):
                            has_subtask_title = True
                            break
                if has_subtask_title:
                    break
        
        if has_subtask_title:
            return "error_english"
            
        tech_name_text = ""
        for elem in root.iter():
            tag = elem.tag.split('}', 1)[-1]
            if tag == "techName" and elem.text:
                tech_name_text = elem.text.strip()
                break
        
        if tech_name_text:
            if re.search(r'\bTask\b', tech_name_text, re.IGNORECASE) and not re.search(r'\bset\b', tech_name_text, re.IGNORECASE):
                return "error_english"

        return "normal"

    def extraer_palabras_texto_plano(self):
        """
        Devuelve (lista_palabras, numero_de_palabras) con todas las palabras
        de texto plano dentro de <para>, <notePara>/<notepara> y <warningAndCautionPara>.
        """
        root = self.tree.getroot()

        # Nombres de etiqueta sin espacios de nombres (namespaces)
        etiquetas_objetivo = {"para", "notePara", "warningAndCautionPara"}

        palabras = []

        for elem in root.iter():
            # Quitar namespace si lo hay, p.ej. {ns}para -> para
            tag_sin_ns = elem.tag.split('}', 1)[-1]

            if tag_sin_ns in etiquetas_objetivo:
                # Texto directo antes del primer hijo
                if elem.text:
                    for p in re.findall(r"\w[\w'-]*", elem.text):
                        palabras.append(p)

                # Texto "tail" después de cada hijo dentro del mismo elemento
                for hijo in elem:
                    if hijo.tail:
                        for p in re.findall(r"\w[\w'-]*", hijo.tail):
                            palabras.append(p)

        return palabras, len(palabras)

    def extraer_graphic_refs(self):
        """
        Cuenta todas las ocurrencias de <graphic> y devuelve un DataFrame con:

        - graphic_id
        - infoEntityIdent
        - titulo  (atributo *title o texto title="..." en la etiqueta)
        """
        root = self.tree.getroot()

        filas = []

        for elem in root.iter():
            tag = elem.tag.split('}', 1)[-1]
            if tag != "graphic":
                continue

            graphic_id = elem.get("id") or "N/A"
            info_entity = elem.get("infoEntityIdent") or "N/A"

            # 1) intentar título en un atributo (*:title, {ns}title, title, etc.)
            titulo = None
            for k, v in elem.attrib.items():
                attr_name = k.split('}', 1)[-1].split(':')[-1]
                if attr_name == "title" and v and str(v).strip():
                    titulo = str(v).strip()
                    break

            # 2) si no hay atributo, buscar texto title="..." en la etiqueta <graphic>
            if titulo is None:
                raw = ET.tostring(elem, encoding="unicode")
                m = re.search(r'title\s*=\s*"([^"]+)"', raw)
                if m:
                    titulo = m.group(1).strip()

            if not titulo:
                titulo = "N/A"

            filas.append({
                "graphic_id": graphic_id,
                "infoEntityIdent": info_entity,
                "titulo": titulo,
            })

        return pd.DataFrame(filas)


    def extraer_tablas_con_entradas(self):
        """
        Cuenta las tablas del XML y devuelve un DataFrame con columnas:
        - table_id
        - tabstyle
        - titulo
        - num_entradas
        """
        root = self.tree.getroot()

        filas = []

        def clean(v):
            v = "" if v is None else str(v).strip()
            return v if v else "N/A"

        for elem in root.iter():
            tag = elem.tag.split('}', 1)[-1]
            if tag != "table":
                continue

            table_id = clean(elem.get("id"))
            tabstyle = clean(elem.get("tabstyle"))

            # título directo hijo de <table>
            titulo = "N/A"
            for child in elem:
                ctag = child.tag.split('}', 1)[-1]
                if ctag == "title" and child.text:
                    titulo = clean(child.text)
                    break

            # nº de <entry> dentro de la tabla
            num_entradas = sum(
                1
                for sub in elem.iter()
                if sub.tag.split('}', 1)[-1] == "entry"
            )

            filas.append({
                "table_id": table_id,
                "tabstyle": tabstyle,
                "titulo": titulo,
                "num_entradas": num_entradas,
            })

        return pd.DataFrame(filas)

    def extraer_diccionario_entradas_tabla(self):
        """
        Devuelve dict {entry_id: texto_normalizado}.
        Si el entry no tiene id, se crea una clave estable por posición.
        """
        root = self.tree.getroot()
        entries = {}
        auto_idx = 0
        for elem in root.iter():
            tag = elem.tag.split("}", 1)[-1]
            if tag != "entry":
                continue

            entry_id = elem.get("id")
            if not entry_id:
                auto_idx += 1
                entry_id = f"__no_id__#{auto_idx}"

            text = " ".join(t.strip() for t in elem.itertext() if t and t.strip())
            text = " ".join(text.split())
            entries[str(entry_id)] = text
        return entries

    def extraer_contenido_tablas_por_titulo(self):
        """
        Devuelve:
        1. dict {titulo: [lista_textos]} para tablas con título.
        2. list [lista_textos] para tablas SIN título.
        3. list [lista_textos] con TODAS las entradas del documento (para búsqueda global).
        """
        root = self.tree.getroot()
        
        tablas_con_titulo = {}
        entradas_sin_titulo = []
        todas_las_entradas = []

        for table in root.iter():
            tag = table.tag.split('}', 1)[-1]
            if tag != "table":
                continue

            # Buscar título (hijo directo o anidado)
            titulo = None
            for child in table:
                ctag = child.tag.split('}', 1)[-1]
                if ctag == "title" and child.text:
                    titulo = " ".join(child.text.split())
                    break
            
            # Extraer entradas de esta tabla
            entradas_esta_tabla = []
            for entry in table.iter():
                etag = entry.tag.split('}', 1)[-1]
                if etag == "entry":
                    # Texto completo normalizado de la entrada
                    text_parts = [t.strip() for t in entry.itertext() if t and t.strip()]
                    full_text = " ".join(text_parts)
                    if full_text:
                        entradas_esta_tabla.append(full_text)
            
            todas_las_entradas.extend(entradas_esta_tabla)
            if titulo:
                tablas_con_titulo.setdefault(titulo, []).extend(entradas_esta_tabla)
            else:
                entradas_sin_titulo.extend(entradas_esta_tabla)
                    
        return tablas_con_titulo, entradas_sin_titulo, todas_las_entradas

    ####933######
    def contar_y_extraer_taskset_en_techname(self):
        """
        Extrae 'Task set ...' de <techName> y busca su <infoName> hermano.
        Devuelve una lista de tuplas (código, info_name).
        """
        root = self.tree.getroot()

        # Capturamos todo lo que hay después de "Task set" o "Tarea" como código
        patron = self.patron_c04
        
        task_sets = []

        for parent in root.iter():
            tech_name_text = None
            info_name_text = "N/A"
            
            for child in parent:
                tag = child.tag.split('}', 1)[-1]
                if tag == "techName" and child.text:
                    tech_name_text = child.text.strip()
                elif tag == "infoName" and child.text:
                    info_name_text = child.text.strip()
            
            if tech_name_text:
                m = patron.search(tech_name_text)
                if m:
                    code = m.group(1).strip()
                    task_sets.append((code, info_name_text))

        return len(task_sets), task_sets


    def extraer_subtareas(self):
        """
        Busca en el XML los proceduralStep con un title que empiece por:
        'Task <codigo> <nombre...>'
        y devuelve (lista_subtareas, numero_subtareas).

        Cada subtarea será una tupla: (codigo, nombre)
        """
        root = self.tree.getroot()

        subtareas = []
        patron = self.patron_c05

        for elem in root.iter():
            tag_sin_ns = elem.tag.split('}', 1)[-1]
            if tag_sin_ns == "proceduralStep":
                for hijo in elem:
                    hijo_tag = hijo.tag.split('}', 1)[-1]
                    if hijo_tag == "title" and hijo.text:
                        m = patron.match(hijo.text)
                        if m:
                            codigo = m.group(1)
                            nombre = m.group(2).lower()
                            subtareas.append((codigo, nombre))

        return subtareas, len(subtareas)


    def extraer_pasos_con_texto(self):
        """
        Devuelve un diccionario {step_id: texto_contenido} para cada
        paso de una subtarea.
        El texto se normaliza para comparaciones.
        """
        root = self.tree.getroot()
        patron_task = self.patron_c05
        pasos = {}

        for elem in root.iter():
            tag = elem.tag.split('}', 1)[-1]
            if tag != "proceduralStep":
                continue

            is_subtask = False
            # Comprobar si es un proceduralStep de una subtarea (tiene title "Task...")
            for hijo in elem:
                hijo_tag = hijo.tag.split('}', 1)[-1]
                if hijo_tag == "title" and hijo.text and patron_task.match(hijo.text):
                    is_subtask = True
                    break
            
            if not is_subtask:
                continue

            # Si es subtarea, buscar los pasos reales dentro de proceduralStepAlts
            for hijo in elem:
                hijo_tag = hijo.tag.split('}', 1)[-1]
                if hijo_tag != "proceduralStepAlts":
                    continue

                for step in hijo:
                    step_tag = step.tag.split('}', 1)[-1]
                    if step_tag != "proceduralStep":
                        continue
                    
                    step_id = step.get("id")
                    if not step_id:
                        continue

                    # Extraer todo el texto del paso, normalizarlo para comparar
                    text_parts = [t.strip() for t in step.itertext() if t and t.strip()]
                    full_text = " ".join(text_parts)
                    
                    pasos[str(step_id)] = full_text
        return pasos

    def _traverse_step_structure(self, element, current_path, paths_set):
        """
        Función auxiliar recursiva para generar las rutas de la estructura de pasos.
        """
        # Los elementos a procesar son los proceduralStep hijos del elemento actual
        child_steps = [child for child in element if child.tag.split('}', 1)[-1] == "proceduralStep"]
        
        for i, step in enumerate(child_steps):
            # Creamos la nueva ruta para este paso
            new_path = f"{current_path}/{i}" if current_path else str(i)
            paths_set.add(new_path)
            
            # Buscamos si este paso tiene sub-pasos anidados
            for sub_alt in step:
                if sub_alt.tag.split('}', 1)[-1] == "proceduralStepAlts":
                    # Si los tiene, llamamos recursivamente
                    self._traverse_step_structure(sub_alt, new_path, paths_set)

    def _iter_pasos_subtarea(self, subtarea_elem):
        """
        Devuelve (yield) los proceduralStep que son pasos de una subtarea,
        aceptando las DOS estructuras validas del XML:
          - pasos dentro de <proceduralStepAlts> (estructura clasica), y
          - pasos como proceduralStep hijos directos de la subtarea (en paralelo).
        No desciende a subtareas anidadas: solo da los pasos de este nivel.
        """
        for hijo in subtarea_elem:
            tag = hijo.tag.split('}', 1)[-1]
            if tag == "proceduralStepAlts":
                for step in hijo:
                    if step.tag.split('}', 1)[-1] == "proceduralStep":
                        yield step
            elif tag == "proceduralStep":
                yield hijo

    def extraer_estructura_pasos_por_subtarea(self):
        """
        Devuelve un diccionario donde las claves son los nombres normalizados de las subtareas
        y los valores son conjuntos (sets) con "rutas" que representan la estructura
        anidada de sus proceduralSteps.
        Ejemplo de ruta: "0/1/0" para el primer sub-paso del segundo paso del primer paso.
        """
        root = self.tree.getroot()
        patron_task = self.patron_c05
        subtareas_con_pasos = {}

        for elem in root.iter():
            tag = elem.tag.split('}', 1)[-1]
            if tag != "proceduralStep":
                continue

            # Identificar si es una subtarea por su título
            title_text = None
            for hijo in elem:
                hijo_tag = hijo.tag.split('}', 1)[-1]
                if hijo_tag == "title" and hijo.text:
                    title_text = hijo.text
                    break
            
            if not title_text:
                continue
            
            m = patron_task.match(title_text)
            if not m:
                continue
            
            nombre_subtarea = m.group(2).lower()
            nombre_normalizado = ' '.join(str(nombre_subtarea).split())

            pasos_de_esta_subtarea = set()
            # Estructura clasica con <proceduralStepAlts>?
            tiene_alts = any(
                h.tag.split('}', 1)[-1] == "proceduralStepAlts" for h in elem
            )
            if tiene_alts:
                # Clasica: pasos dentro de <proceduralStepAlts> (logica intacta)
                for hijo_subtarea in elem:
                    if hijo_subtarea.tag.split('}', 1)[-1] == "proceduralStepAlts":
                        self._traverse_step_structure(hijo_subtarea, "", pasos_de_esta_subtarea)
            else:
                # En paralelo: pasos como proceduralStep hijos directos
                self._traverse_step_structure(elem, "", pasos_de_esta_subtarea)

            if pasos_de_esta_subtarea:
                subtareas_con_pasos.setdefault(nombre_normalizado, set()).update(pasos_de_esta_subtarea)
                
        return subtareas_con_pasos

    def matriz_subtareas_pasos(self):
        root = self.tree.getroot()

        patron_task = self.patron_c05

        # Lista de subtareas con sus pasos (título e id de cada paso)
        subtareas = []

        for elem in root.iter():
            tag = elem.tag.split('}', 1)[-1]
            if tag != "proceduralStep":
                continue

            # ¿Es una subtarea con title "Task ... ..."?
            title_text = None
            for hijo in elem:
                hijo_tag = hijo.tag.split('}', 1)[-1]
                if hijo_tag == "title" and hijo.text:
                    title_text = hijo.text
                    break

            if not title_text:
                continue

            m = patron_task.match(title_text)
            if not m:
                continue

            codigo_subtarea = m.group(1)
            nombre_subtarea = m.group(2).lower()

            pasos = []

            # Buscar pasos dentro de proceduralStepAlts
            for hijo in elem:
                hijo_tag = hijo.tag.split('}', 1)[-1]
                if hijo_tag != "proceduralStepAlts":
                    continue

                for step in hijo:
                    step_tag = step.tag.split('}', 1)[-1]
                    if step_tag != "proceduralStep":
                        continue

                    # AQUÍ se guarda el id del paso: stp-000016, stp-000017, ...
                    step_id = step.get("id") or "N/A"

                    # Primer <para> no vacío = título del paso
                    titulo_paso = None
                    for sub in step.iter():
                        sub_tag = sub.tag.split('}', 1)[-1]
                        if sub_tag == "para" and sub.text and sub.text.strip():
                            titulo_paso = sub.text.strip()
                            break

                    if titulo_paso is None:
                        pasos.append({"titulo": 1, "id": step_id})
                    else:
                        pasos.append({"titulo": titulo_paso, "id": step_id})

            subtareas.append((codigo_subtarea, nombre_subtarea, pasos))

        if not subtareas:
            return pd.DataFrame()

        # Máximo nº de pasos entre todas las subtareas
        max_pasos = max(len(pasos) for _, _, pasos in subtareas)

        # Construir filas del DataFrame
        filas_df = []
        for codigo, nombre, pasos in subtareas:
            pasos_padded = pasos + [{"titulo": 0, "id": "N/A"}] * (max_pasos - len(pasos))
            fila = {
                "codigo_subtarea": codigo,
                "nombre_subtarea": nombre,
            }
            for i, paso in enumerate(pasos_padded, start=1):
                fila[f"step_{i}"] = paso["titulo"]
                fila[f"step_{i}_id"] = paso["id"]  # <- aquí queda guardado stp-000016, etc.
            filas_df.append(fila)

        df = pd.DataFrame(filas_df)
        return df


    def matriz_referencias_internas(self):
        """
        Devuelve un DataFrame con columnas:
        - internalRefId
        - internalRefTargetType
        - codigo_subtarea
        - nombre_subtarea
        - num_paso
        """
        root = self.tree.getroot()

        patron_task = self.patron_c05
        filas = []

        for elem in root.iter():
            tag = elem.tag.split('}', 1)[-1]
            if tag != "proceduralStep":
                continue

            # ¿Es una subtarea con title "Task ... ..."?
            title_text = None
            for hijo in elem:
                hijo_tag = hijo.tag.split('}', 1)[-1]
                if hijo_tag == "title" and hijo.text:
                    title_text = hijo.text
                    break

            if not title_text:
                continue

            m = patron_task.match(title_text)
            if not m:
                continue

            codigo_subtarea = m.group(1)
            nombre_subtarea = m.group(2).lower()

            # Pasos de la subtarea (proceduralStepAlts o hijos directos)
            num_paso = 0
            for step in self._iter_pasos_subtarea(elem):
                num_paso += 1

                # Dentro de este paso, buscamos internalRef
                for sub in step.iter():
                    sub_tag = sub.tag.split('}', 1)[-1]
                    if sub_tag == "internalRef":
                        internal_id = sub.get("internalRefId")
                        target_type = sub.get("internalRefTargetType")
                        if internal_id and target_type:
                            filas.append({
                                "internalRefId": internal_id,
                                "internalRefTargetType": target_type,
                                "codigo_subtarea": codigo_subtarea,
                                "nombre_subtarea": nombre_subtarea,
                                "num_paso": num_paso,
                            })

        df_refs = pd.DataFrame(filas)
        return df_refs

    def extraer_dm_refs_con_subtareas(self):
        """
        Extrae todas las refs a DM code que estén dentro de los pasos de subtareas
        'Task ...' y devuelve un DataFrame con columnas (rellenando vacíos con 'N/A'):

        - dmRef_id
        - assyCode
        - disassyCode
        - disassyCodeVariant
        - infoCode
        - infoCodeVariant
        - itemLocationCode
        - modelIdentCode
        - subSubSystemCode
        - subSystemCode
        - systemCode
        - systemDiffCode
        - techName
        - codigo_subtarea
        - nombre_subtarea
        - num_paso
        """
        root = self.tree.getroot()

        patron_task = self.patron_c05
        filas = []

        def clean(value):
            value = "" if value is None else str(value).strip()
            return value if value else "N/A"

        # Recorremos todos los proceduralStep para localizar subtareas Task...
        for ps in root.iter():
            tag = ps.tag.split('}', 1)[-1]
            if tag != "proceduralStep":
                continue

            # ¿Es una subtarea con <title>Task ... ...</title>?
            title_text = None
            for hijo in ps:
                hijo_tag = hijo.tag.split('}', 1)[-1]
                if hijo_tag == "title" and hijo.text:
                    title_text = hijo.text
                    break

            if not title_text:
                continue

            m = patron_task.match(title_text)
            if not m:
                continue

            codigo_subtarea = clean(m.group(1))
            nombre_subtarea = clean(m.group(2)).lower()

            # Pasos de la subtarea (proceduralStepAlts o hijos directos)
            num_paso = 0
            for step in self._iter_pasos_subtarea(ps):
                num_paso += 1

                # En este paso buscamos dmRef
                for sub in step.iter():
                    sub_tag = sub.tag.split('}', 1)[-1]
                    if sub_tag != "dmRef":
                        continue

                    dmref = sub
                    dmref_id = clean(dmref.get("id"))

                    # dmRefIdent/dmCode
                    dmcode_elem = None
                    for child in dmref:
                        ctag = child.tag.split('}', 1)[-1]
                        if ctag == "dmRefIdent":
                            for gc in child:
                                if gc.tag.split('}', 1)[-1] == "dmCode":
                                    dmcode_elem = gc
                                    break
                        if dmcode_elem is not None:
                            break

                    if dmcode_elem is None:
                        continue  # dmRef sin dmCode

                    # techName dentro de dmRefAddressItems
                    tech_name = "N/A"
                    for child in dmref:
                        ctag = child.tag.split('}', 1)[-1]
                        if ctag == "dmRefAddressItems":
                            for gc in child.iter():
                                if gc.tag.split('}', 1)[-1] == "techName" and gc.text:
                                    tech_name = clean(gc.text)
                                    break
                        if tech_name != "N/A":
                            break

                    attrs = dmcode_elem.attrib
                    fila = {
                        "dmRef_id": dmref_id,
                        "assyCode": clean(attrs.get("assyCode")),
                        "disassyCode": clean(attrs.get("disassyCode")),
                        "disassyCodeVariant": clean(attrs.get("disassyCodeVariant")),
                        "infoCode": clean(attrs.get("infoCode")),
                        "infoCodeVariant": clean(attrs.get("infoCodeVariant")),
                        "itemLocationCode": clean(attrs.get("itemLocationCode")),
                        "modelIdentCode": clean(attrs.get("modelIdentCode")),
                        "subSubSystemCode": clean(attrs.get("subSubSystemCode")),
                        "subSystemCode": clean(attrs.get("subSystemCode")),
                        "systemCode": clean(attrs.get("systemCode")),
                        "systemDiffCode": clean(attrs.get("systemDiffCode")),
                        "techName": tech_name,
                        "codigo_subtarea": codigo_subtarea,
                        "nombre_subtarea": nombre_subtarea,
                        "num_paso": num_paso,
                    }
                    filas.append(fila)

        return pd.DataFrame(filas)

    def extraer_externalPub_refs_con_subtareas(self):
        """
        Devuelve un DataFrame con las referencias externas encontradas en los pasos
        de subtareas 'Task ...', con columnas:

        - externalPubRef_id
        - codigo_subtarea
        - nombre_subtarea
        - num_paso
        """
        root = self.tree.getroot()

        patron_task = self.patron_c05
        filas = []

        def clean(value):
            value = "" if value is None else str(value).strip()
            return value if value else "N/A"

        # Recorremos todos los proceduralStep para localizar subtareas Task...
        for ps in root.iter():
            tag = ps.tag.split('}', 1)[-1]
            if tag != "proceduralStep":
                continue

            # ¿Es una subtarea con <title>Task ... ...</title>?
            title_text = None
            for hijo in ps:
                hijo_tag = hijo.tag.split('}', 1)[-1]
                if hijo_tag == "title" and hijo.text:
                    title_text = hijo.text
                    break

            if not title_text:
                continue

            m = patron_task.match(title_text)
            if not m:
                continue

            codigo_subtarea = clean(m.group(1))
            nombre_subtarea = clean(m.group(2)).lower()

            # Pasos de la subtarea (proceduralStepAlts o hijos directos)
            num_paso = 0
            for step in self._iter_pasos_subtarea(ps):
                num_paso += 1

                # En este paso buscamos externalPubRef
                for sub in step.iter():
                    sub_tag = sub.tag.split('}', 1)[-1]
                    if sub_tag != "externalPubRef":
                        continue

                    ext_id = clean(sub.get("id"))

                    filas.append({
                        "externalPubRef_id": ext_id,
                        "codigo_subtarea": codigo_subtarea,
                        "nombre_subtarea": nombre_subtarea,
                        "num_paso": num_paso,
                    })

        return pd.DataFrame(filas)

    ####930####
    def extraer_configuraciones(self):
        """
        Devuelve un DataFrame con las configuraciones del DMC 933 y comprueba
        que el nº de configuraciones en la tabla 'MSN by configuration' coincide
        con el nº de definiciones en 'Configuration definition'.

        Columnas del DataFrame:
        - config_name_tab     (texto CONF 001, CONF 002... en la tabla)
        - msn_range           (rango(s) de MSN asociados en la tabla)
        - config_def_text     (texto del para en Configuration definition)
        """
        root = self.tree.getroot()

        def clean(v):
            v = "" if v is None else str(v).strip()
            return v if v else "N/A"

        # --- 1) Configs en tabla "MSN by configuration" ---
        configs_tabla = []

        for lp in root.iter():
            tag = lp.tag.split('}', 1)[-1]
            if tag != "levelledPara":
                continue

            title_text = None
            for child in lp:
                ctag = child.tag.split('}', 1)[-1]
                if ctag == "title" and child.text:
                    title_text = child.text.strip()
                    break

            if not title_text or not re.search(r"^\s*(?:MSN\s+(?:by|por)\s+)?(?:configuraci[oó]n(?:es)?|configuration?s?)\s*$", title_text, re.IGNORECASE):
                continue

            # Dentro de este levelledPara, buscamos la tabla
            tabla = None
            for sub in lp.iter():
                if sub.tag.split('}', 1)[-1] == "table":
                    tabla = sub
                    break

            if tabla is None:
                break

            # Filas de configuración en <tbody>
            for tbody in tabla.iter():
                if tbody.tag.split('}', 1)[-1] != "tbody":
                    continue
                for row in tbody:
                    if row.tag.split('}', 1)[-1] != "row":
                        continue
                    entries = [e for e in row if e.tag.split('}', 1)[-1] == "entry"]
                    if len(entries) < 2:
                        continue

                    # COL1 = MSN range, COL2 = CONFIGURATION
                    msn_entry = entries[0]
                    conf_entry = entries[1]

                    msn_text = " ".join(
                        clean(p.text)
                        for p in msn_entry.iter()
                        if p.tag.split('}', 1)[-1] == "para" and p.text
                    )

                    conf_text = " ".join(
                        clean(p.text)
                        for p in conf_entry.iter()
                        if p.tag.split('}', 1)[-1] == "para" and p.text
                    )

                    if conf_text and conf_text != "N/A":
                        configs_tabla.append({
                            "config_name_tab": conf_text,
                            "msn_range": msn_text,
                        })

            break  # ya hemos procesado el bloque correcto

        # --- 2) Configs en "Configuration definition" ---
        configs_def = []

        for lp in root.iter():
            tag = lp.tag.split('}', 1)[-1]
            if tag != "levelledPara":
                continue

            title_text = None
            for child in lp:
                ctag = child.tag.split('}', 1)[-1]
                if ctag == "title" and child.text:
                    title_text = child.text.strip()
                    break

            if not title_text or not re.search(r"^\s*(?:definici[oó]n\s+(?:de\s+(?:la\s+)?)?)?(?:configuraci[oó]n(?:es)?|configuration?s?)(?:\s+definition?s?)?\s*$", title_text, re.IGNORECASE):
                continue

            # levelledPara hijos con su para de definición
            for sub_lp in lp:
                if sub_lp.tag.split('}', 1)[-1] != "levelledPara":
                    continue

                def_text = " ".join(
                    clean(p.text)
                    for p in sub_lp.iter()
                    if p.tag.split('}', 1)[-1] == "para" and p.text
                )

                if def_text:
                    configs_def.append(def_text)

            break  # ya procesado el bloque

        # --- 3) Comparación y construcción del DataFrame ---
        n_tab = len(configs_tabla)
        n_def = len(configs_def)

        if n_tab != n_def:
            warnings.warn(
                f"El número de configuraciones en la tabla (MSN by configuration) ({n_tab}) "
                f"no coincide con el número de definiciones en Configuration definition ({n_def}).",
                UserWarning,
            )

        filas = []
        max_len = max(n_tab, n_def)
        for i in range(max_len):
            config_name_tab = configs_tabla[i]["config_name_tab"] if i < n_tab else "N/A"
            msn_range = configs_tabla[i]["msn_range"] if i < n_tab else "N/A"
            config_def_text = configs_def[i] if i < n_def else "N/A"

            filas.append({
                "config_name_tab": config_name_tab,
                "msn_range": msn_range,
                "config_def_text": config_def_text,
            })

        return pd.DataFrame(filas)

    #def material sets
    def extraer_sbIndividualSpare_con_sbSpareSet(self):
        """
        Devuelve un DataFrame con todas las ocurrencias de <sbIndividualSpare> del XML.

        Columnas:
        - sbIndividualSpare_name  (name del embeddedSpareDescr)
        - sbIndividualSpare_id    (id del sbIndividualSpare)
        - sbSpareSet_applicRefId  (applicRefId del sbSpareSet contenedor)
        - sbSpareSet_id           (id del sbSpareSet contenedor)
        - sbSpareSet_name         (name del sbSpareSet contenedor)
        """
        root = self.tree.getroot()

        filas = []

        def clean(value):
            value = "" if value is None else str(value).strip()
            return value if value else "N/A"

        # Recorremos todos los sbSpareSet
        for sbset in root.iter():
            tag = sbset.tag.split('}', 1)[-1]
            if tag != "sbSpareSet":
                continue

            sbset_id = clean(sbset.get("id"))
            sbset_applic = clean(sbset.get("applicRefId"))

            # name hijo directo de sbSpareSet
            sbset_name = "N/A"
            for child in sbset:
                ctag = child.tag.split('}', 1)[-1]
                if ctag == "name" and child.text:
                    sbset_name = clean(child.text)
                    break

            # Dentro de este sbSpareSet buscamos sbIndividualSpare
            for spare in sbset.iter():
                if spare.tag.split('}', 1)[-1] != "sbIndividualSpare":
                    continue

                spare_id = clean(spare.get("id"))

                spare_name = "N/A"
                props = []

                for sub in spare.iter():
                    ctag = sub.tag.split('}', 1)[-1]
                    
                    # Para visualización en reporte
                    if ctag == "name" and sub.text and spare_name == "N/A":
                        spare_name = clean(sub.text)
                    
                    # Recolectar TODOS los atributos (excepto ID)
                    for k, v in sorted(sub.attrib.items()):
                        if k.lower() == "id": continue
                        props.append(clean(v))
                    # Recolectar texto
                    if sub.text and sub.text.strip():
                        props.append(clean(sub.text))

                attrs = tuple(props)

                filas.append({
                    "sbIndividualSpare_name": spare_name,
                    "sbIndividualSpare_id": spare_id,
                    "sbSpareSet_applicRefId": sbset_applic,
                    "sbSpareSet_id": sbset_id,
                    "sbSpareSet_name": sbset_name,
                    "sbIndividualSpare_attrs": attrs,
                })

        return pd.DataFrame(filas)

    #defssparespartso removed recoge spares,ints y tabla de remove, y reidentified
    def extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet(self):
        """
        Devuelve un DataFrame con todas las ocurrencias de <sbIndividualRemovedSpare>.

        Columnas:
        - sbIndividualRemovedSpare_name
        - sbIndividualRemovedSpare_id
        - sbRemovedSpareSet_applicRefId
        - sbRemovedSpareSet_id
        - sbRemovedSpareSet_name
        """
        root = self.tree.getroot()

        filas = []

        def clean(value):
            value = "" if value is None else str(value).strip()
            return value if value else "N/A"

        # Recorremos todos los sbRemovedSpareSet
        for sbset in root.iter():
            tag = sbset.tag.split('}', 1)[-1]
            if tag != "sbRemovedSpareSet":
                continue

            sbset_id = clean(sbset.get("id"))
            sbset_applic = clean(sbset.get("applicRefId"))

            # name hijo directo de sbRemovedSpareSet
            sbset_name = "N/A"
            for child in sbset:
                ctag = child.tag.split('}', 1)[-1]
                if ctag == "name" and child.text:
                    sbset_name = clean(child.text)
                    break

            # Dentro de este sbRemovedSpareSet buscamos sbIndividualRemovedSpare
            for spare in sbset.iter():
                if spare.tag.split('}', 1)[-1] != "sbIndividualRemovedSpare":
                    continue

                spare_id = clean(spare.get("id"))

                spare_name = "N/A"
                props = []

                for sub in spare.iter():
                    ctag = sub.tag.split('}', 1)[-1]
                    
                    # Para visualización
                    if ctag == "name" and sub.text and spare_name == "N/A":
                        spare_name = clean(sub.text)
                    
                    # Recolectar TODOS los atributos (excepto ID)
                    for k, v in sorted(sub.attrib.items()):
                        if k.lower() == "id": continue
                        props.append(clean(v))
                    # Recolectar texto
                    if sub.text and sub.text.strip():
                        props.append(clean(sub.text))

                attrs = tuple(props)

                filas.append({
                    "sbIndividualRemovedSpare_name": spare_name,
                    "sbIndividualRemovedSpare_id": spare_id,
                    "sbRemovedSpareSet_applicRefId": sbset_applic,
                    "sbRemovedSpareSet_id": sbset_id,
                    "sbRemovedSpareSet_name": sbset_name,
                    "sbIndividualRemovedSpare_attrs": attrs,
                })

        return pd.DataFrame(filas)

    #defstools
    def extraer_tools_con_sbSupportEquipSet(self):
        """
        Devuelve un DataFrame con todas las tools definidas en <sbSupportEquipSet>.

        Columnas:
        - tool_name                  (name dentro de embeddedSupportEquipDescr)
        - sbIndividualSupportEquip_id
        - toolNumber
        - sbSupportEquipSet_applicRefId
        - sbSupportEquipSet_id
        - sbSupportEquipSet_name
        """
        root = self.tree.getroot()

        filas = []

        def clean(value):
            value = "" if value is None else str(value).strip()
            return value if value else "N/A"

        # Recorremos todos los sbSupportEquipSet
        for sbset in root.iter():
            tag = sbset.tag.split('}', 1)[-1]
            if tag != "sbSupportEquipSet":
                continue

            set_id = clean(sbset.get("id"))
            set_applic = clean(sbset.get("applicRefId"))

            # name del set
            set_name = "N/A"
            for child in sbset:
                ctag = child.tag.split('}', 1)[-1]
                if ctag == "name" and child.text:
                    set_name = clean(child.text)
                    break

            # sbIndividualSupportEquip dentro del set
            for equip in sbset.iter():
                if equip.tag.split('}', 1)[-1] != "sbIndividualSupportEquip":
                    continue

                equip_id = clean(equip.get("id"))

                tool_name = "N/A"
                tool_number = "N/A"
                props = []

                for sub in equip.iter():
                    ctag = sub.tag.split('}', 1)[-1]

                    if ctag == "name" and sub.text and tool_name == "N/A":
                        tool_name = clean(sub.text)
                    elif ctag == "toolRef":
                        tool_number = clean(sub.get("toolNumber"))

                    # Recolectar TODOS los atributos (excepto ID)
                    for k, v in sorted(sub.attrib.items()):
                        if k.lower() == "id": continue
                        props.append(clean(v))
                    # Recolectar texto
                    if sub.text and sub.text.strip():
                        props.append(clean(sub.text))

                attrs = tuple(props)

                filas.append({
                    "tool_name": tool_name,
                    "sbIndividualSupportEquip_id": equip_id,
                    "toolNumber": tool_number,
                    "sbSupportEquipSet_applicRefId": set_applic,
                    "sbSupportEquipSet_id": set_id,
                    "sbSupportEquipSet_name": set_name,
                    "sbIndividualSupportEquip_attrs": attrs,
                })

        return pd.DataFrame(filas)

    #defcmls
    def extraer_supplies_con_sbSupplySet(self):
        """
        Devuelve un DataFrame con todas las supplies definidas en <sbSupplySet>.

        Columnas:
        - supply_name
        - sbIndividualSupply_id
        - supplyRqmtNumber
        - sbSupplySet_applicRefId
        - sbSupplySet_id
        - sbSupplySet_name
        """
        root = self.tree.getroot()

        filas = []

        def clean(value):
            value = "" if value is None else str(value).strip()
            return value if value else "N/A"

        # Recorremos todos los sbSupplySet
        for sbset in root.iter():
            tag = sbset.tag.split('}', 1)[-1]
            if tag != "sbSupplySet":
                continue

            set_id = clean(sbset.get("id"))
            set_applic = clean(sbset.get("applicRefId"))

            # name del set
            set_name = "N/A"
            for child in sbset:
                ctag = child.tag.split('}', 1)[-1]
                if ctag == "name" and child.text:
                    set_name = clean(child.text)
                    break

            # sbIndividualSupply dentro del set
            for sup in sbset.iter():
                if sup.tag.split('}', 1)[-1] != "sbIndividualSupply":
                    continue

                sup_id = clean(sup.get("id"))
                supply_name = "N/A"
                supply_rqmt = "N/A"
                props = []

                for sub in sup.iter():
                    ctag = sub.tag.split('}', 1)[-1]

                    if ctag == "name" and sub.text and supply_name == "N/A":
                        supply_name = clean(sub.text)
                    elif ctag == "supplyRqmtRef":
                        supply_rqmt = clean(sub.get("supplyRqmtNumber"))

                    # Recolectar TODOS los atributos (excepto ID)
                    for k, v in sorted(sub.attrib.items()):
                        if k.lower() == "id": continue
                        props.append(clean(v))
                    # Recolectar texto
                    if sub.text and sub.text.strip():
                        props.append(clean(sub.text))

                attrs = tuple(props)

                filas.append({
                    "supply_name": supply_name,
                    "sbIndividualSupply_id": sup_id,
                    "supplyRqmtNumber": supply_rqmt,
                    "sbSupplySet_applicRefId": set_applic,
                    "sbSupplySet_id": set_id,
                    "sbSupplySet_name": set_name,
                    "sbIndividualSupply_attrs": attrs,
                })

        return pd.DataFrame(filas)



    """
    Este módulo agrupa distintas funciones de recuento y extracción de información
    a partir de ficheros XML S1000D. De forma resumida, cada función cuenta / extrae:

    - extraer_palabras_texto_plano(self.ruta_xml)
        Cuenta todas las palabras de texto plano que aparecen en <para>,
        <notePara> y <warningAndCautionPara>. Devuelve la lista de palabras
        y el número total.

    - extraer_graphic_refs(self.ruta_xml)
        Recorre todas las etiquetas <graphic> del XML y devuelve un DataFrame
        con su id, el atributo infoEntityIdent y el título asociado (ya sea en
        un atributo *title o en el texto title="..." de la etiqueta).

    - extraer_tablas_con_entradas(self.ruta_xml)
        Cuenta todas las tablas <table> del documento (en cualquier parte) y
        devuelve un DataFrame con id, estilo (tabstyle), título y número total
        de celdas <entry> de cada tabla.

    - extraer_subtareas(self.ruta_xml)
        Localiza los proceduralStep cuyo <title> empieza por "Task <código> <nombre>"
        y devuelve la lista de subtareas encontradas junto con su número total.

    - matriz_subtareas_pasos(self.ruta_xml)
        Construye una matriz (DataFrame) donde cada fila es una subtarea "Task ..."
        y las columnas step_1, step_2, ... contienen el título del primer <para> de
        cada paso, o 1 si el paso no tiene título, o 0 si la subtarea no tiene
        ese paso (para cuadrar la matriz).

    - matriz_referencias_internas(self.ruta_xml)
        Para cada subtarea "Task ..." y para cada uno de sus pasos, cuenta las
        referencias internas <internalRef>. Devuelve un DataFrame con internalRefId,
        internalRefTargetType, código y nombre de subtarea y número de paso.

    - extraer_dm_refs_con_subtareas(self.ruta_xml)
        Dentro de los pasos de cada subtarea "Task ...", busca referencias a otros
        DMC en <dmRef>. Devuelve un DataFrame con los atributos del <dmCode>
        (assyCode, disassyCode, infoCode, etc.), el techName del título
        de la referencia y la subtarea/paso donde aparece. Los atributos vacíos
        se rellenan con "N/A".

    - extraer_externalPub_refs_con_subtareas(self.ruta_xml)
        Recorre los pasos de las subtareas "Task ..." y cuenta las referencias
        externas <externalPubRef>. Devuelve un DataFrame con su id, el código y
        nombre de subtarea y el número de paso.

    - extraer_configuraciones(self.ruta_xml)
        Analiza el bloque "MSN by configuration" (tabla) y el bloque
        "Configuration definition". Cuenta las configuraciones en la tabla
        (CONF 001, CONF 002, ...) y las definiciones asociadas. Devuelve un
        DataFrame que alinea ambos orígenes y lanza un warning si el número de
        configuraciones en la tabla no coincide con el número de definiciones.

    - extraer_sbIndividualSpare_con_sbSpareSet(self.ruta_xml)
        Recorre los <sbSpareSet> y extrae todos los <sbIndividualSpare> (spares).
        Devuelve un DataFrame con el nombre y id del spare, así como el applicRefId,
        id y nombre del sbSpareSet en el que se encuentra.

    - extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet(self.ruta_xml)
        Similar a la anterior, pero para los repuestos retirados. Recorre
        <sbRemovedSpareSet> y extrae los <sbIndividualRemovedSpare>, devolviendo
        un DataFrame con nombre e id del removed spare y los datos del set padre.

    - extraer_tools_con_sbSupportEquipSet(self.ruta_xml)
        Analiza los <sbSupportEquipSet> (standard/special tools) y extrae todas las
        herramientas definidas en <sbIndividualSupportEquip>. Devuelve un DataFrame
        con nombre de la tool, id del sbIndividualSupportEquip, toolNumber y los
        datos del set (id, applicRefId, nombre).

    - extraer_supplies_con_sbSupplySet(self.ruta_xml)
        Analiza los consumibles en <sbSupplySet> dentro de <sbSuppliesList>.
        Devuelve un DataFrame con nombre del consumible, id del sbIndividualSupply,
        número de requerimiento (supplyRqmtNumber) y los datos del set de
        consumibles (id, applicRefId, nombre).
    """
if __name__ == "__main__":
    from metodosrecuento import metodosrecuento
    # Cambia la ruta al XML que quieras probar
    mr = metodosrecuento(r"s1000d\AJ-A-T46-01-16-00AAA-930A-A.xml")
    df_pasos = mr.matriz_subtareas_pasos()
    print(df_pasos)
    mr.matriz_subtareas_pasos().to_csv("matriz_subtareas_pasos.csv", index=False)

    # 1) Texto plano
    palabras, total_palabras = mr.extraer_palabras_texto_plano()
    print("1) Palabras de texto plano:", total_palabras)

    # 2) Gráficos
    df_graph = mr.extraer_graphic_refs()
    print("2) Graphics:", len(df_graph))

    # 3) Tablas (todas)
    df_tablas = mr.extraer_tablas_con_entradas()
    print("3) Tablas (totales):", len(df_tablas))

    # 4) Subtareas Task ...
    subtareas, total_subt = mr.extraer_subtareas()
    print(pd.DataFrame(mr.extraer_subtareas()[0], columns=["codigo", "nombre"]))
    print("4) Subtareas Task:", total_subt)

    # 5) Matriz subtareas vs pasos
    df_pasos = mr.matriz_subtareas_pasos()
    print("5) Matriz subtareas/pasos:", df_pasos.shape)

    # 6) Referencias internas internalRef
    df_int = mr.matriz_referencias_internas()
    print("6) internalRef:", len(df_int))

    # 7) Referencias a DM (dmRef)
    df_dm = mr.extraer_dm_refs_con_subtareas()
    print("7) dmRef:", len(df_dm))

    # 8) Referencias externas externalPubRef
    df_ext = mr.extraer_externalPub_refs_con_subtareas()
    print("8) externalPubRef:", len(df_ext))

    # 9) Configuraciones (solo si el XML tiene MSN/configuration)
    df_cfg = mr.extraer_configuraciones()
    print("9) Configuraciones:", len(df_cfg))
    mr.extraer_configuraciones().to_csv("configuraciones.csv", index=False)

    # 10) Spares (sbSpareSet / sbIndividualSpare)
    df_spares = mr.extraer_sbIndividualSpare_con_sbSpareSet()
    print("10) Individual spares:", len(df_spares))

    # 11) Removed spares (sbRemovedSpareSet)
    df_removed = mr.extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet()
    print("11) Removed spares:", len(df_removed))

    # 12) Tools (sbSupportEquipSet)
    df_tools = mr.extraer_tools_con_sbSupportEquipSet()
    print("12) Tools:", len(df_tools))

    # 13) Supplies / consumibles (sbSupplySet)
    df_supplies = mr.extraer_supplies_con_sbSupplySet()
    print("13) Supplies:", len(df_supplies))
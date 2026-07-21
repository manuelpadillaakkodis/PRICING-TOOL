import xml.etree.ElementTree as ET
import re
import pandas as pd

class metodosrecuento_legacy:
    """
    Clase para extraer contadores de ficheros XML con esquema antiguo (AMSB).
    Implementa la misma interfaz (métodos y tipos de retorno) que metodosrecuento
    para compatibilidad con funcionespesado.py.
    """
    def __init__(self, ruta_xml):
        self.ruta_xml = ruta_xml
        # Permite ruta de archivo o objeto file-like (BytesIO)
        self.tree = ET.parse(self.ruta_xml)
        self.root = self.tree.getroot()

    def extraer_palabras_texto_plano(self):
        """C01: Palabras en <para>, <notePara>, <warningAndCautionPara>."""
        num_palabras = 0
        # En legacy, el texto suele estar en <para>.
        # Buscamos en todo el documento.
        tags_texto = ['para', 'notePara', 'warningAndCautionPara']
        
        for tag in tags_texto:
            for elem in self.root.iter(tag):
                if elem.text:
                    num_palabras += len(re.findall(r"\w[\w'-]*", elem.text))
                for child in elem:
                    if child.tail:
                        num_palabras += len(re.findall(r"\w[\w'-]*", child.tail))
        return [], num_palabras

    def extraer_graphic_refs(self):
        """C02: Gráficos. En legacy se cuentan los <sheet> dentro de <figure>."""
        filas = []
        for figure in self.root.iter('figure'):
            # Intentar obtener título de la figura
            title_elem = figure.find('titlefigure')
            titulo = title_elem.text if title_elem is not None else "N/A"
            
            for sheet in figure.iter('sheet'):
                # Mapeamos 'path' (ej: ICN-...) a 'infoEntityIdent' para compatibilidad
                path = sheet.get('path', 'N/A')
                sheet_id = sheet.get('id', 'N/A')
                
                filas.append({
                    "graphic_id": sheet_id,
                    "infoEntityIdent": path,
                    "titulo": titulo
                })
        return pd.DataFrame(filas)

    def extraer_tablas_con_entradas(self):
        """C03: Tablas. Busca <table> y cuenta <entry> o <td>."""
        filas = []
        for table in self.root.iter('table'):
            table_id = table.get('id', 'N/A')
            tabstyle = table.get('tabstyle', 'N/A')
            
            # Título
            title_elem = table.find('title')
            titulo = title_elem.text if title_elem is not None else "N/A"
            
            # Contar entradas. En legacy puede ser <entry> o <td> (HTML style)
            entries = list(table.iter('entry'))
            if not entries:
                entries = list(table.iter('td'))
                
            num_entradas = len(entries)
            
            filas.append({
                "table_id": table_id,
                "tabstyle": tabstyle,
                "titulo": titulo,
                "num_entradas": num_entradas
            })
        return pd.DataFrame(filas)

    def contar_y_extraer_taskset_en_techname(self):
        """C04: Task Sets. En legacy equivalen a las <task>."""
        # XPath: //content/procedure_content/task
        codigos = []
        # Buscamos en procedure_content para ser más específicos, o en todo el doc
        for task in self.root.iter('task'):
            # Filtramos tasks que sean de contenido (suelen tener número)
            num = task.get('number')
            if num:
                codigos.append(num)
        return len(codigos), codigos

    def extraer_subtareas(self):
        """C05: Subtareas. En legacy son <subtask>."""
        subtareas = []
        for sub in self.root.iter('subtask'):
            code = sub.get('number', 'N/A')
            title_elem = sub.find('title_subtask')
            name = title_elem.text if title_elem is not None else "N/A"
            subtareas.append((code, name))
        return subtareas, len(subtareas)

    def matriz_subtareas_pasos(self):
        """C06: Pasos. En legacy son <listitem> dentro de <subtask>."""
        filas = []
        for sub in self.root.iter('subtask'):
            code = sub.get('number', 'N/A')
            title_elem = sub.find('title_subtask')
            name = title_elem.text if title_elem is not None else "N/A"
            
            pasos = []
            # Buscamos listas dentro de la subtarea
            # A veces hay listas anidadas, contamos todos los listitem como pasos planos
            # para simplificar y aproximar la carga de trabajo.
            count = 0
            for lst in sub.iter('list'):
                for item in lst.findall('listitem'):
                    count += 1
                    # Intentamos sacar texto del primer para como título
                    para = item.find('para')
                    titulo_paso = para.text[:50] if para is not None and para.text else f"Step {count}"
                    pasos.append({"titulo": titulo_paso})
            
            if not pasos:
                continue

            # Construir fila
            row = {"codigo_subtarea": code, "nombre_subtarea": name}
            for i, p in enumerate(pasos, 1):
                row[f"step_{i}"] = p["titulo"]
            filas.append(row)
            
        return pd.DataFrame(filas)

    def matriz_referencias_internas(self):
        """C07: Referencias internas (<ref_figure>, <ref_part>, etc)."""
        filas = []
        tags_ref = ['ref_figure', 'ref_part', 'ref_tool', 'ref_cons']
        
        # Recorremos todo el árbol buscando estas etiquetas
        for elem in self.root.iter():
            tag = elem.tag.split('}', 1)[-1] # Quitar namespace si hay
            if tag in tags_ref:
                ref_id = elem.get('ref_id') or elem.get('ref', 'N/A')
                filas.append({
                    "internalRefId": ref_id,
                    "internalRefTargetType": tag
                })
        return pd.DataFrame(filas)

    def _construir_mapa_docs(self):
        """Helper para C08/C09: Mapea id de tabla de referencias a su contenido."""
        doc_map = {}
        # Buscar en <tech_tables>/<references_document_tables>
        for rdt in self.root.iter('reference_document_tables'):
            rid = rdt.get('id')
            doc_ref = rdt.find('doc_reference')
            if rid and doc_ref is not None and doc_ref.text:
                doc_map[rid] = doc_ref.text.strip()
        return doc_map

    def extraer_dm_refs_con_subtareas(self):
        """C08: Referencias a DM (DMC-...)."""
        filas = []
        doc_map = self._construir_mapa_docs()
        
        for elem in self.root.iter('ref_document'):
            rid = elem.get('ref_id')
            if rid in doc_map:
                val = doc_map[rid]
                # Heurística simple: si contiene "DMC-", es un Data Module
                if "DMC-" in val:
                    filas.append({
                        "dmRef_id": rid,
                        "techName": val, # Usamos el código como techName
                        # Campos extra para compatibilidad con DF de S1000D
                        "modelIdentCode": "N/A", "systemCode": "N/A" 
                    })
        return pd.DataFrame(filas)

    def extraer_externalPub_refs_con_subtareas(self):
        """C09: Referencias Externas (No DMC)."""
        filas = []
        doc_map = self._construir_mapa_docs()
        
        for elem in self.root.iter('ref_document'):
            rid = elem.get('ref_id')
            if rid in doc_map:
                val = doc_map[rid]
                if "DMC-" not in val:
                    filas.append({"externalPubRef_id": rid})
        return pd.DataFrame(filas)

    def extraer_configuraciones(self):
        """C10: Configuraciones."""
        filas = []
        for conf in self.root.iter('configuration'):
            cid = conf.get('id', 'N/A')
            
            # Definición
            definition = conf.find('definition/para')
            def_text = definition.text if definition is not None else "N/A"
            
            # MSNs (rango)
            msns = []
            msns_elem = conf.find('msns')
            if msns_elem is not None:
                for m in msns_elem.iter():
                    if m.text and m.text.strip():
                        msns.append(m.text.strip())
            msn_text = ", ".join(msns) if msns else "N/A"

            filas.append({
                "config_name_tab": cid,
                "config_def_text": def_text,
                "msn_range": msn_text
            })
        return pd.DataFrame(filas)

    def extraer_sbIndividualSpare_con_sbSpareSet(self):
        """C11 (Spares) y C12 (Sets). En legacy: Kits y Componentes."""
        filas = []
        for kit in self.root.iter('kit'):
            kit_id = kit.get('id', 'N/A')
            kit_ref_elem = kit.find('reference')
            kit_name = kit_ref_elem.text if kit_ref_elem is not None else kit_id
            
            # Componentes dentro del kit
            for comp in kit.iter('component'):
                comp_id = comp.get('id', 'N/A')
                pn_elem = comp.find('new_part_number')
                comp_name = pn_elem.text if pn_elem is not None else "N/A"
                
                filas.append({
                    "sbIndividualSpare_name": comp_name,
                    "sbIndividualSpare_id": comp_id,
                    "sbSpareSet_id": kit_id,
                    "sbSpareSet_name": kit_name
                })
        return pd.DataFrame(filas)

    def extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet(self):
        """C13: Repuestos retirados."""
        filas = []
        # Buscar sección específica
        for section in self.root.iter('parts_removed_by_operator'):
            for comp in section.iter('component'):
                comp_id = comp.get('id', 'N/A')
                pn_elem = comp.find('old_part_number')
                name = pn_elem.text if pn_elem is not None else "N/A"
                
                filas.append({
                    "sbIndividualRemovedSpare_id": comp_id,
                    "sbIndividualRemovedSpare_name": name
                })
        return pd.DataFrame(filas)

    def extraer_tools_con_sbSupportEquipSet(self):
        """C14: Herramientas (Special y Standard)."""
        filas = []
        # Iteramos por las secciones (sets)
        for section_tag in ['special_tools', 'standard_tools']:
            for section in self.root.iter(section_tag):
                # Pero iteramos y guardamos cada <tool> individual
                for tool in section.iter('tool'):
                    tool_id = tool.get('id', 'N/A')
                    pn_elem = tool.find('part_number')
                    name = pn_elem.text if pn_elem is not None else "N/A"
                    
                    filas.append({
                        "sbIndividualSupportEquip_id": tool_id,
                        "tool_name": name,
                        "sbSupportEquipSet_id": section_tag # Solo informativo
                    })
        return pd.DataFrame(filas)

    def extraer_supplies_con_sbSupplySet(self):
        """C15: Consumibles."""
        filas = []
        for section in self.root.iter('consumable_materials'):
            for cons in section.iter('consumable'):
                cons_id = cons.get('id', 'N/A')
                # En legacy suele ser reference_cml o description
                desc_elem = cons.find('description')
                name = desc_elem.text if desc_elem is not None else "N/A"
                
                filas.append({
                    "sbIndividualSupply_id": cons_id,
                    "supply_name": name,
                    "sbSupplySet_id": "consumable_materials"
                })
        return pd.DataFrame(filas)

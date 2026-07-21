"""
    Calcula los contadores C01..C15 para un XML S1000D
    usando los métodos definidos en ``metodosrecuento``.

    Parámetros
    ----------
    ruta_xml : str
        Ruta al fichero XML a analizar.
    coeficientes : dict[str, float | str] or None
        Diccionario de coeficientes tal y como se obtiene desde la
        tabla de la GUI (por ejemplo: {'C01': '3', 'C02': '0.05', ...}).
        Si es None, solo se devuelven los valores de los contadores.

    Devuelve
    --------
    dict
        Diccionario con:
        - 'counters':  {'C01': valor, ..., 'C15': valor}
        - 'weights':   {'C01': {'count', 'coefficient', 'weight'}, ...}
        - 'total_weight': suma de todos los pesos
    """
import os
import re
import zipfile
import io
import xml.etree.ElementTree as ET
from collections import Counter
from metodosrecuento import metodosrecuento

def weightnewxml(ruta_xml, coeficientes=None):


    mr = metodosrecuento(ruta_xml)

    counters: dict[str, int] = {}

    # C01 - palabras de texto plano en para / notePara / warningAndCautionPara
    try:
        _, total_palabras = mr.extraer_palabras_texto_plano()
        counters["C01"] = int(total_palabras)
    except Exception:
        counters["C01"] = 0

    # C02 - gráficos (<graphic>)
    try:
        df_graph = mr.extraer_graphic_refs()
        counters["C02"] = int(len(df_graph))
    except Exception:
        counters["C02"] = 0

    # C03 - entradas de tablas (suma de entradas con contenido)
    try:
        # Usamos la misma extracción que en revised para consistencia (ignora entradas vacías)
        _, _, all_entries = mr.extraer_contenido_tablas_por_titulo()
        counters["C03"] = len(all_entries)
    except Exception:
        counters["C03"] = 0

    # C04 - task sets en <techName>
    try:
        _, items = mr.contar_y_extraer_taskset_en_techname()
        # Obtenemos los códigos normalizados de cada Task Set declarado
        norm_codes = []
        if items:
            for code, info_name in items:
                code_str = str(code).lower()
                m = re.search(r'\b(\d{3}-\d{3}-\d{3})\b', code_str)
                norm_code = m.group(1) if m else ' '.join(code_str.split())
                norm_codes.append(norm_code)
        counters["C04"] = len(norm_codes)
    except Exception:
        counters["C04"] = 0

    # C05 - subtareas "Task ..." (proceduralStep con título Task <codigo> <nombre>)
    try:
        subtareas, _ = mr.extraer_subtareas()
        norm_tasks = []
        if subtareas:
            for code, name in subtareas:
                # Normalizar código: a partir del primer guion (ej: 247219-941... -> 941...)
                parts = str(code).split('-', 1)
                norm_code = parts[1].strip() if len(parts) > 1 else str(code).strip()
                norm_name = ' '.join(str(name).split())
                norm_tasks.append((norm_code, norm_name))
        counters["C05"] = len(norm_tasks)
    except Exception:
        counters["C05"] = 0

    # C06 - pasos dentro de las subtareas (proceduralStepAlts)
    try:
        # Usamos la estructura de pasos (rutas anidadas) en lugar de la matriz plana
        structures = mr.extraer_estructura_pasos_por_subtarea()
        total_steps = sum(len(paths) for paths in structures.values())
        counters["C06"] = int(total_steps)
    except Exception:
        counters["C06"] = 0

    # C07 - referencias internas <internalRef>
    try:
        df_int = mr.matriz_referencias_internas()
        counters["C07"] = int(len(df_int))
    except Exception:
        counters["C07"] = 0

    # C08 - referencias a DMs <dmRef>
    try:
        df_dm = mr.extraer_dm_refs_con_subtareas()
        counters["C08"] = int(len(df_dm))
    except Exception:
        counters["C08"] = 0

    # C09 - referencias externas <externalPubRef>
    try:
        df_ext = mr.extraer_externalPub_refs_con_subtareas()
        counters["C09"] = int(len(df_ext))
    except Exception:
        counters["C09"] = 0

    # C10 - configuraciones (MSN by configuration / Configuration definition)
    try:
        df_cfg = mr.extraer_configuraciones()
        counters["C10"] = int(len(df_cfg))
    except Exception:
        counters["C10"] = 0

    # C11 / C12 - repuestos introducidos por sbIndividualSpare
    try:
        df_spares = mr.extraer_sbIndividualSpare_con_sbSpareSet()
        # C11: número total de sbIndividualSpare (únicos por atributos)
        if not df_spares.empty and "sbIndividualSpare_attrs" in df_spares.columns:
            counters["C11"] = len(set(df_spares["sbIndividualSpare_attrs"]))
        else:
            counters["C11"] = int(len(df_spares))
        # C12: número de sets de repuestos distintos (sbSpareSet_name menos 3 chars)
        if not df_spares.empty and "sbSpareSet_name" in df_spares.columns:
            # Normalizamos nombres quitando los últimos 3 caracteres (ej: ...R00)
            unique_sets = {str(n).strip()[:-3] for n in df_spares["sbSpareSet_name"] if n and str(n).strip()}
            unique_sets = {u for u in unique_sets if u} # Filtrar vacíos resultantes
            counters["C12"] = len(unique_sets)
        else:
            counters["C12"] = 0
    except Exception:
        counters["C11"] = 0
        counters["C12"] = 0

    # C13 - repuestos retirados <sbIndividualRemovedSpare>
    try:
        df_removed = mr.extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet()
        if not df_removed.empty and "sbIndividualRemovedSpare_attrs" in df_removed.columns:
            counters["C13"] = len(set(df_removed["sbIndividualRemovedSpare_attrs"]))
        else:
            counters["C13"] = int(len(df_removed))
    except Exception:
        counters["C13"] = 0

    # C14 - herramientas <sbIndividualSupportEquip>
    try:
        df_tools = mr.extraer_tools_con_sbSupportEquipSet()
        if not df_tools.empty and "sbIndividualSupportEquip_attrs" in df_tools.columns:
            counters["C14"] = len(set(df_tools["sbIndividualSupportEquip_attrs"]))
        else:
            counters["C14"] = int(len(df_tools))
    except Exception:
        counters["C14"] = 0

    # C15 - consumibles <sbIndividualSupply>
    try:
        df_supplies = mr.extraer_supplies_con_sbSupplySet()
        if not df_supplies.empty and "sbIndividualSupply_attrs" in df_supplies.columns:
            counters["C15"] = len(set(df_supplies["sbIndividualSupply_attrs"]))
        else:
            counters["C15"] = int(len(df_supplies))
    except Exception:
        counters["C15"] = 0

    # Si no se proporcionan coeficientes, devolvemos solo los contadores
    if coeficientes is None:
        return {"counters": counters, "weights": {}, "total_weight": 0.0}

    # Cálculo de pesos por contador usando el diccionario de coeficientes
    weights: dict[str, dict[str, float]] = {}
    total_weight = 0.0

    for idx in range(1, 16):
        key = f"C{idx:02d}"
        count = counters.get(key, 0)

        raw_coef = coeficientes.get(key, 0)
        try:
            coef = float(str(raw_coef).replace(",", "."))
        except (TypeError, ValueError):
            coef = 0.0

        weight_value = float(count) * coef
        total_weight += weight_value

        weights[key] = {
            "count": float(count),
            "coefficient": coef,
            "weight": weight_value,
        }

    return {
        "counters": counters,
        "weights": weights,
        "total_weight": total_weight,
    }




def weightrevisedxml(ruta_xml_original, ruta_xml_nuevo, coeficientes=None):
    
    
    """
    Calcula los contadores C01..C15 en modo Revised/Dummy comparando dos XML:
    - ``ruta_xml_original``: SB original
    - ``ruta_xml_nuevo``: SB revised/dummy

    Regla general: solo se contabilizan los elementos del XML nuevo que sean
    distintos respecto al original (por ID cuando aplique).

    Para C01 (texto plano) se aplica comparación tipo multiconjunto:
    por cada palabra del nuevo, si existe una "gemela" en el original se
    descuenta (no se cuenta); solo se cuentan las no emparejadas.
    """
    def _to_float(value):
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    def _safe_unique(values):
        try:
            return {str(v) for v in values if str(v).strip() and str(v) != "N/A"}
        except Exception:
            return set()

    def _diff_new_only(new_ids, old_ids):
        return len(set(new_ids) - set(old_ids))

    mr_old = metodosrecuento(ruta_xml_original)
    mr_new = metodosrecuento(ruta_xml_nuevo)

    counters: dict[str, int] = {}

    # C01 - texto plano: contar palabras nuevas (no emparejadas) vs original
    try:
        words_old, _ = mr_old.extraer_palabras_texto_plano()
        words_new, _ = mr_new.extraer_palabras_texto_plano()

        old_counts = Counter(w.casefold() for w in words_old)
        delta_words = 0
        for w in words_new:
            key = w.casefold()
            if old_counts.get(key, 0) > 0:
                old_counts[key] -= 1
            else:
                delta_words += 1

        counters["C01"] = int(delta_words)
    except Exception:
        counters["C01"] = 0

    # C02 - gráficos: ICN (infoEntityIdent) nuevos vs original
    try:
        df_old = mr_old.extraer_graphic_refs()
        df_new = mr_new.extraer_graphic_refs()

        old_icn = _safe_unique(df_old["infoEntityIdent"]) if "infoEntityIdent" in df_old.columns else set()
        new_icn = _safe_unique(df_new["infoEntityIdent"]) if "infoEntityIdent" in df_new.columns else set()

        # Si viniesen sin ICN, comparamos por id gráfico como fallback
        if not new_icn:
            old_icn = _safe_unique(df_old["graphic_id"]) if "graphic_id" in df_old.columns else set()
            new_icn = _safe_unique(df_new["graphic_id"]) if "graphic_id" in df_new.columns else set()

        counters["C02"] = int(_diff_new_only(new_icn, old_icn))
    except Exception:
        counters["C02"] = 0

    # C03 - tablas: lógica por título y contenido (sin IDs)
    try:
        old_titled, old_untitled, old_all = mr_old.extraer_contenido_tablas_por_titulo()
        new_titled, new_untitled, new_all = mr_new.extraer_contenido_tablas_por_titulo()
        
        total_new_entries = 0
        
        # 1. Tablas CON título en el nuevo: buscar en tabla con mismo título del viejo
        for titulo, new_entries in new_titled.items():
            old_entries = old_titled.get(titulo, [])
            # Diferencia de multiconjuntos: cuenta cuántas veces aparece el texto en new extra respecto a old
            diff = Counter(new_entries) - Counter(old_entries)
            total_new_entries += sum(diff.values())
            
        # 2. Tablas SIN título en el nuevo: buscar en TODO el documento viejo
        if new_untitled:
            diff = Counter(new_untitled) - Counter(old_all)
            total_new_entries += sum(diff.values())
            
        counters["C03"] = int(total_new_entries)
    except Exception:
        counters["C03"] = 0

    # C04 - task sets: códigos nuevos o incrementos en cantidad
    try:
        _n_old, items_old = mr_old.contar_y_extraer_taskset_en_techname()
        _n_new, items_new = mr_new.contar_y_extraer_taskset_en_techname()
        
        def get_norm_code(code):
            code_str = str(code).lower()
            m = re.search(r'\b(\d{3}-\d{3}-\d{3})\b', code_str)
            return m.group(1) if m else ' '.join(code_str.split())
            
        codes_old = [get_norm_code(t[0]) for t in items_old] if items_old else []
        codes_new = [get_norm_code(t[0]) for t in items_new] if items_new else []

        # Contamos la diferencia neta de elementos Task Set por cada código
        diff = Counter(codes_new) - Counter(codes_old)
        counters["C04"] = sum(diff.values())
    except Exception:
        counters["C04"] = 0


    # C05 - subtareas Task: (código, nombre) nuevos vs original
    try:
        subt_old, _ = mr_old.extraer_subtareas()
        subt_new, _ = mr_new.extraer_subtareas()
        
        def get_norm_task(code, name):
            # Código a partir del primer guion
            parts = str(code).split('-', 1)
            norm_code = parts[1].strip() if len(parts) > 1 else str(code).strip()
            norm_name = ' '.join(str(name).split())
            return (norm_code, norm_name)

        tasks_old = [get_norm_task(c, n) for c, n in subt_old] if subt_old else []
        tasks_new = [get_norm_task(c, n) for c, n in subt_new] if subt_new else []

        # Contamos la diferencia neta de elementos Subtarea por cada tupla (código, nombre)
        diff = Counter(tasks_new) - Counter(tasks_old)
        counters["C05"] = sum(diff.values())
    except Exception:
        counters["C05"] = 0
    
    # C06 - pasos: se compara la estructura anidada de proceduralSteps por subtarea
    try:
        # La función devuelve {nombre_subtarea: {set de rutas de estructura}}
        old_structures = mr_old.extraer_estructura_pasos_por_subtarea()
        new_structures = mr_new.extraer_estructura_pasos_por_subtarea()

        changed_steps = 0
        # Iteramos por las subtareas del XML nuevo
        for subtask_name, new_paths_set in new_structures.items():
            # Buscamos la misma subtarea (por nombre) en el XML viejo
            old_paths_set = old_structures.get(subtask_name, set())

            # Contamos las rutas de estructura que están en el nuevo pero no en el viejo.
            # Esto cubre tanto subtareas nuevas (old_paths_set estará vacío) como
            # subtareas modificadas.
            new_or_changed_paths = new_paths_set - old_paths_set
            changed_steps += len(new_or_changed_paths)
        
        counters["C06"] = int(changed_steps)
    except Exception:
        counters["C06"] = 0

    # C07 - internalRef: ids nuevos vs original
    try:
        df_old = mr_old.matriz_referencias_internas()
        df_new = mr_new.matriz_referencias_internas()
        old_ids = _safe_unique(df_old["internalRefId"]) if "internalRefId" in df_old.columns else set()
        new_ids = _safe_unique(df_new["internalRefId"]) if "internalRefId" in df_new.columns else set()
        counters["C07"] = int(_diff_new_only(new_ids, old_ids))
    except Exception:
        counters["C07"] = 0

    # C08 - dmRef: ids nuevos vs original
    try:
        df_old = mr_old.extraer_dm_refs_con_subtareas()
        df_new = mr_new.extraer_dm_refs_con_subtareas()
        old_ids = _safe_unique(df_old["dmRef_id"]) if "dmRef_id" in df_old.columns else set()
        new_ids = _safe_unique(df_new["dmRef_id"]) if "dmRef_id" in df_new.columns else set()
        counters["C08"] = int(_diff_new_only(new_ids, old_ids))
    except Exception:
        counters["C08"] = 0

    # C09 - externalPubRef: ids nuevos vs original
    try:
        df_old = mr_old.extraer_externalPub_refs_con_subtareas()
        df_new = mr_new.extraer_externalPub_refs_con_subtareas()
        old_ids = _safe_unique(df_old["externalPubRef_id"]) if "externalPubRef_id" in df_old.columns else set()
        new_ids = _safe_unique(df_new["externalPubRef_id"]) if "externalPubRef_id" in df_new.columns else set()
        counters["C09"] = int(_diff_new_only(new_ids, old_ids))
    except Exception:
        counters["C09"] = 0

    # C10 - configuraciones: filas nuevas vs original (tupla de valores)
    try:
        df_old = mr_old.extraer_configuraciones()
        df_new = mr_new.extraer_configuraciones()

        def rows_to_set(df):
            if df is None or df.empty:
                return set()
            cols = [c for c in ["config_name_tab", "msn_range", "config_def_text"] if c in df.columns]
            if not cols:
                return set()
            return {
                tuple(str(row[c]) for c in cols)
                for _, row in df[cols].fillna("N/A").iterrows()
            }

        counters["C10"] = int(_diff_new_only(rows_to_set(df_new), rows_to_set(df_old)))
    except Exception:
        counters["C10"] = 0

    # C11 - sbIndividualSpare: atributos nuevos vs original
    # C12 - sbSpareSet: nombres de set (menos 3 chars) nuevos vs original
    try:
        df_old = mr_old.extraer_sbIndividualSpare_con_sbSpareSet()
        df_new = mr_new.extraer_sbIndividualSpare_con_sbSpareSet()

        old_attrs = set(df_old["sbIndividualSpare_attrs"]) if not df_old.empty and "sbIndividualSpare_attrs" in df_old.columns else set()
        new_attrs = set(df_new["sbIndividualSpare_attrs"]) if not df_new.empty and "sbIndividualSpare_attrs" in df_new.columns else set()
        counters["C11"] = int(_diff_new_only(new_attrs, old_attrs))

        def get_norm_set_names(df):
            if df.empty or "sbSpareSet_name" not in df.columns:
                return set()
            # Normalizar: quitar últimos 3 chars y filtrar vacíos
            return {str(n).strip()[:-3] for n in df["sbSpareSet_name"] if n and str(n).strip() and str(n).strip()[:-3]}

        old_set_names = get_norm_set_names(df_old)
        new_set_names = get_norm_set_names(df_new)
        counters["C12"] = int(_diff_new_only(new_set_names, old_set_names))
    except Exception:
        counters["C11"] = 0
        counters["C12"] = 0

    # C13 - removed spares: atributos nuevos vs original
    try:
        df_old = mr_old.extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet()
        df_new = mr_new.extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet()
        old_attrs = set(df_old["sbIndividualRemovedSpare_attrs"]) if not df_old.empty and "sbIndividualRemovedSpare_attrs" in df_old.columns else set()
        new_attrs = set(df_new["sbIndividualRemovedSpare_attrs"]) if not df_new.empty and "sbIndividualRemovedSpare_attrs" in df_new.columns else set()
        counters["C13"] = int(_diff_new_only(new_attrs, old_attrs))
    except Exception:
        counters["C13"] = 0

    # C14 - tools: atributos nuevos vs original
    try:
        df_old = mr_old.extraer_tools_con_sbSupportEquipSet()
        df_new = mr_new.extraer_tools_con_sbSupportEquipSet()
        old_attrs = set(df_old["sbIndividualSupportEquip_attrs"]) if not df_old.empty and "sbIndividualSupportEquip_attrs" in df_old.columns else set()
        new_attrs = set(df_new["sbIndividualSupportEquip_attrs"]) if not df_new.empty and "sbIndividualSupportEquip_attrs" in df_new.columns else set()
        counters["C14"] = int(_diff_new_only(new_attrs, old_attrs))
    except Exception:
        counters["C14"] = 0

    # C15 - supplies: atributos nuevos vs original
    try:
        df_old = mr_old.extraer_supplies_con_sbSupplySet()
        df_new = mr_new.extraer_supplies_con_sbSupplySet()
        old_attrs = set(df_old["sbIndividualSupply_attrs"]) if not df_old.empty and "sbIndividualSupply_attrs" in df_old.columns else set()
        new_attrs = set(df_new["sbIndividualSupply_attrs"]) if not df_new.empty and "sbIndividualSupply_attrs" in df_new.columns else set()
        counters["C15"] = int(_diff_new_only(new_attrs, old_attrs))
    except Exception:
        counters["C15"] = 0

    if coeficientes is None:
        return {"counters": counters, "weights": {}, "total_weight": 0.0}

    weights = {}
    total_weight = 0.0
    for idx in range(1, 16):
        key = f"C{idx:02d}"
        count = counters.get(key, 0)
        coef = _to_float(coeficientes.get(key, 0))
        w = float(count) * coef
        total_weight += w
        weights[key] = {"count": float(count), "coefficient": coef, "weight": w}

    return {"counters": counters, "weights": weights, "total_weight": total_weight}

def get_xml_content(zip_path, keyword):
    """Extrae el contenido de un XML (930 o 933) de un ZIP en memoria."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            candidates = [n for n in z.namelist() if keyword in n and n.lower().endswith('.xml')]
            if not candidates:
                return None, None
            # Tomamos el primero que coincida
            target = candidates[0]
            return io.BytesIO(z.read(target)), target
    except Exception:
        return None, None

def comparar_zips(zip_path_old, zip_path_new, coeficientes=None):
    """Compara dos ZIPs (Original vs Revised) analizando módulos 930 y 933."""
    total_w = 0.0
    details = {}
    
    zip_name = os.path.basename(zip_path_new)
    old_name = os.path.basename(zip_path_old)

    for key in ["930", "933"]:
        c_old, n_old = get_xml_content(zip_path_old, key)
        c_new, n_new = get_xml_content(zip_path_new, key)
        
        if c_old and c_new:
            w = weightrevisedxml(c_old, c_new, coeficientes)
            total_w += w["total_weight"]
            details[key] = w
        elif c_new:
            # Si falta el original, procesamos como New
            w = weightnewxml(c_new, coeficientes)
            total_w += w["total_weight"]
            details[key] = w
            
    return {"Zip": zip_name, "Type": f"REVISED (vs {old_name})", "Total Weight": total_w, "Details": details}

def revisiones_y_originales(folder_path, coeficientes=None):
    """
    Recorre la carpeta buscando ZIPs.
    Agrupa por nombre base y sufijo -XX.
    Si encuentra par (Original, Revised), compara.
    Si no, procesa como New.
    Extrae XMLs 930 y 933 en memoria.
    """
    results = []
    
    if not os.path.isdir(folder_path):
        return results

    files = [f for f in os.listdir(folder_path) if f.lower().endswith('.zip')]
    
    # Agrupar: BASE -> [(suffix, filename), ...]
    # Regex: algo + guion + 2 digitos + .zip
    pattern = re.compile(r'^(.*)-(\d{2})\.zip$', re.IGNORECASE)
    groups = {}
    
    for f in files:
        m = pattern.match(f)
        if m:
            base = m.group(1)
            suffix = int(m.group(2))
            if base not in groups: groups[base] = []
            groups[base].append((suffix, f))
        else:
            # Sin sufijo -XX, tratar como grupo único (New)
            groups[f] = [(-1, f)]
            
    for base, file_list in groups.items():
        file_list.sort(key=lambda x: x[0]) # Ordenar por sufijo
        
        # Determinar si es Revised (pareja) o New
        if len(file_list) >= 2:
            # Tomamos los dos últimos: penúltimo (original) y último (revised)
            orig_ver = file_list[-2]
            rev_ver = file_list[-1]
            
            orig_path = os.path.join(folder_path, orig_ver[1])
            rev_path = os.path.join(folder_path, rev_ver[1])
            
            # Usamos la nueva función compartida
            res = comparar_zips(orig_path, rev_path, coeficientes)
            # Ajustamos el nombre del Zip para que sea solo el nombre de archivo, no la ruta completa si comparar_zips devolviera ruta
            res["Zip"] = rev_ver[1] 
            results.append(res)
        
        else:
            # Caso New (único archivo o sin sufijo)
            curr_ver = file_list[-1]
            zip_path = os.path.join(folder_path, curr_ver[1])
            
            total_w = 0.0
            details = {}
            
            for key in ["930", "933"]:
                content, name = get_xml_content(zip_path, key)
                if content:
                    w = weightnewxml(content, coeficientes)
                    total_w += w["total_weight"]
                    details[key] = w
                    
            results.append({"Zip": curr_ver[1], "Type": "NEW", "Total Weight": total_w, "Details": details})
                    
    return results
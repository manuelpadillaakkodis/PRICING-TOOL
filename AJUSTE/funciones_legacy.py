import pandas as pd
from metodosrecuento_legacy import metodosrecuento_legacy

def weightlegacyxml(ruta_xml, coeficientes=None):
    """
    Calcula los contadores C01..C15 para un XML Legacy (AMSB)
    usando los métodos definidos en ``metodosrecuento_legacy``.

    Parámetros
    ----------
    ruta_xml : str
        Ruta al fichero XML a analizar.
    coeficientes : dict[str, float | str] or None
        Diccionario de coeficientes (ej: {'C01': '0.1', ...}).
        Si es None, solo se devuelven los contadores.

    Devuelve
    --------
    dict
        Diccionario con:
        - 'counters':  {'C01': valor, ..., 'C15': valor}
        - 'weights':   {'C01': {'count', 'coefficient', 'weight'}, ...}
        - 'total_weight': suma de todos los pesos
    """
    mr = metodosrecuento_legacy(ruta_xml)
    counters = {}

    # C01 - Palabras (Texto Plano)
    try:
        _, total_palabras = mr.extraer_palabras_texto_plano()
        counters["C01"] = int(total_palabras)
    except Exception:
        counters["C01"] = 0

    # C02 - Gráficos
    try:
        df_graph = mr.extraer_graphic_refs()
        counters["C02"] = int(len(df_graph))
    except Exception:
        counters["C02"] = 0

    # C03 - Tablas (entradas)
    try:
        df_tablas = mr.extraer_tablas_con_entradas()
        if not df_tablas.empty and "num_entradas" in df_tablas.columns:
            counters["C03"] = int(df_tablas["num_entradas"].sum())
        else:
            counters["C03"] = 0
    except Exception:
        counters["C03"] = 0

    # C04 - Task Sets (Tasks en legacy)
    try:
        total_taskset, codigos_taskset = mr.contar_y_extraer_taskset_en_techname()
        # En legacy, cada <task> cuenta, usamos len(set) por si hay duplicados técnicos
        counters["C04"] = int(len(set(codigos_taskset))) if codigos_taskset else int(total_taskset)
    except Exception:
        counters["C04"] = 0

    # C05 - Subtareas
    try:
        subtareas, _ = mr.extraer_subtareas()
        if subtareas:
            # subtareas es lista de tuplas (codigo, nombre)
            codigos = {codigo for codigo, _nombre in subtareas}
            counters["C05"] = int(len(codigos))
        else:
            counters["C05"] = 0
    except Exception:
        counters["C05"] = 0

    # C06 - Pasos
    try:
        df_pasos = mr.matriz_subtareas_pasos()
        if not df_pasos.empty:
            # Columnas de pasos (step_1, step_2...)
            step_cols = [c for c in df_pasos.columns if c.startswith("step_") and not c.endswith("_id")]
            # En la matriz legacy, 0 es padding (sin paso)
            counters["C06"] = int((df_pasos[step_cols] != 0).sum().sum())
        else:
            counters["C06"] = 0
    except Exception:
        counters["C06"] = 0

    # C07 - Referencias internas
    try:
        df_int = mr.matriz_referencias_internas()
        counters["C07"] = int(len(df_int))
    except Exception:
        counters["C07"] = 0

    # C08 - Referencias a DM (DMC-...)
    try:
        df_dm = mr.extraer_dm_refs_con_subtareas()
        counters["C08"] = int(len(df_dm))
    except Exception:
        counters["C08"] = 0

    # C09 - Referencias Externas (No DMC)
    try:
        df_ext = mr.extraer_externalPub_refs_con_subtareas()
        counters["C09"] = int(len(df_ext))
    except Exception:
        counters["C09"] = 0

    # C10 - Configuraciones
    try:
        df_cfg = mr.extraer_configuraciones()
        counters["C10"] = int(len(df_cfg))
    except Exception:
        counters["C10"] = 0

    # C11 - Repuestos (Spares)
    try:
        df_spares = mr.extraer_sbIndividualSpare_con_sbSpareSet()
        counters["C11"] = int(len(df_spares))
        
        # C12 - Sets de Repuestos
        if not df_spares.empty and "sbSpareSet_id" in df_spares.columns:
            counters["C12"] = int(df_spares["sbSpareSet_id"].nunique())
        else:
            counters["C12"] = 0
    except Exception:
        counters["C11"] = 0
        counters["C12"] = 0

    # C13 - Repuestos Retirados
    try:
        df_removed = mr.extraer_sbIndividualRemovedSpare_con_sbRemovedSpareSet()
        counters["C13"] = int(len(df_removed))
    except Exception:
        counters["C13"] = 0

    # C14 - Herramientas
    try:
        df_tools = mr.extraer_tools_con_sbSupportEquipSet()
        counters["C14"] = int(len(df_tools))
    except Exception:
        counters["C14"] = 0

    # C15 - Consumibles
    try:
        df_supplies = mr.extraer_supplies_con_sbSupplySet()
        counters["C15"] = int(len(df_supplies))
    except Exception:
        counters["C15"] = 0

    # Cálculo de pesos
    if coeficientes is None:
        return {"counters": counters, "weights": {}, "total_weight": 0.0}

    weights = {}
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

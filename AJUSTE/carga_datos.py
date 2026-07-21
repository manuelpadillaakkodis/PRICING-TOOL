"""
carga_datos.py — Funciones de carga de datos para ajuste/reajuste de coeficientes.

Gestiona la lectura de:
  - Listas de SBs con puntos facturados (Excel sin cabecera)
  - Coeficientes iniciales de un ajuste previo (Excel con hojas Coeficientes/Matriz_A/Detalle)

Columna D (opcional): si una fila incluye en la 4ª columna el identificador de
otro SB, ese SB se procesará en modo "dummy"; es decir, sus contadores se
calcularán de forma DIFERENCIAL (revised) comparándolo contra el SB de
referencia indicado. Ese peso comparado es el que se usa para calibrar los
coeficientes.
"""

import os
import re
import pandas as pd
import numpy as np


def _norm_ref(valor):
    """
    Normaliza un identificador de SB de referencia (columna D) a str o None.
    Trata None, NaN, cadena vacía y la cadena 'nan' como ausencia de referencia.
    """
    if valor is None or pd.isna(valor):
        return None
    txt = str(valor).strip()
    return txt if txt and txt.lower() != "nan" else None


def _ref_dummy_columna_d(row):
    """
    Devuelve el identificador de SB de referencia (columna D, índice 3) si la
    fila lo trae y no está vacío; en caso contrario None.
    """
    if len(row) <= 3:
        return None
    return _norm_ref(row[3])


def cargar_lista_sb_con_filtros(ruta_excel):
    """
    Lee un Excel con SBs y pesos, aplicando los filtros del primer disparo:
      - Solo aviones objetivo (A400M, 295, 235, 212)
      - Excluye prefijos SBA400M46- y SBA400M24- (salvo S1000D con col C='X' y
        referencia en col D, que se admiten para pesado comparativo)
      - Solo revisión -00 (los S1000D con col C = 'X' quedan exentos de este filtro)
      - Detecta prioridad (col C = 'X')
      - Detecta SB de referencia para modo dummy (col D)

    Formato esperado (sin cabecera):
      Col A: Nombre del SB
      Col B: Peso / puntos
      Col C (opcional): 'X' marca el SB como S1000D (prioritario). Además exime
                        del filtro de revisión -00, admitiendo revisiones y dummies.
      Col D (opcional): identificador de un SB de referencia. Si se rellena,
                        el SB se pesa como dummy (diferencial) contra ese SB.

    Devuelve
    --------
    list of dict con claves:
      'sb_name', 'peso', 'es_prioritario', 'usar_metodo_nuevo', 'sb_dummy_ref'
    """
    if not os.path.exists(ruta_excel):
        raise FileNotFoundError(f"El archivo no existe: {ruta_excel}")

    df = pd.read_excel(ruta_excel, header=None)
    resultado = []

    for _, row in df.iterrows():
        if len(row) < 2:
            continue

        sb_ref = row[0]
        peso_ref = row[1]

        if pd.isna(sb_ref) or pd.isna(peso_ref):
            continue

        sb_name = str(sb_ref).strip()
        sb_clean = re.sub(r'\.(xml|zip)$', '', sb_name, flags=re.IGNORECASE)

        # Si no tiene sufijo de revisión (ej. -00, -01, etc.), se le asigna -00 por defecto
        match_rev = re.search(r'-(\d{2})(?:-[A-Z]{1,2})?$', sb_clean, re.IGNORECASE)
        if not match_rev:
            sb_clean = sb_clean + "-00"
            sb_name = sb_name + "-00"
            match_rev = re.search(r'-(\d{2})(?:-[A-Z]{1,2})?$', sb_clean, re.IGNORECASE)

        # Solo aviones objetivo
        es_avion_objetivo = ("A400M" in sb_clean.upper() or
                             any(x in sb_clean for x in ["295", "235", "212"]))
        if not es_avion_objetivo:
            continue

        # Detectar prioridad / S1000D en Col C ('X')
        es_prioritario = False
        usar_metodo_nuevo = False
        if len(row) > 2:
            val_c = row[2]
            if not pd.isna(val_c) and str(val_c).strip().upper() == 'X':
                es_prioritario = True
                usar_metodo_nuevo = True

        # SB de referencia para modo dummy (Col D)
        sb_dummy_ref = _ref_dummy_columna_d(row)

        # Excluir prefijos no deseados (ATA 24 y ATA 46 que no sean S1000D/prioritarios)
        es_ata_24_46 = (
            re.search(r'A400M(24|46)', sb_clean, re.IGNORECASE) is not None or
            re.search(r'(295|235|212)[-_/\s]?(24|46)', sb_clean, re.IGNORECASE) is not None
        )
        if es_ata_24_46 and not es_prioritario:
            print(f"[INFO] Saltando {sb_name}: ATA 24/46 excluido para SBs legacy.")
            continue

        # Filtrado por revisión -00.
        # Los SB S1000D (Col C = 'X') quedan EXENTOS de este filtro: pueden ser
        # revisiones (distintas de -00) o dummies (Col D) y se pesan de forma
        # comparativa. El resto de SBs siguen exigiendo revisión -00.
        if not es_prioritario:
            match_rev = re.search(r'-(\d{2})(?:-[A-Z]{1,2})?$', sb_clean, re.IGNORECASE)
            if not match_rev:
                print(f"[INFO] Saltando {sb_name}: Formato de revisión no reconocido.")
                continue
            if match_rev.group(1) != "00":
                print(f"[INFO] Saltando {sb_name}: Revisión '{match_rev.group(1)}' (se requiere '00').")
                continue

        # Validar peso numérico
        try:
            peso = float(peso_ref)
            if np.isnan(peso):
                continue
        except (ValueError, TypeError):
            continue

        # El modo dummy usa el motor S1000D (módulos 930/933): se lee como ZIP.
        if sb_dummy_ref is not None:
            usar_metodo_nuevo = True

        resultado.append({
            'sb_name': sb_name,
            'peso': peso,
            'es_prioritario': es_prioritario,
            'usar_metodo_nuevo': usar_metodo_nuevo,
            'sb_dummy_ref': sb_dummy_ref,
        })

    return resultado


def cargar_lista_sb_simple(ruta_excel):
    """
    Lee una lista de SBs con puntos facturados (formato simple, sin filtros).

    Formato (sin cabecera):
      Col A: Nombre del SB
      Col B: Puntos facturados
      Col C (opcional): 'X' marca el SB como S1000D (prioritario)
      Col D (opcional): identificador de un SB de referencia. Si se rellena,
                        el SB se pesa como dummy (diferencial) contra ese SB.

    Devuelve
    --------
    pd.DataFrame con columnas ['sb_name', 'puntos', 'es_prioritario', 'sb_dummy_ref']
    """
    df = pd.read_excel(ruta_excel, header=None)

    # Si la primera fila parece cabecera (no numérica en col 1), saltarla
    try:
        float(df.iloc[0, 1])
    except (ValueError, TypeError):
        df = df.iloc[1:].reset_index(drop=True)

    # Construir columnas por posición (robusto aunque haya más de 2 columnas)
    out = pd.DataFrame()
    
    # Procesar nombres de SBs añadiendo -00 si no tienen revisión
    raw_names = df.iloc[:, 0].astype(str).str.strip().tolist()
    clean_names = []
    for name in raw_names:
        sb_clean = re.sub(r'\.(xml|zip)$', '', name, flags=re.IGNORECASE)
        match_rev = re.search(r'-(\d{2})(?:-[A-Z]{1,2})?$', sb_clean, re.IGNORECASE)
        if not match_rev:
            clean_names.append(sb_clean + "-00")
        else:
            clean_names.append(sb_clean)
            
    out['sb_name'] = clean_names
    out['puntos'] = pd.to_numeric(df.iloc[:, 1], errors='coerce')

    # Col C (índice 2): Prioritario ('X' = S1000D)
    if df.shape[1] > 2:
        out['es_prioritario'] = df.iloc[:, 2].astype(str).str.strip().str.upper() == 'X'
    else:
        out['es_prioritario'] = False

    # Col D (índice 3): SB de referencia para modo dummy (si existe la columna)
    if df.shape[1] > 3:
        out['sb_dummy_ref'] = [_norm_ref(v) for v in df.iloc[:, 3].tolist()]
    else:
        out['sb_dummy_ref'] = None

    out = out.dropna(subset=['puntos']).reset_index(drop=True)

    # Filtrar ATA 24 y ATA 46 que no son prioritarios (no S1000D)
    keep_indices = []
    for idx, row in out.iterrows():
        name = row['sb_name']
        es_prio = row['es_prioritario']
        es_ata_24_46 = (
            re.search(r'A400M(24|46)', name, re.IGNORECASE) is not None or
            re.search(r'(295|235|212)[-_/\s]?(24|46)', name, re.IGNORECASE) is not None
        )
        if es_ata_24_46 and not es_prio:
            continue
        keep_indices.append(idx)
    out = out.iloc[keep_indices].reset_index(drop=True)

    return out


def cargar_coeficientes_desde_excel(ruta_excel):
    """
    Lee coeficientes iniciales de un Excel de ajuste previo.

    Esperamos hojas:
      - 'Coeficientes': columnas [Contador, Coeficiente]
      - 'Matriz_A' (opcional): contadores C01..C15
      - 'Detalle' o 'Análisis por SB' (opcional): pesos reales y nombres

    Devuelve
    --------
    dict con:
      'x0':       np.array(15) coeficientes
      'A_orig':   np.array o None (Matriz A)
      'b_orig':   np.array o None (pesos reales)
      'sbs_orig': list o None (nombres SBs)
    """
    xls = pd.ExcelFile(ruta_excel)

    # --- Coeficientes ---
    if "Coeficientes" not in xls.sheet_names:
        raise ValueError("El Excel no contiene la hoja 'Coeficientes'.")

    df_coefs = pd.read_excel(xls, sheet_name="Coeficientes")
    coef_dict = dict(zip(df_coefs.iloc[:, 0], df_coefs.iloc[:, 1]))
    x0 = np.array([coef_dict.get(f"C{i+1:02d}", 0.0) for i in range(15)])

    # --- Vector b y nombres (opcional) ---
    b_orig = None
    sbs_orig = None
    df_det = None
    
    if "Análisis por SB" in xls.sheet_names:
        df_det = pd.read_excel(xls, sheet_name="Análisis por SB")
        col_real = ("Peso Real (puntos)" if "Peso Real (puntos)" in df_det.columns
                    else "Peso Real")
        if col_real in df_det.columns:
            b_orig = df_det[col_real].values
        sbs_orig = df_det["Nombre SB"].tolist() if "Nombre SB" in df_det.columns else None
    elif "Detalle" in xls.sheet_names:
        df_det = pd.read_excel(xls, sheet_name="Detalle")
        if "Real" in df_det.columns:
            b_orig = df_det["Real"].values
        sbs_orig = df_det["SB"].tolist() if "SB" in df_det.columns else None

    # --- Matriz A original (opcional) ---
    A_orig = None
    if "Matriz_A" in xls.sheet_names:
        df_A = pd.read_excel(xls, sheet_name="Matriz_A")
        cols_to_drop = [c for c in ["SB", "Nombre SB"] if c in df_A.columns]
        if cols_to_drop:
            # La Matriz_A sí tiene la columna de nombres de SBs (nueva versión)
            sbs_orig = df_A[cols_to_drop[0]].tolist()
            df_A_numeric = df_A.drop(columns=cols_to_drop)
            A_orig = df_A_numeric.values
            
            # Alinear b_orig si existe df_det
            if df_det is not None and sbs_orig is not None:
                col_sb = "Nombre SB" if "Nombre SB" in df_det.columns else "SB"
                col_real = ("Peso Real (puntos)" if "Peso Real (puntos)" in df_det.columns
                            else ("Peso Real" if "Peso Real" in df_det.columns else "Real"))
                if col_sb in df_det.columns and col_real in df_det.columns:
                    sb_to_b = dict(zip(df_det[col_sb].astype(str).str.strip(), df_det[col_real]))
                    b_orig = np.array([sb_to_b.get(str(name).strip(), 0.0) for name in sbs_orig], dtype=float)
        else:
            # La Matriz_A NO tiene la columna de nombres de SBs (versión antigua)
            # Mapeamos usando el orden de sbs_orig y b_orig cargados de la hoja de detalles (mismo orden)
            A_orig = df_A.values

    return {
        'x0': x0,
        'A_orig': A_orig,
        'b_orig': b_orig,
        'sbs_orig': sbs_orig,
    }


def cargar_datos_ajuste_manual(ruta_excel):
    """
    Carga Matriz A, vector b, coeficientes y nombres desde un Excel previo
    para la ventana de ajuste manual.

    Devuelve
    --------
    tuple (A, b, x_orig, sbs_names) o lanza excepción
    """
    xls = pd.ExcelFile(ruta_excel)

    if "Matriz_A" not in xls.sheet_names:
        raise ValueError("El Excel no contiene la hoja 'Matriz_A'.")

    df_A = pd.read_excel(xls, sheet_name="Matriz_A")

    # Leer hoja de detalles primero si existe
    df_det = None
    if "Análisis por SB" in xls.sheet_names:
        df_det = pd.read_excel(xls, sheet_name="Análisis por SB")
    elif "Detalle" in xls.sheet_names:
        df_det = pd.read_excel(xls, sheet_name="Detalle")

    sbs_names = None
    b = None
    
    cols_to_drop = [c for c in ["SB", "Nombre SB"] if c in df_A.columns]
    if cols_to_drop:
        # Nueva versión: Matriz_A tiene los nombres
        sbs_names = df_A[cols_to_drop[0]].tolist()
        df_A_numeric = df_A.drop(columns=cols_to_drop)
        A = df_A_numeric.values
        
        # Alinear b
        if df_det is not None:
            col_sb = "Nombre SB" if "Nombre SB" in df_det.columns else "SB"
            col_real = ("Peso Real" if "Peso Real" in df_det.columns
                        else ("Peso Real (puntos)" if "Peso Real (puntos)" in df_det.columns else "Real"))
            if col_sb in df_det.columns and col_real in df_det.columns:
                sb_to_b = dict(zip(df_det[col_sb].astype(str).str.strip(), df_det[col_real]))
                b = np.array([sb_to_b.get(str(name).strip(), 0.0) for name in sbs_names], dtype=float)
    else:
        # Antigua versión: Matriz_A NO tiene nombres
        # Se mapea directamente en base al orden de la hoja de detalles (mismo orden)
        A = df_A.values
        if df_det is not None:
            col_sb = "Nombre SB" if "Nombre SB" in df_det.columns else "SB"
            col_real = ("Peso Real" if "Peso Real" in df_det.columns
                        else ("Peso Real (puntos)" if "Peso Real (puntos)" in df_det.columns else "Real"))
            if col_sb in df_det.columns:
                sbs_names = df_det[col_sb].tolist()
            if col_real in df_det.columns:
                b = df_det[col_real].values

    if sbs_names is None:
        raise ValueError("No se pudieron determinar los nombres de los SBs (falta hoja de detalles u columna de nombres).")
    if b is None:
        raise ValueError("No se pudo determinar el vector b de pesos reales (falta hoja de detalles u columna de peso real).")

    # Coeficientes
    if "Coeficientes" not in xls.sheet_names:
        raise ValueError("No se encontró la hoja 'Coeficientes'.")

    df_coefs = pd.read_excel(xls, sheet_name="Coeficientes")
    coef_dict = dict(zip(df_coefs.iloc[:, 0], df_coefs.iloc[:, 1]))
    x_orig = np.array([coef_dict.get(f"C{i+1:02d}", 0.0) for i in range(15)])

    return A, b, x_orig, sbs_names

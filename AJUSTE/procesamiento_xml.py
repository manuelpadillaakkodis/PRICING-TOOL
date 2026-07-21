"""
procesamiento_xml.py — Procesamiento de XMLs para construir la Matriz A.

Gestiona la lectura de archivos XML (Legacy) y ZIP (S1000D con módulos 930/933)
para extraer los contadores C01..C15 de cada SB.

Modo dummy: si para un SB se indica un SB de referencia (columna D del Excel),
sus contadores se calculan de forma DIFERENCIAL (revised) comparando el SB
contra el de referencia, exactamente igual que el modo Dummy de la herramienta
de pesado. La comparación usa el motor S1000D (módulos 930/933).
"""

import os
import re
import numpy as np

# Importa los lectores de XML adaptándose a DÓNDE estén físicamente los ficheros:
#   1) Si están en el subpaquete  AJUSTE/lector_xml/   -> se usa esta opción.
#   2) Si están "planos" junto a este archivo (AJUSTE/) -> se usa el respaldo.
# De este modo funciona sin importar cómo estén organizadas las carpetas.
try:
    from .lector_xml.funciones_legacy import weightlegacyxml
    from .lector_xml.funcionespesado import weightnewxml, weightrevisedxml, get_xml_content
except ImportError:
    from .funciones_legacy import weightlegacyxml
    from .funcionespesado import weightnewxml, weightrevisedxml, get_xml_content


def _es_referencia_valida(valor):
    """True si 'valor' es un identificador de SB no vacío (columna D)."""
    if valor is None:
        return False
    txt = str(valor).strip()
    return txt != "" and txt.lower() != "nan"


def _resolver_ruta_sb(sb_name, carpeta_xmls, usar_metodo_nuevo):
    """
    Resuelve la ruta física de un SB dentro de la carpeta.

    Aplica la misma lógica de extensión (.zip / .xml) y el mismo fallback de
    quitar el prefijo "SB" que usa el resto del módulo.

    Devuelve la ruta existente o None si no se encuentra.
    """
    sb_name = str(sb_name).strip()
    
    # Determinar candidatos de nombres de archivos según el método sugerido
    candidatos = []
    if usar_metodo_nuevo is True:
        candidatos = [sb_name + ".zip", sb_name + ".xml"]
    elif usar_metodo_nuevo is False:
        candidatos = [sb_name + ".xml", sb_name + ".zip"]
    else:  # None
        if sb_name.lower().endswith(('.xml', '.zip')):
            candidatos = [sb_name]
        else:
            candidatos = [sb_name + ".xml", sb_name + ".zip"]

    for filename in candidatos:
        # 1. Comprobar ruta directa
        ruta_archivo = os.path.join(carpeta_xmls, filename)
        if os.path.exists(ruta_archivo):
            return ruta_archivo

        # 2. Comprobar quitando el prefijo "SB"
        alt_filename = filename
        has_sb = False
        if filename.upper().startswith("SB"):
            has_sb = True
            alt_filename = filename[2:]  # Quitar "SB"
            if alt_filename.startswith(("-", " ")):
                alt_filename = alt_filename[1:]
            alt_ruta = os.path.join(carpeta_xmls, alt_filename)
            if os.path.exists(alt_ruta):
                print(f"[INFO] Usando '{alt_filename}' en lugar de '{filename}'.")
                return alt_ruta

        # 3. Si tiene extensión .zip (o es un zip temporal), intentar quitar la revisión al final (ej: -00)
        name_no_ext, ext = os.path.splitext(filename)
        if ext.lower() == '.zip':
            name_no_rev = re.sub(r'-\d{2}$', '', name_no_ext, flags=re.IGNORECASE)
            if name_no_rev != name_no_ext:
                # Probar con prefijo "SB" pero sin revisión (ej: SBA400M24-7225.zip)
                filename_no_rev = name_no_rev + ext
                ruta_no_rev = os.path.join(carpeta_xmls, filename_no_rev)
                if os.path.exists(ruta_no_rev):
                    print(f"[INFO] Usando '{filename_no_rev}' en lugar de '{filename}'.")
                    return ruta_no_rev
                
                # Probar sin prefijo "SB" y sin revisión (ej: A400M24-7225.zip)
                if has_sb:
                    alt_name_no_ext, _ = os.path.splitext(alt_filename)
                    alt_name_no_rev = re.sub(r'-\d{2}$', '', alt_name_no_ext, flags=re.IGNORECASE)
                    alt_filename_no_rev = alt_name_no_rev + ext
                    ruta_alt_no_rev = os.path.join(carpeta_xmls, alt_filename_no_rev)
                    if os.path.exists(ruta_alt_no_rev):
                        print(f"[INFO] Usando '{alt_filename_no_rev}' en lugar de '{filename}'.")
                        return ruta_alt_no_rev

    return None


def _contadores_dummy(ruta_nuevo, ruta_original):
    """
    Calcula los contadores DIFERENCIALES (revised) de un SB (``ruta_nuevo``)
    comparado contra un SB de referencia (``ruta_original``), sumando los
    módulos 930 y 933 del ZIP S1000D.

    Reutiliza la misma lógica que el modo Dummy de funcionespesado:
      - Si el módulo existe en ambos ZIP -> comparación revised.
      - Si solo existe en el nuevo -> se cuenta como nuevo (weightnewxml).

    Devuelve dict {C01: v, ..., C15: v}.
    Lanza ValueError si no hay módulos 930/933 válidos.
    """
    contadores = {}
    found_modules = False
    for module_key in ["930", "933"]:
        c_new, _ = get_xml_content(ruta_nuevo, module_key)
        c_old, _ = get_xml_content(ruta_original, module_key)

        if c_new and c_old:
            found_modules = True
            res = weightrevisedxml(c_old, c_new, coeficientes=None)
            for k, v in res['counters'].items():
                contadores[k] = contadores.get(k, 0) + v
        elif c_new:
            # El original no tiene este módulo: su contenido cuenta como nuevo.
            found_modules = True
            res = weightnewxml(c_new, coeficientes=None)
            for k, v in res['counters'].items():
                contadores[k] = contadores.get(k, 0) + v

    if not found_modules:
        raise ValueError("Los ZIP no contienen módulos 930 ni 933 válidos para la comparación dummy.")

    return contadores


def procesar_sb_xml(sb_name, carpeta_xmls, usar_metodo_nuevo=None, sb_dummy_ref=None):
    """
    Procesa un SB individual para obtener su vector de contadores C01..C15.

    Parámetros
    ----------
    sb_name : str
        Nombre del SB (sin extensión o con .xml/.zip)
    carpeta_xmls : str
        Ruta a la carpeta que contiene los XMLs/ZIPs
    usar_metodo_nuevo : bool o None
        Si True, usa S1000D (ZIP). Si False, Legacy (XML).
        Si None, lo detecta automáticamente por el nombre.
    sb_dummy_ref : str o None
        Si se indica (columna D del Excel), el SB se pesa en modo DUMMY:
        sus contadores se calculan comparando ``sb_name`` (revised) contra
        ``sb_dummy_ref`` (original). La comparación usa el motor S1000D
        (módulos 930/933), por lo que ambos SB se leen como ZIP.

    Devuelve
    --------
    list[int] de 15 elementos [C01, ..., C15] o None si falla
    """
    es_dummy = _es_referencia_valida(sb_dummy_ref)

    # En modo dummy la comparación usa el motor S1000D (930/933): ambos SB son ZIP.
    if es_dummy:
        usar_metodo_nuevo = True
    elif usar_metodo_nuevo is None:
        usar_metodo_nuevo = sb_name.upper().startswith("SBA400M")

    ruta_archivo = _resolver_ruta_sb(sb_name, carpeta_xmls, usar_metodo_nuevo)
    if ruta_archivo is None:
        return None

    try:
        # ----- Modo DUMMY: contadores diferenciales contra el SB de referencia -----
        if es_dummy:
            ruta_ref = _resolver_ruta_sb(sb_dummy_ref, carpeta_xmls, usar_metodo_nuevo=True)
            if ruta_ref is None:
                print(f"[ERROR] SB de referencia '{sb_dummy_ref}' no encontrado "
                      f"(dummy de '{sb_name}').")
                return None
            contadores = _contadores_dummy(ruta_archivo, ruta_ref)
            return [contadores.get(f"C{i:02d}", 0) for i in range(1, 16)]

        # ----- Modo normal (recuento total) -----
        # Detectar el método real según la extensión del archivo físico encontrado
        metodo_nuevo_real = ruta_archivo.lower().endswith('.zip')

        contadores = {}
        if metodo_nuevo_real:
            found_modules = False
            for module_key in ["930", "933"]:
                content, _ = get_xml_content(ruta_archivo, module_key)
                if content:
                    found_modules = True
                    res = weightnewxml(content, coeficientes=None)
                    for k, v in res['counters'].items():
                        contadores[k] = contadores.get(k, 0) + v
            if not found_modules:
                raise ValueError("El ZIP no contiene módulos 930 ni 933 válidos.")
        else:
            resultado = weightlegacyxml(ruta_archivo, coeficientes=None)
            contadores = resultado['counters']

        return [contadores.get(f"C{i:02d}", 0) for i in range(1, 16)]

    except Exception as e:
        print(f"[ERROR] Fallo al procesar {sb_name}: {e}")
        return None


def construir_matriz_desde_lista_filtrada(lista_sbs, carpeta_xmls, callback=None):
    """
    Construye la Matriz A a partir de una lista filtrada de SBs
    (resultado de cargar_lista_sb_con_filtros).

    Parámetros
    ----------
    lista_sbs : list of dict
        Cada dict tiene: 'sb_name', 'peso', 'es_prioritario', 'usar_metodo_nuevo'
        y, opcionalmente, 'sb_dummy_ref' (SB de referencia para modo dummy).
    carpeta_xmls : str
    callback : callable(current, total, name) o None

    Devuelve
    --------
    dict con:
      'A':           np.array (n × 15)
      'b':           np.array (n,)
      'sbs':         list[str]
      'is_priority': np.array[bool]
      'errores':     list[str]
    """
    A_rows = []
    b_vec = []
    sbs_procesados = []
    is_priority = []
    errores = []

    total = len(lista_sbs)

    for idx, item in enumerate(lista_sbs):
        sb_name = item['sb_name']
        peso = item['peso']

        if callback:
            callback(idx + 1, total, sb_name)

        fila = procesar_sb_xml(
            sb_name, carpeta_xmls,
            item['usar_metodo_nuevo'],
            sb_dummy_ref=item.get('sb_dummy_ref'),
        )
        if fila is not None:
            A_rows.append(fila)
            b_vec.append(peso)
            sbs_procesados.append(sb_name)
            is_priority.append(item['es_prioritario'])
            etiqueta = "DUMMY" if _es_referencia_valida(item.get('sb_dummy_ref')) else "OK"
            print(f"[{etiqueta}] {sb_name}")
        else:
            errores.append(f"{sb_name} (No encontrado/error)")
            print(f"[AVISO] {sb_name}: No procesable")

    if not A_rows:
        return None

    return {
        'A': np.array(A_rows, dtype=float),
        'b': np.array(b_vec, dtype=float),
        'sbs': sbs_procesados,
        'is_priority': np.array(is_priority, dtype=bool),
        'errores': errores,
    }


def construir_matriz_con_reutilizacion(df_lista_sb, carpeta_xmls,
                                        A_orig=None, sbs_orig=None,
                                        callback=None):
    """
    Construye la Matriz A para el reajuste.
    Reutiliza contadores de SBs que existan en A_orig; procesa XMLs para el resto.

    Las filas dummy (con 'sb_dummy_ref') se recalculan SIEMPRE, porque sus
    contadores son diferenciales y podrían no coincidir con una fila previa
    calculada en modo total.

    Parámetros
    ----------
    df_lista_sb : pd.DataFrame con columnas ['sb_name', 'puntos'] y,
        opcionalmente, 'sb_dummy_ref' y 'es_prioritario'.
    carpeta_xmls : str
    A_orig : np.array o None
    sbs_orig : list o None
    callback : callable o None

    Devuelve
    --------
    dict con:
      'A':           np.array (n × 15)
      'b':           np.array (n,)
      'sbs':         list[str]
      'is_priority': np.array[bool]
      'fuente':      list[str] ('original', 'xml' o 'dummy')
      'errores':     list[str]
    """
    # Lookup de SBs originales
    orig_lookup = {}
    if A_orig is not None and sbs_orig is not None:
        for i, name in enumerate(sbs_orig):
            clean = str(name).strip()
            if clean not in orig_lookup:
                orig_lookup[clean] = A_orig[i]

    A_rows = []
    b_vec = []
    sbs_procesados = []
    is_priority = []
    fuente_list = []
    errores = []

    total = len(df_lista_sb)

    for idx, row in df_lista_sb.iterrows():
        sb_name = row['sb_name']
        puntos = row['puntos']
        sb_dummy_ref = row.get('sb_dummy_ref', None)
        es_dummy = _es_referencia_valida(sb_dummy_ref)
        es_prioritario = row.get('es_prioritario', False)

        if callback:
            callback(idx + 1, total, sb_name)

        # ¿Existe en el ajuste original? (los dummy se recalculan siempre)
        if not es_dummy and sb_name in orig_lookup:
            A_rows.append(orig_lookup[sb_name])
            b_vec.append(puntos)
            sbs_procesados.append(sb_name)
            is_priority.append(es_prioritario)
            fuente_list.append("original")
            print(f"[REUTILIZADO] {sb_name}")
            continue

        # Procesar XML (en modo normal o dummy según sb_dummy_ref)
        fila = procesar_sb_xml(sb_name, carpeta_xmls, sb_dummy_ref=sb_dummy_ref)
        if fila is not None:
            A_rows.append(fila)
            b_vec.append(puntos)
            sbs_procesados.append(sb_name)
            is_priority.append(es_prioritario)
            fuente_list.append("dummy" if es_dummy else "xml")
            print(f"[{'DUMMY' if es_dummy else 'XML'}] {sb_name}")
        else:
            errores.append(sb_name)
            print(f"[SKIP] {sb_name}")

    if not A_rows:
        return None

    return {
        'A': np.array(A_rows, dtype=float),
        'b': np.array(b_vec, dtype=float),
        'sbs': sbs_procesados,
        'is_priority': np.array(is_priority, dtype=bool),
        'fuente': fuente_list,
        'errores': errores,
    }

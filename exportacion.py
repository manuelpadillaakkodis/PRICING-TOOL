"""
exportacion.py — Generación de informes Excel para la herramienta de pesado.

Este módulo SOLO se encarga de exportar a Excel. No contiene ninguna lógica de
conteo ni de pesado: recibe los resultados ya calculados (exactamente la misma
estructura que devuelven `comparar_zips` / `weightnewxml` en `funcionespesado`):

    {
        "Zip":          <nombre del SB>,
        "Type":         "NEW" | "REVISED (vs ...)" | "DUMMY (vs ...)",
        "Total Weight": <float>,
        "Details":      { "930": {"weights": {...}, ...}, "933": {...} },
        # campos auxiliares opcionales que añade la GUI ("_previous", "_pair")
    }

Responsabilidades:
  - Versionar nombres de archivo para NO sobrescribir un informe existente.
  - Construir las hojas Resumen / Contadores / Detalle.
  - Exportar el modo normal, el modo dummy y la exportación CONJUNTA (un solo xlsx).
"""

import os
import pandas as pd

# Lista fija de contadores (la lógica de negocio sigue siendo C01..C15)
CONTADORES = [f"C{i:02d}" for i in range(1, 16)]


# --------------------------------------------------------------------------- #
#  VERSIONADO DE NOMBRES (no se pisa ningún informe existente)
# --------------------------------------------------------------------------- #
def generar_ruta_versionada(ruta):
    """
    Si `ruta` no existe, la devuelve tal cual. Si ya existe, devuelve la primera
    variante libre añadiendo " (2)", " (3)", ... antes de la extensión.

    Ej.:  reporte.xlsx  ->  reporte (2).xlsx  ->  reporte (3).xlsx
    """
    if not ruta:
        return ruta
    if not os.path.exists(ruta):
        return ruta

    base, ext = os.path.splitext(ruta)
    n = 2
    candidato = f"{base} ({n}){ext}"
    while os.path.exists(candidato):
        n += 1
        candidato = f"{base} ({n}){ext}"
    return candidato


# --------------------------------------------------------------------------- #
#  AGREGACIÓN POR CONTADOR (suma de los módulos 930 + 933)
# --------------------------------------------------------------------------- #
def agregar_por_contador(item):
    """
    Suma cantidades y pesos por contador a lo largo de todos los módulos del SB.

    Devuelve: {"C01": {"count", "coefficient", "weight"}, ..., "C15": {...}}
    """
    agg = {key: {"count": 0.0, "coefficient": 0.0, "weight": 0.0} for key in CONTADORES}
    for _modulo, data in item.get("Details", {}).items():
        weights = data.get("weights", {})
        for key in CONTADORES:
            info = weights.get(key, {})
            agg[key]["count"] += float(info.get("count", 0) or 0)
            agg[key]["weight"] += float(info.get("weight", 0) or 0)
            coef = info.get("coefficient", 0)
            if coef:  # el coeficiente es el mismo en todos los módulos
                agg[key]["coefficient"] = float(coef)
    return agg


def _es_diferencial(tipo):
    """True si el resultado es un pesado diferencial (revisión o dummy)."""
    t = str(tipo).upper()
    return ("REVISED" in t) or ("DUMMY" in t)


# --------------------------------------------------------------------------- #
#  CONSTRUCCIÓN DE HOJAS
# --------------------------------------------------------------------------- #
def _filas_resumen(resultados):
    """Una fila por SB: nombre, modo y peso total."""
    return [
        {
            "Nombre": item.get("Zip", ""),
            "Modo": item.get("Type", ""),
            "Total de puntos": item.get("Total Weight", 0),
        }
        for item in resultados
    ]


def _filas_contadores(resultados):
    """Vista compacta: una fila por SB con C01..C15 (cantidades) + peso total."""
    filas = []
    for item in resultados:
        agg = agregar_por_contador(item)
        fila = {"SB": item.get("Zip", ""), "Modo": item.get("Type", "")}
        for key in CONTADORES:
            fila[key] = agg[key]["count"]
        fila["Peso total"] = item.get("Total Weight", 0)
        filas.append(fila)
    return filas


def _filas_detalle(resultados):
    """Detalle: una fila por (SB, módulo, contador) con cantidad, coef. y peso."""
    filas = []
    for item in resultados:
        nombre = item.get("Zip", "")
        tipo = item.get("Type", "")
        total = item.get("Total Weight", 0)

        for modulo, data in item.get("Details", {}).items():
            weights = data.get("weights", {})
            for key in CONTADORES:
                info = weights.get(key, {"count": 0, "coefficient": 0, "weight": 0})
                filas.append({
                    "Archivo": nombre,
                    "Tipo": tipo,
                    "Módulo": modulo,
                    "Contador": key,
                    "Cantidad": info.get("count", 0),
                    "Coeficiente": info.get("coefficient", 0),
                    "Peso": info.get("weight", 0),
                })

        texto_total = "TOTAL DIFERENCIAS" if _es_diferencial(tipo) else "TOTAL NUEVO"
        filas.append({
            "Archivo": nombre, "Tipo": tipo, "Módulo": texto_total,
            "Contador": "", "Cantidad": "", "Coeficiente": "", "Peso": total,
        })
        filas.append({})  # fila vacía de separación visual
    return filas


def _escribir_hojas(writer, resultados, sufijo=""):
    """Escribe las hojas Resumen / Contadores / Detalle de un conjunto."""
    df_resumen = pd.DataFrame(_filas_resumen(resultados)).reindex(
        columns=["Nombre", "Modo", "Total de puntos"])
    #df_contadores = pd.DataFrame(_filas_contadores(resultados)).reindex(
    #    columns=["SB", "Modo"] + CONTADORES + ["Peso total"])
    df_detalle = pd.DataFrame(_filas_detalle(resultados)).reindex(
        columns=["Archivo", "Tipo", "Módulo", "Contador", "Cantidad", "Coeficiente", "Peso"])

    df_resumen.to_excel(writer, sheet_name=f"Resumen{sufijo}", index=False)
    #df_contadores.to_excel(writer, sheet_name=f"Contadores{sufijo}", index=False)
    df_detalle.to_excel(writer, sheet_name=f"Detalle{sufijo}", index=False)


# --------------------------------------------------------------------------- #
#  API PÚBLICA DE EXPORTACIÓN
# --------------------------------------------------------------------------- #
def exportar_resultados(resultados, ruta):
    """
    Exporta una lista de resultados (modo normal o modo dummy) a un .xlsx.
    El nombre se versiona si ya existe. Devuelve la ruta final escrita.
    """
    ruta = generar_ruta_versionada(ruta)
    with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
        _escribir_hojas(writer, resultados or [])
    return ruta


def exportar_combinado(resultados_normal, resultados_dummy, ruta):
    """
    Exporta AMBOS conjuntos (New&Revised + Dummy) a un ÚNICO .xlsx, con una hoja
    "Resumen global" y luego las hojas de cada pestaña. Versiona el nombre.
    Devuelve la ruta final escrita.
    """
    ruta = generar_ruta_versionada(ruta)
    resultados_normal = resultados_normal or []
    resultados_dummy = resultados_dummy or []

    with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
        # --- Resumen global (todos los SB de ambas pestañas en una sola tabla) ---
        filas = []
        for it in resultados_normal:
            filas.append({"Pestaña": "New & Revised", "Nombre": it.get("Zip", ""),
                          "Modo": it.get("Type", ""), "Total de puntos": it.get("Total Weight", 0)})
        for it in resultados_dummy:
            filas.append({"Pestaña": "Dummy", "Nombre": it.get("Zip", ""),
                          "Modo": it.get("Type", ""), "Total de puntos": it.get("Total Weight", 0)})
        if not filas:
            filas = [{"Pestaña": "", "Nombre": "Sin resultados", "Modo": "", "Total de puntos": ""}]
        pd.DataFrame(filas).reindex(
            columns=["Pestaña", "Nombre", "Modo", "Total de puntos"]
        ).to_excel(writer, sheet_name="Resumen global", index=False)

        # --- Hojas por pestaña ---
        if resultados_normal:
            _escribir_hojas(writer, resultados_normal, sufijo=" New-Rev")
        if resultados_dummy:
            _escribir_hojas(writer, resultados_dummy, sufijo=" Dummy")

    return ruta

"""
Script para extraer SBs (LTA) y sus pesos de múltiples archivos Excel en una carpeta.
Transforma los identificadores de SB al formato LTA y genera un archivo consolidado.
"""

import os
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox

def transformar_sb_lta(sb_string):
    """
    Transforma un identificador de SB de LTA al formato requerido.
    Ej: "SB-295-71-0007-01-Sp" -> "SB295-71-0007-01-E"
    Filtra para asegurar que solo sean códigos 295, 235 o 212.
    """
    sb_string = sb_string.strip()
    # 1. Quitar el primer guion si empieza con "SB-"
    if sb_string.upper().startswith("SB-"):
        transformed_sb = "SB" + sb_string[3:]
    else:
        transformed_sb = sb_string

    # Validar códigos de avión permitidos (295, 235, 212)
    if not any(transformed_sb.upper().startswith(prefix) for prefix in ["SB295", "SB235", "SB212"]):
        return None

    # 2. Mapear y cambiar el sufijo de idioma
    suffix_map = {
        "Sp": "E",
        "En": "I",
        "Fr": "F"
    }
    
    parts = transformed_sb.rsplit('-', 1)
    if len(parts) == 2:
        base, suffix = parts
        # Comprobar si el sufijo está en el mapa (insensible a mayúsculas)
        for key_map, value_map in suffix_map.items():
            if suffix.lower() == key_map.lower():
                return f"{base}-{value_map}"

    # Si no se encuentra un sufijo conocido, devolver el SB con el primer guion quitado
    return transformed_sb

def extraer_pesos_lta():
    # Configuración de Tkinter
    root = tk.Tk()
    root.withdraw()

    print("Seleccione la carpeta que contiene los archivos Excel de LTA...")
    carpeta_origen = filedialog.askdirectory(title="Seleccionar carpeta con Excels de LTA")
    
    if not carpeta_origen:
        print("Operación cancelada.")
        return

    archivos_excel = [f for f in os.listdir(carpeta_origen) if f.lower().endswith(('.xlsx', '.xls'))]
    
    if not archivos_excel:
        messagebox.showwarning("Aviso", "No se encontraron archivos Excel en la carpeta seleccionada.")
        return

    print(f"Procesando {len(archivos_excel)} archivos en: {carpeta_origen}")

    datos_extraidos = [] # Lista de tuplas (SB, Peso)

    for archivo in archivos_excel:
        ruta_completa = os.path.join(carpeta_origen, archivo)
        try:
            xls = pd.ExcelFile(ruta_completa)
            
            for nombre_hoja in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=nombre_hoja, header=None)
                
                idx_header = -1
                col_sb = -1
                col_weight = -1
                
                for i, row in df.head(50).iterrows():
                    row_str = [str(x).strip() for x in row.tolist()]
                    sb_matches = [j for j, x in enumerate(row_str) if "SB Ident" in x]
                    weight_matches = [j for j, x in enumerate(row_str) if "Weight assessment" in x]
                    
                    if sb_matches and weight_matches:
                        idx_header = i
                        col_sb = sb_matches[0]
                        col_weight = weight_matches[0]
                        break
                
                if idx_header != -1:
                    for i in range(idx_header + 1, len(df)):
                        row = df.iloc[i]
                        
                        if col_sb < len(row) and col_weight < len(row) and not pd.isna(row[col_sb]):
                            txt_sb = str(row[col_sb])
                            
                            # Aplicar transformación específica de LTA
                            sb_encontrado = transformar_sb_lta(txt_sb)
                            
                            if sb_encontrado:
                                try:
                                    val_weight = row[col_weight]
                                    if not pd.isna(val_weight):
                                        peso_encontrado = float(val_weight)
                                        datos_extraidos.append([sb_encontrado, peso_encontrado])
                                except (ValueError, TypeError):
                                    continue
        except Exception as e:
            print(f"Error leyendo {archivo}: {e}")

    if not datos_extraidos:
        messagebox.showinfo("Resultado", "No se encontraron SBs válidos en las columnas 'SB Ident'.")
        return

    df_resultado = pd.DataFrame(datos_extraidos, columns=["SB", "Peso"])
    df_resultado.drop_duplicates(inplace=True)

    ruta_excel_salida = os.path.join(carpeta_origen, "lista_sbs_lta_consolidada.xlsx")
    df_resultado.to_excel(ruta_excel_salida, index=False, header=False)
    print(f"\nArchivo Excel generado exitosamente: {ruta_excel_salida}")

    lista_sbs = df_resultado["SB"].tolist()
    ruta_txt_salida = os.path.join(carpeta_origen, "lista_sbs_lta_python.txt")
    with open(ruta_txt_salida, "w", encoding="utf-8") as f:
        f.write(str(lista_sbs))
    
    print("\nLISTA DE SBs EXTRAÍDOS (Formato Python):")
    print(lista_sbs)
    
    messagebox.showinfo("Proceso Terminado", f"Se han extraído {len(lista_sbs)} SBs de LTA.\nArchivos guardados en la carpeta de origen.")

if __name__ == "__main__":
    extraer_pesos_lta()
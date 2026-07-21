"""
Script para extraer SBs (A400M) y sus pesos de múltiples archivos Excel en una carpeta.
Genera un archivo consolidado y muestra la lista de SBs por pantalla.
"""

import os
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
import re

def extraer_pesos_a400m():
    # Configuración de Tkinter
    root = tk.Tk()
    root.withdraw()

    print("Seleccione la carpeta que contiene los archivos Excel...")
    carpeta_origen = filedialog.askdirectory(title="Seleccionar carpeta con Excels de origen")
    
    if not carpeta_origen:
        print("Operación cancelada.")
        return

    archivos_excel = [f for f in os.listdir(carpeta_origen) if f.lower().endswith(('.xlsx', '.xls'))]
    
    if not archivos_excel:
        messagebox.showwarning("Aviso", "No se encontraron archivos Excel en la carpeta seleccionada.")
        return

    print(f"Procesando {len(archivos_excel)} archivos en: {carpeta_origen}")

    datos_extraidos = [] # Lista de tuplas (SB, Peso, ArchivoOrigen)
    
    # Patrón actualizado para detectar SBs (ej: A400M-53-7176-00 o A400M87-7124-00-En)
    # Captura A400M seguido de caracteres y termina en dígito (para limpiar sufijos como -En)
    patron_sb = re.compile(r"(A400M[\w\d-]*\d)", re.IGNORECASE)

    for archivo in archivos_excel:
        ruta_completa = os.path.join(carpeta_origen, archivo)
        try:
            # Leemos el Excel. Usamos ExcelFile para iterar por hojas si es necesario
            xls = pd.ExcelFile(ruta_completa)
            
            for nombre_hoja in xls.sheet_names:
                # Leemos sin cabecera para procesar como matriz pura
                df = pd.read_excel(xls, sheet_name=nombre_hoja, header=None)
                
                # --- NUEVA LÓGICA: Buscar cabeceras específicas ---
                idx_header = -1
                col_sb = -1
                col_weight = -1
                
                # Buscamos en las primeras 50 filas para encontrar la cabecera
                for i, row in df.head(50).iterrows():
                    row_str = [str(x).strip() for x in row.tolist()]
                    
                    # Indices de columnas que contienen los textos clave
                    sb_matches = [j for j, x in enumerate(row_str) if "SB Ident" in x]
                    weight_matches = [j for j, x in enumerate(row_str) if "Weight assessment" in x]
                    
                    if sb_matches and weight_matches:
                        idx_header = i
                        col_sb = sb_matches[0]
                        col_weight = weight_matches[0]
                        break
                
                if idx_header != -1:
                    # Iteramos por las filas de datos (desde la fila siguiente al header)
                    for i in range(idx_header + 1, len(df)):
                        row = df.iloc[i]
                        
                        if col_sb < len(row) and col_weight < len(row):
                            txt_sb = str(row[col_sb]).strip()
                            # Extraer SB limpio usando regex
                            match = patron_sb.search(txt_sb)
                            
                            if match:
                                sb_encontrado = match.group(1)
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
        messagebox.showinfo("Resultado", "No se encontraron SBs que coincidan con el patrón 'A400M-...'")
        return

    # Crear DataFrame
    df_resultado = pd.DataFrame(datos_extraidos, columns=["SB", "Peso"])
    
    # Eliminar duplicados exactos si los hubiera (mismo SB y mismo peso)
    df_resultado.drop_duplicates(inplace=True)

    # Guardar en Excel
    ruta_salida = os.path.join(carpeta_origen, "lista_sbs_a400m_consolidada.xlsx")
    try:
        # Guardamos sin índice y sin cabecera (para que sea compatible directo con el script de coeficientes)
        # Columna A: SB, Columna B: Peso
        df_resultado.to_excel(ruta_salida, index=False, header=False)
        print(f"\nArchivo generado exitosamente: {ruta_salida}")
    except Exception as e:
        messagebox.showerror("Error al guardar", f"No se pudo guardar el archivo de salida:\n{e}")
        return

    # Imprimir lista en formato Python
    lista_sbs = df_resultado["SB"].tolist()
    
    print("\n" + "="*40)
    print("LISTA DE SBs EXTRAÍDOS (Formato Python):")
    print("="*40)
    print(lista_sbs)
    print("="*40)
    
    # Guardar también en un archivo de texto (.txt)
    ruta_txt = os.path.join(carpeta_origen, "lista_sbs_python.txt")
    try:
        with open(ruta_txt, "w", encoding="utf-8") as f:
            f.write(str(lista_sbs))
    except Exception as e:
        print(f"Error al guardar el txt: {e}")
    
    messagebox.showinfo("Proceso Terminado", f"Se han extraído {len(lista_sbs)} SBs.\nArchivos guardados:\n- {os.path.basename(ruta_salida)}\n- {os.path.basename(ruta_txt)}")

if __name__ == "__main__":
    extraer_pesos_a400m()

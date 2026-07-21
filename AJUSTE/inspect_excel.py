import pandas as pd
import os

excel_path = "Ajuste 1 definitivo.xlsx"
print("Exists:", os.path.exists(excel_path))
xls = pd.ExcelFile(excel_path)
print("Sheet names:", xls.sheet_names)

if "Matriz_A" in xls.sheet_names:
    df_A = pd.read_excel(xls, "Matriz_A")
    print("Matriz_A shape:", df_A.shape)
    print("Matriz_A columns:", list(df_A.columns))
    print("Matriz_A head:\n", df_A.head(5))

if "Análisis por SB" in xls.sheet_names:
    df_det = pd.read_excel(xls, "Análisis por SB")
    print("Análisis por SB shape:", df_det.shape)
    print("Análisis por SB columns:", list(df_det.columns))
    print("Análisis por SB head:\n", df_det.head(5))
elif "Detalle" in xls.sheet_names:
    df_det = pd.read_excel(xls, "Detalle")
    print("Detalle shape:", df_det.shape)
    print("Detalle columns:", list(df_det.columns))
    print("Detalle head:\n", df_det.head(5))

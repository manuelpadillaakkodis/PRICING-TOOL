"""
metricas.py — Cálculo de métricas y generación de reportes Excel.

Funciones para evaluar la calidad de un ajuste y exportar resultados
en formato Excel con múltiples hojas.
"""

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def calcular_metricas(A, b, x):
    """
    Calcula métricas de calidad del ajuste.

    Devuelve
    --------
    dict con: 'r2', 'mae', 'rmse', 'bias', 'residuals', 'predicciones'
    """
    pred = A @ x
    residuals = pred - b

    mae = np.mean(np.abs(residuals))
    mse = np.mean(residuals ** 2)
    rmse = np.sqrt(mse)
    bias = np.mean(residuals)

    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((b - np.mean(b)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

    return {
        'r2': r2,
        'mae': mae,
        'rmse': rmse,
        'bias': bias,
        'residuals': residuals,
        'predicciones': pred,
    }


def calcular_metricas_subgrupo(diferencias, b_subgrupo):
    """
    Calcula métricas para un subgrupo (ej: SBs S1000D).
    """
    mae = np.mean(np.abs(diferencias))
    rmse = np.sqrt(np.mean(diferencias ** 2))
    bias = np.mean(diferencias)

    ss_res = np.sum(diferencias ** 2)
    ss_tot = np.sum((b_subgrupo - np.mean(b_subgrupo)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

    return {'r2': r2, 'mae': mae, 'rmse': rmse, 'bias': bias}


def comparar_jerarquias(x_nuevo, x_inicial):
    """
    Compara el ranking de dos vectores de coeficientes.
    Usa ranking con empates (valores iguales obtienen el mismo rango).

    Devuelve
    --------
    df : pd.DataFrame, ranking_preservado : bool
    """
    nombres = [f"C{i+1:02d}" for i in range(15)]

    rank_ini_pos = rankdata(-x_inicial, method='min').astype(int)
    rank_new_pos = rankdata(-x_nuevo, method='min').astype(int)

    df = pd.DataFrame({
        'Coeficiente': nombres,
        'Valor Inicial': x_inicial,
        'Rank Inicial': rank_ini_pos,
        'Valor Nuevo': x_nuevo,
        'Rank Nuevo': rank_new_pos,
        'Delta Valor': x_nuevo - x_inicial,
        '% Cambio': np.where(x_inicial != 0,
                             (x_nuevo - x_inicial) / x_inicial * 100, 0.0),
        'Delta Rank': rank_new_pos - rank_ini_pos,
    })

    ranking_preservado = np.all(rank_ini_pos == rank_new_pos)
    return df, ranking_preservado


# =============================================================================
#  GENERACIÓN DE REPORTES EXCEL
# =============================================================================

def guardar_reporte_primer_disparo(ruta, x_full, A, b, sbs, final_weights,
                                    is_priority=None):
    """
    Guarda el reporte del cálculo del primer disparo (ajuste desde cero).
    """
    pred = A @ x_full
    diff = pred - b

    coefs_dict = {f"C{i+1:02d}": x_full[i] for i in range(15)}

    df_detalle = pd.DataFrame({
        "Nombre SB": sbs,
        "Peso Real (puntos)": b,
        "Peso Calculado (puntos)": pred,
        "Diferencia (puntos)": diff,
        "Desviación (%)": np.where(b != 0, (diff / b) * 100, 0.0),
        "Influencia Final": final_weights,
        "Estado": ["Ignorado (Outlier)" if w < 0.1 else "Activo"
                   for w in final_weights],
    })
    df_detalle = df_detalle.iloc[
        np.abs(df_detalle["Diferencia (puntos)"].values).argsort()[::-1]
    ]

    with pd.ExcelWriter(ruta, engine='openpyxl') as writer:
        pd.DataFrame(list(coefs_dict.items()),
                     columns=["Contador", "Coeficiente"]).to_excel(
            writer, sheet_name="Coeficientes", index=False
        )
        df_detalle.to_excel(writer, sheet_name="Análisis por SB", index=False)
        df_A = pd.DataFrame(A, columns=[f"C{i+1:02d}" for i in range(15)])
        df_A.insert(0, "SB", sbs)
        df_A.to_excel(
            writer, sheet_name="Matriz_A", index=False
        )


def guardar_reporte_reajuste(ruta, x_nuevo, x_inicial, A, b,
                              sbs, fuente_list, metricas, errores=None,
                              is_priority=None):
    """
    Guarda el reporte comparativo del reajuste con jerarquía.
    """
    with pd.ExcelWriter(ruta, engine='openpyxl') as writer:
        # Coeficientes (comparación)
        df_comp, ranking_ok = comparar_jerarquias(x_nuevo, x_inicial)
        df_comp.to_excel(writer, sheet_name="Coeficientes", index=False)

        # Análisis por SB
        pred = A @ x_nuevo
        diff = pred - b
        det_dict = {
            "Nombre SB": sbs,
            "Fuente": fuente_list if fuente_list else ["N/A"] * len(sbs),
            "Peso Real (puntos)": b,
            "Peso Calculado (puntos)": pred,
            "Diferencia (puntos)": diff,
            "Desviación (%)": np.where(b != 0, (diff / b) * 100, 0.0),
        }
        if is_priority is not None:
            det_dict["S1000D"] = ["X" if p else "" for p in is_priority]

        df_det = pd.DataFrame(det_dict)
        df_det = df_det.iloc[np.abs(diff).argsort()[::-1]]
        df_det.to_excel(writer, sheet_name="Análisis por SB", index=False)

        # Métricas
        met_names = ["R²", "MAE", "RMSE", "Bias", "SBs procesados",
                     "Ranking preservado", "Método"]
        met_vals = [
            f"{metricas['r2']:.6f}",
            f"{metricas['mae']:.4f}",
            f"{metricas['rmse']:.4f}",
            f"{metricas['bias']:.6f}",
            str(len(sbs)),
            "SÍ" if ranking_ok else "NO",
            metricas.get('metodo', 'N/A'),
        ]
        if 'best_weight' in metricas:
            met_names.append("Importancia S1000D (peso)")
            met_vals.append(f"{metricas['best_weight']:.1f}x")

        df_metricas = pd.DataFrame({
            "Métrica": met_names,
            "Valor": met_vals
        })
        df_metricas.to_excel(writer, sheet_name="Métricas", index=False)

        # Matriz A
        df_A = pd.DataFrame(A, columns=[f"C{i+1:02d}" for i in range(15)])
        df_A.insert(0, "SB", sbs)
        df_A.to_excel(
            writer, sheet_name="Matriz_A", index=False
        )

        # Errores
        if errores:
            pd.DataFrame({"SB no procesado": errores}).to_excel(
                writer, sheet_name="Errores", index=False
            )

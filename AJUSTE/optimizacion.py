"""
optimizacion.py — Algoritmos de optimización de coeficientes C01-C15.

Contiene:
  - Parameter tying (agrupación de variables)
  - Ajuste desde cero con IRLS + lsq_linear (primer disparo)
  - Reajuste con preservación de jerarquía (SLSQP con restricciones de orden)
  - Cálculos relajados y sin restricciones
"""

import sys
import numpy as np
import scipy.optimize
from scipy.stats import rankdata


# =============================================================================
#  PARAMETER TYING (AGRUPACIÓN)
# =============================================================================

# Grupos de contadores que comparten el mismo coeficiente:
IDX_REFS = [6, 7, 8]       # C07, C08, C09 (referencias)
IDX_LOGS = [10, 12, 13, 14] # C11, C13, C14, C15 (logística)
IDX_OTHERS = [0, 1, 2, 3, 4, 5, 9, 11]  # C01-C06, C10, C12 (individuales)

# Orden de columnas en A_red (10 variables):
# 0:C01, 1:C02, 2:C03, 3:C04, 4:C05, 5:C06, 6:C10, 7:C12, 8:Refs, 9:Logs


def construir_A_reducida(A):
    """
    Construye la Matriz A reducida con parameter tying.

    Devuelve (A_red, mapping)
    """
    A_red = A[:, IDX_OTHERS].copy()
    col_refs = np.sum(A[:, IDX_REFS], axis=1).reshape(-1, 1)
    col_logs = np.sum(A[:, IDX_LOGS], axis=1).reshape(-1, 1)
    A_red = np.hstack((A_red, col_refs, col_logs))

    mapping = {
        'idx_others': IDX_OTHERS,
        'idx_refs': IDX_REFS,
        'idx_logs': IDX_LOGS,
    }
    return A_red, mapping


def desempaquetar_coefs(x_red, mapping=None):
    """
    Reconstruye el vector de 15 coeficientes a partir del reducido de 10.
    """
    x_full = np.zeros(15)
    idx_others = IDX_OTHERS if mapping is None else mapping['idx_others']

    for red_i, full_i in enumerate(idx_others):
        x_full[full_i] = x_red[red_i]

    # Refs (pos 8) → C07, C08, C09
    for fi in IDX_REFS:
        x_full[fi] = x_red[8]

    # Logs (pos 9) → C11, C13, C14, C15
    for fi in IDX_LOGS:
        x_full[fi] = x_red[9]

    return x_full


def empaquetar_coefs(x_full, mapping=None):
    """
    Reduce un vector de 15 coeficientes a 10 (promediando grupos).
    """
    x_red = np.zeros(10)
    idx_others = IDX_OTHERS if mapping is None else mapping['idx_others']

    for red_i, full_i in enumerate(idx_others):
        x_red[red_i] = x_full[full_i]

    x_red[8] = np.mean([x_full[fi] for fi in IDX_REFS])
    x_red[9] = np.mean([x_full[fi] for fi in IDX_LOGS])

    return x_red


# =============================================================================
#  LOWER BOUNDS (JERARQUÍA POR DEFECTO DEL PRIMER DISPARO)
# =============================================================================

def crear_lb_jerarquia_defecto():
    """
    Crea los Lower Bounds según la jerarquía estándar del primer disparo.
    Devuelve np.array(10) para la Matriz reducida.
    """
    lb = np.ones(10) * 0.01
    lb[0] = 0.05    # C01 (Palabras)
    lb[8] = 0.10    # Refs (C07+C08+C09)
    lb[5] = 0.50    # C06 (Pasos)
    lb[2] = 0.50    # C03 (Tablas)
    lb[7] = 0.50    # C12 (Kits)
    lb[9] = 1.00    # Logs (C11+C13+C14+C15)
    lb[1] = 5.00    # C02 (Ilustraciones)
    lb[4] = 10.00   # C05 (Subtareas)
    lb[3] = 15.00   # C04 (Tareas)
    lb[6] = 50.00   # C10 (Configuración)
    return lb


# =============================================================================
#  AJUSTE DESDE CERO (PRIMER DISPARO)
# =============================================================================

def ajuste_primer_disparo(A, b, is_priority, peso_s1000d=1.0, max_iter_irls=700):
    """
    Calcula coeficientes desde cero usando IRLS con parameter tying y jerarquía.

    Es la lógica original de resolver_optimizacion_completa.

    Parámetros
    ----------
    A : np.array (n × 15)
    b : np.array (n,)
    is_priority : np.array[bool] (n,)
    peso_s1000d : float — Peso de importancia para SBs S1000D
    max_iter_irls : int

    Devuelve
    --------
    dict con:
      'x_full': np.array(15) — coeficientes óptimos
      'x_red':  np.array(10) — coeficientes reducidos
      'A_red':  np.array — Matriz reducida
      'r2', 'mae', 'rmse', 'bias': float
      'final_weights': np.array — pesos IRLS finales
      'best_weight': float — peso de importancia usado
    """
    A_red, mapping = construir_A_reducida(A)
    num_vars = A_red.shape[1]

    lb = crear_lb_jerarquia_defecto()
    ub = np.inf

    # Solución inicial
    res_init = scipy.optimize.lsq_linear(A_red, b, bounds=(lb, ub))
    best_x_red = res_init.x
    best_final_weights = np.ones(len(b))

    pred_init = A_red @ best_x_red
    ss_res = np.sum((pred_init - b) ** 2)
    ss_tot = np.sum((b - np.mean(b)) ** 2)
    best_r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    best_weight = 1.0

    # Vector de prioridades
    p_vec = np.where(is_priority, peso_s1000d, 1.0)

    # --- IRLS ---
    print(f"\n[IRLS] Iniciando ajuste robusto (Primer Disparo) - {len(b)} SBs...")
    sys.stdout.flush()
    res_curr = scipy.optimize.lsq_linear(A_red, b, bounds=(lb, ub))
    x_curr = res_curr.x
    tol = 1e-4
    delta = 1e-5
    weights = np.ones(len(b))

    for k in range(max_iter_irls):
        x_prev = x_curr.copy()
        pred = A_red @ x_curr
        residuals = np.abs(pred - b)

        # --- NUEVA LÓGICA DE PESOS ROBUSTOS (Mediana con decaimiento suave) ---
        error_tipico = np.median(residuals)
        scale = max(error_tipico, 1e-5) 
        ratio_error = residuals / scale
        umbral_tolerancia = 2.0
        
        weights = np.ones(len(b)) * p_vec
        outliers_mask = ratio_error > umbral_tolerancia
        weights[outliers_mask] = weights[outliers_mask] * (umbral_tolerancia / ratio_error[outliers_mask])
        
        weights = weights / np.mean(weights)
        # ---------------------------------------------------------------------

        sqrt_w = np.sqrt(weights)[:, np.newaxis]
        A_w = A_red * sqrt_w
        b_w = b * np.sqrt(weights)

        res_iter = scipy.optimize.lsq_linear(A_w, b_w, bounds=(lb, ub))
        x_curr = res_iter.x

        # Calcular métricas para mostrar la evolución en cada iteración
        pred_full = A_red @ x_curr
        ss_res = np.sum((pred_full - b) ** 2)
        ss_tot = np.sum((b - np.mean(b)) ** 2)
        r2_curr = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        mae_curr = np.mean(np.abs(pred_full - b))
        rmse_curr = np.sqrt(np.mean((pred_full - b) ** 2))
        
        print(f"  [IRLS] Iteración {k+1:03d}/{max_iter_irls:03d} | R² Real: {r2_curr:.6f} | RMSE: {rmse_curr:.4f} | MAE: {mae_curr:.4f} | Error típico: {error_tipico:.4f}")
        sys.stdout.flush()

        if np.linalg.norm(x_curr - x_prev) < tol:
            print(f"[IRLS] Convergió en iteración {k+1}")
            sys.stdout.flush()
            break

    # Evaluar
    pred_final = A_red @ x_curr
    ss_res = np.sum((pred_final - b) ** 2)
    r2_curr = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    if r2_curr > best_r2:
        best_r2 = r2_curr
        best_x_red = x_curr
        best_weight = peso_s1000d
        best_final_weights = weights

    # Desempaquetar
    x_full = desempaquetar_coefs(best_x_red)

    # Métricas finales
    from .metricas import calcular_metricas
    metricas = calcular_metricas(A, b, x_full)

    return {
        'x_full': x_full,
        'x_red': best_x_red,
        'A_red': A_red,
        'r2': metricas['r2'],
        'mae': metricas['mae'],
        'rmse': metricas['rmse'],
        'bias': metricas['bias'],
        'final_weights': best_final_weights,
        'best_weight': best_weight,
        'predicciones': metricas['predicciones'],
        'residuals': metricas['residuals'],
    }


def ajuste_relajado(A, b):
    """
    Cálculo relajado: mantiene agrupaciones pero sin jerarquía de precios.
    """
    A_red, mapping = construir_A_reducida(A)
    lb_relaxed = np.ones(A_red.shape[1]) * 0.01
    res = scipy.optimize.lsq_linear(A_red, b, bounds=(lb_relaxed, np.inf))
    x_full = desempaquetar_coefs(res.x)

    from .metricas import calcular_metricas
    metricas = calcular_metricas(A, b, x_full)
    return {'x_full': x_full, **metricas}


def ajuste_sin_restricciones(A, b):
    """
    Cálculo sin restricciones: solo positivos.
    """
    res = scipy.optimize.lsq_linear(A, b, bounds=(0, np.inf))
    x_full = res.x

    from .metricas import calcular_metricas
    metricas = calcular_metricas(A, b, x_full)
    return {'x_full': x_full, **metricas}


# =============================================================================
#  REAJUSTE CON PRESERVACIÓN DE JERARQUÍA
# =============================================================================

def reajuste_con_jerarquia(A, b, x0_full, lambda_jerarquia=1.0,
                            mantener_grupos=True, callback=None,
                            is_priority=None, peso_s1000d=1.0):
    """
    Re-optimiza coeficientes preservando la jerarquía (ranking + proporciones).

    Minimiza:
      ||A·x - b||²  +  λ · Σ (ratio_actual / ratio_original - 1)²

    Con restricciones de orden:
      Si x0[i] > x0[j], entonces x[i] ≥ x[j] + ε

    Devuelve
    --------
    dict con: 'x_full', 'r2', 'mae', 'rmse', 'bias', 'converged', 'message'
    """
    epsilon_orden = 0.001

    if is_priority is not None and peso_s1000d != 1.0:
        p_vec = np.where(is_priority, peso_s1000d, 1.0)
        p_vec = p_vec / np.mean(p_vec) # Normalizar pesos
        sqrt_w = np.sqrt(p_vec)
        A_work_base = A * sqrt_w[:, np.newaxis]
        b_work_base = b * sqrt_w
    else:
        A_work_base = A.copy()
        b_work_base = b.copy()

    if mantener_grupos:
        A_work, mapping = construir_A_reducida(A_work_base)
        x0_work = empaquetar_coefs(x0_full)
        n_vars = 10
    else:
        A_work = A_work_base
        x0_work = x0_full.copy()
        n_vars = 15

    b_scale = np.max(np.abs(b_work_base)) if np.max(np.abs(b_work_base)) > 0 else 1.0

    # Función objetivo
    def objetivo(x):
        pred = A_work @ x
        ssr = np.sum((pred - b_work_base) ** 2) / (b_scale ** 2)

        pen_ratio = 0.0
        if lambda_jerarquia > 0:
            for i in range(n_vars):
                for j in range(n_vars):
                    if i != j and x0_work[j] > epsilon_orden and x0_work[i] > epsilon_orden:
                        ratio_orig = x0_work[i] / x0_work[j]
                        ratio_actual = x[i] / max(x[j], epsilon_orden)
                        pen_ratio += (ratio_actual / ratio_orig - 1.0) ** 2
            pen_ratio *= lambda_jerarquia

        return ssr + pen_ratio

    # Gradiente
    def gradiente(x):
        pred = A_work @ x
        residuals = pred - b_work_base
        grad_ssr = 2.0 * (A_work.T @ residuals) / (b_scale ** 2)

        grad_pen = np.zeros(n_vars)
        if lambda_jerarquia > 0:
            for i in range(n_vars):
                for j in range(n_vars):
                    if i != j and x0_work[j] > epsilon_orden and x0_work[i] > epsilon_orden:
                        ratio_orig = x0_work[i] / x0_work[j]
                        ratio_actual = x[i] / max(x[j], epsilon_orden)
                        diff_ratio = ratio_actual / ratio_orig - 1.0
                        grad_pen[i] += 2.0 * diff_ratio / (ratio_orig * max(x[j], epsilon_orden))
                        grad_pen[j] -= 2.0 * diff_ratio * x[i] / (ratio_orig * max(x[j], epsilon_orden) ** 2)
            grad_pen *= lambda_jerarquia

        return grad_ssr + grad_pen

    # Restricciones de orden (consecutivas en ranking)
    constraints = []
    sorted_indices = np.argsort(-x0_work)
    for k in range(len(sorted_indices) - 1):
        i = sorted_indices[k]
        j = sorted_indices[k + 1]
        if x0_work[i] > x0_work[j]:
            constraints.append({
                'type': 'ineq',
                'fun': lambda x, i=i, j=j: x[i] - x[j] - epsilon_orden
            })

    bounds = [(0.001, None) for _ in range(n_vars)]

    iter_count = [0]
    def slsqp_callback(xk):
        iter_count[0] += 1
        x_full_current = desempaquetar_coefs(xk) if mantener_grupos else xk
        from .metricas import calcular_metricas
        met = calcular_metricas(A, b, x_full_current)
        msg = f"    [SLSQP] Iter {iter_count[0]:03d} → R²: {met['r2']:.6f} | RMSE: {met['rmse']:.4f}"
        if callback:
            callback(msg)
        else:
            print(msg)

    result = scipy.optimize.minimize(
        objetivo, x0_work,
        method='SLSQP', jac=gradiente,
        bounds=bounds, constraints=constraints,
        callback=slsqp_callback,
        options={'maxiter': 2000, 'ftol': 1e-12, 'disp': False}
    )

    x_opt = desempaquetar_coefs(result.x) if mantener_grupos else result.x

    from .metricas import calcular_metricas
    metricas = calcular_metricas(A, b, x_opt)

    return {
        'x_full': x_opt,
        'converged': result.success,
        'message': result.message,
        'metodo': f"SLSQP (λ={lambda_jerarquia})",
        'best_weight': peso_s1000d,
        **metricas,
    }


def irls_con_jerarquia(A, b, x0_full, max_iter=500, lambda_jerarquia=1.0,
                       mantener_grupos=True, callback=None,
                       is_priority=None, peso_s1000d=1.0):
    """
    IRLS robusto envolviendo reajuste_con_jerarquia con ponderación de prioridad.
    """
    x_curr = x0_full.copy()
    tol = 1e-4
    best_x = x_curr.copy()
    best_r2 = -np.inf

    p_vec = np.ones(len(b))
    if is_priority is not None and peso_s1000d != 1.0:
        p_vec = np.where(is_priority, peso_s1000d, 1.0)

    def _emit(msg):
        if callback:
            callback(msg)
        else:
            print(msg)

    for k in range(max_iter):
        x_prev = x_curr.copy()

        pred = A @ x_curr
        residuals = np.abs(pred - b)
        # --- NUEVA LÓGICA DE PESOS ROBUSTOS (Mediana con decaimiento suave) ---
        error_tipico = np.median(residuals)
        scale = max(error_tipico, 1e-5) 
        ratio_error = residuals / scale
        umbral_tolerancia = 2.0
        
        weights = np.ones(len(b)) * p_vec
        outliers_mask = ratio_error > umbral_tolerancia
        weights[outliers_mask] = weights[outliers_mask] * (umbral_tolerancia / ratio_error[outliers_mask])
        
        weights = weights / np.mean(weights)
        # ---------------------------------------------------------------------

        sqrt_w = np.sqrt(weights)
        A_w = A * sqrt_w[:, np.newaxis]
        b_w = b * sqrt_w

        num_outliers = int(np.sum(outliers_mask))
        _emit(f"\n[IRLS] ═══ Iteración {k+1}/{max_iter} ═══")
        _emit(f"  → Error típico (mediana de residuos): {error_tipico:.4f}")
        _emit(f"  → SBs anómalos (outliers) detectados: {num_outliers}/{len(b)} — se les reduce peso.")
        _emit(f"  → Lanzando sub-optimización SLSQP (con datos ponderados)...")

        res = reajuste_con_jerarquia(
            A_w, b_w, x_curr, lambda_jerarquia, mantener_grupos, callback=_emit
        )
        x_curr = res['x_full']

        # Evaluar sin ponderación
        from .metricas import calcular_metricas
        m_real = calcular_metricas(A, b, x_curr)
        
        _emit(f"  → SLSQP finalizado: {res.get('message', 'OK')}")
        _emit(f"  → R² REAL (sin ponderar): {m_real['r2']:.6f} | RMSE REAL: {m_real['rmse']:.4f} | MAE: {m_real['mae']:.4f}")

        if m_real['r2'] > best_r2:
            mejora = m_real['r2'] - best_r2 if best_r2 > -np.inf else 0.0
            best_r2 = m_real['r2']
            best_x = x_curr.copy()
            if k > 0:
                _emit(f"  ★ Nuevo mejor R²: {best_r2:.6f} (+{mejora:.6f})")

        diff_norm = np.linalg.norm(x_curr - x_prev)
        _emit(f"  → Δ coeficientes: {diff_norm:.6f}  (umbral convergencia: {tol:.6f})")

        if diff_norm < tol:
            _emit(f"\n[IRLS] ✓ ¡Convergencia alcanzada en la iteración {k+1}!")
            _emit(f"  → Los coeficientes se han estabilizado (Δ={diff_norm:.2e} < tol={tol:.2e}).")
            break

    from .metricas import calcular_metricas
    metricas = calcular_metricas(A, b, best_x)

    return {
        'x_full': best_x,
        'metodo': f"IRLS+SLSQP (λ={lambda_jerarquia}, {min(k+1, max_iter)} iters)",
        'best_weight': peso_s1000d,
        **metricas,
    }


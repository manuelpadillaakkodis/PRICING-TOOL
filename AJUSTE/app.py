"""
app.py — Aplicación principal GUI para Ajuste y Reajuste de Coeficientes.

Punto de entrada: python -m AJUSTE.app  (o  python AJUSTE/app.py)

Funcionalidades:
  1. Ajuste desde cero (Primer Disparo): Excel + XMLs → coeficientes óptimos
  2. Reajuste con Jerarquía: coefs previos + nueva lista SBs → coefs re-optimizados
  3. Ajuste Manual: importar Excel previo y modificar coefs manualmente
"""

import os
import sys

# ---------------------------------------------------------------------------
#  BOOTSTRAP DE IMPORTACIONES
#  Hace que la aplicación se comporte igual tanto si se ejecuta:
#     (a) como módulo del paquete:   python -m AJUSTE.app
#     (b) como script suelto:        python app.py        (desde cualquier sitio)
#     (c) como ejecutable .exe:      app.exe              (compilado, PyInstaller)
#  y SIN depender del nombre de la carpeta que contiene el paquete: si renombras
#  "AJUSTE" a cualquier otra cosa, sigue funcionando.
#
#  Cómo: cuando el módulo NO se está ejecutando ya dentro de un paquete
#  (caso b y c), añadimos la carpeta padre (y la del ejecutable congelado)
#  al sys.path y fijamos __package__ a partir del nombre real de la carpeta
#  (técnica de PEP 366). Así las importaciones relativas (from .modulo)
#  resuelven correctamente en todos los casos.
# ---------------------------------------------------------------------------
if not __package__:
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _parent_dir = os.path.dirname(_this_dir)
    # En ejecutables PyInstaller los módulos se extraen bajo sys._MEIPASS.
    for _p in (_parent_dir, getattr(sys, "_MEIPASS", None)):
        if _p and _p not in sys.path:
            sys.path.insert(0, _p)
    __package__ = os.path.basename(_this_dir)

import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog

# Imports del paquete (relativos: no dependen del nombre de la carpeta)
from .carga_datos import (
    cargar_lista_sb_con_filtros,
    cargar_lista_sb_simple,
    cargar_coeficientes_desde_excel,
    cargar_datos_ajuste_manual,
)
from .procesamiento_xml import (
    construir_matriz_desde_lista_filtrada,
    construir_matriz_con_reutilizacion,
)
from .optimizacion import (
    ajuste_primer_disparo,
    ajuste_relajado,
    ajuste_sin_restricciones,
    reajuste_con_jerarquia,
    irls_con_jerarquia,
    desempaquetar_coefs,
)
from .metricas import (
    calcular_metricas,
    calcular_metricas_subgrupo,
    comparar_jerarquias,
    guardar_reporte_primer_disparo,
    guardar_reporte_reajuste,
)
from .ajuste_manual import AdjustmentWindow


def obtener_archivos_no_usados(carpeta_xml, sbs_usados):
    """
    Compara los archivos físicos de carpeta_xml contra la lista sbs_usados
    usando una normalización de nombres para encontrar cuáles no se han usado.
    """
    import os
    import re
    if not carpeta_xml or not os.path.exists(carpeta_xml):
        return []
        
    try:
        archivos = [f for f in os.listdir(carpeta_xml) if f.lower().endswith(('.xml', '.zip'))]
    except Exception:
        return []

    def normalizar(nombre):
        n = nombre.lower().strip()
        # Quitar extensión .xml o .zip
        n = re.sub(r'\.(xml|zip)$', '', n)
        # Quitar prefijo "sb" seguido opcionalmente de espacio, guion o guion bajo
        n = re.sub(r'^sb[-_ ]?', '', n)
        # Quitar sufijo de revisión al final (ej: -00, -01)
        n = re.sub(r'-\d{2}$', '', n)
        # Quitar caracteres no alfanuméricos
        n = re.sub(r'[^a-z0-9]', '', n)
        return n

    usados_norm = {normalizar(sb) for sb in sbs_usados if sb}
    
    no_usados = []
    for f in archivos:
        f_norm = normalizar(f)
        if f_norm not in usados_norm:
            no_usados.append(f)
            
    return sorted(no_usados)


# =============================================================================
#  FLUJO 1: AJUSTE DESDE CERO (PRIMER DISPARO)
# =============================================================================

def flujo_ajuste_desde_cero(ruta_excel, carpeta_xmls, parent_window=None):
    """
    Ejecuta el flujo completo de ajuste desde cero:
    1. Lee Excel con SBs y pesos (con filtros)
    2. Procesa XMLs → Matriz A
    3. Optimiza con IRLS + parameter tying + jerarquía
    4. Muestra resultados y ofrece guardar
    5. Ofrece cálculos relajado/sin restricciones si la calidad es baja
    6. Ofrece ajuste manual
    """
    if not ruta_excel or not carpeta_xmls:
        messagebox.showwarning("Faltan datos",
                               "Seleccione el Excel y la carpeta de XMLs.")
        return

    if not os.path.exists(ruta_excel):
        messagebox.showerror("Error", "El archivo Excel no existe.")
        return

    # --- 1. Cargar y filtrar SBs ---
    print(f"Leyendo Excel: {ruta_excel}")
    try:
        lista_sbs = cargar_lista_sb_con_filtros(ruta_excel)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo leer el Excel:\n{e}")
        return

    if not lista_sbs:
        messagebox.showerror("Error", "No se encontraron SBs válidos en el Excel.")
        return

    print(f"SBs válidos encontrados: {len(lista_sbs)}")

    # --- 2. Construir Matriz A ---
    print("Procesando XMLs...")
    data = construir_matriz_desde_lista_filtrada(lista_sbs, carpeta_xmls)
    if data is None:
        messagebox.showerror("Error",
                              "No se procesó ningún SB válido.\n"
                              "Verifique rutas y nombres en el Excel.")
        return

    A = data['A']
    b = data['b']
    sbs = data['sbs']
    is_priority = data['is_priority']
    errores = data['errores']

    print(f"SBs procesados: {len(sbs)}, Errores: {len(errores)}")
    if len(sbs) > 0:
        print("\nLista de SBs leídos/procesados con éxito:")
        for name in sbs:
            print(f"  - {name}")
    if len(errores) > 0:
        print("\nLista de SBs que no se pudieron procesar/encontrar:")
        for name in errores:
            print(f"  - {name}")
            
    import time
    print("\n[PAUSA] Esperando 10 segundos para revisar los SBs leídos antes de iniciar el cálculo...")
    time.sleep(30)

    # --- 3. Determinar peso S1000D ---
    peso_s1000d = 1.0
    if np.any(is_priority):
        n_prio = np.sum(is_priority)
        n_legacy = len(b) - n_prio
        rec_val = max(2.0, min(n_legacy / n_prio if n_prio > 0 else 5.0, 50.0))

        w_input = simpledialog.askfloat(
            "Importancia S1000D",
            f"Se han detectado {n_prio} SBs S1000D frente a {n_legacy} Legacy.\n"
            f"Recomendación para equilibrar: {rec_val:.1f}x\n\n"
            "Introduzca el grado de importancia (peso):",
            initialvalue=round(rec_val, 1), minvalue=1.0, maxvalue=1000.0,
            parent=parent_window
        )
        if w_input is not None:
            peso_s1000d = w_input
            print(f"Usando importancia {w_input:.1f}x para SBs S1000D.")
        else:
            print("Usando peso estándar (1x).")
    else:
        print("No hay SBs prioritarios. Usando peso estándar (1x).")

    # --- 4. Optimizar ---
    print(f"\nCalculando coeficientes para {len(sbs)} SBs...")
    try:
        resultado = ajuste_primer_disparo(A, b, is_priority,
                                           peso_s1000d=peso_s1000d)
    except Exception as e:
        messagebox.showerror("Error Matemático",
                              f"Error al resolver el sistema:\n{e}")
        return

    x = resultado['x_full']
    pred = resultado['predicciones']
    diff = resultado['residuals']

    # --- 5. Mostrar resultados ---
    coefs_dict = {f"C{i+1:02d}": x[i] for i in range(15)}

    msg = f"COEFICIENTES CALCULADOS (Optimizado {resultado['best_weight']:.1f}x en 'X'):\n"
    msg += "-" * 40 + "\n"
    for key, val in coefs_dict.items():
        msg += f"{key}: {val:.4f} puntos\n"

    msg += "-" * 40 + "\n"
    msg += f"SBs procesados: {len(sbs)}\n"
    msg += f"Calidad del ajuste GLOBAL (R²): {resultado['r2']:.4f} (Max=1.0)\n"
    msg += "-" * 40 + "\n"
    msg += f"1. Error Medio Absoluto (MAE): {resultado['mae']:.4f} puntos\n"
    msg += "   -> Promedio de cuánto se equivoca (sin signo).\n"
    msg += f"2. Error Medio (RMSE): {resultado['rmse']:.4f} puntos\n"
    msg += "   -> Penaliza errores grandes. Si > MAE, hay outliers.\n"
    msg += f"3. Error Medio con Signo (Bias): {resultado['bias']:.8f} puntos\n"
    msg += "   -> (+) Sobreestima, (-) Subestima el precio real.\n"

    # Métricas S1000D
    if np.any(is_priority):
        m_s1000d = calcular_metricas_subgrupo(diff[is_priority], b[is_priority])
        msg += (f"\n--- MÉTRICAS S1000D (Prioritarios: {np.sum(is_priority)}) ---\n"
                f"R²: {m_s1000d['r2']:.4f}\n"
                f"MAE: {m_s1000d['mae']:.4f}\n"
                f"RMSE: {m_s1000d['rmse']:.4f}\n"
                f"Bias: {m_s1000d['bias']:.4f}\n")

    # Control de calidad
    LIMIT_R2 = 0.70
    LIMIT_RMSE_PCT = 0.25
    mean_price = np.mean(b)
    rmse_pct = resultado['rmse'] / mean_price if mean_price != 0 else float('inf')

    warnings_calidad = []
    if resultado['r2'] < LIMIT_R2:
        warnings_calidad.append(
            f"- R² bajo ({resultado['r2']:.2f} < {LIMIT_R2})")
    if rmse_pct > LIMIT_RMSE_PCT:
        warnings_calidad.append(
            f"- Error relativo alto ({rmse_pct:.1%} > {LIMIT_RMSE_PCT:.0%})")

    if warnings_calidad:
        msg += "\nAVISO DE CALIDAD:\n" + "\n".join(warnings_calidad)
    if errores:
        msg += f"\nArchivos no leídos: {len(errores)} (ver consola)"

    print("\n" + msg)
    messagebox.showinfo("Resultados (Cálculo Estricto)", msg)

    # --- Aviso de archivos XML no utilizados ---
    no_usados = obtener_archivos_no_usados(carpeta_xmls, sbs)
    if no_usados:
        msg_warn = (f"Se han detectado {len(no_usados)} archivo(s) en la carpeta de XMLs "
                    f"que NO se han utilizado en el ajuste:\n\n")
        if len(no_usados) <= 15:
            msg_warn += "\n".join([f"  - {f}" for f in no_usados])
        else:
            msg_warn += "\n".join([f"  - {f}" for f in no_usados[:15]])
            msg_warn += f"\n  ... y {len(no_usados) - 15} más (ver lista completa en la consola)."
        
        print("\n--- ARCHIVOS DE LA CARPETA NO USADOS ---")
        for f in no_usados:
            print(f"  - {f}")
        print("----------------------------------------\n")
        
        messagebox.showwarning("Archivos XML/ZIP no utilizados", msg_warn)

    # --- 6. Guardar ---
    if messagebox.askyesno("Guardar Reporte",
                            "¿Desea exportar el reporte a Excel?"):
        ruta_guardar = filedialog.asksaveasfilename(
            title="Guardar Reporte",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if ruta_guardar:
            try:
                guardar_reporte_primer_disparo(ruta_guardar, x, A, b, sbs,
                                                resultado['final_weights'],
                                                is_priority)
                messagebox.showinfo("Guardado",
                                     f"Reporte guardado en:\n{ruta_guardar}")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar:\n{e}")

    # --- 7. Cálculos secundarios si calidad es baja ---
    if warnings_calidad:
        if messagebox.askyesno("Calidad del Modelo Baja",
                               "\n".join(warnings_calidad) +
                               "\n\n¿Probar CÁLCULO RELAJADO?"):
            res_rel = ajuste_relajado(A, b)
            x_rel = res_rel['x_full']

            msg_rel = "COEFICIENTES (CÁLCULO RELAJADO):\n"
            msg_rel += "\n".join([f"C{i+1:02d}: {v:.4f}"
                                  for i, v in enumerate(x_rel)])
            msg_rel += f"\n\nR²: {res_rel['r2']:.4f}\nRMSE: {res_rel['rmse']:.4f}"
            messagebox.showinfo("Resultados (Relajado)", msg_rel)

            if messagebox.askyesno("Guardar", "¿Guardar reporte RELAJADO?"):
                ruta_rel = filedialog.asksaveasfilename(
                    title="Guardar Relajado",
                    defaultextension=".xlsx",
                    filetypes=[("Excel", "*.xlsx")]
                )
                if ruta_rel:
                    try:
                        guardar_reporte_primer_disparo(
                            ruta_rel, x_rel, A, b, sbs,
                            np.ones(len(b))
                        )
                        messagebox.showinfo("Guardado", f"Guardado: {ruta_rel}")
                    except Exception as e:
                        messagebox.showerror("Error", str(e))

            # Sin restricciones
            rmse_pct_rel = res_rel['rmse'] / mean_price if mean_price else float('inf')
            if res_rel['r2'] < LIMIT_R2 or rmse_pct_rel > LIMIT_RMSE_PCT:
                if messagebox.askyesno("Calidad Aún Baja",
                                       "¿Ejecutar cálculo SIN RESTRICCIONES?"):
                    res_unc = ajuste_sin_restricciones(A, b)
                    msg_unc = "COEFICIENTES (SIN RESTRICCIONES):\n"
                    msg_unc += "\n".join([f"C{i+1:02d}: {v:.4f}"
                                          for i, v in enumerate(res_unc['x_full'])])
                    msg_unc += f"\n\nR²: {res_unc['r2']:.4f}\nRMSE: {res_unc['rmse']:.4f}"
                    messagebox.showinfo("Sin Restricciones", msg_unc)

    # --- 8. Ajuste manual ---
    if messagebox.askyesno("Ajuste Manual",
                            "¿Realizar ajuste manual sobre los coeficientes?"):
        root_ref = parent_window if parent_window else tk.Tk()
        adj_window = AdjustmentWindow(root_ref, A, b, x, sbs)
        root_ref.wait_window(adj_window.top)


def flujo_ajuste_manual_desde_excel(parent_window=None):
    """
    Carga un Excel previo y lanza la ventana de ajuste manual.
    """
    root = parent_window if parent_window else tk.Tk()
    if not parent_window:
        root.withdraw()

    ruta_excel = filedialog.askopenfilename(
        title="Seleccionar Reporte Excel (con Matriz_A)",
        filetypes=[("Excel files", "*.xlsx")]
    )
    if not ruta_excel:
        return

    try:
        A, b, x_orig, sbs_names = cargar_datos_ajuste_manual(ruta_excel)
        adj_window = AdjustmentWindow(root, A, b, x_orig, sbs_names)
        root.wait_window(adj_window.top)
        if not parent_window:
            root.destroy()
    except Exception as e:
        messagebox.showerror("Error", f"Error al leer el Excel:\n{e}")


# =============================================================================
#  FLUJO 2: REAJUSTE CON JERARQUÍA
# =============================================================================

class ReajusteWindow:
    """
    Ventana de reajuste de coeficientes con preservación de jerarquía.
    """

    def __init__(self, parent=None):
        if parent:
            self.top = tk.Toplevel(parent)
        else:
            self.top = tk.Tk()

        self.top.title("Reajuste de Coeficientes con Preservación de Jerarquía")
        self.top.geometry("750x500")
        self.top.resizable(True, True)

        self.var_excel_coefs = tk.StringVar()
        self.var_excel_sbs = tk.StringVar()
        self.var_carpeta_xml = tk.StringVar()
        self.var_lambda = tk.DoubleVar(value=1.0)
        self.var_mantener_grupos = tk.BooleanVar(value=True)
        self.var_usar_irls = tk.BooleanVar(value=True)
        self.var_max_iter = tk.IntVar(value=500)

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.top, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="Reajuste de Coeficientes",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 10))

        # Archivo coeficientes iniciales
        ttk.Label(main, text="1. Excel de coeficientes iniciales (Ajuste previo):"
                  ).pack(anchor="w")
        f1 = ttk.Frame(main)
        f1.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(f1, textvariable=self.var_excel_coefs).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(f1, text="...", width=3,
                   command=lambda: self._browse_file(self.var_excel_coefs)
                   ).pack(side=tk.RIGHT, padx=(5, 0))

        # Lista de SBs
        ttk.Label(main, text="2. Excel con lista de SBs y puntos facturados:"
                  ).pack(anchor="w")
        f2 = ttk.Frame(main)
        f2.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(f2, textvariable=self.var_excel_sbs).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(f2, text="...", width=3,
                   command=lambda: self._browse_file(self.var_excel_sbs)
                   ).pack(side=tk.RIGHT, padx=(5, 0))

        # Carpeta XMLs
        ttk.Label(main, text="3. Carpeta de XMLs:").pack(anchor="w")
        f3 = ttk.Frame(main)
        f3.pack(fill=tk.X, pady=(0, 12))
        ttk.Entry(f3, textvariable=self.var_carpeta_xml).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(f3, text="...", width=3,
                   command=self._browse_folder).pack(side=tk.RIGHT, padx=(5, 0))

        ttk.Separator(main, orient="horizontal").pack(fill=tk.X, pady=5)

        # Parámetros
        ttk.Label(main, text="Parámetros de optimización:",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 5))

        pf = ttk.Frame(main)
        pf.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(pf, text="λ (peso jerarquía):").grid(
            row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Entry(pf, textvariable=self.var_lambda, width=10).grid(
            row=0, column=1, sticky="w")
        ttk.Label(pf, text="(0=sin preservar, alto=máxima preservación)",
                  foreground="gray").grid(row=0, column=2, sticky="w", padx=(10, 0))

        ttk.Label(pf, text="Max iteraciones IRLS:").grid(
            row=1, column=0, sticky="w", padx=(0, 5), pady=(5, 0))
        ttk.Entry(pf, textvariable=self.var_max_iter, width=10).grid(
            row=1, column=1, sticky="w", pady=(5, 0))

        cf = ttk.Frame(main)
        cf.pack(fill=tk.X, pady=(5, 5))
        ttk.Checkbutton(cf,
                        text="Mantener agrupaciones (C07≈C08≈C09, C11≈C13≈C14≈C15)",
                        variable=self.var_mantener_grupos).pack(anchor="w")
        ttk.Checkbutton(cf,
                        text="Usar IRLS robusto (recomendado para outliers)",
                        variable=self.var_usar_irls).pack(anchor="w")

        ttk.Separator(main, orient="horizontal").pack(fill=tk.X, pady=5)

        # Progreso
        self.progress_label = ttk.Label(main, text="Listo para iniciar.")
        self.progress_label.pack(anchor="w", pady=(5, 2))
        self.progress_bar = ttk.Progressbar(main, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        # Botones
        bf = ttk.Frame(main)
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="▶ Ejecutar Reajuste",
                   command=self._ejecutar).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(bf, text="Cerrar",
                   command=self.top.destroy).pack(side=tk.RIGHT, padx=(5, 0))

    def _browse_file(self, var):
        f = filedialog.askopenfilename(
            filetypes=[("Excel", "*.xlsx *.xls"), ("CSV", "*.csv")])
        if f:
            var.set(f)

    def _browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.var_carpeta_xml.set(d)

    def _log(self, msg):
        print(msg)
        sys.stdout.flush()
        self.top.update_idletasks()

    def _progress(self, current, total, name=""):
        pct = (current / total) * 100 if total > 0 else 0
        self.progress_bar['value'] = pct
        self.progress_label.config(text=f"Procesando {current}/{total}: {name}")
        self.top.update_idletasks()
        print(f"Procesando XMLs: {current}/{total} ({pct:.1f}%) - {name}")
        sys.stdout.flush()

    def _ejecutar(self):
        ruta_coefs = self.var_excel_coefs.get()
        ruta_sbs = self.var_excel_sbs.get()
        carpeta_xml = self.var_carpeta_xml.get()

        if not ruta_coefs or not ruta_sbs or not carpeta_xml:
            messagebox.showwarning("Faltan datos",
                                   "Seleccione los 3 archivos/carpetas.")
            return

        try:
            lam = self.var_lambda.get()
        except (ValueError, tk.TclError):
            lam = 1.0

        try:
            max_iter = self.var_max_iter.get()
        except (ValueError, tk.TclError):
            max_iter = 500

        mantener_grupos = self.var_mantener_grupos.get()
        usar_irls = self.var_usar_irls.get()

        # PASO 1: Cargar coeficientes
        self._log("=" * 60)
        self._log("PASO 1: Cargando coeficientes iniciales...")
        try:
            datos = cargar_coeficientes_desde_excel(ruta_coefs)
            x0 = datos['x0']
            A_orig = datos['A_orig']
            sbs_orig = datos['sbs_orig']
            self._log(f"  → {len(x0)} coeficientes cargados")
            if A_orig is not None:
                self._log(f"  → Matriz A original: {A_orig.shape}")
            for i in range(15):
                self._log(f"    C{i+1:02d} = {x0[i]:.4f}")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar coeficientes:\n{e}")
            return

        # PASO 2: Cargar lista SBs
        self._log("\nPASO 2: Cargando lista de SBs...")
        try:
            df_sbs = cargar_lista_sb_simple(ruta_sbs)
            self._log(f"  → {len(df_sbs)} SBs con puntos facturados")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar SBs:\n{e}")
            return

        # PASO 3: Construir Matriz A
        self._log("\nPASO 3: Construyendo Matriz A...")
        result = construir_matriz_con_reutilizacion(
            df_sbs, carpeta_xml,
            A_orig=A_orig, sbs_orig=sbs_orig,
            callback=self._progress
        )

        if result is None:
            messagebox.showerror("Error", "No se procesó ningún SB.")
            return

        A = result['A']
        b = result['b']
        sbs = result['sbs']
        is_priority = result.get('is_priority', None)
        errores = result['errores']
        fuente = result['fuente']

        n_orig = sum(1 for f in fuente if f == "original")
        n_xml = sum(1 for f in fuente if f == "xml")
        self._log(f"  → {len(sbs)} procesados ({n_orig} reutilizados + {n_xml} XML)")
        self._log(f"  → {len(errores)} no procesables")
        
        if len(sbs) > 0:
            self._log("\nLista de SBs leídos/procesados con éxito:")
            for name in sbs:
                self._log(f"  - {name}")
        if len(errores) > 0:
            self._log("\nLista de SBs que no se pudieron procesar/encontrar:")
            for name in errores:
                self._log(f"  - {name}")
                
        import time
        self._log("\n[PAUSA] Esperando 10 segundos para revisar los SBs leídos antes de iniciar el cálculo...")
        time.sleep(10)

        # PASO 3.5: Determinar peso S1000D
        peso_s1000d = 1.0
        if is_priority is not None and np.any(is_priority):
            n_prio = np.sum(is_priority)
            n_legacy = len(b) - n_prio
            rec_val = max(2.0, min(n_legacy / n_prio if n_prio > 0 else 5.0, 50.0))

            w_input = simpledialog.askfloat(
                "Importancia S1000D",
                f"Se han detectado {n_prio} SBs S1000D frente a {n_legacy} Legacy.\n"
                f"Recomendación para equilibrar: {rec_val:.1f}x\n\n"
                "Introduzca el grado de importancia (peso) para reajuste:",
                initialvalue=round(rec_val, 1), minvalue=1.0, maxvalue=1000.0,
                parent=self.top
            )
            if w_input is not None:
                peso_s1000d = w_input
                self._log(f"  → Usando importancia {w_input:.1f}x para SBs S1000D.")
            else:
                self._log("  → Usando peso estándar (1x).")
        else:
            self._log("  → No hay SBs prioritarios. Usando peso estándar (1x).")

        # PASO 4: Optimizar
        self._log(f"\nPASO 4: Optimizando (λ={lam})...")
        self.progress_label.config(text="Optimizando...")
        self.progress_bar['value'] = 0
        self.top.update_idletasks()

        try:
            if usar_irls:
                self._log(f"  → Método: IRLS robusto ({max_iter} iter)")
                resultado = irls_con_jerarquia(
                    A, b, x0, max_iter=max_iter,
                    lambda_jerarquia=lam, mantener_grupos=mantener_grupos,
                    callback=self._log,
                    is_priority=is_priority, peso_s1000d=peso_s1000d
                )
            else:
                self._log("  → Método: SLSQP directo")
                resultado = reajuste_con_jerarquia(
                    A, b, x0, lambda_jerarquia=lam,
                    mantener_grupos=mantener_grupos,
                    callback=self._log,
                    is_priority=is_priority, peso_s1000d=peso_s1000d
                )

            x_nuevo = resultado['x_full']
            self.progress_bar['value'] = 100
        except Exception as e:
            messagebox.showerror("Error", f"Error:\n{e}")
            import traceback
            self._log(traceback.format_exc())
            return

        # PASO 5: Resultados
        self._log("\n" + "=" * 60)
        self._log("RESULTADOS:")
        self._log("=" * 60)

        df_comp, ranking_ok = comparar_jerarquias(x_nuevo, x0)
        self._log(f"\n{'Coef':>5} {'Inicial':>12} {'Nuevo':>12} {'Delta':>12} "
                  f"{'%':>8} {'RkIni':>6} {'RkNew':>6}")
        self._log("-" * 70)
        for _, row in df_comp.iterrows():
            self._log(
                f"{row['Coeficiente']:>5} {row['Valor Inicial']:>12.4f} "
                f"{row['Valor Nuevo']:>12.4f} {row['Delta Valor']:>12.4f} "
                f"{row['% Cambio']:>7.2f}% {int(row['Rank Inicial']):>6d} "
                f"{int(row['Rank Nuevo']):>6d}"
            )

        self._log(f"\nRanking preservado: {'✓ SÍ' if ranking_ok else '✗ NO'}")
        self._log(f"R²:   {resultado['r2']:.6f}")
        self._log(f"MAE:  {resultado['mae']:.4f}")
        self._log(f"RMSE: {resultado['rmse']:.4f}")
        self._log(f"Bias: {resultado['bias']:.6f}")

        # Métricas S1000D
        m_s1000d = None
        if is_priority is not None and np.any(is_priority):
            pred_new = A @ x_nuevo
            diff_new = pred_new - b
            m_s1000d = calcular_metricas_subgrupo(diff_new[is_priority], b[is_priority])
            self._log(f"\n--- MÉTRICAS S1000D (Prioritarios: {np.sum(is_priority)}) ---")
            self._log(f"  R²:   {m_s1000d['r2']:.6f}")
            self._log(f"  MAE:  {m_s1000d['mae']:.4f}")
            self._log(f"  RMSE: {m_s1000d['rmse']:.4f}")
            self._log(f"  Bias: {m_s1000d['bias']:.6f}")

        m_orig = calcular_metricas(A, b, x0)
        self._log(f"\nComparación (mismos {len(b)} SBs):")
        self._log(f"  R²:   {m_orig['r2']:.6f} → {resultado['r2']:.6f}")
        self._log(f"  RMSE: {m_orig['rmse']:.4f} → {resultado['rmse']:.4f}")

        msg = (f"REAJUSTE COMPLETADO\n\n"
               f"SBs: {len(sbs)}\n"
               f"Ranking preservado: {'SÍ' if ranking_ok else 'NO'}\n\n")
        if m_s1000d is not None:
            msg += (f"MÉTRICAS S1000D (Prioritarios: {np.sum(is_priority)}):\n"
                    f"  R²: {m_s1000d['r2']:.4f} | MAE: {m_s1000d['mae']:.4f} | RMSE: {m_s1000d['rmse']:.4f}\n\n")
        msg += (f"NUEVAS (Global):  R²={resultado['r2']:.4f}  RMSE={resultado['rmse']:.4f}\n"
                f"ORIG (Global):    R²={m_orig['r2']:.4f}  RMSE={m_orig['rmse']:.4f}")
        messagebox.showinfo("Resultados", msg)

        # --- Aviso de archivos XML no utilizados ---
        no_usados = obtener_archivos_no_usados(carpeta_xml, sbs)
        if no_usados:
            msg_warn = (f"Se han detectado {len(no_usados)} archivo(s) en la carpeta de XMLs "
                        f"que NO se han utilizado en el reajuste:\n\n")
            if len(no_usados) <= 15:
                msg_warn += "\n".join([f"  - {f}" for f in no_usados])
            else:
                msg_warn += "\n".join([f"  - {f}" for f in no_usados[:15]])
                msg_warn += f"\n  ... y {len(no_usados) - 15} más (ver lista completa en la consola)."
            
            print("\n--- ARCHIVOS DE LA CARPETA NO USADOS EN EL REAJUSTE ---")
            for f in no_usados:
                print(f"  - {f}")
            print("--------------------------------------------------------\n")
            
            messagebox.showwarning("Archivos XML/ZIP no utilizados", msg_warn)

        # PASO 6: Guardar
        if messagebox.askyesno("Guardar", "¿Guardar reporte completo?"):
            ruta_guardar = filedialog.asksaveasfilename(
                title="Guardar Reporte Reajuste",
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx")]
            )
            if ruta_guardar:
                try:
                    guardar_reporte_reajuste(
                        ruta_guardar, x_nuevo, x0, A, b,
                        sbs, fuente, resultado, errores,
                        is_priority=is_priority
                    )
                    messagebox.showinfo("Guardado", f"Guardado: {ruta_guardar}")
                    self._log(f"\nReporte: {ruta_guardar}")
                except Exception as e:
                    messagebox.showerror("Error", str(e))

        self.progress_label.config(text="✓ Completado.")


# =============================================================================
#  VENTANA PRINCIPAL
# =============================================================================

class MainApp:
    """
    Aplicación principal con los 3 flujos de trabajo.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("Herramienta de Ajuste de Coeficientes")
        self.root.geometry("650x350")
        self.root.resizable(False, False)

        # Variables
        self.excel_path = tk.StringVar()
        self.xml_folder = tk.StringVar()

        # UI
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Herramienta de Ajuste de Coeficientes",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 15))

        # Inputs compartidos (Excel + XMLs)
        ttk.Label(frame, text="Archivo Excel (Lista SBs y Pesos):").pack(anchor="w")
        ef = ttk.Frame(frame)
        ef.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(ef, textvariable=self.excel_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(ef, text="...", width=3,
                   command=self._browse_excel).pack(side=tk.RIGHT, padx=(5, 0))

        ttk.Label(frame, text="Carpeta de XMLs:").pack(anchor="w")
        xf = ttk.Frame(frame)
        xf.pack(fill=tk.X, pady=(0, 15))
        ttk.Entry(xf, textvariable=self.xml_folder).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(xf, text="...", width=3,
                   command=self._browse_folder).pack(side=tk.RIGHT, padx=(5, 0))

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=5)

        # Botones
        ttk.Label(frame, text="Acciones:",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 8))

        bf1 = ttk.Frame(frame)
        bf1.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(bf1, text="📊 Cálculo Completo desde Cero (Excel + XMLs)",
                   command=self._run_full_calc).pack(fill=tk.X)

        bf2 = ttk.Frame(frame)
        bf2.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(bf2, text="🔄 Reajuste con Jerarquía (desde coefs previos)",
                   command=self._run_reajuste).pack(fill=tk.X)

        bf3 = ttk.Frame(frame)
        bf3.pack(fill=tk.X)
        ttk.Button(bf3, text="✏️ Ajuste Manual (importar Excel previo)",
                   command=self._run_manual).pack(fill=tk.X)

    def _browse_excel(self):
        f = filedialog.askopenfilename(
            filetypes=[("Excel", "*.xlsx *.xls")])
        if f:
            self.excel_path.set(f)

    def _browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.xml_folder.set(d)

    def _run_full_calc(self):
        """Flujo 1: Ajuste desde cero."""
        if not self.excel_path.get() or not self.xml_folder.get():
            messagebox.showwarning("Faltan datos",
                                   "Seleccione el Excel y la carpeta de XMLs.")
            return
        flujo_ajuste_desde_cero(self.excel_path.get(), self.xml_folder.get(),
                                 parent_window=self.root)

    def _run_reajuste(self):
        """Flujo 2: Reajuste con jerarquía."""
        win = ReajusteWindow(parent=self.root)
        self.root.wait_window(win.top)

    def _run_manual(self):
        """Flujo 3: Ajuste manual desde Excel."""
        flujo_ajuste_manual_desde_excel(parent_window=self.root)


# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================

def main():
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

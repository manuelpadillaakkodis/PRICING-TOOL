"""
ajuste_manual.py — Ventana GUI de ajuste manual de coeficientes.

Permite al usuario reducir un coeficiente un % y redistribuir el peso
entre otros coeficientes seleccionados.
"""

import numpy as np
import pandas as pd
import scipy.optimize
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class AdjustmentWindow:
    """
    Ventana para ajuste manual de coeficientes:
    1. Seleccionar un coeficiente a REDUCIR
    2. Indicar % de reducción
    3. Seleccionar coeficientes que ABSORBEN el peso
    """

    def __init__(self, parent, A, b, x_orig, sbs_names):
        self.top = tk.Toplevel(parent)
        self.top.title("Ajuste Manual de Coeficientes")
        self.top.geometry("650x600")

        self.A = A
        self.b = b
        self.x_orig = x_orig
        self.sbs_names = sbs_names

        self.var_reduce = tk.StringVar()
        self.var_pct = tk.DoubleVar(value=0.0)
        self.vars_increase = []
        self.checkbuttons = []

        main_frame = ttk.Frame(self.top, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Seleccionar coeficiente a reducir
        ttk.Label(main_frame, text="1. Seleccione el coeficiente a REDUCIR:"
                  ).pack(anchor="w", pady=(0, 5))
        self.combo_reduce = ttk.Combobox(main_frame, textvariable=self.var_reduce,
                                          state="readonly")
        self.combo_reduce['values'] = [f"C{i+1:02d}" for i in range(15)]
        self.combo_reduce.pack(fill=tk.X, pady=(0, 10))
        self.combo_reduce.bind("<<ComboboxSelected>>", self._on_reduce_select)

        # 2. Porcentaje de reducción
        ttk.Label(main_frame, text="2. Indique el porcentaje de reducción (%):"
                  ).pack(anchor="w", pady=(0, 5))
        ttk.Entry(main_frame, textvariable=self.var_pct).pack(fill=tk.X,
                                                                pady=(0, 10))

        # 3. Coeficientes a aumentar
        ttk.Label(main_frame,
                  text="3. Seleccione coeficientes para AUMENTAR (absorber peso):"
                  ).pack(anchor="w", pady=(0, 5))

        frame_list = ttk.Frame(main_frame)
        frame_list.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        canvas = tk.Canvas(frame_list)
        scrollbar = ttk.Scrollbar(frame_list, orient="vertical",
                                   command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for i in range(15):
            key = f"C{i+1:02d}"
            var = tk.BooleanVar()
            chk = ttk.Checkbutton(
                self.scrollable_frame,
                text=f"{key} (Actual: {self.x_orig[i]:.4f})",
                variable=var
            )
            chk.pack(anchor="w")
            self.vars_increase.append(var)
            self.checkbuttons.append(chk)

        ttk.Button(main_frame, text="Calcular Nuevo Ajuste",
                   command=self._calculate).pack(fill=tk.X, pady=10)

    def _on_reduce_select(self, event):
        selected = self.combo_reduce.get()
        for i, chk in enumerate(self.checkbuttons):
            key = f"C{i+1:02d}"
            if key == selected:
                chk.state(['disabled'])
                self.vars_increase[i].set(False)
            else:
                chk.state(['!disabled'])

    def _calculate(self):
        reduce_key = self.var_reduce.get()
        if not reduce_key:
            messagebox.showwarning("Error", "Seleccione un coeficiente para reducir.")
            return

        try:
            pct = self.var_pct.get()
            if pct < 0 or pct > 100:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showwarning("Error", "Porcentaje inválido (0-100).")
            return

        idx_reduce = int(reduce_key[1:]) - 1
        idxs_increase = [i for i, var in enumerate(self.vars_increase) if var.get()]

        if not idxs_increase:
            messagebox.showwarning("Error",
                                    "Seleccione al menos un coeficiente para aumentar.")
            return

        epsilon = 1e-9

        # Fijar todos los coeficientes
        lb = self.x_orig.copy() - epsilon
        ub = self.x_orig.copy() + epsilon

        # Reducir el seleccionado
        val_reduce = self.x_orig[idx_reduce] * (1.0 - pct / 100.0)
        lb[idx_reduce] = val_reduce - epsilon
        ub[idx_reduce] = val_reduce + epsilon

        # Permitir aumento en los seleccionados
        for i in idxs_increase:
            lb[i] = self.x_orig[i]
            ub[i] = np.inf

        try:
            res = scipy.optimize.lsq_linear(self.A, self.b, bounds=(lb, ub))
            x_new = res.x
            residuals = self.A @ x_new - self.b
            bias = np.mean(residuals)

            if abs(bias) > 0.001:
                msg = (f"AVISO: El error medio con signo (Bias) es {bias:.6f}, "
                       f"que supera el límite de 0.001.\n"
                       "¿Desea ver los resultados de todos modos?")
                if not messagebox.askyesno("Advertencia de Bias", msg):
                    return

            self._show_results(x_new, residuals)
        except Exception as e:
            messagebox.showerror("Error de Cálculo", str(e))

    def _show_results(self, x_new, residuals):
        msg = "Nuevos Coeficientes:\n"
        coefs_dict = {}
        for i in range(15):
            key = f"C{i+1:02d}"
            val = x_new[i]
            change = val - self.x_orig[i]
            msg += f"{key}: {val:.4f} (Delta: {change:+.4f})\n"
            coefs_dict[key] = val

        r2 = 1 - (np.sum(residuals**2) /
                   np.sum((self.b - np.mean(self.b))**2))
        msg += f"\nR²: {r2:.4f}"
        msg += f"\nBias: {np.mean(residuals):.6f}"

        messagebox.showinfo("Resultados Ajuste", msg)

        if messagebox.askyesno("Guardar", "¿Desea guardar estos resultados en Excel?"):
            ruta = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                                filetypes=[("Excel", "*.xlsx")])
            if ruta:
                try:
                    df_coefs = pd.DataFrame(list(coefs_dict.items()),
                                             columns=["Contador", "Coeficiente"])
                    df_det = pd.DataFrame({
                        "SB": self.sbs_names,
                        "Real": self.b,
                        "Calc": self.A @ x_new,
                        "Diff": residuals,
                    })
                    df_A = pd.DataFrame(self.A,
                                         columns=[f"C{i+1:02d}" for i in range(15)])
                    df_A.insert(0, "SB", self.sbs_names)

                    with pd.ExcelWriter(ruta) as writer:
                        df_coefs.to_excel(writer, sheet_name="Coeficientes",
                                          index=False)
                        df_det.to_excel(writer, sheet_name="Detalle", index=False)
                        df_A.to_excel(writer, sheet_name="Matriz_A", index=False)
                    messagebox.showinfo("Guardado", "Archivo guardado.")
                except Exception as e:
                    messagebox.showerror("Error", str(e))

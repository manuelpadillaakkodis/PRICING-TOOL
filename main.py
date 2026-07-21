import os
import sys
import csv
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Se REUTILIZAN funciones EXISTENTES de funcionespesado (ese archivo NO se modifica):
#   - comparar_zips : pesado diferencial de un par (Revised / Dummy)
#   - weightnewxml  : pesado total de un módulo (New)
#   - get_xml_content : extrae un módulo (930/933) de un ZIP en memoria
from funcionespesado import comparar_zips, weightnewxml, get_xml_content

# Módulo nuevo de exportación (versionado de nombres + Excel)
import exportacion

# La lógica de negocio sigue siendo C01..C15 (sin cambios)
CONTADORES = [f"C{i:02d}" for i in range(1, 16)]

# Mismo emparejamiento que funcionespesado: nombre base + sufijo de 2 dígitos
PATRON_REV = re.compile(r'^(.*)-(\d{2})\.zip$', re.IGNORECASE)


def _win_pick_folder(initialdir, title, hwnd_owner=0):
    """Abre el dialogo nativo de Windows 'Buscar carpeta' con BIF_BROWSEINCLUDEFILES,
    de modo que SE VEN los archivos de cada carpeta (ademas de las subcarpetas) y
    el usuario selecciona una CARPETA. Devuelve la ruta elegida, "" si se cancela.
    Lanza excepcion si algo falla (para que se use el fallback askdirectory)."""
    import ctypes
    from ctypes import wintypes, byref, c_void_p, c_int

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    user32 = ctypes.windll.user32

    BIF_NEWDIALOGSTYLE     = 0x00000040
    BIF_EDITBOX            = 0x00000010
    BIF_BROWSEINCLUDEFILES = 0x00004000
    BFFM_INITIALIZED       = 1
    BFFM_SETSELECTIONW     = 0x0400 + 103   # WM_USER + 103
    MAX_PATH = 260

    # Callback para posicionar la carpeta inicial
    BFFCALLBACK = ctypes.WINFUNCTYPE(c_int, wintypes.HWND, wintypes.UINT,
                                     wintypes.LPARAM, wintypes.LPARAM)

    def _cb(hwnd, msg, lParam, lpData):
        if msg == BFFM_INITIALIZED and lpData:
            user32.SendMessageW(hwnd, BFFM_SETSELECTIONW, 1, lpData)
        return 0
    cb = BFFCALLBACK(_cb)

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", c_void_p),
            ("pszDisplayName", wintypes.LPWSTR),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", wintypes.UINT),
            ("lpfn", BFFCALLBACK),
            ("lParam", wintypes.LPARAM),
            ("iImage", c_int),
        ]

    # Resolver la ventana propietaria (para que el foco vuelva a la app al cerrar)
    owner = 0
    if hwnd_owner:
        try:
            user32.GetAncestor.restype = c_void_p
            user32.GetAncestor.argtypes = [c_void_p, c_int]
            owner = user32.GetAncestor(hwnd_owner, 2) or hwnd_owner  # GA_ROOT = 2
        except Exception:
            owner = hwnd_owner

    hr_init = ole32.CoInitialize(None)
    need_uninit = hr_init in (0, 1)   # S_OK / S_FALSE -> tenemos un refcount propio
    try:
        display = ctypes.create_unicode_buffer(MAX_PATH)
        init = os.path.abspath(initialdir) if (initialdir and os.path.isdir(initialdir)) else None
        init_buf = ctypes.create_unicode_buffer(init) if init else None

        bi = BROWSEINFO()
        bi.hwndOwner = owner or 0
        bi.pidlRoot = None
        bi.pszDisplayName = ctypes.cast(display, wintypes.LPWSTR)
        bi.lpszTitle = title
        bi.ulFlags = BIF_NEWDIALOGSTYLE | BIF_BROWSEINCLUDEFILES | BIF_EDITBOX
        bi.lpfn = cb
        bi.lParam = ctypes.addressof(init_buf) if init_buf else 0
        bi.iImage = 0

        # Tipos correctos para NO truncar punteros en 64 bits
        shell32.SHBrowseForFolderW.restype = c_void_p
        shell32.SHBrowseForFolderW.argtypes = [c_void_p]
        shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
        shell32.SHGetPathFromIDListW.argtypes = [c_void_p, wintypes.LPWSTR]
        ole32.CoTaskMemFree.restype = None
        ole32.CoTaskMemFree.argtypes = [c_void_p]

        pidl = shell32.SHBrowseForFolderW(byref(bi))
        if not pidl:
            return ""  # el usuario cancelo

        # Con el PIDL ya obtenido, sacamos la ruta y liberamos SIN dejar escapar
        # ninguna excepcion (asi NO se dispara el fallback -> no hay doble dialogo).
        ruta = ""
        try:
            path_buf = ctypes.create_unicode_buffer(MAX_PATH)
            if shell32.SHGetPathFromIDListW(pidl, path_buf):
                ruta = path_buf.value or ""
        finally:
            try:
                ole32.CoTaskMemFree(pidl)
            except Exception:
                pass

        # Si por error se eligio un archivo, usamos su carpeta contenedora
        if ruta and os.path.isfile(ruta):
            ruta = os.path.dirname(ruta)
        return ruta
    finally:
        if need_uninit:
            ole32.CoUninitialize()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ADS - SB Pricing")
        self.geometry("1150x720")

        # Botones más grandes en toda la aplicación
        style = ttk.Style(self)
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Big.TButton", padding=(16, 10), font=("Segoe UI", 11, "bold"))

        # ---------------- Estado en memoria ----------------
        # New & Revised: lista editable de SBs detectados en la carpeta
        self.sb_entries = []            # [{"file", "mode", "previous"}]
        self.resultados_normal = []     # resultados pesados (modo normal)
        self._scanned_folder = None     # última carpeta escaneada (control)

        # Dummy: dos listas de RUTAS COMPLETAS de ficheros (selección múltiple),
        # emparejadas por posición de fila
        self.dummy_initial = []         # [ruta_completa, ...]
        self.dummy_duplicate = []       # [ruta_completa, ...]
        self.resultados_dummy = []

        # Rutas / variables de interfaz
        self.xml_folder = tk.StringVar()
        self.report_folder = tk.StringVar()          # dónde guardar los reportes
        self.dummy_initial_count = tk.StringVar(value="0 file(s)")
        self.dummy_duplicate_count = tk.StringVar(value="0 file(s)")

        # ---------------- Pestañas ----------------
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.tab_coef = ttk.Frame(self.notebook)
        self.tab_new = ttk.Frame(self.notebook)
        self.tab_dummy = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_coef, text="Coefficients")
        self.notebook.add(self.tab_new, text="New and Revised Mode")
        self.notebook.add(self.tab_dummy, text="Duplicate (Dummy) Mode")

        self._build_coef_tab()
        self._build_new_tab()
        self._build_dummy_tab()

        # Los coeficientes se gestionan SOLO en la tabla de la pestaña 1
        # (editable). No se carga ningún CSV automáticamente.
        self._populate_default_counters()

    # ================================================================== #
    #  UTILIDADES GENERALES
    # ================================================================== #
    @staticmethod
    def _fmt(v):
        """Formatea un número: entero si es redondo, 2 decimales si no."""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        if abs(f - round(f)) < 1e-9:
            return str(int(round(f)))
        return f"{f:.2f}"

    @staticmethod
    def _mode_short(tipo):
        t = str(tipo).upper()
        if "REVISED" in t:
            return "Revised"
        if "DUMMY" in t:
            return "Dummy"
        return "New"

    @staticmethod
    def _hay_coeficientes(coef):
        """True si al menos un coeficiente parsea a un valor distinto de 0."""
        for v in coef.values():
            try:
                if float(str(v).replace(",", ".")) != 0.0:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _seleccionar_carpeta(self, var, titulo="Select folder"):
        """Selecciona una CARPETA (mostrando los archivos de su interior) y la fija."""
        carpeta = self._pick_folder(initialdir=(var.get() or None), title=titulo)
        if carpeta:
            var.set(carpeta)
            return carpeta
        return None

    def _pick_folder(self, initialdir=None, title="Select folder"):
        """Selector de CARPETA con interfaz NATIVA de Windows (Vista+), que
        muestra los archivos en gris (no seleccionables) ademas de las carpetas.
        Si no es Windows o algo falla, usa el dialogo estandar de tkinter.
        Devuelve la ruta o None."""
        if sys.platform.startswith("win"):
            try:
                try:
                    hwnd = self.winfo_id()
                except Exception:
                    hwnd = 0
                ruta = _win_pick_folder(initialdir, title, hwnd)
                # "" = el usuario cancelo; cualquier otra cosa = carpeta elegida
                return ruta or None
            except Exception:
                pass  # cae al dialogo estandar
            finally:
                # Devolver el foco de teclado a la app tras el diálogo nativo,
                # para poder seguir escribiendo en los campos en cualquier momento.
                try:
                    self.focus_force()
                    self.after(10, self.focus_force)   # refuerzo tras cerrarse el diálogo
                except Exception:
                    pass
        return filedialog.askdirectory(
            initialdir=(initialdir if initialdir else None), title=title) or None

    # ================================================================== #
    #  PESTAÑA 1 — COEFICIENTES
    # ================================================================== #
    def _build_coef_tab(self):
        outer = ttk.Frame(self.tab_coef, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Coefficients (Validity date: 30-06-2026)",
                  font=("Segoe UI", 11, "bold")).pack(pady=(0, 2))
        ttk.Label(outer, text="Double-click a coefficient to edit it. "
                              "These are the values used when weighting.",
                  foreground="#555").pack(pady=(0, 8))

        # Cuadro de coeficientes
        table_frame = ttk.Frame(outer)
        table_frame.pack(fill="x")

        columns = ("Counter", "Coefficient")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=17)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=200)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="ew")
        vsb.grid(row=0, column=1, sticky="ns")
        table_frame.columnconfigure(0, weight=1)

        # Edición en línea del coeficiente
        self.tree.bind("<Double-1>", self._edit_coef_cell)

        btns = ttk.Frame(outer)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Import...",
                   command=self.import_coefficients_from_csv).pack(side="left")
        ttk.Button(btns, text="Export...",
                   command=self.export_to_csv).pack(side="left", padx=(6, 0))

    # ---------- Lectura/escritura de la tabla de coeficientes ----------
    def obtener_coeficientes(self):
        """Devuelve {counter: coefficient} con lo que haya en la tabla (pestaña 1)."""
        coef = {}
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id)["values"]
            if len(values) < 2:
                continue
            counter, value = values[0], values[1]
            if str(counter).strip() != "":
                coef[str(counter)] = str(value)
        return coef

    def _clear_coefficients_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _populate_default_counters(self):
        """Crea las 15 filas C01..C15 con coeficiente 0 (editable por el usuario)."""
        self._clear_coefficients_table()
        for c in CONTADORES:
            self.tree.insert("", "end", iid=c, values=(c, "0"))

    def _set_coef_values(self, mapping):
        """Actualiza el coeficiente de las filas existentes a partir de {counter: coef}.
        Mantiene siempre las 15 filas C01..C15."""
        # Normalizamos claves del mapping a formato C0X
        norm = {}
        for k, v in mapping.items():
            kk = self._norm_counter_key(k)
            if kk:
                norm[kk] = v
        # Aseguramos las 15 filas y aplicamos valores
        existentes = set(self.tree.get_children())
        for c in CONTADORES:
            val = norm.get(c, "0")
            if c in existentes:
                self.tree.item(c, values=(c, val))
            else:
                self.tree.insert("", "end", iid=c, values=(c, val))

    @staticmethod
    def _norm_counter_key(raw):
        """'C1','c01','1','Counter 3'... -> 'C03'. Devuelve None si no es 1..15."""
        m = re.search(r'(\d{1,2})', str(raw))
        if not m:
            return None
        n = int(m.group(1))
        if 1 <= n <= 15:
            return f"C{n:02d}"
        return None

    def _edit_coef_cell(self, event):
        """Edición en línea de la columna 'Coefficient' (doble clic)."""
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if not row or col != "#2":   # solo la columna Coefficient
            return
        x, y, w, h = self.tree.bbox(row, col)
        valor_actual = self.tree.set(row, "Coefficient")

        edit = ttk.Entry(self.tree)
        edit.place(x=x, y=y, width=w, height=h)
        edit.insert(0, valor_actual)
        edit.focus_set()
        edit.select_range(0, "end")

        def guardar(_=None):
            nuevo = edit.get().strip()
            self.tree.set(row, "Coefficient", nuevo)
            edit.destroy()

        def cancelar(_=None):
            edit.destroy()

        edit.bind("<Return>", guardar)
        edit.bind("<KP_Enter>", guardar)
        edit.bind("<FocusOut>", guardar)
        edit.bind("<Escape>", cancelar)

    def _read_coefficients_csv(self, path):
        """Lee un CSV y devuelve {counter: coef} (no toca la tabla)."""
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                sample = f.read(1024)
                f.seek(0)
                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample)
                except csv.Error:
                    dialect = csv.get_dialect("excel")
                reader = csv.reader(f, dialect)
                rows = list(reader)
        except Exception as e:
            messagebox.showerror("Import", f"Could not read the CSV:\n{e}")
            return None

        if not rows:
            return {}

        start_idx = 0
        header = [c.strip().lower() for c in rows[0]]
        if header and len(header) >= 2 and ("counter" in header[0] or "coef" in header[1]):
            start_idx = 1

        mapping = {}
        for row in rows[start_idx:]:
            if len(row) < 2:
                continue
            counter = row[0].strip()
            coeff = row[1].strip()
            if counter:
                mapping[counter] = coeff
        return mapping

    def import_coefficients_from_csv(self):
        file_path = filedialog.askopenfilename(
            title="Select coefficients CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not file_path:
            return
        mapping = self._read_coefficients_csv(file_path)
        if mapping is None:
            return
        self._set_coef_values(mapping)
        messagebox.showinfo("Import", f"Coefficients loaded into the table from:\n{file_path}")

    def export_to_csv(self):
        if not self.tree.get_children():
            messagebox.showwarning("Export", "There is no data to export.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export table to CSV",
            confirmoverwrite=False,
        )
        if not file_path:
            return
        # No se pisa: si existe, se versiona
        file_path = exportacion.generar_ruta_versionada(file_path)
        columns = [self.tree.heading(col)["text"] for col in self.tree["columns"]]
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(columns)
            for item in self.tree.get_children():
                writer.writerow(self.tree.item(item)["values"])
        messagebox.showinfo("Export", f"Table exported to:\n{file_path}")

    # ================================================================== #
    #  PESTAÑA 2 — NEW & REVISED
    # ================================================================== #
    def _build_new_tab(self):
        # --- Selección de carpetas (entrada de SBs y salida de reportes) ---
        top = ttk.Frame(self.tab_new, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="SB folder (where are the zip files):").grid(row=0, column=0, sticky="w")
        ent_sb = ttk.Entry(top, textvariable=self.xml_folder)
        ent_sb.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(top, text="Select...",
                   command=self._on_select_new_folder).grid(row=0, column=2)
        # Type/paste a path and press Enter to load it
        ent_sb.bind("<Return>", lambda e: self._on_typed_new_folder())

        ttk.Label(top, text="Where to save the reports:").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        ent_save = ttk.Entry(top, textvariable=self.report_folder)
        ent_save.grid(row=1, column=1, sticky="ew", padx=5, pady=(6, 0))
        ttk.Button(top, text="Select...",
                   command=self._on_select_report_folder).grid(
            row=1, column=2, pady=(6, 0))
        ent_save.bind("<Return>", lambda e: self._on_typed_report_folder())
        ttk.Label(
            top,
            text="Tip: you can type or paste a path in these fields and "
                 "press Enter to confirm it.",
            foreground="#777",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        top.columnconfigure(1, weight=1)

        # --- Lista de SBs cargados (editable) ---
        mid = ttk.LabelFrame(self.tab_new, text="Selected SBs", padding=8)
        mid.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        cols = ("File", "Mode", "Previous SB (original)")
        self.tree_sb = ttk.Treeview(mid, columns=cols, show="headings", height=6)
        for c, w in zip(cols, (560, 90, 300)):
            self.tree_sb.heading(c, text=c)
            self.tree_sb.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree_sb.yview)
        self.tree_sb.configure(yscrollcommand=vsb.set)
        self.tree_sb.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        sb_btns = ttk.Frame(mid)
        sb_btns.grid(row=0, column=2, sticky="ns", padx=(8, 0))
        ttk.Button(sb_btns, text="🗑 Delete",
                   command=self._delete_selected_sb).pack(fill="x")
        ttk.Button(sb_btns, text="Clear all",
                   command=self._clear_sb_list).pack(fill="x", pady=(5, 0))

        # --- Compute ---
        act = ttk.Frame(self.tab_new, padding=(10, 0))
        act.pack(fill="x")
        ttk.Button(act, text="▶ Compute (Weight XML)", style="Big.TButton",
                   command=self._compute_new).pack(side="right")
        ttk.Button(act, text="Clear computation",
                   command=self._clear_results_new).pack(side="right", padx=(0, 8))

        # --- Resultados ---
        res = ttk.LabelFrame(
            self.tab_new,
            text="Pricing results  —  double-click a row to see the per-counter, per-XML breakdown (930 / 933)",
            padding=8,
        )
        res.pack(fill="both", expand=True, padx=10, pady=5)

        rcols = ("SB Ident", "Mode", "Previous SB", "TOTAL WEIGHT") + tuple(CONTADORES)
        self.tree_res = ttk.Treeview(res, columns=rcols, show="headings", height=8)
        self.tree_res.heading("SB Ident", text="SB Ident")
        self.tree_res.column("SB Ident", width=240, anchor="w")
        self.tree_res.heading("Mode", text="Mode")
        self.tree_res.column("Mode", width=70, anchor="center")
        self.tree_res.heading("Previous SB", text="Previous SB")
        self.tree_res.column("Previous SB", width=200, anchor="w")
        self.tree_res.heading("TOTAL WEIGHT", text="TOTAL WEIGHT")
        self.tree_res.column("TOTAL WEIGHT", width=120, anchor="center")
        for c in CONTADORES:
            self.tree_res.heading(c, text=c)
            self.tree_res.column(c, width=55, anchor="center")

        rvsb = ttk.Scrollbar(res, orient="vertical", command=self.tree_res.yview)
        rhsb = ttk.Scrollbar(res, orient="horizontal", command=self.tree_res.xview)
        self.tree_res.configure(yscrollcommand=rvsb.set, xscrollcommand=rhsb.set)
        self.tree_res.grid(row=0, column=0, sticky="nsew")
        rvsb.grid(row=0, column=1, sticky="ns")
        rhsb.grid(row=1, column=0, sticky="ew")
        res.rowconfigure(0, weight=1)
        res.columnconfigure(0, weight=1)
        self.tree_res.bind(
            "<Double-1>",
            lambda e: self._show_breakdown(self.tree_res, self.resultados_normal),
        )

        # --- Exportación ---
        exp = ttk.Frame(self.tab_new, padding=(10, 0, 10, 10))
        exp.pack(fill="x")
        ttk.Button(exp, text="Export results...",
                   command=self._export_normal).pack(side="right")

    def _on_select_new_folder(self):
        carpeta = self._seleccionar_carpeta(self.xml_folder)
        if carpeta:
            self._scan_new_folder(carpeta)

    def _on_typed_new_folder(self):
        """Carga la carpeta escrita/pegada a mano en el campo (botón Load o Enter).
        Normaliza la ruta, escanea si es válida y avisa si no existe."""
        carpeta = self.xml_folder.get().strip().strip('"').strip()
        if not carpeta:
            return
        carpeta = os.path.normpath(os.path.expanduser(os.path.expandvars(carpeta)))
        if os.path.isdir(carpeta):
            self.xml_folder.set(carpeta)
            self._scan_new_folder(carpeta)
        else:
            messagebox.showwarning(
                "SB folder", f"The path does not exist or is not a folder:\n{carpeta}")

    def _on_select_report_folder(self):
        self._seleccionar_carpeta(
            self.report_folder,
            titulo="Select the output folder")

    def _on_typed_report_folder(self):
        """Confirms the output folder typed/pasted by hand (Enter). Normalizes the
        path; if it doesn't exist, offers to create it."""
        folder = self.report_folder.get().strip().strip('"').strip()
        if not folder:
            return
        folder = os.path.normpath(os.path.expanduser(os.path.expandvars(folder)))
        self.report_folder.set(folder)
        if os.path.isdir(folder):
            messagebox.showinfo("Where to save", f"Output folder set to:\n{folder}")
        else:
            if messagebox.askyesno(
                    "Where to save",
                    f"This folder does not exist:\n{folder}\n\nCreate it?"):
                try:
                    os.makedirs(folder, exist_ok=True)
                    messagebox.showinfo("Where to save", f"Folder created:\n{folder}")
                except Exception as ex:
                    messagebox.showerror(
                        "Where to save", f"Could not create the folder:\n{ex}")

    def _scan_new_folder(self, carpeta):
        """Escanea la carpeta y clasifica New/Revised SIN pesar (igual criterio
        que revisiones_y_originales: base + sufijo, penúltimo=original, último=revisado)."""
        try:
            files = [f for f in os.listdir(carpeta) if f.lower().endswith(".zip")]
        except Exception as e:
            messagebox.showerror("Folder", f"Could not read the folder:\n{e}")
            return

        groups = {}
        for f in files:
            m = PATRON_REV.match(f)
            if m:
                base = m.group(1)
                suffix = int(m.group(2))
                groups.setdefault(base, []).append((suffix, f))
            else:
                groups.setdefault(f, []).append((-1, f))

        self.sb_entries = []
        for _base, lst in groups.items():
            lst.sort(key=lambda x: x[0])
            if len(lst) >= 2:
                self.sb_entries.append(
                    {"file": lst[-1][1], "mode": "Revised", "previous": lst[-2][1]})
            else:
                self.sb_entries.append(
                    {"file": lst[-1][1], "mode": "New", "previous": ""})

        self.sb_entries.sort(key=lambda e: e["file"].lower())
        self._scanned_folder = carpeta
        self._refresh_sb_tree()
        if not self.sb_entries:
            messagebox.showinfo("Selected SBs",
                                "No .zip files were found in the folder.")

    def _refresh_sb_tree(self):
        self.tree_sb.delete(*self.tree_sb.get_children())
        for i, e in enumerate(self.sb_entries):
            self.tree_sb.insert("", "end", iid=str(i),
                                values=(e["file"], e["mode"], e["previous"]))

    def _delete_selected_sb(self):
        sel = self.tree_sb.selection()
        if not sel:
            messagebox.showinfo("Delete", "Select one or more rows to delete.")
            return
        for i in sorted((int(x) for x in sel), reverse=True):
            del self.sb_entries[i]
        self._refresh_sb_tree()

    def _clear_sb_list(self):
        self.sb_entries = []
        self._refresh_sb_tree()

    def _pesar_nuevo(self, zip_path, zip_name, coef):
        """Replica el pesado NEW de revisiones_y_originales (módulos 930/933)."""
        total_w = 0.0
        details = {}
        for key in ("930", "933"):
            content, _ = get_xml_content(zip_path, key)
            if content:
                w = weightnewxml(content, coef)
                total_w += w["total_weight"]
                details[key] = w
        return {"Zip": zip_name, "Type": "NEW", "Total Weight": total_w, "Details": details}

    def _compute_new(self):
        carpeta = self.xml_folder.get()
        if not carpeta or not os.path.isdir(carpeta):
            messagebox.showwarning("Compute", "Select a valid SB folder first.")
            return
        if not self.sb_entries:
            messagebox.showwarning("Compute", "There are no SBs in the list.")
            return

        coef = self.obtener_coeficientes()
        if not self._hay_coeficientes(coef):
            if not messagebox.askyesno(
                "Empty coefficients",
                "All coefficients in the 'Coefficients' tab are 0 (or empty),\n"
                "so the TOTAL WEIGHT will be 0.\n\n"
                "Do you want to continue anyway?"):
                return
        self.resultados_normal = []
        errores = []

        for e in self.sb_entries:
            rev_path = os.path.join(carpeta, e["file"])
            try:
                if e["mode"] == "Revised" and e["previous"]:
                    orig_path = os.path.join(carpeta, e["previous"])
                    res = comparar_zips(orig_path, rev_path, coef)
                    res["Zip"] = e["file"]
                    res["Type"] = f"REVISED (vs {e['previous']})"
                    res["_previous"] = e["previous"]
                else:
                    res = self._pesar_nuevo(rev_path, e["file"], coef)
                    res["_previous"] = ""
                self.resultados_normal.append(res)
            except Exception as ex:
                errores.append(f"{e['file']}: {ex}")

        self._fill_new_results()

        if errores:
            messagebox.showwarning(
                "Compute",
                f"Weighting complete ({len(self.resultados_normal)} OK).\n\n"
                "Could not be weighted:\n" + "\n".join(errores))
        else:
            messagebox.showinfo(
                "Compute", f"Weighting complete: {len(self.resultados_normal)} SB(s).")

    def _fill_new_results(self):
        t = self.tree_res
        t.delete(*t.get_children())
        for idx, item in enumerate(self.resultados_normal):
            agg = exportacion.agregar_por_contador(item)
            counts = tuple(self._fmt(agg[c]["count"]) for c in CONTADORES)
            vals = (
                item.get("Zip", ""),
                self._mode_short(item.get("Type", "")),
                item.get("_previous", ""),
                self._fmt(item.get("Total Weight", 0)),
            ) + counts
            t.insert("", "end", iid=str(idx), values=vals)

    def _clear_results_new(self):
        """Clears only the bottom results table (keeps the Selected SBs list)."""
        self.resultados_normal = []
        self.tree_res.delete(*self.tree_res.get_children())

    def _resolve_export_path(self, default_name, title):
        """Devuelve la ruta destino. Si hay 'Where to save' fijada, guarda allí
        con el nombre por defecto (auto-versionado); si no, abre un diálogo."""
        folder = self.report_folder.get().strip().strip('"').strip()
        if folder:
            folder = os.path.normpath(os.path.expanduser(os.path.expandvars(folder)))
        if folder and os.path.isdir(folder):
            return os.path.join(folder, default_name)
        ruta = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=default_name,
            confirmoverwrite=False,
        )
        return ruta or None

    def _export_normal(self):
        if not self.resultados_normal:
            messagebox.showwarning("Export", "No results. Run Compute first.")
            return
        ruta = self._resolve_export_path("reporte_new_revised.xlsx",
                                         "Export New & Revised results")
        if not ruta:
            return
        try:
            final = exportacion.exportar_resultados(self.resultados_normal, ruta)
            messagebox.showinfo("Export", f"Saved to:\n{final}")
        except Exception as ex:
            messagebox.showerror("Export", f"Could not export:\n{ex}")

    # ================================================================== #
    #  PESTAÑA 3 — DUMMY / DUPLICATE
    # ================================================================== #
    def _build_dummy_tab(self):
        panels = ttk.Frame(self.tab_dummy, padding=(10, 10))
        panels.pack(fill="both", expand=True)

        fI = ttk.LabelFrame(panels, text="Initial SBs", padding=8)
        fI.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._build_dummy_panel(fI, "initial")

        fD = ttk.LabelFrame(panels, text="Duplicate SBs", padding=8)
        fD.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self._build_dummy_panel(fD, "duplicate")

        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        panels.rowconfigure(0, weight=1)

        ttk.Label(
            self.tab_dummy,
            text=("Initial row N is paired with Duplicate row N. "
                  "Use ▲ ▼ and 🗑 to review and change the pairs before running."),
            foreground="#555",
        ).pack(padx=10, anchor="w")

        act = ttk.Frame(self.tab_dummy, padding=(10, 5))
        act.pack(fill="x")
        ttk.Button(act, text="▶ Compute", style="Big.TButton",
                   command=self._compute_dummy).pack(side="right")

        res = ttk.LabelFrame(
            self.tab_dummy,
            text="Pricing results  —  double-click a row to see the per-counter, per-XML breakdown (930 / 933)",
            padding=8,
        )
        res.pack(fill="both", expand=True, padx=10, pady=5)

        rcols = ("SB Ident", "Dummy (vs)", "DIFFERENTIAL WEIGHT") + tuple(CONTADORES)
        self.tree_res_dummy = ttk.Treeview(res, columns=rcols, show="headings", height=7)
        self.tree_res_dummy.heading("SB Ident", text="SB Ident")
        self.tree_res_dummy.column("SB Ident", width=230, anchor="w")
        self.tree_res_dummy.heading("Dummy (vs)", text="Dummy (vs)")
        self.tree_res_dummy.column("Dummy (vs)", width=210, anchor="w")
        self.tree_res_dummy.heading("DIFFERENTIAL WEIGHT", text="DIFFERENTIAL WEIGHT")
        self.tree_res_dummy.column("DIFFERENTIAL WEIGHT", width=160, anchor="center")
        for c in CONTADORES:
            self.tree_res_dummy.heading(c, text=c)
            self.tree_res_dummy.column(c, width=55, anchor="center")

        rvsb = ttk.Scrollbar(res, orient="vertical", command=self.tree_res_dummy.yview)
        rhsb = ttk.Scrollbar(res, orient="horizontal", command=self.tree_res_dummy.xview)
        self.tree_res_dummy.configure(yscrollcommand=rvsb.set, xscrollcommand=rhsb.set)
        self.tree_res_dummy.grid(row=0, column=0, sticky="nsew")
        rvsb.grid(row=0, column=1, sticky="ns")
        rhsb.grid(row=1, column=0, sticky="ew")
        res.rowconfigure(0, weight=1)
        res.columnconfigure(0, weight=1)
        self.tree_res_dummy.bind(
            "<Double-1>",
            lambda e: self._show_breakdown(self.tree_res_dummy, self.resultados_dummy),
        )

        exp = ttk.Frame(self.tab_dummy, padding=(10, 0, 10, 10))
        exp.pack(fill="x")
        ttk.Button(exp, text="Joint export (both tabs)...",
                   command=self._export_joint).pack(side="right", padx=(5, 0))
        ttk.Button(exp, text="Export dummy results...",
                   command=self._export_dummy).pack(side="right")

    def _build_dummy_panel(self, parent, which):
        count_var = self.dummy_initial_count if which == "initial" else self.dummy_duplicate_count

        bar = ttk.Frame(parent)
        bar.pack(fill="x")
        ttk.Button(bar, text="Select files...",
                   command=lambda: self._on_select_dummy_files(which)).pack(side="left")
        ttk.Button(bar, text="Duplicate",
                   command=lambda: self._dummy_duplicate(which)).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Clear",
                   command=lambda: self._dummy_clear(which)).pack(side="left", padx=(6, 0))
        ttk.Label(bar, textvariable=count_var, foreground="#555").pack(
            side="left", padx=(8, 0))

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, pady=(6, 0))

        cols = ("#", "File")
        tree = ttk.Treeview(body, columns=cols, show="headings")
        tree.heading("#", text="#")
        tree.column("#", width=36, anchor="center")
        tree.heading("File", text="File")
        tree.column("File", width=300, anchor="w")
        vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        btns = ttk.Frame(body)
        btns.grid(row=0, column=2, sticky="ns", padx=(6, 0))
        ttk.Button(btns, text="🗑", width=3,
                   command=lambda: self._dummy_delete(which)).pack()
        ttk.Button(btns, text="▲", width=3,
                   command=lambda: self._dummy_move(which, -1)).pack(pady=(6, 0))
        ttk.Button(btns, text="▼", width=3,
                   command=lambda: self._dummy_move(which, 1)).pack(pady=(6, 0))

        if which == "initial":
            self.tree_dummy_initial = tree
        else:
            self.tree_dummy_duplicate = tree

    # Helpers de acceso a la lista/tree según el panel
    def _dummy_list(self, which):
        return self.dummy_initial if which == "initial" else self.dummy_duplicate

    def _set_dummy_list(self, which, lst):
        if which == "initial":
            self.dummy_initial = lst
        else:
            self.dummy_duplicate = lst

    def _dummy_tree(self, which):
        return self.tree_dummy_initial if which == "initial" else self.tree_dummy_duplicate

    def _dummy_count_var(self, which):
        return self.dummy_initial_count if which == "initial" else self.dummy_duplicate_count

    def _on_select_dummy_files(self, which):
        """Selección MÚLTIPLE de ficheros (no carpeta). Se añaden a la lista."""
        paths = filedialog.askopenfilenames(
            title="Select one or more SB ZIP files",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        )
        if not paths:
            return
        lst = self._dummy_list(which)
        for p in paths:
            if p not in lst:
                lst.append(p)
        self._refresh_dummy_tree(which)

    def _dummy_clear(self, which):
        self._set_dummy_list(which, [])
        self._refresh_dummy_tree(which)

    def _dummy_duplicate(self, which):
        """Duplica la(s) fila(s) seleccionada(s): útil si varios duplicados
        comparten el mismo SB original, sin tener que reseleccionar ficheros."""
        tree = self._dummy_tree(which)
        lst = self._dummy_list(which)
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("Duplicate", "Select one or more rows to duplicate.")
            return
        # Insertamos una copia justo después de cada seleccionada (de mayor a menor índice)
        for i in sorted((int(x) for x in sel), reverse=True):
            lst.insert(i + 1, lst[i])
        self._refresh_dummy_tree(which)

    def _refresh_dummy_tree(self, which):
        tree = self._dummy_tree(which)
        lst = self._dummy_list(which)
        tree.delete(*tree.get_children())
        for i, p in enumerate(lst):
            tree.insert("", "end", iid=str(i), values=(i + 1, os.path.basename(p)))
        self._dummy_count_var(which).set(f"{len(lst)} file(s)")

    def _dummy_delete(self, which):
        tree = self._dummy_tree(which)
        lst = self._dummy_list(which)
        sel = tree.selection()
        if not sel:
            return
        for i in sorted((int(x) for x in sel), reverse=True):
            del lst[i]
        self._refresh_dummy_tree(which)

    def _dummy_move(self, which, delta):
        tree = self._dummy_tree(which)
        lst = self._dummy_list(which)
        sel = tree.selection()
        if not sel:
            return
        i = int(sel[0])
        j = i + delta
        if j < 0 or j >= len(lst):
            return
        lst[i], lst[j] = lst[j], lst[i]
        self._refresh_dummy_tree(which)
        tree.selection_set(str(j))
        tree.see(str(j))

    def _compute_dummy(self):
        if not self.dummy_initial or not self.dummy_duplicate:
            messagebox.showwarning("Compute", "Select files in Initial and Duplicate.")
            return

        n = min(len(self.dummy_initial), len(self.dummy_duplicate))
        if len(self.dummy_initial) != len(self.dummy_duplicate):
            if not messagebox.askyesno(
                "Unequal pairs",
                f"Initial has {len(self.dummy_initial)} SB(s) and Duplicate {len(self.dummy_duplicate)}.\n"
                f"Only the first {n} will be paired. Continue?"):
                return

        coef = self.obtener_coeficientes()
        if not self._hay_coeficientes(coef):
            if not messagebox.askyesno(
                "Empty coefficients",
                "All coefficients in the 'Coefficients' tab are 0 (or empty),\n"
                "so the DIFFERENTIAL WEIGHT will be 0.\n\n"
                "Do you want to continue anyway?"):
                return
        self.resultados_dummy = []
        errores = []

        for i in range(n):
            ini_path = self.dummy_initial[i]      # baseline (original)
            dup_path = self.dummy_duplicate[i]    # SB que se pesa (nuevo)
            ini = os.path.basename(ini_path)
            dup = os.path.basename(dup_path)
            try:
                # comparar_zips(old, new): el diferencial es 'lo nuevo en dup vs ini'
                res = comparar_zips(ini_path, dup_path, coef)
                res["Zip"] = dup
                res["Type"] = f"DUMMY (vs {ini})"
                res["_pair"] = ini
                self.resultados_dummy.append(res)
            except Exception as ex:
                errores.append(f"{dup} vs {ini}: {ex}")

        self._fill_dummy_results()

        if errores:
            messagebox.showwarning(
                "Compute",
                f"Dummy weighting complete ({len(self.resultados_dummy)} OK).\n\n"
                "Pairs with errors:\n" + "\n".join(errores))
        else:
            messagebox.showinfo(
                "Compute", f"Dummy weighting complete: {len(self.resultados_dummy)} pair(s).")

    def _fill_dummy_results(self):
        t = self.tree_res_dummy
        t.delete(*t.get_children())
        for idx, item in enumerate(self.resultados_dummy):
            agg = exportacion.agregar_por_contador(item)
            counts = tuple(self._fmt(agg[c]["count"]) for c in CONTADORES)
            vals = (
                item.get("Zip", ""),
                item.get("_pair", ""),
                self._fmt(item.get("Total Weight", 0)),
            ) + counts
            t.insert("", "end", iid=str(idx), values=vals)

    def _export_dummy(self):
        if not self.resultados_dummy:
            messagebox.showwarning("Export", "No dummy results. Run Compute first.")
            return
        ruta = self._resolve_export_path("reporte_dummy.xlsx", "Export dummy results")
        if not ruta:
            return
        try:
            final = exportacion.exportar_resultados(self.resultados_dummy, ruta)
            messagebox.showinfo("Export", f"Saved to:\n{final}")
        except Exception as ex:
            messagebox.showerror("Export", f"Could not export:\n{ex}")

    def _export_joint(self):
        if not self.resultados_normal and not self.resultados_dummy:
            messagebox.showwarning("Export", "There are no results in either tab.")
            return
        ruta = self._resolve_export_path("reporte_conjunto.xlsx", "Joint export (both tabs)")
        if not ruta:
            return
        try:
            final = exportacion.exportar_combinado(
                self.resultados_normal, self.resultados_dummy, ruta)
            messagebox.showinfo("Export", f"Saved to:\n{final}")
        except Exception as ex:
            messagebox.showerror("Export", f"Could not export:\n{ex}")

    # ================================================================== #
    #  VENTANA DE DESGLOSE POR CONTADOR Y POR XML (930 / 933)
    # ================================================================== #
    def _por_modulo(self, item):
        """Por contador: cantidad y peso en 930 y en 933, y peso total (930+933)."""
        det = item.get("Details", {})

        def cw(mod, key):
            info = det.get(mod, {}).get("weights", {}).get(key, {})
            return (float(info.get("count", 0) or 0), float(info.get("weight", 0) or 0))

        out = {}
        for c in CONTADORES:
            c930, w930 = cw("930", c)
            c933, w933 = cw("933", c)
            out[c] = {"c930": c930, "c933": c933,
                      "w930": w930, "w933": w933, "wt": w930 + w933}
        return out

    def _show_breakdown(self, tree, resultados):
        sel = tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(resultados):
            return
        item = resultados[idx]
        por_mod = self._por_modulo(item)
        total = item.get("Total Weight", 0)

        win = tk.Toplevel(self)
        win.title(f"Breakdown — {item.get('Zip', '')}")
        win.geometry("780x620")
        win.transient(self)

        ttk.Label(win, text=item.get("Zip", ""),
                  font=("Segoe UI", 11, "bold")).pack(pady=(10, 0))
        ttk.Label(win, text=item.get("Type", ""), foreground="#555").pack()

        # Peso total destacado (suma de los 15 contadores de los DOS XML)
        big = ttk.Frame(win, padding=10)
        big.pack(fill="x")
        ttk.Label(big, text="TOTAL WEIGHT  (930 + 933)", font=("Segoe UI", 10)).pack()
        ttk.Label(big, text=self._fmt(total),
                  font=("Segoe UI", 26, "bold"), foreground="#0a7d28").pack()

        # Tabla por contador, con columnas para cada XML
        cols = ("Counter", "Count 930", "Count 933", "Weight 930", "Weight 933", "Weight total")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=17)
        for c, w in zip(cols, (80, 90, 90, 100, 100, 110)):
            tv.heading(c, text=c)
            tv.column(c, width=w, anchor="center")
        tv.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tot = {"c930": 0.0, "c933": 0.0, "w930": 0.0, "w933": 0.0, "wt": 0.0}
        for c in CONTADORES:
            a = por_mod[c]
            for k in tot:
                tot[k] += a[k]
            tv.insert("", "end", values=(
                c,
                self._fmt(a["c930"]), self._fmt(a["c933"]),
                self._fmt(a["w930"]), self._fmt(a["w933"]),
                self._fmt(a["wt"]),
            ))
        # Fila TOTAL (sumando ambos XML)
        tv.insert("", "end", values=(
            "TOTAL",
            self._fmt(tot["c930"]), self._fmt(tot["c933"]),
            self._fmt(tot["w930"]), self._fmt(tot["w933"]),
            self._fmt(tot["wt"]),
        ))

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))


if __name__ == "__main__":
    app = App()
    app.mainloop()
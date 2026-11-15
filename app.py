import calendar
import sqlite3
import sys
import tkinter as tk
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import openpyxl


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


DB_FILE = get_base_dir() / "db.sqlite3"


MESES = {
    "01 - Janeiro": "01",
    "02 - Fevereiro": "02",
    "03 - Março": "03",
    "04 - Abril": "04",
    "05 - Maio": "05",
    "06 - Junho": "06",
    "07 - Julho": "07",
    "08 - Agosto": "08",
    "09 - Setembro": "09",
    "10 - Outubro": "10",
    "11 - Novembro": "11",
    "12 - Dezembro": "12",
}


# ==============================================================================
# 1. VALIDATION & FORMATTING
# ==============================================================================


def parse_positive_decimal(raw: str, label: str) -> Decimal:
    try:
        val = Decimal(raw.strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{label} inválido.")
    if not val.is_finite() or val <= 0:
        raise ValueError(f"{label} deve ser maior que zero.")
    return val


def parse_money(raw: str) -> float:
    return float(round(parse_positive_decimal(raw, "Preço"), 2))


def parse_quantity(raw: str, medida: str) -> float:
    val = parse_positive_decimal(raw, "Quantidade")
    if medida == "unidade":
        if val != val.to_integral_value():
            raise ValueError(
                "Produtos em 'unidade' não permitem quantidade fracionada."
            )
        return float(int(val))
    if medida == "kg":
        return float(round(val, 4))
    raise ValueError("Medida inválida.")


def parse_datetime_br(raw: str) -> str:
    text = raw.strip()
    if not text:
        return datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        return datetime.strptime(text, "%d/%m/%Y %H:%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError("Data/hora inválida. Use DD/MM/AAAA HH:MM.")


def format_datetime_br(iso_str: str) -> str:
    return datetime.strptime(iso_str, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")


def fmt_qtd(qtd: float, medida: str) -> str:
    return f"{int(qtd)}" if medida == "unidade" else f"{qtd:.3f}"


# ==============================================================================
# 2. DATABASE LAYER
# ==============================================================================


class Database:
    def __init__(self, path: Path = DB_FILE):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def _init_schema(self):
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS catalogo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    produto TEXT NOT NULL UNIQUE CHECK(length(trim(produto)) > 0),
                    preco REAL NOT NULL CHECK(preco > 0),
                    medida TEXT NOT NULL CHECK(medida IN ('unidade', 'kg'))
                ) STRICT;

                CREATE TABLE IF NOT EXISTS lancamentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL CHECK(data GLOB '????-??-?? ??:??'),
                    produto_id INTEGER NOT NULL REFERENCES catalogo(id) ON DELETE RESTRICT,
                    produto_nome TEXT NOT NULL,
                    quantidade REAL NOT NULL CHECK(quantidade > 0),
                    medida TEXT NOT NULL CHECK(medida IN ('unidade', 'kg')),
                    preco_unitario REAL NOT NULL CHECK(preco_unitario > 0),
                    total REAL NOT NULL CHECK(total > 0),
                    CHECK(medida = 'kg' OR quantidade = floor(quantidade))
                ) STRICT;
            """)
            if self.conn.execute("SELECT COUNT(*) FROM catalogo").fetchone()[0] == 0:
                self.conn.executemany(
                    "INSERT INTO catalogo (produto, preco, medida) VALUES (?, ?, ?)",
                    [(p.strip().upper(), pr, m) for p, pr, m in INITIAL_PRODUCTS],
                )

    def get_catalog(self):
        return self.conn.execute(
            "SELECT id, produto, preco, medida FROM catalogo ORDER BY produto ASC"
        ).fetchall()

    def get_product_by_name(self, name: str):
        return self.conn.execute(
            "SELECT id, produto, preco, medida FROM catalogo WHERE produto = ?",
            (name.strip().upper(),),
        ).fetchone()

    def upsert_product(
        self, produto: str, preco_raw: str, medida: str, prod_id: int | None = None
    ):
        nome = produto.strip().upper()
        if not nome:
            raise ValueError("Nome do produto é obrigatório.")
        if medida not in ("unidade", "kg"):
            raise ValueError("Medida deve ser 'unidade' ou 'kg'.")
        preco = parse_money(preco_raw)

        try:
            with self.conn:
                if prod_id is None:
                    self.conn.execute(
                        "INSERT INTO catalogo (produto, preco, medida) VALUES (?, ?, ?)",
                        (nome, preco, medida),
                    )
                else:
                    self.conn.execute(
                        "UPDATE catalogo SET produto = ?, preco = ?, medida = ? WHERE id = ?",
                        (nome, preco, medida, prod_id),
                    )
        except sqlite3.IntegrityError:
            raise ValueError(f"Produto '{nome}' já existe no catálogo.")

    def delete_product(self, prod_id: int):
        try:
            with self.conn:
                self.conn.execute("DELETE FROM catalogo WHERE id = ?", (prod_id,))
        except sqlite3.IntegrityError:
            raise ValueError(
                "Não é possível excluir: produto já possui lançamentos registrados."
            )

    def upsert_lancamento(
        self, data_raw: str, produto_nome: str, qtd_raw: str, lanc_id: int | None = None
    ):
        prod = self.get_product_by_name(produto_nome)
        if not prod:
            raise ValueError("Selecione um produto válido cadastrado no Catálogo.")

        iso_dt = parse_datetime_br(data_raw)
        medida, preco = prod["medida"], float(prod["preco"])

        if lanc_id is not None:
            existing = self.conn.execute(
                "SELECT produto_id, medida, preco_unitario FROM lancamentos WHERE id = ?",
                (lanc_id,),
            ).fetchone()
            if not existing:
                raise ValueError("Lançamento não encontrado.")
            if existing["produto_id"] == prod["id"]:
                medida, preco = existing["medida"], float(existing["preco_unitario"])

        qtd = parse_quantity(qtd_raw, medida)
        total = round(qtd * preco, 2)

        with self.conn:
            if lanc_id is None:
                self.conn.execute(
                    """INSERT INTO lancamentos
                       (data, produto_id, produto_nome, quantidade, medida, preco_unitario, total)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (iso_dt, prod["id"], prod["produto"], qtd, medida, preco, total),
                )
            else:
                self.conn.execute(
                    """UPDATE lancamentos
                       SET data = ?, produto_id = ?, produto_nome = ?,
                           quantidade = ?, medida = ?, preco_unitario = ?, total = ?
                       WHERE id = ?""",
                    (
                        iso_dt,
                        prod["id"],
                        prod["produto"],
                        qtd,
                        medida,
                        preco,
                        total,
                        lanc_id,
                    ),
                )

    def get_lancamentos(self, limit: int = 300):
        return self.conn.execute(
            """SELECT id, data, produto_nome, quantidade, medida, preco_unitario, total
               FROM lancamentos ORDER BY data DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    def delete_lancamento(self, lanc_id: int):
        with self.conn:
            self.conn.execute("DELETE FROM lancamentos WHERE id = ?", (lanc_id,))

    def get_available_years(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT substr(data, 1, 4) AS ano FROM lancamentos ORDER BY ano DESC"
        ).fetchall()
        years = [r["ano"] for r in rows]
        cur = str(date.today().year)
        if cur not in years:
            years.insert(0, cur)
        return years

    def get_monthly_summary(self, year: str):
        return self.conn.execute(
            """SELECT substr(data, 6, 2) AS mes,
                      COALESCE(SUM(CASE WHEN medida = 'unidade' THEN quantidade ELSE 0 END), 0) AS total_un,
                      COALESCE(SUM(CASE WHEN medida = 'kg' THEN quantidade ELSE 0 END), 0) AS total_kg,
                      COALESCE(SUM(total), 0) AS total_valor
               FROM lancamentos WHERE substr(data, 1, 4) = ?
               GROUP BY mes ORDER BY mes ASC""",
            (year,),
        ).fetchall()

    def get_product_breakdown(self, year: str, month: str):
        return self.conn.execute(
            """SELECT produto_nome, medida, SUM(quantidade) AS qtd_total, SUM(total) AS valor_total
               FROM lancamentos WHERE substr(data, 1, 7) = ?
               GROUP BY produto_nome, medida ORDER BY valor_total DESC""",
            (f"{year}-{month.zfill(2)}",),
        ).fetchall()


# ==============================================================================
# 3. CUSTOM WIDGETS (Strict Autocomplete + Calendar DateTime Picker)
# ==============================================================================


class AutocompleteCombobox(ttk.Entry):
    def __init__(self, master, on_valid_select=None, **kwargs):
        self._var = tk.StringVar()
        super().__init__(master, textvariable=self._var, **kwargs)
        self._all_values: list[str] = []
        self._on_valid_select = on_valid_select
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self._internal = False

        self._var.trace_add("write", self._on_text_changed)
        self.bind("<FocusIn>", lambda _: self._filter_and_show())
        self.bind("<Down>", lambda _: self._move(1))
        self.bind("<Up>", lambda _: self._move(-1))
        self.bind("<Return>", self._accept)
        self.bind("<Tab>", self._accept)
        self.bind("<Escape>", lambda _: self._close())
        self.bind("<FocusOut>", self._on_focus_out)

    def set_completion_list(self, values: list[str]):
        self._all_values = sorted(values)

    def get(self) -> str:
        return self._var.get()

    def set(self, value: str):
        self._internal = True
        self._var.set(value)
        self._internal = False

    def _on_text_changed(self, *_):
        if not self._internal and self.focus_get() is self:
            self._filter_and_show()

    def _filter_and_show(self):
        typed = self._var.get().strip().upper()
        matches = (
            [v for v in self._all_values if typed in v] if typed else self._all_values
        )
        if not matches:
            self._close()
            return

        if not self._popup or not self._popup.winfo_exists():
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            self._listbox = tk.Listbox(self._popup, exportselection=False, takefocus=0)
            self._listbox.pack(fill="both", expand=True)
            self._listbox.bind("<Button-1>", self._on_click)

        self._listbox.delete(0, tk.END)
        for item in matches:
            self._listbox.insert(tk.END, item)
        self._listbox.selection_set(0)

        x, y = self.winfo_rootx(), self.winfo_rooty() + self.winfo_height()
        w = max(self.winfo_width(), 280)
        h = min(len(matches), 8) * 20 + 4
        self._popup.geometry(f"{w}x{h}+{x}+{y}")
        self._popup.lift()

    def _move(self, delta: int):
        if not self._popup or not self._popup.winfo_exists():
            self._filter_and_show()
            return "break"
        cur = self._listbox.curselection()
        idx = max(0, min(self._listbox.size() - 1, (cur[0] if cur else 0) + delta))
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        return "break"

    def _accept(self, event=None):
        if self._popup and self._popup.winfo_exists() and self._listbox.curselection():
            self._commit(self._listbox.get(self._listbox.curselection()[0]))
            if event and event.keysym == "Return":
                return "break"

    def _on_click(self, event):
        idx = self._listbox.nearest(event.y)
        if 0 <= idx < self._listbox.size():
            self._commit(self._listbox.get(idx))
        self.focus_set()

    def _commit(self, value: str):
        self.set(value)
        self.icursor(tk.END)
        self._close()
        if self._on_valid_select:
            self._on_valid_select(value)

    def _on_focus_out(self, _event=None):
        self._close()
        val = self._var.get().strip().upper()
        if val in self._all_values:
            self._commit(val)
        else:
            self.set("")
            if self._on_valid_select:
                self._on_valid_select("")

    def _close(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
        self._popup = None
        self._listbox = None


class DateTimePicker(ttk.Frame):
    def __init__(self, master, width: int = 16):
        super().__init__(master)
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, width=width)
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(self, text="📅", width=3, command=self._open_calendar).pack(
            side="left", padx=(2, 0)
        )
        self._popup: tk.Toplevel | None = None

    def get(self) -> str:
        return self.var.get()

    def set(self, val: str):
        self.var.set(val)

    def _current_dt(self) -> datetime:
        try:
            return datetime.strptime(self.var.get().strip(), "%d/%m/%Y %H:%M")
        except ValueError:
            return datetime.now()

    def _open_calendar(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            return

        dt = self._current_dt()
        self._cal_year, self._cal_month = dt.year, dt.month
        self._hour_var = tk.StringVar(value=f"{dt.hour:02d}")
        self._min_var = tk.StringVar(value=f"{dt.minute:02d}")

        self._popup = tk.Toplevel(self)
        self._popup.wm_overrideredirect(True)
        self._popup.attributes("-topmost", True)

        container = ttk.Frame(self._popup, relief="solid", borderwidth=1, padding=6)
        container.pack()

        # Header: Month/Year navigation
        nav = ttk.Frame(container)
        nav.pack(fill="x", pady=(0, 4))
        ttk.Button(nav, text="<", width=3, command=lambda: self._shift_month(-1)).pack(
            side="left"
        )
        self._lbl_month = ttk.Label(
            nav, width=14, anchor="center", font=("TkDefaultFont", 9, "bold")
        )
        self._lbl_month.pack(side="left", expand=True)
        ttk.Button(nav, text=">", width=3, command=lambda: self._shift_month(1)).pack(
            side="right"
        )

        # Day grid
        self._grid_frame = ttk.Frame(container)
        self._grid_frame.pack()

        # Time selector + Now button
        time_bar = ttk.Frame(container)
        time_bar.pack(fill="x", pady=(6, 0))
        ttk.Label(time_bar, text="Hora:").pack(side="left")
        ttk.Spinbox(
            time_bar,
            from_=0,
            to=23,
            format="%02.0f",
            textvariable=self._hour_var,
            width=3,
        ).pack(side="left", padx=2)
        ttk.Label(time_bar, text=":").pack(side="left")
        ttk.Spinbox(
            time_bar,
            from_=0,
            to=59,
            format="%02.0f",
            textvariable=self._min_var,
            width=3,
        ).pack(side="left", padx=2)
        ttk.Button(time_bar, text="Agora", width=6, command=self._pick_now).pack(
            side="right"
        )
        ttk.Button(time_bar, text="Fechar", width=6, command=self._popup.destroy).pack(
            side="right", padx=2
        )

        self._render_days()

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self._popup.geometry(f"+{x}+{y}")

    def _shift_month(self, delta: int):
        m = self._cal_month + delta
        if m < 1:
            self._cal_month, self._cal_year = 12, self._cal_year - 1
        elif m > 12:
            self._cal_month, self._cal_year = 1, self._cal_year + 1
        else:
            self._cal_month = m
        self._render_days()

    def _render_days(self):
        for w in self._grid_frame.winfo_children():
            w.destroy()

        month_name = list(MESES.keys())[self._cal_month - 1].split(" - ")[1]
        self._lbl_month.config(text=f"{month_name} {self._cal_year}")

        for idx, day_name in enumerate(
            ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        ):
            ttk.Label(self._grid_frame, text=day_name, width=4, anchor="center").grid(
                row=0, column=idx
            )

        for r_idx, week in enumerate(
            calendar.monthcalendar(self._cal_year, self._cal_month), start=1
        ):
            for c_idx, day in enumerate(week):
                if day:
                    ttk.Button(
                        self._grid_frame,
                        text=str(day),
                        width=3,
                        command=lambda d=day: self._select_day(d),
                    ).grid(row=r_idx, column=c_idx, padx=1, pady=1)

    def _select_day(self, day: int):
        try:
            h = max(0, min(23, int(self._hour_var.get())))
            m = max(0, min(59, int(self._min_var.get())))
        except ValueError:
            now = datetime.now()
            h, m = now.hour, now.minute
        self.set(f"{day:02d}/{self._cal_month:02d}/{self._cal_year} {h:02d}:{m:02d}")
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()

    def _pick_now(self):
        self.set(datetime.now().strftime("%d/%m/%Y %H:%M"))
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()


# ==============================================================================
# 4. MAIN APPLICATION
# ==============================================================================


class App(tk.Tk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.title("Lança Fácil")
        self.iconbitmap(default=str(resource_path("icon.ico")))
        self.minsize(860, 540)
        try:
            self.state("zoomed")
        except tk.TclError:
            self.attributes("-zoomed", True)

        ttk.Style(self).theme_use("clam")

        self.selected_cat_id: int | None = None
        self.selected_lanc_id: int | None = None

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_lanc = ttk.Frame(self.notebook, padding=10)
        self.tab_cat = ttk.Frame(self.notebook, padding=10)
        self.tab_rel = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_lanc, text="Lançamentos")
        self.notebook.add(self.tab_cat, text="Catálogo")
        self.notebook.add(self.tab_rel, text="Relatórios")

        self._build_lancamentos_tab()
        self._build_catalogo_tab()
        self._build_relatorios_tab()

        self.refresh_all()
        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self.refresh_all())

    @staticmethod
    def _make_treeview(
        parent, columns_spec: list[tuple[str, str, int, str]]
    ) -> ttk.Treeview:
        cols = [c[0] for c in columns_spec]
        tree = ttk.Treeview(parent, columns=cols, show="headings")
        for col, title, width, anchor in columns_spec:
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor=anchor)
        return tree

    @staticmethod
    def _populate_tree(tree: ttk.Treeview, rows: list[tuple]):
        tree.delete(*tree.get_children())
        for r in rows:
            tree.insert("", "end", values=r)

    # --------------------------------------------------------------------------
    # TAB 1: LANCAMENTOS
    # --------------------------------------------------------------------------
    def _build_lancamentos_tab(self):
        form = ttk.LabelFrame(self.tab_lanc, text="Lançamento", padding=10)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Data e Hora:").grid(row=0, column=0, sticky="w", padx=4)
        self.dt_lanc = DateTimePicker(form, width=16)
        self.dt_lanc.grid(row=1, column=0, padx=4, pady=2)

        ttk.Label(form, text="Produto:").grid(row=0, column=1, sticky="w", padx=4)
        self.cmb_lanc_prod = AutocompleteCombobox(
            form, width=36, on_valid_select=self._on_lanc_product_selected
        )
        self.cmb_lanc_prod.grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(form, text="Quantidade:").grid(row=0, column=2, sticky="w", padx=4)
        self.var_lanc_qtd = tk.StringVar()
        self.var_lanc_qtd.trace_add("write", lambda *_: self._recalc_lanc_preview())
        ttk.Entry(form, width=12, textvariable=self.var_lanc_qtd).grid(
            row=1, column=2, padx=4, pady=2
        )

        self.var_lanc_medida = tk.StringVar(value="-")
        self.var_lanc_preco = tk.StringVar(value="0.00")
        self.var_lanc_total = tk.StringVar(value="0.00")

        for col_idx, (lbl, var, w) in enumerate(
            [
                ("Medida:", self.var_lanc_medida, 10),
                ("Preço (R$):", self.var_lanc_preco, 10),
                ("Total (R$):", self.var_lanc_total, 12),
            ],
            start=3,
        ):
            ttk.Label(form, text=lbl).grid(row=0, column=col_idx, sticky="w", padx=4)
            ttk.Entry(form, width=w, textvariable=var, state="readonly").grid(
                row=1, column=col_idx, padx=4, pady=2
            )

        ttk.Button(form, text="Salvar", command=self._save_lancamento).grid(
            row=1, column=6, padx=(8, 2), pady=2
        )
        ttk.Button(form, text="Limpar", command=self._clear_lancamento_form).grid(
            row=1, column=7, padx=2, pady=2
        )

        self.tree_lanc = self._make_treeview(
            self.tab_lanc,
            [
                ("id", "ID", 50, "w"),
                ("data", "Data / Hora", 140, "w"),
                ("produto", "Produto", 280, "w"),
                ("qtd", "Qtd", 90, "e"),
                ("medida", "Medida", 90, "center"),
                ("preco", "Preço (R$)", 110, "e"),
                ("total", "Total (R$)", 110, "e"),
            ],
        )
        self.tree_lanc.pack(fill="both", expand=True)
        self.tree_lanc.bind("<<TreeviewSelect>>", self._on_lanc_select)

        bottom = ttk.Frame(self.tab_lanc)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(
            bottom, text="Excluir Selecionado", command=self._delete_lancamento
        ).pack(side="right")

    def _on_lanc_product_selected(self, prod_name: str):
        if prod_name and not self.dt_lanc.get().strip():
            self.dt_lanc.set(datetime.now().strftime("%d/%m/%Y %H:%M"))

        prod = self.db.get_product_by_name(prod_name) if prod_name else None
        if prod:
            self.var_lanc_medida.set(prod["medida"])
            self.var_lanc_preco.set(f"{prod['preco']:.2f}")
        else:
            self.var_lanc_medida.set("-")
            self.var_lanc_preco.set("0.00")
        self._recalc_lanc_preview()

    def _recalc_lanc_preview(self):
        medida = self.var_lanc_medida.get()
        if medida not in ("unidade", "kg"):
            self.var_lanc_total.set("0.00")
            return
        try:
            preco = float(self.var_lanc_preco.get())
            qtd = parse_quantity(self.var_lanc_qtd.get(), medida)
            self.var_lanc_total.set(f"{qtd * preco:.2f}")
        except ValueError:
            self.var_lanc_total.set("0.00")

    def _on_lanc_select(self, _event=None):
        sel = self.tree_lanc.selection()
        if not sel:
            return
        vals = self.tree_lanc.item(sel[0], "values")
        self.selected_lanc_id = int(vals[0])
        self.dt_lanc.set(vals[1])
        self.cmb_lanc_prod.set(vals[2])
        self.var_lanc_qtd.set(vals[3])
        self.var_lanc_medida.set(vals[4])
        self.var_lanc_preco.set(vals[5])
        self.var_lanc_total.set(vals[6])

    def _clear_lancamento_form(self):
        self.selected_lanc_id = None
        self.dt_lanc.set("")
        self.cmb_lanc_prod.set("")
        self.var_lanc_qtd.set("")
        self.var_lanc_medida.set("-")
        self.var_lanc_preco.set("0.00")
        self.var_lanc_total.set("0.00")
        self.tree_lanc.selection_remove(self.tree_lanc.selection())

    def _save_lancamento(self):
        try:
            self.db.upsert_lancamento(
                self.dt_lanc.get(),
                self.cmb_lanc_prod.get(),
                self.var_lanc_qtd.get(),
                self.selected_lanc_id,
            )
            self._clear_lancamento_form()
            self.refresh_all()
        except ValueError as exc:
            messagebox.showerror("Entrada Inválida", str(exc))

    def _delete_lancamento(self):
        sel = self.tree_lanc.selection()
        if not sel:
            return
        lanc_id = int(self.tree_lanc.item(sel[0], "values")[0])
        if messagebox.askyesno("Confirmar", "Excluir lançamento selecionado?"):
            self.db.delete_lancamento(lanc_id)
            self._clear_lancamento_form()
            self.refresh_all()

    # --------------------------------------------------------------------------
    # TAB 2: CATALOGO
    # --------------------------------------------------------------------------
    def _build_catalogo_tab(self):
        form = ttk.LabelFrame(self.tab_cat, text="Cadastro de Produtos", padding=10)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Produto:").grid(row=0, column=0, sticky="w", padx=4)
        self.ent_cat_nome = ttk.Entry(form, width=42)
        self.ent_cat_nome.grid(row=1, column=0, padx=4, pady=2)

        ttk.Label(form, text="Preço (R$):").grid(row=0, column=1, sticky="w", padx=4)
        self.ent_cat_preco = ttk.Entry(form, width=14)
        self.ent_cat_preco.grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(form, text="Medida:").grid(row=0, column=2, sticky="w", padx=4)
        self.cmb_cat_medida = ttk.Combobox(
            form, values=["unidade", "kg"], state="readonly", width=12
        )
        self.cmb_cat_medida.set("unidade")
        self.cmb_cat_medida.grid(row=1, column=2, padx=4, pady=2)

        ttk.Button(form, text="Salvar", command=self._save_catalogo).grid(
            row=1, column=3, padx=6
        )
        ttk.Button(form, text="Limpar", command=self._clear_catalogo_form).grid(
            row=1, column=4, padx=2
        )

        self.tree_cat = self._make_treeview(
            self.tab_cat,
            [
                ("id", "ID", 60, "w"),
                ("produto", "Produto", 440, "w"),
                ("preco", "Preço (R$)", 140, "e"),
                ("medida", "Medida", 120, "center"),
            ],
        )
        self.tree_cat.pack(fill="both", expand=True)
        self.tree_cat.bind("<<TreeviewSelect>>", self._on_cat_select)

        bottom = ttk.Frame(self.tab_cat)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(bottom, text="Excluir Produto", command=self._delete_catalogo).pack(
            side="right"
        )

    def _on_cat_select(self, _event=None):
        sel = self.tree_cat.selection()
        if not sel:
            return
        vals = self.tree_cat.item(sel[0], "values")
        self.selected_cat_id = int(vals[0])
        self.ent_cat_nome.delete(0, tk.END)
        self.ent_cat_nome.insert(0, vals[1])
        self.ent_cat_preco.delete(0, tk.END)
        self.ent_cat_preco.insert(0, vals[2])
        self.cmb_cat_medida.set(vals[3])

    def _clear_catalogo_form(self):
        self.selected_cat_id = None
        self.ent_cat_nome.delete(0, tk.END)
        self.ent_cat_preco.delete(0, tk.END)
        self.cmb_cat_medida.set("unidade")
        self.tree_cat.selection_remove(self.tree_cat.selection())

    def _save_catalogo(self):
        try:
            self.db.upsert_product(
                self.ent_cat_nome.get(),
                self.ent_cat_preco.get(),
                self.cmb_cat_medida.get(),
                self.selected_cat_id,
            )
            self._clear_catalogo_form()
            self.refresh_all()
        except ValueError as exc:
            messagebox.showerror("Erro no Catálogo", str(exc))

    def _delete_catalogo(self):
        if self.selected_cat_id is None:
            return
        if messagebox.askyesno("Confirmar", "Excluir produto selecionado?"):
            try:
                self.db.delete_product(self.selected_cat_id)
                self._clear_catalogo_form()
                self.refresh_all()
            except ValueError as exc:
                messagebox.showerror("Operação Bloqueada", str(exc))

    # --------------------------------------------------------------------------
    # TAB 3: RELATORIOS
    # --------------------------------------------------------------------------
    def _build_relatorios_tab(self):
        controls = ttk.Frame(self.tab_rel)
        controls.pack(fill="x", pady=(0, 8))

        ttk.Label(controls, text="Ano:").pack(side="left", padx=(0, 4))
        self.cmb_rel_ano = ttk.Combobox(controls, state="readonly", width=8)
        self.cmb_rel_ano.pack(side="left", padx=(0, 12))
        self.cmb_rel_ano.bind("<<ComboboxSelected>>", lambda _: self._refresh_reports())

        ttk.Label(controls, text="Mês:").pack(side="left", padx=(0, 4))
        self.cmb_rel_mes = ttk.Combobox(
            controls, values=list(MESES.keys()), state="readonly", width=16
        )
        self.cmb_rel_mes.current(date.today().month - 1)
        self.cmb_rel_mes.pack(side="left", padx=(0, 12))
        self.cmb_rel_mes.bind("<<ComboboxSelected>>", lambda _: self._refresh_reports())

        ttk.Button(
            controls, text="Exportar Excel (.xlsx)", command=self._export_excel
        ).pack(side="right")

        paned = ttk.PanedWindow(self.tab_rel, orient="horizontal")
        paned.pack(fill="both", expand=True)

        frame_left = ttk.LabelFrame(paned, text="Resumo Mensal", padding=6)
        frame_right = ttk.LabelFrame(
            paned, text="Produtos (Mês Selecionado)", padding=6
        )
        paned.add(frame_left, weight=1)
        paned.add(frame_right, weight=1)

        self.tree_rel_meses = self._make_treeview(
            frame_left,
            [
                ("mes", "Mês", 110, "w"),
                ("un", "Unidades", 90, "e"),
                ("kg", "Kg", 90, "e"),
                ("valor", "Total (R$)", 110, "e"),
            ],
        )
        self.tree_rel_meses.pack(fill="both", expand=True)
        self.tree_rel_meses.bind("<<TreeviewSelect>>", self._on_month_row_click)

        self.tree_rel_prod = self._make_treeview(
            frame_right,
            [
                ("produto", "Produto", 210, "w"),
                ("medida", "Medida", 70, "center"),
                ("qtd", "Quantidade", 90, "e"),
                ("valor", "Total (R$)", 100, "e"),
            ],
        )
        self.tree_rel_prod.pack(fill="both", expand=True)

    def _on_month_row_click(self, _event=None):
        sel = self.tree_rel_meses.selection()
        if not sel:
            return
        mes_num = self.tree_rel_meses.item(sel[0], "values")[0][:2]
        for label, code in MESES.items():
            if code == mes_num:
                self.cmb_rel_mes.set(label)
                self._refresh_product_breakdown()
                break

    def _refresh_reports(self):
        years = self.db.get_available_years()
        cur_year = self.cmb_rel_ano.get()
        self.cmb_rel_ano["values"] = years
        if cur_year not in years:
            cur_year = years[0]
            self.cmb_rel_ano.set(cur_year)

        summary = {r["mes"]: r for r in self.db.get_monthly_summary(cur_year)}
        rows = []
        for label, code in MESES.items():
            r = summary.get(code)
            rows.append(
                (
                    label,
                    int(r["total_un"]) if r else 0,
                    f"{r['total_kg']:.3f}" if r else "0.000",
                    f"{r['total_valor']:.2f}" if r else "0.00",
                )
            )
        self._populate_tree(self.tree_rel_meses, rows)
        self._refresh_product_breakdown()

    def _refresh_product_breakdown(self):
        year = self.cmb_rel_ano.get()
        month_code = MESES[self.cmb_rel_mes.get()]
        rows = [
            (
                r["produto_nome"],
                r["medida"],
                fmt_qtd(r["qtd_total"], r["medida"]),
                f"{r['valor_total']:.2f}",
            )
            for r in self.db.get_product_breakdown(year, month_code)
        ]
        self._populate_tree(self.tree_rel_prod, rows)

    def _export_excel(self):
        if openpyxl is None:
            messagebox.showerror(
                "Dependência Ausente",
                "Instale o pacote 'openpyxl' para exportar Excel.",
            )
            return

        year = self.cmb_rel_ano.get()
        month_code = MESES[self.cmb_rel_mes.get()]
        filepath = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Planilha Excel", "*.xlsx")],
            initialfile=f"Relatorio_{year}_{month_code}.xlsx",
        )
        if not filepath:
            return

        wb = openpyxl.Workbook()
        ws_geral = wb.active
        ws_geral.title = f"Resumo_{year}"
        ws_geral.append(["Mês", "Total Unidades", "Total Kg", "Total Valor (R$)"])

        summary = {r["mes"]: r for r in self.db.get_monthly_summary(year)}
        for label, code in MESES.items():
            r = summary.get(code)
            ws_geral.append(
                [
                    label,
                    int(r["total_un"]) if r else 0,
                    round(float(r["total_kg"]), 3) if r else 0.0,
                    round(float(r["total_valor"]), 2) if r else 0.0,
                ]
            )

        ws_prod = wb.create_sheet(title=f"Produtos_{year}_{month_code}")
        ws_prod.append(["Produto", "Medida", "Quantidade Total", "Valor Total (R$)"])
        for r in self.db.get_product_breakdown(year, month_code):
            qtd = (
                int(r["qtd_total"])
                if r["medida"] == "unidade"
                else round(float(r["qtd_total"]), 3)
            )
            ws_prod.append(
                [r["produto_nome"], r["medida"], qtd, round(float(r["valor_total"]), 2)]
            )

        wb.save(filepath)
        messagebox.showinfo("Exportação Concluída", f"Arquivo salvo em:\n{filepath}")

    # --------------------------------------------------------------------------
    # GLOBAL REFRESH
    # --------------------------------------------------------------------------
    def refresh_all(self):
        catalog_rows = self.db.get_catalog()
        self._populate_tree(
            self.tree_cat,
            [
                (r["id"], r["produto"], f"{r['preco']:.2f}", r["medida"])
                for r in catalog_rows
            ],
        )
        self.cmb_lanc_prod.set_completion_list([r["produto"] for r in catalog_rows])

        lanc_rows = [
            (
                r["id"],
                format_datetime_br(r["data"]),
                r["produto_nome"],
                fmt_qtd(r["quantidade"], r["medida"]),
                r["medida"],
                f"{r['preco_unitario']:.2f}",
                f"{r['total']:.2f}",
            )
            for r in self.db.get_lancamentos()
        ]
        self._populate_tree(self.tree_lanc, lanc_rows)
        self._refresh_reports()


if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "controledesperdicio.app"
        )

    app = App(Database(DB_FILE))
    app.mainloop()

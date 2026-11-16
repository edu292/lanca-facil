import tkinter as tk
from collections.abc import Callable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from csv_io import (
    export_catalog_csv,
    export_entries_csv,
    import_catalog_csv,
    import_entries_csv,
)
from db import Database, ImportStats
from formatting import (
    LABEL_TO_UNIT,
    UNIT_TO_LABEL,
    fmt_datetime_br,
    fmt_money,
    fmt_quantity,
    month_choices,
    month_label,
    parse_datetime_br,
    parse_money,
    parse_month_choice,
    parse_quantity,
)
from widgets import AutocompleteCombobox, DataTable, DateTimePicker, EditableTabBar


def run_csv_import(
    parent: tk.Misc,
    title: str,
    importer: Callable[[Path], ImportStats],
    on_success: Callable[[], None],
) -> None:
    path = filedialog.askopenfilename(
        parent=parent, title=title, filetypes=[("Arquivo CSV", "*.csv")]
    )
    if not path:
        return
    try:
        stats = importer(Path(path))
        on_success()
        lines = [f"Inseridos: {stats.inserted}"]
        if stats.updated:
            lines.append(f"Atualizados: {stats.updated}")
        lines.append(f"Ignorados: {stats.skipped}")
        messagebox.showinfo("Importação Concluída", "\n".join(lines), parent=parent)
    except Exception as exc:
        messagebox.showerror("Erro ao Importar CSV", str(exc), parent=parent)


def run_csv_export(
    parent: tk.Misc,
    title: str,
    default_filename: str,
    exporter: Callable[[Path], None],
) -> None:
    path = filedialog.asksaveasfilename(
        parent=parent,
        title=title,
        defaultextension=".csv",
        filetypes=[("Arquivo CSV", "*.csv")],
        initialfile=default_filename,
    )
    if not path:
        return
    try:
        exporter(Path(path))
        messagebox.showinfo("Exportação Concluída", f"Salvo em:\n{path}", parent=parent)
    except Exception as exc:
        messagebox.showerror("Erro ao Exportar CSV", str(exc), parent=parent)


class EntriesView(ttk.Frame):
    def __init__(self, parent, db: Database, on_change: Callable[[], None]):
        super().__init__(parent, padding=10)
        self.db = db
        self.on_change = on_change
        self.selected_id: int | None = None
        self._build()

    def _build(self) -> None:
        form = ttk.LabelFrame(self, text="Lançamento", padding=10)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Data e Hora:").grid(row=0, column=0, sticky="w", padx=4)
        self.dt_picker = DateTimePicker(form, width=16)
        self.dt_picker.grid(row=1, column=0, padx=4, pady=2)

        ttk.Label(form, text="Produto:").grid(row=0, column=1, sticky="w", padx=4)
        self.cmb_prod = AutocompleteCombobox(
            form, width=36, on_valid_select=self._on_product_selected
        )
        self.cmb_prod.grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(form, text="Quantidade:").grid(row=0, column=2, sticky="w", padx=4)
        self.var_qtd = tk.StringVar()
        self.var_qtd.trace_add("write", lambda *_: self._recalc_preview())
        ttk.Entry(form, width=12, textvariable=self.var_qtd).grid(
            row=1, column=2, padx=4, pady=2
        )

        self.var_unit = tk.StringVar(value="-")
        self.var_price = tk.StringVar(value="0.00")
        self.var_total = tk.StringVar(value="0.00")

        for col_idx, (lbl, var, w) in enumerate(
            [
                ("Medida:", self.var_unit, 10),
                ("Preço (R$):", self.var_price, 10),
                ("Total (R$):", self.var_total, 12),
            ],
            start=3,
        ):
            ttk.Label(form, text=lbl).grid(row=0, column=col_idx, sticky="w", padx=4)
            ttk.Entry(form, width=w, textvariable=var, state="readonly").grid(
                row=1, column=col_idx, padx=4, pady=2
            )

        ttk.Button(form, text="Salvar", command=self._save).grid(
            row=1, column=6, padx=(8, 2), pady=2
        )
        ttk.Button(form, text="Limpar", command=self.clear_form).grid(
            row=1, column=7, padx=2, pady=2
        )

        table_box = ttk.LabelFrame(self, text="Lançamentos", padding=6)
        table_box.pack(fill="both", expand=True)

        self.table = DataTable(
            table_box,
            [
                ("id", "ID", 50, "w"),
                ("data", "Data / Hora", 140, "w"),
                ("produto", "Produto", 280, "w"),
                ("qtd", "Qtd", 90, "e"),
                ("medida", "Medida", 90, "center"),
                ("preco", "Preço (R$)", 110, "e"),
                ("total", "Total (R$)", 110, "e"),
            ],
            on_select=self._on_row_select,
        )
        self.table.pack(fill="both", expand=True)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(bottom, text="Importar CSV", command=self.import_csv).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(bottom, text="Exportar CSV", command=self.export_csv).pack(
            side="left"
        )
        ttk.Button(bottom, text="Excluir Selecionado", command=self._delete).pack(
            side="right"
        )

    def _on_product_selected(self, prod_name: str):
        if prod_name and not self.dt_picker.get().strip():
            self.dt_picker.set(fmt_datetime_br(datetime.now()))

        prod = self.db.get_product_by_name(prod_name) if prod_name else None
        if prod:
            self.var_unit.set(UNIT_TO_LABEL[prod.unit])
            self.var_price.set(fmt_money(prod.price))
        else:
            self.var_unit.set("-")
            self.var_price.set("0.00")
        self._recalc_preview()

    def _recalc_preview(self):
        unit = LABEL_TO_UNIT.get(self.var_unit.get())
        if unit is None:
            self.var_total.set("0.00")
            return
        try:
            price = Decimal(self.var_price.get())
            qty = parse_quantity(self.var_qtd.get(), unit)
            total = (qty * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.var_total.set(fmt_money(total))
        except ValueError, InvalidOperation:
            self.var_total.set("0.00")

    def _on_row_select(self, vals: tuple):
        self.selected_id = int(vals[0])
        self.dt_picker.set(vals[1])
        self.cmb_prod.set(vals[2])
        self.var_qtd.set(vals[3])
        self.var_unit.set(vals[4])
        self.var_price.set(vals[5])
        self.var_total.set(vals[6])

    def clear_form(self):
        self.selected_id = None
        self.dt_picker.set("")
        self.cmb_prod.set("")
        self.var_qtd.set("")
        self.var_unit.set("-")
        self.var_price.set("0.00")
        self.var_total.set("0.00")
        self.table.clear_selection()

    def _save(self):
        try:
            prod_name = self.cmb_prod.get().strip()
            prod = self.db.get_product_by_name(prod_name) if prod_name else None
            if prod is None:
                raise ValueError("Selecione um produto válido cadastrado no Catálogo.")

            ts = parse_datetime_br(self.dt_picker.get())
            unit = LABEL_TO_UNIT.get(self.var_unit.get(), prod.unit)
            qty = parse_quantity(self.var_qtd.get(), unit)

            self.db.save_entry(
                timestamp=ts,
                product_id=prod.id,
                quantity=qty,
                entry_id=self.selected_id,
            )
            self.clear_form()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror("Entrada Inválida", str(exc), parent=self)

    def _delete(self):
        vals = self.table.selected_values()
        if not vals:
            return
        if messagebox.askyesno(
            "Confirmar", "Excluir lançamento selecionado?", parent=self
        ):
            self.db.delete_entry(int(vals[0]))
            self.clear_form()
            self.on_change()

    def import_csv(self) -> None:
        run_csv_import(
            self,
            "Importar Lançamentos (CSV)",
            lambda p: import_entries_csv(self.db, p),
            self.on_change,
        )

    def export_csv(self) -> None:
        run_csv_export(
            self,
            "Exportar Lançamentos (CSV)",
            "lancamentos.csv",
            lambda p: export_entries_csv(self.db, p),
        )

    def refresh(self) -> None:
        self.cmb_prod.set_completion_list([p.name for p in self.db.list_products()])
        rows = [
            (
                e.id,
                fmt_datetime_br(e.timestamp),
                e.product_name,
                fmt_quantity(e.quantity, e.unit),
                UNIT_TO_LABEL[e.unit],
                fmt_money(e.unit_price),
                fmt_money(e.total),
            )
            for e in self.db.list_entries()
        ]
        self.table.set_rows(rows)


class CatalogView(ttk.Frame):
    def __init__(self, parent, db: Database, on_change: Callable[[], None]):
        super().__init__(parent, padding=10)
        self.db = db
        self.on_change = on_change
        self.selected_prod_id: int | None = None
        self._build()

    def _build(self) -> None:
        self.tab_bar = EditableTabBar(
            self,
            on_select=self._on_catalog_switched,
            on_create=self._create_catalog,
            on_rename=self._rename_catalog,
            on_delete=self._delete_catalog,
            item_noun="Catálogo",
        )
        self.tab_bar.pack(fill="x", pady=(0, 8))

        form = ttk.LabelFrame(self, text="Cadastro de Produtos", padding=10)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Produto:").grid(row=0, column=0, sticky="w", padx=4)
        self.ent_name = ttk.Entry(form, width=42)
        self.ent_name.grid(row=1, column=0, padx=4, pady=2)

        ttk.Label(form, text="Preço (R$):").grid(row=0, column=1, sticky="w", padx=4)
        self.ent_price = ttk.Entry(form, width=14)
        self.ent_price.grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(form, text="Medida:").grid(row=0, column=2, sticky="w", padx=4)
        self.cmb_unit = ttk.Combobox(
            form, values=list(LABEL_TO_UNIT.keys()), state="readonly", width=12
        )
        self.cmb_unit.set("unidade")
        self.cmb_unit.grid(row=1, column=2, padx=4, pady=2)

        self.btn_save = ttk.Button(form, text="Salvar", command=self._save_product)
        self.btn_save.grid(row=1, column=3, padx=6)

        self.btn_clear = ttk.Button(form, text="Limpar", command=self.clear_form)
        self.btn_clear.grid(row=1, column=4, padx=2)

        table_box = ttk.LabelFrame(self, text="Produtos", padding=6)
        table_box.pack(fill="both", expand=True)

        self.table = DataTable(
            table_box,
            [
                ("id", "ID", 60, "w"),
                ("produto", "Produto", 440, "w"),
                ("preco", "Preço (R$)", 140, "e"),
                ("medida", "Medida", 120, "center"),
            ],
            on_select=self._on_row_select,
        )
        self.table.pack(fill="both", expand=True)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(bottom, text="Importar CSV", command=self.import_csv).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(bottom, text="Exportar CSV", command=self.export_csv).pack(
            side="left"
        )
        self.btn_delete = ttk.Button(
            bottom, text="Excluir Produto", command=self._delete_product
        )
        self.btn_delete.pack(side="right")

    def _set_editor_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.ent_name.config(state=state)
        self.ent_price.config(state=state)
        self.cmb_unit.config(state="readonly" if enabled else "disabled")
        self.btn_save.config(state=state)
        self.btn_clear.config(state=state)
        self.btn_delete.config(state=state)

    def _create_catalog(self, name: str) -> None:
        try:
            created = self.db.save_catalog(name)
            self.tab_bar.current_id = created.id
            self.clear_form()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror("Erro ao Criar Catálogo", str(exc), parent=self)

    def _rename_catalog(self, catalog_id: int, new_name: str) -> None:
        try:
            self.db.save_catalog(new_name, catalog_id=catalog_id)
            self.on_change()
        except ValueError as exc:
            messagebox.showerror("Erro ao Renomear", str(exc), parent=self)

    def _delete_catalog(self, catalog_id: int, catalog_name: str) -> None:
        if not messagebox.askyesno(
            "Confirmar Exclusão", f"Excluir o catálogo '{catalog_name}'?", parent=self
        ):
            return
        try:
            self.db.delete_catalog(catalog_id)
            if self.tab_bar.current_id == catalog_id:
                self.tab_bar.current_id = None
            self.clear_form()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror("Operação Bloqueada", str(exc), parent=self)

    def _on_catalog_switched(self, catalog_id: int) -> None:
        self.clear_form()
        self.refresh()

    def _load_products(self, catalog_id: int | None) -> None:
        if catalog_id is None:
            self.table.set_rows([])
            return
        products = self.db.list_products(catalog_id=catalog_id)
        self.table.set_rows(
            [
                (p.id, p.name, fmt_money(p.price), UNIT_TO_LABEL[p.unit])
                for p in products
            ]
        )

    def _on_row_select(self, vals: tuple):
        if self.tab_bar.current_id is None:
            return
        self.selected_prod_id = int(vals[0])
        self.ent_name.delete(0, tk.END)
        self.ent_name.insert(0, vals[1])
        self.ent_price.delete(0, tk.END)
        self.ent_price.insert(0, vals[2])
        self.cmb_unit.set(vals[3])

    def clear_form(self):
        self.selected_prod_id = None
        was_disabled = str(self.ent_name.cget("state")) == "disabled"
        if was_disabled:
            self.ent_name.config(state="normal")
            self.ent_price.config(state="normal")
        self.ent_name.delete(0, tk.END)
        self.ent_price.delete(0, tk.END)
        self.cmb_unit.set("unidade")
        self.table.clear_selection()
        if was_disabled:
            self.ent_name.config(state="disabled")
            self.ent_price.config(state="disabled")

    def _save_product(self):
        if self.tab_bar.current_id is None:
            return
        try:
            self.db.save_product(
                catalog_id=self.tab_bar.current_id,
                name=self.ent_name.get(),
                price=parse_money(self.ent_price.get()),
                unit=LABEL_TO_UNIT[self.cmb_unit.get()],
                product_id=self.selected_prod_id,
            )
            self.clear_form()
            self.on_change()
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Erro no Catálogo", str(exc), parent=self)

    def _delete_product(self):
        if self.tab_bar.current_id is None or self.selected_prod_id is None:
            return
        if messagebox.askyesno(
            "Confirmar", "Excluir produto selecionado?", parent=self
        ):
            try:
                self.db.delete_product(self.selected_prod_id)
                self.clear_form()
                self.on_change()
            except ValueError as exc:
                messagebox.showerror("Operação Bloqueada", str(exc), parent=self)

    def import_csv(self) -> None:
        run_csv_import(
            self,
            "Importar Catálogo (CSV)",
            lambda p: import_catalog_csv(self.db, p),
            self.on_change,
        )

    def export_csv(self) -> None:
        run_csv_export(
            self,
            "Exportar Catálogo (CSV)",
            "catalogo.csv",
            lambda p: export_catalog_csv(self.db, p),
        )

    def refresh(self) -> None:
        catalogs = self.db.list_catalogs()
        active_id = self.tab_bar.set_items([(c.id, c.name) for c in catalogs])
        has_catalog = active_id is not None
        if not has_catalog:
            self.clear_form()
        self._set_editor_enabled(has_catalog)
        self._load_products(active_id)


class ReportsView(ttk.Frame):
    def __init__(self, parent, db: Database):
        super().__init__(parent, padding=10)
        self.db = db
        self._build()

    def _build(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 8))

        ttk.Label(controls, text="Ano:").pack(side="left", padx=(0, 4))
        self.cmb_year = ttk.Combobox(controls, state="readonly", width=8)
        self.cmb_year.pack(side="left", padx=(0, 12))
        self.cmb_year.bind("<<ComboboxSelected>>", lambda _: self.refresh())

        ttk.Label(controls, text="Mês:").pack(side="left", padx=(0, 4))
        self.cmb_month = ttk.Combobox(
            controls, values=month_choices(), state="readonly", width=16
        )
        self.cmb_month.current(date.today().month - 1)
        self.cmb_month.pack(side="left", padx=(0, 12))
        self.cmb_month.bind("<<ComboboxSelected>>", lambda _: self._refresh_products())

        ttk.Button(
            controls, text="Exportar Excel (.xlsx)", command=self.export_xlsx
        ).pack(side="right")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        frame_left = ttk.LabelFrame(paned, text="Resumo Mensal", padding=6)
        frame_right = ttk.LabelFrame(
            paned, text="Produtos (Mês Selecionado)", padding=6
        )
        paned.add(frame_left, weight=1)
        paned.add(frame_right, weight=1)

        self.tbl_months = DataTable(
            frame_left,
            [
                ("mes", "Mês", 110, "w"),
                ("un", "Unidades", 90, "e"),
                ("kg", "Kg", 90, "e"),
                ("valor", "Total (R$)", 110, "e"),
            ],
            on_select=self._on_month_selected,
        )
        self.tbl_months.pack(fill="both", expand=True)

        self.tbl_products = DataTable(
            frame_right,
            [
                ("produto", "Produto", 210, "w"),
                ("medida", "Medida", 70, "center"),
                ("qtd", "Quantidade", 90, "e"),
                ("valor", "Total (R$)", 100, "e"),
            ],
        )
        self.tbl_products.pack(fill="both", expand=True)

    def _on_month_selected(self, vals: tuple):
        month_num = parse_month_choice(vals[0])
        self.cmb_month.set(month_label(month_num))
        self._refresh_products()

    def _refresh_products(self) -> None:
        year = int(self.cmb_year.get())
        month = parse_month_choice(self.cmb_month.get())
        breakdowns = self.db.get_product_breakdown(year, month)
        rows = [
            (
                b.product_name,
                UNIT_TO_LABEL[b.unit],
                fmt_quantity(b.total_quantity, b.unit),
                fmt_money(b.total_amount),
            )
            for b in breakdowns
        ]
        summary_row = (
            (
                "TOTAL",
                "-",
                "-",
                fmt_money(sum((b.total_amount for b in breakdowns), Decimal("0.00"))),
            )
            if breakdowns
            else None
        )
        self.tbl_products.set_rows(rows, summary_row=summary_row)

    def export_xlsx(self) -> None:
        from report import export_monthly_report_xlsx

        year = int(self.cmb_year.get())
        month = parse_month_choice(self.cmb_month.get())
        filepath = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".xlsx",
            filetypes=[("Planilha Excel", "*.xlsx")],
            initialfile=f"Relatorio_{year}_{month:02d}.xlsx",
        )
        if not filepath:
            return
        export_monthly_report_xlsx(self.db, year, month, Path(filepath))
        messagebox.showinfo(
            "Exportação Concluída", f"Arquivo salvo em:\n{filepath}", parent=self
        )

    def refresh(self) -> None:
        years = [str(y) for y in self.db.get_available_years()]
        cur_year = self.cmb_year.get()
        self.cmb_year["values"] = years
        if cur_year not in years:
            cur_year = years[0]
            self.cmb_year.set(cur_year)

        summary = {s.month: s for s in self.db.get_monthly_summary(int(cur_year))}
        rows = [
            (
                month_label(code),
                int(s.total_units) if s else 0,
                f"{s.total_kg:.3f}" if s else "0.000",
                fmt_money(s.total_amount) if s else "0.00",
            )
            for code in range(1, 13)
            for s in [summary.get(code)]
        ]
        self.tbl_months.set_rows(rows)
        self._refresh_products()

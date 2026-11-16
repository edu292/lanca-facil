import calendar
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from tkinter import simpledialog, ttk


class AutocompleteCombobox(ttk.Entry):
    def __init__(self, master, on_valid_select=None, **kwargs):
        self._var = tk.StringVar()
        super().__init__(master, textvariable=self._var, **kwargs)
        self._all_values: list[str] = []
        self._on_valid_select = on_valid_select
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self._internal = False
        self._selecting_from_list = False

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
            self._listbox = tk.Listbox(
                self._popup,
                exportselection=False,
                activestyle="none",
                selectbackground="#2b579a",
                selectforeground="#ffffff",
                font=("TkDefaultFont", 9),
                borderwidth=1,
                relief="solid",
            )
            self._listbox.pack(fill="both", expand=True)
            self._listbox.bind("<Enter>", lambda _: self._set_list_hover(True))
            self._listbox.bind("<Leave>", lambda _: self._set_list_hover(False))
            self._listbox.bind("<Motion>", self._on_mouse_move)
            self._listbox.bind("<ButtonPress-1>", self._on_mouse_press)
            self._listbox.bind("<FocusOut>", self._on_focus_out)

        self._listbox.delete(0, tk.END)
        for item in matches:
            self._listbox.insert(tk.END, item)
        self._listbox.selection_set(0)

        x, y = self.winfo_rootx(), self.winfo_rooty() + self.winfo_height()
        w = max(self.winfo_width(), 280)
        h = min(len(matches), 8) * 22 + 4
        self._popup.geometry(f"{w}x{h}+{x}+{y}")
        self._popup.lift()

    def _set_list_hover(self, hovering: bool) -> None:
        self._selecting_from_list = hovering

    def _on_mouse_move(self, event: tk.Event) -> None:
        if not self._listbox:
            return
        idx = self._listbox.nearest(event.y)
        if 0 <= idx < self._listbox.size():
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(idx)

    def _on_mouse_press(self, event: tk.Event):
        if not self._listbox:
            return "break"
        idx = self._listbox.nearest(event.y)
        if 0 <= idx < self._listbox.size():
            value = self._listbox.get(idx)
            self._selecting_from_list = False
            self._commit(value)
        self.focus_set()
        return "break"

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

    def _commit(self, value: str):
        self.set(value)
        self.icursor(tk.END)
        self._close()
        if self._on_valid_select:
            self._on_valid_select(value)

    def _is_focus_inside(self) -> bool:
        if self._selecting_from_list:
            return True
        focused = self.focus_get()
        return focused is not None and focused in (self, self._popup, self._listbox)

    def _on_focus_out(self, _event=None):
        if self._is_focus_inside():
            return
        self._close()
        val = self._var.get().strip().upper()
        if val in self._all_values:
            self._commit(val)
        else:
            self.set("")
            if self._on_valid_select:
                self._on_valid_select("")

    def _close(self):
        self._selecting_from_list = False
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
        self._icon = self._build_calendar_icon()
        ttk.Button(self, image=self._icon, command=self._open_calendar).pack(
            side="left", padx=(2, 0)
        )
        self._popup: tk.Toplevel | None = None

    @staticmethod
    def _build_calendar_icon() -> tk.PhotoImage:
        img = tk.PhotoImage(width=14, height=14)
        border, header, body, dot = "#444444", "#2b579a", "#ffffff", "#555555"

        img.put(border, to=(1, 2, 13, 13))
        img.put(body, to=(2, 5, 12, 12))
        img.put(header, to=(2, 3, 12, 5))
        img.put(border, to=(4, 1, 5, 3))
        img.put(border, to=(9, 1, 10, 3))
        for y in (7, 10):
            for x in (4, 7, 10):
                img.put(dot, to=(x, y, x + 1, y + 1))
        return img

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

        container = ttk.Frame(
            self._popup, relief="solid", borderwidth=1, padding=(14, 8, 14, 14)
        )
        container.pack()

        top_bar = ttk.Frame(container)
        top_bar.pack(fill="x", pady=(0, 6))
        close_btn = tk.Label(
            top_bar,
            text="×",
            fg="#555555",
            font=("TkDefaultFont", 11, "bold"),
            cursor="hand2",
            padx=6,
            pady=1,
        )
        close_btn.pack(side="right", padx=(0, 0))
        close_btn.bind("<Button-1>", lambda _: self._popup.destroy())
        close_btn.bind(
            "<Enter>", lambda _: close_btn.config(fg="#ffffff", bg="#c42b1c")
        )
        close_btn.bind(
            "<Leave>",
            lambda _: close_btn.config(
                fg="#555555",
                bg=self.cget("background")
                if hasattr(self, "background")
                else "#dcdad5",
            ),
        )
        default_bg = close_btn.cget("bg")
        close_btn.bind(
            "<Leave>", lambda _: close_btn.config(fg="#555555", bg=default_bg)
        )

        nav = ttk.Frame(container)
        nav.pack(fill="x", pady=(0, 8))
        ttk.Button(nav, text="<", width=3, command=lambda: self._shift_month(-1)).pack(
            side="left"
        )
        self._lbl_month = ttk.Label(
            nav, width=18, anchor="center", font=("TkDefaultFont", 10, "bold")
        )
        self._lbl_month.pack(side="left", expand=True)
        ttk.Button(nav, text=">", width=3, command=lambda: self._shift_month(1)).pack(
            side="right"
        )

        self._grid_frame = ttk.Frame(container)
        self._grid_frame.pack(pady=(2, 4))

        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=(8, 8))

        time_bar = ttk.Frame(container)
        time_bar.pack(fill="x")
        ttk.Label(time_bar, text="Hora:").pack(side="left")
        ttk.Spinbox(
            time_bar,
            from_=0,
            to=23,
            format="%02.0f",
            textvariable=self._hour_var,
            width=3,
        ).pack(side="left", padx=3)
        ttk.Label(time_bar, text=":").pack(side="left")
        ttk.Spinbox(
            time_bar,
            from_=0,
            to=59,
            format="%02.0f",
            textvariable=self._min_var,
            width=3,
        ).pack(side="left", padx=3)
        ttk.Button(time_bar, text="Agora", width=7, command=self._pick_now).pack(
            side="right"
        )

        self._popup.bind("<Escape>", lambda _: self._popup.destroy())

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

        month_name = calendar.month_name[self._cal_month].capitalize()
        self._lbl_month.config(text=f"{month_name} {self._cal_year}")

        for idx, day_name in enumerate(calendar.day_abbr):
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


@dataclass(frozen=True, slots=True)
class TableTheme:
    style_name: str = "App.Treeview"
    rowheight: int = 28
    font: tuple = ("TkDefaultFont", 9)
    heading_font: tuple = ("TkDefaultFont", 9, "bold")
    heading_padding: tuple[int, int] = (6, 6)
    background: str = "#ffffff"
    fieldbackground: str = "#ffffff"
    odd_background: str = "#ffffff"
    even_background: str = "#f2f5f8"
    selected_background: str = "#2b579a"
    selected_foreground: str = "#ffffff"
    summary_background: str = "#e2e8f0"
    summary_foreground: str = "#000000"
    summary_font: tuple = ("TkDefaultFont", 9, "bold")
    wrapper_padding: tuple[int, int] = (0, 4)

    def apply(self, style: ttk.Style | None = None) -> str:
        s = style or ttk.Style()
        s.configure(
            self.style_name,
            rowheight=self.rowheight,
            font=self.font,
            background=self.background,
            fieldbackground=self.fieldbackground,
        )
        s.configure(
            f"{self.style_name}.Heading",
            font=self.heading_font,
            padding=self.heading_padding,
        )
        s.map(
            self.style_name,
            background=[("selected", self.selected_background)],
            foreground=[("selected", self.selected_foreground)],
        )
        return self.style_name


DEFAULT_TABLE_THEME = TableTheme()


class DataTable(ttk.Frame):
    def __init__(
        self,
        parent,
        columns_spec: list[tuple[str, str, int, str]],
        on_select: Callable[[tuple], None] | None = None,
        theme: TableTheme = DEFAULT_TABLE_THEME,
    ):
        super().__init__(parent, padding=theme.wrapper_padding)
        self.theme = theme
        style_name = self.theme.apply()

        self.tree = ttk.Treeview(
            self,
            columns=[c[0] for c in columns_spec],
            show="headings",
            style=style_name,
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.tag_configure("odd", background=self.theme.odd_background)
        self.tree.tag_configure("even", background=self.theme.even_background)
        self.tree.tag_configure(
            "summary",
            background=self.theme.summary_background,
            foreground=self.theme.summary_foreground,
            font=self.theme.summary_font,
        )

        for col, title, width, anchor in columns_spec:
            self.tree.heading(col, text=f"  {title}  " if anchor == "w" else title)
            self.tree.column(col, width=width, anchor=anchor)

        if on_select:
            self.tree.bind(
                "<<TreeviewSelect>>", lambda _: self._dispatch_select(on_select)
            )

    def _dispatch_select(self, callback: Callable[[tuple], None]) -> None:
        vals = self.selected_values()
        if vals is not None:
            callback(vals)

    def set_rows(self, rows: list[tuple], summary_row: tuple | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for idx, r in enumerate(rows):
            tag = "even" if idx % 2 else "odd"
            self.tree.insert("", "end", values=r, tags=(tag,))
        if summary_row is not None:
            self.tree.insert("", "end", values=summary_row, tags=("summary",))

    def selected_values(self) -> tuple | None:
        sel = self.tree.selection()
        if not sel:
            return None
        if "summary" in self.tree.item(sel[0], "tags"):
            return None
        return tuple(self.tree.item(sel[0], "values"))

    def clear_selection(self) -> None:
        self.tree.selection_remove(self.tree.selection())


class _EditTabDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        noun: str,
        current_name: str,
        on_rename: Callable[[str], None],
        on_delete: Callable[[], None],
    ):
        super().__init__(parent)
        self.title(f"Editar {noun}")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())

        self._on_rename = on_rename
        self._on_delete = on_delete

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text=f"Nome do {noun.lower()}:").pack(anchor="w")
        self._var = tk.StringVar(value=current_name)
        entry = ttk.Entry(body, textvariable=self._var, width=32)
        entry.pack(fill="x", pady=(4, 12))
        entry.select_range(0, tk.END)

        actions = ttk.Frame(body)
        actions.pack(fill="x")

        ttk.Button(actions, text="Excluir", command=self._handle_delete).pack(
            side="left"
        )
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(
            side="right", padx=(4, 0)
        )
        ttk.Button(actions, text="Salvar", command=self._handle_save).pack(side="right")

        self.bind("<Return>", lambda _: self._handle_save())
        self.bind("<Escape>", lambda _: self.destroy())

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        self.wait_visibility()
        self.grab_set()
        entry.focus_set()

    def _handle_save(self) -> None:
        new_name = self._var.get().strip()
        if not new_name:
            return
        self.destroy()
        self._on_rename(new_name)

    def _handle_delete(self) -> None:
        self.destroy()
        self._on_delete()


class EditableTabBar(ttk.Frame):
    def __init__(
        self,
        parent,
        on_select: Callable[[int], None],
        on_create: Callable[[str], None],
        on_rename: Callable[[int, str], None],
        on_delete: Callable[[int, str], None],
        item_noun: str = "Item",
    ):
        super().__init__(parent)
        self._on_select = on_select
        self._on_create = on_create
        self._on_rename = on_rename
        self._on_delete = on_delete
        self._item_noun = item_noun
        self.current_id: int | None = None

        self._strip = ttk.Frame(self)
        self._strip.pack(fill="x")
        ttk.Separator(self, orient="horizontal").pack(fill="x")

    def set_items(self, items: list[tuple[int, str]]) -> int | None:
        for child in self._strip.winfo_children():
            child.destroy()

        valid_ids = {item_id for item_id, _ in items}
        if self.current_id not in valid_ids:
            self.current_id = items[0][0] if items else None

        for item_id, label in items:
            is_active = item_id == self.current_id
            bg = "#ffffff" if is_active else "#dcdad5"
            tab = tk.Frame(
                self._strip,
                bd=1,
                relief="solid" if is_active else "raised",
                bg=bg,
                padx=12,
                pady=4,
                cursor="hand2",
            )
            tab.pack(side="left", padx=(0, 2))

            lbl = tk.Label(
                tab,
                text=label,
                bg=bg,
                fg="#000000",
                font=("TkDefaultFont", 9, "bold" if is_active else "normal"),
                cursor="hand2",
            )
            lbl.pack()

            for w in (tab, lbl):
                w.bind("<Button-1>", lambda _, i=item_id: self._select(i))
                w.bind(
                    "<Double-1>",
                    lambda _, i=item_id, n=label: self._open_edit_dialog(i, n),
                )

        add_tab = tk.Frame(
            self._strip,
            bd=1,
            relief="raised",
            bg="#dcdad5",
            padx=10,
            pady=4,
            cursor="hand2",
        )
        add_tab.pack(side="left")
        add_lbl = tk.Label(
            add_tab,
            text="+",
            bg="#dcdad5",
            fg="#000000",
            font=("TkDefaultFont", 9, "bold"),
            cursor="hand2",
        )
        add_lbl.pack()
        for w in (add_tab, add_lbl):
            w.bind("<Button-1>", lambda _: self._prompt_create())

        if not items:
            ttk.Label(
                self._strip,
                text=f"Clique em '+' para criar o primeiro {self._item_noun.lower()}.",
                foreground="#555555",
            ).pack(side="left", padx=10)

        return self.current_id

    def _select(self, item_id: int) -> None:
        if item_id != self.current_id:
            self.current_id = item_id
            self._on_select(item_id)

    def _prompt_create(self) -> None:
        name = simpledialog.askstring(
            f"Novo {self._item_noun}",
            f"Nome do novo {self._item_noun.lower()}:",
            parent=self,
        )
        if name and name.strip():
            self._on_create(name)

    def _open_edit_dialog(self, item_id: int, current_name: str) -> None:
        _EditTabDialog(
            parent=self,
            noun=self._item_noun,
            current_name=current_name,
            on_rename=lambda new_name: self._on_rename(item_id, new_name),
            on_delete=lambda: self._on_delete(item_id, current_name),
        )

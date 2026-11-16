import json
import locale
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from db import Database
from views import CatalogView, EntriesView, ReportsView


def get_base_dir() -> Path:
    if "__compiled__" in globals():
        exe = os.environ.get("NUITKA_ONEFILE_BINARY") or sys.argv[0]
        return Path(exe).resolve().parent
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative_path: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    elif "__compiled__" in globals():
        base = Path(__file__).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative_path


def load_brand() -> dict[str, str]:
    brand_file = resource_path("assets/brand.json")
    return json.loads(brand_file.read_text(encoding="utf-8"))


def configure_locale() -> None:
    candidates = (
        "pt_BR.UTF-8",
        "pt_BR.utf8",
        "pt_BR",
        "Portuguese_Brazil.1252",
        "Portuguese_Brazil.utf8",
        "pt_PT.UTF-8",
        "pt_PT",
        "",
    )
    for loc in candidates:
        try:
            locale.setlocale(locale.LC_ALL, loc)
            return
        except locale.Error:
            continue


DB_FILE = get_base_dir() / "db.sqlite3"


class App(tk.Tk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        brand = load_brand()
        self.title(brand["app_title"])
        if sys.platform.startswith("win"):
            icon = resource_path("assets/icon.ico")
            self.iconbitmap(default=str(icon))
        else:
            icon = resource_path("assets/icon.png")
            self._app_icon = tk.PhotoImage(file=str(icon))
            self.iconphoto(True, self._app_icon)
        self.minsize(860, 540)
        try:
            self.state("zoomed")
        except tk.TclError:
            self.attributes("-zoomed", True)

        ttk.Style(self).theme_use("clam")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.view_entries = EntriesView(self.notebook, db, on_change=self.refresh_all)
        self.view_catalog = CatalogView(self.notebook, db, on_change=self.refresh_all)
        self.view_reports = ReportsView(self.notebook, db)

        self.notebook.add(self.view_entries, text="Lançamentos")
        self.notebook.add(self.view_catalog, text="Catálogo")
        self.notebook.add(self.view_reports, text="Relatórios")

        self.bind("<Control-i>", lambda _: self._dispatch_shortcut("import_csv"))
        self.bind("<Control-e>", lambda _: self._dispatch_shortcut("export_csv"))
        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self.refresh_all())

        self.refresh_all()

    def _dispatch_shortcut(self, method_name: str) -> None:
        active = self.nametowidget(self.notebook.select())
        action = getattr(active, method_name, None)
        if callable(action):
            action()

    def refresh_all(self) -> None:
        self.view_entries.refresh()
        self.view_catalog.refresh()
        self.view_reports.refresh()


if __name__ == "__main__":
    configure_locale()
    app = App(Database(DB_FILE))
    app.mainloop()

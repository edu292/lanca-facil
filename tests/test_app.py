import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import pytest

from app import App, get_base_dir, resource_path


@pytest.fixture
def app_factory(tk_root):
    created = []
    prev_default_root = tk._default_root

    def _make(database):
        tk._default_root = None
        app = App(database)
        app.withdraw()
        app.update()
        created.append(app)
        return app

    yield _make

    for app in created:
        if app.winfo_exists():
            app.destroy()
    tk._default_root = prev_default_root


def test_app_mounts_expected_tabs(app_factory, mock_db):
    app = app_factory(mock_db)
    tabs = [app.notebook.tab(i, "text") for i in range(app.notebook.index("end"))]
    assert tabs == ["Lançamentos", "Catálogo", "Relatórios"]


def test_keyboard_shortcuts_route_to_active_tab_only(app_factory, mock_db):
    app = app_factory(mock_db)
    app.deiconify()
    app.focus_force()
    app.update()

    with (
        patch.object(app.view_entries, "import_csv") as ent_imp,
        patch.object(app.view_entries, "export_csv") as ent_exp,
        patch.object(app.view_catalog, "import_csv") as cat_imp,
        patch.object(app.view_catalog, "export_csv") as cat_exp,
    ):
        # Active: Lançamentos
        app.notebook.select(app.view_entries)
        app.update()
        app.event_generate("<Control-i>")
        app.event_generate("<Control-e>")
        app.update()
        ent_imp.assert_called_once()
        ent_exp.assert_called_once()
        cat_imp.assert_not_called()
        cat_exp.assert_not_called()

        # Active: Catálogo
        app.notebook.select(app.view_catalog)
        app.update()
        app.event_generate("<Control-i>")
        app.event_generate("<Control-e>")
        app.update()
        cat_imp.assert_called_once()
        cat_exp.assert_called_once()

        # Active: Relatórios (no CSV actions; must not raise)
        app.notebook.select(app.view_reports)
        app.update()
        app.event_generate("<Control-i>")
        app.event_generate("<Control-e>")
        app.update()


def test_cross_view_data_synchronization_on_change_and_tab_switch(app_factory, db):
    app = app_factory(db)
    assert app.view_entries.cmb_prod._all_values == []

    # 1. Create catalog & product via CatalogView and trigger on_change
    app.notebook.select(app.view_catalog)
    app.update()
    app.view_catalog._create_catalog("PADARIA")
    app.view_catalog.ent_name.insert(0, "PÃO DE QUEIJO")
    app.view_catalog.ent_price.insert(0, "4,50")
    app.view_catalog._save_product()

    # EntriesView autocomplete list must immediately know about the new product
    assert app.view_entries.cmb_prod._all_values == ["PÃO DE QUEIJO"]

    # 2. Record an entry for a past year (2023) and switch to ReportsView
    app.notebook.select(app.view_entries)
    app.update()
    app.view_entries.dt_picker.set("10/06/2023 09:00")
    app.view_entries.cmb_prod.set("PÃO DE QUEIJO")
    app.view_entries._on_product_selected("PÃO DE QUEIJO")
    app.view_entries.var_qtd.set("2")
    app.view_entries._save()

    app.notebook.select(app.view_reports)
    app.update()
    assert "2023" in app.view_reports.cmb_year["values"]


def test_frozen_and_source_path_resolution(monkeypatch, tmp_path):
    # Normal source execution
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert get_base_dir().is_dir()
    assert resource_path("icon.ico").name == "icon.ico"

    # PyInstaller frozen bundle execution
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    fake_exe = dist_dir / "LancaFacil.exe"
    fake_meipass = tmp_path / "_MEI12345"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)

    assert get_base_dir() == tmp_path.resolve()
    assert resource_path("icon.ico") == Path(fake_meipass) / "icon.ico"

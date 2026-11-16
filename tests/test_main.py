from unittest.mock import patch

from app import App


def test_app_tabs_shortcuts_and_refresh_sync(tk_root, mock_db):
    app = App(mock_db)
    try:
        tabs = [app.notebook.tab(i, "text") for i in range(3)]
        assert tabs == ["Lançamentos", "Catálogo", "Relatórios"]

        with (
            patch.object(app.view_entries, "import_csv") as ent_imp,
            patch.object(app.view_catalog, "export_csv") as cat_exp,
            patch.object(app, "refresh_all") as refresh_spy,
        ):
            # Tab 0: EntriesView active
            app.notebook.select(app.view_entries)
            app._dispatch_shortcut("import_csv")
            ent_imp.assert_called_once()

            # Tab 1: CatalogView active
            app.notebook.select(app.view_catalog)
            app._dispatch_shortcut("export_csv")
            cat_exp.assert_called_once()

            # Tab 2: ReportsView active (no CSV methods -> must not raise)
            app.notebook.select(app.view_reports)
            app._dispatch_shortcut("import_csv")
            app._dispatch_shortcut("export_csv")

            assert refresh_spy.call_count >= 1
    finally:
        app.destroy()

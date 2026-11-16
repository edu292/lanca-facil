from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from db import Catalog, Entry, Product, ProductBreakdown, Unit
from views import CatalogView, EntriesView, ReportsView


def test_entries_view_auto_timestamp_live_preview_and_validation(tk_root, mock_db):
    prod_unit = Product(1, 1, "BOLO", Decimal("12.50"), Unit.UNIT)
    mock_db.get_product_by_name.side_effect = lambda name: (
        prod_unit if name == "BOLO" else None
    )

    on_change = MagicMock()
    view = EntriesView(tk_root, mock_db, on_change=on_change)

    # Selecting product populates timestamp (when empty), unit, and price
    view._on_product_selected("BOLO")
    assert view.dt_picker.get() != ""
    assert view.var_unit.get() == "unidade"
    assert view.var_price.get() == "12.50"

    # Existing timestamp is preserved on subsequent product change
    view.dt_picker.set("01/01/2026 10:00")
    view._on_product_selected("BOLO")
    assert view.dt_picker.get() == "01/01/2026 10:00"

    # Live preview updates on valid quantity and resets to 0.00 on fractional unit
    view.var_qtd.set("3")
    assert view.var_total.get() == "37.50"
    view.var_qtd.set("3.5")
    assert view.var_total.get() == "0.00"

    # Invalid save triggers error dialog without calling db.save_entry
    with patch("views.messagebox.showerror") as err_box:
        view._save()
        err_box.assert_called_once()
        mock_db.save_entry.assert_not_called()

    # Valid save delegates to db, clears form, and fires on_change
    view.cmb_prod.set("BOLO")
    view.var_qtd.set("2")
    view._save()
    mock_db.save_entry.assert_called_once_with(
        timestamp=datetime(2026, 1, 1, 10, 0),
        product_id=1,
        quantity=Decimal(2),
        entry_id=None,
    )
    assert view.var_qtd.get() == ""
    on_change.assert_called_once()


def test_entries_view_row_selection_and_delete_confirmation(tk_root, mock_db):
    mock_db.list_entries.return_value = [
        Entry(
            7,
            datetime(2026, 2, 10, 14, 0),
            1,
            "CAFÉ",
            Decimal(2),
            Unit.UNIT,
            Decimal("5.00"),
            Decimal("10.00"),
        )
    ]
    view = EntriesView(tk_root, mock_db, on_change=MagicMock())
    view.refresh()

    row_id = view.table.tree.get_children()[0]
    view.table.tree.selection_set(row_id)
    view.table._dispatch_select(view._on_row_select)
    assert view.selected_id == 7
    assert view.cmb_prod.get() == "CAFÉ"

    with patch("views.messagebox.askyesno", return_value=True):
        view._delete()
    mock_db.delete_entry.assert_called_once_with(7)
    assert view.selected_id is None


def test_catalog_view_empty_state_lock_and_clear_form(tk_root, mock_db):
    view = CatalogView(tk_root, mock_db, on_change=MagicMock())
    view.refresh()

    # No catalogs -> inputs locked
    assert str(view.ent_name.cget("state")) == "disabled"
    assert str(view.btn_save.cget("state")) == "disabled"

    # clear_form safely resets even while disabled
    view.clear_form()
    assert str(view.ent_name.cget("state")) == "disabled"

    # Adding a catalog enables editor
    mock_db.list_catalogs.return_value = [Catalog(1, "GERAL")]
    view.refresh()
    assert str(view.ent_name.cget("state")) == "normal"

    # Backend ValueError surfaces via messagebox
    mock_db.save_catalog.side_effect = ValueError("Duplicado")
    with patch("views.messagebox.showerror") as err_box:
        view._create_catalog("GERAL")
        err_box.assert_called_once()


def test_reports_view_sync_and_xlsx_export(tk_root, mock_db, tmp_path):
    mock_db.get_product_breakdown.return_value = [
        ProductBreakdown(1, "PÃO", Unit.KG, Decimal("2.000"), Decimal("20.00"))
    ]
    view = ReportsView(tk_root, mock_db)
    view.refresh()

    # Selecting a month row updates combobox and refreshes product summary row
    march_row = view.tbl_months.tree.get_children()[2]
    view.tbl_months.tree.selection_set(march_row)
    view.tbl_months._dispatch_select(view._on_month_selected)
    assert view.cmb_month.get().startswith("03 -")

    prod_rows = view.tbl_products.tree.get_children()
    assert "summary" in view.tbl_products.tree.item(prod_rows[-1], "tags")

    # Export flow
    out_file = tmp_path / "out.xlsx"
    with (
        patch("views.filedialog.asksaveasfilename", return_value=str(out_file)),
        patch("report.export_monthly_report_xlsx") as export_fn,
        patch("views.messagebox.showinfo") as info_box,
    ):
        view.export_xlsx()
        export_fn.assert_called_once_with(mock_db, 2026, 3, out_file)
        info_box.assert_called_once()

from unittest.mock import MagicMock, patch

from widgets import AutocompleteCombobox, DataTable, DateTimePicker, EditableTabBar


def test_autocomplete_combobox_filtering_navigation_and_focus_out(tk_root):
    selected = []
    cb = AutocompleteCombobox(tk_root, on_valid_select=selected.append)
    cb.pack()
    cb.set_completion_list(["SUCO DE LARANJA", "SUCO DE UVA", "CAFÉ"])
    tk_root.update_idletasks()

    # Substring filtering
    cb.focus_set()
    cb.set("uva")
    cb._on_text_changed()
    assert cb._popup is not None and cb._listbox.size() == 1
    assert cb._listbox.get(0) == "SUCO DE UVA"

    # Keyboard accept commits value and closes popup
    cb._accept()
    assert cb.get() == "SUCO DE UVA"
    assert cb._popup is None
    assert selected[-1] == "SUCO DE UVA"

    # Focus out with invalid text clears input and notifies callback
    cb.set("INEXISTENTE")
    with patch.object(cb, "focus_get", return_value=tk_root):
        cb._on_focus_out()
    assert cb.get() == ""
    assert selected[-1] == ""


def test_datetime_picker_month_rollover_and_selection(tk_root):
    picker = DateTimePicker(tk_root)
    picker.set("15/01/2026 08:45")
    picker._open_calendar()
    try:
        # Roll backward from Jan 2026 -> Dec 2025
        picker._shift_month(-1)
        assert (picker._cal_year, picker._cal_month) == (2025, 12)

        # Roll forward from Dec 2025 -> Jan 2026
        picker._shift_month(1)
        assert (picker._cal_year, picker._cal_month) == (2026, 1)

        # Clamp out-of-range hour/minute spinbox inputs
        picker._hour_var.set("99")
        picker._min_var.set("-5")
        picker._select_day(20)
        assert picker.get() == "20/01/2026 23:00"
    finally:
        if picker._popup and picker._popup.winfo_exists():
            picker._popup.destroy()


def test_datatable_summary_row_cannot_be_selected(tk_root):
    on_select = MagicMock()
    tbl = DataTable(
        tk_root,
        [("id", "ID", 50, "w"), ("val", "Val", 50, "e")],
        on_select=on_select,
    )
    tbl.set_rows([(1, "10.00"), (2, "20.00")], summary_row=("TOTAL", "30.00"))

    children = tbl.tree.get_children()
    assert tbl.tree.item(children[0], "tags") == ("odd",)
    assert tbl.tree.item(children[1], "tags") == ("even",)
    assert tbl.tree.item(children[2], "tags") == ("summary",)

    # Selecting summary row must return None and suppress callback
    tbl.tree.selection_set(children[2])
    tbl._dispatch_select(on_select)
    assert tbl.selected_values() is None
    on_select.assert_not_called()

    # Selecting data row returns values and fires callback
    tbl.tree.selection_set(children[0])
    tbl._dispatch_select(on_select)
    on_select.assert_called_once_with(("1", "10.00"))


def test_editable_tab_bar_selection_and_creation(tk_root):
    on_select = MagicMock()
    on_create = MagicMock()
    bar = EditableTabBar(
        tk_root,
        on_select=on_select,
        on_create=on_create,
        on_rename=MagicMock(),
        on_delete=MagicMock(),
    )
    active = bar.set_items([(1, "CAT A"), (2, "CAT B")])
    assert active == 1

    bar._select(2)
    assert bar.current_id == 2
    on_select.assert_called_once_with(2)

    with patch("widgets.simpledialog.askstring", return_value="CAT C"):
        bar._prompt_create()
    on_create.assert_called_once_with("CAT C")

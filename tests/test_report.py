from datetime import datetime
from decimal import Decimal

import openpyxl

from db import Unit
from report import export_monthly_report_xlsx


def test_export_monthly_report_xlsx_with_data(db, tmp_path):
    cat = db.save_catalog("GERAL")
    p_unit = db.save_product(cat.id, "CANETA", Decimal("2.50"), Unit.UNIT)
    p_kg = db.save_product(cat.id, "ARROZ", Decimal("6.00"), Unit.KG)

    db.save_entry(datetime(2026, 4, 2, 10, 0), p_unit.id, Decimal(4))  # 10.00
    db.save_entry(datetime(2026, 4, 3, 10, 0), p_kg.id, Decimal("2.5"))  # 15.00

    out = tmp_path / "report.xlsx"
    export_monthly_report_xlsx(db, 2026, 4, out)

    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Resumo_2026", "Produtos_2026_04"]

    ws_summary = wb["Resumo_2026"]
    assert ws_summary.max_row == 13  # Header + 12 months
    april_row = [cell.value for cell in ws_summary[5]]
    assert april_row[1:] == [4, 2.5, 25.0]
    jan_row = [cell.value for cell in ws_summary[2]]
    assert jan_row[1:] == [0, 0, 0]

    ws_products = wb["Produtos_2026_04"]
    assert ws_products.max_row == 4  # Header + 2 products + TOTAL
    total_row = [cell.value for cell in ws_products[4]]
    assert total_row == ["TOTAL", "-", "-", 25.0]
    assert ws_products[4][0].font.bold is True


def test_export_monthly_report_xlsx_empty_month_omits_total(db, tmp_path):
    out = tmp_path / "empty.xlsx"
    export_monthly_report_xlsx(db, 2026, 8, out)

    wb = openpyxl.load_workbook(out)
    ws_products = wb["Produtos_2026_08"]
    assert ws_products.max_row == 1  # Only header row, no TOTAL row

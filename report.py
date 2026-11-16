from decimal import Decimal
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from db import Database, Unit
from formatting import UNIT_TO_LABEL, month_label


def export_monthly_report_xlsx(db: Database, year: int, month: int, path: Path) -> None:
    wb = openpyxl.Workbook()

    ws_summary = wb.active
    ws_summary.title = f"Resumo_{year}"
    ws_summary.append(["Mês", "Total Unidades", "Total Kg", "Total Valor (R$)"])

    summary = {s.month: s for s in db.get_monthly_summary(year)}
    for code in range(1, 13):
        s = summary.get(code)
        ws_summary.append(
            [
                month_label(code),
                int(s.total_units) if s else 0,
                round(float(s.total_kg), 3) if s else 0.0,
                round(float(s.total_amount), 2) if s else 0.0,
            ]
        )

    ws_products = wb.create_sheet(title=f"Produtos_{year}_{month:02d}")
    ws_products.append(["Produto", "Medida", "Quantidade Total", "Valor Total (R$)"])
    breakdowns = db.get_product_breakdown(year, month)
    for b in breakdowns:
        qty = (
            int(b.total_quantity)
            if b.unit is Unit.UNIT
            else round(float(b.total_quantity), 3)
        )
        ws_products.append(
            [
                b.product_name,
                UNIT_TO_LABEL[b.unit],
                qty,
                round(float(b.total_amount), 2),
            ]
        )

    if breakdowns:
        total_amount = sum((b.total_amount for b in breakdowns), Decimal("0.00"))
        ws_products.append(["TOTAL", "-", "-", round(float(total_amount), 2)])
        for cell in ws_products[ws_products.max_row]:
            cell.font = Font(bold=True)

    wb.save(path)

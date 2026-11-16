from decimal import Decimal
from pathlib import Path

import xlsxwriter

from db import Database, Unit
from formatting import UNIT_TO_LABEL, month_label


def export_monthly_report_xlsx(db: Database, year: int, month: int, path: Path) -> None:
    with xlsxwriter.Workbook(str(path)) as wb:
        bold = wb.add_format({"bold": True})

        ws_summary = wb.add_worksheet(f"Resumo_{year}")
        ws_summary.write_row(
            0, 0, ["Mês", "Total Unidades", "Total Kg", "Total Valor (R$)"]
        )

        summary = {s.month: s for s in db.get_monthly_summary(year)}
        for row_idx, code in enumerate(range(1, 13), start=1):
            s = summary.get(code)
            ws_summary.write_row(
                row_idx,
                0,
                [
                    month_label(code),
                    int(s.total_units) if s else 0,
                    round(float(s.total_kg), 3) if s else 0.0,
                    round(float(s.total_amount), 2) if s else 0.0,
                ],
            )

        ws_products = wb.add_worksheet(f"Produtos_{year}_{month:02d}")
        ws_products.write_row(
            0, 0, ["Produto", "Medida", "Quantidade Total", "Valor Total (R$)"]
        )

        breakdowns = db.get_product_breakdown(year, month)
        for row_idx, b in enumerate(breakdowns, start=1):
            qty = (
                int(b.total_quantity)
                if b.unit is Unit.UNIT
                else round(float(b.total_quantity), 3)
            )
            ws_products.write_row(
                row_idx,
                0,
                [
                    b.product_name,
                    UNIT_TO_LABEL[b.unit],
                    qty,
                    round(float(b.total_amount), 2),
                ],
            )

        if breakdowns:
            total_amount = sum((b.total_amount for b in breakdowns), Decimal("0.00"))
            ws_products.write_row(
                len(breakdowns) + 1,
                0,
                ["TOTAL", "-", "-", round(float(total_amount), 2)],
                bold,
            )

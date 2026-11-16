import csv
from dataclasses import fields
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from db import CatalogItem, Database, EntryRecord, ImportStats, Unit
from formatting import fmt_money, parse_decimal


def _headers_for(dataclass_type: type[Any]) -> list[str]:
    return [f.name for f in fields(dataclass_type)]


def _serialize_value(val: Any) -> str:
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M")
    if isinstance(val, Decimal):
        return fmt_money(val) if val == val.quantize(Decimal("0.01")) else str(val)
    return str(val)


def export_catalog_csv(db: Database, path: Path) -> None:
    headers = _headers_for(CatalogItem)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for item in db.list_catalog_items():
            writer.writerow([_serialize_value(getattr(item, h)) for h in headers])


def import_catalog_csv(db: Database, path: Path) -> ImportStats:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        items = [
            CatalogItem(
                catalog=row["catalog"],
                product=row["product"],
                price=parse_decimal(row["price"], "Preço"),
                unit=Unit(row["unit"].strip().lower()),
            )
            for row in csv.DictReader(f)
        ]
    return db.import_catalog_items(items)


def export_entries_csv(db: Database, path: Path) -> None:
    headers = _headers_for(EntryRecord)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for rec in db.list_entry_records():
            writer.writerow([_serialize_value(getattr(rec, h)) for h in headers])


def import_entries_csv(db: Database, path: Path) -> ImportStats:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        records: list[EntryRecord] = []
        for row in csv.DictReader(f):
            qty = parse_decimal(row["quantity"], "Quantidade")
            unit_price = parse_decimal(row["unit_price"], "Preço")
            total = (
                parse_decimal(row["total"], "Total")
                if row.get("total", "").strip()
                else (qty * unit_price).quantize(Decimal("0.01"))
            )
            records.append(
                EntryRecord(
                    timestamp=datetime.strptime(
                        row["timestamp"].strip(), "%Y-%m-%d %H:%M"
                    ),
                    catalog=row.get("catalog") or "GENERAL",
                    product=row["product"],
                    quantity=qty,
                    unit=Unit(row["unit"].strip().lower()),
                    unit_price=unit_price,
                    total=total,
                )
            )
    return db.import_entry_records(records)

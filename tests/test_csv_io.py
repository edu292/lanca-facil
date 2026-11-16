from datetime import datetime
from decimal import Decimal

import pytest

from csv_io import (
    export_catalog_csv,
    export_entries_csv,
    import_catalog_csv,
    import_entries_csv,
)
from db import Database, Unit


def test_catalog_csv_roundtrip_with_bom(db, tmp_path):
    cat = db.save_catalog("AÇOUGUE")
    db.save_product(cat.id, "PICANHA", Decimal("79.90"), Unit.KG)

    csv_path = tmp_path / "catalog.csv"
    export_catalog_csv(db, csv_path)

    # Rewrite with UTF-8 BOM and mixed-case unit to verify resilient parsing
    raw_text = csv_path.read_text(encoding="utf-8").replace(",kg", ", KG ")
    csv_path.write_text(raw_text, encoding="utf-8-sig")

    target_db = Database(":memory:")
    stats = import_catalog_csv(target_db, csv_path)
    assert stats.inserted == 1
    imported = target_db.get_product_by_name("PICANHA")
    assert imported.price == Decimal("79.90")
    assert imported.unit is Unit.KG
    target_db.conn.close()


def test_entries_csv_roundtrip_and_optional_total_fallback(db, tmp_path):
    cat = db.save_catalog("PADARIA")
    prod = db.save_product(cat.id, "BOLO", Decimal("15.00"), Unit.UNIT)
    db.save_entry(datetime(2026, 7, 4, 16, 20), prod.id, Decimal(2))

    csv_path = tmp_path / "entries.csv"
    export_entries_csv(db, csv_path)

    # Blank out 'total' and 'catalog' to test fallback calculation and 'GENERAL' default
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    header = lines[0]
    row_parts = lines[1].split(",")
    row_parts[1] = ""  # catalog -> GENERAL
    row_parts[6] = ""  # total -> computed from qty * unit_price
    csv_path.write_text("\n".join([header, ",".join(row_parts)]), encoding="utf-8")

    target_db = Database(":memory:")
    stats = import_entries_csv(target_db, csv_path)
    assert stats.inserted == 1

    entries = target_db.list_entries()
    assert len(entries) == 1
    assert entries[0].total == Decimal("30.00")
    assert target_db.list_catalogs()[0].name == "GENERAL"
    target_db.conn.close()


def test_malformed_csv_raises(db, tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("wrong,headers\n1,2\n", encoding="utf-8")
    with pytest.raises(KeyError):
        import_catalog_csv(db, bad_csv)

from datetime import date, datetime
from decimal import Decimal

import pytest

from db import CatalogItem, EntryRecord, Unit


def test_catalog_normalization_uniqueness_and_restrict(db):
    cat = db.save_catalog("  bebidas ")
    assert cat.name == "BEBIDAS"

    with pytest.raises(ValueError):
        db.save_catalog("BEBIDAS")

    with pytest.raises(ValueError):
        db.save_catalog("OUTRO", catalog_id=9999)

    db.save_product(cat.id, "Suco", Decimal("5.00"), Unit.UNIT)
    with pytest.raises(ValueError):
        db.delete_catalog(cat.id)


def test_product_constraints_and_restrict(db):
    c1 = db.save_catalog("PADARIA")
    c2 = db.save_catalog("CONFEITARIA")
    prod = db.save_product(c1.id, " pão francês ", Decimal("14.90"), Unit.KG)
    assert prod.name == "PÃO FRANCÊS"
    assert prod.price == Decimal("14.90")

    # Global uniqueness across different catalogs
    with pytest.raises(ValueError):
        db.save_product(c2.id, "PÃO FRANCÊS", Decimal("15.00"), Unit.KG)

    db.save_entry(datetime(2026, 5, 1, 10, 0), prod.id, Decimal("0.5"))
    with pytest.raises(ValueError):
        db.delete_product(prod.id)


def test_entry_generated_total_and_historical_price_immutability(db):
    cat = db.save_catalog("GERAL")
    prod = db.save_product(cat.id, "CAFÉ", Decimal("10.00"), Unit.UNIT)

    entry = db.save_entry(datetime(2026, 5, 10, 8, 0), prod.id, Decimal(3))
    assert entry.total == Decimal("30.00")

    # Update catalog product price and unit
    db.save_product(cat.id, "CAFÉ", Decimal("25.00"), Unit.KG, product_id=prod.id)

    # Editing quantity on existing entry for same product preserves historical price/unit
    edited = db.save_entry(
        datetime(2026, 5, 10, 9, 0), prod.id, Decimal(4), entry_id=entry.id
    )
    assert edited.unit is Unit.UNIT
    assert edited.unit_price == Decimal("10.00")
    assert edited.total == Decimal("40.00")

    # Swapping to a different product adopts the new product's price and unit
    prod2 = db.save_product(cat.id, "QUEIJO", Decimal("40.00"), Unit.KG)
    swapped = db.save_entry(
        datetime(2026, 5, 10, 9, 0), prod2.id, Decimal("0.25"), entry_id=entry.id
    )
    assert swapped.unit is Unit.KG
    assert swapped.unit_price == Decimal("40.00")
    assert swapped.total == Decimal("10.00")


def test_entry_unit_fractional_blocked_and_ordering(db):
    cat = db.save_catalog("GERAL")
    prod = db.save_product(cat.id, "GARRAFA", Decimal("5.00"), Unit.UNIT)

    with pytest.raises(ValueError):
        db.save_entry(datetime(2026, 1, 1, 10, 0), prod.id, Decimal("1.5"))

    e1 = db.save_entry(datetime(2026, 1, 1, 10, 0), prod.id, Decimal(1))
    e2 = db.save_entry(datetime(2026, 1, 1, 10, 0), prod.id, Decimal(2))
    e3 = db.save_entry(datetime(2026, 1, 2, 10, 0), prod.id, Decimal(1))

    entries = db.list_entries(limit=2)
    assert [e.id for e in entries] == [e3.id, e2.id]
    assert e1.id not in [e.id for e in entries]


def test_import_catalog_and_entries_stats_and_dedup(db):
    cat_stats = db.import_catalog_items(
        [
            CatalogItem("Lanches", "Coxinha", Decimal("6.50"), Unit.UNIT),
            CatalogItem("Salgados", "coxinha", Decimal("7.00"), Unit.UNIT),  # update
            CatalogItem("", "Invalido", Decimal("5.00"), Unit.UNIT),  # skip
            CatalogItem("Lanches", "Zero", Decimal("0.00"), Unit.UNIT),  # skip
        ]
    )
    assert (cat_stats.inserted, cat_stats.updated, cat_stats.skipped) == (1, 1, 2)
    prod = db.get_product_by_name("COXINHA")
    assert prod.price == Decimal("7.00")

    ts = datetime(2026, 6, 1, 12, 0)
    rec = EntryRecord(
        ts,
        "Lanches",
        "COXINHA",
        Decimal(2),
        Unit.UNIT,
        Decimal("7.00"),
        Decimal("14.00"),
    )
    new_prod_rec = EntryRecord(
        ts, "Bebidas", "ÁGUA", Decimal(1), Unit.UNIT, Decimal("3.00"), Decimal("3.00")
    )
    bad_unit_rec = EntryRecord(
        ts,
        "Bebidas",
        "ÁGUA",
        Decimal("1.5"),
        Unit.UNIT,
        Decimal("3.00"),
        Decimal("4.50"),
    )

    ent_stats = db.import_entry_records([rec, rec, new_prod_rec, bad_unit_rec])
    assert (ent_stats.inserted, ent_stats.updated, ent_stats.skipped) == (2, 0, 2)
    assert db.get_product_by_name("ÁGUA") is not None


def test_reporting_queries(db):
    cat = db.save_catalog("GERAL")
    p_unit = db.save_product(cat.id, "ITEM A", Decimal("10.00"), Unit.UNIT)
    p_kg = db.save_product(cat.id, "ITEM B", Decimal("20.00"), Unit.KG)

    db.save_entry(datetime(2024, 3, 10, 10, 0), p_unit.id, Decimal(2))  # 20.00
    db.save_entry(datetime(2024, 3, 15, 10, 0), p_kg.id, Decimal("1.5"))  # 30.00
    db.save_entry(datetime(2024, 3, 20, 10, 0), p_unit.id, Decimal(1))  # 10.00

    years = db.get_available_years()
    assert years[0] == date.today().year
    assert 2024 in years

    monthly = db.get_monthly_summary(2024)
    assert len(monthly) == 1
    assert monthly[0].month == 3
    assert monthly[0].total_units == Decimal(3)
    assert monthly[0].total_kg == Decimal("1.5")
    assert monthly[0].total_amount == Decimal("60.00")

    breakdown = db.get_product_breakdown(2024, 3)
    assert [b.product_name for b in breakdown] == ["ITEM A", "ITEM B"]
    assert breakdown[0].total_amount == Decimal("30.00")
    assert breakdown[1].total_amount == Decimal("30.00")

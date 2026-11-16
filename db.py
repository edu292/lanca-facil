import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path


class Unit(StrEnum):
    UNIT = "unit"
    KG = "kg"


def _to_cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _from_cents(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)


@dataclass(frozen=True, slots=True)
class Catalog:
    id: int
    name: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Catalog:
        return cls(id=row["id"], name=row["name"])


@dataclass(frozen=True, slots=True)
class Product:
    id: int
    catalog_id: int
    name: str
    price: Decimal
    unit: Unit

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Product:
        return cls(
            id=row["id"],
            catalog_id=row["catalog_id"],
            name=row["name"],
            price=_from_cents(row["price_cents"]),
            unit=Unit(row["unit"]),
        )


@dataclass(frozen=True, slots=True)
class Entry:
    id: int
    timestamp: datetime
    product_id: int
    product_name: str
    quantity: Decimal
    unit: Unit
    unit_price: Decimal
    total: Decimal

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Entry:
        return cls(
            id=row["id"],
            timestamp=datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M"),
            product_id=row["product_id"],
            product_name=row["product_name"],
            quantity=Decimal(str(row["quantity"])),
            unit=Unit(row["unit"]),
            unit_price=_from_cents(row["unit_price_cents"]),
            total=_from_cents(row["total_cents"]),
        )


@dataclass(frozen=True, slots=True)
class CatalogItem:
    catalog: str
    product: str
    price: Decimal
    unit: Unit

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> CatalogItem:
        return cls(
            catalog=row["catalog"],
            product=row["product"],
            price=_from_cents(row["price_cents"]),
            unit=Unit(row["unit"]),
        )


@dataclass(frozen=True, slots=True)
class EntryRecord:
    timestamp: datetime
    catalog: str
    product: str
    quantity: Decimal
    unit: Unit
    unit_price: Decimal
    total: Decimal

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> EntryRecord:
        return cls(
            timestamp=datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M"),
            catalog=row["catalog"],
            product=row["product"],
            quantity=Decimal(str(row["quantity"])),
            unit=Unit(row["unit"]),
            unit_price=_from_cents(row["unit_price_cents"]),
            total=_from_cents(row["total_cents"]),
        )


@dataclass(frozen=True, slots=True)
class ImportStats:
    inserted: int
    updated: int
    skipped: int


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    month: int
    total_units: Decimal
    total_kg: Decimal
    total_amount: Decimal

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> MonthlySummary:
        return cls(
            month=int(row["month"]),
            total_units=Decimal(str(row["total_units"])),
            total_kg=Decimal(str(row["total_kg"])),
            total_amount=_from_cents(row["total_cents"]),
        )


@dataclass(frozen=True, slots=True)
class ProductBreakdown:
    product_id: int
    product_name: str
    unit: Unit
    total_quantity: Decimal
    total_amount: Decimal

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ProductBreakdown:
        return cls(
            product_id=row["product_id"],
            product_name=row["product_name"],
            unit=Unit(row["unit"]),
            total_quantity=Decimal(str(row["total_quantity"])),
            total_amount=_from_cents(row["total_cents"]),
        )


class Database:
    def __init__(self, path: Path | str = "app.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS catalogs (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE CHECK(length(trim(name)) > 0)
                ) STRICT;

                CREATE TABLE IF NOT EXISTS products (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    catalog_id  INTEGER NOT NULL REFERENCES catalogs(id) ON DELETE RESTRICT,
                    name        TEXT NOT NULL UNIQUE CHECK(length(trim(name)) > 0),
                    price_cents INTEGER NOT NULL CHECK(price_cents > 0),
                    unit        TEXT NOT NULL CHECK(unit IN ('unit', 'kg'))
                ) STRICT;

                CREATE TABLE IF NOT EXISTS entries (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp        TEXT NOT NULL CHECK(timestamp GLOB '????-??-?? ??:??'),
                    product_id       INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                    quantity         REAL NOT NULL CHECK(quantity > 0),
                    unit             TEXT NOT NULL CHECK(unit IN ('unit', 'kg')),
                    unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents > 0),
                    total_cents      INTEGER GENERATED ALWAYS AS (
                                         CAST(ROUND(quantity * unit_price_cents) AS INTEGER)
                                     ) STORED,
                    CHECK(unit = 'kg' OR quantity = floor(quantity))
                ) STRICT;
            """)

    def _ensure_catalog_id(self, name: str) -> int:
        normalized = name.strip().upper()
        if not normalized:
            raise ValueError("O nome do catálogo é obrigatório.")
        self.conn.execute(
            "INSERT OR IGNORE INTO catalogs (name) VALUES (?)", (normalized,)
        )
        row = self.conn.execute(
            "SELECT id FROM catalogs WHERE name = ?", (normalized,)
        ).fetchone()
        return int(row["id"])

    def list_catalogs(self) -> list[Catalog]:
        rows = self.conn.execute(
            "SELECT id, name FROM catalogs ORDER BY name ASC"
        ).fetchall()
        return [Catalog.from_row(r) for r in rows]

    def save_catalog(self, name: str, catalog_id: int | None = None) -> Catalog:
        normalized = name.strip().upper()
        if not normalized:
            raise ValueError("O nome do catálogo é obrigatório.")
        try:
            with self.conn:
                if catalog_id is None:
                    row = self.conn.execute(
                        "INSERT INTO catalogs (name) VALUES (?) RETURNING id, name",
                        (normalized,),
                    ).fetchone()
                else:
                    row = self.conn.execute(
                        "UPDATE catalogs SET name = ? WHERE id = ? RETURNING id, name",
                        (normalized, catalog_id),
                    ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"O catálogo '{normalized}' já existe.") from exc

        if row is None:
            raise ValueError(f"Catálogo (ID {catalog_id}) não encontrado.")
        return Catalog.from_row(row)

    def delete_catalog(self, catalog_id: int) -> None:
        try:
            with self.conn:
                self.conn.execute("DELETE FROM catalogs WHERE id = ?", (catalog_id,))
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "Não é possível excluir o catálogo: ainda existem produtos vinculados a ele."
            ) from exc

    def list_products(self, catalog_id: int | None = None) -> list[Product]:
        if catalog_id is None:
            rows = self.conn.execute(
                "SELECT id, catalog_id, name, price_cents, unit FROM products ORDER BY name ASC"
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT id, catalog_id, name, price_cents, unit
                   FROM products WHERE catalog_id = ? ORDER BY name ASC""",
                (catalog_id,),
            ).fetchall()
        return [Product.from_row(r) for r in rows]

    def get_product_by_name(self, name: str) -> Product | None:
        row = self.conn.execute(
            "SELECT id, catalog_id, name, price_cents, unit FROM products WHERE name = ?",
            (name.strip().upper(),),
        ).fetchone()
        return Product.from_row(row) if row else None

    def save_product(
        self,
        catalog_id: int,
        name: str,
        price: Decimal,
        unit: Unit,
        product_id: int | None = None,
    ) -> Product:
        normalized = name.strip().upper()
        if not normalized:
            raise ValueError("O nome do produto é obrigatório.")
        if price <= 0:
            raise ValueError("O preço deve ser maior que zero.")

        price_cents = _to_cents(price)
        try:
            with self.conn:
                if product_id is None:
                    row = self.conn.execute(
                        """INSERT INTO products (catalog_id, name, price_cents, unit)
                           VALUES (?, ?, ?, ?)
                           RETURNING id, catalog_id, name, price_cents, unit""",
                        (catalog_id, normalized, price_cents, unit),
                    ).fetchone()
                else:
                    row = self.conn.execute(
                        """UPDATE products
                           SET catalog_id = ?, name = ?, price_cents = ?, unit = ?
                           WHERE id = ?
                           RETURNING id, catalog_id, name, price_cents, unit""",
                        (catalog_id, normalized, price_cents, unit, product_id),
                    ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"O produto '{normalized}' já existe ou o catálogo informado não existe."
            ) from exc

        if row is None:
            raise ValueError(f"Produto (ID {product_id}) não encontrado.")
        return Product.from_row(row)

    def delete_product(self, product_id: int) -> None:
        try:
            with self.conn:
                self.conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "Não é possível excluir o produto: existem lançamentos vinculados a ele."
            ) from exc

    def get_entry_row(self, entry_id: int) -> sqlite3.Row:
        row = self.conn.execute(
            """SELECT e.id, e.timestamp, e.product_id, p.name AS product_name,
                      e.quantity, e.unit, e.unit_price_cents, e.total_cents
               FROM entries e
               JOIN products p ON p.id = e.product_id
               WHERE e.id = ?""",
            (entry_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Lançamento (ID {entry_id}) não encontrado.")
        return row

    def save_entry(
        self,
        timestamp: datetime,
        product_id: int,
        quantity: Decimal,
        entry_id: int | None = None,
    ) -> Entry:
        if quantity <= 0:
            raise ValueError("A quantidade deve ser maior que zero.")

        prod_row = self.conn.execute(
            "SELECT id, price_cents, unit FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if prod_row is None:
            raise ValueError(f"Produto (ID {product_id}) não encontrado.")

        unit = Unit(prod_row["unit"])
        price_cents: int = prod_row["price_cents"]

        if entry_id is not None:
            existing = self.conn.execute(
                "SELECT product_id, unit, unit_price_cents FROM entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"Produto (ID {product_id}) não encontrado.")
            if existing["product_id"] == product_id:
                unit = Unit(existing["unit"])
                price_cents = existing["unit_price_cents"]

        if unit is Unit.UNIT and quantity != int(quantity):
            raise ValueError(
                "Quantidade de produtos medidos em unidades deve ver um valor inteiro."
            )

        iso_dt = timestamp.strftime("%Y-%m-%d %H:%M")
        qty_float = float(quantity)

        with self.conn:
            if entry_id is None:
                cur = self.conn.execute(
                    """INSERT INTO entries
                       (timestamp, product_id, quantity, unit, unit_price_cents)
                       VALUES (?, ?, ?, ?, ?)""",
                    (iso_dt, product_id, qty_float, unit, price_cents),
                )
                saved_id = cur.lastrowid
            else:
                self.conn.execute(
                    """UPDATE entries
                       SET timestamp = ?, product_id = ?, quantity = ?,
                           unit = ?, unit_price_cents = ?
                       WHERE id = ?""",
                    (iso_dt, product_id, qty_float, unit, price_cents, entry_id),
                )
                saved_id = entry_id

        assert saved_id is not None
        return Entry.from_row(self.get_entry_row(saved_id))

    def list_entries(self, limit: int = 300) -> list[Entry]:
        rows = self.conn.execute(
            """SELECT e.id, e.timestamp, e.product_id, p.name AS product_name,
                      e.quantity, e.unit, e.unit_price_cents, e.total_cents
               FROM entries e
               JOIN products p ON p.id = e.product_id
               ORDER BY e.timestamp DESC, e.id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [Entry.from_row(r) for r in rows]

    def delete_entry(self, entry_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    def list_catalog_items(self) -> list[CatalogItem]:
        rows = self.conn.execute("""
            SELECT c.name AS catalog, p.name AS product, p.price_cents, p.unit
            FROM products p
            JOIN catalogs c ON c.id = p.catalog_id
            ORDER BY c.name ASC, p.name ASC
        """).fetchall()
        return [CatalogItem.from_row(r) for r in rows]

    def import_catalog_items(self, items: list[CatalogItem]) -> ImportStats:
        inserted = updated = skipped = 0
        with self.conn:
            for item in items:
                cat_name = item.catalog.strip().upper()
                prod_name = item.product.strip().upper()
                if not cat_name or not prod_name or item.price <= 0:
                    skipped += 1
                    continue

                cat_id = self._ensure_catalog_id(cat_name)
                price_cents = _to_cents(item.price)
                existing = self.conn.execute(
                    "SELECT id FROM products WHERE name = ?", (prod_name,)
                ).fetchone()

                if existing is None:
                    self.conn.execute(
                        """INSERT INTO products (catalog_id, name, price_cents, unit)
                           VALUES (?, ?, ?, ?)""",
                        (cat_id, prod_name, price_cents, item.unit),
                    )
                    inserted += 1
                else:
                    self.conn.execute(
                        """UPDATE products
                           SET catalog_id = ?, price_cents = ?, unit = ?
                           WHERE id = ?""",
                        (cat_id, price_cents, item.unit, existing["id"]),
                    )
                    updated += 1

        return ImportStats(inserted=inserted, updated=updated, skipped=skipped)

    def list_entry_records(self) -> list[EntryRecord]:
        rows = self.conn.execute("""
            SELECT e.timestamp,
                   c.name AS catalog,
                   p.name AS product,
                   e.quantity,
                   e.unit,
                   e.unit_price_cents,
                   e.total_cents
            FROM entries e
            JOIN products p ON p.id = e.product_id
            JOIN catalogs c ON c.id = p.catalog_id
            ORDER BY e.timestamp ASC, e.id ASC
        """).fetchall()
        return [EntryRecord.from_row(r) for r in rows]

    def import_entry_records(self, records: list[EntryRecord]) -> ImportStats:
        inserted = skipped = 0
        with self.conn:
            for rec in records:
                prod_name = rec.product.strip().upper()
                cat_name = (rec.catalog or "GENERAL").strip().upper()
                if not prod_name or rec.quantity <= 0 or rec.unit_price <= 0:
                    skipped += 1
                    continue

                if rec.unit is Unit.UNIT and rec.quantity != int(rec.quantity):
                    skipped += 1
                    continue

                iso_dt = rec.timestamp.strftime("%Y-%m-%d %H:%M")
                qty_float = float(rec.quantity)
                price_cents = _to_cents(rec.unit_price)

                prod_row = self.conn.execute(
                    "SELECT id FROM products WHERE name = ?", (prod_name,)
                ).fetchone()

                if prod_row is None:
                    cat_id = self._ensure_catalog_id(cat_name)
                    cur = self.conn.execute(
                        """INSERT INTO products (catalog_id, name, price_cents, unit)
                           VALUES (?, ?, ?, ?)""",
                        (cat_id, prod_name, price_cents, rec.unit),
                    )
                    prod_id = int(cur.lastrowid)
                else:
                    prod_id = int(prod_row["id"])

                duplicate = self.conn.execute(
                    """SELECT 1 FROM entries
                       WHERE timestamp = ? AND product_id = ?
                         AND quantity = ? AND unit_price_cents = ?""",
                    (iso_dt, prod_id, qty_float, price_cents),
                ).fetchone()
                if duplicate:
                    skipped += 1
                    continue

                self.conn.execute(
                    """INSERT INTO entries
                       (timestamp, product_id, quantity, unit, unit_price_cents)
                       VALUES (?, ?, ?, ?, ?)""",
                    (iso_dt, prod_id, qty_float, rec.unit, price_cents),
                )
                inserted += 1

        return ImportStats(inserted=inserted, updated=0, skipped=skipped)

    def get_available_years(self) -> list[int]:
        rows = self.conn.execute(
            "SELECT DISTINCT CAST(substr(timestamp, 1, 4) AS INTEGER) AS year FROM entries ORDER BY year DESC"
        ).fetchall()
        years = [r["year"] for r in rows]
        current_year = date.today().year
        if current_year not in years:
            years.insert(0, current_year)
        return years

    def get_monthly_summary(self, year: int) -> list[MonthlySummary]:
        rows = self.conn.execute(
            """SELECT substr(timestamp, 6, 2) AS month,
                      COALESCE(SUM(CASE WHEN unit = 'unit' THEN quantity ELSE 0 END), 0) AS total_units,
                      COALESCE(SUM(CASE WHEN unit = 'kg' THEN quantity ELSE 0 END), 0) AS total_kg,
                      COALESCE(SUM(total_cents), 0) AS total_cents
               FROM entries
               WHERE substr(timestamp, 1, 4) = ?
               GROUP BY month
               ORDER BY month ASC""",
            (f"{year:04d}",),
        ).fetchall()
        return [MonthlySummary.from_row(r) for r in rows]

    def get_product_breakdown(self, year: int, month: int) -> list[ProductBreakdown]:
        rows = self.conn.execute(
            """SELECT e.product_id,
                      p.name AS product_name,
                      e.unit,
                      SUM(e.quantity) AS total_quantity,
                      SUM(e.total_cents) AS total_cents
               FROM entries e
               JOIN products p ON p.id = e.product_id
               WHERE substr(e.timestamp, 1, 7) = ?
               GROUP BY e.product_id, p.name, e.unit
               ORDER BY total_cents DESC""",
            (f"{year:04d}-{month:02d}",),
        ).fetchall()
        return [ProductBreakdown.from_row(r) for r in rows]

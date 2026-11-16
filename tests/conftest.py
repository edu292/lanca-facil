import tkinter as tk
from unittest.mock import MagicMock

import pytest

from db import Database


@pytest.fixture
def db() -> Database:
    database = Database(":memory:")
    yield database
    database.conn.close()


@pytest.fixture
def mock_db() -> MagicMock:
    m = MagicMock(spec=Database)
    m.list_products.return_value = []
    m.list_entries.return_value = []
    m.list_catalogs.return_value = []
    m.get_available_years.return_value = [2026]
    m.get_monthly_summary.return_value = []
    m.get_product_breakdown.return_value = []
    return m


@pytest.fixture(scope="session")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()

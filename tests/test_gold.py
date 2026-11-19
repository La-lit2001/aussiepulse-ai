"""Check the year-ago CPI comparison."""

import hashlib
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from aussiepulse.warehouse.build_gold import (
    SilverMonth,
    change_from_previous,
    compare_months,
    build_gold,
    latest_comparison,
)
from aussiepulse.warehouse.build_silver import build_silver
from aussiepulse.warehouse.load_bronze import load_csv

DECEMBER = Path(__file__).parent / "fixtures" / "cpi_two_decembers.csv"


def test_december_2025_is_3_66_points_above_december_2024():
    difference, percent = change_from_previous(Decimal("100.97"), Decimal("97.31"))
    assert difference == Decimal("3.6600")
    assert percent == Decimal("3.7612")


def test_a_month_without_last_year_has_no_change():
    months = [
        SilverMonth(1, "2024-12", date(2024, 12, 1), Decimal("97.31"), "Australia", "All groups CPI", "Monthly")
    ]
    change = compare_months(months)[0]
    assert change.percent_change is None
    assert change.previous_time_period is None


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set, so the gold build is not run.")
    try:
        with psycopg.connect(url) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as error:
        pytest.skip(f"PostgreSQL is not reachable: {error}")
    return url


def test_gold_stores_the_december_comparison_and_can_be_rebuilt(database_url, tmp_path):
    payload = DECEMBER.read_bytes()
    copy = tmp_path / "cpi.csv"
    copy.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    load_csv(database_url, copy)
    build_silver(database_url, digest)

    first = build_gold(database_url, digest)
    second = build_gold(database_url, digest)
    assert first == {"months_stored": 2, "comparisons": 1}
    assert second == first

    latest = latest_comparison(database_url, digest)
    assert latest is not None
    assert latest.time_period == "2025-12"
    assert latest.previous_time_period == "2024-12"
    assert latest.index_change == Decimal("3.6600")
    assert latest.percent_change == Decimal("3.7612")

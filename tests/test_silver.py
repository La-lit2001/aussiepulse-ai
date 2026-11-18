"""Check that silver keeps one number per month and records bad rows."""

import hashlib
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from aussiepulse.warehouse.build_silver import BronzeFields, build_silver, check_one, classify_rows
from aussiepulse.warehouse.load_bronze import load_csv

FIXTURE = Path(__file__).parent / "fixtures" / "cpi_two_months.csv"


def _fields(row_id: int, period: str, price: str | None) -> BronzeFields:
    return BronzeFields(
        bronze_row_id=row_id,
        time_period=period,
        obs_value=price,
        region="Australia",
        index_name="All groups CPI",
        frequency="Monthly",
    )


def test_a_text_price_becomes_a_number_on_the_first_of_the_month():
    result = check_one(_fields(1, "2024-12", "97.31"))
    assert result.index_value == Decimal("97.31")
    assert result.month_start == date(2024, 12, 1)


def test_a_blank_price_is_rejected():
    result = check_one(_fields(2, "2024-03", None))
    assert result.reason == "missing_price"


def test_a_repeated_month_is_kept_once():
    accepted, rejected = classify_rows(
        [
            _fields(1, "2024-12", "97.31"),
            _fields(2, "2024-12", "97.31"),
        ]
    )
    assert len(accepted) == 1
    assert rejected[0].reason == "duplicate_month"


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set, so the silver build is not run.")
    try:
        with psycopg.connect(url) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as error:
        pytest.skip(f"PostgreSQL is not reachable: {error}")
    return url


def test_silver_keeps_two_months_and_can_be_rebuilt(database_url, tmp_path):
    copy = tmp_path / "cpi.csv"
    payload = FIXTURE.read_bytes()
    copy.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    load_csv(database_url, copy)

    first = build_silver(database_url, digest)
    second = build_silver(database_url, digest)
    assert first == {"months_kept": 2, "rows_rejected": 0}
    assert second == {"months_kept": 2, "rows_rejected": 0}

    with psycopg.connect(database_url) as connection:
        stored = connection.execute(
            """
            SELECT month.index_value
            FROM silver.cpi_month AS month
            JOIN bronze.cpi_file AS file ON file.file_id = month.file_id
            WHERE month.time_period = '2024-12' AND file.sha256 = %s
            """,
            (digest,),
        ).fetchone()
    assert stored[0] == Decimal("97.31")

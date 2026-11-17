"""Load a tiny CPI file into PostgreSQL, then load it again."""

import os
from pathlib import Path

import psycopg
import pytest

from aussiepulse.warehouse.load_bronze import load_csv, read_bronze_rows

FIXTURE = Path(__file__).parent / "fixtures" / "cpi_two_months.csv"


def test_reader_keeps_the_original_line_and_the_text_value():
    rows = read_bronze_rows(FIXTURE.read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert rows[0].time_period == "2024-12"
    assert rows[0].obs_value == "97.31"
    assert "97.31" in rows[0].raw_line


def test_blank_value_is_kept_as_an_empty_cell():
    data_line = FIXTURE.read_text(encoding="utf-8").splitlines()[2]
    blank_line = data_line.replace("2024-04", "2024-03").replace(",96.4,", ",,")
    text = FIXTURE.read_text(encoding="utf-8").splitlines()[0] + "\n" + blank_line + "\n"
    rows = read_bronze_rows(text)
    assert rows[0].time_period == "2024-03"
    assert rows[0].obs_value is None


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set, so the database load is not run.")
    try:
        with psycopg.connect(url) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as error:
        pytest.skip(f"PostgreSQL is not reachable: {error}")
    return url


def test_loading_the_same_file_twice_does_not_duplicate_rows(database_url, tmp_path):
    copy = tmp_path / "cpi.csv"
    copy.write_bytes(FIXTURE.read_bytes())
    first = load_csv(database_url, copy)
    second = load_csv(database_url, copy)
    assert first["rows_stored"] == 2
    assert second["file_inserted"] == 0
    assert second["rows_stored"] == 2

    digest_sql = "SELECT obs_value FROM bronze.cpi_row WHERE time_period = '2024-12'"
    with psycopg.connect(database_url) as connection:
        stored = connection.execute(digest_sql).fetchall()
    assert stored[0][0] == "97.31"

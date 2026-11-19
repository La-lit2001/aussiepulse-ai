"""Compare each checked month with the same month one year earlier.

Silver says what the index was. Gold says how much it moved.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import psycopg

from aussiepulse.warehouse.load_bronze import read_dotenv

LOGGER = logging.getLogger("aussiepulse.warehouse.build_gold")

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "sql" / "gold" / "001_cpi_gold.sql"
FOUR_PLACES = Decimal("0.0001")


@dataclass(frozen=True)
class SilverMonth:
    """One checked month, ready to compare."""

    silver_month_id: int
    time_period: str
    month_start: date
    index_value: Decimal
    region: str
    index_name: str
    frequency: str


@dataclass(frozen=True)
class AnnualChange:
    """One month, plus the comparison when last year's month exists."""

    silver_month_id: int
    time_period: str
    month_start: date
    region: str
    index_name: str
    frequency: str
    index_value: Decimal
    previous_time_period: str | None
    previous_index_value: Decimal | None
    index_change: Decimal | None
    percent_change: Decimal | None


def one_year_earlier(month_start: date) -> date:
    """1 December 2025 becomes 1 December 2024."""

    return month_start.replace(year=month_start.year - 1)


def change_from_previous(current: Decimal, previous: Decimal) -> tuple[Decimal, Decimal]:
    """Return the point change and the percent change, both to 4 decimal places."""

    if previous == 0:
        raise ValueError("Cannot calculate a percent change from a previous value of zero.")
    difference = current - previous
    percent = (difference / previous) * Decimal("100")
    return difference.quantize(FOUR_PLACES), percent.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def compare_months(months: list[SilverMonth]) -> list[AnnualChange]:
    """Match each month with the same region and index one year earlier."""

    lookup = {
        (month.month_start, month.region, month.index_name, month.frequency): month
        for month in months
    }
    changes: list[AnnualChange] = []
    for month in months:
        previous = lookup.get(
            (one_year_earlier(month.month_start), month.region, month.index_name, month.frequency)
        )
        difference = None
        percent = None
        if previous is not None:
            difference, percent = change_from_previous(month.index_value, previous.index_value)
        changes.append(
            AnnualChange(
                silver_month_id=month.silver_month_id,
                time_period=month.time_period,
                month_start=month.month_start,
                region=month.region,
                index_name=month.index_name,
                frequency=month.frequency,
                index_value=month.index_value,
                previous_time_period=None if previous is None else previous.time_period,
                previous_index_value=None if previous is None else previous.index_value,
                index_change=difference,
                percent_change=percent,
            )
        )
    return changes


def build_gold(database_url: str, sha256: str | None = None) -> dict[str, int]:
    """Rebuild the gold table from the silver months of one file."""

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema_sql)
            if sha256 is None:
                cursor.execute(
                    """
                    SELECT file_id
                    FROM bronze.cpi_file
                    ORDER BY ingested_at DESC, file_id DESC
                    LIMIT 1
                    """
                )
            else:
                cursor.execute(
                    "SELECT file_id FROM bronze.cpi_file WHERE sha256 = %s",
                    (sha256,),
                )
            found = cursor.fetchone()
            if found is None:
                raise ValueError("No bronze CPI file is loaded.")
            file_id = found[0]

            cursor.execute(
                """
                SELECT month_id, time_period, month_start, index_value, region, index_name, frequency
                FROM silver.cpi_month
                WHERE file_id = %s
                ORDER BY month_start
                """,
                (file_id,),
            )
            source = cursor.fetchall()
            if not source:
                raise ValueError("No silver months are built for this file. Run build_silver first.")
            months = [
                SilverMonth(
                    silver_month_id=record[0],
                    time_period=record[1],
                    month_start=record[2],
                    index_value=record[3],
                    region=record[4],
                    index_name=record[5],
                    frequency=record[6],
                )
                for record in source
            ]
            changes = compare_months(months)
            cursor.execute("DELETE FROM gold.cpi_annual_change WHERE file_id = %s", (file_id,))
            cursor.executemany(
                """
                INSERT INTO gold.cpi_annual_change (
                    file_id, silver_month_id, time_period, month_start, region, index_name,
                    frequency, index_value, previous_time_period, previous_index_value,
                    index_change, percent_change
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        file_id,
                        row.silver_month_id,
                        row.time_period,
                        row.month_start,
                        row.region,
                        row.index_name,
                        row.frequency,
                        row.index_value,
                        row.previous_time_period,
                        row.previous_index_value,
                        row.index_change,
                        row.percent_change,
                    )
                    for row in changes
                ],
            )
        connection.commit()

    comparisons = sum(1 for row in changes if row.percent_change is not None)
    LOGGER.info("Gold stored %s months, with %s year-ago comparisons.", len(changes), comparisons)
    return {"months_stored": len(changes), "comparisons": comparisons}


def latest_comparison(database_url: str, sha256: str | None = None) -> AnnualChange | None:
    """Return the newest month that has a year-ago comparison."""

    query = """
        SELECT
            change.silver_month_id,
            change.time_period,
            change.month_start,
            change.index_value,
            change.region,
            change.index_name,
            change.frequency,
            change.previous_time_period,
            change.previous_index_value,
            change.index_change,
            change.percent_change
        FROM gold.cpi_annual_change AS change
        JOIN bronze.cpi_file AS file ON file.file_id = change.file_id
        WHERE change.percent_change IS NOT NULL
    """
    parameters: tuple[str, ...] = ()
    if sha256 is not None:
        query += " AND file.sha256 = %s"
        parameters = (sha256,)
    query += " ORDER BY change.month_start DESC LIMIT 1"
    with psycopg.connect(database_url) as connection:
        record = connection.execute(query, parameters).fetchone()
    if record is None:
        return None
    return AnnualChange(
        silver_month_id=record[0],
        time_period=record[1],
        month_start=record[2],
        index_value=record[3],
        region=record[4],
        index_name=record[5],
        frequency=record[6],
        previous_time_period=record[7],
        previous_index_value=record[8],
        index_change=record[9],
        percent_change=record[10],
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    read_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL. Copy .env.example to .env and start the database.")
    result = build_gold(database_url)
    print(f"months_stored={result['months_stored']}")
    print(f"comparisons={result['comparisons']}")
    latest = latest_comparison(database_url)
    if latest is None:
        print("latest=none")
        return
    print(
        f"latest={latest.time_period} index={latest.index_value} "
        f"previous={latest.previous_time_period} previous_index={latest.previous_index_value} "
        f"change={latest.index_change} percent_change={latest.percent_change}"
    )


if __name__ == "__main__":
    main()

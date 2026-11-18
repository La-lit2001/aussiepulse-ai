"""Turn bronze text rows into one checked price per month.

Bronze keeps the original words. Silver keeps only rows that pass the
checks, and it stores the price as a number.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

from aussiepulse.warehouse.load_bronze import read_dotenv

LOGGER = logging.getLogger("aussiepulse.warehouse.build_silver")

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "sql" / "silver" / "001_cpi_silver.sql"
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class BronzeFields:
    """The text fields we read from one bronze row."""

    bronze_row_id: int
    time_period: str | None
    obs_value: str | None
    region: str | None
    index_name: str | None
    frequency: str | None


@dataclass(frozen=True)
class AcceptedMonth:
    bronze_row_id: int
    time_period: str
    month_start: date
    index_value: Decimal
    region: str
    index_name: str
    frequency: str


@dataclass(frozen=True)
class RejectedMonth:
    bronze_row_id: int
    reason: str


def check_one(row: BronzeFields) -> AcceptedMonth | RejectedMonth:
    """Decide whether one bronze row is safe to treat as a price."""

    period = (row.time_period or "").strip()
    if not period:
        return RejectedMonth(row.bronze_row_id, "missing_month")
    if MONTH_PATTERN.fullmatch(period) is None:
        return RejectedMonth(row.bronze_row_id, "bad_month")

    raw_price = (row.obs_value or "").strip()
    if not raw_price:
        return RejectedMonth(row.bronze_row_id, "missing_price")
    try:
        price = Decimal(raw_price)
    except InvalidOperation:
        return RejectedMonth(row.bronze_row_id, "bad_price")

    region = (row.region or "").strip()
    index_name = (row.index_name or "").strip()
    frequency = (row.frequency or "").strip()
    if not region or not index_name or not frequency:
        return RejectedMonth(row.bronze_row_id, "missing_label")

    year, month = period.split("-")
    return AcceptedMonth(
        bronze_row_id=row.bronze_row_id,
        time_period=period,
        month_start=date(int(year), int(month), 1),
        index_value=price,
        region=region,
        index_name=index_name,
        frequency=frequency,
    )


def classify_rows(rows: list[BronzeFields]) -> tuple[list[AcceptedMonth], list[RejectedMonth]]:
    """Check every row. A repeated month is kept once and the extra copy is rejected."""

    accepted: list[AcceptedMonth] = []
    rejected: list[RejectedMonth] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        result = check_one(row)
        if isinstance(result, RejectedMonth):
            rejected.append(result)
            continue
        key = (result.time_period, result.region, result.index_name, result.frequency)
        if key in seen:
            rejected.append(RejectedMonth(row.bronze_row_id, "duplicate_month"))
            continue
        seen.add(key)
        accepted.append(result)
    return accepted, rejected


def build_silver(database_url: str, sha256: str | None = None) -> dict[str, int]:
    """Rebuild the silver tables from one bronze file."""

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema_sql)
            if sha256 is None:
                cursor.execute(
                    """
                    SELECT file_id, sha256
                    FROM bronze.cpi_file
                    ORDER BY ingested_at DESC, file_id DESC
                    LIMIT 1
                    """
                )
            else:
                cursor.execute(
                    "SELECT file_id, sha256 FROM bronze.cpi_file WHERE sha256 = %s",
                    (sha256,),
                )
            found = cursor.fetchone()
            if found is None:
                raise ValueError("No bronze CPI file is loaded. Load the CSV before building silver.")
            file_id = found[0]

            cursor.execute(
                """
                SELECT row_id, time_period, obs_value, region, index_name, frequency
                FROM bronze.cpi_row
                WHERE file_id = %s
                ORDER BY source_row_number
                """,
                (file_id,),
            )
            source_rows = [
                BronzeFields(
                    bronze_row_id=record[0],
                    time_period=record[1],
                    obs_value=record[2],
                    region=record[3],
                    index_name=record[4],
                    frequency=record[5],
                )
                for record in cursor.fetchall()
            ]
            accepted, rejected = classify_rows(source_rows)

            cursor.execute("DELETE FROM silver.cpi_rejection WHERE file_id = %s", (file_id,))
            cursor.execute("DELETE FROM silver.cpi_month WHERE file_id = %s", (file_id,))
            cursor.executemany(
                """
                INSERT INTO silver.cpi_month (
                    file_id, bronze_row_id, time_period, month_start,
                    index_value, region, index_name, frequency
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        file_id,
                        row.bronze_row_id,
                        row.time_period,
                        row.month_start,
                        row.index_value,
                        row.region,
                        row.index_name,
                        row.frequency,
                    )
                    for row in accepted
                ],
            )
            cursor.executemany(
                """
                INSERT INTO silver.cpi_rejection (file_id, bronze_row_id, reason)
                VALUES (%s, %s, %s)
                """,
                [(file_id, row.bronze_row_id, row.reason) for row in rejected],
            )
        connection.commit()

    LOGGER.info("Silver kept %s months and rejected %s rows.", len(accepted), len(rejected))
    return {"months_kept": len(accepted), "rows_rejected": len(rejected)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    read_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL. Copy .env.example to .env and start the database.")
    result = build_silver(database_url)
    print(f"months_kept={result['months_kept']}")
    print(f"rows_rejected={result['rows_rejected']}")


if __name__ == "__main__":
    main()

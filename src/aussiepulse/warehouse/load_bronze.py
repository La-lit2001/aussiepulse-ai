"""Copy the raw CPI file into PostgreSQL.

The CSV on disk stays the source. The database gets a copy of each
line, plus the file's checksum, so we can reload the same file without
storing it twice.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import psycopg

LOGGER = logging.getLogger("aussiepulse.warehouse.load_bronze")

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "sql" / "bronze" / "001_cpi_bronze.sql"
DEFAULT_CSV = ROOT / "data" / "bronze" / "cpi" / "cpi_australia_all_groups_monthly.csv"
DEFAULT_MANIFEST = DEFAULT_CSV.with_name("manifest.json")


@dataclass(frozen=True)
class BronzeRow:
    """One line from the CSV, kept as text."""

    source_row_number: int
    raw_line: str
    time_period: str | None
    obs_value: str | None
    region: str | None
    index_name: str | None
    frequency: str | None


def read_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines into the process if they are not already set."""

    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def read_bronze_rows(text: str) -> list[BronzeRow]:
    """Turn the CSV text into rows without changing the original lines."""

    lines = text.splitlines()
    if not lines:
        raise ValueError("CPI file is empty.")
    header = next(csv.reader([lines[0]]))
    required = {"TIME_PERIOD", "OBS_VALUE", "Region", "Index", "Frequency"}
    missing = required.difference(header)
    if missing:
        raise ValueError(f"CPI file is missing columns: {sorted(missing)}")

    rows: list[BronzeRow] = []
    for source_row_number, raw_line in enumerate(lines[1:], start=2):
        if not raw_line.strip():
            continue
        values = next(csv.reader([raw_line]))
        padded = values + [""] * (len(header) - len(values))
        record = dict(zip(header, padded))

        def cell(name: str) -> str | None:
            value = (record.get(name) or "").strip()
            return value or None

        rows.append(
            BronzeRow(
                source_row_number=source_row_number,
                raw_line=raw_line,
                time_period=cell("TIME_PERIOD"),
                obs_value=cell("OBS_VALUE"),
                region=cell("Region"),
                index_name=cell("Index"),
                frequency=cell("Frequency"),
            )
        )
    if not rows:
        raise ValueError("CPI file has a header but no data rows.")
    return rows


def load_csv(database_url: str, csv_path: Path, manifest_path: Path | None = None) -> dict[str, int]:
    """Create the bronze tables if needed, then insert this file once."""

    payload = csv_path.read_bytes()
    text = payload.decode("utf-8")
    rows = read_bronze_rows(text)
    digest = hashlib.sha256(payload).hexdigest()
    manifest = _read_manifest(manifest_path, digest, len(payload))
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema_sql)
            cursor.execute(
                """
                INSERT INTO bronze.cpi_file (
                    source_name, series_id, source_url, sha256, downloaded_at, byte_count
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (sha256) DO NOTHING
                RETURNING file_id
                """,
                (
                    manifest["source_name"],
                    manifest["series_id"],
                    manifest["source_url"],
                    digest,
                    manifest["downloaded_at"],
                    int(manifest["bytes"]),
                ),
            )
            inserted_file = cursor.fetchone()
            cursor.execute(
                "SELECT file_id FROM bronze.cpi_file WHERE sha256 = %s",
                (digest,),
            )
            file_id = cursor.fetchone()[0]
            cursor.executemany(
                """
                INSERT INTO bronze.cpi_row (
                    file_id, source_row_number, raw_line,
                    time_period, obs_value, region, index_name, frequency
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (file_id, source_row_number) DO NOTHING
                """,
                [
                    (
                        file_id,
                        row.source_row_number,
                        row.raw_line,
                        row.time_period,
                        row.obs_value,
                        row.region,
                        row.index_name,
                        row.frequency,
                    )
                    for row in rows
                ],
            )
            inserted_rows = cursor.rowcount
            cursor.execute(
                "SELECT count(*) FROM bronze.cpi_row WHERE file_id = %s",
                (file_id,),
            )
            stored_rows = cursor.fetchone()[0]
        connection.commit()

    LOGGER.info("Stored file %s with %s rows.", digest[:12], stored_rows)
    return {
        "file_inserted": 1 if inserted_file else 0,
        "rows_received": len(rows),
        "rows_inserted": inserted_rows if inserted_rows and inserted_rows > 0 else 0,
        "rows_stored": stored_rows,
    }


def _read_manifest(path: Path | None, digest: str, byte_count: int) -> dict[str, str]:
    if path is not None and path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["bytes"] = str(byte_count)
        if manifest.get("sha256") and manifest["sha256"] != digest:
            raise ValueError("manifest checksum does not match the CSV file.")
        return manifest
    from datetime import datetime, timezone

    return {
        "source_name": "Australian Bureau of Statistics",
        "series_id": "ABS,CPI,2.0.0/1.10001.10.50.M",
        "source_url": "https://data.api.abs.gov.au/rest/data/ABS,CPI,2.0.0/1.10001.10.50.M",
        "sha256": digest,
        "downloaded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "bytes": str(byte_count),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    read_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL. Copy .env.example to .env and start the database.")
    if not DEFAULT_CSV.exists():
        raise SystemExit("Missing bronze CSV. Run src/aussiepulse/ingest/cpi.py first.")
    result = load_csv(database_url, DEFAULT_CSV, DEFAULT_MANIFEST)
    print(f"file_inserted={result['file_inserted']}")
    print(f"rows_received={result['rows_received']}")
    print(f"rows_stored={result['rows_stored']}")


if __name__ == "__main__":
    main()

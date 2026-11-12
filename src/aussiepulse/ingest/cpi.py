"""Download one ABS Consumer Price Index series.

Bronze means we keep the file exactly as the ABS sent it. We do not
change numbers in this step. A small manifest sits beside the file so
we can say when we downloaded it and how to fetch the same series again.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger("aussiepulse.ingest.cpi")

# All groups CPI, Australia, original, monthly.
# Checked on 11 November 2026: this URL returned HTTP 200.
CPI_SERIES_URL = (
    "https://data.api.abs.gov.au/rest/data/ABS,CPI,2.0.0/"
    "1.10001.10.50.M?startPeriod=2020-01&format=csvfilewithlabels"
)
SOURCE_NAME = "Australian Bureau of Statistics"
SERIES_ID = "ABS,CPI,2.0.0/1.10001.10.50.M"


@dataclass(frozen=True)
class Observation:
    """One month of the price index."""

    time_period: str
    value: float
    region: str
    index_name: str
    frequency: str


def parse_cpi_csv(text: str) -> list[Observation]:
    """Read the ABS CSV and keep rows that have a month and a number.

    The file has two names for some fields, such as TIME_PERIOD and
    "Time Period". We use the code columns. They are the ones that were
    filled in when this series was downloaded.
    """

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CPI file has no header row.")

    required = {"TIME_PERIOD", "OBS_VALUE", "Region", "Index", "Frequency"}
    missing = required.difference(reader.fieldnames)
    if missing:
        raise ValueError(f"CPI file is missing columns: {sorted(missing)}")

    observations: list[Observation] = []
    for line_number, row in enumerate(reader, start=2):
        period = (row.get("TIME_PERIOD") or "").strip()
        raw_value = (row.get("OBS_VALUE") or "").strip()
        if not period or not raw_value:
            LOGGER.warning("Skipping row %s because period or value is empty.", line_number)
            continue
        try:
            value = float(raw_value)
        except ValueError as error:
            raise ValueError(f"Row {line_number} has a value that is not a number: {raw_value}") from error
        observations.append(
            Observation(
                time_period=period,
                value=value,
                region=(row.get("Region") or "").strip(),
                index_name=(row.get("Index") or "").strip(),
                frequency=(row.get("Frequency") or "").strip(),
            )
        )

    if not observations:
        raise ValueError("CPI file has a header but no data rows.")
    return observations


def download_bytes(url: str, attempts: int = 3, timeout_seconds: int = 30) -> bytes:
    """Download a URL. Try again after a short wait if the network fails.

    This is the same idea as knocking on a door three times before you
    decide nobody is home.
    """

    request = urllib.request.Request(url, headers={"User-Agent": "aussiepulse-ai/0.1"})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            LOGGER.info("Download attempt %s of %s.", attempt, attempts)
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read()
            if not payload:
                raise ValueError("ABS returned an empty file.")
            return payload
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            last_error = error
            LOGGER.warning("Download attempt %s failed: %s", attempt, error)
            if attempt < attempts:
                time.sleep(attempt)
    raise RuntimeError(f"Could not download CPI data from the ABS: {last_error}") from last_error


def save_bronze(destination: Path, payload: bytes, source_url: str) -> dict[str, str]:
    """Write the raw file and a manifest. The CSV bytes are not edited."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    manifest = {
        "source_name": SOURCE_NAME,
        "series_id": SERIES_ID,
        "source_url": source_url,
        "downloaded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sha256": digest,
        "bytes": str(len(payload)),
        "licence_note": "Based on Australian Bureau of Statistics data. ABS website material is used under Creative Commons Attribution 4.0.",
    }
    manifest_path = destination.with_name("manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Saved %s bytes to %s.", len(payload), destination)
    return manifest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(__file__).resolve().parents[3]
    destination = root / "data" / "bronze" / "cpi" / "cpi_australia_all_groups_monthly.csv"
    payload = download_bytes(CPI_SERIES_URL)
    text = payload.decode("utf-8")
    observations = parse_cpi_csv(text)
    ordered = sorted(observations, key=lambda item: item.time_period)
    manifest = save_bronze(destination, payload, CPI_SERIES_URL)
    print(f"rows={len(ordered)}")
    print(f"earliest={ordered[0].time_period}:{ordered[0].value}")
    print(f"latest={ordered[-1].time_period}:{ordered[-1].value}")
    print(f"sha256={manifest['sha256']}")
    print(f"file={destination}")


if __name__ == "__main__":
    main()

"""Checks for the CPI reader. These do not call the ABS website."""

from pathlib import Path

import pytest

from aussiepulse.ingest.cpi import parse_cpi_csv

FIXTURE = Path(__file__).parent / "fixtures" / "cpi_two_months.csv"


def test_two_real_looking_rows_keep_month_and_value():
    observations = parse_cpi_csv(FIXTURE.read_text(encoding="utf-8"))
    assert len(observations) == 2
    assert observations[0].time_period == "2024-12"
    assert observations[0].value == 97.31
    assert observations[0].region == "Australia"
    assert observations[1].time_period == "2024-04"
    assert observations[1].value == 96.4


def test_header_without_rows_is_an_error():
    header = FIXTURE.read_text(encoding="utf-8").splitlines()[0]
    with pytest.raises(ValueError, match="no data rows"):
        parse_cpi_csv(header + "\n")


def test_missing_column_is_an_error():
    with pytest.raises(ValueError, match="missing columns"):
        parse_cpi_csv("TIME_PERIOD,OBS_VALUE\n2024-12,97.31\n")

# AussiePulse AI

A practice data platform for one question: **what did the Australian Consumer Price Index do, and can we show the ABS file the number came from?**

This is slice 1 of a larger project. It downloads one public series and stores that file unchanged. It does not have a database, a scheduler, or an assistant yet.

## What works now

The script downloads monthly All groups CPI for Australia from the [ABS Data API](https://www.abs.gov.au/statistics/application-programming-interfaces-apis/data-api-user-guide). It writes:

- `data/bronze/cpi/cpi_australia_all_groups_monthly.csv` — the file as the ABS sent it
- `data/bronze/cpi/manifest.json` — the URL, the download time, and a checksum

Those two files are left out of git on purpose. Anyone can recreate them with the command below. The tests use a tiny fixture instead of calling the website.

## Run it

From the repository root, on Windows PowerShell or any other terminal:

```powershell
$env:PYTHONPATH = "src"
python src/aussiepulse/ingest/cpi.py
```

A good run prints `rows=30` or another count the ABS returns that day, then `earliest=` and `latest=`. On 12 November 2026 this series came back as 30 months, from 2024-04 to 2026-09. The file is not in date order. The script sorts only the summary it prints. The saved CSV stays in the ABS order.

## Test it

```powershell
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m pytest
```

GitHub Actions runs the same tests on every push.

## Data licence

Based on Australian Bureau of Statistics data. ABS website material is used under [Creative Commons Attribution 4.0](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer).

## What this is not

The downloader runs on a laptop. It is not a production platform. There is no retry dashboard, no warehouse, and no cloud deployment.

## Next slice

Load the bronze CSV into PostgreSQL, still without editing the raw file.

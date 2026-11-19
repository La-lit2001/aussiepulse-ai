# AussiePulse AI

A practice data platform for one question: **what did the Australian Consumer Price Index do, and can we show the ABS file the number came from?**

The project currently does two things. It downloads one public price series, and it copies that file into a local PostgreSQL database. It does not have a scheduler or an assistant yet.

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

## Put the file in the database

PostgreSQL is the program that holds tables. Docker starts it on your computer with one command. Install Docker Desktop first, and leave it running.

```powershell
Copy-Item .env.example .env
docker compose up -d
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m aussiepulse.warehouse.load_bronze
```

The first run prints `file_inserted=1` and `rows_stored=` followed by the number of data lines. Run the same command again. It prints `file_inserted=0` and the same `rows_stored`. The second run found the file was already there, so it did not add the months a second time.

The price stays text in this table, such as `97.31`. The original CSV is not edited.

## Check the rows

Silver means the checked copy. A good row has a real month, such as `2024-12`, and a price that can be read as a number. That number is stored on the first day of the month. A blank price is not thrown away from the original table. It is listed in `silver.cpi_rejection` with the reason `missing_price`. If the same month appears twice, one copy is kept.

Run this after the bronze load:

```powershell
python -m aussiepulse.warehouse.build_silver
```

A good run on the full ABS file prints `months_kept=` and `rows_rejected=0`. Run it again and the counts stay the same. The command rebuilds the checked table instead of adding a second copy.

## Compare with last year

Gold is the answer a person would ask. For each checked month, the program looks for the same month one year earlier. December 2025 is compared with December 2024. The difference is stored as points and as a percent. A month that has no earlier year is still stored, with an empty change.

```powershell
python -m aussiepulse.warehouse.build_gold
```

The printout includes `months_stored=`, `comparisons=`, and a `latest=` line for the newest month that has a comparison. Run it again and the counts stay the same. Rebuild silver before rebuilding gold if you have loaded a new file.

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

The database runs on a laptop. The password in `.env.example` is only for that local database. This is not a company production system. There is no scheduler, dashboard, or cloud deployment.

## Next slice

Run this download, check, and comparison on a schedule, and record it when the ABS website fails.

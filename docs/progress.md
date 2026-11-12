# Progress

Updated 12 November 2026.

## Done

- Chose one real source: ABS monthly All groups CPI for Australia.
- Confirmed the Data API returns that series.
- Repository holds a downloader that saves the file unchanged and writes a manifest.
- Unit tests read a two-row fixture. They do not call the ABS website.

## Next, after this slice is understood

Load the bronze file into PostgreSQL without changing the raw file.

## Not started

Silver cleaning, gold metrics, dbt, PySpark, Airflow, the assistant, and the dashboard.

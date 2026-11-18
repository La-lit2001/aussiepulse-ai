# Progress

Updated 12 November 2026.

## Done

- Chose one real source: ABS monthly All groups CPI for Australia.
- Confirmed the Data API returns that series.
- Repository holds a downloader that saves the file unchanged and writes a manifest.
- Unit tests read a two-row fixture. They do not call the ABS website.
- PostgreSQL can store each raw line in `bronze.cpi_row`. Loading the same file twice does not duplicate it.
- Silver keeps one checked number per month in `silver.cpi_month`. Rows that fail a check are listed in `silver.cpi_rejection`.

## Next, after this slice is understood

Add the gold number: the change from the same month a year earlier.

## Not started

Silver cleaning, gold metrics, dbt, PySpark, Airflow, the assistant, and the dashboard.

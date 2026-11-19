# Architecture, slice 1

AussiePulse keeps official Australian numbers in layers.

```text
ABS Data API
    |
    v
Bronze: the CSV, unchanged, plus a manifest
    |
    v
Silver: one checked row per month          (not built yet)
    |
    v
Gold: change versus the same month last year (not built yet)
    |
    +--> dashboard                           (not built yet)
    +--> assistant that cites a gold row     (not built yet)
```

The download script saves the ABS response as bytes. It does not round numbers or drop months.

`bronze.cpi_file` records the checksum. `bronze.cpi_row` records each original line. Prices stay text there.

Silver reads those lines. A valid line becomes one row in `silver.cpi_month`, with the price stored as a number on the first day of that month. A line that fails a check is written to `silver.cpi_rejection` and left unchanged in bronze.

Gold reads the silver months. `gold.cpi_annual_change` stores the index, the index from 12 months earlier, the point change, and the percent change. The match is the same region, index, and frequency. An early month with no prior year keeps empty change columns.

The laptop folder `data/bronze/` stands in for a cloud file store such as Azure Data Lake. We are not spending cloud money in this slice.

The series is All groups CPI, Australia, original, monthly.

`https://data.api.abs.gov.au/rest/data/ABS,CPI,2.0.0/1.10001.10.50.M?startPeriod=2020-01&format=csvfilewithlabels`

ABS website material is under Creative Commons Attribution 4.0. Anything we calculate later is labelled "Based on Australian Bureau of Statistics data."

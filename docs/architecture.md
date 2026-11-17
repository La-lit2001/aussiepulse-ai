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

The next step copies those lines into PostgreSQL. The table `bronze.cpi_file` records the checksum. The table `bronze.cpi_row` records each original line. Prices stay text until the silver step.

The laptop folder `data/bronze/` stands in for a cloud file store such as Azure Data Lake. We are not spending cloud money in this slice.

The series is All groups CPI, Australia, original, monthly.

`https://data.api.abs.gov.au/rest/data/ABS,CPI,2.0.0/1.10001.10.50.M?startPeriod=2020-01&format=csvfilewithlabels`

ABS website material is under Creative Commons Attribution 4.0. Anything we calculate later is labelled "Based on Australian Bureau of Statistics data."

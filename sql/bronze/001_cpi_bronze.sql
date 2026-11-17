-- Bronze keeps the CPI file we downloaded.
-- The numbers stay text. Turning "97.31" into a real number happens later, in silver.

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.cpi_file (
    file_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name text NOT NULL,
    series_id text NOT NULL,
    source_url text NOT NULL,
    sha256 text NOT NULL UNIQUE,
    downloaded_at timestamptz NOT NULL,
    byte_count integer NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bronze.cpi_row (
    row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id bigint NOT NULL REFERENCES bronze.cpi_file (file_id),
    source_row_number integer NOT NULL,
    raw_line text NOT NULL,
    time_period text,
    obs_value text,
    region text,
    index_name text,
    frequency text,
    UNIQUE (file_id, source_row_number)
);

-- A book index lets you jump to a month instead of reading every row.
CREATE INDEX IF NOT EXISTS cpi_row_time_period_idx
    ON bronze.cpi_row (time_period);

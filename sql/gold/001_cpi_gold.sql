-- Gold is the business answer.
-- For each checked month, look up the same month one year earlier.
-- A month with no earlier year is still stored. Its change columns stay empty.

CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.cpi_annual_change (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id bigint NOT NULL REFERENCES bronze.cpi_file (file_id),
    silver_month_id bigint NOT NULL REFERENCES silver.cpi_month (month_id) ON DELETE CASCADE,
    time_period text NOT NULL,
    month_start date NOT NULL,
    region text NOT NULL,
    index_name text NOT NULL,
    frequency text NOT NULL,
    index_value numeric(12, 4) NOT NULL,
    previous_time_period text,
    previous_index_value numeric(12, 4),
    index_change numeric(12, 4),
    percent_change numeric(10, 4),
    built_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (file_id, time_period, region, index_name, frequency)
);

CREATE INDEX IF NOT EXISTS cpi_annual_change_month_start_idx
    ON gold.cpi_annual_change (month_start);

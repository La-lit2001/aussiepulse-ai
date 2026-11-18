-- Silver is the checked copy.
-- Each kept row has one month and one real number.
-- Rows that fail a check are listed separately. They are not deleted from bronze.

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.cpi_month (
    month_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id bigint NOT NULL REFERENCES bronze.cpi_file (file_id),
    bronze_row_id bigint NOT NULL REFERENCES bronze.cpi_row (row_id),
    time_period text NOT NULL,
    month_start date NOT NULL,
    index_value numeric(12, 4) NOT NULL,
    region text NOT NULL,
    index_name text NOT NULL,
    frequency text NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (file_id, time_period, region, index_name, frequency)
);

CREATE TABLE IF NOT EXISTS silver.cpi_rejection (
    rejection_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id bigint NOT NULL REFERENCES bronze.cpi_file (file_id),
    bronze_row_id bigint NOT NULL REFERENCES bronze.cpi_row (row_id),
    reason text NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cpi_month_month_start_idx
    ON silver.cpi_month (month_start);

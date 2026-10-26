import pytest

from analyst.config import settings
from analyst.db import validate_sql


def test_select_gets_limit():
    sql, err = validate_sql("SELECT id FROM customers;")
    assert err is None
    assert f"LIMIT {settings.max_rows}" in sql


def test_existing_limit_kept():
    sql, err = validate_sql("SELECT id FROM customers LIMIT 5")
    assert err is None and "LIMIT 5" in sql


def test_cte_allowed():
    _, err = validate_sql("WITH t AS (SELECT 1 AS a) SELECT a FROM t")
    assert err is None


def test_union_wrapped():
    sql, err = validate_sql("SELECT 1 AS a UNION SELECT 2")
    assert err is None and "LIMIT" in sql


@pytest.mark.parametrize(
    "bad",
    [
        "DROP TABLE customers",
        "DELETE FROM orders",
        "UPDATE orders SET status='x'",
        "INSERT INTO customers VALUES (1)",
        "SELECT 1; DROP TABLE customers",
        "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
        "SELECT pg_sleep(100)",
        "SELECT * FROM pg_catalog.pg_user",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM pg_stat_activity",
        "SELECT current_setting('server_version')",
        "",
    ],
)
def test_rejects_unsafe(bad):
    sql, err = validate_sql(bad)
    assert sql is None and err

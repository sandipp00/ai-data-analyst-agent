"""Needs the docker Postgres from `docker compose up` + `python -m scripts.seed`; skipped otherwise."""
import psycopg
import pytest

from analyst import db


def _db_ready() -> bool:
    try:
        db.run_query("SELECT 1 FROM customers LIMIT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="seeded Postgres not available")


@pytest.mark.parametrize(
    "stmt",
    ["DELETE FROM orders", "UPDATE customers SET name='x'", "DROP TABLE orders", "CREATE TABLE evil (a int)"],
)
def test_readonly_role_cannot_write(stmt):
    with db._connect() as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.Error):
            cur.execute(stmt)


def test_readonly_even_without_validator():
    with pytest.raises(psycopg.Error):
        db.run_query("WITH d AS (DELETE FROM orders RETURNING 1) SELECT * FROM d")


def test_statement_timeout_enforced():
    with pytest.raises(psycopg.Error):
        db.run_query("SELECT count(*) FROM generate_series(1, 1000000000)")

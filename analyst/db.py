import re
from functools import lru_cache

import pandas as pd
import psycopg
import sqlglot
from psycopg import sql as pgsql
from sqlglot import exp

from analyst.config import settings

_FORBIDDEN_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "AlterTable",
        "Merge", "Command", "TruncateTable", "Copy", "Grant", "Set",
    )
    if hasattr(exp, name)
)
_FORBIDDEN_FUNCS = re.compile(
    r"\b(pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_terminate_backend|"
    r"pg_cancel_backend|lo_import|lo_export|dblink|set_config|"
    r"current_setting|pg_stat_file|query_to_xml|table_to_xml)\b",
    re.IGNORECASE,
)
_SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


def _touches_system_catalog(stmt: exp.Expression) -> bool:
    for table in stmt.find_all(exp.Table):
        if table.db.lower() in _SYSTEM_SCHEMAS or table.name.lower().startswith("pg_"):
            return True
    return False


def validate_sql(sql: str) -> tuple[str | None, str | None]:
    """Return (clean_sql, None) if sql is a single safe read-only query, else (None, error)."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return None, "Empty SQL."
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.SqlglotError as e:
        return None, f"Syntax error: {e}"
    if len(statements) != 1:
        return None, "Exactly one SQL statement is allowed."
    stmt = statements[0]
    if not isinstance(stmt, (exp.Select, exp.Union)):
        return None, "Only SELECT queries are allowed."
    if stmt.find(*_FORBIDDEN_NODES):
        return None, "Query contains a data-modifying or administrative statement."
    if _touches_system_catalog(stmt):
        return None, "Query reads system catalogs; use only the application tables."
    if _FORBIDDEN_FUNCS.search(sql):
        return None, "Query uses a forbidden function."

    if isinstance(stmt, exp.Select):
        if not stmt.args.get("limit"):
            stmt = stmt.limit(settings.max_rows)
    else:
        stmt = exp.select("*").from_(stmt.subquery("_q")).limit(settings.max_rows)
    return stmt.sql(dialect="postgres", pretty=True), None


def _connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(
        url or settings.database_url,
        options=f"-c statement_timeout={settings.statement_timeout_ms} "
        "-c default_transaction_read_only=on",
    )


def run_query(sql: str) -> pd.DataFrame:
    with _connect() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [c.name for c in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=columns)
    for col in df.columns:  # Decimal -> float so Plotly/pandas treat them as numbers
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass
    return df


@lru_cache(maxsize=1)
def get_schema_text(sample_rows: int = 2) -> str:
    """Describe public tables, columns, keys and a few sample rows for the LLM prompt."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        tables: dict[str, list[str]] = {}
        for table, column, dtype in cur.fetchall():
            tables.setdefault(table, []).append(f"{column} {dtype}")

        cur.execute(
            """
            SELECT conrelid::regclass::text, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE contype IN ('p', 'f') AND connamespace = 'public'::regnamespace
            ORDER BY 1, contype DESC
            """
        )
        constraints: dict[str, list[str]] = {}
        for table, definition in cur.fetchall():
            constraints.setdefault(table, []).append(definition)

        blocks = []
        for table, cols in tables.items():
            lines = [f"TABLE {table}"]
            lines += [f"  {c}" for c in cols]
            lines += [f"  {d}" for d in constraints.get(table, [])]
            if sample_rows:
                cur.execute(
                    pgsql.SQL("SELECT * FROM {} LIMIT %s").format(pgsql.Identifier(table)),
                    (sample_rows,),
                )
                names = [c.name for c in cur.description]
                for row in cur.fetchall():
                    sample = ", ".join(f"{n}={v!r}" for n, v in zip(names, row))
                    lines.append(f"  -- sample: {sample}"[:300])
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)

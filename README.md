# AI Data Analyst Agent

Ask a question in plain English → get **SQL**, a **Plotly chart**, and a **written explanation**.

**Stack:** LangGraph · PostgreSQL · Plotly · Streamlit · Gemini (via `langchain-google-genai`, free tier)

## How it works

```
START → load_schema → generate_sql → validate_sql → execute_sql → explain → END
                          ▲              │  │ error       │ error
                          └──────────────┴──┴─────────────┘   (retry up to MAX_SQL_RETRIES, then give_up)
```

| Node | Job |
|---|---|
| `load_schema` | Reads tables, columns, PK/FKs and sample rows from Postgres |
| `generate_sql` | LLM writes a query (structured output). Also repairs a failed query using the error message. Says "not answerable" if the schema can't answer |
| `validate_sql` | `sqlglot` guard: single `SELECT`/CTE only, no DML/DDL, no dangerous functions, auto `LIMIT` |
| `execute_sql` | Runs in a read-only transaction with a statement timeout |
| `explain` | One LLM call writes the plain-language summary and picks a `ChartSpec` (type, x, y, color); `build_figure` validates it against the real columns and builds the Plotly figure |

**Model fallback:** each Gemini model has its own free-tier quota. If `LLM_MODEL` runs out (429), is overloaded (503) or times out, the next model in `LLM_FALLBACK_MODELS` is tried, and a failed model is skipped for a while (1 h after a quota error, 5 min otherwise).

**Safety is layered:** SQL validator → read-only transaction → statement timeout → a `SELECT`-only Postgres role (`analyst_ro`).

## Setup

```powershell
# 1. Postgres (port 5433 on host)
docker compose up -d

# 2. Python env
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Config
copy .env.example .env     # then set GOOGLE_API_KEY (free key: https://aistudio.google.com/apikey)

# 4. Demo data (customers, products, orders, order_items) + read-only role
python -m scripts.seed

# 5. Run
streamlit run app.py
# or: python cli.py "top 5 categories by revenue" --chart
```

Example questions: *"Show monthly revenue for the last 12 months"*, *"Which countries have the most customers?"*, *"Cancellation rate by segment"*.
Follow-ups work too ("now break that down by category") because recent question/SQL pairs are passed back in.

## Use your own database

1. Point `DATABASE_URL` at your Postgres, ideally using a role with `SELECT`-only grants.
2. Edit `analyst/business_context.txt` with your metric definitions (revenue, active user, etc.). This is the single biggest lever on answer quality.
3. Skip `scripts.seed`.

## Tests

```powershell
pytest
```
Covers the SQL guard, chart building, and graph routing (no API key or database needed).

## Evaluation

```powershell
python -m evals.run_evals            # scores the agent on evals/cases.json against reference SQL
```
Each case compares the agent's result set to a hand-written reference query (column names and row order ignored). Add your own cases to `evals/cases.json`. Uses the real LLM, so it is slow on the free tier.

## Docker

`docker compose --profile app up --build` also runs the Streamlit app on http://localhost:8501 (seed the database first). CI (`.github/workflows/ci.yml`) runs the tests against a seeded Postgres.

## Layout

```
analyst/        config, db (schema + guard + execution), nodes, graph, charts, llm, state
scripts/seed.py demo schema + synthetic data + read-only role
app.py          Streamlit chat UI
cli.py          terminal interface
tests/
evals/          question set + scorer
```

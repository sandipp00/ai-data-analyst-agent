from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from analyst import db
from analyst.charts import ChartSpec, build_figure
from analyst.config import settings
from analyst.llm import structured_llm
from analyst.state import AnalystState

SQL_SYSTEM = """You are a senior data analyst who writes PostgreSQL.

Rules:
- Use only the tables and columns in the schema. Never invent columns.
- Write exactly one read-only SELECT (CTEs allowed). Never modify data.
- Alias computed columns with clear snake_case names.
- Qualify column names when joining. Prefer explicit JOINs.
- For time series use date_trunc and ORDER BY the period.
- If the question cannot be answered from this schema, set answerable=false and
  explain why (or ask a clarifying question) in `message`.

Business definitions:
{business_context}

Database schema:
{schema}"""

EXPLAIN_SYSTEM = """You are a data analyst explaining query results to a business user.
Write 2-5 sentences in plain language: answer the question directly, cite the key
numbers, and call out any notable pattern or caveat (e.g. results truncated, empty).
Do not mention SQL syntax. Do not invent numbers that are not in the data."""

CHART_SYSTEM = """Pick the best Plotly chart for a query result.
- Trends over time -> line (never scatter); category comparisons -> bar; shares of a whole
  with <= 8 categories -> pie; two numeric columns -> scatter; one numeric distribution
  -> histogram.
- Use only column names that appear in the result. y must be numeric.
- Choose chart_type 'none' if a table or single number is clearer."""


class Analysis(BaseModel):
    answer: str = Field(description="The plain-language explanation of the result.")
    chart: ChartSpec


class SQLResult(BaseModel):
    answerable: bool = Field(description="False if the schema cannot answer the question.")
    sql: str = Field("", description="The PostgreSQL SELECT query.")
    message: str = Field("", description="Explanation/clarifying question when not answerable.")


def load_schema(state: AnalystState) -> dict:
    return {"schema": db.get_schema_text(), "attempts": 0, "error": None}


def generate_sql(state: AnalystState) -> dict:
    system = SQL_SYSTEM.format(
        business_context=settings.business_context, schema=state["schema"]
    )
    parts = []
    for turn in state.get("history", [])[-3:]:
        parts.append(f"Earlier question: {turn['question']}\nEarlier SQL:\n{turn['sql']}")
    parts.append(f"Question: {state['question']}")
    if state.get("error"):
        parts.append(
            f"Your previous query failed.\nQuery:\n{state['sql']}\nError: {state['error']}\n"
            "Return a corrected query."
        )
    result: SQLResult = structured_llm(SQLResult).invoke(
        [SystemMessage(system), HumanMessage("\n\n".join(parts))]
    )
    if not result.answerable:
        return {"answerable": False, "answer": result.message or "I can't answer that from this database."}
    return {"answerable": True, "sql": result.sql}


def validate_sql(state: AnalystState) -> dict:
    clean, error = db.validate_sql(state["sql"])
    if error:
        return {"error": error, "attempts": state["attempts"] + 1}
    return {"sql": clean, "error": None}


def execute_sql(state: AnalystState) -> dict:
    try:
        return {"df": db.run_query(state["sql"]), "error": None}
    except Exception as e:  # database errors feed back into the repair loop
        return {"error": str(e).strip(), "attempts": state["attempts"] + 1}


def give_up(state: AnalystState) -> dict:
    return {
        "answer": "I couldn't produce a working query for that question. "
        f"Last error: {state.get('error')}"
    }


def explain(state: AnalystState) -> dict:
    """One LLM call: write the explanation and pick the chart for the result."""
    df = state["df"]
    note = f" (showing first 50 of {len(df)})" if len(df) > 50 else ""
    data = df.head(50).to_csv(index=False) if not df.empty else "(no rows returned)"
    prompt = (
        f"Question: {state['question']}\nSQL:\n{state['sql']}\n"
        f"Column dtypes: {df.dtypes.astype(str).to_dict()}\n"
        f"Result{note}:\n{data}"
    )
    result: Analysis = structured_llm(Analysis).invoke(
        [SystemMessage(EXPLAIN_SYSTEM + "\n\n" + CHART_SYSTEM), HumanMessage(prompt)]
    )
    figure = build_figure(df, result.chart) if len(df) >= 2 else None
    return {"answer": result.answer.strip(), "figure": figure}


# ---- routing ----------------------------------------------------------------

def route_after_generate(state: AnalystState) -> str:
    return "validate_sql" if state.get("answerable") else "end"


def route_after_validate(state: AnalystState) -> str:
    if not state.get("error"):
        return "execute_sql"
    return "generate_sql" if state["attempts"] <= settings.max_sql_retries else "give_up"


def route_after_execute(state: AnalystState) -> str:
    if not state.get("error"):
        return "explain"
    return "generate_sql" if state["attempts"] <= settings.max_sql_retries else "give_up"

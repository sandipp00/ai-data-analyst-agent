import time

import streamlit as st

from analyst import db, stream_question

st.set_page_config(page_title="AI Data Analyst", page_icon="📊", layout="wide")
st.title("📊 AI Data Analyst")
st.caption("Ask a question about your data — get SQL, a chart, and an explanation.")

EXAMPLES = [
    "What are the top 5 product categories by revenue?",
    "Show monthly revenue for the last 12 months",
    "Which countries have the most customers?",
    "What is the cancellation rate by customer segment?",
]

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.subheader("Try asking")
    clicked = None
    for example in EXAMPLES:
        if st.button(example, use_container_width=True):
            clicked = example
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    with st.expander("Database schema"):
        try:
            st.code(db.get_schema_text(), language="text")
        except Exception as e:
            st.error(f"Cannot reach the database: {e}")


def describe(node: str, state: dict) -> str | None:
    """One progress line for a finished graph node."""
    error = (state.get("error") or "").splitlines()[0] if state.get("error") else None
    if node == "load_schema":
        return "Loaded the database schema"
    if node == "generate_sql":
        if not state.get("answerable"):
            return "This can't be answered from the database"
        return "Rewrote the query" if state.get("attempts") else "Wrote a SQL query"
    if node == "validate_sql":
        return f"Query failed the safety check: {error}" if error else "Query passed the safety check"
    if node == "execute_sql":
        if error:
            return f"Query failed: {error}"
        return f"Ran the query: {len(state['df']):,} rows"
    if node == "explain":
        return "Wrote the explanation and picked a chart"
    if node == "give_up":
        return f"Gave up after {state.get('attempts', 0)} failed attempts"
    return None


def run_with_progress(question: str, history: list[dict]) -> dict:
    """Run the agent, showing each step in a status box as it finishes."""
    start = time.perf_counter()
    steps: list[str] = []
    with st.status("Analyzing...", expanded=True) as status:
        try:
            out: dict = {}
            for node, out in stream_question(question, history):
                line = describe(node, out)
                if line:
                    steps.append(line)
                    st.write(line)
                    status.update(label=f"{line}...")
                if node == "generate_sql" and out.get("answerable"):
                    st.code(out["sql"], language="sql")
            result = {k: out.get(k) for k in ("answer", "sql", "df", "figure")}
            result["answer"] = result["answer"] or "No answer produced."
            failed = result["df"] is None and out.get("answerable") is not False
        except Exception as e:
            result, failed = {"answer": f"Something went wrong: {e}"}, True
            steps.append(f"Error: {e}")
        result["steps"] = steps
        result["seconds"] = time.perf_counter() - start
        status.update(**status_args(result, failed), expanded=False)
    result["failed"] = failed
    return result


def status_args(result: dict, failed: bool) -> dict:
    return {
        "label": f"{'Failed' if failed else 'Done'} in {result['seconds']:.0f}s",
        "state": "error" if failed else "complete",
    }


def render(result: dict, key: str, show_steps: bool = True) -> None:
    if show_steps and result.get("steps"):
        with st.status(**status_args(result, result.get("failed", False)), expanded=False):
            for line in result["steps"]:
                st.write(line)
    # Escape $ so amounts like "$264,690 ... $202,196" aren't rendered as LaTeX math.
    st.markdown(result["answer"].replace("$", r"\$"))
    if result.get("figure") is not None:
        st.plotly_chart(result["figure"], use_container_width=True)
    if result.get("df") is not None:
        st.dataframe(result["df"], use_container_width=True)
        st.download_button(
            "Download CSV",
            result["df"].to_csv(index=False).encode("utf-8"),
            file_name="result.csv",
            mime="text/csv",
            key=f"csv-{key}",
        )
    if result.get("sql"):
        with st.expander("SQL"):
            st.code(result["sql"], language="sql")


for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render(msg["content"], key=str(i))

question = st.chat_input("Ask a question about your data") or clicked
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Pair each question with the answer right after it. Don't assume strict
    # alternation: an interrupted run leaves a user message with no answer.
    msgs = st.session_state.messages
    history = [
        {"question": q["content"], "sql": a["content"]["sql"]}
        for q, a in zip(msgs, msgs[1:])
        if q["role"] == "user" and a["role"] == "assistant" and a["content"].get("sql")
    ]
    with st.chat_message("assistant"):
        result = run_with_progress(question, history)
        render(result, key=str(len(st.session_state.messages)), show_steps=False)
    st.session_state.messages.append({"role": "assistant", "content": result})

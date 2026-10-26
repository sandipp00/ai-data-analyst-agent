import streamlit as st

from analyst import db, run_question

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


def render(result: dict, key: str) -> None:
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
        with st.spinner("Analyzing..."):
            try:
                out = run_question(question, history)
                result = {k: out.get(k) for k in ("answer", "sql", "df", "figure")}
                result["answer"] = result["answer"] or "No answer produced."
            except Exception as e:
                result = {"answer": f"Something went wrong: {e}"}
        render(result, key=str(len(st.session_state.messages)))
    st.session_state.messages.append({"role": "assistant", "content": result})

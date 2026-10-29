import logging
import time
from collections.abc import Iterator
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from analyst import nodes
from analyst.state import AnalystState

log = logging.getLogger("analyst")


def build_graph():
    g = StateGraph(AnalystState)
    g.add_node("load_schema", nodes.load_schema)
    g.add_node("generate_sql", nodes.generate_sql)
    g.add_node("validate_sql", nodes.validate_sql)
    g.add_node("execute_sql", nodes.execute_sql)
    g.add_node("explain", nodes.explain)
    g.add_node("give_up", nodes.give_up)

    g.add_edge(START, "load_schema")
    g.add_edge("load_schema", "generate_sql")
    g.add_conditional_edges(
        "generate_sql",
        nodes.route_after_generate,
        {"validate_sql": "validate_sql", "end": END},
    )
    g.add_conditional_edges(
        "validate_sql",
        nodes.route_after_validate,
        {"execute_sql": "execute_sql", "generate_sql": "generate_sql", "give_up": "give_up"},
    )
    g.add_conditional_edges(
        "execute_sql",
        nodes.route_after_execute,
        {"explain": "explain", "generate_sql": "generate_sql", "give_up": "give_up"},
    )
    g.add_edge("explain", END)
    g.add_edge("give_up", END)
    return g.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


def stream_question(
    question: str, history: list[dict] | None = None
) -> Iterator[tuple[str, AnalystState]]:
    """Run the agent step by step, yielding (node name, state so far) after each node.
    `history` is a list of prior {"question", "sql"} turns for follow-ups."""
    start = time.perf_counter()
    out: AnalystState = {"question": question, "history": history or []}
    for update in get_graph().stream(dict(out), stream_mode="updates"):
        for node, changes in update.items():
            out.update(changes or {})
            yield node, out
    df = out.get("df")
    log.info(
        "question=%r answerable=%s rows=%s retries=%s seconds=%.1f sql=%r",
        question,
        out.get("answerable"),
        None if df is None else len(df),
        out.get("attempts", 0),
        time.perf_counter() - start,
        " ".join((out.get("sql") or "").split()),
    )


def run_question(question: str, history: list[dict] | None = None) -> AnalystState:
    """Run the agent to completion and return the final state."""
    out: AnalystState = {}
    for _, out in stream_question(question, history):
        pass
    return out

"""Full-graph tests with the LLM and database stubbed out (no key or Postgres needed)."""
import pandas as pd
import pytest

from analyst import graph, nodes
from analyst.charts import ChartSpec


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, schema):
        outer = self

        class _Runnable:
            def invoke(self, messages):
                outer.calls.append(messages)
                return outer.responses.pop(0)

        return _Runnable()


@pytest.fixture
def stub(monkeypatch):
    def install(responses, run_query=None):
        fake = FakeLLM(responses)
        monkeypatch.setattr(nodes, "structured_llm", fake)
        monkeypatch.setattr(nodes.db, "get_schema_text", lambda: "TABLE t\n  a integer")
        if run_query:
            monkeypatch.setattr(nodes.db, "run_query", run_query)
        return fake

    return install


def sql(q):
    return nodes.SQLResult(answerable=True, sql=q)


def analysis():
    return nodes.Analysis(answer="Two rows.", chart=ChartSpec(chart_type="bar", x="a", y="b"))


def test_happy_path(stub):
    fake = stub(
        [sql("SELECT 1 AS a, 2 AS b UNION ALL SELECT 3, 4"), analysis()],
        run_query=lambda q: pd.DataFrame({"a": [1, 3], "b": [2, 4]}),
    )
    out = graph.build_graph().invoke({"question": "q", "history": []})
    assert out["answer"] == "Two rows."
    assert out["figure"] is not None
    assert len(fake.calls) == 2


def test_unanswerable_skips_database(stub):
    stub([nodes.SQLResult(answerable=False, message="No salary data.")])
    out = graph.build_graph().invoke({"question": "CEO salary?", "history": []})
    assert out["answer"] == "No salary data."
    assert "df" not in out


def test_unsafe_sql_is_repaired(stub):
    fake = stub(
        [sql("DROP TABLE t"), sql("SELECT 1 AS a"), analysis()],
        run_query=lambda q: pd.DataFrame({"a": [1]}),
    )
    out = graph.build_graph().invoke({"question": "q", "history": []})
    assert out["sql"].startswith("SELECT")
    assert "Only SELECT" in str(fake.calls[1][-1].content)  # error fed back to the LLM


def test_execution_error_retries_then_gives_up(stub):
    def boom(q):
        raise RuntimeError("column x does not exist")

    stub([sql("SELECT x FROM t")] * 3, run_query=boom)
    out = graph.build_graph().invoke({"question": "q", "history": []})
    assert "couldn't produce a working query" in out["answer"]
    assert "column x does not exist" in out["answer"]


def test_history_is_passed_to_llm(stub):
    fake = stub([nodes.SQLResult(answerable=False, message="n/a")])
    history = [{"question": "first?", "sql": "SELECT 1"}]
    graph.build_graph().invoke({"question": "and now?", "history": history})
    prompt = fake.calls[0][-1].content
    assert "first?" in prompt and "SELECT 1" in prompt

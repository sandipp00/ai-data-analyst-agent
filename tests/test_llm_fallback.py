import pytest
from langchain_core.runnables import RunnableLambda

from analyst import llm


class FakeModel:
    def __init__(self, model, fail=None):
        self.model, self.fail, self.calls = model, fail, 0

    def with_structured_output(self, schema):
        def call(_):
            self.calls += 1
            if self.fail:
                raise RuntimeError(self.fail)
            return self.model

        return RunnableLambda(call)


@pytest.fixture(autouse=True)
def fresh_cooldowns(monkeypatch):
    monkeypatch.setattr(llm, "_cooldown_until", {})


def use(monkeypatch, *models):
    monkeypatch.setattr(llm, "get_models", lambda: list(models))


def test_falls_back_to_next_model(monkeypatch):
    use(monkeypatch, FakeModel("a", "429 RESOURCE_EXHAUSTED"), FakeModel("b", "503"), FakeModel("c"))
    assert llm.structured_llm(dict).invoke("q") == "c"


def test_primary_used_when_it_works(monkeypatch):
    use(monkeypatch, FakeModel("a"), FakeModel("b"))
    assert llm.structured_llm(dict).invoke("q") == "a"


def test_failed_model_is_skipped_on_later_calls(monkeypatch):
    a, b = FakeModel("a", "429 RESOURCE_EXHAUSTED"), FakeModel("b")
    use(monkeypatch, a, b)
    llm.structured_llm(dict).invoke("q")
    llm.structured_llm(dict).invoke("q")
    assert (a.calls, b.calls) == (1, 2)


def test_all_cooling_down_still_tries(monkeypatch):
    a = FakeModel("a")
    use(monkeypatch, a)
    llm._cooldown_until["a"] = float("inf")
    assert llm.structured_llm(dict).invoke("q") == "a"


def test_error_lists_every_model_when_all_fail(monkeypatch):
    use(monkeypatch, FakeModel("a", "429"), FakeModel("b", "504"))
    with pytest.raises(RuntimeError, match="(?s)a: 429.*b: 504"):
        llm.structured_llm(dict).invoke("q")


def test_models_are_deduplicated_in_order():
    names = [m.model for m in llm.get_models()]
    assert len(names) == len(set(names))

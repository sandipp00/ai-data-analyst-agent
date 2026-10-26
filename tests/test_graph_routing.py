from analyst import nodes
from analyst.config import settings


def test_validation_error_retries_then_gives_up():
    assert nodes.route_after_validate({"error": "bad", "attempts": 1}) == "generate_sql"
    assert nodes.route_after_validate({"error": "bad", "attempts": settings.max_sql_retries + 1}) == "give_up"
    assert nodes.route_after_validate({"error": None, "attempts": 0}) == "execute_sql"


def test_execute_error_routing():
    assert nodes.route_after_execute({"error": "boom", "attempts": 1}) == "generate_sql"
    assert nodes.route_after_execute({"error": None, "attempts": 0}) == "explain"


def test_unanswerable_ends():
    assert nodes.route_after_generate({"answerable": False}) == "end"

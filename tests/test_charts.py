import pandas as pd

from analyst.charts import ChartSpec, build_figure

DF = pd.DataFrame({"month": ["2025-01", "2025-02", "2025-03"], "revenue": [10.0, 20.0, 15.0]})


def test_bar():
    fig = build_figure(DF, ChartSpec(chart_type="bar", x="month", y="revenue", title="t"))
    assert fig is not None and fig.data[0].type == "bar"


def test_none_spec():
    assert build_figure(DF, ChartSpec(chart_type="none")) is None


def test_unknown_column_returns_none():
    assert build_figure(DF, ChartSpec(chart_type="line", x="nope", y="revenue")) is None


def test_non_numeric_y_returns_none():
    assert build_figure(DF, ChartSpec(chart_type="bar", x="revenue", y="month")) is None


def test_scatter_on_category_axis_becomes_line():
    fig = build_figure(DF, ChartSpec(chart_type="scatter", x="month", y="revenue"))
    assert fig.data[0].type == "scatter" and fig.data[0].mode == "lines"

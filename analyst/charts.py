from typing import Literal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pydantic import BaseModel, Field

ChartType = Literal["bar", "line", "area", "pie", "scatter", "histogram", "box", "none"]


class ChartSpec(BaseModel):
    chart_type: ChartType = Field(
        description="Best chart for the result; 'none' if a table or single number says it all."
    )
    x: str | None = Field(None, description="Result column for the x axis (or pie labels).")
    y: str | None = Field(None, description="Numeric result column for the y axis (or pie values).")
    color: str | None = Field(None, description="Optional result column to split series by.")
    title: str = Field("", description="Short descriptive chart title.")


_PLAIN = {"bar": px.bar, "line": px.line, "area": px.area, "scatter": px.scatter, "box": px.box}


def build_figure(df: pd.DataFrame, spec: ChartSpec) -> go.Figure | None:
    """Build a Plotly figure from a spec, returning None if the spec doesn't fit the data."""
    if spec.chart_type == "none" or df.empty:
        return None

    cols = set(df.columns)
    x = spec.x if spec.x in cols else None
    y = spec.y if spec.y in cols else None
    color = spec.color if spec.color in cols else None
    kwargs = {"title": spec.title or None, "template": "plotly_white"}
    kind = spec.chart_type
    if kind == "scatter" and x and not pd.api.types.is_numeric_dtype(df[x]):
        kind = "line"  # a scatter over dates/categories reads better as a trend line

    if kind == "histogram":
        if not x:
            return None
        fig = px.histogram(df, x=x, color=color, **kwargs)
    else:
        if not (x and y) or not pd.api.types.is_numeric_dtype(df[y]):
            return None
        if kind == "pie":
            fig = px.pie(df, names=x, values=y, **kwargs)
        else:
            data = df.sort_values(x) if kind in ("line", "area") else df
            fig = _PLAIN[kind](data, x=x, y=y, color=color, **kwargs)

    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    return fig

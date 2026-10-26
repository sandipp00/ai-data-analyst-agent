from typing import TypedDict

import pandas as pd
import plotly.graph_objects as go


class AnalystState(TypedDict, total=False):
    # inputs
    question: str
    history: list[dict]  # prior turns: {"question": ..., "sql": ...}
    # working state
    schema: str
    sql: str
    answerable: bool
    error: str | None
    attempts: int
    # outputs
    df: pd.DataFrame
    figure: go.Figure | None
    answer: str

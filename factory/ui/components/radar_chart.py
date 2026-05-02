"""Radar chart for score_breakdown (4 dimensions, 0-25 each)."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

DIMENSIONS = ("novelty", "demand", "monetization", "feasibility")
COLORS = {
    "line": "#4F46E5",
    "fill": "rgba(79, 70, 229, 0.25)",
}


def render_radar(breakdown: dict[str, Any] | None, max_val: int = 25) -> go.Figure:
    """Return a plotly Figure rendering the 4-dimension score breakdown."""
    values: list[float] = []
    for d in DIMENSIONS:
        raw = (breakdown or {}).get(d)
        try:
            values.append(float(raw) if raw is not None else 0.0)
        except (TypeError, ValueError):
            values.append(0.0)
    # Close the loop by repeating the first value
    values.append(values[0])
    theta = [d.capitalize() for d in DIMENSIONS] + [DIMENSIONS[0].capitalize()]

    fig = go.Figure(
        data=[
            go.Scatterpolar(
                r=values,
                theta=theta,
                fill="toself",
                line={"color": COLORS["line"], "width": 2},
                fillcolor=COLORS["fill"],
                marker={"size": 8},
                hovertemplate="%{theta}: %{r}/25<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        polar={
            "radialaxis": {
                "visible": True,
                "range": [0, max_val],
                "tickvals": [5, 10, 15, 20, 25],
                "gridcolor": "#e5e7eb",
            },
            "angularaxis": {"gridcolor": "#e5e7eb"},
        },
        showlegend=False,
        margin={"t": 30, "b": 30, "l": 40, "r": 40},
        height=360,
    )
    return fig

"""
OmniView IQ — DataViz Theme & Plotly Styling Engine
===================================================

Applies best practices from the DataViz Skill & Datawrapper Color Guides:
- Okabe-Ito accessible color-blind safe palette
- Functional color usage (color conveys threshold / status only)
- Direct label annotations on reference lines
- High data-to-ink ratio (subtle gridlines, no chart junk, honest zero baselines)
"""

from __future__ import annotations

from typing import Any
import plotly.graph_objects as go

# ── Okabe-Ito Color-Blind Safe Palette ──────────────────────────────────────
# Reference: Datawrapper Color Guide & Wong (Nature Methods, 2011)
PALETTE = {
    "blue": "#0072B2",        # Primary signal / baseline series
    "orange": "#E69F00",      # Warning / caution / near-miss
    "green": "#009E73",       # Normal / healthy / Zone A
    "yellow": "#F0E442",      # Watch / Zone B
    "vermillion": "#D55E00",  # Critical / breach / Zone D
    "sky_blue": "#56B4E9",    # Secondary reference signal
    "purple": "#CC79A7",      # Accent / projections / CUSUM
    "dark_gray": "#1E293B",    # Text primary
    "muted_gray": "#64748B",   # Secondary text / gridlines
    "light_gray": "#94A3B8",   # Subtle borders
    "bg_dark": "#0F172A",      # Surface dark
    "grid_color": "rgba(148, 163, 184, 0.15)",
}


def apply_dataviz_layout(
    fig: go.Figure,
    title: str,
    height: int = 380,
    xaxis_title: str = "Time",
    yaxis_title: str = "",
    show_legend: bool = True,
) -> go.Figure:
    """Apply Wilke & Tufte clean data-to-ink design principles to a Plotly figure."""
    fig.update_layout(
        title={
            "text": f"<b>{title}</b>",
            "font": {"size": 14, "color": "#F8FAFC", "family": "Inter, system-ui, sans-serif"},
            "x": 0.01,
            "xanchor": "left",
            "y": 0.96,
        },
        height=height,
        margin={"l": 48, "r": 24, "t": 48, "b": 40},
        paper_bgcolor="#0F172A",
        plot_bgcolor="#0F172A",
        font={"family": "Inter, system-ui, sans-serif", "color": "#E2E8F0", "size": 11},
        showlegend=show_legend,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1.0,
            "font": {"size": 10, "color": "#94A3B8"},
            "bgcolor": "rgba(15, 23, 42, 0.7)",
        },
        hovermode="x unified",
        hoverlabel={
            "bgcolor": "#1E293B",
            "font_size": 11,
            "font_family": "Inter, monospace",
            "bordercolor": "#334155",
        },
    )

    fig.update_xaxes(
        title_text=xaxis_title,
        title_font={"size": 11, "color": "#94A3B8"},
        tickfont={"size": 10, "color": "#94A3B8"},
        showgrid=True,
        gridcolor=PALETTE["grid_color"],
        gridwidth=1,
        zeroline=False,
    )

    fig.update_yaxes(
        title_text=yaxis_title,
        title_font={"size": 11, "color": "#94A3B8"},
        tickfont={"size": 10, "color": "#94A3B8"},
        showgrid=True,
        gridcolor=PALETTE["grid_color"],
        gridwidth=1,
        zeroline=True,
        zerolinecolor="rgba(148, 163, 184, 0.25)",
    )

    return fig


def add_threshold_line(
    fig: go.Figure,
    y_val: float,
    label: str,
    color: str = PALETTE["vermillion"],
    line_dash: str = "dash",
    annotation_position: str = "top right",
) -> None:
    """Add a direct-labeled reference line adhering to Wilke's direct labeling rule."""
    fig.add_hline(
        y=y_val,
        line_dash=line_dash,
        line_color=color,
        line_width=1.5,
        annotation_text=f"<b>{label} ({y_val})</b>",
        annotation_position=annotation_position,
        annotation_font_size=10,
        annotation_font_color=color,
    )


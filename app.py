from __future__ import annotations

from io import BytesIO, StringIO

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from fleet_repair_age import (
    AGGREGATION_METHODS,
    AUTO_COLUMN_ALIASES,
    SMOOTHING_METHODS,
    apply_smoothing,
    auto_map_columns,
    build_category_summary,
    clean_repair_age_data,
    load_table,
)


st.set_page_config(
    page_title="Fleet Repair % by Vehicle Age",
    page_icon="📈",
    layout="wide",
)


# Embedded fallback sample so Streamlit Cloud does not crash if sample_repair_age.csv
# is not included in the deployed repo.
SAMPLE_CSV = """Health Segments,Age,Median
Trailers,,1.45%
Service / Light Fleet,0,4.20%
Cleaning and Servicing Fleet,0,0.81%
Inspection/Specialty,0,0.41%
Trailers,0,11.47%
Exclude,1,1.21%
Cleaning and Servicing Fleet,1,3.43%
Service / Light Fleet,1,2.38%
Inspection/Specialty,1,0.19%
Trailers,1,5.22%
Service / Light Fleet,2,1.74%
Cleaning and Servicing Fleet,2,6.38%
Inspection/Specialty,2,6.98%
Trailers,2,24.17%
Power Units,2,8.80%
Cleaning and Servicing Fleet,3,10.19%
Service / Light Fleet,3,7.21%
Inspection/Specialty,3,0.78%
Trailers,3,28.15%
"""


SMOOTHING_DOC = """
### What smoothing does

Smoothing creates a second value called `smoothed_median_repair_pct` for each category-age point.  
It does **not** overwrite the raw `median_repair_pct`.

Use smoothing when the raw age curve is noisy because each age/category point has limited repair history. The goal is to reveal the underlying shape of repair cost intensity as assets age.

### Available methods

**None**  
Plots the raw uploaded median repair percentage only.

**Centered moving average**  
For each age, averages nearby ages within the selected window. A 3-age centered window for age 2 uses ages 1, 2, and 3 when available. This is best for presentation because it smooths noise without creating as much lag.

**Trailing moving average**  
For each age, averages the current age and prior ages. A 3-age trailing window for age 3 uses ages 1, 2, and 3. This is more conservative because it does not use future ages to smooth the current point.

**Weighted moving average**  
Similar to a trailing moving average, but newer ages receive more weight. With a 3-age window, the oldest point gets weight 1, the middle gets weight 2, and the newest gets weight 3. This reacts faster than a simple trailing average.

**Exponential smoothing**  
Applies a recursive smoothing formula where the current smoothed value is a blend of the current raw value and the previous smoothed value. Higher alpha reacts faster to changes; lower alpha creates a flatter curve.

Formula:

`smoothed_t = alpha * raw_t + (1 - alpha) * smoothed_(t-1)`

### How to read the chart

- Solid lines are smoothed values when smoothing is enabled.
- Raw points can be shown as markers for auditability.
- The summary table keeps both raw and smoothed metrics.
- Smoothing is calculated independently within each category. Categories never borrow values from other categories.

### Recommended settings

For this fleet repair-age data, start with:

- **Centered moving average**
- **Window size = 3**
- **Minimum periods = 1**
- **Show raw points = on**

That gives a readable curve while still keeping the uploaded values visible.
"""


@st.cache_data(show_spinner=False)
def cached_load_table(file_name: str, file_bytes: bytes, sheet_name: str | None = None) -> pd.DataFrame:
    return load_table(file_name=file_name, file_bytes=file_bytes, sheet_name=sheet_name)


@st.cache_data(show_spinner=False)
def cached_excel_sheet_names(file_bytes: bytes) -> list[str]:
    return pd.ExcelFile(BytesIO(file_bytes)).sheet_names


@st.cache_data(show_spinner=False)
def cached_sample() -> pd.DataFrame:
    return pd.read_csv(StringIO(SAMPLE_CSV))


def _selectbox_index(options: list[str], selected: str | None) -> int:
    if selected in options:
        return options.index(selected)
    return 0


def _format_pct(value: float) -> str:
    return f"{value:.2f}%"


def _safe_metric(label: str, value) -> None:
    st.metric(label, value if value is not None else "—")


def render_data_quality(clean_result) -> None:
    issues = []
    if clean_result.rows_dropped_missing_category:
        issues.append(f"{clean_result.rows_dropped_missing_category:,} row(s) dropped for missing category.")
    if clean_result.rows_dropped_missing_age:
        issues.append(f"{clean_result.rows_dropped_missing_age:,} row(s) dropped for missing/non-numeric age.")
    if clean_result.rows_dropped_missing_median:
        issues.append(f"{clean_result.rows_dropped_missing_median:,} row(s) dropped for missing/non-numeric median repair %.")
    if clean_result.rows_dropped_excluded_category:
        issues.append(f"{clean_result.rows_dropped_excluded_category:,} row(s) dropped due to excluded categories.")
    if clean_result.duplicate_category_age_rows:
        issues.append(
            f"{clean_result.duplicate_category_age_rows:,} duplicate category-age row(s) aggregated "
            f"using {clean_result.aggregation_method}."
        )

    if issues:
        with st.expander("Data quality notes", expanded=False):
            for issue in issues:
                st.write(f"- {issue}")


def build_line_chart(
    plot_df: pd.DataFrame,
    value_col: str,
    smoothing_label: str,
    show_raw_points: bool,
    show_line_markers: bool,
    show_data_labels: bool,
) -> go.Figure:
    fig = go.Figure()

    categories = sorted(plot_df["category"].unique().tolist())

    for category in categories:
        grp = plot_df.loc[plot_df["category"] == category].sort_values("age").copy()

        if show_raw_points and value_col != "median_repair_pct":
            fig.add_trace(
                go.Scatter(
                    x=grp["age"],
                    y=grp["median_repair_pct"],
                    mode="markers",
                    name=f"{category} raw",
                    legendgroup=category,
                    showlegend=False,
                    marker=dict(size=7, opacity=0.45, symbol="circle-open"),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Age: %{x}<br>"
                        "Raw median repair %: %{y:.2f}%"
                        "<extra></extra>"
                    ),
                    customdata=grp[["category"]],
                )
            )

        text_values = grp[value_col].map(lambda x: f"{x:.1f}%") if show_data_labels else None
        mode = "lines+markers+text" if show_data_labels else ("lines+markers" if show_line_markers else "lines")

        fig.add_trace(
            go.Scatter(
                x=grp["age"],
                y=grp[value_col],
                mode=mode,
                name=category,
                legendgroup=category,
                text=text_values,
                textposition="top center",
                line=dict(width=3),
                marker=dict(size=8),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Age: %{x}<br>"
                    f"{smoothing_label}: " + "%{y:.2f}%<br>"
                    "Raw median repair %: %{customdata[1]:.2f}%"
                    "<extra></extra>"
                ),
                customdata=grp[["category", "median_repair_pct"]],
            )
        )

    fig.update_layout(
        title="Median repair % by vehicle age and health segment",
        xaxis_title="Vehicle age",
        yaxis_title="Median repair %",
        hovermode="x unified",
        legend_title_text="Health segment",
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.update_yaxes(ticksuffix="%", rangemode="tozero")
    fig.update_xaxes(dtick=1)

    return fig


def main() -> None:
    st.title("Fleet Repair % by Vehicle Age")
    st.caption(
        "Upload a CSV or Excel file with health segment/category, vehicle age, and median repair %. "
        "The app cleans percent formats, handles Excel percent values, filters categories, smooths curves, and plots category lines by age."
    )

    with st.sidebar:
        st.header("1. Upload")
        uploaded_file = st.file_uploader(
            "Upload repair-age table",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=False,
        )

        sheet_name = None
        raw_df = None
        source_label = "Embedded sample data"

        if uploaded_file is None:
            st.info("No file uploaded. Showing embedded sample data.")
            raw_df = cached_sample()
        else:
            file_bytes = uploaded_file.getvalue()
            source_label = uploaded_file.name

            if uploaded_file.name.lower().endswith((".xlsx", ".xls")):
                sheet_names = cached_excel_sheet_names(file_bytes)
                sheet_name = st.selectbox("Excel sheet", sheet_names)
            raw_df = cached_load_table(uploaded_file.name, file_bytes, sheet_name)

        if raw_df is None or raw_df.empty:
            st.error("The uploaded file is empty or could not be read.")
            st.stop()

        st.divider()
        st.header("2. Map columns")

        columns = list(raw_df.columns)
        inferred = auto_map_columns(raw_df)

        category_col = st.selectbox(
            "Category / health segment column",
            columns,
            index=_selectbox_index(columns, inferred.get("category")),
            help=f"Auto-detected aliases: {', '.join(AUTO_COLUMN_ALIASES['category'])}",
        )
        age_col = st.selectbox(
            "Vehicle age column",
            columns,
            index=_selectbox_index(columns, inferred.get("age")),
            help=f"Auto-detected aliases: {', '.join(AUTO_COLUMN_ALIASES['age'])}",
        )
        median_col = st.selectbox(
            "Median repair % column",
            columns,
            index=_selectbox_index(columns, inferred.get("median_repair_pct")),
            help=f"Auto-detected aliases: {', '.join(AUTO_COLUMN_ALIASES['median_repair_pct'])}",
        )

        st.divider()
        st.header("3. Filters")

        all_categories_preview = (
            raw_df[category_col]
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .sort_values()
            .unique()
            .tolist()
        )

        default_exclusions = [c for c in all_categories_preview if c.lower() in {"exclude", "excluded"}]

        excluded_categories = st.multiselect(
            "Exclude categories",
            options=all_categories_preview,
            default=default_exclusions,
        )

        aggregation_label = st.selectbox(
            "If duplicate category-age rows exist",
            list(AGGREGATION_METHODS.keys()),
            index=0,
        )

    clean_result = clean_repair_age_data(
        raw_df=raw_df,
        category_col=category_col,
        age_col=age_col,
        median_col=median_col,
        excluded_categories=excluded_categories,
        aggregation_method=AGGREGATION_METHODS[aggregation_label],
    )

    clean_df = clean_result.data

    if clean_df.empty:
        st.error("No usable rows remain after cleaning. Check the mapped columns and filters.")
        render_data_quality(clean_result)
        st.stop()

    min_age = int(clean_df["age"].min())
    max_age = int(clean_df["age"].max())

    with st.sidebar:
        age_range = st.slider(
            "Age range",
            min_value=min_age,
            max_value=max_age,
            value=(min_age, max_age),
            step=1,
        )

        available_categories = sorted(clean_df["category"].unique().tolist())
        selected_categories = st.multiselect(
            "Categories to plot",
            options=available_categories,
            default=available_categories,
        )

        st.divider()
        st.header("4. Smoothing")

        smoothing_label = st.selectbox(
            "Smoothing method",
            list(SMOOTHING_METHODS.keys()),
            index=1,
            help="Start with Centered moving average and a 3-age window for a clean presentation curve.",
        )
        smoothing_method = SMOOTHING_METHODS[smoothing_label]

        smoothing_window = st.slider(
            "Smoothing window size",
            min_value=2,
            max_value=9,
            value=3,
            step=1,
            disabled=smoothing_method in {"none", "exponential"},
            help="Number of age points used in moving-average smoothing.",
        )

        min_periods = st.slider(
            "Minimum points required",
            min_value=1,
            max_value=9,
            value=1,
            step=1,
            disabled=smoothing_method in {"none", "exponential"},
            help="Minimum number of available age points required to calculate a smoothed value.",
        )
        min_periods = min(min_periods, smoothing_window)

        smoothing_alpha = st.slider(
            "Exponential alpha",
            min_value=0.05,
            max_value=1.00,
            value=0.35,
            step=0.05,
            disabled=smoothing_method != "exponential",
            help="Higher alpha reacts faster; lower alpha creates a flatter line.",
        )

        show_raw_points = st.checkbox(
            "Show raw points behind smoothed line",
            value=True,
            help="Recommended. Keeps the smoothing auditable.",
        )
        show_line_markers = st.checkbox("Show line markers", value=True)
        show_data_labels = st.checkbox("Show point labels", value=False)
        use_smoothed_for_summary = st.checkbox(
            "Use smoothed values in summary metrics",
            value=True,
            help="When off, the summary table uses raw median repair % values.",
        )
        show_raw_table = st.checkbox("Show raw uploaded table", value=False)

    plot_df = clean_df[
        clean_df["category"].isin(selected_categories)
        & clean_df["age"].between(age_range[0], age_range[1])
    ].copy()

    if plot_df.empty:
        st.warning("No rows match the selected filters.")
        render_data_quality(clean_result)
        st.stop()

    plot_df = apply_smoothing(
        plot_df,
        method=smoothing_method,
        window=smoothing_window,
        min_periods=min_periods,
        alpha=smoothing_alpha,
    )

    value_col = "smoothed_median_repair_pct" if smoothing_method != "none" else "median_repair_pct"
    display_value_label = "Smoothed median repair %" if smoothing_method != "none" else "Raw median repair %"

    summary_value_col = value_col if use_smoothed_for_summary else "median_repair_pct"
    category_summary = build_category_summary(plot_df, value_col=summary_value_col)

    st.subheader("Dataset summary")
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    highest_row = plot_df.loc[plot_df[value_col].idxmax()]
    with kpi1:
        _safe_metric("Rows plotted", f"{len(plot_df):,}")
    with kpi2:
        _safe_metric("Categories", f"{plot_df['category'].nunique():,}")
    with kpi3:
        _safe_metric("Age range", f"{int(plot_df['age'].min())}–{int(plot_df['age'].max())}")
    with kpi4:
        _safe_metric(f"Peak {display_value_label.lower()}", _format_pct(float(highest_row[value_col])))
    with kpi5:
        _safe_metric("Peak category / age", f"{highest_row['category']} / {int(highest_row['age'])}")

    if smoothing_method != "none":
        st.info(
            f"Smoothing enabled: **{smoothing_label}**. "
            "The chart line uses smoothed values while raw uploaded points remain available for audit."
        )

    with st.expander("Smoothing documentation", expanded=False):
        st.markdown(SMOOTHING_DOC)

    render_data_quality(clean_result)

    st.subheader("Median repair % by vehicle age")

    chart_df = plot_df.sort_values(["category", "age"]).copy()

    fig = build_line_chart(
        plot_df=chart_df,
        value_col=value_col,
        smoothing_label=display_value_label,
        show_raw_points=show_raw_points,
        show_line_markers=show_line_markers,
        show_data_labels=show_data_labels,
    )

    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns([1.1, 1])

    with left:
        st.subheader("Trend summary by category")
        st.caption(
            f"Summary values are based on "
            f"{'smoothed' if use_smoothed_for_summary and smoothing_method != 'none' else 'raw'} median repair %."
        )
        display_summary = category_summary.copy()
        display_summary = display_summary.sort_values("change_pp", ascending=False)
        display_summary["first_value"] = display_summary["first_value"].map(_format_pct)
        display_summary["last_value"] = display_summary["last_value"].map(_format_pct)
        display_summary["peak_value"] = display_summary["peak_value"].map(_format_pct)
        display_summary["change_pp"] = display_summary["change_pp"].map(lambda x: f"{x:+.2f} pts")
        display_summary["avg_change_per_age"] = display_summary["avg_change_per_age"].map(lambda x: f"{x:+.2f} pts/age")

        display_summary = display_summary.rename(
            columns={
                "category": "Category",
                "points": "Points",
                "first_age": "First Age",
                "first_value": "First Median %",
                "last_age": "Last Age",
                "last_value": "Last Median %",
                "peak_age": "Peak Age",
                "peak_value": "Peak Median %",
                "change_pp": "Change",
                "avg_change_per_age": "Avg Change / Age",
            }
        )
        st.dataframe(display_summary, use_container_width=True, hide_index=True)

    with right:
        st.subheader("Change from first to latest age")
        change_df = category_summary.sort_values("change_pp", ascending=True).copy()

        fig_change = px.bar(
            change_df,
            x="change_pp",
            y="category",
            orientation="h",
            text=change_df["change_pp"].map(lambda x: f"{x:+.1f}"),
            labels={
                "change_pp": "Change in median repair % points",
                "category": "Health segment",
            },
            title="Median repair % point change across selected ages",
        )
        fig_change.update_layout(margin=dict(l=20, r=20, t=60, b=20))
        fig_change.update_xaxes(ticksuffix=" pts", zeroline=True)
        fig_change.update_yaxes(title=None)
        st.plotly_chart(fig_change, use_container_width=True)

    st.subheader("Small multiples")
    facet_df = chart_df.copy()
    facet_value_col = value_col
    fig_facet = px.line(
        facet_df,
        x="age",
        y=facet_value_col,
        color="category",
        facet_col="category",
        facet_col_wrap=2,
        markers=show_line_markers,
        labels={
            "age": "Vehicle age",
            facet_value_col: display_value_label,
            "category": "Health segment",
        },
        title="Separate repair-age curve by category",
    )
    fig_facet.update_yaxes(ticksuffix="%", rangemode="tozero")
    fig_facet.update_xaxes(dtick=1)
    fig_facet.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig_facet.update_layout(showlegend=False, margin=dict(l=20, r=20, t=70, b=20))
    st.plotly_chart(fig_facet, use_container_width=True)

    st.subheader("Age-category heatmap")
    heatmap_df = plot_df.pivot_table(
        index="category",
        columns="age",
        values=value_col,
        aggfunc="median",
    ).sort_index()

    fig_heat = px.imshow(
        heatmap_df,
        aspect="auto",
        text_auto=".1f",
        labels=dict(x="Vehicle age", y="Health segment", color=display_value_label),
        title=f"{display_value_label} heatmap",
    )
    fig_heat.update_layout(margin=dict(l=20, r=20, t=60, b=20))
    st.plotly_chart(fig_heat, use_container_width=True)

    st.subheader("Cleaned data")
    output_cols = ["category", "age", "median_repair_pct", "smoothed_median_repair_pct", "smoothing_method"]
    st.dataframe(
        plot_df.sort_values(["category", "age"])[output_cols],
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = plot_df.sort_values(["category", "age"])[output_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download cleaned plotted data",
        data=csv_bytes,
        file_name="cleaned_repair_age_plot_data.csv",
        mime="text/csv",
    )

    if show_raw_table:
        st.subheader(f"Raw uploaded table: {source_label}")
        st.dataframe(raw_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()

from __future__ import annotations

from io import BytesIO, StringIO

import pandas as pd
import plotly.express as px
import streamlit as st

from fleet_repair_age import (
    AGGREGATION_METHODS,
    AUTO_COLUMN_ALIASES,
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


def main() -> None:
    st.title("Fleet Repair % by Vehicle Age")
    st.caption(
        "Upload a CSV or Excel file with health segment/category, vehicle age, and median repair %. "
        "The app cleans percent formats, handles Excel percent values, filters categories, and plots category lines by age."
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

        show_markers = st.checkbox("Show markers", value=True)
        show_data_labels = st.checkbox("Show point labels", value=False)
        show_raw_table = st.checkbox("Show raw uploaded table", value=False)

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

    plot_df = clean_df[
        clean_df["category"].isin(selected_categories)
        & clean_df["age"].between(age_range[0], age_range[1])
    ].copy()

    if plot_df.empty:
        st.warning("No rows match the selected filters.")
        render_data_quality(clean_result)
        st.stop()

    category_summary = build_category_summary(plot_df)

    st.subheader("Dataset summary")
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    highest_row = plot_df.loc[plot_df["median_repair_pct"].idxmax()]
    with kpi1:
        _safe_metric("Rows plotted", f"{len(plot_df):,}")
    with kpi2:
        _safe_metric("Categories", f"{plot_df['category'].nunique():,}")
    with kpi3:
        _safe_metric("Age range", f"{int(plot_df['age'].min())}–{int(plot_df['age'].max())}")
    with kpi4:
        _safe_metric("Peak median repair %", _format_pct(float(highest_row["median_repair_pct"])))
    with kpi5:
        _safe_metric("Peak category / age", f"{highest_row['category']} / {int(highest_row['age'])}")

    render_data_quality(clean_result)

    st.subheader("Median repair % by vehicle age")

    chart_df = plot_df.sort_values(["category", "age"]).copy()
    chart_df["label"] = chart_df["median_repair_pct"].map(lambda x: f"{x:.1f}%")

    fig = px.line(
        chart_df,
        x="age",
        y="median_repair_pct",
        color="category",
        markers=show_markers,
        text="label" if show_data_labels else None,
        labels={
            "age": "Vehicle age",
            "median_repair_pct": "Median repair %",
            "category": "Health segment",
        },
        title="Median repair % by vehicle age and health segment",
    )
    fig.update_layout(
        hovermode="x unified",
        legend_title_text="Health segment",
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.update_yaxes(ticksuffix="%", rangemode="tozero")
    fig.update_xaxes(dtick=1)
    if show_data_labels:
        fig.update_traces(textposition="top center")

    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns([1.1, 1])

    with left:
        st.subheader("Trend summary by category")
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
    fig_facet = px.line(
        facet_df,
        x="age",
        y="median_repair_pct",
        color="category",
        facet_col="category",
        facet_col_wrap=2,
        markers=show_markers,
        labels={
            "age": "Vehicle age",
            "median_repair_pct": "Median repair %",
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
        values="median_repair_pct",
        aggfunc="median",
    ).sort_index()

    fig_heat = px.imshow(
        heatmap_df,
        aspect="auto",
        text_auto=".1f",
        labels=dict(x="Vehicle age", y="Health segment", color="Median repair %"),
        title="Median repair % heatmap",
    )
    fig_heat.update_layout(margin=dict(l=20, r=20, t=60, b=20))
    st.plotly_chart(fig_heat, use_container_width=True)

    st.subheader("Cleaned data")
    st.dataframe(
        plot_df.sort_values(["category", "age"]),
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = plot_df.sort_values(["category", "age"]).to_csv(index=False).encode("utf-8")
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

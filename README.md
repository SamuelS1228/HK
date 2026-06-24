# Fleet Repair % by Vehicle Age — Streamlit App

Interactive Streamlit dashboard for plotting median repair percentage by vehicle age for each fleet health segment/category.

## What it does

- Uploads CSV, XLSX, or XLS files.
- Auto-detects common column names:
  - `Health Segments`, `Health Segment`, `Segment`, `Category`
  - `Age`, `Vehicle Age`, `Asset Age`
  - `Median`, `Median Repair %`, `Repair %`
- Handles percent formats correctly:
  - `1.45%` -> `1.45`
  - Excel numeric percent `0.0145` -> `1.45`
  - Numeric `1.45` -> `1.45`
- Plots:
  - Multi-line repair-age curve by category
  - Category trend summary
  - Change from first to latest age
  - Small-multiple category curves
  - Age-category heatmap
- Filters:
  - Category selection
  - Age range
  - Category exclusion, e.g. `Exclude`
- Exports cleaned plotted data.

## Expected input format

Minimum required columns:

| Health Segments | Age | Median |
|---|---:|---:|
| Service / Light Fleet | 0 | 4.20% |
| Cleaning and Servicing Fleet | 0 | 0.81% |
| Inspection/Specialty | 0 | 0.41% |
| Trailers | 0 | 11.47% |

Column names can vary because the app has a manual column-mapping sidebar.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Test helper logic

```bash
python -m unittest discover -s tests
```

## Streamlit Community Cloud

Put these files in the repo root:

```text
app.py
fleet_repair_age.py
requirements.txt
sample_repair_age.csv
.streamlit/config.toml
```

The app uses `st.file_uploader`, so large files are governed by Streamlit's upload-size setting. The included config sets the limit to 200 MB.

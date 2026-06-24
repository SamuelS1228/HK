# Fleet Repair % by Vehicle Age — Streamlit App

Interactive Streamlit dashboard for plotting median repair percentage by vehicle age for each fleet health segment/category.

## Files required in the repo

```text
app.py
fleet_repair_age.py
requirements.txt
.streamlit/config.toml
```

`sample_repair_age.csv` is not required. The app has embedded fallback sample data, so it will not crash when no upload has been provided.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Test

```bash
python -m unittest discover -s tests
```

## Input columns

Minimum required fields:

| Health Segments | Age | Median |
|---|---:|---:|
| Service / Light Fleet | 0 | 4.20% |
| Cleaning and Servicing Fleet | 0 | 0.81% |
| Inspection/Specialty | 0 | 0.41% |
| Trailers | 0 | 11.47% |

The app lets you manually map columns if your uploaded file uses different names.

# Fleet Repair % by Vehicle Age — Streamlit App

Interactive Streamlit dashboard for plotting median repair percentage by vehicle age for each fleet health segment/category.

## Files required in the repo

```text
app.py
fleet_repair_age.py
requirements.txt
.streamlit/config.toml
```

The app has embedded fallback sample data, so it will not crash when no upload has been provided.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Test

```bash
python -m unittest discover -s tests
```

## Expected input columns

Minimum required fields:

| Health Segments | Age | Median |
|---|---:|---:|
| Service / Light Fleet | 0 | 4.20% |
| Cleaning and Servicing Fleet | 0 | 0.81% |
| Inspection/Specialty | 0 | 0.41% |
| Trailers | 0 | 11.47% |

The app lets you manually map columns if your uploaded file uses different names.

## Smoothing documentation

### What smoothing does

Smoothing creates a second value called `smoothed_median_repair_pct` for each category-age point.

It does **not** overwrite the uploaded/raw value, which remains available as `median_repair_pct`.

Use smoothing when the raw age curve is noisy because each age/category point has limited repair history. The goal is to reveal the underlying shape of repair cost intensity as assets age.

### Available smoothing methods

#### None

No smoothing. The chart line uses the raw median repair percentage.

#### Centered moving average

For each age, averages nearby age points within the selected window.

Example with window size 3:

| Age being smoothed | Values used |
|---:|---|
| 2 | Ages 1, 2, and 3 |

This is usually the best presentation view because it reduces noise while keeping the curve centered on the age being shown.

#### Trailing moving average

For each age, averages the current age and prior ages.

Example with window size 3:

| Age being smoothed | Values used |
|---:|---|
| 3 | Ages 1, 2, and 3 |

This is more conservative than centered smoothing because it does not use later ages to smooth earlier ages.

#### Weighted moving average

Uses a trailing window but gives newer age points more weight.

Example with window size 3:

| Age | Weight |
|---:|---:|
| Oldest point | 1 |
| Middle point | 2 |
| Newest point | 3 |

This reacts faster than a simple trailing moving average.

#### Exponential smoothing

Applies a recursive formula:

```text
smoothed_t = alpha * raw_t + (1 - alpha) * smoothed_(t-1)
```

Higher alpha reacts faster to changes. Lower alpha creates a flatter, more stable curve.

### Minimum points required

`Minimum points required` controls whether a smoothed value is calculated when the full smoothing window is not available.

Example:

- Window size = 3
- Minimum points = 1

At the first age point, the app can still calculate a smoothed value using one available point.

If minimum points = 3, the first two points in a trailing moving average would be blank until three points are available.

### Recommended starting setting

For this fleet repair-age use case:

```text
Smoothing method: Centered moving average
Window size: 3
Minimum points required: 1
Show raw points: On
```

This gives a readable curve and keeps the uploaded values visible for auditability.

### Important interpretation rules

- Smoothing is calculated separately for each category.
- Categories never borrow values from other categories.
- Raw values are still exported.
- Smoothed values are exported as a separate column.
- The summary table can be switched between raw and smoothed values.
- Smoothing should help explain the curve; it should not be used to hide outliers without explanation.

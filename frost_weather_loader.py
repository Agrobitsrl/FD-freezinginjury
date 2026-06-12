"""
FROST INJURY — WEATHER LOADER  v1.0
Agrobit srl

Reads daily weather data from one of three sources:
  - CSV file               (delimiter auto-detected)
  - Excel file             (.xlsx / .xls — first sheet)
  - pandas DataFrame       (passed programmatically, e.g. from a mobile-API JSON)

Required columns (renamable via config.WEATHER_COLUMNS):
  date, temp_max, temp_min
Optional columns:
  humidity, rainfall, is_forecast

The loader normalises column names, parses dates, sorts chronologically and
interpolates missing temperatures (linear, ≤3-day gap).
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Union
import pandas as pd
from config import WEATHER_COLUMNS, DATE_FORMAT


# HELPERS
def _detect_date_format(series: pd.Series) -> str:
    """Auto-detect date format from sample non-null value."""
    sample = str(series.dropna().iloc[0])
    if re.match(r"^\d{4}-\d{2}-\d{2}", sample): return "%Y-%m-%d"
    if re.match(r"^\d{2}-\d{2}-\d{4}", sample): return "%d-%m-%Y"
    if re.match(r"^\d{2}/\d{2}/\d{4}", sample): return "%d/%m/%Y"
    if re.match(r"^\d{4}/\d{2}/\d{2}", sample): return "%Y/%m/%d"
    return "%Y-%m-%d"


def _read_any(path: Path) -> pd.DataFrame:
    """Dispatch to the correct pandas reader based on extension."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        # Sniff delimiter (',' vs ';')
        with open(path, "r", encoding="utf-8") as fh:
            head = fh.readline()
        sep = ";" if head.count(";") > head.count(",") else ","
        return pd.read_csv(path, sep=sep)
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(path)
    if suffix == ".xls":
        return pd.read_excel(path, engine="xlrd")
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported weather file format: {suffix}")


# Public API
def load_weather(
    source: Union[str, Path, pd.DataFrame],
) -> pd.DataFrame:
    """
    Load and normalise daily weather data.

    Parameters
    ----------
    source : path-like
        A path to a CSV/XLSX/JSON file.

    Returns
    -------
    DataFrame with columns:
        date (datetime64[ns]), temp_max (float), temp_min (float),
        humidity (float, may be NaN), rainfall (float, may be NaN),
        is_forecast (bool, default False)
    Sorted chronologically, no duplicates, gaps interpolated.
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = _read_any(Path(source))

    # Column name normalisation
    rev_map = {v: k for k, v in WEATHER_COLUMNS.items()}
    df = df.rename(columns=rev_map)

    required = {"date", "temp_max", "temp_min"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required column(s) {missing} in weather data. "
            f"Available: {list(df.columns)}"
        )

    # Date parsing
    fmt = DATE_FORMAT if DATE_FORMAT != "auto" else _detect_date_format(df["date"])
    df["date"] = pd.to_datetime(df["date"], format=fmt, dayfirst=True, errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    df = df.drop_duplicates(subset=["date"]).reset_index(drop=True)

    # Optional columns
    if "humidity"    not in df.columns: df["humidity"]    = pd.NA
    if "rainfall"    not in df.columns: df["rainfall"]    = 0.0
    if "is_forecast" not in df.columns: df["is_forecast"] = False

    # Type coercion
    df["temp_max"] = pd.to_numeric(df["temp_max"], errors="coerce")
    df["temp_min"] = pd.to_numeric(df["temp_min"], errors="coerce")
    df["humidity"] = pd.to_numeric(df["humidity"], errors="coerce")
    df["rainfall"] = pd.to_numeric(df["rainfall"], errors="coerce").fillna(0.0)
    df["is_forecast"] = df["is_forecast"].astype(bool)

    # Gap filling for temperature
    df["temp_max"] = df["temp_max"].interpolate(method="linear", limit=3)
    df["temp_min"] = df["temp_min"].interpolate(method="linear", limit=3)

    # Final sanity check
    if df["temp_min"].isna().any() or df["temp_max"].isna().any():
        n = df["temp_min"].isna().sum() + df["temp_max"].isna().sum()
        raise ValueError(
            f"{n} rows still have NaN temperatures after interpolation — "
            "input data has gaps longer than 3 days."
        )

    return df[["date", "temp_max", "temp_min", "humidity",
               "rainfall", "is_forecast"]]


def split_observed_forecast(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split the weather dataframe into observed and forecast parts.

    Forecast rows are those flagged via is_forecast=True. If no such flag is
    set, all rows are considered observed.
    """
    obs = df[~df["is_forecast"]].reset_index(drop=True)
    fct = df[ df["is_forecast"]].reset_index(drop=True)
    return obs, fct

"""
FROST INJURY MODEL — CORE ENGINE  v1.0
Agrobit srl

Pipeline
--------
1.  load_frost_rules()         → parse frost_bbch_gdd.json
2.  compute_gdd()              → add gdd_daily, gdd_cum, season_year to weather df
3.  find_active_stage()        → for a given crop and GDD value, return the BBCH
                                 stage whose phenology_window_gdd contains it
4.  classify_frost_risk()      → compare T_min with the stage's warning/critical
                                 thresholds → severity ∈ {0,1,2,3}
5.  run_frost_alerts()         → run the full pipeline for one or many crops

GDD convention
--------------
    GDD_daily = max(0, (Tmax + Tmin)/2 − Tbase)
    GDD_cum   = season-cumulative; resets on config.GDD_RESET_MONTH (1 = Jan NH, 7 = Jul SH).
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Union
import numpy as np
import pandas as pd
from config import (
    RULES_JSON, GDD_BASE_C, GDD_RESET_MONTH,
    WATCH_BUFFER_C, SEVERITY_LABELS, RECOMMENDED_ACTIONS,
    STAGE_MATCHING_POLICY,
)


# RULE LOADING
def load_frost_rules(path: Union[str, Path] = RULES_JSON) -> dict:
    """
    Parse frost_bbch_gdd.json and return the dictionary, stripped of _metadata.
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if k != "_metadata"}


def available_crops(rules: dict) -> list[str]:
    return sorted(rules.keys())


# GDD COMPUTATION
def _season_year(date: pd.Timestamp, reset_month: int = GDD_RESET_MONTH) -> int:
    """Year-bucket used to cumulate GDD, so the counter resets on reset_month."""
    return date.year if date.month >= reset_month else date.year - 1


def compute_gdd(
    weather_df: pd.DataFrame,
    t_base: float = GDD_BASE_C,
    reset_month: int = GDD_RESET_MONTH,
) -> pd.DataFrame:
    """
    Add columns: temp_avg, gdd_daily, season_year, gdd_cum  to weather_df.
    """
    df = weather_df.copy()
    df["temp_avg"]    = (df["temp_max"] + df["temp_min"]) / 2.0
    df["gdd_daily"]   = np.maximum(0.0, df["temp_avg"] - t_base)
    df["season_year"] = df["date"].apply(lambda d: _season_year(d, reset_month))
    df["gdd_cum"]     = df.groupby("season_year")["gdd_daily"].cumsum()
    return df


# STAGE LOOKUP
def find_active_stage(
    gdd_cum: float,
    stages: list[dict],
    policy: str = STAGE_MATCHING_POLICY,
) -> Optional[dict]:
    """
    Return the BBCH stage active at the given cumulative GDD, or None.
    """
    matches = [s for s in stages if s["gdd_lo"] <= gdd_cum <= s["gdd_hi"]]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    if policy == "most_conservative":
        return max(matches, key=lambda s: s["warning_threshold_C"])
    if policy == "narrowest":
        return min(matches, key=lambda s: s["gdd_hi"] - s["gdd_lo"])
    return matches[0]   # "first_match"


# RISK CLASSIFICATION
def classify_frost_risk(
    t_min: float,
    stage: Optional[dict],
    watch_buffer: float = WATCH_BUFFER_C,
) -> dict:
    """
    Compare T_min against the stage's warning and critical thresholds.
    If stage is None (GDD outside any defined window) → "Out of season".
    """
    if stage is None:
        return {
            "severity":           -1,
            "risk_class":         "Out of season",
            "warning_threshold":  None,
            "critical_threshold": None,
            "margin_C":           None,
            "action":             RECOMMENDED_ACTIONS["Out of season"],
        }

    warn = stage["warning_threshold_C"]
    crit = stage["critical_threshold_C"]

    if t_min <= crit:
        sev = 3
    elif t_min <= warn:
        sev = 2
    elif t_min <= warn + watch_buffer:
        sev = 1
    else:
        sev = 0

    risk_class = SEVERITY_LABELS[sev]
    return {
        "severity":           sev,
        "risk_class":         risk_class,
        "warning_threshold":  warn,
        "critical_threshold": crit,
        "margin_C":           round(t_min - warn, 2),   # negative = past warning
        "action":             RECOMMENDED_ACTIONS[risk_class],
    }


# MAIN PIPELINE
def run_frost_alerts(
    weather_df: pd.DataFrame,
    rules:      dict,
    crops:      Optional[list[str]] = None,
    t_base:     float = GDD_BASE_C,
) -> pd.DataFrame:
    """
    Run the full frost-alert pipeline.
    """
    if crops is None:
        crops = available_crops(rules)

    weather_gdd = compute_gdd(weather_df, t_base=t_base)

    rows = []
    for crop in crops:
        if crop not in rules:
            raise KeyError(f"Crop '{crop}' not found in rules. "
                           f"Available: {available_crops(rules)}")
        stages = rules[crop]["stages"]

        for _, w in weather_gdd.iterrows():
            stage = find_active_stage(w["gdd_cum"], stages)
            risk  = classify_frost_risk(w["temp_min"], stage)

            rows.append({
                "date":              w["date"].date().isoformat(),
                "crop":              crop,
                "temp_max":          round(float(w["temp_max"]), 2),
                "temp_min":          round(float(w["temp_min"]), 2),
                "temp_avg":          round(float(w["temp_avg"]), 2),
                "gdd_daily":         round(float(w["gdd_daily"]), 2),
                "gdd_cum":           round(float(w["gdd_cum"]), 2),
                "is_forecast":       bool(w["is_forecast"]),
                "bbch_range":        stage["bbch_range"]         if stage else None,
                "phenological_phase":stage["phenological_phase"] if stage else None,
                "frost_type":        stage.get("frost_type")     if stage else None,
                "evidence_level":    stage.get("evidence_level") if stage else None,
                "warning_threshold_C":  risk["warning_threshold"],
                "critical_threshold_C": risk["critical_threshold"],
                "severity":          risk["severity"],
                "risk_class":        risk["risk_class"],
                "margin_C":          risk["margin_C"],
                "action":            risk["action"],
            })

    return pd.DataFrame(rows)


# ALERT FILTERING
def filter_alerts(df: pd.DataFrame, min_severity: int = 1) -> pd.DataFrame:
    """Return only rows where severity >= min_severity (1=Watch, 2=Warning, 3=Critical)."""
    return df[df["severity"] >= min_severity].reset_index(drop=True)


# CONVERSION TO PUSH PAYLOADS
def to_push_payloads(df: pd.DataFrame) -> list[dict]:
    """
    Build a slim JSON payload list suitable for FCM/APNS push notifications.
    Includes only rows with severity ≥ 1.
    """
    alerts = filter_alerts(df, min_severity=1)
    payloads = []
    for _, r in alerts.iterrows():
        payloads.append({
            "crop":       r["crop"],
            "date":       r["date"],
            "is_forecast":bool(r["is_forecast"]),
            "bbch":       r["bbch_range"],
            "severity":   int(r["severity"]),
            "risk":       r["risk_class"],
            "t_min":      r["temp_min"],
            "warn":       r["warning_threshold_C"],
            "crit":       r["critical_threshold_C"],
            "msg":        r["action"],
        })
    return payloads

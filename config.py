"""
FROST INJURY MODEL — CONFIGURATION  v1.0
Agrobit srl

All user-editable settings live here.
"""


from pathlib import Path

# PATHS
BASE_DIR        = Path(__file__).resolve().parent
RULES_JSON      = BASE_DIR / "frost_bbch_gdd.json"     # from BBCH to GDD mapping + thresholds
OUTPUT_DIR      = BASE_DIR / "output"
DEFAULT_WEATHER = BASE_DIR / "weather_data.xlsx"       # change at runtime via --weather

# WEATHER DATA
WEATHER_COLUMNS = {
    "date":         "date",         # ISO 8601 preferred, multiple formats accepted
    "temp_max":     "temp_max",     # °C
    "temp_min":     "temp_min",     # °C
    "humidity":     "humidity",     # % RH
    "rainfall":     "rainfall",     # mm
    "is_forecast":  "is_forecast",  # bool — True if row is forecast
}

# Date parsing: "auto" or one of {"%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"}
DATE_FORMAT = "auto"

# GROWING-DEGREE-DAYS PARAMETERS
# Base temperature for host phenology
GDD_BASE_C       = 5.0          # °C
GDD_RESET_MONTH  = 1            # 1 = Jan (NH), 7 = Jul (SH)
GDD_METHOD       = "average"    # "average" | "single_sine"  (average = simple)

# FROST ALERT SEVERITY MAPPING
# Severity is derived from comparing T_min with the stage-specific thresholds read from frost_bbch_gdd.json. 
WATCH_BUFFER_C   = 1.5
SEVERITY_LABELS  = {
    0: "Safe",            #   t_min > warning + WATCH_BUFFER_C
    1: "Watch",           #   warning < t_min ≤ warning + WATCH_BUFFER_C
    2: "Warning",         #   critical < t_min ≤ warning
    3: "Critical",        #   t_min ≤ critical
}
SEVERITY_COLORS  = {
    "Safe":         "#2E7D32",
    "Watch":        "#FBC02D",
    "Warning":      "#F57C00",
    "Critical":     "#C62828",
    "Out of season":"#90A4AE",
}
RECOMMENDED_ACTIONS = {
    "Safe":     "No action required. Continue routine monitoring.",
    "Watch":    "Verify weather forecast for the next 24 h. Prepare protection equipment.",
    "Warning":  "Activate frost protection (wind machines, sprinklers, heaters). Operational lead time ≈ 2-4 h.",
    "Critical": "Maximum protection NOW. All active systems must be ON. Document damage post-event.",
    "Out of season": "No phenological exposure (GDD outside any defined BBCH window).",
}

# STAGE-MATCHING POLICY when more than one BBCH range matches the current GDD
STAGE_MATCHING_POLICY = "most_conservative"

# OUTPUT
CSV_OUTPUT      = "frost_alerts.csv"
JSON_OUTPUT     = "frost_alerts.json"
JSON_INDENT     = 2

# Filter the output to alerting rows only?  (Safe rows make the file noisy;
# alert-only mode produces a slim, push-notification-ready payload)
JSON_ALERTS_ONLY = False

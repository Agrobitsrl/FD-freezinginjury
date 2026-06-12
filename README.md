# Frost Injury Alert Model (FDM-frostmodel)

Standalone Python module to generate frost-risk alerts for **19 perennial crops**, based on:
- BBCH-stage-specific critical temperatures (`frost_bbch_gdd.json`)
- Growing Degree Days accumulation (base 5 °C, NH default)
- Observed + forecast daily weather

Schema-compatible with the Agrobit PDM Fuzzy Risk Model v2.0.

Developed within the **SmartCherry** sub-innovation project (SIP10, code RZTHQ) funded by the OpenAgri
Open Call under the European Union's Horizon Europe research and innovation programme,
Grant Agreement No. 101134083.

---

## Files

| File | Role |
|---|---|
| `config.py`                  | Paths, GDD base, severity thresholds, output format |
| `frost_bbch_gdd.json`        | BBCH ↔ GDD mapping with warning/critical thresholds (19 crops, 95 stages) |
| `frost_weather_loader.py`    | Load CSV / XLSX / JSON / DataFrame; auto-normalise schema; split observed/forecast |
| `frost_model.py`             | Core engine: GDD compute, BBCH stage finder, risk classifier |
| `frost_chart.py`             | Per-crop frost charts |
| `main.py`                    | CLI entry point |
| `weather_data.xlsx`          | Sample weather dataset (default input) |
| `output/`                    | Generated CSV / JSON outputs and per-crop charts (re-created on each run) |

---

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## Quick start

```bash
# All crops on the bundled sample data
python main.py --all

# Single crop
python main.py --crop Apple

# Multiple crops, custom weather source, alert-only output
python main.py --crop Apple Vineyard Olive \
               --weather mydata.csv \
               --alerts-only

# Push-payload mode for mobile backend (only severity >= 1)
python main.py --all --push
```

---

## Weather input format

CSV / XLSX / JSON with at minimum:

| Column | Type | Required | Notes |
|---|---|---|---|
| `date`        | date    | ✓ | ISO 8601 preferred; multiple formats auto-detected |
| `temp_max`    | float   | ✓ | °C |
| `temp_min`    | float   | ✓ | °C |
| `humidity`    | float   |   | % RH |
| `rainfall`    | float   |   | mm |
| `is_forecast` | bool    |   | `true` for forecast rows |

Gaps up to 3 days are interpolated linearly.

---

## How the alert level is decided

For each (crop, day) the engine:

1. **Cumulates GDD** since season start (`GDD_RESET_MONTH`, default 1 Jan).
2. **Locates the active BBCH stage** by matching `gdd_cum` against the JSON `phenology_window_gdd`.
3. **Compares T_min** with the stage's `warning_threshold_C` and `critical_threshold_C`:

| T_min vs thresholds | Severity | Label | Action |
|---|---|---|---|
| T_min ≤ critical | 3 | **Critical** | Maximum protection NOW |
| critical < T_min ≤ warning | 2 | **Warning** | Activate frost protection |
| warning < T_min ≤ warning + 1.5 °C | 1 | **Watch** | Verify forecast, prepare equipment |
| T_min > warning + 1.5 °C | 0 | **Safe** | No action |
| No active BBCH stage | -1 | **Out of season** | No phenological exposure |

The 1.5 °C buffer is configurable in `config.WATCH_BUFFER_C`.

---

## Output

`output/frost_alerts.csv` — one row per (crop, day):

```
date, crop, temp_max, temp_min, temp_avg, gdd_daily, gdd_cum, is_forecast,
bbch_range, phenological_phase, frost_type, evidence_level,
warning_threshold_C, critical_threshold_C, severity, risk_class, margin_C, action
```

`output/frost_alerts.json` — same data in JSON. With `--push`, a compact payload:

```json
[
  {
    "crop": "Apple",
    "date": "2026-04-08",
    "is_forecast": false,
    "bbch": "57-61",
    "severity": 2,
    "risk": "Warning",
    "t_min": -2.8,
    "warn": -2.0,
    "crit": -3.9,
    "msg": "Activate frost protection (wind machines, sprinklers, heaters). Operational lead time ≈ 2-4 h."
  }
]
```

---

## Programmatic API

```python
from frost_weather_loader import load_weather
from frost_model import load_frost_rules, run_frost_alerts

weather = load_weather("mydata.csv")
rules   = load_frost_rules()
alerts  = run_frost_alerts(weather, rules, crops=["Apple", "Vineyard"])
```

Other public helpers: `frost_weather_loader.split_observed_forecast`, and
`frost_model.available_crops`, `frost_model.filter_alerts`, `frost_model.to_push_payloads`.

---

## Integration with the PDM Fuzzy Risk Model

`frost_bbch_gdd.json` is schema-compatible with `PDM-fuzzymodel/pest.json`:

- `phenology_window_gdd: [lo, hi]` identical name and units
- `pheno_t_base_C = 5.0` matches `PDM-fuzzymodel/config.PHENOLOGY_T_BASE`
- Each stage can be loaded as a virtual abiotic "FrostInjury" pest

This enables the same `weather_data.xlsx` to drive both the biotic (pest/disease) and abiotic (frost) risk pipelines without data duplication.

---

## Scientific basis

Critical temperatures are drawn from peer-reviewed sources:

- Snyder & Melo-Abreu (2005) — *Frost Protection: fundamentals, practice and economics* — FAO Env. Nat. Res. 10
- Proebsting & Mills (1978) — *J. Am. Soc. Hortic. Sci.* 103(2):192-198
- Rodrigo (2000) — *Sci. Hortic.* 85(3):155-173 — doi:10.1016/S0304-4238(99)00150-8
- Sakai & Larcher (1987) — *Frost Survival of Plants* — Springer
- Meier (2018) — *BBCH Monograph* — JKI — doi:10.5073/20180906-074619
- Trought, Howell & Cherry (1999) — Lincoln Univ. NZ
- Barranco et al. (2005) — *HortScience* 40(3):558-560
- Yelenosky (1985) — *Hort. Reviews* 7:201-238

GDD calibration anchors are taken from the existing `pest.json` of PDM-fuzzymodel to ensure phenological consistency.

---

## Operational caveats

- Thresholds are literature consensus; **local calibration on cultivar-specific data and microclimate is required** before deploying in a commercial DSS.
- A radiative frost is reduced by canopy moisture, wind, and inversion strength — these dynamics are NOT modelled here. The output is a *threshold-based* alert, not a probabilistic damage forecast.
- Tropical crops carry full-year windows `[0, 9999]`: the alert fires whenever T_min crosses the threshold, regardless of GDD.

---

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). Copyright 2026 Agrobit S.r.l.

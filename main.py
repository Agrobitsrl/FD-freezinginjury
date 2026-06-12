"""
FROST INJURY MODEL — CLI ENTRY POINT  v1.0
Agrobit srl

Usage
-----
  python main.py                                   # interactive crop selection on default sample weather
  python main.py --crop Apple                      # single crop
  python main.py --crop Apple Vineyard Olive       # multiple crops
  python main.py --all                             # all 19 crops
  python main.py --weather path/to/weather.csv     # override weather source
  python main.py --alerts-only                     # output only severity ≥ 1 rows
  python main.py --push                            # produce mobile push-payload JSON
  python main.py --quiet                           # suppress per-row terminal output
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
import pandas as pd
from config import (
    RULES_JSON, DEFAULT_WEATHER, OUTPUT_DIR,
    CSV_OUTPUT, JSON_OUTPUT, JSON_INDENT, JSON_ALERTS_ONLY,
    SEVERITY_COLORS,
)
from frost_weather_loader import load_weather, split_observed_forecast
from frost_model import (
    load_frost_rules, available_crops, run_frost_alerts,
    filter_alerts, to_push_payloads,
)


# HELPERS
def _select_crops_interactive(available: list[str]) -> list[str]:
    print("\nAvailable crops:\n")
    for i, c in enumerate(available, 1):
        print(f"  {i:>2}.  {c}")
    print("\n   A.   All crops\n")
    while True:
        raw = input("Select numbers separated by commas (e.g. 1,3,5) or A: ").strip()
        if raw.upper() == "A":
            return available
        try:
            idx = [int(x.strip()) for x in raw.split(",")]
            sel = [available[i - 1] for i in idx if 1 <= i <= len(available)]
            if sel:
                return sel
        except (ValueError, IndexError):
            pass
        print("  Invalid input — try again.\n")


def _print_summary(df: pd.DataFrame) -> None:
    print("\n" + "=" * 72)
    print("  FROST ALERT SUMMARY")
    print("=" * 72)
    header = f"  {'Crop':<14} {'Records':>8} {'Crit':>6} {'Warn':>6} {'Watch':>6} {'OoS':>6}"
    print(header)
    print("  " + "-" * 68)
    for crop, grp in df.groupby("crop"):
        n   = len(grp)
        n_c = (grp["risk_class"] == "Critical").sum()
        n_w = (grp["risk_class"] == "Warning").sum()
        n_a = (grp["risk_class"] == "Watch").sum()
        n_o = (grp["risk_class"] == "Out of season").sum()
        print(f"  {crop:<14} {n:>8} {n_c:>6} {n_w:>6} {n_a:>6} {n_o:>6}")
    print("=" * 72)


# MAIN
def main() -> None:
    p = argparse.ArgumentParser(
        description="Agrobit — Frost Injury Alert Model  v1.0"
    )
    p.add_argument("--crop",   nargs="+", metavar="CROP",
                   help="One or more crop names to analyse")
    p.add_argument("--all",    action="store_true",
                   help="Analyse all available crops")
    p.add_argument("--weather", type=Path, default=DEFAULT_WEATHER,
                   help=f"Weather source (CSV/XLSX/JSON). Default: {DEFAULT_WEATHER}")
    p.add_argument("--rules",  type=Path, default=RULES_JSON,
                   help=f"BBCH→GDD rules JSON. Default: {RULES_JSON}")
    p.add_argument("--out",    type=Path, default=OUTPUT_DIR,
                   help=f"Output directory. Default: {OUTPUT_DIR}")
    p.add_argument("--alerts-only", action="store_true",
                   help="Filter output to severity ≥ 1 (Watch/Warning/Critical)")
    p.add_argument("--push",   action="store_true",
                   help="Emit a compact push-notification payload JSON")
    p.add_argument("--quiet",  action="store_true",
                   help="Suppress summary output")
    args = p.parse_args()

    print("\n" + "=" * 60)
    print("  Agrobit — Frost Injury Alert Model  v1.0")
    print("=" * 60)

    # Load rules
    try:
        rules = load_frost_rules(args.rules)
    except FileNotFoundError:
        print(f"\n  ERROR: rules file not found: {args.rules}")
        sys.exit(1)
    print(f"  Rules:    {len(rules)} crops loaded from {args.rules.name}")

    # Load weather
    try:
        weather = load_weather(args.weather)
    except FileNotFoundError:
        print(f"\n  ERROR: weather file not found: {args.weather}")
        sys.exit(1)
    except ValueError as e:
        print(f"\n  ERROR loading weather: {e}")
        sys.exit(1)

    obs, fct = split_observed_forecast(weather)
    print(f"  Weather:  {weather['date'].min().date()} → {weather['date'].max().date()}  "
          f"({len(weather)} days; observed={len(obs)}, forecast={len(fct)})")

    # Crop selection
    available = available_crops(rules)
    if args.all:
        selected = available
    elif args.crop:
        selected = []
        for c in args.crop:
            match = next((a for a in available if a.lower() == c.lower()), None)
            if match:
                selected.append(match)
            else:
                close = [a for a in available if c.lower() in a.lower()]
                hint  = f" Did you mean: {', '.join(close)}?" if close else ""
                print(f"  ERROR: crop '{c}' not recognised.{hint}")
                sys.exit(1)
    else:
        selected = _select_crops_interactive(available)

    print(f"\n  Crops:    {', '.join(selected)}\n")

    # Run model
    print("Running frost-alert model...")
    t0 = time.time()
    results = run_frost_alerts(weather, rules, crops=selected)
    print(f"  Done in {time.time()-t0:.2f}s — {len(results):,} (crop, day) records")

    # Output
    args.out.mkdir(parents=True, exist_ok=True)
    csv_path  = args.out / CSV_OUTPUT
    json_path = args.out / JSON_OUTPUT

    out_df = filter_alerts(results, min_severity=1) if args.alerts_only else results
    out_df.to_csv(csv_path, index=False)
    print(f"  CSV  → {csv_path}  ({len(out_df)} rows)")

    if args.push:
        payloads = to_push_payloads(results)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payloads, f, indent=JSON_INDENT, ensure_ascii=False)
        print(f"  PUSH → {json_path}  ({len(payloads)} alerts)")
    else:
        # Full JSON dump (or alert-only depending on config / CLI flag)
        records = out_df.to_dict(orient="records") if not JSON_ALERTS_ONLY \
                  else filter_alerts(results, min_severity=1).to_dict(orient="records")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=JSON_INDENT, ensure_ascii=False, default=str)
        print(f"  JSON → {json_path}  ({len(records)} rows)")

    # Summary
    if not args.quiet:
        _print_summary(results)
        crit = filter_alerts(results, min_severity=3)
        if not crit.empty:
            print("\n  Critical events:")
            for _, r in crit.head(10).iterrows():
                tag = "(forecast)" if r["is_forecast"] else "(observed)"
                print(f"   • {r['date']}  {r['crop']:<12} {tag}  "
                      f"T_min={r['temp_min']:>5}°C  "
                      f"BBCH={r['bbch_range']:<8}  "
                      f"≤{r['critical_threshold_C']}°C  → {r['risk_class']}")


if __name__ == "__main__":
    main()

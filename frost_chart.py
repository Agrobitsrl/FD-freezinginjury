"""
FROST INJURY MODEL — CHART GENERATOR  v1.0
Agrobit srl

Usage
-----
  python frost_chart.py                                             # select crop interactively on default sample weather
  python frost_chart.py --crop Apple                                # specific crop
  python frost_chart.py --crop Apple Vineyard Olive
  python frost_chart.py --all                                       # all crops
  python frost_chart.py --crop Apple --location "Lari, Toscana"
  python frost_chart.py --weather altro_file.xlsx --crop Cherry
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates  as mdates
from matplotlib.lines import Line2D
import numpy  as np
import pandas as pd
from config               import RULES_JSON, OUTPUT_DIR
from frost_weather_loader import load_weather
from frost_model          import load_frost_rules, available_crops, run_frost_alerts


# PATHS
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

WEATHER_FILE = BASE_DIR / "weather_data.xlsx"

# RISK PALETTE
RISK_BG = {
    "Safe":           "#C8E6C9",
    "Watch":          "#FFF176",
    "Warning":        "#FFAB40",
    "Critical":       "#EF5350",
    "Out of season":  "#ECEFF1",
}
RISK_BG_ALPHA = {
    "Safe":           0.35,
    "Watch":          0.55,
    "Warning":        0.65,
    "Critical":       0.70,
    "Out of season":  0.25,
}
RISK_DOT = {
    "Watch":    "#F9A825",
    "Warning":  "#E65100",
    "Critical": "#B71C1C",
}
RISK_IT = {
    "Safe":          "Sicuro",
    "Watch":         "Rischio Basso",
    "Warning":       "Rischio Medio",
    "Critical":      "Rischio Alto",
    "Out of season": "Fuori stagione",
}


# INTERACTIVE SELECTION OF CROPS
def _select_crops_interactive(available: list[str]) -> list[str]:
    print("\nAvailable crops:\n")
    for i, c in enumerate(available, 1):
        print(f"  {i:>2}.  {c}")
    print("\n   A.   All crops \n")
    while True:
        raw = input("Select comma-separated number/s (e.g. 1,3) or A: ").strip()
        if raw.upper() == "A":
            return available
        try:
            idx = [int(x.strip()) for x in raw.split(",")]
            sel = [available[i - 1] for i in idx if 1 <= i <= len(available)]
            if sel:
                return sel
        except (ValueError, IndexError):
            pass
        print("  Invalid input — please try again.\n")


# CHARTS
def plot_frost_chart(
    df:          pd.DataFrame,
    crop:        str,
    output_path: Path,
    location:    str = "Lari (Toscana)",
) -> None:
    """
    Generates and saves the frost risk chart for a single crop.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(20, 7))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#FCFCFC")

    rc_prev = None
    x0_band = None
    for _, row in df.iterrows():
        rc = row["risk_class"]
        d  = row["date"]
        if rc != rc_prev:
            if rc_prev is not None:
                ax.axvspan(x0_band, d,
                           alpha=RISK_BG_ALPHA[rc_prev],
                           color=RISK_BG[rc_prev], linewidth=0, zorder=1)
            rc_prev = rc
            x0_band = d

    if rc_prev is not None:
        ax.axvspan(x0_band, df["date"].iloc[-1] + pd.Timedelta(days=1),
                   alpha=RISK_BG_ALPHA[rc_prev],
                   color=RISK_BG[rc_prev], linewidth=0, zorder=1)

    # THRESHOLD STEPS
    warn_arr = df["warning_threshold_C"].values.astype(float)
    crit_arr = df["critical_threshold_C"].values.astype(float)
    oos_mask = (df["risk_class"] == "Out of season").values
    warn_arr = np.where(oos_mask, np.nan, warn_arr)
    crit_arr = np.where(oos_mask, np.nan, crit_arr)

    ax.step(df["date"], warn_arr, where="post",
            color="#E65100", linewidth=1.8, linestyle="--", alpha=0.85, zorder=3,
            label="Moderate threshold (°C)")
    ax.step(df["date"], crit_arr, where="post",
            color="#B71C1C", linewidth=1.8, linestyle=":",  alpha=0.85, zorder=3,
            label="Critical threshold (°C)")

    # T_min
    ax.plot(df["date"], df["temp_min"],
            color="#1565C0", linewidth=2.0, zorder=5,
            label="T min (°C)")

    # Active days with alerts (points)
    for rc, dot_color in RISK_DOT.items():
        mask = df["risk_class"] == rc
        if mask.any():
            ax.scatter(df.loc[mask, "date"], df.loc[mask, "temp_min"],
                       color=dot_color, s=45, zorder=6,
                       edgecolors="white", linewidths=0.7,
                       label=RISK_IT[rc])

    # 0 °C line
    ax.axhline(0, color="#546E7A", linewidth=1.1, linestyle="-.", alpha=0.7, zorder=2)

    # BBCH stage transitions
    df["_phase_key"] = (
        df["bbch_range"].fillna("oos") + "|" +
        df["phenological_phase"].fillna("")
    )
    trans_mask  = df["_phase_key"] != df["_phase_key"].shift(1)
    transitions = df[trans_mask & df["bbch_range"].notna()].copy()

    for _, tr in transitions.iterrows():
        xpos = tr["date"]
        ax.axvline(xpos, color="#78909C", linewidth=0.8,
                   linestyle="-", alpha=0.4, zorder=2)
        phase_lbl = (
            f"BBCH {tr['bbch_range']}\n{tr['phenological_phase']}"
            if pd.notna(tr.get("phenological_phase")) and tr["phenological_phase"]
            else f"BBCH {tr['bbch_range']}"
        )
        ax.text(
            xpos + pd.Timedelta(days=1.2),
            0.96,
            phase_lbl,
            transform=ax.get_xaxis_transform(),
            fontsize=6.5, color="#37474F",
            va="top", ha="left",
            rotation=90,
            clip_on=True,
            zorder=7,
        )

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=40, ha="right", fontsize=9)

    ax.set_ylabel("Temperature (°C)", fontsize=11)
    ax.grid(axis="y", alpha=0.3, linewidth=0.6, color="#B0BEC5")
    ax.grid(axis="x", alpha=0.12, linewidth=0.5, color="#B0BEC5")

    t_vals  = df["temp_min"].dropna().values
    y_range = max(t_vals.max() - t_vals.min(), 10)
    ax.set_ylim(t_vals.min() - y_range * 0.10,
                t_vals.max() + y_range * 0.28)

    d_from = df["date"].iloc[0].strftime("%d/%m/%Y")
    d_to   = df["date"].iloc[-1].strftime("%d/%m/%Y")
    ax.set_title(
        f"Frost Risk — {crop} — {location}\n"
        f"{d_from} → {d_to}",
        fontsize=14, fontweight="bold", pad=14,
    )

    # Legend
    patch_handles = [
        mpatches.Patch(facecolor=RISK_BG["Watch"],    alpha=RISK_BG_ALPHA["Watch"],
                       edgecolor="#888", label="Low risk"),
        mpatches.Patch(facecolor=RISK_BG["Warning"],  alpha=RISK_BG_ALPHA["Warning"],
                       edgecolor="#888", label="Moderate risk"),
        mpatches.Patch(facecolor=RISK_BG["Critical"], alpha=RISK_BG_ALPHA["Critical"],
                       edgecolor="#888", label="High risk"),
    ]
    line_handles = [
        Line2D([0], [0], color="#1565C0", linewidth=2.0,
               label="T min (°C)"),
        Line2D([0], [0], color="#E65100", linewidth=1.8, linestyle="--",
               label="Moderate threshold"),
        Line2D([0], [0], color="#B71C1C", linewidth=1.8, linestyle=":",
               label="Critical threshold"),
        Line2D([0], [0], color="#546E7A", linewidth=1.1, linestyle="-.",
               label="0 °C"),
    ]
    ax.legend(
        handles=patch_handles + line_handles,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        borderaxespad=0,
        fontsize=8.5,
        framealpha=0.95,
        ncol=1,
        edgecolor="#ccc",
    )

    # Saving
    plt.tight_layout(rect=[0, 0, 0.85, 1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Grafico salvato → {output_path}")


# Entry point
def main() -> None:
    p = argparse.ArgumentParser(
        description="Agrobit — Frost risk"
    )
    p.add_argument("--crop",     nargs="+", metavar="CROP",
                   help="One or more crop names to generate charts for")
    p.add_argument("--all",      action="store_true",
                   help="Generate charts for all available crops")
    p.add_argument("--weather",  type=Path, default=WEATHER_FILE,
                   help=f"Weather file (XLSX/CSV/JSON). Default: {WEATHER_FILE.name}")
    p.add_argument("--rules",    type=Path, default=RULES_JSON,
                   help=f"Regole BBCH→GDD JSON. Default: {RULES_JSON.name}")
    p.add_argument("--out",      type=Path, default=OUTPUT_DIR,
                   help=f"Directory output. Default: {OUTPUT_DIR}")
    p.add_argument("--location", type=str, default="Lari (Toscana)",
                   help="Name of the weather station for the chart title")
    args = p.parse_args()

    print("\n" + "=" * 62)
    print("  Agrobit — Frost risk generator")
    print("=" * 62)

    try:
        rules = load_frost_rules(args.rules)
    except FileNotFoundError:
        print(f"\n  ERROR: risk rules not found: {args.rules}")
        sys.exit(1)
    print(f"  Rules:  {len(rules)} crops loaded from {args.rules.name}")

    try:
        weather = load_weather(args.weather)
    except FileNotFoundError:
        print(f"\n  ERROR: weather file not found: {args.weather}")
        sys.exit(1)
    except ValueError as e:
        print(f"\n  ERROR loading weather data: {e}")
        sys.exit(1)

    print(f"  Weather:   {weather['date'].min().date()} → {weather['date'].max().date()}"
          f"  ({len(weather)} days, station: {args.location})")

    all_crops = available_crops(rules)
    if args.all:
        selected = all_crops
    elif args.crop:
        selected = []
        for c in args.crop:
            match = next((a for a in all_crops if a.lower() == c.lower()), None)
            if match:
                selected.append(match)
            else:
                close = [a for a in all_crops if c.lower() in a.lower()]
                hint  = f" ERROR: {', '.join(close)}?" if close else ""
                print(f"  ERROR: crop '{c}' not recognized.{hint}")
                sys.exit(1)
    else:
        selected = _select_crops_interactive(all_crops)

    print(f"  Crops: {', '.join(selected)}\n")

    for crop in selected:
        print(f"  Processing: {crop} ...")
        results = run_frost_alerts(weather, rules, crops=[crop])
        fname    = f"frost_chart_{crop.lower().replace(' ', '_')}.png"
        out_path = args.out / fname
        plot_frost_chart(results, crop, out_path, location=args.location)

    print(f"\n  All charts saved in: {args.out}")
    print("=" * 62 + "\n")


if __name__ == "__main__":
    main()

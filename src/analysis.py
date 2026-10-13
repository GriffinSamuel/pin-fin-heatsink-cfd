"""Sweep analysis (T7): Pareto front, figures and a results table.

Input: results/sweep.csv written by src.sweep (one row per case). Works on any table with the
columns d, pd, h, layout, R_max_K_W, dP_Pa, fin_mass_g, status (rows with status != ok are
dropped). Writes results/pareto.csv, figures/*.png and docs/results.md.

    .venv/bin/python -m src.analysis --csv results/sweep.csv --out results --fig figures --docs docs
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# reference palette (dataviz skill): fixed categorical order, text in ink tokens
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
LAYOUT_COLOR = {"inline": BLUE, "staggered": ORANGE}
PD_COLOR = {1.8: BLUE, 2.2: ORANGE, 2.8: AQUA}
H_MARKER = {20.0: "o", 35.0: "s"}

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": AXIS,
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 10, "legend.frameon": False, "savefig.dpi": 160,
})


def pareto_front(df: pd.DataFrame, x: str = "dP_Pa", y: str = "R_max_K_W") -> pd.DataFrame:
    """Non-dominated rows minimising both x and y, sorted by x."""
    d = df.sort_values([x, y]).reset_index(drop=True)
    keep, best_y = [], np.inf
    for i, r in d.iterrows():
        if r[y] < best_y:
            keep.append(i)
            best_y = r[y]
    return d.loc[keep]


def load(csv: str) -> pd.DataFrame:
    df = pd.read_csv(csv)
    if "status" in df:
        df = df[df["status"] == "ok"]
    df = df.dropna(subset=["R_max_K_W", "dP_Pa"]).copy()
    df["T_chip_max_C"] = 25 + 100 * df["R_max_K_W"]
    return df


def fig_pareto(df: pd.DataFrame, front: pd.DataFrame, path: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    for lay, g in df.groupby("layout"):
        for h, gg in g.groupby("h"):
            ax.scatter(gg["dP_Pa"], gg["R_max_K_W"], s=38, marker=H_MARKER.get(h, "o"),
                       facecolors=LAYOUT_COLOR[lay], edgecolors="#fcfcfb", linewidths=1.2,
                       label=f"{lay}, h = {h:g} mm", zorder=3)
    ax.plot(front["dP_Pa"], front["R_max_K_W"], color=INK2, lw=1.6, zorder=2, label="Pareto front")
    for i, (_, r) in enumerate(front.iterrows()):
        ax.annotate(f"d{r['d']:g} p/d{r['pd']:g} h{r['h']:g} {r['layout'][:3]}",
                    (r["dP_Pa"], r["R_max_K_W"]), xytext=(7, 5 if i % 2 == 0 else -11),
                    textcoords="offset points", fontsize=7.5, color=INK2)
    ax.set_xlabel("Pressure drop across the heat sink, Pa")
    ax.set_ylabel("Thermal resistance chip-to-inlet, K/W")
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_vs_diameter(df: pd.DataFrame, path: str, y: str, ylabel: str) -> None:
    hs = sorted(df["h"].unique())
    fig, axes = plt.subplots(1, len(hs), figsize=(3.8 * len(hs), 4.2), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, h in zip(axes, hs):
        g = df[df["h"] == h]
        for pd_, gg in g.groupby("pd"):
            for lay, g3 in gg.groupby("layout"):
                g3 = g3.sort_values("d")
                ax.plot(g3["d"], g3[y], marker="o", ms=5, lw=1.8, color=PD_COLOR.get(pd_, MUTED),
                        ls="-" if lay == "inline" else "--", label=f"p/d = {pd_:g}, {lay}")
        ax.set_title(f"fin height {h:g} mm", loc="left", fontsize=10, color=INK2)
        ax.set_xlabel("pin diameter d, mm")
        ax.set_xticks(sorted(df["d"].unique()))
    axes[0].set_ylabel(ylabel)
    axes[-1].legend(fontsize=7.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_mass(df: pd.DataFrame, front: pd.DataFrame, path: str) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for lay, g in df.groupby("layout"):
        ax.scatter(g["fin_mass_g"], g["R_max_K_W"], s=36, color=LAYOUT_COLOR[lay], edgecolors="#fcfcfb",
                   linewidths=1.2, label=lay, zorder=3)
    ax.scatter(front["fin_mass_g"], front["R_max_K_W"], s=110, facecolors="none", edgecolors=INK2,
               linewidths=1.2, label="Pareto designs", zorder=4)
    ax.set_xlabel("fin mass, g")
    ax.set_ylabel("Thermal resistance, K/W")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_validation(df: pd.DataFrame, path: str) -> None:
    """CFD vs hand calculation for every case (needs analytic_* columns)."""
    if "analytic_R_K_W" not in df or df["analytic_R_K_W"].isna().all():
        return
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 4.0))
    for ax, (a, c, lab) in zip(axes, [("analytic_R_K_W", "R_max_K_W", "Thermal resistance, K/W"),
                                      ("analytic_dP_Pa", "dP_Pa", "Pressure drop, Pa")]):
        for lay, g in df.groupby("layout"):
            ax.scatter(g[a], g[c], s=34, color=LAYOUT_COLOR[lay], edgecolors="#fcfcfb", linewidths=1.2, label=lay, zorder=3)
        lim = [0, max(df[a].max(), df[c].max()) * 1.08]
        ax.plot(lim, lim, color=AXIS, lw=1, zorder=1)
        ax.plot(lim, [1.3 * v for v in lim], color=GRID, lw=1, ls="--", zorder=1)
        ax.plot(lim, [0.7 * v for v in lim], color=GRID, lw=1, ls="--", zorder=1)
        ax.set_xlim(lim); ax.set_ylim(lim)
        ax.set_xlabel(f"hand calculation: {lab}")
        ax.set_ylabel(f"CFD: {lab}")
        ax.legend(fontsize=8, loc="upper left")
    fig.suptitle("CFD against correlations (dashed: ±30 %)", x=0.02, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write_results_md(df: pd.DataFrame, front: pd.DataFrame, path: str, title: str) -> None:
    best_R = df.loc[df["R_max_K_W"].idxmin()]
    best_dP = df.loc[df["dP_Pa"].idxmin()]
    lines = [f"# {title}", "",
             f"{len(df)} converged cases. Thermal resistance R = (T_chip,max - T_inlet) / 100 W.", "",
             f"- Lowest R: {best_R['R_max_K_W']:.3f} K/W (chip {best_R['T_chip_max_C']:.1f} C) for "
             f"d = {best_R['d']:g} mm, p/d = {best_R['pd']:g}, h = {best_R['h']:g} mm, {best_R['layout']}, "
             f"at {best_R['dP_Pa']:.0f} Pa.",
             f"- Lowest pressure drop: {best_dP['dP_Pa']:.0f} Pa for d = {best_dP['d']:g} mm, p/d = {best_dP['pd']:g}, "
             f"h = {best_dP['h']:g} mm, {best_dP['layout']}, at R = {best_dP['R_max_K_W']:.3f} K/W.",
             f"- Pareto-optimal designs: {len(front)} of {len(df)}.", "",
             "## Pareto front (minimise R and dP)", "",
             "| d mm | p/d | h mm | layout | pins | fin mass g | R K/W | T_chip C | dP Pa |",
             "|---|---|---|---|---|---|---|---|---|"]
    for _, r in front.iterrows():
        lines.append(f"| {r['d']:g} | {r['pd']:g} | {r['h']:g} | {r['layout']} | {int(r.get('n_pins', 0) or 0)} | "
                     f"{r.get('fin_mass_g', float('nan')):.1f} | {r['R_max_K_W']:.3f} | {r['T_chip_max_C']:.1f} | {r['dP_Pa']:.0f} |")
    if "analytic_R_K_W" in df and not df["analytic_R_K_W"].isna().all():
        errR = (df["R_max_K_W"] / df["analytic_R_K_W"] - 1) * 100
        errP = (df["dP_Pa"] / df["analytic_dP_Pa"] - 1) * 100
        lines += ["", "## CFD vs hand calculation", "",
                  f"- R: CFD/correlation ratio mean {1 + errR.mean()/100:.2f}, range {1 + errR.min()/100:.2f} to {1 + errR.max()/100:.2f}",
                  f"- dP: CFD/correlation ratio mean {1 + errP.mean()/100:.2f}, range {1 + errP.min()/100:.2f} to {1 + errP.max()/100:.2f}"]
    lines += ["", "## All cases", "",
              "| d | p/d | h | layout | R K/W | dP Pa | T_chip C | fin mass g |", "|---|---|---|---|---|---|---|---|"]
    for _, r in df.sort_values("R_max_K_W").iterrows():
        lines.append(f"| {r['d']:g} | {r['pd']:g} | {r['h']:g} | {r['layout']} | {r['R_max_K_W']:.3f} | "
                     f"{r['dP_Pa']:.0f} | {r['T_chip_max_C']:.1f} | {r.get('fin_mass_g', float('nan')):.1f} |")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def run(csv: str, out: str, fig: str, docs: str, title: str = "Pin-fin heat sink sweep, 4 m/s") -> pd.DataFrame:
    df = load(csv)
    front = pareto_front(df)
    os.makedirs(out, exist_ok=True); os.makedirs(fig, exist_ok=True)
    front.to_csv(os.path.join(out, "pareto.csv"), index=False)
    fig_pareto(df, front, os.path.join(fig, "pareto.png"), title)
    fig_vs_diameter(df, os.path.join(fig, "R_vs_d.png"), "R_max_K_W", "Thermal resistance, K/W")
    fig_vs_diameter(df, os.path.join(fig, "dP_vs_d.png"), "dP_Pa", "Pressure drop, Pa")
    fig_mass(df, front, os.path.join(fig, "mass_vs_R.png"))
    fig_validation(df, os.path.join(fig, "validation.png"))
    write_results_md(df, front, os.path.join(docs, "results.md"), title)
    return front


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="results/sweep.csv")
    ap.add_argument("--out", default="results")
    ap.add_argument("--fig", default="figures")
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--title", default="Pin-fin heat sink sweep, 4 m/s")
    a = ap.parse_args(argv)
    front = run(a.csv, a.out, a.fig, a.docs, a.title)
    print(front[["d", "pd", "h", "layout", "R_max_K_W", "dP_Pa"]].to_string(index=False))


if __name__ == "__main__":
    main()

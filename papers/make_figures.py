#!/usr/bin/env python3
"""
Publication figures for the BioForm-LM manuscript, rebuilt around the audited,
real results (results/*.json). Every number plotted here is loaded from a result
file produced by a script in scripts/, not hand-typed, so a figure cannot drift
from the analysis that produced it.

Outputs vector PDF + 300-dpi PNG into papers/figures/ (PDF for LaTeX, PNG because
Word cannot embed PDF artwork). Run:  python papers/make_figures.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = Path(__file__).parent / "figures"
FIG_DIR.mkdir(exist_ok=True)

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 9,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "axes.linewidth": 0.7,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

BLUE = "#2b6cb0"
ORANGE = "#dd6b20"
GREY = "#a0aec0"
GREEN = "#2f855a"
RED = "#c53030"
LIGHT = "#e2e8f0"

COL_W = 3.35
FULL_W = 6.9


def save(fig, name):
    fig.savefig(FIG_DIR / f"{name}.pdf")
    fig.savefig(FIG_DIR / f"{name}.png", dpi=300)
    plt.close(fig)


def load(name):
    return json.loads((ROOT / "results" / name).read_text())


# ===========================================================================
# Figure 1: simulator audit (v1 dead/corner-seeking -> v2 interior optima)
# ===========================================================================
def fig1_architecture():
    v = load("simulator_diagnosis_v1_vs_v2.json")
    slots = ["ph", "ionic_str", "osmolarity", "temperature"]
    labels = ["pH", "Ionic\nstrength", "Osmolarity", "Temperature"]
    v1 = [v["v1"]["monotonicity"][s]["interior_argmax_frac"] * 100 for s in slots]
    v2 = [v["v2"]["monotonicity"][s]["interior_argmax_frac"] * 100 for s in slots]

    fig, axes = plt.subplots(1, 2, figsize=(FULL_W, 2.5))

    ax = axes[0]
    x = np.arange(len(labels))
    w = 0.34
    ax.bar(x - w / 2, v1, w, color=RED, label="v1 (DLVO + Lumry–Eyring)")
    ax.bar(x + w / 2, v2, w, color=BLUE, label="v2 (+ 9 degradation pathways)")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("Interior-optimum fraction (%)")
    ax.set_ylim(0, 105)
    ax.set_title("(a) Optima stop collapsing to box corners", loc="left", fontsize=8.5)
    ax.legend(loc="upper left", frameon=False, fontsize=6.6)
    for xi, (a, b) in enumerate(zip(v1, v2)):
        ax.text(xi - w / 2, a + 2, f"{a:.0f}", ha="center", fontsize=6.5, color=RED)
        ax.text(xi + w / 2, b + 2, f"{b:.0f}", ha="center", fontsize=6.5, color=BLUE)

    ax = axes[1]
    dead = v["v1"]["dead_slots"]
    cats = ["Buffer\nspecies", "Buffer\nconcentration"]
    vals = [dead["buffer_species_spread"], dead["buffer_conc_spread"]]
    ax.bar(cats, vals, color=GREY, width=0.5)
    ax.set_ylim(-0.02, 0.15)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_ylabel("Predicted-stability spread\n(varying this slot alone)")
    ax.set_title("(b) Two of eight recipe slots are dead in v1", loc="left", fontsize=8.5)
    for i, val in enumerate(vals):
        ax.text(i, 0.01, f"{val:.1f}\n(exactly 0.0)", ha="center", fontsize=7)

    fig.tight_layout()
    save(fig, "fig1_architecture")


# ===========================================================================
# Figure 2: the n=27 -> n=80 selection artifact
# ===========================================================================
def fig2_recall():
    seq = load("sequence_conditionality.json")
    val = load("conditionality_validation.json")

    fig, axes = plt.subplots(2, 1, figsize=(COL_W, 4.4))

    # (a) correlation + bootstrap CI at both sample sizes
    ax = axes[0]
    n27_rho = val["screen"][0]["rho"]
    n27_ci = val["bootstrap_ci95"]
    n80_rho = seq["ph_vs_sequence"]["fv_pi"]["spearman"]
    xs = [0, 1]
    rhos = [n27_rho, n80_rho]
    los = [n27_ci[0], n80_rho]
    his = [n27_ci[1], n80_rho]
    ax.errorbar([0], [n27_rho], yerr=[[n27_rho - n27_ci[0]], [n27_ci[1] - n27_rho]],
                fmt="o", color=RED, capsize=3, markersize=6, label="n=27 subsample")
    ax.errorbar([1], [n80_rho], yerr=0, fmt="o", color=BLUE, capsize=3,
                markersize=6, label="n=80 full sample")
    ax.axhline(0, color="black", lw=0.7, ls="--")
    ax.set_xlim(-0.6, 1.6)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["n=27\n(complete rows\nonly)", "n=80\n(all pH\nrecords)"])
    ax.set_ylabel(r"Spearman $\rho$(Fv pI, pH)")
    ax.set_title("(a) Effect vanishes at full sample size", loc="left", fontsize=8)
    ax.text(0, n27_ci[0] - 0.08, f"p={val['screen'][0]['p_perm']:.3f}\nHolm p={val['screen'][0]['p_holm']:.2f}",
            ha="center", fontsize=6.3)
    ax.text(1, n80_rho - 0.13, f"p={seq['ph_vs_sequence']['fv_pi']['p']:.2f}",
            ha="center", fontsize=6.3)
    ax.legend(loc="lower left", frameon=False, fontsize=6.2)

    # (b) LOPO MAE vs baseline
    ax = axes[1]
    lopo = val["lopo"]
    cats = ["Baseline\n(no info)", "Sequence\nmodel"]
    vals_ = [lopo["mae_baseline"], lopo["mae_sequence"]]
    colors = [GREY, RED]
    ax.bar(cats, vals_, color=colors, width=0.5)
    ax.set_ylabel("LOPO mean absolute error\n(pH units)")
    ax.set_title("(b) Fails out-of-sample prediction", loc="left", fontsize=8)
    for i, val_ in enumerate(vals_):
        ax.text(i, val_ + 0.01, f"{val_:.3f}", ha="center", fontsize=7)
    ax.text(0.5, max(vals_) + 0.06, f"sign-flip p={lopo['sign_flip_p']:.2f}",
            ha="center", fontsize=6.6, transform=ax.transData)
    ax.set_ylim(0, max(vals_) * 1.35)

    fig.tight_layout()
    save(fig, "fig2_recall")


# ===========================================================================
# Figure 3: platform baseline (design-space concentration) + ICL necessity
# ===========================================================================
def fig3_calibration():
    plat = load("platform_convergence.json")

    fig = plt.figure(figsize=(FULL_W, 2.6))
    axes = fig.subplots(1, 3)

    # (a) pH clustering across 80 molecules
    ax = axes[0]
    ph = plat["design_space_concentration"]["ph"]
    mae_platform = plat["beat_platform"]["platform_lopo_mae"]
    models = plat["beat_platform"]["models"]
    cats = ["Platform\n(median)"] + list(models.keys())
    maes = [mae_platform] + [models[k]["mae"] for k in models]
    colors = [GREEN] + [RED, ORANGE][: len(models)]
    ax.bar(cats, maes, color=colors, width=0.55)
    ax.set_ylabel("LOPO MAE, formulation pH")
    ax.set_title("(a) No covariate beats\nthe platform baseline", loc="left", fontsize=8)
    for i, m in enumerate(maes):
        ax.text(i, m + 0.005, f"{m:.3f}", ha="center", fontsize=6.8)
    ax.tick_params(axis="x", labelsize=6.3)
    ax.set_ylim(0, max(maes) * 1.25)

    # (b) design-space concentration: top-1 share
    ax = axes[1]
    buf = plat["design_space_concentration"].get("buffer_species")
    surf_key = "surfactant"
    rows = []
    if buf:
        rows.append(("Buffer\n(" + buf["top"] + ")", buf["top_share"] * 100))
    plat_baseline = plat["platform_baseline"]
    if "surfactant" in plat_baseline:
        s = plat_baseline["surfactant"]
        rows.append(("Surfactant\n(" + s["prediction"] + ")", s["accuracy"] * 100))
    labels_ = [r[0] for r in rows]
    vals_ = [r[1] for r in rows]
    ax.bar(labels_, vals_, color=BLUE, width=0.5)
    ax.axhline(100, color=GREY, lw=0.6, ls=":")
    ax.set_ylabel("Share of molecules using\nthe single most common choice (%)")
    ax.set_ylim(0, 110)
    ax.set_title("(b) A narrow, conventional\ndesign space", loc="left", fontsize=8)
    for i, v_ in enumerate(vals_):
        ax.text(i, v_ + 3, f"{v_:.0f}%", ha="center", fontsize=7.5)

    # (c) ICL necessity: unanimous effect in both directions, freshly verified
    # by re-running inference for both checkpoints with/without context and
    # comparing likelihood_percentile per protein (results/icl_necessity_verified.json;
    # see scripts/evaluate_real.py -- this is the metric that actually consumes
    # the inference-time prefix, unlike the stability-classification score).
    ax = axes[2]
    icl_res = load("icl_necessity_verified.json")
    icl_stat = icl_res["icl_trained_model"]
    flat_stat = icl_res["flat_trained_model"]
    cats = [f"ICL-structured\npretraining\n({icl_stat['n_improved']}/{icl_stat['n']} improve)",
            f"Flat-triple\npretraining\n({flat_stat['n_improved']}/{flat_stat['n']} improve)"]
    vals_ = [icl_stat["mean_delta"], flat_stat["mean_delta"]]
    colors = [BLUE, ORANGE]
    ax.bar(cats, vals_, color=colors, width=0.5)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_ylabel(r"Mean $\Delta$ likelihood percentile from"
                  "\nsupplying real in-context examples")
    p_str = f"p={icl_stat['exact_two_sided_p']:.4f}"
    ax.set_title(f"(c) ICL-structured pretraining\nis necessary ({p_str})", loc="left", fontsize=8)
    for i, v_ in enumerate(vals_):
        ax.text(i, v_ + (0.003 if v_ >= 0 else -0.008), f"{v_:+.3f}",
                ha="center", fontsize=7.5)
    ax.tick_params(axis="x", labelsize=6.3)

    fig.tight_layout()
    save(fig, "fig3_calibration")


if __name__ == "__main__":
    fig1_architecture()
    fig2_recall()
    fig3_calibration()
    print(f"wrote figures to {FIG_DIR}")

#!/usr/bin/env python3
"""Experiment Reader - the three questions a senior analyst asks before reading an A/B test.

1. Synthesize three experiments as user-level data (fixed seed): a clean winner, a test
   with a sample-ratio mismatch, and a flat test that hides a segment reversal. Each user
   has an arm, an assignment day, a platform, a user type, a conversion flag and a
   heavy-tailed revenue figure in INR.
2. Engine per experiment: SRM chi-square; two-proportion z-test with a 95% CI on the
   relative lift; Welch t-test on revenue per user; Beta-Binomial posterior (P(B>A),
   expected loss); a peeking guard that replays the p-value at day 3/5/7; a segment
   check that flags a segment whose CI excludes zero against the overall direction.
3. Evidence pack per experiment, with a deterministic verdict:
   SHIP / HOLD / INVALID (SRM) / INVESTIGATE (segment reversal).
4. Narrate: with GEMINI_API_KEY or ANTHROPIC_API_KEY set, an LLM writes the decision
   memo. Every number it writes is checked against the evidence pack; if it invents one,
   the deterministic template is used. Without a key you get the template. The engine
   decides; the LLM only explains.

Run:  python experiment_reader.py
Out:  memos.md, lifts.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import llm  # noqa: E402

RNG = np.random.default_rng(25)
SEGMENTS = {"platform": ["Android", "iOS"], "user_type": ["new", "returning"]}
DAYS = 14
PEEK_DAYS = (3, 5, 7)


# --------------------------------------------------------------------------- data
def make_users(n: int, p_a: float, lift: dict[str, float], novelty: float = 0.0) -> pd.DataFrame:
    """One experiment. `lift` maps segment value -> relative lift for arm B (default key '*')."""
    d = pd.DataFrame({
        "arm": np.where(RNG.random(n) < 0.5, "A", "B"),
        "day": RNG.integers(1, DAYS + 1, n),
        "platform": RNG.choice(SEGMENTS["platform"], n, p=[0.5, 0.5]),
        "user_type": RNG.choice(SEGMENTS["user_type"], n, p=[0.4, 0.6]),
    })
    rel = np.full(n, lift.get("*", 0.0))
    for seg, v in lift.items():
        if seg != "*":
            rel = np.where((d.platform == seg) | (d.user_type == seg), v, rel)
    rel = np.where(d.day <= 3, rel + novelty, rel)                   # early-adopter bump
    p = np.where(d.arm == "B", p_a * (1 + rel), p_a)
    d["converted"] = (RNG.random(n) < p).astype(int)
    d["revenue"] = np.where(d.converted == 1, RNG.lognormal(7.2, 1.1, n).round(0), 0.0)
    return d


def make_experiments() -> dict[str, pd.DataFrame]:
    clean = make_users(300_000, 0.12, {"*": 0.025})
    srm = make_users(100_000, 0.10, {"*": 0.0})
    # a logging bug drops 15% of arm B's iOS sessions - mostly the ones that never converted
    drop = (srm.arm == "B") & (srm.platform == "iOS") & (RNG.random(len(srm)) < 0.15) & (srm.converted == 0)
    srm = srm[~drop].reset_index(drop=True)
    flat = make_users(300_000, 0.10, {"Android": 0.06, "iOS": -0.06}, novelty=0.06)
    return {"checkout_upi_intent": clean, "onboarding_kyc_lite": srm, "home_offers_rail": flat}


# --------------------------------------------------------------------------- engine
def pval(p: float) -> float:
    """4 decimals when readable, scientific when tiny - never a misleading 0.0."""
    return round(float(p), 4) if p >= 1e-4 else float(f"{p:.1e}")


def srm_test(n_a: int, n_b: int, intended_a: float = 0.5) -> dict:
    n = n_a + n_b
    chi2, p = stats.chisquare([n_a, n_b], [n * intended_a, n * (1 - intended_a)])
    return {"intended_split": f"{intended_a:.0%}/{1 - intended_a:.0%}",
            "observed_split": f"{n_a / n:.1%}/{n_b / n:.1%}",
            "chi2": round(float(chi2), 2), "p_value": pval(p)}


def conversion_lift(a: pd.Series, b: pd.Series) -> dict:
    """Two-proportion z-test plus a delta-method 95% CI on the relative lift."""
    n_a, n_b, x_a, x_b = len(a), len(b), int(a.sum()), int(b.sum())
    p_a, p_b = x_a / n_a, x_b / n_b
    pooled = (x_a + x_b) / (n_a + n_b)
    se = np.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    z = (p_b - p_a) / se if se else 0.0
    p_value = 2 * stats.norm.sf(abs(z))
    se_log = np.sqrt((1 - p_a) / (n_a * p_a) + (1 - p_b) / (n_b * p_b))
    lo, hi = np.exp(np.log(p_b / p_a) + np.array([-1.96, 1.96]) * se_log) - 1
    return {"rate_a": round(p_a * 100, 3), "rate_b": round(p_b * 100, 3),
            "lift_pct": round((p_b / p_a - 1) * 100, 2),
            "ci_low_pct": round(lo * 100, 2), "ci_high_pct": round(hi * 100, 2),
            "z": round(float(z), 2), "p_value": pval(p_value)}


def revenue_lift(a: pd.Series, b: pd.Series) -> dict:
    t, p = stats.ttest_ind(b, a, equal_var=False)
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    diff = b.mean() - a.mean()
    return {"rpu_a_inr": round(a.mean(), 2), "rpu_b_inr": round(b.mean(), 2),
            "lift_pct": round(diff / a.mean() * 100, 2),
            "ci_low_pct": round((diff - 1.96 * se) / a.mean() * 100, 2),
            "ci_high_pct": round((diff + 1.96 * se) / a.mean() * 100, 2),
            "welch_p": pval(p)}


def bayesian_read(a: pd.Series, b: pd.Series, draws: int = 200_000) -> dict:
    """Beta(1,1) priors. Expected loss = what you give up, relative to A, if B is worse."""
    rng = np.random.default_rng(0)
    pa = rng.beta(1 + a.sum(), 1 + len(a) - a.sum(), draws)
    pb = rng.beta(1 + b.sum(), 1 + len(b) - b.sum(), draws)
    loss = np.maximum(pa - pb, 0).mean() / pa.mean()
    return {"p_b_beats_a": round(float((pb > pa).mean()), 4),
            "expected_loss_pct": round(float(loss * 100), 3)}


def peeking_guard(d: pd.DataFrame, final_p: float) -> dict:
    path = {f"day_{k}": conversion_lift(d[(d.arm == "A") & (d.day <= k)].converted,
                                        d[(d.arm == "B") & (d.day <= k)].converted)["p_value"]
            for k in PEEK_DAYS}
    crossed = [k for k, p in path.items() if p < 0.05]
    return {"p_value_path": path, f"day_{DAYS}": final_p,
            "flag": bool(crossed) and final_p >= 0.05,
            "crossed_then_recovered_at": crossed if final_p >= 0.05 else []}


def segment_table(d: pd.DataFrame, overall_sign: int) -> list[dict]:
    rows = []
    for col, values in SEGMENTS.items():
        for v in values:
            s = d[d[col] == v]
            r = conversion_lift(s[s.arm == "A"].converted, s[s.arm == "B"].converted)
            excludes_zero = r["ci_low_pct"] > 0 or r["ci_high_pct"] < 0
            seg_sign = 1 if r["lift_pct"] > 0 else -1
            rows.append({"segment": v, "dimension": col, "users": len(s),
                         "lift_pct": r["lift_pct"], "ci_low_pct": r["ci_low_pct"],
                         "ci_high_pct": r["ci_high_pct"],
                         "reversal": bool(excludes_zero and seg_sign != overall_sign)})
    return rows


def verdict(ev: dict) -> str:
    if ev["srm"]["p_value"] < 0.001:
        return "INVALID (SRM)"
    if any(s["reversal"] for s in ev["segments"]):
        return "INVESTIGATE (segment reversal)"
    if ev["conversion"]["ci_low_pct"] > 0 and not ev["peeking"]["flag"]:
        return "SHIP"
    return "HOLD"


def read_experiment(name: str, d: pd.DataFrame) -> dict:
    a, b = d[d.arm == "A"], d[d.arm == "B"]
    conv = conversion_lift(a.converted, b.converted)
    ev = {"experiment": name, "users_a": len(a), "users_b": len(b), "days": DAYS,
          "srm": srm_test(len(a), len(b)), "conversion": conv,
          "revenue": revenue_lift(a.revenue, b.revenue),
          "bayes": bayesian_read(a.converted, b.converted),
          "peeking": peeking_guard(d, conv["p_value"]),
          "segments": segment_table(d, 1 if conv["lift_pct"] >= 0 else -1)}
    ev["verdict"] = verdict(ev)
    return ev


# --------------------------------------------------------------------------- narrative
def srm_p(ev: dict) -> str:
    p = ev["srm"]["p_value"]
    return "< 0.001" if p < 0.001 else f"= {p:g}"


def template_memo(ev: dict) -> str:
    c, v = ev["conversion"], ev["verdict"]
    lift = f"conversion {c['lift_pct']:+g}% relative (95% CI {c['ci_low_pct']:+g}% to {c['ci_high_pct']:+g}%)"
    if v.startswith("INVALID"):
        caveat = (f"Assignment was meant to be {ev['srm']['intended_split']} but landed "
                  f"{ev['srm']['observed_split']} (SRM p {srm_p(ev)}); the arms are not comparable, "
                  f"so the {lift} is not a lift, it is a selection effect.")
        action = "Next: find where users leaked from one arm (logging, bot filter, app version) and rerun."
    elif v.startswith("INVESTIGATE"):
        rev = [s for s in ev["segments"] if s["reversal"]]
        seg = "; ".join(f"{s['segment']} {s['lift_pct']:+g}% (CI {s['ci_low_pct']:+g}% to {s['ci_high_pct']:+g}%)"
                        for s in rev)
        caveat = f"Overall {lift}, P(B>A) = {ev['bayes']['p_b_beats_a']:.0%}, but the average hides a reversal: {seg}."
        action = "Next: do not ship or kill on the average - split the decision by segment and find out why the losing side loses."
    elif v == "SHIP":
        caveat = (f"{lift[0].upper() + lift[1:]}, P(B>A) = {ev['bayes']['p_b_beats_a']:.1%}, "
                  f"expected loss {ev['bayes']['expected_loss_pct']:g}% of baseline; "
                  f"revenue per user {ev['revenue']['lift_pct']:+g}% "
                  f"(CI {ev['revenue']['ci_low_pct']:+g}% to {ev['revenue']['ci_high_pct']:+g}%).")
        action = "Next: ship to 100% and hold back a 5% control for four weeks to confirm the lift persists."
    else:
        caveat = f"{lift[0].upper() + lift[1:]}; the interval includes zero."
        if ev["peeking"]["flag"]:
            caveat += (f" Significance came and went (p < 0.05 at "
                       f"{', '.join(k.replace('_', ' ') for k in ev['peeking']['crossed_then_recovered_at'])}, "
                       f"{c['p_value']:g} at day {DAYS}) - an early stop would have shipped a flat test.")
        action = "Next: keep the test running to the pre-registered sample size, or close it as no effect."
    if ev["peeking"]["flag"] and v != "HOLD":
        caveat += (f" Peeking guard: p dipped below 0.05 at "
                   f"{', '.join(k.replace('_', ' ') for k in ev['peeking']['crossed_then_recovered_at'])} "
                   f"and recovered to {c['p_value']:g} by day {DAYS}.")
    return f"Verdict: {v}.\n{caveat}\n{action}"


SYSTEM = """You write one-paragraph A/B test decision memos for a product lead at a payments company.
Format: three or four short lines.
1) "Verdict: <verdict>." exactly as given in the evidence.
2) The conversion lift and its 95% CI, plain English.
3) The caveat that matters most for this verdict: SRM, peeking, or a segment reversal. If none, P(B>A) and expected loss.
4) Starts with "Next:" and gives ONE concrete action.
Use ONLY numbers present in the evidence. Never compute new numbers or re-round. No jargon about models."""


def narrate(ev: dict) -> tuple[str, str]:
    text = llm.complete(SYSTEM, json.dumps(ev, indent=2), max_tokens=300)
    if text is None:
        return template_memo(ev), "template (no API key)"
    bad = llm.unpinned(text, ev)
    if bad:
        return template_memo(ev), f"template (LLM invented numbers: {sorted(bad)})"
    return text, f"llm ({llm.provider()})"


# --------------------------------------------------------------------------- chart
def plot(packs: list[dict], path: str = "lifts.png") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(packs), figsize=(13, 4.6), sharey=True)
    for ax, ev in zip(axes, packs):
        rows = [("Overall", ev["conversion"], True)] + [(s["segment"], s, s["reversal"]) for s in ev["segments"]]
        y = np.arange(len(rows))[::-1]
        bad = ev["verdict"] != "SHIP"
        for yi, (label, r, flag) in zip(y, rows):
            overall = label == "Overall"
            colour = "#d9534f" if (overall and bad) or (not overall and flag) else ("#4A6FA5" if overall else "#8a8f98")
            ax.plot([r["ci_low_pct"], r["ci_high_pct"]], [yi, yi], color=colour, lw=2 if overall else 1.4,
                    solid_capstyle="round")
            ax.plot(r["lift_pct"], yi, "o", color=colour, ms=9 if overall else 7, mec="white", mew=1.2)
            ax.annotate(f"{r['lift_pct']:+.1f}%", (r["ci_high_pct"], yi), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8, color="#444",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
        ax.axvline(0, color="#999", lw=1, ls="--", zorder=0)
        ax.set_yticks(y)
        ax.set_yticklabels([r[0] for r in rows], fontsize=9)
        ax.set_title(f"{ev['experiment']}\n{ev['verdict']}", fontsize=10, loc="left")
        ax.set_xlabel("relative conversion lift, % (dot = estimate, bar = 95% CI)", fontsize=8)
        ax.grid(axis="x", alpha=0.2)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        lo = min(r["ci_low_pct"] for _, r, _ in rows)
        hi = max(r["ci_high_pct"] for _, r, _ in rows)
        ax.set_xlim(lo - 2, hi + 4)
    fig.suptitle("Three experiments, one reading each: overall lift vs per-segment lift", fontsize=11, x=0.01, ha="left")
    plt.tight_layout()
    plt.savefig(path, dpi=130)


# --------------------------------------------------------------------------- main
def main() -> None:
    exps = make_experiments()
    packs = [read_experiment(name, d) for name, d in exps.items()]
    print(f"{sum(len(d) for d in exps.values()):,} users across {len(exps)} experiments · "
          f"{DAYS}-day windows · LLM provider: {llm.provider()}\n")

    out = ["# Experiment decision memos", "",
           "SRM chi-square, two-proportion z-test, Welch t, Beta-Binomial posterior, peeking replay, "
           f"segment check. Memos written by: {llm.provider()}; every number verified against the evidence pack.", ""]
    for ev in packs:
        memo, src = narrate(ev)
        print(f"── {ev['experiment']}  [{src}]")
        print(memo, "\n")
        out += [f"## {ev['experiment']}", "", memo, "", f"*source: {src}*", "",
                "<details><summary>evidence</summary>", "", "```json",
                json.dumps(ev, indent=2), "```", "</details>", ""]
    Path("memos.md").write_text("\n".join(out), encoding="utf-8")
    plot(packs)
    print("wrote memos.md and lifts.png")


if __name__ == "__main__":
    main()

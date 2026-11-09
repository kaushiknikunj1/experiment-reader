# Experiment Reader

Most A/B readouts I have been handed are a p-value and a vibe. "B won, p = 0.03, ship it." Nobody asks whether the 50/50 split actually landed 50/50, whether the test was declared on the day it first dipped under 0.05, or whether the average is two segments cancelling each other out. Those three questions are what a senior analyst asks before looking at the lift at all — and they are the questions that reverse a decision most often.

This project is that analyst as code. The engine runs the checks and produces a verdict — SHIP, HOLD, INVALID or INVESTIGATE — and a language model writes the one-paragraph memo, without being allowed to touch a number.

```
── onboarding_kyc_lite  [template (no API key)]
Verdict: INVALID (SRM).
Assignment was meant to be 50%/50% but landed 51.7%/48.3% (SRM p < 0.001); the arms are not comparable, so the conversion +5.96% relative (95% CI +2.1% to +9.95%) is not a lift, it is a selection effect.
Next: find where users leaked from one arm (logging, bot filter, app version) and rerun.

── home_offers_rail  [template (no API key)]
Verdict: INVESTIGATE (segment reversal).
Overall conversion +1.24% relative (95% CI -0.9% to +3.43%), P(B>A) = 87%, but the average hides a reversal: iOS -5.73% (CI -8.57% to -2.79%). Peeking guard: p dipped below 0.05 at day 3 and recovered to 0.2593 by day 14.
Next: do not ship or kill on the average - split the decision by segment and find out why the losing side loses.
```

That is the deterministic template. With an API key the same evidence pack goes to an LLM, which writes the memo in plainer English — and is then checked.

## How it works

1. **Data.** Three experiments as user-level rows (arm, assignment day, platform, new/returning, converted, revenue in INR with a lognormal tail) — ~700k synthetic users, fixed seed, no employer data. One is a clean +2.9% winner. One has a logging bug that drops 15% of arm B's non-converting iOS sessions, so B looks like a +6% win on a 51.7/48.3 split. One is flat overall (+1.2%) because Android is +8% and iOS is -6%.
2. **Engine.** Per experiment: a chi-square test for sample-ratio mismatch; a two-proportion z-test with a delta-method 95% CI on the *relative* lift; a Welch t-test on revenue per user; a Beta-Binomial posterior for P(B>A) and expected loss; a peeking guard that replays the p-value at day 3, 5 and 7 and flags if it crossed 0.05 and came back; a per-segment lift with CI, flagged when a segment's interval excludes zero on the opposite side of the overall estimate.
3. **Evidence pack and verdict.** Every number lands in one dict. The verdict is a fixed order of precedence — SRM beats everything, a segment reversal beats a significant average, and SHIP requires the CI to exclude zero *and* no peeking flag. The verdict is decided before any text is written.
4. **Write + verify.** The pack goes to an LLM with a four-line format: verdict first, lift and CI, the one caveat that matters, one next action. Every number in the reply is checked against the pack; if any was invented or re-rounded, the deterministic template is used and the output says so.

Step 4 matters more here than in most places. An experiment memo is the document people quote for the next quarter — "the UPI intent test gave us 3%" — and if the model rounds +2.86% to "about 3%" or restates a CI it never saw, that number is the one that survives. The engine decides; the writer only explains.

## Run it

```bash
pip install -r requirements.txt
python experiment_reader.py
python test_experiment_reader.py
```

Works with no API key — you get the template memos. For LLM-written memos set one of:

```bash
export GEMINI_API_KEY=...        # preferred; uses gemini-2.5-flash via REST
export ANTHROPIC_API_KEY=...     # uses the official anthropic SDK, claude-opus-5-5
```

Outputs: `memos.md` (memos + collapsible evidence packs) and `lifts.png` (one panel per experiment: overall lift with CI, per-segment dots, red where the reader refused the average).

## What I'd change for production

- Replace the fixed 95% CI with the pre-registered sample size and a sequential-testing correction (mSPRT or alpha-spending). The peeking guard here is a replay that tells you a stop would have been wrong; in production the stopping rule itself should be safe.
- Segment checks on four segments are fine; on forty they are a multiple-comparisons machine. Add a Bonferroni or hierarchical shrinkage step before a reversal is allowed to override the average.
- Pull the intended split, start date and primary metric from the experiment registry rather than hard-coding 50/50 and 14 days. Half the SRM cases I have seen were a ramp that someone changed mid-flight, and the registry knows that; the data alone does not.

Companion reading: [A/B Testing Guide](https://nikunjkaushik.com/blog/ab-testing.html). Part of the [Building with AI](https://nikunjkaushik.com/projects.html) set on my site.

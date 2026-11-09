# Experiment decision memos

SRM chi-square, two-proportion z-test, Welch t, Beta-Binomial posterior, peeking replay, segment check. Memos written by: none; every number verified against the evidence pack.

## checkout_upi_intent

Verdict: SHIP.
Conversion +2.86% relative (95% CI +0.89% to +4.87%), P(B>A) = 99.8%, expected loss 0.001% of baseline; revenue per user +2.74% (CI -0.93% to +6.41%).
Next: ship to 100% and hold back a 5% control for four weeks to confirm the lift persists.

*source: template (no API key)*

<details><summary>evidence</summary>

```json
{
  "experiment": "checkout_upi_intent",
  "users_a": 150154,
  "users_b": 149846,
  "days": 14,
  "srm": {
    "intended_split": "50%/50%",
    "observed_split": "50.1%/49.9%",
    "chi2": 0.32,
    "p_value": 0.5739
  },
  "conversion": {
    "rate_a": 11.843,
    "rate_b": 12.181,
    "lift_pct": 2.86,
    "ci_low_pct": 0.89,
    "ci_high_pct": 4.87,
    "z": 2.85,
    "p_value": 0.0043
  },
  "revenue": {
    "rpu_a_inr": 284.23,
    "rpu_b_inr": 292.01,
    "lift_pct": 2.74,
    "ci_low_pct": -0.93,
    "ci_high_pct": 6.41,
    "welch_p": 0.1439
  },
  "bayes": {
    "p_b_beats_a": 0.9979,
    "expected_loss_pct": 0.001
  },
  "peeking": {
    "p_value_path": {
      "day_3": 0.072,
      "day_5": 0.1711,
      "day_7": 0.0616
    },
    "day_14": 0.0043,
    "flag": false,
    "crossed_then_recovered_at": []
  },
  "segments": [
    {
      "segment": "Android",
      "dimension": "platform",
      "users": 149943,
      "lift_pct": 3.97,
      "ci_low_pct": 1.16,
      "ci_high_pct": 6.86,
      "reversal": false
    },
    {
      "segment": "iOS",
      "dimension": "platform",
      "users": 150057,
      "lift_pct": 1.76,
      "ci_low_pct": -0.99,
      "ci_high_pct": 4.59,
      "reversal": false
    },
    {
      "segment": "new",
      "dimension": "user_type",
      "users": 120090,
      "lift_pct": 5.36,
      "ci_low_pct": 2.17,
      "ci_high_pct": 8.64,
      "reversal": false
    },
    {
      "segment": "returning",
      "dimension": "user_type",
      "users": 179910,
      "lift_pct": 1.24,
      "ci_low_pct": -1.25,
      "ci_high_pct": 3.8,
      "reversal": false
    }
  ],
  "verdict": "SHIP"
}
```
</details>

## onboarding_kyc_lite

Verdict: INVALID (SRM).
Assignment was meant to be 50%/50% but landed 51.7%/48.3% (SRM p < 0.001); the arms are not comparable, so the conversion +5.96% relative (95% CI +2.1% to +9.95%) is not a lift, it is a selection effect.
Next: find where users leaked from one arm (logging, bot filter, app version) and rerun.

*source: template (no API key)*

<details><summary>evidence</summary>

```json
{
  "experiment": "onboarding_kyc_lite",
  "users_a": 49965,
  "users_b": 46670,
  "days": 14,
  "srm": {
    "intended_split": "50%/50%",
    "observed_split": "51.7%/48.3%",
    "chi2": 112.35,
    "p_value": 3e-26
  },
  "conversion": {
    "rate_a": 10.093,
    "rate_b": 10.694,
    "lift_pct": 5.96,
    "ci_low_pct": 2.1,
    "ci_high_pct": 9.95,
    "z": 3.06,
    "p_value": 0.0022
  },
  "revenue": {
    "rpu_a_inr": 252.91,
    "rpu_b_inr": 266.06,
    "lift_pct": 5.2,
    "ci_low_pct": -2.39,
    "ci_high_pct": 12.79,
    "welch_p": 0.1793
  },
  "bayes": {
    "p_b_beats_a": 0.9989,
    "expected_loss_pct": 0.001
  },
  "peeking": {
    "p_value_path": {
      "day_3": 0.1245,
      "day_5": 0.0314,
      "day_7": 0.0345
    },
    "day_14": 0.0022,
    "flag": false,
    "crossed_then_recovered_at": []
  },
  "segments": [
    {
      "segment": "Android",
      "dimension": "platform",
      "users": 50179,
      "lift_pct": -0.96,
      "ci_low_pct": -6.01,
      "ci_high_pct": 4.36,
      "reversal": false
    },
    {
      "segment": "iOS",
      "dimension": "platform",
      "users": 46456,
      "lift_pct": 13.94,
      "ci_low_pct": 8.12,
      "ci_high_pct": 20.08,
      "reversal": false
    },
    {
      "segment": "new",
      "dimension": "user_type",
      "users": 38727,
      "lift_pct": 4.66,
      "ci_low_pct": -1.34,
      "ci_high_pct": 11.02,
      "reversal": false
    },
    {
      "segment": "returning",
      "dimension": "user_type",
      "users": 57908,
      "lift_pct": 6.83,
      "ci_low_pct": 1.86,
      "ci_high_pct": 12.04,
      "reversal": false
    }
  ],
  "verdict": "INVALID (SRM)"
}
```
</details>

## home_offers_rail

Verdict: INVESTIGATE (segment reversal).
Overall conversion +1.24% relative (95% CI -0.9% to +3.43%), P(B>A) = 87%, but the average hides a reversal: iOS -5.73% (CI -8.57% to -2.79%). Peeking guard: p dipped below 0.05 at day 3 and recovered to 0.2593 by day 14.
Next: do not ship or kill on the average - split the decision by segment and find out why the losing side loses.

*source: template (no API key)*

<details><summary>evidence</summary>

```json
{
  "experiment": "home_offers_rail",
  "users_a": 150243,
  "users_b": 149757,
  "days": 14,
  "srm": {
    "intended_split": "50%/50%",
    "observed_split": "50.1%/49.9%",
    "chi2": 0.79,
    "p_value": 0.3749
  },
  "conversion": {
    "rate_a": 10.008,
    "rate_b": 10.132,
    "lift_pct": 1.24,
    "ci_low_pct": -0.9,
    "ci_high_pct": 3.43,
    "z": 1.13,
    "p_value": 0.2593
  },
  "revenue": {
    "rpu_a_inr": 249.19,
    "rpu_b_inr": 250.44,
    "lift_pct": 0.5,
    "ci_low_pct": -3.69,
    "ci_high_pct": 4.69,
    "welch_p": 0.8152
  },
  "bayes": {
    "p_b_beats_a": 0.869,
    "expected_loss_pct": 0.071
  },
  "peeking": {
    "p_value_path": {
      "day_3": 0.0286,
      "day_5": 0.1021,
      "day_7": 0.4733
    },
    "day_14": 0.2593,
    "flag": true,
    "crossed_then_recovered_at": [
      "day_3"
    ]
  },
  "segments": [
    {
      "segment": "Android",
      "dimension": "platform",
      "users": 149660,
      "lift_pct": 8.39,
      "ci_low_pct": 5.2,
      "ci_high_pct": 11.68,
      "reversal": false
    },
    {
      "segment": "iOS",
      "dimension": "platform",
      "users": 150340,
      "lift_pct": -5.73,
      "ci_low_pct": -8.57,
      "ci_high_pct": -2.79,
      "reversal": true
    },
    {
      "segment": "new",
      "dimension": "user_type",
      "users": 119953,
      "lift_pct": -0.47,
      "ci_low_pct": -3.78,
      "ci_high_pct": 2.95,
      "reversal": false
    },
    {
      "segment": "returning",
      "dimension": "user_type",
      "users": 180047,
      "lift_pct": 2.39,
      "ci_low_pct": -0.4,
      "ci_high_pct": 5.26,
      "reversal": false
    }
  ],
  "verdict": "INVESTIGATE (segment reversal)"
}
```
</details>

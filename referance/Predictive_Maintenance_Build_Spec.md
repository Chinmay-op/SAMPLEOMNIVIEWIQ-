# Predictive Maintenance (Layer 3, Unit 2b) — Build Spec & Presentation Guide

Companion notebook: `Predictive_Maintenance_Prototype.ipynb` — run this alongside for live proof of every claim below.

---

## 1. The one thing to say upfront in any presentation

**We don't have failure-labeled history yet, so a classic "predict remaining useful life" supervised model isn't buildable on day one — and pretending otherwise won't survive questioning.** This is the same cold-start problem already solved for anomaly detection, solved the same way: stage the approach so it delivers value immediately and gets smarter as real maintenance events accumulate.

---

## 2. Staged Approach

| Stage | Trigger | What it is | Data needed | Confidence |
|---|---|---|---|---|
| A — Health Index | Day 1 | Unsupervised: deviation from population-prior baseline, converted to a 0–100 score | Zero failure history — reuses the same population priors already needed for anomaly detection (Unit 3) | Medium, but immediately useful |
| B — Risk Classifier | ~10–20 real logged maintenance events | Supervised binary classification: "will this machine need attention in the next N days" | A handful of real maintenance/failure logs — doesn't need to be a large dataset | Rising with more events |
| C — Survival / RUL model | Enough run-to-failure histories across the fleet | Time-to-event modeling (Cox proportional hazards or Weibull) for an actual days-remaining estimate | Months of accumulated failure data across many machines | Full, only once data supports it |

Stage A is what ships first. Stages B and C are the roadmap, not blockers.

---

## 3. What parameters are needed

No new sensors. Everything reuses fields already flowing through your meter data, the same ones flagged in the anomaly-detection feature table — just interpreted as **trends over days/weeks**, not point-in-time readings:

| Feature | Signal it degrades | Direction of concern |
|---|---|---|
| `Current_R/Y/B_Harm` | insulation stress, non-linear load | rising |
| `Voltage_R/Y/B_Harm` | power quality degradation | rising |
| `PF_Ave` | bearing friction, mechanical inefficiency | falling |
| `Neutral_current` | imbalance, loose connections | rising |
| phase current imbalance (derived) | winding/wiring issues | rising |

**Derived features actually fed to the model** — 7-day rolling slope of each signal above, plus the raw value's deviation from the population-prior baseline (mean/std per equipment class). Slopes catch early drift; deviation catches "already bad."

---

## 4. Preprocessing Steps

1. **Resample to daily aggregates.** This is a slow signal — daily is enough resolution, no need for the 15-minute granularity the anomaly detector needs.
2. **Handle gaps.** Forward-fill short gaps; flag anything longer than a few days as reduced confidence rather than silently interpolating across it.
3. **Normalize by load** — same normalization Unit 1 already does for the anomaly path, reused here rather than rebuilt.
4. **Rolling trend features** — fit a line over a trailing 7-day (and optionally 30-day) window per signal, take the slope. This is the core preprocessing step; everything downstream depends on it.
5. **Health Index computation** — average absolute z-score across all tracked signals vs. population-prior baseline, converted to a 0–100 score.

---

## 5. Algorithms, and why each one

| Stage | Algorithm | Why this one |
|---|---|---|
| A | Weighted z-score composite (Health Index) | No training required, interpretable (each contributing feature is visible), works from day one |
| A (early warning) | CUSUM change-point detection | Catches a sustained shift a few days before a fixed threshold would trip — cheap to implement, no library dependency |
| B | Random Forest (or Gradient Boosted Trees) classifier | Handles small tabular datasets well, gives feature importances for free — you can explain *why* a machine was flagged, which matters in front of an audience |
| C | Cox Proportional Hazards or Weibull survival model | Purpose-built for time-to-event data once you actually have failure timestamps — not worth building until Stage B's data volume exists |

**Deliberately not used:** deep learning / LSTM-style sequence models. They need far more run-to-failure data than this platform will have for a long time, and are much harder to explain in a demo. Revisit only if Stage C's data volume genuinely supports it.

---

## 6. How the prediction actually works, end to end

```
Daily batch trigger, per machine
        v
Pull last 30-60 days of normalized readings (from Unit 1's output)
        v
Compute rolling 7-day slopes per tracked signal
        v
Compute Health Index (z-score deviation vs. population prior)
        v
   -----+-----
   |         |
Stage A     Stage B (if enough labeled events exist)
(always     (Random Forest risk classification,
 runs)       runs alongside A, not instead of it)
   |         |
   -----+-----
        v
Wrap into Layer 3 output schema (event_type: maintenance_risk)
        v
Unit 5 -> Layer 4 (Digital Twin health score) + Layer 5 (maintenance ticket dispatch)
```

Stage A and B run in parallel once B exists, not as a replacement — B refines the risk tier, A remains the always-available fallback and the explainable baseline.

---

## 7. Output (what leaves this unit)

```json
{
  "event_id": "uuid",
  "machine_id": "pump_02",
  "timestamp": "2026-02-15",
  "source_unit": "predictive_maintenance",
  "event_type": "maintenance_risk",
  "severity": "alert",
  "health_index": 38.4,
  "risk_tier": "high",
  "confidence_stage": "stage_a_unsupervised",
  "contributing_features": {
    "current_r_harm_slope_7d": 0.21,
    "pf_ave_slope_7d": -0.004,
    "phase_imbalance_slope_7d": 0.18
  }
}
```

Same output contract as every other Layer 3 engine (§3 of the base architecture doc) — Layer 4/5 don't need special-case handling for this unit.

---

## 8. Plugging into the real pipeline

- **Runs as a scheduled batch job** (daily), not real-time per-reading — this is the main operational difference from the anomaly detector.
- **No separate ingestion path** — consumes Unit 1's already-computed normalized, rolling-feature stream directly.
- **One function is the integration surface:** `predict_maintenance_risk(machine_id, latest_feature_row, confidence_stage) -> schema dict`. Everything else (data pull, feature computation) is shared infrastructure, not specific to this unit.
- **Feeds two places directly:** Layer 4's Digital Twin (machine health score on the 3D model) and Layer 5's Intelligence layer (automated maintenance ticket dispatch, routed to a team based on which feature triggered the flag).

---

## 9. What to actually demo

1. Health Index chart: degrading machine curve visibly separating from a healthy machine's flat line — this is the single clearest visual for a senior audience.
2. Change-point detection catching the shift before it's obvious on the raw chart — shows the system is "ahead," not just reactive.
3. Feature importance from the Stage B classifier — shows *why* a machine was flagged, not just that it was.
4. Be upfront, in the room, that Stage B is running on synthetic labels for now — this is exactly the kind of honesty that made the anomaly-detection cold-start story credible, and the same principle protects this unit under questioning.

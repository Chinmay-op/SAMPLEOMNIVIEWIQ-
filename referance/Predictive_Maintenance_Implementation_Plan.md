# Predictive Maintenance — Implementation Plan (Stage 0 → Stage C)

**Reads alongside:** `Predictive_Maintenance_Build_Spec.md` (the what/why/algorithms), `Predictive_Maintenance_Prototype.ipynb` (the proof-of-mechanics). This document is the *when* and *in what order*.

---

## 0. What each stage achieves, at a glance

| Stage | Unlocks | Depends on |
|---|---|---|
| 0 — Foundation | Nothing user-facing yet — this is the plumbing everything else needs | Nothing — start immediately |
| A — Health Index | A working, demoable predictive maintenance feature on day one, zero failure history required | Stage 0 complete |
| B — Risk Classifier | Sharper, learned risk tiering that improves as real usage accumulates | ~10–20 real logged maintenance events |
| C — Survival/RUL | Actual "days until likely failure" estimates — the most commercially compelling capability | Months of accumulated failure history across the fleet |

The honest framing for any stakeholder conversation: **Stage A ships now. Stage B and C are roadmap, gated by data the team doesn't control the speed of.**

---

## Stage 0 — Foundation (before any model code)

**Goal:** everything Stage A needs to exist is in place — nothing modeling-related happens yet.

### Tasks
- [ ] **Confirm the equipment class list** for the demo/initial site(s) — this determines how many sets of population priors need sourcing (reuse the list already being built for Layer 0's onboarding).
- [ ] **Source population-prior baselines per equipment class** — manufacturer spec sheets where available, team-estimated ranges elsewhere. Own this decision explicitly (see open question in the base architecture doc, §14 of the Layer 4 doc raised the same question for Rule Templates — same owner makes sense here).
- [ ] **Extend the Layer 0 config schema** to carry these priors (already scoped in `Layer3_Model_Layer_Technical_Architecture.md`, §8) — this is a config change, not new code, consistent with the platform's core doctrine.
- [ ] **Define "maintenance event" as a logged data structure** — this was left open last time and needs resolving now, not when Stage B starts. Minimum fields: `machine_id`, `event_date`, `event_type` (repair / replace / inspection-only), `triggered_by` (system alert / manual observation), `notes`. Decide *where* this gets logged — a new table, or reuse Layer 5's maintenance ticket system if that exists by then. This single decision determines whether Stage B has usable data when its trigger condition is met.
- [ ] **Confirm the canonical load indicator and rolling-window infrastructure from Unit 1** are actually available to pull from — Predictive Maintenance should not build its own ingestion path.
- [ ] **Set up the dev environment / repo structure** — promote the notebook's logic into a proper module (`predictive_maintenance.py` or equivalent) with the notebook kept as the test bed, not the production code path.

### Exit criteria
Can pull 30+ days of normalized, feature-engineered data for at least one machine (real or dummy) end-to-end, with equipment-class priors resolvable from config. If this doesn't work cleanly, nothing in Stage A will either — don't proceed until it does.

---

## Stage A — Health Index (the first real deliverable)

**Goal:** a production-grade, always-on predictive maintenance signal that needs zero failure history.

### Tasks
- [ ] Implement rolling-slope feature computation as a production module (the notebook's §3 logic, generalized to run per-machine on a schedule rather than once on a dataframe).
- [ ] Implement the Health Index formula, parametrized by equipment class (pulling priors from Layer 0 config, not hardcoded like the notebook demo).
- [ ] Implement CUSUM change-point detection as the early-warning layer on top of the Health Index.
- [ ] Wrap output into the Layer 3 schema (`event_type: maintenance_risk`) exactly as specified in the build spec §7.
- [ ] Deploy as a scheduled daily batch job, one run per machine.
- [ ] Wire the output into Layer 4 (machine health score shown on the Digital Twin) and Layer 5 (a stub maintenance ticket, even if dispatch routing isn't fully built yet).
- [ ] Build the demo visual: Health Index trend chart per machine, matching the notebook's §4 plot but against real/pipeline data.

### Success criteria
- On dummy or early real data, a genuinely degrading machine's Health Index visibly separates from a healthy machine's (as validated in the notebook: ~97→0 vs. staying 90–97).
- False-positive rate on the change-point detector is low enough to be defensible if questioned live.
- Daily batch job completes comfortably inside its scheduling window, per machine count at the pilot site.

### What this achieves
This is the stage worth presenting. It's real, it works without any failure-history dependency, and it's honest about being Stage A — that honesty is itself part of what makes the platform's story credible (same principle that made the anomaly-detection cold-start story land).

---

## Stage B — Supervised Risk Classifier

**Trigger to start building:** ~10–20 real logged maintenance events exist (from Stage 0's logging structure). Don't start this stage on a fixed calendar date — start it when the trigger condition is actually met.

### Tasks
- [ ] Confirm the maintenance-event logging pipeline (Stage 0) has actually been capturing usable events — audit before building on top of it.
- [ ] Build the labeled-dataset construction pipeline: join logged events to the trend features that preceded them.
- [ ] Train the Random Forest classifier (per build spec §5) on real labels instead of the notebook's synthetic ones.
- [ ] Validate on held-out events — precision/recall, and a sanity check that it outperforms Stage A alone.
- [ ] Add a retraining cadence (recommend monthly to start — revisit once you see how fast labeled data accumulates).
- [ ] Surface feature importances/explanations in whatever UI displays the risk tier — this is what makes a flagged machine's alert defensible to an operator.
- [ ] Version model artifacts — you'll want to compare a new retrain against the previous one before promoting it.

### Success criteria
The classifier measurably outperforms Stage A alone on held-out real events (not just on training data), and every flagged prediction can still be explained via contributing features — losing explainability to gain a small accuracy bump is not a good trade at this stage.

### What this achieves
Risk tiering that's learned from your actual fleet's failure patterns rather than generic population priors — sharper, and it keeps improving as more events are logged, with no architecture change required to keep benefiting from more data.

---

## Stage C — Survival / RUL Modeling

**Trigger to start building:** enough run-to-failure histories exist across the fleet — realistically months out, and only worth starting once Stage B's data volume clearly supports it. Don't pre-build this; it's roadmap, not backlog.

### Tasks (when triggered)
- [ ] Aggregate failure histories across sites/machines into a proper time-to-event dataset.
- [ ] Implement a Cox Proportional Hazards or Weibull survival model (per build spec §5).
- [ ] Validate against held-out real failures — check calibration of the actual days-to-failure estimate, not just risk ranking.
- [ ] Integrate the RUL-in-days output into Layer 5's compliance/optimization reports.

### Success criteria
RUL estimates fall within an acceptable error bound against actual failure timing — define "acceptable" with whoever owns the maintenance-scheduling decision this feeds, since that's a business tolerance, not a modeling one.

### What this achieves
The most commercially compelling capability in this unit — an actual "you have ~N days before this needs attention" figure, which is what turns predictive maintenance from "flagged as risky" into "schedule the technician for next Tuesday."

---

## Cross-cutting work, running from Stage 0 onward

These aren't a separate stage — they run in parallel throughout:

- **Config governance:** someone owns keeping equipment-class priors current as new machine types are added — same ownership question raised for Layer 0 broadly.
- **Monitoring:** track dismiss-rate on maintenance-risk alerts, distribution of confidence_stage across the fleet, and time from flag to actual technician action — same monitoring discipline used for the anomaly detection unit (base architecture doc §6).
- **Data quality:** gap handling in the daily feature pipeline needs to keep working as more machines/sites are added, not just at pilot scale.

---

## Summary Timeline

| Stage | Realistic timeframe | Gating factor |
|---|---|---|
| 0 — Foundation | 1–2 weeks | Team availability only |
| A — Health Index | 3–4 weeks after Stage 0 | Team availability only |
| B — Risk Classifier | Starts whenever 10–20 real events exist | **Not fully in the team's control** — depends on real maintenance activity being logged |
| C — Survival/RUL | Starts whenever fleet-wide failure history is sufficient | **Not fully in the team's control** — realistically months out |

Stages 0 and A are the part to commit to a calendar. B and C should be presented as data-gated milestones, not dated ones — committing a date to something outside the team's control is the kind of claim that erodes trust when it slips.

---

## Definition of Done — quick checklist

- [ ] Stage 0: config extended, priors sourced, maintenance-event logging schema live, dev pipeline pulling real feature data end-to-end
- [ ] Stage A: Health Index + change-point detection running as a daily batch job, wired into Layer 4/5, demo-ready chart working
- [ ] Stage B: classifier trained on real (not synthetic) labels, outperforms Stage A on held-out events, explainability preserved
- [ ] Stage C: RUL model validated against real failures, integrated into reporting

---

## Risks to flag now, not later

- **Stage B/C timing depends on real-world data accumulation the team can't accelerate.** Set expectations accordingly in any roadmap presented externally.
- **Prior-sourcing quality directly determines Stage A's accuracy.** If population priors are rough team estimates rather than manufacturer specs, say so — it affects how confidently Stage A's flags should be presented.
- **The maintenance-event logging schema (Stage 0) needs buy-in from whoever owns ticketing/CMMS today**, if that's a separate system from what Layer 5 builds — resolve this early, since Stage B is unbuildable without it regardless of how good the modeling work is.

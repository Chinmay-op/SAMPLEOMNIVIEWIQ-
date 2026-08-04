# Predictive Maintenance — Your To-Do Plan (Colab, plain language)

Do these phases in order. Each one has a clear "done when" line — don't move to the next phase until you hit it.

---

## Phase 1 — Set up Colab & import your real data

**You do:**
1. Open a new Google Colab notebook.
2. Mount your Google Drive:
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   ```
3. Load your real header-schema CSV:
   ```python
   import pandas as pd
   df = pd.read_csv('/content/drive/MyDrive/<your folder>/<your file>.csv')
   df.head()
   ```
4. Check the basics:
   ```python
   print(df.shape)
   print(df.columns.tolist())
   print(df['Date_time'].min(), df['Date_time'].max())
   ```

**Done when:**
- The file loads with no error.
- The columns match the 51 fields we mapped out earlier (`kW_Total`, `PF_Ave`, `Current_R/Y/B_Harm`, `Neutral_current`, etc.).
- You can see a sensible date range (not all one day, not full of gaps you weren't expecting).

---

## Phase 2 — Clean & sanity-check the data

**You do:**
1. Check for missing values: `df.isnull().sum()`
2. Check for duplicate timestamps: `df.duplicated(subset=['Date_time','Deviced_id']).sum()`
3. Plot a couple of raw fields over time to eyeball them (`kW_Total`, `PF_Ave`, `Current_R_Harm`) — just to see if the values look physically reasonable (no wild negative numbers, no impossible spikes).
4. Decide your load indicator (recommended: `Current_Total`).

**Done when:**
- You know how much missing data you have and roughly why (sensor gaps? specific machines?).
- The raw values look physically plausible on a simple plot — no obvious data-quality landmine before you build anything on top of it.

---

## Phase 3 — Build the features (preprocessing)

**You do:**
1. Normalize signals by your load indicator.
2. Compute 7-day rolling slope for: `Current_R/Y/B_Harm`, `PF_Ave`, `Neutral_current`, phase imbalance (this is the code from the prototype notebook, §3 — copy it in and run it against your real dataframe instead of the synthetic one).
3. Spot-check a few rows to make sure the slope values look sane (not all zero, not all NaN).

**Done when:**
- The feature columns exist for every machine with enough history (at least 7+ days of data).
- Spot-checked values make sense — e.g. a slope near zero for a stable period, non-zero where the raw signal is visibly trending.

---

## Phase 4 — Build the Health Index (Stage A)

**You do:**
1. Set the population-prior baseline values (mean/std per feature) — use manufacturer specs if you have them, otherwise a reasonable estimate for now (flag it as "to confirm" — don't treat it as final).
2. Run the Health Index formula (prototype notebook §4) against your real data.
3. Plot Health Index over time, per machine.

**Done when:**
- The code runs cleanly against real data with no errors.
- You get a Health Index value (0–100) for every machine, every day it has data.
- The chart is legible — even if none of your real machines are visibly degrading yet, the numbers should look stable and reasonable (mostly in a sensible range, not swinging wildly).

**Note:** your real data may not contain an actual degrading machine yet — that's fine and expected. This phase is about proving the *pipeline* works on real data, not about finding a real fault on day one.

---

## Phase 5 — Add early-warning detection

**You do:**
1. Run the CUSUM change-point function (prototype notebook §5) against each machine's real Health Index series.
2. Check whether anything gets flagged, and if so, whether it lines up with anything you already know happened to that machine.

**Done when:**
- The function runs without error on real data.
- Any flags it raises are explainable — either they line up with something real, or you can see why the model reacted (a genuine shift in the underlying values).

---

## Phase 6 — Package the output & prep to demo

**You do:**
1. Run the `predict_maintenance_risk()` function (prototype notebook §7) on your latest real data for a couple of machines.
2. Confirm the JSON output looks right — health index, risk tier, contributing features all populated correctly.
3. Save your Health Index chart as the core visual for any presentation.

**Done when:**
- You have a real JSON payload generated from real data, not the synthetic demo.
- You have one clean chart you'd be comfortable putting in front of someone senior.
- You can explain, in one sentence, why each machine's risk tier is what it is.

---

## After this: what's next (not part of this checklist)

Once Phase 6 is done, you have a working Stage A prototype on real data. The next steps — turning this into a scheduled production job, and eventually training Stage B on real logged maintenance events — are covered in `Predictive_Maintenance_Implementation_Plan.md`. Don't start those until Phase 6 here is solid; there's no point building the production wrapper around a pipeline you haven't proven on real data yet.

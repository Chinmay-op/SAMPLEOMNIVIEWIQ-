# Development Execution Log

Persistent record of Lead / agent ticket slices for OmniView IQ (bottle factory POC).  
**Agents:** append or update an entry when finishing work. See [`AGENTS.md`](../../AGENTS.md).

---

## Entry template

```markdown
### YYYY-MM-DD — OI-XX — <short title>

| Field | Value |
|-------|--------|
| Status | Planned / In Progress / Done |
| Goal | |
| Decisions | |
| Files touched | |
| Commands | |
| Tests | |
| Risks / follow-ups | |
| Next | |
```

---

## Entries

### 2026-09-11 — integration/consolidated — Gate 0 cleared (736/738 passing)

| Field | Value |
|-------|--------|
| Status | **Done** — 4 blockers resolved per DevB + DevC written confirmation |
| Confirmations | `blocker_response.md` (Chinmay/DevC) + `Blocker_Resolution_Recommendations.md` (Vibhanshu/DevB) — independent reviews, agreed on all 4 |
| B1 bot API | `seed.py` calls `generator()` (no args) everywhere; anomalies are internal Poisson timers |
| B2 sensor_type | Short-form (`electrical`, `vibration`, ...) canonical — renamed in all 7 schema `const`s and all 7 bots' emitted `sensor_type` |
| B3 bot ranges | Merged DevB `origin/production_branch@0f94d48` (realistic ambient/thermal/stroke physics) |
| B4 idle threshold | Split — `IDLE_CURRENT_THRESHOLD_A` (0.65, OI-57 rule) vs new `DASHBOARD_IDLE_CURRENT_A` (10.0, OI-68 gauge) |
| Also fixed | vibration_bot dropped 2 dead fields rejected by `additionalProperties:false`; 3 stale test fixtures brought up to the real required-field lists; `seed.py` now calls the shared `AR1Wanderer.end_tick()` once per sample — it existed but nothing called it, so the 2nd+ timestamp in any timeline collided with the 1st on thermal_bot's `mv` key |
| Tests | **736 passed / 2 failed** (was 29 failed) |
| Still open — DevB's | `test_vibration_bot` + `test_gas_bot`: the test's `set_state()` helper writes `data/live_sim_state.json`, but neither bot reads `machine_state` from it — severity is pure internal Poisson/physics state, module-global, persists across the pytest session. Confirmed non-deterministic (fails differently in isolation each run). DevB decides: wire `machine_state` in, or redesign the test |
| Next | DevB fixes the 2 remaining; then push `integration/consolidated` |

### 2026-09-08 — integration/consolidated — full-suite verification + dev-blocker list

| Field | Value |
|-------|--------|
| Status | **Merge sound; 709/738 tests pass. 29 fail — all need DevB+DevC coordination** |
| Fixed here | (1) `config.py` `CONTRACTED_DEMAND_KVA` alias — chinmay merge dropped DevC's spelling, broke 14 collections. (2) `ingest/db.py` — restored DevC's full module (`BackfillResult`, `backfill_insert`, `query_by_time_range`) + re-appended `query_window`; the merge wrongly based it on live-spine's older db.py. (3) `pyproject.toml` — added undeclared `ntplib` (DevC OI-53). |
| Venv | `uv pip install --python .venv/bin/python -e ".[dev]"` — pulls sqlalchemy / psycopg2 / paho / jsonschema / ntplib |
| Lead suites | Rules + HD-parity + Owner + SiteProfile + adapters — **all green (48/48 + domain)** |
| BLOCKER 1 — bot API | DevB's rewritten bots expose `generate_reading()` (no args; anomaly internal via `get_poisson_anomaly()`). DevC's `ingest/seed.py:297` calls `generator(is_anomaly=False)`. Breaks 19 `test_seed.py`. **Decision needed:** DevC updates `seed.py` to the new bot API, or DevB restores the `is_anomaly` kwarg. |
| BLOCKER 2 — schema `sensor_type` | DevB schemas freeze `electrical_meter / vibration_node / thermal_probe / pressure_transmitter / gas_particle_sensor / digital_pulse_counter / ambient_weather`; Layer 3 contract §2 + DevC `SENSOR_TYPES` freeze `electrical / vibration / thermal / pressure / gas / stroke / ambient`. Breaks 2 `test_validation.py` + 3 `test_subscriber.py` + `test_bots.py::test_vibration_bot`. **Decision needed:** align on the 7 const values + which `data` fields are `required` (DevB's new strict schemas add `z_axis_kurtosis`, `voltage_v_l1_n`, `delta_active_energy_kwh`, … that DevC payloads omit). |
| BLOCKER 3 — bot value ranges | DevB's physics rewrite changed output ranges; DevB's own `test_bots.py` still asserts old ranges (electrical 119 vs `>250`, ambient 42.8 vs `<=40`, gas missing `NORMAL`). **DevB updates their bot-test expectations.** |
| BLOCKER 4 — idle threshold | `test_dashboard_queries.py::test_detects_idle_by_low_current` expects idle at 5 A; dashboard now reads Lead's `IDLE_CURRENT_THRESHOLD_A = 0.65` (merge kept Lead's OI-57 value over DevC's OI-68 `10.0`). **DevC confirms:** dashboard "% idle" gauge should call `get_idle_current_threshold_a()` (and test sets it), or dashboard idle % gets its own threshold distinct from the lazy-idle rule. |
| Next | Circulate blockers 1–4 to DevB/DevC; apply agreed fixes on `integration/consolidated`; then push |

### 2026-09-08 — integration/consolidated — merge all 3 lanes + HD-graph

| Field | Value |
|-------|--------|
| Status | **Done (local; HD-graph pushed, consolidated branch not pushed)** |
| Goal | One up-to-date branch for Lead/DevB/DevC to resume from — folds in DevC `chinmay` (+7), DevB `production_branch` (+8), Lead `yash` (+3), and the uncommitted HD-graph Rounds 1–8 remediation |
| Base | `origin/integration/live-spine` (`5704e49`) |
| HD-graph | Committed in its own repo as `dde6a95`, pushed to `Gritsama-Technologies/HD-graph` `main`. Superproject pointer bumped |
| Datasets | `data/sensor_datasets/*.csv` (7 × ~43k lines) and `synthetic_data/output/*.parquet` deliberately NOT carried onto this branch — gitignored; they remain on `origin/production_branch`. Regenerate locally from the edge/bots generators |
| Conflicts | `config.py` union (Lead OI-57 thresholds win over DevC OI-68 dupes; DevC NTP/dash/alert + DevB OI-40 calibration appended). `ingest/db.py` union. `rules/__init__.py` Lead + DevC action_cards. DevC OI-74 test → `test_site_walkthrough.py`. 7 edge bots → DevB rewrite. 8 `synthetic_data/*_simulator.py` → DevB deletion accepted |
| Tests | Lead rule + domain suite **48 passed**. Ingest/edge suites need `pip install -e ".[dev]"` (sqlalchemy/psycopg2/paho now in merged pyproject) |
| Follow-ups | (1) DevB schema `sensor_type` consts still mismatch the frozen 7 — Phase B. (2) `integration/consolidated` not pushed — awaiting review |
| Next | `pip install -e ".[dev]"`; review; push `integration/consolidated`; live-spine Docker smoke |

### 2026-08-17 — integration/live-spine docs + live Owner slice

| Field | Value |
|-------|--------|
| Status | **Done on `integration/live-spine` (push requested)** |
| Goal | Document merged DevB∪DevC∪yash branch; land adapters / vib / motor / TSDB window / Owner UI |
| Decisions | Stables untouched; `OMNIVIEW_OWNER_FEED=tsdb` when compose is up; CSV/correlated remains synthetic offline |
| Files touched | `Docs/DS/INTEGRATION_LIVE_SPINE.md`, explainer, Owner BFF/UI, `src/omniview/adapters/`, `vibration_zone.py`, `detectors_live.py`, `ingest/db.py` `query_window` |
| Tests | `tests/test_vibration_zone.py`, `tests/test_adapters_wire.py` |
| Risks / follow-ups | MQTT→TSDB compose smoke needs Docker |
| Next | Optional PR slices back to stables — never dump onto `yash` as daily target |


### 2026-08-15 — Correlated triplet showcase (Owner BFF + UI)

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Replace remapped-master showcase with three physics-correlated raws; wire Owner KPI/correlation without a new master CSV SoT |
| Decisions | Default feed = correlated when index present; `OMNIVIEW_OWNER_FEED=master` opt-in; leave pack raws + `master_aligned.csv` untouched; humidity/ISO vib not invented |
| Files touched | `generate_correlated_triplet.py`, `correlated_feed.py`, `backend/app.py`, Owner UI banner/Power/Correlation, `smoke_bff.py`, `docs/CORRELATED_TRIPLET.md` + catalog/contracts, HD honesty strip, this log |
| Commands | `generate_correlated_triplet.py`; BFF `:8020`; `smoke_bff.py` |
| Tests | Smoke: `correlated_shared_clock`, motor↔kW Pearson > 0.5, forecast from synthetic processed HD |
| Risks / follow-ups | Narrow `plant_correlated_raw.csv` is experimental only; HD `:5173` still campus-default |
| Next | Demo Owner `:5175` correlation + Power phase richness |

### 2026-08-15 — Unified synthetic plant raw (correlated)

| Field | Value |
|-------|--------|
| Status | **Superseded** (narrow unified CSV; see triplet entry above) |
| Goal | New synthetic raw where motor load, machine kW, transformer demand, and pressure share locked physics (fix master remapping honesty gap) |
| Decisions | Separate CSV under `data/synthetic/`; leave MetroPT/HD/Idle and `master_aligned.csv` untouched; every row `synthetic=true` |
| Files touched | `Owner-dashboard/scripts/generate_correlated_plant_raw.py`, `data/synthetic/*`, `docs/SYNTHETIC_PLANT_RAW.md`, this log |
| Commands | `generate_correlated_plant_raw.py` |
| Tests | Self-check: 10080 rows; motor↔machine_kw Pearson ≈ 0.999; loaded mean kW > offload |
| Risks / follow-ups | Replaced as showcase SoT by three-file triplet |
| Next | — |

### 2026-08-15 — Full HD master corpus + Owner wire-up

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Replace 4-day/6h master with all ~260 HD days × 1440-min grid; HD carry-forward; Pressure/Idle round-robin + honesty flags; BFF/smoke for scale |
| Decisions | `demo_day` = HD calendar; `hd_day == demo_day`; cycled MetroPT/Idle not independent ML labels; default downsample 4000 |
| Files touched | `Owner-dashboard/scripts/build_master_timeline.py`, `data/master/*`, docs, `backend/app.py` day index, `smoke_bff.py`, this log |
| Commands | `build_master_timeline.py`; uvicorn `:8020`; `smoke_bff.py`; `graphify update .` |
| Tests | Smoke: day_count=260, dense day 1440 rows, forecast96=96, correlation OK |
| Risks / follow-ups | First/last HD days may be partial; Pressure/Idle tiled — not unique fault days |
| Next | Site meters for real machine kW / co-located clocks |

### 2026-08-14 — Owner master timeline + single-machine composition

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Multi-day master corpus + Hospital-only single demo_day UI; motor load bands + machine_share_pct; 96-slot forecast; clearer rule vs ML layers |
| Decisions | Remap via build_master_timeline.py; owner_master.v1; machine share POC proxy; College/Hostel dropped from Owner chrome |
| Files touched | Owner-dashboard scripts/data/docs/backend/frontend; smoke; this log |
| Commands | build_master_timeline.py; uvicorn :8020; smoke_bff.py; graphify update |
| Tests | Smoke master + correlation + forecast96 + layers |
| Risks / follow-ups | Idle short vs 6h window; share not site-calibrated |
| Next | Site meter for real machine kW |

### 2026-08-14 — Owner POC shared timeline + sensor catalog

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Honest signal map + 3-way Power/Pressure/Idle correlation on `poc_shared_demo_clock` (elapsed remap, 60s buckets) without inventing mapping-required series |
| Decisions | Default `bucket_s=60`; `alignment: poc_shared_demo_clock` + `native_calendars`; catalog via `/api/catalog/sensors`; UI callouts for TP2/voltage/humidity/vib; demo preset airleak + idle true_positive |
| Files touched | `Owner-dashboard/docs/{SENSOR_CATALOG,CORRELATION_CONTRACT,SCREEN_MAP}.md`; `backend/app.py`; `frontend` Overview/Correlation/Power/Pressure/Idle/App/styles; `scripts/smoke_bff.py`; this log |
| Commands | `uvicorn app:app --port 8020`; `../.venv/bin/python scripts/smoke_bff.py`; `graphify update .` |
| Tests | Smoke OK: `alignment=poc_shared_demo_clock`, paired_pp=24, idle buckets=21, lazy_idle=1, mapping_required=8 |
| Risks / follow-ups | `paired_all_three` sparse (HD 15‑min vs 60s); no TP2/humidity series until adapters; vibration corpus TBD |
| Next | Optional Owner nav from SiteProfile `owner_dashboard_screens`; DevC live pipe later |

### 2026-08-14 — Base Core SiteProfile kernel

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Name the tunable Base (SiteProfile + family ingest + Layer3 detectors) so hospital vs bottle factory retarget by YAML, not a platform fork or one universal ML model |
| Decisions | Default profile `bottle_factory_poc` matches today’s knobs (POC unchanged); `hospital_campus_dev` is engine-dev, `pressure_leak` off; knob order explicit → env → profile → defaults; lab ML stays promotion-gated |
| Files touched | `Docs/DS/Base_Core_Site_Profile_ADR.md`; `profiles/*.yaml`; `src/omniview/site/`; `src/omniview/config.py`; demand/idle defaults; `AGENTS.md`; capsule; `INTEGRATION_MODULE_MAP.md` §8; Owner-dashboard SCREEN_MAP; `tests/test_site_profile.py`; this log |
| Commands | `.venv/bin/python -m pytest tests/ -q` |
| Tests | **44 passed** (5 SiteProfile + existing suite) |
| Risks / follow-ups | Owner-dashboard nav not yet wired to `detector_enabled` (contract documented). Hospital KPIs (chiller count, occupancy) remain null placeholders. |
| Next | Optional: Owner-dashboard reads `owner_dashboard_screens`; hospital survey fields → profile KPIs when OI-43/site pack confirms |

### 2026-08-14 — OI-59 — Pressure-graph remediation (band, health, leak ML)

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Fix audit defects: leak ML was a loaded-detector; promotion gate hardcoded to pass; 0–40 bar band inert on MetroPT; health score saturated on long windows |
| Decisions | Per-machine band (`metropt3-apu` 7.0–10.5, `hp-compressor` 25–40); health penalties are sample-rate based; leak ML trains loaded-only slope features with class weights + fixture holdout; negatives extracted from raw MetroPT 2020-03-28/29 (not synthesized); `evaluate` writes `out/gate_report.json`; `promote_to_layer3` stays false |
| Files touched | `src/omniview/config.py`, `src/omniview/rules/pressure_{live,health,capacity,leak}.py`; `Pressure-graph/` models/train/evaluate/replay/pack API; fixtures `metropt_quiet_unloaded.csv` + `metropt_loaded_healthy_20200328/29*.csv`; tests; pack docs; this log |
| Commands | `python main.py preprocess --from-fixtures`; `train-leak`; `train`; `evaluate`; `replay-window --start 2020-04-18T00:00:00Z --end 2020-04-18T06:00:00Z`; `.venv/bin/python -m pytest tests/ -q` |
| Tests | **39 passed**. Holdout `normal_cycle` no ML alert; holdout air-leak alerts; gate `fp=0` / `loaded_healthy_false_positive=false` / `promote_to_layer3=false`; sandbox 30 bar range warning vs site in-band; health differs by window length |
| Risks / follow-ups | Ready-for-human-review is true on this fixture suite — still lab-only until ADR. Horizon RMSE worse than persistence. Band/decay thresholds remain placeholders (OI-43). |
| Next | Human ADR if promoting leak ML; otherwise leave OI-59 as Layer3 SoT |

### 2026-08-14 — DevB + DevC model plug requirements (docs)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Lead handoff doc listing exact schema/MQTT deliverables so DevB + DevC plug into F02–F06 / HD MD path without alternate demand math |
| Decisions | One SoT doc; short MQTT topic types vs long schema consts kept both with explicit map; Lead owns adapters; edge `rolling_kva_15min` / wire `iso_health_zone` not HD truth |
| Files touched | `Docs/DS/DevB_DevC_Model_Plug_Requirements.md`; links in `AGENTS.md`, `POC_Feature_Specs/INTEGRATION_MODULE_MAP.md`, `OmniView_Agent_Context_Capsule.md`; this log |
| Commands | N/A (docs) |
| Tests | N/A |
| Risks / follow-ups | Implement Lead adapters; DevC injector rename to Vib field names; DevB add `schema_version` + restore notebook on merge |
| Next | `mqtt_to_md_sample` adapter + joint acceptance demo |

### 2026-08-17 — integration/live-spine docs + live Owner slice

| Field | Value |
|-------|--------|
| Status | **Done on `integration/live-spine` (push requested)** |
| Goal | Document merged DevB∪DevC∪yash branch; land adapters / vib / motor / TSDB window / Owner UI |
| Decisions | Stables untouched; `OMNIVIEW_OWNER_FEED=tsdb` when compose is up; CSV/correlated remains synthetic offline |
| Files touched | `Docs/DS/INTEGRATION_LIVE_SPINE.md`, explainer, Owner BFF/UI, `src/omniview/adapters/`, `vibration_zone.py`, `detectors_live.py`, `ingest/db.py` `query_window` |
| Tests | `tests/test_vibration_zone.py`, `tests/test_adapters_wire.py` |
| Risks / follow-ups | MQTT→TSDB compose smoke needs Docker |
| Next | Optional PR slices back to stables — never dump onto `yash` as daily target |

### 2026-08-15 — Correlated triplet showcase (Owner BFF + UI)

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Replace remapped-master showcase with three physics-correlated raws; wire Owner KPI/correlation without a new master CSV SoT |
| Decisions | Default feed = correlated when index present; `OMNIVIEW_OWNER_FEED=master` opt-in; leave pack raws + `master_aligned.csv` untouched; humidity/ISO vib not invented |
| Files touched | `generate_correlated_triplet.py`, `correlated_feed.py`, `backend/app.py`, Owner UI banner/Power/Correlation, `smoke_bff.py`, `docs/CORRELATED_TRIPLET.md` + catalog/contracts, HD honesty strip, this log |
| Commands | `generate_correlated_triplet.py`; BFF `:8020`; `smoke_bff.py` |
| Tests | Smoke: `correlated_shared_clock`, motor↔kW Pearson > 0.5, forecast from synthetic processed HD |
| Risks / follow-ups | Narrow `plant_correlated_raw.csv` is experimental only; HD `:5173` still campus-default |
| Next | Demo Owner `:5175` correlation + Power phase richness |

### 2026-08-15 — Unified synthetic plant raw (correlated)

| Field | Value |
|-------|--------|
| Status | **Superseded** (narrow unified CSV; see triplet entry above) |
| Goal | New synthetic raw where motor load, machine kW, transformer demand, and pressure share locked physics (fix master remapping honesty gap) |
| Decisions | Separate CSV under `data/synthetic/`; leave MetroPT/HD/Idle and `master_aligned.csv` untouched; every row `synthetic=true` |
| Files touched | `Owner-dashboard/scripts/generate_correlated_plant_raw.py`, `data/synthetic/*`, `docs/SYNTHETIC_PLANT_RAW.md`, this log |
| Commands | `generate_correlated_plant_raw.py` |
| Tests | Self-check: 10080 rows; motor↔machine_kw Pearson ≈ 0.999; loaded mean kW > offload |
| Risks / follow-ups | Replaced as showcase SoT by three-file triplet |
| Next | — |

### 2026-08-15 — Full HD master corpus + Owner wire-up

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Replace 4-day/6h master with all ~260 HD days × 1440-min grid; HD carry-forward; Pressure/Idle round-robin + honesty flags; BFF/smoke for scale |
| Decisions | `demo_day` = HD calendar; `hd_day == demo_day`; cycled MetroPT/Idle not independent ML labels; default downsample 4000 |
| Files touched | `Owner-dashboard/scripts/build_master_timeline.py`, `data/master/*`, docs, `backend/app.py` day index, `smoke_bff.py`, this log |
| Commands | `build_master_timeline.py`; uvicorn `:8020`; `smoke_bff.py`; `graphify update .` |
| Tests | Smoke: day_count=260, dense day 1440 rows, forecast96=96, correlation OK |
| Risks / follow-ups | First/last HD days may be partial; Pressure/Idle tiled — not unique fault days |
| Next | Site meters for real machine kW / co-located clocks |

### 2026-08-14 — Owner master timeline + single-machine composition

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Multi-day master corpus + Hospital-only single demo_day UI; motor load bands + machine_share_pct; 96-slot forecast; clearer rule vs ML layers |
| Decisions | Remap via build_master_timeline.py; owner_master.v1; machine share POC proxy; College/Hostel dropped from Owner chrome |
| Files touched | Owner-dashboard scripts/data/docs/backend/frontend; smoke; this log |
| Commands | build_master_timeline.py; uvicorn :8020; smoke_bff.py; graphify update |
| Tests | Smoke master + correlation + forecast96 + layers |
| Risks / follow-ups | Idle short vs 6h window; share not site-calibrated |
| Next | Site meter for real machine kW |

### 2026-08-14 — Owner POC shared timeline + sensor catalog

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Honest signal map + 3-way Power/Pressure/Idle correlation on `poc_shared_demo_clock` (elapsed remap, 60s buckets) without inventing mapping-required series |
| Decisions | Default `bucket_s=60`; `alignment: poc_shared_demo_clock` + `native_calendars`; catalog via `/api/catalog/sensors`; UI callouts for TP2/voltage/humidity/vib; demo preset airleak + idle true_positive |
| Files touched | `Owner-dashboard/docs/{SENSOR_CATALOG,CORRELATION_CONTRACT,SCREEN_MAP}.md`; `backend/app.py`; `frontend` Overview/Correlation/Power/Pressure/Idle/App/styles; `scripts/smoke_bff.py`; this log |
| Commands | `uvicorn app:app --port 8020`; `../.venv/bin/python scripts/smoke_bff.py`; `graphify update .` |
| Tests | Smoke OK: `alignment=poc_shared_demo_clock`, paired_pp=24, idle buckets=21, lazy_idle=1, mapping_required=8 |
| Risks / follow-ups | `paired_all_three` sparse (HD 15‑min vs 60s); no TP2/humidity series until adapters; vibration corpus TBD |
| Next | Optional Owner nav from SiteProfile `owner_dashboard_screens`; DevC live pipe later |

### 2026-08-14 — Base Core SiteProfile kernel

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Name the tunable Base (SiteProfile + family ingest + Layer3 detectors) so hospital vs bottle factory retarget by YAML, not a platform fork or one universal ML model |
| Decisions | Default profile `bottle_factory_poc` matches today’s knobs (POC unchanged); `hospital_campus_dev` is engine-dev, `pressure_leak` off; knob order explicit → env → profile → defaults; lab ML stays promotion-gated |
| Files touched | `Docs/DS/Base_Core_Site_Profile_ADR.md`; `profiles/*.yaml`; `src/omniview/site/`; `src/omniview/config.py`; demand/idle defaults; `AGENTS.md`; capsule; `INTEGRATION_MODULE_MAP.md` §8; Owner-dashboard SCREEN_MAP; `tests/test_site_profile.py`; this log |
| Commands | `.venv/bin/python -m pytest tests/ -q` |
| Tests | **44 passed** (5 SiteProfile + existing suite) |
| Risks / follow-ups | Owner-dashboard nav not yet wired to `detector_enabled` (contract documented). Hospital KPIs (chiller count, occupancy) remain null placeholders. |
| Next | Optional: Owner-dashboard reads `owner_dashboard_screens`; hospital survey fields → profile KPIs when OI-43/site pack confirms |

### 2026-08-14 — OI-59 — Pressure-graph remediation (band, health, leak ML)

| Field | Value |
|-------|--------|
| Status | **Done** |
| Goal | Fix audit defects: leak ML was a loaded-detector; promotion gate hardcoded to pass; 0–40 bar band inert on MetroPT; health score saturated on long windows |
| Decisions | Per-machine band (`metropt3-apu` 7.0–10.5, `hp-compressor` 25–40); health penalties are sample-rate based; leak ML trains loaded-only slope features with class weights + fixture holdout; negatives extracted from raw MetroPT 2020-03-28/29 (not synthesized); `evaluate` writes `out/gate_report.json`; `promote_to_layer3` stays false |
| Files touched | `src/omniview/config.py`, `src/omniview/rules/pressure_{live,health,capacity,leak}.py`; `Pressure-graph/` models/train/evaluate/replay/pack API; fixtures `metropt_quiet_unloaded.csv` + `metropt_loaded_healthy_20200328/29*.csv`; tests; pack docs; this log |
| Commands | `python main.py preprocess --from-fixtures`; `train-leak`; `train`; `evaluate`; `replay-window --start 2020-04-18T00:00:00Z --end 2020-04-18T06:00:00Z`; `.venv/bin/python -m pytest tests/ -q` |
| Tests | **39 passed**. Holdout `normal_cycle` no ML alert; holdout air-leak alerts; gate `fp=0` / `loaded_healthy_false_positive=false` / `promote_to_layer3=false`; sandbox 30 bar range warning vs site in-band; health differs by window length |
| Risks / follow-ups | Ready-for-human-review is true on this fixture suite — still lab-only until ADR. Horizon RMSE worse than persistence. Band/decay thresholds remain placeholders (OI-43). |
| Next | Human ADR if promoting leak ML; otherwise leave OI-59 as Layer3 SoT |

### 2026-08-14 — DevB + DevC model plug requirements (docs)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Lead handoff doc listing exact schema/MQTT deliverables so DevB + DevC plug into F02–F06 / HD MD path without alternate demand math |
| Decisions | One SoT doc; short MQTT topic types vs long schema consts kept both with explicit map; Lead owns adapters; edge `rolling_kva_15min` / wire `iso_health_zone` not HD truth |
| Files touched | `Docs/DS/DevB_DevC_Model_Plug_Requirements.md`; links in `AGENTS.md`, `POC_Feature_Specs/INTEGRATION_MODULE_MAP.md`, `OmniView_Agent_Context_Capsule.md`; this log |
| Commands | N/A (docs) |
| Tests | N/A |
| Risks / follow-ups | Implement Lead adapters; DevC injector rename to Vib field names; DevB add `schema_version` + restore notebook on merge |
| Next | `mqtt_to_md_sample` adapter + joint acceptance demo |

### 2026-08 — OI-42 — Layer3 contracts

| Field | Value |
|-------|--------|
| Status | Done |
| Goal | Freeze Layer3 event contracts; resolve dangling Layer3 architecture refs |
| Decisions | Author `Docs/architeture/Layer3_Model_Layer_Technical_Architecture.md`; include `md_risk` + later `demand_forecast` |
| Files touched | `Docs/architeture/Layer3_Model_Layer_Technical_Architecture.md`, reference link fixes |
| Tests | N/A (docs) |
| Risks / follow-ups | Event field names must stay synced with DevB/DevC |
| Next | OI-62 / OI-56 |

### 2026-08-10 — OI-56 — Live demand window + MD fixtures

| Field | Value |
|-------|--------|
| Status | Done (offline) |
| Goal | HD live-window math → `md_risk` by ~min 11 on synthetic bottle fixtures |
| Decisions | Port PowerMonitor formulation into `demand_window.py`; alert at T≥11 and projected≥contract; main-tree `src/omniview/` |
| Files touched | `src/omniview/rules/demand_window.py`, `md_risk.py`, `fixtures/demand/*`, `scripts/demo_md_risk.py`, `tests/test_*.py` |
| Commands | `.venv/bin/pytest tests/ -q`; `scripts/demo_md_risk.py` |
| Tests | 6 passed (demand window + md_risk) |
| Risks / follow-ups | MQTT wiring later; `CONTRACT_DEMAND_KVA` placeholder until OI-43; 15-min aggregated CSV weak for min-11 demo |
| Next | OI-62 PdM module |

### 2026-08-10 — OI-62 — PdM Stage A module

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Docs-first then extract notebook Stage A into `predictive_maintenance.py` |
| Decisions | Phase 0 docs before code; `DEMO_PRIORS` frozen placeholders for OI-63; synthetic fixture for CI (no heta in pytest); CUSUM defaults kept notebook-faithful (over-flag noted → OI-66) |
| Files touched | `AGENTS.md`; `Docs/DS/OmniView_Agent_Context_Capsule.md`; `Docs/DS/OI-62_Predictive_Maintenance_Module_PRD.md`; `Docs/DS/DEVELOPMENT_EXECUTION_LOG.md`; `src/omniview/rules/predictive_maintenance.py`; `src/omniview/rules/__init__.py`; `fixtures/pdm/synthetic_daily_features.json`; `tests/test_predictive_maintenance.py`; `scripts/demo_pdm.py`; `pyproject.toml` (numpy/pandas); Lead checklist OI-62 |
| Commands | `uv pip install --python .venv -e ".[dev]"`; `pytest tests/test_predictive_maintenance.py tests/test_demand_window.py tests/test_md_risk.py -q`; `python scripts/demo_pdm.py` |
| Tests | **11 passed** (5 PdM + 6 demand/md_risk); demo emits `maintenance_risk` with `synthetic: true`, HI≈49.7, risk_tier=medium on fixture |
| Risks / follow-ups | Notebook CUSUM defaults over-flag on drifting HI (12/12 flags on fixture) → OI-66; priors not site-confirmed → OI-63 |
| Next | OI-63 priors config; Sprint 1 board: OI-50 lazy-idle/leak scenarios |

### 2026-08-10 — Lead process explorer (HD-graph style UI)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Phase-wise local UI to inspect shipped Lead work (OI-42 / OI-56 / OI-62) on fixtures |
| Decisions | No Streamlit; Vite React frontend under `webapp/frontend` (target remote `Mightium/omniview-iq-poc-ui`); FastAPI bridge only — reuses existing rules; honesty banners for synthetic/placeholders |
| Files touched | `webapp/backend/app.py`, `webapp/frontend/*`, `scripts/serve_process_explorer.py`, `webapp/README.md`, `pyproject.toml` (`explorer` extra), `AGENTS.md` |
| Commands | `uv pip install --python .venv -e ".[explorer]"`; `.venv/bin/python scripts/serve_process_explorer.py`; `cd webapp/frontend && npm install && npm run dev` |
| Tests | API smoke via `/api/health`, `/api/phase/md-risk`, `/api/phase/pdm` |
| Risks / follow-ups | Push frontend to empty `omniview-iq-poc-ui` when asked; not a substitute for DevC OI-68/69 |
| Next | Optional publish UI remote; Sprint board OI-50 |

### 2026-08-11 — MD-first POC (pluggable ingest)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Lock Max Demand as POC hero; CSV/fixture E2E; freeze ingest so MQTT plugs into same `md_risk` |
| Decisions | Omniview = orchestration + intelligence; acquisition pluggable (CSV now, MQTT later); PdM parked next wave; explorer defaults to MD |
| Files touched | `Docs/DS/HD_graph_Master_Demand_Blueprint.md` §2.1; `fixtures/demand/INGEST_CONTRACT.md`; `MD_POC_DEMO_SCRIPT.md`; `HOW_TO_LOAD_DATA.md`; Layer3 §4.1 ingest pointer; `AGENTS.md`; capsule; `webapp/` MD-first nav; `tests/test_md_risk.py` CSV case |
| Commands | `pytest tests/test_demand_window.py tests/test_md_risk.py -q` (7 passed); `demo_md_risk.py --data near-miss` / `quiet` / `custom_template.csv` |
| Tests | 7 passed. Near-miss + CSV: first `md_risk` at T=11.0, projected=500 ≥ contract=500, `synthetic: true`. Quiet: 0 events |
| Risks / follow-ups | MQTT adapter (DevC) must emit ingest contract samples; `CONTRACT_DEMAND_KVA` still placeholder (OI-43) |
| Next | Plug MQTT when acquisition ready; then next POC function (not parallel PdM show) |

### 2026-08-13 — POC Feature Specs pack (F01–F09 + Integration)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Document nine agreed bottle POC features + module integration map |
| Decisions | Truth pack under `Docs/DS/POC_Feature_Specs/`; HITL; two nodes; prefer this pack over marketing `POC-fetures.md`; F03 Should/demo; F08 thin twin not FMI; F09 playbook arbitration |
| Files touched | `Docs/DS/POC_Feature_Specs/*`; `AGENTS.md`; `OmniView_Agent_Context_Capsule.md`; this log |
| Commands | N/A (docs) |
| Tests | N/A |
| Risks / follow-ups | Keep Jira synced; implement per INTEGRATION build order |
| Next | F02 Jira acceptance; F01/F08 pipe; F04–F06 detectors |

### 2026-08-13 — Pressure-graph pack (F05 / MetroPT-only)

| Field | Value |
|-------|--------|
| Status | **Completed** (docs + fixtures) |
| Goal | Standalone Pressure-graph pack mirroring Idle-graph; MetroPT-3 sole dataset for live + sandbox |
| Decisions | `pressure.v1` frozen; afumetto out of scope; fixtures MetroPT-semantic; OI-59 code not in this slice |
| Files touched | `Pressure-graph/**`; F05/README/INTEGRATION/AGENTS/F01_CONNECTOR; Idle/Vib pointer wording; this log |
| Commands | N/A (docs) |
| Tests | N/A |
| Risks / follow-ups | Download MetroPT raw locally; implement OI-59 against fixtures |
| Next | OI-59 rule module + adapter from COLUMN_MAP_METROPT3 |

### 2026-08-13 — MetroPT download + OI-59 pressure rules

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Kaggle MCP clone MetroPT-3; adapter; real air-leak fixtures; OI-59 live+leak offline |
| Decisions | MetroPT-only; `DV_eletric` spelling; 15s downsample; placeholder decay threshold 0.15 bar/min; HITL only |
| Files touched | `Pressure-graph/data/raw/*` (gitignored); `src/omniview/pressure/`; `pressure_live.py`/`pressure_leak.py`; fixtures; tests; demos; docs |
| Commands | Kaggle MCP download; `metropt_to_pressure_v1.py`; `pytest tests/test_pressure_leak.py` |
| Tests | 6 passed (`test_pressure_leak.py`) |
| Risks / follow-ups | Site WIKA map later; MQTT publish still DevC; threshold site-tune |
| Next | Wire F01 card when DevC shell ready; Idle/Vib datasets |

### 2026-08-14 — Pressure lab explorer UI (Lead webapp)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | See OI-59 rules in Lead process explorer (fixtures → chart → pressure_leak) |
| Decisions | Extend existing `webapp/` (not a second HD-graph clone); fixtures only |
| Files touched | `webapp/backend/app.py`; `PressurePanel.jsx`; `api.js`; `App.jsx`; READMEs; this log |
| Commands | Direct call `pressure_run`; serve via `scripts/serve_process_explorer.py` |
| Tests | API smoke via importing endpoint functions |
| Risks / follow-ups | Large airleak charts downsampled in UI only |
| Next | Idle/Vib datasets or DevC bind |

### 2026-08-14 — ziya07 download + OI-57 lazy-idle rules

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | `kagglehub` clone ziya07/sensor-maintenance-dataset; adapter; hand-authored FR5 fixtures; OI-57 duration-gate offline |
| Decisions | ziya07 has real co-located `Current (A)`/`Temperature (°C)` — used for threshold-range calibration only, not as a continuous stream (50 equipment IDs, ~2-day gaps); FR5's ≥15-min sustained-window fixtures hand-authored per pre-approved fallback (`source: hand`); placeholder thresholds `IDLE_TEMP_THRESHOLD_C=25.0`, `IDLE_CURRENT_THRESHOLD_A=0.65` |
| Files touched | `Idle-graph/data/raw/*` (gitignored); `Idle-graph/fixtures/*.csv`; `Idle-graph/docs/COLUMN_MAP_ZIYA07.md`; `Idle-graph/docs/DATASET_SOURCES.md`; `src/omniview/idle/`; `src/omniview/rules/lazy_idle.py`; `src/omniview/config.py`; `tests/test_lazy_idle.py`; `scripts/demo_lazy_idle.py`; `scripts/ziya07_to_idle_v1.py`; F04 spec / POC README / INTEGRATION_MODULE_MAP / AGENTS.md pointers |
| Commands | `kagglehub.dataset_download`; `pytest tests/test_lazy_idle.py`; `scripts/demo_lazy_idle.py` |
| Tests | 4 passed (`test_lazy_idle.py`); 22 passed full suite |
| Risks / follow-ups | Site temp/current sensor map later (OI-79); threshold site-tune; `Operational Status` column confirmed uncorrelated with load in ziya07 — not used |
| Next | Vibration-graph dataset (F06); wire F01/F08 card when DevC shell ready |

### 2026-08-14 — Pressure HD-parity stack (single compound)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Docs+Arch then preprocess / health / capacity / aligned-window / train / pack UI; twin deferred |
| Decisions | Single compound (not HD multi-consumer); OI-59 Layer3 SoT until ML promotion; windowed APIs not raw 208MB in browser; JSON lab models (numpy) |
| Files touched | `Pressure-graph/**` (main, preprocessing, webapp, docs); `src/omniview/rules/pressure_health.py`, `pressure_capacity.py`; tests; this log |
| Commands | `main.py preprocess --from-fixtures`; `train` / `train-leak`; `replay-window`; `pytest` pressure tests |
| Tests | `test_pressure_health_capacity.py`, `test_pressure_replay_window.py` (+ existing leak) |
| Risks / follow-ups | Full raw preprocess slow/large; human ML promotion ADR; twin plan after harness green |
| Next | Twin plan only after models tested on aligned windows |

### 2026-08-14 — Owner dashboard (Power + Pressure composition)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Independent owner-granular SPA composing HD power + Pressure leak/health/capacity with elapsed-demo correlation; Idle stub for later |
| Decisions | New `Owner-dashboard/` (not Lead/Pressure labs); BFF reads corpora on disk (no twin); correlation = elapsed-time join (`alignment: elapsed_demo`); HITL events only |
| Files touched | `Owner-dashboard/**` (docs, backend `app.py`, frontend 6 screens); `AGENTS.md` router; this log |
| Commands | `uvicorn app:app --port 8020`; `npm install && npm run build` / `npm run dev` on `:5175`; curl/BFF smoke |
| Tests | BFF smoke: health, power/pressure days+series/replay, correlation buckets, overview, events |
| Risks / follow-ups | Sandbox calendars not co-located — keep honesty banners; wire Idle-graph when F04 pack ready; live `isbm-main-feed` / `hp-compressor` adapters later |
| Next | Lazy-idle third domain in same shell; optional MD live-window from Lead fixtures beyond overlay |

### 2026-08-14 — Idle HD-parity stack (single compound)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Mirror Pressure-graph's HD-parity build for Idle-graph: preprocess / health / capacity / ML lab / aligned-window / pack UI + root Lead panel |
| Decisions | ziya07 is not continuous — `preprocessing.py`'s `build_from_fixtures` is the *primary* path (not fallback, unlike Pressure); each fixture assigned its own day-offset to avoid interleaving four scenarios that share the same 2024-01-01 clock (found during preprocessing smoke-test, fixed); OI-57 rule stays Layer3 SoT until ML promotion; serve on port 8011 (Pressure owns 8010) |
| Files touched | `Idle-graph/**` (main.py, preprocessing.py, docs/{ARCHITECTURE_HD_PARITY,PROCESSED_SCHEMA,IDLE_ML_PROMOTION}.md, webapp/, scripts/); `src/omniview/rules/idle_health.py`, `idle_capacity.py`; `webapp/backend/app.py` (+idle endpoints), `webapp/frontend/src/components/IdlePanel.jsx`, `api.js`, `App.jsx` (root Lead panel); `tests/test_idle_health_capacity.py`, `test_idle_replay_window.py`; fixed a `sys.modules` name collision between Idle/Pressure's same-named `preprocessing`/`replay_aligned_window` modules that broke `test_pressure_replay_window.py` (now isolated via `importlib`) |
| Commands | `main.py preprocess`; `train-ml`; `replay-window --start … --end …`; `pytest -q` |
| Tests | `test_idle_health_capacity.py`, `test_idle_replay_window.py` (+ existing `test_lazy_idle.py`); 32 passed full suite |
| Risks / follow-ups | Toy logistic ML model doesn't yet agree with the rule on the true-positive window (promotion gate correctly blocks it — expected, not a bug); human ML promotion ADR; twin plan after harness green |
| Next | Same HD-parity pass for Vibration-graph (F06); twin plan only after models tested on aligned windows |

### 2026-08-14 — Owner dashboard Idle wire (F04 / OI-57)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Replace Owner Idle stub with replay_aligned_window facade; Overview/Events include lazy_idle |
| Decisions | No 3-way correlation; Idle scenario/day filter independent of HD/MetroPT clocks; ML lab labeled non-Layer3; importlib unique key for Idle replay module |
| Files touched | `Owner-dashboard/backend/app.py`; `frontend/src/screens/Idle.jsx` (IdleStub removed); Overview/Events/App; docs SCREEN_MAP/CORRELATION/README; `scripts/smoke_bff.py`; AGENTS.md; this log |
| Commands | `uvicorn` `:8020`; `scripts/smoke_bff.py`; `npm run build` |
| Tests | BFF smoke: idle days/scenarios/replay (true_positive fires), overview lazy_idle_count, events HITL card |
| Risks / follow-ups | ML still disagrees on true-positive (lab only); live site adapters later |
| Next | Vibration-graph HD-parity; optional 3-way correlation after co-located capture |

### 2026-08-10 — Lead process explorer (HD-graph style UI)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Phase-wise local UI to inspect shipped Lead work (OI-42 / OI-56 / OI-62) on fixtures |
| Decisions | No Streamlit; Vite React frontend under `webapp/frontend` (target remote `Mightium/omniview-iq-poc-ui`); FastAPI bridge only — reuses existing rules; honesty banners for synthetic/placeholders |
| Files touched | `webapp/backend/app.py`, `webapp/frontend/*`, `scripts/serve_process_explorer.py`, `webapp/README.md`, `pyproject.toml` (`explorer` extra), `AGENTS.md` |
| Commands | `uv pip install --python .venv -e ".[explorer]"`; `.venv/bin/python scripts/serve_process_explorer.py`; `cd webapp/frontend && npm install && npm run dev` |
| Tests | API smoke via `/api/health`, `/api/phase/md-risk`, `/api/phase/pdm` |
| Risks / follow-ups | Push frontend to empty `omniview-iq-poc-ui` when asked; not a substitute for DevC OI-68/69 |
| Next | Optional publish UI remote; Sprint board OI-50 |

### 2026-08-11 — MD-first POC (pluggable ingest)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Lock Max Demand as POC hero; CSV/fixture E2E; freeze ingest so MQTT plugs into same `md_risk` |
| Decisions | Omniview = orchestration + intelligence; acquisition pluggable (CSV now, MQTT later); PdM parked next wave; explorer defaults to MD |
| Files touched | `Docs/DS/HD_graph_Master_Demand_Blueprint.md` §2.1; `fixtures/demand/INGEST_CONTRACT.md`; `MD_POC_DEMO_SCRIPT.md`; `HOW_TO_LOAD_DATA.md`; Layer3 §4.1 ingest pointer; `AGENTS.md`; capsule; `webapp/` MD-first nav; `tests/test_md_risk.py` CSV case |
| Commands | `pytest tests/test_demand_window.py tests/test_md_risk.py -q` (7 passed); `demo_md_risk.py --data near-miss` / `quiet` / `custom_template.csv` |
| Tests | 7 passed. Near-miss + CSV: first `md_risk` at T=11.0, projected=500 ≥ contract=500, `synthetic: true`. Quiet: 0 events |
| Risks / follow-ups | MQTT adapter (DevC) must emit ingest contract samples; `CONTRACT_DEMAND_KVA` still placeholder (OI-43) |
| Next | Plug MQTT when acquisition ready; then next POC function (not parallel PdM show) |

### 2026-08-13 — POC Feature Specs pack (F01–F09 + Integration)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Document nine agreed bottle POC features + module integration map |
| Decisions | Truth pack under `Docs/DS/POC_Feature_Specs/`; HITL; two nodes; prefer this pack over marketing `POC-fetures.md`; F03 Should/demo; F08 thin twin not FMI; F09 playbook arbitration |
| Files touched | `Docs/DS/POC_Feature_Specs/*`; `AGENTS.md`; `OmniView_Agent_Context_Capsule.md`; this log |
| Commands | N/A (docs) |
| Tests | N/A |
| Risks / follow-ups | Keep Jira synced; implement per INTEGRATION build order |
| Next | F02 Jira acceptance; F01/F08 pipe; F04–F06 detectors |

### 2026-08-13 — Pressure-graph pack (F05 / MetroPT-only)

| Field | Value |
|-------|--------|
| Status | **Completed** (docs + fixtures) |
| Goal | Standalone Pressure-graph pack mirroring Idle-graph; MetroPT-3 sole dataset for live + sandbox |
| Decisions | `pressure.v1` frozen; afumetto out of scope; fixtures MetroPT-semantic; OI-59 code not in this slice |
| Files touched | `Pressure-graph/**`; F05/README/INTEGRATION/AGENTS/F01_CONNECTOR; Idle/Vib pointer wording; this log |
| Commands | N/A (docs) |
| Tests | N/A |
| Risks / follow-ups | Download MetroPT raw locally; implement OI-59 against fixtures |
| Next | OI-59 rule module + adapter from COLUMN_MAP_METROPT3 |

### 2026-08-13 — MetroPT download + OI-59 pressure rules

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Kaggle MCP clone MetroPT-3; adapter; real air-leak fixtures; OI-59 live+leak offline |
| Decisions | MetroPT-only; `DV_eletric` spelling; 15s downsample; placeholder decay threshold 0.15 bar/min; HITL only |
| Files touched | `Pressure-graph/data/raw/*` (gitignored); `src/omniview/pressure/`; `pressure_live.py`/`pressure_leak.py`; fixtures; tests; demos; docs |
| Commands | Kaggle MCP download; `metropt_to_pressure_v1.py`; `pytest tests/test_pressure_leak.py` |
| Tests | 6 passed (`test_pressure_leak.py`) |
| Risks / follow-ups | Site WIKA map later; MQTT publish still DevC; threshold site-tune |
| Next | Wire F01 card when DevC shell ready; Idle/Vib datasets |

### 2026-08-14 — Pressure lab explorer UI (Lead webapp)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | See OI-59 rules in Lead process explorer (fixtures → chart → pressure_leak) |
| Decisions | Extend existing `webapp/` (not a second HD-graph clone); fixtures only |
| Files touched | `webapp/backend/app.py`; `PressurePanel.jsx`; `api.js`; `App.jsx`; READMEs; this log |
| Commands | Direct call `pressure_run`; serve via `scripts/serve_process_explorer.py` |
| Tests | API smoke via importing endpoint functions |
| Risks / follow-ups | Large airleak charts downsampled in UI only |
| Next | Idle/Vib datasets or DevC bind |

### 2026-08-14 — ziya07 download + OI-57 lazy-idle rules

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | `kagglehub` clone ziya07/sensor-maintenance-dataset; adapter; hand-authored FR5 fixtures; OI-57 duration-gate offline |
| Decisions | ziya07 has real co-located `Current (A)`/`Temperature (°C)` — used for threshold-range calibration only, not as a continuous stream (50 equipment IDs, ~2-day gaps); FR5's ≥15-min sustained-window fixtures hand-authored per pre-approved fallback (`source: hand`); placeholder thresholds `IDLE_TEMP_THRESHOLD_C=25.0`, `IDLE_CURRENT_THRESHOLD_A=0.65` |
| Files touched | `Idle-graph/data/raw/*` (gitignored); `Idle-graph/fixtures/*.csv`; `Idle-graph/docs/COLUMN_MAP_ZIYA07.md`; `Idle-graph/docs/DATASET_SOURCES.md`; `src/omniview/idle/`; `src/omniview/rules/lazy_idle.py`; `src/omniview/config.py`; `tests/test_lazy_idle.py`; `scripts/demo_lazy_idle.py`; `scripts/ziya07_to_idle_v1.py`; F04 spec / POC README / INTEGRATION_MODULE_MAP / AGENTS.md pointers |
| Commands | `kagglehub.dataset_download`; `pytest tests/test_lazy_idle.py`; `scripts/demo_lazy_idle.py` |
| Tests | 4 passed (`test_lazy_idle.py`); 22 passed full suite |
| Risks / follow-ups | Site temp/current sensor map later (OI-79); threshold site-tune; `Operational Status` column confirmed uncorrelated with load in ziya07 — not used |
| Next | Vibration-graph dataset (F06); wire F01/F08 card when DevC shell ready |

### 2026-08-14 — Pressure HD-parity stack (single compound)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Docs+Arch then preprocess / health / capacity / aligned-window / train / pack UI; twin deferred |
| Decisions | Single compound (not HD multi-consumer); OI-59 Layer3 SoT until ML promotion; windowed APIs not raw 208MB in browser; JSON lab models (numpy) |
| Files touched | `Pressure-graph/**` (main, preprocessing, webapp, docs); `src/omniview/rules/pressure_health.py`, `pressure_capacity.py`; tests; this log |
| Commands | `main.py preprocess --from-fixtures`; `train` / `train-leak`; `replay-window`; `pytest` pressure tests |
| Tests | `test_pressure_health_capacity.py`, `test_pressure_replay_window.py` (+ existing leak) |
| Risks / follow-ups | Full raw preprocess slow/large; human ML promotion ADR; twin plan after harness green |
| Next | Twin plan only after models tested on aligned windows |

### 2026-08-14 — Owner dashboard (Power + Pressure composition)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Independent owner-granular SPA composing HD power + Pressure leak/health/capacity with elapsed-demo correlation; Idle stub for later |
| Decisions | New `Owner-dashboard/` (not Lead/Pressure labs); BFF reads corpora on disk (no twin); correlation = elapsed-time join (`alignment: elapsed_demo`); HITL events only |
| Files touched | `Owner-dashboard/**` (docs, backend `app.py`, frontend 6 screens); `AGENTS.md` router; this log |
| Commands | `uvicorn app:app --port 8020`; `npm install && npm run build` / `npm run dev` on `:5175`; curl/BFF smoke |
| Tests | BFF smoke: health, power/pressure days+series/replay, correlation buckets, overview, events |
| Risks / follow-ups | Sandbox calendars not co-located — keep honesty banners; wire Idle-graph when F04 pack ready; live `isbm-main-feed` / `hp-compressor` adapters later |
| Next | Lazy-idle third domain in same shell; optional MD live-window from Lead fixtures beyond overlay |

### 2026-08-14 — Idle HD-parity stack (single compound)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Mirror Pressure-graph's HD-parity build for Idle-graph: preprocess / health / capacity / ML lab / aligned-window / pack UI + root Lead panel |
| Decisions | ziya07 is not continuous — `preprocessing.py`'s `build_from_fixtures` is the *primary* path (not fallback, unlike Pressure); each fixture assigned its own day-offset to avoid interleaving four scenarios that share the same 2024-01-01 clock (found during preprocessing smoke-test, fixed); OI-57 rule stays Layer3 SoT until ML promotion; serve on port 8011 (Pressure owns 8010) |
| Files touched | `Idle-graph/**` (main.py, preprocessing.py, docs/{ARCHITECTURE_HD_PARITY,PROCESSED_SCHEMA,IDLE_ML_PROMOTION}.md, webapp/, scripts/); `src/omniview/rules/idle_health.py`, `idle_capacity.py`; `webapp/backend/app.py` (+idle endpoints), `webapp/frontend/src/components/IdlePanel.jsx`, `api.js`, `App.jsx` (root Lead panel); `tests/test_idle_health_capacity.py`, `test_idle_replay_window.py`; fixed a `sys.modules` name collision between Idle/Pressure's same-named `preprocessing`/`replay_aligned_window` modules that broke `test_pressure_replay_window.py` (now isolated via `importlib`) |
| Commands | `main.py preprocess`; `train-ml`; `replay-window --start … --end …`; `pytest -q` |
| Tests | `test_idle_health_capacity.py`, `test_idle_replay_window.py` (+ existing `test_lazy_idle.py`); 32 passed full suite |
| Risks / follow-ups | Toy logistic ML model doesn't yet agree with the rule on the true-positive window (promotion gate correctly blocks it — expected, not a bug); human ML promotion ADR; twin plan after harness green |
| Next | Same HD-parity pass for Vibration-graph (F06); twin plan only after models tested on aligned windows |

### 2026-08-17 — Owner live spine (D0–P6 slice)

| Field | Value |
|-------|--------|
| Status | **In progress on `yash` + `integration/live-spine`** |
| Goal | Product path gen → MQTT → Timescale → adapters → Layer3 → Owner; HITL; `synthetic: true` |
| Decisions | Freeze `yash` / `Vib_branch` / `chinmay`; merge only on `integration/live-spine`; Owner `OMNIVIEW_OWNER_FEED=tsdb` when ingest exists; CSV/correlated remains offline/CI |
| Files touched | `Docs/DS/OWNER_LIVE_*`, `BRANCH_AND_MERGE_WORKFLOW.md`, `LIVE_PIPELINE_RUNBOOK.md`, `DETECTOR_ATTACH_MATRIX.md`, `.cursor/rules/owner-live-platform.mdc`; `src/omniview/adapters/wire.py`; `src/omniview/rules/vibration_zone.py`, `detectors_live.py`; `Owner-dashboard/` BFF+UI (Vibration/Motor); live-spine `ingest/db.py` `query_window`; this log |
| Commands | `pytest tests/test_vibration_zone.py`; Owner BFF `:8020` + UI `:5175`; `docker compose up` on live-spine when Docker is available |
| Tests | `test_vibration_zone.py`; BFF smoke adds `/api/vibration/replay` + `/api/motor/health` |
| Risks / follow-ups | Compose MQTT→TSDB smoke needs Docker; ISO bands + `CONTRACT_DEMAND_KVA` + `DEMO_PRIORS` remain placeholders; do not merge integration dump onto `yash` |
| Next | Push `integration/live-spine` + `stable/*` tags when ready; site nameplate for ISO class |

### 2026-08-14 — Owner dashboard Idle wire (F04 / OI-57)

| Field | Value |
|-------|--------|
| Status | **Completed** |
| Goal | Replace Owner Idle stub with replay_aligned_window facade; Overview/Events include lazy_idle |
| Decisions | No 3-way correlation; Idle scenario/day filter independent of HD/MetroPT clocks; ML lab labeled non-Layer3; importlib unique key for Idle replay module |
| Files touched | `Owner-dashboard/backend/app.py`; `frontend/src/screens/Idle.jsx` (IdleStub removed); Overview/Events/App; docs SCREEN_MAP/CORRELATION/README; `scripts/smoke_bff.py`; AGENTS.md; this log |
| Commands | `uvicorn` `:8020`; `scripts/smoke_bff.py`; `npm run build` |
| Tests | BFF smoke: idle days/scenarios/replay (true_positive fires), overview lazy_idle_count, events HITL card |
| Risks / follow-ups | ML still disagrees on true-positive (lab only); live site adapters later |
| Next | Vibration-graph HD-parity; optional 3-way correlation after co-located capture |

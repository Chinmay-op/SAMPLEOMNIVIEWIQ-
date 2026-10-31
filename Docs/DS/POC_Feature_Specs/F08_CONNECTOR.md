# F08 connector — thin live twin status-source map

**Companion to:** [`F08_Thin_Live_Twin.md`](F08_Thin_Live_Twin.md)
**Purpose:** Name what F08's per-node status cards read. F08 is explicitly a **subset view** of [`F01_CONNECTOR.md`](F01_CONNECTOR.md) — status only, no charts — so this doc cross-references rather than re-deriving the same source list.

## 1. Sources

Same upstream engines as `F01_CONNECTOR.md` §1 (demand supply layer, Idle-graph, Pressure-graph, Vibration-graph, Stage-A PdM) — see that doc for the full table. F08 additionally reads raw TSDB latest-value points directly (last kVA/kW/PF, temp/pressure/vib readings) for the two POC nodes, independent of whether a rule has fired.

## 2. Aggregation logic

**Latest-value reads for the two nodes, no charting.** Per `machine_id` (`isbm-main-feed`, `hp-compressor`): last reading of each instrumented signal + timestamp freshness (online/offline/stale) + any currently-active alert badge from the sources above. This is strictly a subset of F01's join — F08 exists to answer "is this node alive and what's its status," not to show trends.

## 3. Current status

Same as `F01_CONNECTOR.md` §3 — no dashboard shell exists yet (OI-68); TSDB latest-value queries (OI-54) are the other prerequisite, also not yet wired to a live pipe.

## 4. Future: orchestration layer

Once the orchestration/connector service (see `INTEGRATION_MODULE_MAP.md` §7) exists, F08's status view becomes a thin filtered read against it rather than a second independent source list — kept identical to F01's sources by construction, not by manual sync.

Here is a concise, point-wise summary of the POC features targeted for the **OmniView IQ** pilot:

### 1. Unified Architecture & Edge Ingestion

* **Six-Layer Stack:** Integrates IoT edge sensing, connectivity, digital twin modeling, predictive AI, and automated reporting into a single operational framework.
* **Multi-Modal Data Capture:** Simultaneously monitors electrical parameters (3-phase kVA/kW, power factor, up to 31st-order harmonics) and mechanical health (ISO 10816-3 RMS vibration, surface temperature, pneumatic pressure).
* **Zero-Perimeter-Risk Data Tunneling:** Uses an mTLS-authenticated local-host extraction agent to stream telemetry to an on-premise Kubernetes backend without exposing enterprise network perimeters.
* **Offline Resilience:** Local gateway flash storage buffers telemetry during connectivity outages and automatically backfills timestamped registers upon reconnection.

---

### 2. Predictive AI & Anomaly Detection

* **24-Hour Demand Forecasting:** Employs LSTM and XGBoost machine learning models to continuously project daily load curves and peak consumption windows.
* **Real-Time Deviation Tracking:** Automatically flags electrical/mechanical anomalies, baseline efficiency drift, unexpected machine offline states, and invisible energy waste.
* **Automated Load-Curve Flattening:** Triggers proactive peak-shaving workflows to drive a **60–70% reduction** in excess demand penalties.
* **Dynamic Mid-Cycle Recalibration:** Automatically recalibrates forecasts when machines stop or are removed mid-cycle, isolating production loss and tracking specific equipment drift.
* **ROI-Prioritized Actions:** Translates detected anomalies into prioritized optimization recommendations ranked by projected energy and financial savings.

---

### 3. Digital Twin & Sandbox Simulation

* **FMI-Compliant Modeling:** Virtualizes plant electrical and mechanical systems to simulate energy behavior and efficiency improvements.
* **Isolated Sandbox Staging:** Tests optimization rules, alert thresholds, and load-balancing scenarios safely without risking live production operations.

---

### 4. Automated dMRV & Compliance

* **Automated dMRV:** Continuously measures and verifies carbon metrics to support carbon asset generation and monetization.
* **Immutable Audit Trails:** Links tamper-evident blockchain records to hardware-bound device identities (HDID) for audit readiness.
* **ISO 14064 Tracking:** Automates greenhouse gas accounting and reporting aligned with international standards.

---

### 5. Shop-Floor Governance & Operator Visibility

* **Glanceable Shop-Floor Display:** Feeds live Modbus registers to physical jumbo LED displays for instant operator visibility on the production floor.
* **Hierarchical Alert Matrix:** Escalates multi-tiered notifications across shop-floor operators, maintenance teams, and facility managers based on event severity.
* **Multi-Tenant Security:** Enforces strict tenant isolation, role-based access control, and hardware identity verification (HDID) across all nodes.
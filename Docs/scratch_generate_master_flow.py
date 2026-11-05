import json

candidate = {
    "schema_version": 1,
    "diagram_type": "architecture",
    "meta": {
        "title": "OmniView IQ — End-to-End Master Architecture & Signal-Flow Pipeline",
        "subtitle": "Complete Hardware-to-Intelligence Flow: Sensors, Edge Resilience, 9 Detectors, Action Cards & Persona Alerts",
        "output": ".archify/architecture-master-flow-20261031-175500/master-flow.html",
        "quality_profile": "showcase",
        "visual_preset": "signal-flow"
    },
    "components": [
        # ── Col 0: Layer 1 — 7 Physical Sensors & OT Instrumentation (Plant Floor) ──
        {
            "id": "s1_elec",
            "type": "external",
            "label": "Selec MFM384 + CTs",
            "sublabel": "F02/F04: 3-Phase Power Meter",
            "tag": "kVA, kW, V, I, PF, THD (15s)",
            "pos": [40, 60],
            "size": [175, 62]
        },
        {
            "id": "s2_vib",
            "type": "external",
            "label": "Banner Q45VT / QM42VT",
            "sublabel": "F06/PdM: Dual-Axis Vibration",
            "tag": "RMS mm/s, Accel, Kurtosis (60s)",
            "pos": [40, 160],
            "size": [175, 62]
        },
        {
            "id": "s3_therm",
            "type": "external",
            "label": "Omron E5CC / RTD PT100",
            "sublabel": "F04/F07: Process Temperature",
            "tag": "Barrel PV, SP, MV% (15s)",
            "pos": [40, 260],
            "size": [175, 62]
        },
        {
            "id": "s4_press",
            "type": "external",
            "label": "WIKA Model A-10",
            "sublabel": "F05: 40-Bar Pressure Transducer",
            "tag": "0–40 bar, 4-20mA loop (60s)",
            "pos": [40, 360],
            "size": [175, 62]
        },
        {
            "id": "s5_gas",
            "type": "external",
            "label": "Schneider HeatTag",
            "sublabel": "S1: Switchboard Particle/Gas",
            "tag": "Gas PPM, Particle Index (60s)",
            "pos": [40, 460],
            "size": [175, 62]
        },
        {
            "id": "s6_stroke",
            "type": "external",
            "label": "Sick IME18 / IFM DI5009",
            "sublabel": "F06: Mold Stroke Counter",
            "tag": "24V DI Pulses, Cycle Time (15s)",
            "pos": [40, 560],
            "size": [175, 62]
        },
        {
            "id": "s7_amb",
            "type": "external",
            "label": "Schneider TH110",
            "sublabel": "F03: Ambient Weather Node",
            "tag": "Temp °C, % RH, Dew Point (60s)",
            "pos": [40, 660],
            "size": [175, 62]
        },

        # ── Col 1: Layer 2 — Edge Gateway & Hardware Resilience ──
        {
            "id": "ntp_guard",
            "type": "security",
            "label": "NTP Drift Guard",
            "sublabel": "edge/ntp_guard.py",
            "tag": "<5s Drift Cap (MSEDCL Sync)",
            "pos": [310, 160],
            "size": [190, 62]
        },
        {
            "id": "edge_gateway",
            "type": "backend",
            "label": "Teltonika RUT956",
            "sublabel": "Edge Poller & Thread Daemon",
            "tag": "RS-485 Modbus RTU / 24V DI / 4G",
            "pos": [310, 335],
            "size": [190, 130]
        },
        {
            "id": "offline_buffer",
            "type": "database",
            "label": "Offline Buffer & Replay",
            "sublabel": "offline_buffer.py & replay.py",
            "tag": "SQLite WAL FIFO | Zero Gap Drain",
            "pos": [310, 560],
            "size": [190, 72]
        },

        # ── Col 2: Layer 3 (Part 1) — Ingestion, Normalization & TimescaleDB ──
        {
            "id": "mqtt_broker",
            "type": "messagebus",
            "label": "Mosquitto Broker",
            "sublabel": "Ingestion Topic Hierarchy",
            "tag": "TLS 8883 / QoS 1 At-Least-Once",
            "pos": [580, 160],
            "size": [180, 66]
        },
        {
            "id": "subscriber_val",
            "type": "backend",
            "label": "Subscriber & Validator",
            "sublabel": "subscriber.py & validation.py",
            "tag": "7 DevB JSON Schemas Verified",
            "pos": [580, 290],
            "size": [180, 66]
        },
        {
            "id": "tsdb",
            "type": "database",
            "label": "TimescaleDB Engine",
            "sublabel": "ingest/db.py (PostgreSQL 16)",
            "tag": "7 Hypertables | ON CONFLICT DEDUP",
            "pos": [580, 420],
            "size": [180, 72]
        },
        {
            "id": "wire_adapter",
            "type": "backend",
            "label": "Canonical Wire Adapter",
            "sublabel": "adapters/wire.py",
            "tag": "Single SoT: ~87 Field Renames",
            "pos": [580, 555],
            "size": [180, 72]
        },

        # ── Col 3: Layer 3 (Part 2) — 9 Rule Engines & PdM Pipeline ──
        {
            "id": "det_md",
            "type": "backend",
            "label": "F02: MD Risk Detector",
            "sublabel": "demand_window.py",
            "tag": "500 kVA Cap | Min-11 FSM",
            "pos": [850, 60],
            "size": [205, 54]
        },
        {
            "id": "det_lazy",
            "type": "backend",
            "label": "F04: Lazy-Idle Waste",
            "sublabel": "lazy_idle.py",
            "tag": "I<0.65A + T>25°C for >=15m",
            "pos": [850, 130],
            "size": [205, 54]
        },
        {
            "id": "det_leak",
            "type": "backend",
            "label": "F05: Pressure Leak",
            "sublabel": "pressure_leak.py",
            "tag": "Decay <-0.15 bar/min Loaded",
            "pos": [850, 200],
            "size": [205, 54]
        },
        {
            "id": "det_vib",
            "type": "backend",
            "label": "F06: Vibration Zones",
            "sublabel": "vibration_zone.py",
            "tag": "ISO 10816-3 Class II (A-D)",
            "pos": [850, 270],
            "size": [205, 54]
        },
        {
            "id": "det_gas",
            "type": "backend",
            "label": "S1: Panel Overheat",
            "sublabel": "gas_model.py (Enhanced)",
            "tag": "Gas PPM + Rise >2°C/min",
            "pos": [850, 340],
            "size": [205, 54]
        },
        {
            "id": "det_stroke",
            "type": "backend",
            "label": "F06: Stroke Jam Anomaly",
            "sublabel": "stroke_jam.py",
            "tag": "Cycle >16.5s or >30s Gap",
            "pos": [850, 410],
            "size": [205, 54]
        },
        {
            "id": "det_amb",
            "type": "backend",
            "label": "F03: Ambient Chiller OLS",
            "sublabel": "ambient_correlation.py",
            "tag": "Weather vs Chiller kW OLS",
            "pos": [850, 480],
            "size": [205, 54]
        },
        {
            "id": "det_cool",
            "type": "backend",
            "label": "F07: Cooling Malfunction",
            "sublabel": "cooling_malfunction.py",
            "tag": "Power >50kW + Temp <100°C",
            "pos": [850, 550],
            "size": [205, 54]
        },
        {
            "id": "det_pdm",
            "type": "backend",
            "label": "PdM: Health Index (HI)",
            "sublabel": "predictive/health_index.py",
            "tag": "7d Slopes + Z-Score + CUSUM",
            "pos": [850, 620],
            "size": [205, 62]
        },

        # ── Col 4: Layers 4 & 5 — Arbitration, Action Synthesis & Monetization ──
        {
            "id": "conflict_arb",
            "type": "security",
            "label": "Conflict Arbitrator",
            "sublabel": "Layer 4 What-If Sandbox",
            "tag": "Safety > Compliance > Cost",
            "pos": [1145, 160],
            "size": [200, 74]
        },
        {
            "id": "action_cards",
            "type": "frontend",
            "label": "Action Card Synthesizer",
            "sublabel": "rules/action_cards.py",
            "tag": "Guidance + Do Not + ₹ Impact",
            "pos": [1145, 310],
            "size": [200, 175]
        },
        {
            "id": "monetize_engine",
            "type": "backend",
            "label": "Monetization Engine",
            "sublabel": "MSEDCL HT-I Tariff & ROI",
            "tag": "₹350/kVA Penalty | ₹340/Break",
            "pos": [1145, 555],
            "size": [200, 72]
        },

        # ── Col 5: Layer 6 — Delivery, Persona Routing, Floor Display & Dashboard ──
        {
            "id": "alert_router",
            "type": "frontend",
            "label": "Persona Alert Router",
            "sublabel": "dashboard/alert_router.py",
            "tag": "Anti-Fatigue Role Routing",
            "pos": [1430, 160],
            "size": [195, 95]
        },
        {
            "id": "jumbo_display",
            "type": "external",
            "label": "Multispan RS-6006 Jumbo",
            "sublabel": "Shop Floor LED Display",
            "tag": "Live kVA + Strobe Alert",
            "pos": [1430, 335],
            "size": [195, 80]
        },
        {
            "id": "dashboard_app",
            "type": "frontend",
            "label": "Streamlit Command Center",
            "sublabel": "dashboard/app.py",
            "tag": "4 Hero KPIs + Live Charts",
            "pos": [1430, 485],
            "size": [195, 120]
        }
    ],
    "boundaries": [
        {
            "kind": "region",
            "label": "Plant Floor & Sensing (Layer 1)",
            "wraps": ["s1_elec", "s2_vib", "s3_therm", "s4_press", "s5_gas", "s6_stroke", "s7_amb"]
        },
        {
            "kind": "security-group",
            "label": "Edge Gateway & Hardware Resilience (Layer 2)",
            "wraps": ["ntp_guard", "edge_gateway", "offline_buffer"]
        },
        {
            "kind": "region",
            "label": "Cloud Ingestion & Storage (Layer 3)",
            "wraps": ["mqtt_broker", "subscriber_val", "tsdb", "wire_adapter"]
        },
        {
            "kind": "region",
            "label": "Live Rule Engines & PdM Pipeline (Layer 3/4)",
            "wraps": ["det_md", "det_lazy", "det_leak", "det_vib", "det_gas", "det_stroke", "det_amb", "det_cool", "det_pdm"]
        },
        {
            "kind": "security-group",
            "label": "Arbitration & Monetization (Layers 4 & 5)",
            "wraps": ["conflict_arb", "action_cards", "monetize_engine"]
        },
        {
            "kind": "region",
            "label": "Delivery, Persona Alerting & Actuation (Layer 6)",
            "wraps": ["alert_router", "jumbo_display", "dashboard_app"]
        }
    ],
    "connections": [
        # Col 0 (Sensors) -> Col 1 (Edge Gateway)
        { "id": "c-s1-edge", "from": "s1_elec", "to": "edge_gateway", "fromSide": "right", "toSide": "top" },
        { "id": "c-s2-edge", "from": "s2_vib", "to": "edge_gateway", "fromSide": "right", "toSide": "top" },
        { "id": "c-s3-edge", "from": "s3_therm", "to": "edge_gateway", "fromSide": "right", "toSide": "left" },
        { "id": "c-s4-edge", "from": "s4_press", "to": "edge_gateway", "fromSide": "right", "toSide": "left" },
        { "id": "c-s5-edge", "from": "s5_gas", "to": "edge_gateway", "fromSide": "right", "toSide": "left" },
        { "id": "c-s6-edge", "from": "s6_stroke", "to": "edge_gateway", "fromSide": "right", "toSide": "bottom" },
        { "id": "c-s7-edge", "from": "s7_amb", "to": "edge_gateway", "fromSide": "right", "toSide": "bottom" },

        # Col 1 Edge Resilience Internal
        { "id": "c-edge-ntp", "from": "edge_gateway", "to": "ntp_guard", "label": "<5s clock drift", "fromSide": "top", "toSide": "bottom", "variant": "security" },
        { "id": "c-edge-buf", "from": "edge_gateway", "to": "offline_buffer", "label": "4G dropout buffer", "fromSide": "bottom", "toSide": "top", "variant": "dashed" },
        { "id": "c-buf-edge", "from": "offline_buffer", "to": "edge_gateway", "label": "FIFO replay drain", "fromSide": "top", "toSide": "bottom", "variant": "dashed" },

        # Col 1 Edge -> Col 2 Cloud Ingestion
        { "id": "c-edge-mqtt", "from": "edge_gateway", "to": "mqtt_broker", "label": "TLS 8883 / QoS 1", "fromSide": "right", "toSide": "left", "variant": "emphasis" },
        { "id": "c-mqtt-sub", "from": "mqtt_broker", "to": "subscriber_val", "fromSide": "bottom", "toSide": "top" },
        { "id": "c-sub-tsdb", "from": "subscriber_val", "to": "tsdb", "label": "Dedup Insert", "fromSide": "bottom", "toSide": "top" },
        { "id": "c-tsdb-wire", "from": "tsdb", "to": "wire_adapter", "fromSide": "bottom", "toSide": "top" },

        # Col 2 Wire Adapter -> Col 3 Detectors (Fan-Out)
        { "id": "c-wire-md", "from": "wire_adapter", "to": "det_md" },
        { "id": "c-wire-lazy", "from": "wire_adapter", "to": "det_lazy" },
        { "id": "c-wire-leak", "from": "wire_adapter", "to": "det_leak" },
        { "id": "c-wire-vib", "from": "wire_adapter", "to": "det_vib" },
        { "id": "c-wire-gas", "from": "wire_adapter", "to": "det_gas" },
        { "id": "c-wire-stroke", "from": "wire_adapter", "to": "det_stroke" },
        { "id": "c-wire-amb", "from": "wire_adapter", "to": "det_amb" },
        { "id": "c-wire-cool", "from": "wire_adapter", "to": "det_cool" },
        { "id": "c-wire-pdm", "from": "wire_adapter", "to": "det_pdm", "variant": "dashed" },

        # Col 3 Detectors -> Col 4 Action Cards & Conflict Arbitration (Fan-In)
        { "id": "c-md-card", "from": "det_md", "to": "action_cards" },
        { "id": "c-lazy-card", "from": "det_lazy", "to": "action_cards" },
        { "id": "c-leak-card", "from": "det_leak", "to": "action_cards" },
        { "id": "c-gas-card", "from": "det_gas", "to": "action_cards" },
        { "id": "c-stroke-card", "from": "det_stroke", "to": "action_cards" },
        { "id": "c-amb-card", "from": "det_amb", "to": "action_cards" },
        { "id": "c-cool-card", "from": "det_cool", "to": "action_cards" },
        { "id": "c-pdm-card", "from": "det_pdm", "to": "action_cards" },

        # Conflict Arbitration Loop
        { "id": "c-vib-arb", "from": "det_vib", "to": "conflict_arb", "variant": "security" },
        { "id": "c-md-arb", "from": "det_md", "to": "conflict_arb", "variant": "security" },
        { "id": "c-arb-card", "from": "conflict_arb", "to": "action_cards", "label": "arbitrated card", "fromSide": "bottom", "toSide": "top", "variant": "emphasis" },

        # Action Cards <-> Monetize Engine
        { "id": "c-card-mon", "from": "action_cards", "to": "monetize_engine", "label": "₹ calculate", "fromSide": "bottom", "toSide": "top" },
        { "id": "c-mon-card", "from": "monetize_engine", "to": "action_cards", "label": "rupee_impact", "fromSide": "top", "toSide": "bottom", "variant": "dashed" },

        # Col 4 Action Cards -> Col 5 Delivery & UI
        { "id": "c-card-router", "from": "action_cards", "to": "alert_router", "label": "persona cards", "fromSide": "right", "toSide": "left", "variant": "emphasis" },
        { "id": "c-router-jumbo", "from": "alert_router", "to": "jumbo_display", "label": "RS-485 strobe", "fromSide": "bottom", "toSide": "top", "variant": "emphasis" },
        { "id": "c-card-dash", "from": "action_cards", "to": "dashboard_app", "label": "live alert feed", "fromSide": "right", "toSide": "left", "variant": "emphasis" }
    ],
    "cards": [
        {
            "dot": "cyan",
            "title": "1. Field Instrumentation & Physical Signals (Layer 1 Sensing)",
            "items": [
                "Selec MFM384: 3-phase electrical power (kVA, kW, V, I, PF, THD up to 31st harmonic) polled every 15s via Modbus RTU",
                "Banner Q45VT: Triaxial vibration RMS velocity (mm/s), acceleration, crest factor, and kurtosis polled every 60s",
                "Omron E5CC: Heating zone process variable (PV °C), set-point (SP), and MV% duty cycle polled every 15s",
                "WIKA Model A-10: 0–40 bar pneumatic line pressure via 4-20mA current loop converted to Modbus digital values",
                "Schneider HeatTag: Switchboard air analysis measuring gas concentration ppm, micro-particle index, and thermal rise rate",
                "Sick IME18 / IFM DI5009: 24V DC digital pulse counter tracking completed strokes, cycle times, and machine operational state",
                "Schneider TH110: Ambient wireless room temperature (°C), relative humidity (% RH), and dew point offset"
            ]
        },
        {
            "dot": "emerald",
            "title": "2. Real-Time Detection & Predictive Maintenance (Layer 3 Intelligence)",
            "items": [
                "F02 MD Risk (demand_window.py): Exact 15-minute integration matching MSEDCL billing; alerts at Minute 11 if projected demand >= 500 kVA",
                "F04 Lazy-Idle (lazy_idle.py): Detects heating waste when barrel PV > 25°C while motor current < 0.65A sustained for >= 15 continuous minutes",
                "F05 Pressure Leak (pressure_leak.py): 5-minute linear regression slope detecting decay < -0.15 bar/min while compressor is loaded",
                "F06 Vibration Zones (vibration_zone.py): ISO 10816-3 Class II classification: Zone A (<2.8), Zone B (<7.1), Zone C Alert (<18.0), Zone D Danger (>=18.0 mm/s)",
                "S1 Panel Overheat (gas_model.py): Multi-signal correlation of gas ppm, particle index, and thermal rise rate > 2°C/min prior to visible smoke",
                "F06 Stroke Jam (stroke_jam.py): Outlier cycle time (>16.5s vs 15.0s nominal) and 30-second production gap detection while machine energized",
                "F03 Ambient Correlation (ambient_correlation.py): OLS linear regression correlating ambient temperature against chiller electrical consumption",
                "F07 Cooling Malfunction (cooling_malfunction.py): Flags opposing thermal energy when active power > 50 kW while barrel temperature < 100°C",
                "PdM Health Index (predictive_maintenance.py): 7-day rolling least-squares slopes, z-score normalization, 0–100 HI score, and CUSUM change-point drift"
            ]
        },
        {
            "dot": "amber",
            "title": "3. All Generated Alerts, Event Types & Severity Tiers",
            "items": [
                "md_nearmiss (CRITICAL): Triggered at Minute 11 when projected 15-min demand crosses 500 kVA contract limit",
                "lazy_idle (WARNING): Triggered after 15 minutes of unmonitored heater operation during breaks or mold changeovers",
                "leak_proxy (WARNING): Triggered on pneumatic pressure decay under load indicating manifold or quick-connect leakage",
                "critical_vibration (WARNING/CRITICAL): Emits Zone C alert (7.1-18 mm/s) or Zone D critical trip advisory (>=18 mm/s)",
                "gas_overheat (WARNING/CRITICAL): Emits Level 1 early warning or Level 2 critical insulation breakdown alert",
                "stroke_anomaly (WARNING): Emits cycle delay or jam event to defend machine OEE and Specific Energy Consumption (SEC)",
                "ambient_correlation (INFO/WARNING): Emits chiller efficiency drift or cooling tower fouling advisory",
                "cooling_malfunction (WARNING): Emits cooling valve stuck open, heater burnout, or sensor disconnect event",
                "maintenance_risk (WARNING/CRITICAL): Emits asset degradation alert when Health Index drops into Medium (<70) or High Risk (<40)",
                "conflict_arbitration (CRITICAL): Emits resolved multi-objective trade-off when safety shutdown threatens demand breach"
            ]
        },
        {
            "dot": "rose",
            "title": "4. Action Cards, Recommendations & Anti-Actions (Human-in-the-Loop)",
            "items": [
                "MD Risk Suggestion: Stagger non-essential auxiliary loads (grinders/chillers). DO NOT hard-trip main breaker (avoids load spikes)",
                "Lazy-Idle Suggestion: Switch barrel heaters to 140°C standby setback. DO NOT cold-shut heaters (avoids 45-min thermal recovery delay)",
                "Leak Suggestion: Audit Line 2 fittings with ultrasonic detector. DO NOT raise compressor setpoint (prevents 7%/bar electrical surge)",
                "Vibration Suggestion: Inspect bearings and coupling alignment. DO NOT restart without physical inspection if Zone D reached",
                "Panel Overheat Suggestion: Infrared scan MCC busbar terminations. DO NOT open energized switchboard without arc-flash PPE",
                "Stroke Jam Suggestion: Check mold ejector pins and pneumatic toggle. DO NOT increase hydraulic pressure to force mold closing",
                "Cooling Malfunction Suggestion: Inspect cooling circuit solenoid and RTDs during shift break. DO NOT shut down machine immediately",
                "Strict Operational Rule: All Action Cards provide guidance to operators and engineers — ZERO automatic physical actuation"
            ]
        },
        {
            "dot": "violet",
            "title": "5. Financial Monetization, MSEDCL Tariff & Projected ROI (Pune ISBM)",
            "items": [
                "F02 Demand Defense: Saves ₹35,000–₹75,000/month by avoiding MSEDCL statutory contract demand breach penalty surcharges",
                "F04 Waste Recovery: Saves ₹1,22,400/month (₹340/break) by cutting unmonitored barrel heating during shift transitions",
                "F05 Leak Recovery: Saves ₹35,000–₹65,000/month in continuous compressor motor over-compensation power consumption",
                "F06 PdM & Mechanical: Saves ₹1,80,500 net per prevented catastrophic compressor/spindle motor seizure",
                "F03 Chiller Optimization: Saves ₹1,19,232/month via heat-exchanger fouling detection and ambient setpoint tuning",
                "F06 OEE & SEC: Saves ₹35,062/month in avoided idle-loaded compressor energy waste (W5) per 1,000 bottles produced",
                "Cumulative Plant Impact: ₹4,90,000+ monthly operational savings delivered with payback period under 60 days"
            ]
        }
    ]
}

target_path = r"d:\OmniView iq\.archify\architecture-master-flow-20261031-175500\candidate.json"
with open(target_path, "w", encoding="utf-8") as f:
    json.dump(candidate, f, indent=2)

print("candidate.json updated successfully to", target_path)

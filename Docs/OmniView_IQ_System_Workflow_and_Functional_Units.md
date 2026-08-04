# OmniView IQ — System Workflow & Internal Functional Units

**Site:** ISBM-PET Bottle Manufacturing, Pune
**Purpose of this document:** trace exactly how a piece of data moves through the system, end to end, and what happens *inside* each functional unit along the way — including the time-ordered message exchanges for the scenarios that matter most to this POC.
**Companion documents:** `OmniView_IQ_POC_Plan_PRD_and_Architecture.md` (plan/PRD/cost), `OmniView_IQ_POC_Architecture_High_and_Low_Level.md` (architecture rationale)

---

## 1. How to Read This Document

Three views of the same system, each answering a different question:

- **§2 System Workflow** — the single, top-to-bottom journey of one reading, start to finish.
- **§3 Functional Units** — zoom into each stage and see what it does *internally*, independent of the others. Each unit has a defined input, a defined output, and its own internal steps.
- **§4 Sequence Diagrams** — the actual time-ordered conversation between units for five real scenarios this POC needs to prove. This is the "who talks to whom, in what order, and what do they say" view — the one that matters most for building and testing.

---

## 2. End-to-End System Workflow

```mermaid
flowchart TB
    A["Physical event<br/>e.g. compressor draws current"] --> B["Sensor captures reading"]
    B --> C["Edge gateway polls & timestamps"]
    C --> D["Gateway publishes over MQTT"]
    D --> E["Cloud ingests & stores"]
    E --> F["Feature extraction"]
    F --> G["Model layer evaluates"]
    G --> H{"Normal or anomalous?"}
    H -->|"Normal"| I["Logged, dashboard updates silently"]
    H -->|"Anomalous"| J["Conflict arbitration checks<br/>for competing goals"]
    J --> K["Monetize: translate to ₹ impact"]
    K --> L["Deliver: route to correct stakeholder"]
```

This is the same flow regardless of which physical event triggers it — a vibration spike, a pressure decay, or a current draw approaching the demand limit all travel this identical path. What changes between scenarios is only what happens at the decision diamond (H) and downstream of it — Section 4 walks through five concrete versions of this path.

---

## 3. Functional Units — Internal Workflow

Each unit below is intentionally self-contained: it has one job, a clear input, and a clear output. This is what makes the system testable piece by piece rather than only as a whole.

### 3.1 Sensing Unit (Layer 1)
**Input:** physical phenomena (current, vibration, pressure, temperature). **Output:** raw analog/digital readings on a Modbus-addressable bus.

```mermaid
flowchart LR
    A["Physical signal"] --> B["Transducer<br/>CT / MEMS / 4-20mA"]
    B --> C["Local signal conditioning"]
    C --> D["Modbus register update"]
```
The sensing unit does no interpretation — a vibration node doesn't know what "critical" means, it just continuously updates a register with the latest RMS velocity value. Keeping this unit "dumb" is deliberate: it means the sensing hardware never needs a firmware update when the anomaly-detection logic changes.

### 3.2 Edge Connectivity Unit (Layer 2)
**Input:** Modbus register values from up to four sensor types. **Output:** timestamped JSON payloads over MQTT.

```mermaid
flowchart LR
    A["Poll scheduler<br/>15s electrical / 60s physical"] --> B["Modbus master read"]
    B --> C["NTP-stamp reading"]
    C --> D{"Network available?"}
    D -->|"Yes"| E["Publish via MQTT"]
    D -->|"No"| F["Write to local buffer"]
    F --> G["Retry on interval"]
    G --> D
```
This unit's entire reason for existing is the "No" branch. Everything else here is a straightforward poll-and-forward loop; the offline buffer and retry loop are what make the system trustworthy on an unreliable cellular connection.

### 3.3 Ingestion & Storage Unit (Layer 3, part 1)
**Input:** MQTT JSON payloads. **Output:** indexed time-series records.

```mermaid
flowchart LR
    A["MQTT broker receives payload"] --> B["Validate schema & sensor tag"]
    B --> C{"Timestamp in order?"}
    C -->|"Yes"| D["Write to time-series DB"]
    C -->|"No — backfilled"| E["Insert at correct historical position"]
    E --> D
```
The branch at C is what makes offline backfill actually work: a reading that arrives late (because the gateway buffered it during an outage) still gets written into its correct place in the timeline, not appended as if it just happened.

### 3.4 Feature Extraction & Modeling Unit (Layer 3, part 2)
**Input:** raw stored readings. **Output:** an evaluated state — normal, or a specific named anomaly.

```mermaid
flowchart LR
    A["Pull latest window of readings"] --> B["Compute derived features<br/>RMS velocity, rolling kVA avg, PF"]
    B --> C{"System age"}
    C -->|"Day 1–5"| D["Apply static heuristic thresholds"]
    C -->|"Day 10+"| E["Apply trained ML model"]
    D --> F["Evaluated state"]
    E --> F
```
This is the unit responsible for the cold-start strategy: the branch at C is a literal switch that changes behavior as the system matures, without needing anyone to manually "turn on" the ML model — it activates once enough historical data exists to train it reliably.

### 3.5 Intelligence / Arbitration Unit (Layer 4)
**Input:** an evaluated anomalous state. **Output:** a single resolved action recommendation.

```mermaid
flowchart LR
    A["Anomalous state received"] --> B{"Competing goals?"}
    B -->|"No — single concern"| C["Pass through as-is"]
    B -->|"Yes — e.g. safety vs compliance"| D["Run What-If sandbox<br/>on recent telemetry snapshot"]
    D --> E["Rank by Safety > Compliance > Cost"]
    E --> F["Resolved single action recommendation"]
    C --> G["Final recommendation"]
    F --> G
```
Most events pass straight through this unit untouched (branch C) — arbitration only does real work when two goals genuinely conflict, which is the rare, high-stakes case this unit exists to handle correctly.

### 3.6 Monetize Unit (Layer 5)
**Input:** a resolved recommendation or a routine reading. **Output:** the same event, annotated with a ₹ figure.

```mermaid
flowchart LR
    A["Event with physical values<br/>e.g. kWh, kVA"] --> B["Apply MSEDCL tariff rules"]
    B --> C["Apply Time-of-Day multiplier"]
    C --> D["Compute ₹ impact"]
    D --> E["Annotated event"]
```
This unit is intentionally kept separate from the intelligence unit — tariff logic changes independently of anomaly-detection logic (e.g. if MSEDCL revises rates), and this separation means one can be updated without touching the other.

### 3.7 Deliver & Act Unit (Layer 6)
**Input:** an annotated, resolved event. **Output:** a delivered notification to exactly the right person.

```mermaid
flowchart LR
    A["Annotated event"] --> B["Look up stakeholder-routing rule"]
    B --> C{"Which role owns this?"}
    C -->|"Operator"| D["SMS + floor display"]
    C -->|"Maintenance"| E["CMMS ticket + email"]
    C -->|"Plant manager"| F["Push notification + action card"]
    C -->|"Finance/ESG"| G["Scheduled MIS report"]
```
The routing table this unit consults is what prevents alert fatigue (Section 3.3 of the architecture doc) — every event has exactly one designated recipient type, never a broadcast to all four.

---

## 4. Sequence Diagrams — Time-Ordered Scenarios

These are the conversations that actually happen between units over time. Five scenarios cover everything this POC needs to prove.

### 4.1 Routine Telemetry Cycle (the baseline, happens continuously)

```mermaid
sequenceDiagram
    participant S as Sensors
    participant GW as Edge Gateway
    participant MQ as MQTT Broker
    participant DB as Time-Series DB
    participant M as Model Layer
    participant DASH as Dashboard

    loop Every 15s (electrical) / 60s (physical)
        S->>GW: Modbus register read
        GW->>GW: NTP timestamp
        GW->>MQ: Publish JSON payload
        MQ->>DB: Store reading
        DB->>M: Evaluate against thresholds
        M-->>DASH: Update live view (state: normal)
    end
```
This loop runs continuously and silently — no alert fires, no arbitration engages. It's the background heartbeat that all the other scenarios below interrupt or extend.

### 4.2 Predictive Demand (MD) Breach Alert

```mermaid
sequenceDiagram
    participant S as Energy Sensor
    participant GW as Edge Gateway
    participant M as Model Layer
    participant MON as Monetize Unit
    participant DEL as Deliver Unit
    participant PM as Plant Manager

    S->>GW: kVA reading (15s poll)
    GW->>M: Timestamped payload
    M->>M: Update rolling 15-min kVA average
    M->>M: Forecast trajectory vs 500 kVA limit
    Note over M: At minute 11 of the window,<br/>forecast crosses 95% threshold
    M->>MON: Anomalous state: MD_BREACH_RISK
    MON->>MON: Compute ₹ penalty if unmitigated
    MON->>DEL: Annotated event (state + ₹ figure)
    DEL->>PM: Push notification + "What-If" action card
    Note over PM: ~4 minutes remain to act<br/>before the 15-min window closes
```
The critical design detail here is the **minute-11 trigger point** — chosen specifically to leave a real window for a human to act before the billing window mathematically locks in.

### 4.3 Lazy-Idle Detection

```mermaid
sequenceDiagram
    participant T as Thermal Sensor
    participant C as Current Sensor
    participant M as Model Layer
    participant DEL as Deliver Unit
    participant MT as Maintenance Engineer

    T->>M: Barrel temp reading (>250°C)
    C->>M: Current reading (<10A, idle-level)
    M->>M: Check duration of this combined state
    Note over M: Rule: temp elevated AND<br/>current idle for 15 continuous minutes
    alt Condition sustained 15 min
        M->>DEL: Anomalous state: LAZY_IDLE_EVENT
        DEL->>MT: CMMS ticket + asset history
    else Condition clears early
        M->>M: Reset timer, no alert
    end
```
This is a heuristic rule (from the Day 1–5 static-threshold branch in §3.4) — it doesn't need a trained model because the physical signature (heat without work) is unambiguous by definition.

### 4.4 Offline Outage & Chronological Backfill

```mermaid
sequenceDiagram
    participant S as Sensors
    participant GW as Edge Gateway
    participant MQ as MQTT Broker
    participant DB as Time-Series DB

    S->>GW: Readings continue every poll cycle
    Note over GW: 4G connection drops
    GW->>GW: Buffer readings locally (with timestamps)
    Note over GW: ...outage continues...
    S->>GW: More readings, still buffering
    Note over GW: 4G connection restored
    GW->>MQ: Replay buffered readings, in original order
    MQ->>DB: Insert each at its correct historical timestamp
    Note over DB: No gap in the time-series —<br/>outage is invisible downstream
```
This sequence is what makes an idle-waste capture defensible even if the network happened to drop during the very changeover event being measured — nothing downstream ever sees a gap.

### 4.5 Conflict Arbitration — Safety vs. Compliance Stress Test

```mermaid
sequenceDiagram
    participant V as Vibration Sensor
    participant M as Model Layer
    participant ARB as Arbitration Unit (D5)
    participant SIM as What-If Sandbox
    participant MON as Monetize Unit
    participant DEL as Deliver Unit
    participant PM as Plant Manager

    Note over M: Facility already at 480/500 kVA<br/>during MSEDCL peak hours
    V->>M: Vibration reading = 14.5 mm/s (Critical Zone D)
    M->>ARB: Anomalous state: CRITICAL_VIBRATION
    ARB->>ARB: Detect competing goal:<br/>hard shutdown would spike kVA past limit
    ARB->>SIM: Run scenario on recent telemetry snapshot
    SIM-->>ARB: Result: 4-min staggered deceleration<br/>+ shed 50kW non-critical load avoids both risks
    ARB->>MON: Resolved action + estimated ₹ impact avoided
    MON->>DEL: Annotated single action card
    DEL->>PM: "Shed HVAC load now. Decelerate compressor<br/>over 4 minutes. Avoids rotor failure AND ₹40,000 penalty."
```
Note that only **one** action card reaches the Plant Manager — not two competing alerts. That consolidation, happening inside the arbitration unit before anything is delivered, is the entire point of Layer 4 existing as a separate unit from Layer 6.

---

## 5. Cross-Reference — Which Functional Unit Appears in Which Sequence

| Functional Unit | 4.1 Routine | 4.2 MD Breach | 4.3 Lazy Idle | 4.4 Offline | 4.5 Arbitration |
|---|:---:|:---:|:---:|:---:|:---:|
| Sensing | ✓ | ✓ | ✓ | ✓ | ✓ |
| Edge Connectivity | ✓ | ✓ | — | ✓ | — |
| Ingestion & Storage | ✓ | — | — | ✓ | — |
| Feature Extraction & Model | ✓ | ✓ | ✓ | — | ✓ |
| Intelligence/Arbitration | — | — | — | — | ✓ |
| Monetize | — | ✓ | — | — | ✓ |
| Deliver & Act | — | ✓ | ✓ | — | ✓ |

Reading this table top to bottom for any single column tells you exactly which units need to be working — and therefore which units need to be tested — for that scenario to be demonstrable during the POC.

---

*This document is the workflow/sequence reference; system rationale lives in `OmniView_IQ_POC_Architecture_High_and_Low_Level.md`, and the full execution plan lives in `OmniView_IQ_POC_Plan_PRD_and_Architecture.md`.*

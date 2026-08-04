### 1. Gas / Particle Overheating Sensor

* **Where it will be placed:** Inside main switchboards, circuit breaker panels, and enclosed electrical distribution cabinets.
* **Purpose:** Analyzes switchboard air for micro-particles and gases released by degrading wire insulation. It detects early-stage cable or connection micro-overheating before smoke, visible damage, or electrical fires occur.

---

### 2. Vibration & Mechanical Health Sensor

* **Where it will be placed:** Mounted directly onto high-stress rotating machinery components, such as motor housings, bearing blocks, gearboxes, spindles, and pumps.
* **Purpose:** Continuously measures triaxial vibration velocity and surface temperature to detect mechanical imbalance, bearing wear, shaft misalignment, and looseness long before asset failure or unplanned downtime.

---

### 3. Surface Thermal / Process Temperature Sensor

* **Where it will be placed:** On machine heating zones, extruder barrels, heat exchangers, or critical process piping.
* **Purpose:** Monitors real-time process thermal stability to ensure machines operate within precise temperature bands, preventing poor product quality, melt-temperature defects, and excessive heating energy waste.

---

### 4. Pneumatic / Process Pressure Sensor

* **Where it will be placed:** Tapped directly into existing compressed-air intake lines, pneumatic gauge ports, or fluid pipelines on the machine.
* **Purpose:** Tracks pressure fluctuations and drops across the system to catch compressed-air leaks, compressor inefficiencies, clogged filters, and supply drops that disrupt automated machine cycles.

---

### 5. Electrical Energy Meter & Current Transformers (CTs)

* **Where it will be placed:** Inside the main electrical distribution board, Motor Control Center (MCC), or clamped around live 3-phase feeder cables supplying target machinery.
* **Purpose:** Measures active power consumption (kW/kVA), power factor, voltage/current RMS, and harmonic distortion. It identifies electrical efficiency drift, tracks peak demand, and pinpoints power quality issues without interrupting machine operation.

---

### 6. Production / Stroke Counters (Digital Pulse Sensors)

* **Where it will be placed:** On machine stroke mechanisms, molding ejection systems, conveyor output lines, or connected directly to PLC digital pulse outputs.
* **Purpose:** Counts completed production cycles, stroke throughput, and active vs. idle machine states. This data is correlated with energy consumption to calculate **energy consumed per unit produced** and Overall Equipment Effectiveness (OEE).

---

### 7. Ambient Temperature & Humidity Sensor

* **Where it will be placed:** Across the open shop floor, inside control rooms, or near temperature-sensitive production cells.
* **Purpose:** Establishes baseline ambient room conditions to correlate seasonal or environmental temperature shifts against machine cooling loads and overall facility energy demand.

---
# Name, Make, Dataset, Datasheet

### 1. Gas / Particle Overheating Sensor

* **Finalized Sensor Model:** Schneider Electric PowerLogic HeatTag
* **Official Datasheet & Technical Guide:** [Schneider Electric PowerLogic HeatTag User Guide & Technical Description](https://productinfo.se.com/heattag/doca0171xx-00-heattag/English/BM_DOCA0171%20PowerLogic%20HeatTag%20User%20Guide_0000448632.xml/$/TPC_HeatTag_Description_0000448640)
* **Public Benchmark Dataset URL:** [UCI AI4I 2020 Predictive Maintenance Dataset](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset) *(synthetic industrial dataset featuring heat dissipation and electrical overheating failure modes)*
* **Parameters We Will Be Using:**
    * Gas concentration and micro-particle index in switchboard air
    * Internal panel air temperature and overheating alert severity levels
    * Rate of thermal rise prior to visible smoke or connection failure

---

### 2. Vibration & Mechanical Health Sensor

* **Finalized Sensor Model:** Banner Engineering QM42VT / Q45VT Wireless MEMS Vibration & Temperature Node
* **Official Datasheet & Technical Guide:** [Banner Engineering QM42VT / Q45VT Official Technical Datasheet (PDF)](https://info.bannerengineering.com/cs/groups/public/documents/literature/187068.pdf)
* **Public Benchmark Dataset URL:** [Case Western Reserve University (CWRU) Bearing Data Center](http://csegroups.case.edu/bearingdatacenter/home)
* **Parameters We Will Be Using:**
    * ISO 10816-3 RMS vibration velocity (mm/s)
    * Triaxial acceleration across X, Y, and Z axes
    * Co-located mechanical surface temperature

---

### 3. Surface Thermal / Process Temperature Sensor

* **Finalized Sensor Model:** Banner Q45VT / QM42VT Co-Located Surface Probe *(or process-specific RTD/PT100 probe deployed on heating zones such as an ISBM machine barrel)*
* **Official Datasheet & Technical Guide:** [Banner Engineering QM42VT / Q45VT Official Technical Datasheet (PDF)](https://info.bannerengineering.com/cs/groups/public/documents/literature/187068.pdf)
* **Public Benchmark Dataset URL:** [Numenta Anomaly Benchmark (NAB) - Machine Temperature System Failure Dataset](https://www.kaggle.com/datasets/boltzmannbrain/nab/data)
* **Parameters We Will Be Using:**
    * Real-time surface/barrel temperature (°C)
    * Thermal rate of rise ($\Delta T / \Delta t$)
    * Thermal stability deviation from process set-point

---

### 4. Pneumatic / Process Pressure Sensor

* **Finalized Sensor Model:** WIKA Model A-10 Pressure Transmitter (0–40 bar, 4-20mA Output)
* **Official Datasheet & Technical Guide:** [WIKA A-10 Pressure Transmitter Official Operating Instructions & Datasheet (PDF)](https://www.wika.com/media/Operating-instructions/Operating-instructions/Pressure/Pressure-sensors/oi_a_10_en_de_fr_es.pdf)
* **Public Benchmark Dataset URL:** [UCI Condition Monitoring of Hydraulic & Pneumatic Systems Dataset](https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems)
* **Parameters We Will Be Using:**
    * Line supply pressure (0–40 bar range)
    * Analog 4-20mA loop current converted into digital Modbus pressure values
    * Pressure drop rate across automated cycles (compressor efficiency and leakage indicator)

---

### 5. Electrical Energy Meter & Current Transformers (CTs)

* **Finalized Sensor Model:** Selec MFM384-C-CE Multifunction Meter paired with Selec SCCT-30/20 Split-Core CTs
* **Official Datasheet & Technical Guide:**
* **Meter:** [Selec MFM384 Multifunction Meter Technical Specification Page](https://www.selec.com/product-details/multifunction-meter)
* **Split-Core CTs:** [Selec SCCT Split-Core Current Transformers Catalog Page](https://www.selec.com/product-details/split-core-current-transformer-100a)
* **Public Benchmark Dataset URL:** [UCI Steel Industry Energy Consumption Dataset](https://archive.ics.uci.edu/dataset/851/steel+industry+energy+consumption)
* **Parameters We Will Be Using:**
    * Active power consumption (kW Total and kW per-phase R/Y/B)
    * Power factor (PF Average and PF per-phase)
    * RMS current, neutral current, and line-to-line/line-to-neutral voltage
    * Voltage and current harmonic distortion (THD up to the 31st harmonic via FFT)
    * Cumulative active energy (kWh delivered/received), apparent power (VA), and reactive power (kVAR / kVARh)

---

### 6. Production / Stroke Counters (Digital Pulse Sensors)

* **Finalized Sensor Model:** Digital pulse sensor inputs wired to the Teltonika RUT956 Edge Gateway / PLC digital output or Multispan RS-6006 Jumbo LED Modbus Display counter register
* **Official Datasheet & Technical Guide:** [Multispan RS-6006 / PC-6006 Official Technical Catalog & Specification Page](https://multispanindia.com/product-detail.php/jumbo-display-programmable-counters)
* **Public Benchmark Dataset URL:** [Kaggle Manufacturing Cycle Time & OEE Dataset](https://www.kaggle.com/datasets)
* **Parameters We Will Be Using:**
    * Completed stroke / production cycle pulse count
    * Cycle duration (seconds per stroke)
    * Machine operational state (active vs. idle timestamp logs)

---

### 7. Ambient Temperature & Humidity Sensor

* **Finalized Sensor Model:** Schneider Electric PowerLogic TH110 / Easergy CL110 Wireless Ambient Sensor *(or PowerTag Ambient equivalent)*
* **Official Datasheet & Technical Guide:** [Schneider Electric MCSeT TH110 & CL110 Continuous Thermal & Ambient Monitoring Guide](https://www.se.com/in/en/download/document/BQT8678900/)
* **Public Benchmark Dataset URL:** [UCI Appliances Energy Prediction & Ambient Weather Dataset](https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction)
* **Parameters We Will Be Using:**
    * Ambient room temperature (°C)
    * Relative room humidity (% RH)
    * Environmental baseline offset against machine cooling load demand
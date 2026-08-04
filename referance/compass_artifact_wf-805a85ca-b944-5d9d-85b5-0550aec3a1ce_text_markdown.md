# Schneider Electric EcoStruxure Energy Hub — Detailed Competitive Reference (for the OmniView IQ Comparison)

## TL;DR
- **EcoStruxure Energy Hub is a cloud/SaaS energy-management application, NOT a sensor kit.** The intelligence and the licensing sit in the subscription software; the physical layer is Schneider's own metering/sensor ecosystem (PowerTag wireless energy sensors, PowerLogic/EasyLogic Modbus meters, PowerLogic HeatTag) feeding a Panel Server (PAS600/PAS800) or Site Server gateway that pushes data via MQTT-over-TLS 1.2 to Microsoft Azure (Northern Europe).
- **It is premium and subscription-locked.** Software is priced per "device credit" per year — Advanced tier is **$233 USD/device/year list** (or **$594 for 3 years**) — layered on top of hardware CapEx (PAS600 gateway ₹22k–60k in India; each PowerTag ≈ ₹25,748 MRP). A comparable 2-node industrial pilot lands the *hardware* in roughly the same ₹1.0–1.35 lakh band as OmniView IQ, but it adds a **perpetual annual software fee that OmniView IQ avoids** — so 3–5-year total cost of ownership is materially higher.
- **It is buildings-first and electrical-panel-centric.** The supported-device list contains **no machine-vibration node and no process-pressure transmitter** — precisely the measurements OmniView IQ adds for a PET-bottle plant. Energy Hub is strong on revenue-grade metering, power quality, energy-code compliance and tenant billing; it is not a machine-condition / process-monitoring product.

## Key Findings
1. Energy Hub is software-as-a-service — you cannot buy it once. Without an active subscription the app stops working; historical data is retained but locked until renewal.
2. All data must flow through a Schneider-approved gateway meeting ISA/IEC 62443. Only Panel Server (PAS600/PAS800) and Site Server are officially supported for cloud connection.
3. Data is hosted in a Microsoft Azure Tier III data center in Northern Europe, ISO 27001 certified, using TLS 1.2 / MQTT-over-HTTPS.
4. Value proposition centers on Schneider's launch claim (Boston, Apr 26, 2022) of "up to 30% in energy savings," plus footnoted claims that the SaaS model "reduces deployment time and upfront costs by up to 25% and IT maintenance costs by up to 50%," energy-code compliance (ASHRAE 90.1, IECC, Title 24, LEED, NABERS), tenant billing, and electrical-asset uptime.
5. Flagship deployment reference: **Le Grand Monarque hotel, Chartres, France** (a 600-year-old building), deployed with EcoXpert partner B2Ei using PowerLogic PowerTag sensors + EcoStruxure Panel Server; per Schneider's blog (Dec 19, 2023), "Within the initial six months, the hotel experienced a notable 15% reduction in energy usage." The case study notes monthly electricity bills had spiked to roughly $650–$750, and the dashboard exposed a spa hot tub drawing large loads overnight when unused.
6. Hardware is Schneider-proprietary and premium-priced; the ecosystem is effectively closed (best experience only with Schneider devices, though 3rd-party Modbus/pulse meters are supported with limits).

## Details

### (1) Product Overview
EcoStruxure Energy Hub launched **April 2022** (announced in Boston, Apr 26, 2022) as a "scalable, self-service IoT software-as-a-service (SaaS) solution which simplifies the management of digitalized electrical and energy systems." It is part of Schneider's **EcoStruxure for Small and Midsize Buildings** / EcoStruxure Building Activate portfolio. The product follows a three-phase maturity model: (1) Energy Compliance & Basic Awareness, (2) Energy Performance, (3) Energy Optimization.

It is explicitly a **building energy-management** product. The IT & Security Guide states: *"EcoStruxure Energy Hub is a cloud-based energy management IoT solution for buildings. It connects to smart energy devices and equipment in facilities to collect and analyze operational data."*

Marketing framing (Sophie Borgne, SVP Digital Power, Apr 26 2022 press release): *"We know buildings are responsible for 43% of CO2 emissions globally, yet roughly 90% of electrical equipment is not connected to software and monitored in real-time — meaning that a majority of businesses have no visibility into their energy usage."* (A second-phase net-zero release on Oct 12, 2022 rounds the emissions stat to "40% of global CO2 emissions.")

Access is via a web-browser portal and native iOS/Android apps.

### (2) Full Sensor / Hardware Inventory

**Gateways (required — the cloud connection point):**
- **EcoStruxure Panel Server Universal (PAS600 / PAS600L)** — the primary gateway. DIN-rail mounted. Supply: PAS600 = 110–277 VAC/DC; PAS600L = 24 VDC. Two 10/100 Base-T Ethernet RJ45 ports, one RS485 Modbus port, Wi-Fi 2.4 GHz, and an IEEE 802.15.4 wireless concentrator. Supports **up to 64 Modbus RTU slaves** and **up to ~40 IEEE 802.15.4 wireless devices**. Protocols: Modbus-SL (RS485), Modbus TCP/IP, IEEE 802.15.4 wireless, plus digital inputs on the "L" variants. Operating temperature −25 °C to +70 °C; 5–95% RH. Dimensions 71.8 × 70.2 × 85 mm. Cellular only via an **external LTE router** over Ethernet/Wi-Fi (no on-board cellular). Certifications: CE, UL/CSA, IEC 61010, IEC 62443-4-1/4-2, RCM, EAC, UKCA. Total lifecycle carbon footprint 132 kg CO₂ eq.
- **EcoStruxure Panel Server Advanced (PAS800 series)** — higher performance; Wi-Fi 2.4 & 5 GHz; PAS800P adds PoE (IEEE 802.3af / 802.3at Type 1).
- **EcoStruxure Panel Server Entry (PAS400)** — entry model, released later.
- **EcoStruxure Site Server** — alternative supported gateway for site-level cloud connection.

**Wireless energy sensors (IEEE 802.15.4 / Zigbee family):**
- **PowerLogic PowerTag Energy** — compact clip-on wireless energy sensors that mount on circuit breakers. Variants: M63, P63, F63, F160, M250, M630 (up to 630 A); rope-CT versions R120/R200/R600/R1000/R2000 (up to 2000 A). Measures active energy, active power, current, voltage and power factor per circuit; sends voltage-loss alarms with per-phase current before de-energization. Class 1 accuracy, IEC 61557-12. Example SKU: A9MEM1570 (PowerTag Flex F63 3P+N, 63 A).
- **PowerLogic Tag** (QO, E-Frame) and **PowerLogic Tag Rope** (120/600/1000/2000 A).

**Environmental / condition sensors (wireless):**
- **PowerLogic HeatTag (SMT10020)** — wireless smart sensor for early detection of cable/connection overheating by analyzing gas + micro-particles in the switchboard air; three alert severity levels; Zigbee communication; ~30 min test mode + 8 hr auto-learning before normal operation.
- **PowerTag Ambient / PowerLogic PowerTag Ambient** — ambient temperature/humidity.
- **TH110 / CL110** — wireless temperature & humidity sensors (require a downstream gateway).
- **NT935 Temperature Relay.**

**Wired energy/power meters (Modbus RS485 / TCP):**
- **EasyLogic series** (Hexa, EM1xxx/2xxx, DM6xxx, PM1xxxH, PM2xxx) — e.g. EasyLogic PM2230 (power & energy, up to 31st harmonic, RS485 Modbus RTU, Class 0.5S).
- **PowerLogic PM3000, PM5000, PM8000, EM4200, EM3500, EM6400/EM7200** power meters.
- **Acti9 iEM series** DIN-rail energy meters.
- **Embedded metering** in MasterPacT MTZ / ComPacT NSX breakers (MicroLogic X/P/H/E/A).
- **Branch-circuit meters**: HDPM6000, BCPM, EM4900.

**3rd-party device support:** 3rd-party water/gas/electricity meters via pulse inputs, and 3rd-party Modbus meters (via a custom model in EcoStruxure Power Commission Web). Note: PM8000/ION9000 have "limited support for Modbus data only."

**Architectural note for the comparison:** Energy Hub's sensor layer is entirely electrical/panel-focused. There is **no native machine-vibration node and no native process-pressure transmitter** in the supported-device list — exactly the measurements OmniView IQ adds (Banner/NCD wireless vibration+temp nodes, WIKA A-10 pressure transmitter).

### (3) Architecture / Workflow
**Sensor/meter → Gateway (Panel Server or Site Server) → Azure cloud → web/mobile app.**
- Field devices connect to the Panel Server via IEEE 802.15.4 wireless (PowerTags/HeatTag), Modbus RS485, or Modbus TCP/IP.
- The gateway aggregates and securely buffers data at the edge and is the **only** element that initiates the outbound connection.
- Transport to Schneider's cloud: *"Data transmission between the onsite gateways and the Schneider Electric cloud services is encrypted using TLS 1.2 (HTTPS)"*; *"All data transmission to the cloud uses MQTT protocol over Secure HTTP (HTTPS) using a minimum of TLS 1.2."* Only device measurement data + events are sent.
- Hosting: *"Energy Hub data is hosted in a secure Tier III Microsoft cloud service data center, certified to ISO27001."* FAQ: *"Energy Hub is hosted in a Microsoft Azure data center in Northern Europe."*
- Commissioning: EcoStruxure Power Commission (plug-and-play/auto-discovery) or embedded gateway webpages. Setup is marketed as "1-2-3": install meters/breakers → connect through a cloud gateway → configure the app with drag-and-drop in minutes.
- Browser-based; no local software install; cloud security updates auto-applied.

### (4) Features List
- **Platform:** secure cloud hosting (ISO 27001), Schneider + 3rd-party device support, historical data storage (only while subscription active), unlimited users, email + mobile push notifications (100 per device credit/month), technical support & community, iOS/Android apps, web portal, multi-site views & data aggregation.
- **Energy & sustainability:** water/gas/electricity monitoring, peak-demand monitoring & alerts, over-consumption threshold alerts, basic on-off load control & scheduling, refrigeration temperature & status monitoring, HACCP reporting, building energy-code compliance monitoring/reporting, building-area usage ranking, multi-site comparison & ranking, energy intensity & weather normalization, usage during/outside business hours, CO₂-equivalent monitoring & tracking, utility & renewables energy-flow.
- **Tenant billing:** bill-run configuration with simple rates, bill history, export to PDF.
- **Electrical power monitoring:** basic electrical alerts (interruption, overcurrent), power-quality alarms (sag/swell, transient, over/under voltage, THD), circuit-breaker trip alarms, cable-overheating alarms (via HeatTag), live electrical measurement monitoring & trending, digital electrical one-line diagram.
- **Integrations:** Data API (optional add-on subscription).

**Feature tiers:** Essential (BETA) → Advanced → + Advanced. *Essential* = simple energy monitoring for small buildings/retail. *Advanced* = single/multi-site energy analysis, insights, tenant billing. *+ Advanced* = adds electrical power monitoring + asset management (power quality, breaker trips, one-line diagram). A separate **API add-on** enables data export.

Predictive maintenance is limited: HeatTag (overheating) and electrical-asset alarms exist, but there is **no native rotating-machine vibration analytics**.

### (5) Security / IT Architecture (IT & Security Guide, 7EN02-0483-01, July 2023)
- **Secure Development Lifecycle** per ISO/IEC 27000 series; periodic penetration tests; ongoing threat modeling and privacy training.
- **Gateway requirement:** *"Energy Hub only works with gateways that meet the globally recognized ISA/IEC 62443 cybersecurity standards."* Supported: Panel Server (PAS600, PAS800), Site Server.
- **Transport:** TLS 1.2 (HTTPS), MQTT over HTTPS. The gateway initiates the connection; flow can be bi-directional; only the gateway can start it.
- **Hosting:** Microsoft Azure, Tier III, ISO 27001, Northern Europe.
- **App security:** strong password enforcement, optional 2FA/MFA, role-based access control (Viewer / Operator / Admin / Engineer / Support), non-configurable session timeout, and a Schneider Electric ID (central Customer Identity & Access Management).
- **Firewall:** gateways use standard HTTPS port 443 (same as web browsers). Three scenarios: (1) no config needed; (2) proxy configured on the gateway; (3) firewall allowlist of specific endpoints. Named endpoints include `powercloud.se.com`, `cnm-ih-na.azure-devices.net`, `*.azure-devices.net`, `cbBootStrap.gl.StruXureWareCloud.com`, `etp.prod.StruXureWareCloud.com`, `time.gl.StruXureWareCloud.com` (NTP UDP 123), `RemoteShell.rsp.Schneider-Electric.com`, and `schneider-electric-fno.flexnetoperations.com` (daily license check).
- **Data/PII:** only user name + email collected. Automated intrusion detection, full inbound/outbound logging, documented incident-response and recovery procedures.

### (6) Target Use Cases / Segments
- Commercial, industrial, and institutional buildings (mid-market C&I emphasized).
- Small & midsize buildings; retail; hotels (Le Grand Monarque); refrigeration/food service (HACCP); multi-tenant buildings needing tenant billing; data-center-adjacent panelboard monitoring (HDPM6000).
- Primary jobs-to-be-done: energy-code compliance, sustainability/net-zero reporting, energy-cost reduction, tenant accountability, electrical uptime/business continuity.
- **Not positioned for:** process-machine condition monitoring, rotating-equipment predictive maintenance, or process variables (pressure/flow) — OmniView IQ's core differentiation for a PET line.

### (7) Pricing / Cost Data Found

**Software subscription — list prices (se.com/US; carry a "subject to trade discount" disclaimer):**
| SKU | Tier / Term | List Price |
|---|---|---|
| PSWEOADVPLT12A | Advanced, 1 device credit, 1 yr | **$233.00 USD** |
| PSWEOADVPLT36A | Advanced, 1 device credit, 3 yr | **$594.00 USD** (≈ $198/yr) |
| PSWEOAPIOLT36A | API Add-On, 1 device credit, 3 yr | **$84.00 USD** |
| PSWEOPADPLT12A / 36A | "+ Advanced", 1 yr / 3 yr | Discontinued mid-2025; no public price |
| PSWEOESSPLT12A/36A | Essential | Page exists, no public price |
| Any India (INR) SKU | — | Not publicly listed (quote/login only) |

- A **device credit** = one physical device (sensor / meter / breaker). Credits are bought in whole-number increments; more devices = proportionally more subscription cost. Pricing = feature plan × device credits × term, **regardless of number of sites**. 1-year terms cost more per device/year than 3-year terms.
- A distributor net price of **$271.13** was seen for the $594 list SKU (PSWEOADVPLT36A), illustrating typical channel discounting.
- Conflict flagged: a Scribd datasheet aggregator lists $133 for PSWEOADVPLT12A vs. the live se.com $233 — treat **$233 as authoritative**.
- A third-party guide cites an EcoStruxure software band of "USD 800–8,000" and a "45-day free trial" — non-Schneider source, treat with caution (may conflate product lines).

**Hardware (India MRP / market):**
- **Panel Server PAS600 gateway:** IndiaMART listings from **₹22,000** (Crystal Controls, Ahmedabad) up to **₹60,000** (PAS600L 24 VDC, Vamtech, Bengaluru).
- **PowerTag Energy sensors (Schneider India MRP price list, w.e.f. July 15, 2025):** F63 3P+N (A9MEM1570) = **₹25,748**; F63 3P (A9MEM1573) = ₹24,522; F160 (A9MEM1580) = ₹31,666; Rope R200 = ₹59,331; R600 = ₹61,993; R1000 = ₹66,267; R2000 = ₹69,474; NSX M250 3P = ₹40,597; M250 3P+N = ₹44,495; M630 3P = ₹70,168. Global PowerTag F63 ≈ $120–193.
- **EasyLogic PM2230 meter:** ~₹14,000–26,500 street-price band (a Bangladesh distributor showed Tk 26,500 MRP / Tk 14,575 on sale; Indonesia se.com ~Rp 5–7M).
- **HeatTag SMT10020:** premium wireless sensor (India list = price-on-request).

**Illustrative "2-node-equivalent" comparison (order-of-magnitude):**
A minimal Schneider deployment (1 × PAS600 gateway + ~3 PowerTag sensors + Advanced subscription for ~3 device credits) runs approximately:
- **Hardware:** gateway ₹22k–60k + ~3 PowerTags (₹25,748 each ≈ ₹77k) ≈ **₹1.0–1.35 lakh** — broadly the SAME ballpark as OmniView IQ's ₹95k–1.2L; PLUS
- **Software:** $233/device/yr × 3 ≈ **~$700/yr (~₹60k/yr) recurring**, or ~$1,782 (~₹1.5 lakh) over 3 years.

**Interpretation:** On hardware CapEx alone the two solutions are comparable, but Schneider's deployment (a) covers a **narrower measurement scope** (electrical only — no vibration/pressure), and (b) carries a **mandatory, never-ending annual software subscription** that OmniView IQ does not. Over a 3–5-year horizon Schneider's total cost of ownership is materially higher, and the gap widens every year of the subscription.

### (8) Gaps / What Could Not Be Confirmed
- Exact **India INR subscription price** — not published; quote-only.
- Precise **Schneider-direct list price of the PAS600 gateway** (only distributor/IndiaMART figures found).
- The **full-launch eBrochure** (998-22492706) could not be fetched (file exceeded the fetch size limit); its content is corroborated via the leaflet, product pages, and press releases.
- The two **YouTube videos** are short promotional pieces (60-second / overview format); transcripts were not directly retrievable, but their described content (challenge → cloud solution → easy 1-2-3 setup) matches the leaflet messaging exactly. Video 1 ("Simplify Electrical and Energy Management") stresses energy-code compliance, net-zero goals, power reliability and electrical-system maintenance; Video 2 ("Transforming Energy Management in 60 Seconds") stresses scalable cloud IoT SaaS, intuitive setup and data visualization for C&I/institutional buildings.
- HeatTag and every PowerTag India MRP not exhaustively listed.

## Recommendations
1. **Lead with the "no-subscription, multi-physics, open-hardware" wedge.** Frame OmniView IQ against Schneider's "subscription-locked, electrical-only, closed ecosystem." The single strongest lever is recurring cost: Energy Hub charges per-device-credit per-year forever (~$233/device/yr list). Build an explicit 3-year and 5-year TCO table showing the two hardware CapEx figures converging but Schneider's line pulling away every year on subscription.
2. **Attack on measurement scope.** Schneider's supported-device list has zero vibration and zero process-pressure sensors. For a PET plant, blow-molder/compressor vibration and line pressure are core — Schneider would need a separate system bolted on. Make this a "one platform vs. three" argument.
3. **Concede where Schneider is genuinely stronger — to stay credible.** Revenue-grade metering accuracy (Class 0.1S–0.5S), power-quality analytics (sag/swell/THD/transients), certified energy-code compliance reporting, and enterprise cybersecurity (IEC 62443, ISO 27001, Azure) plus brand trust. Position OmniView IQ as "right-sized affordability," not "better than Schneider at everything."
4. **Neutralize the "cheap = insecure" objection.** Document that OmniView IQ's Teltonika RUT956 supports VPN, firewall and TLS, matching Schneider's TLS 1.2 + MQTT + role-based-access narrative at the transport layer. Put a security row in the comparison table so the gap is visibly small.
5. **Know when to refer rather than fight.** If a prospect specifically needs (a) statutory energy-code / tenant-billing compliance, (b) revenue-grade sub-metering, or (c) multi-site portfolio rollups, Schneider is hard to beat — treat these as partner/refer scenarios. The winnable fights are single-site plants that want machine health + energy + process visibility at low CapEx with no recurring fee.

## Caveats
- "Up to 30% energy savings" and "up to 25% lower deployment cost / 50% lower IT-maintenance cost" are **Schneider marketing claims** (footnoted in the Apr 26, 2022 launch release), not independently verified. The Le Grand Monarque "15% in 6 months" is a single vendor-published case study.
- Software list prices are **US-domain figures with a "subject to trade discount" disclaimer**; transacted prices via distributors are typically lower (e.g., a $271 net was seen against a $594 list SKU).
- Hardware prices from IndiaMART/third-party resellers vary widely and may not reflect official Schneider India MRP; treat as ±30%.
- The **"+ Advanced" tier** (the one carrying the electrical power-quality/asset features most relevant to industrial monitoring) was **discontinued mid-2025**, indicating Schneider is restructuring plan packaging — verify current tier names, features and prices at quote time.
- Third-party "USD 800–8,000" and "45-day trial" figures come from a non-Schneider guide and may conflate different EcoStruxure product lines; do not cite these as authoritative Energy Hub pricing.
# OmniView IQ — Hospital Sensor Survey Brief

*A consolidated briefing document, written to be uploaded as a source into NotebookLM for generating a mind map and an audio overview. Every section is self-contained narrative — read top to bottom for the full story, or use the headers as mind-map branches.*

---

## 1. The Big Picture: What This Project Is

OmniView IQ is a facility-monitoring platform. Its engineering team has been building a proof-of-concept around a bottle-manufacturing factory, but the business is now expanding into a new vertical: hospitals. Before OmniView can sell or design a monitoring system for any given hospital, someone has to physically visit that hospital, walk through it, and figure out three things — what departments and utility spaces exist, what sensors would need to go where, and roughly what that would cost.

That visit is called a site survey. Because the company plans to survey many different hospitals over time — not just one — everything built for this purpose had to be reusable: a template, not a one-off spreadsheet.

Two documents work together to support this:

1. **The Hospital Site Survey Field Pack** — an existing, already field-tested walkdown script (a Word document) that tells a surveyor what questions to ask, which role to ask them to (accounts, electrical, HVAC, IT), and which existing OmniView engineering function each answer feeds into.
2. **The Hospital Device & Sensor Master Tracker** — a new Excel workbook, built specifically for this brief's purpose, that turns the qualitative walkdown into a quantitative, costed bill of materials: which departments exist, how many sensors of which type go where, and what the tentative total hardware cost is.

This brief is about the second one — the Excel tracker — and everything that had to be figured out to build it correctly.

---

## 2. The Core Design Problem: Don't Just Copy the Factory Sensor List

The first attempt at building the sensor catalog took a shortcut: it reused the sensor list already chosen for the bottle-factory proof-of-concept — a vibration sensor, a panel-overheating sensor, an energy meter, a pressure sensor, an ambient sensor, and a couple of manufacturing-specific items like a production-cycle counter. That list existed because it fit a factory. It had never actually been checked against what a hospital survey needs.

So the catalog was re-verified from scratch against three independent sources instead of one:

- **hd-working-brife.md** — a document describing OmniView's parent hardware vendor's own sensor platform, in its own words. It groups sensors into three families: *electrical* (multi-functional meters measuring over 40 parameters per feeder), *physical process variables* (temperature, pressure, and flow), and *environmental conditions* (air quality index, ambient temperature and humidity, and both atmospheric and building-internal air pressure).
- **The Hospital Site Survey Field Pack** — the team's own field-tested hospital document, which defines a much narrower "attach" vocabulary: an electrical meter with current transformers, a panel-overheating sensor, a vibration sensor, a pressure sensor, and an ambient sensor. Notably, this document does not mention flow meters, air quality sensors, or room pressure sensors at all.
- **Live web research**, conducted specifically to check two sensor types the hardware document names but the field pack doesn't: room differential pressure monitoring, and air quality monitoring. Both turned out to be real, standard hospital practices with real India-market pricing.

Cross-checking against all three sources produced a materially different, more defensible sensor catalog than simply reusing the factory list.

---

## 3. What Changed, and Why

One sensor was dropped entirely: the digital pulse or cycle counter, which counts machine cycles like a production stroke counter. Neither the hardware vendor's own document nor the hospital field pack backs this as something hospitals commonly need. Its only plausible hospital analogy — counting lift usage or sterilizer cycles — is weak enough that it was removed from the standard catalog rather than kept with a made-up price.

Two sensors were added because they were missing entirely from the first draft, despite being explicitly named in the hardware vendor's own document:

- **Room differential pressure sensing.** Operation theatres are required to run at positive air pressure relative to the corridor outside them, so contaminated air cannot flow in. Isolation wards run the opposite way — negative pressure — so infectious air cannot flow out into the rest of the hospital. This is standard infection-control practice, not a novelty, and it is a genuinely different measurement from utility pressure: it's measured in pascals, not bar, and its purpose is regulatory compliance rather than leak detection.
- **Air quality sensing.** The hardware vendor's document explicitly lists air quality index as an environmental parameter it can capture. Indoor air quality — particulate matter, carbon dioxide, volatile organic compounds — is directly relevant to operation theatres and intensive care units.

One sensor's labeling was clarified to prevent a costly mistake: the vibration sensor already includes a co-located temperature reading on the same physical device, when it is mounted on a motor or pump. A surveyor who didn't know this might have separately bought a standalone temperature sensor for the same asset, doubling the cost for no reason. The catalog entry was relabeled to make the bundling explicit.

The standalone temperature sensor itself — used for boiler water, chiller lines, and other places with no rotating machinery to attach a vibration sensor to — was also repriced. The initial estimate assumed a wireless multi-parameter unit; further research showed that a bare industrial temperature probe is far cheaper, and only needs a transmitter added for it to talk to the gateway.

Finally, one item was moved out of the sensor list altogether without being deleted: the communication gateway. A gateway is not a sensor a surveyor picks per department — it's shared infrastructure. One gateway, sitting near an electrical room, listens to roughly ten sensors around it on that same feeder. If it had stayed selectable in the same per-department dropdown as every other sensor, a surveyor could easily have picked "gateway" under two or three different departments out of habit, silently doubling or tripling its cost in the final total. It was pulled out of the per-department picklist and given its own single line item instead, so it can only ever be counted once per site.

---

## 4. The Final Sensor Catalog

Nine sensor types are selectable per department, plus the gateway tracked separately as shared infrastructure. Every entry uses a generic, descriptive name — never a vendor or brand name — so the same list can be shown directly to a hospital client without exposing sourcing decisions.

**Electrical Energy Meter with Current Transformers.** Measures three-phase power, voltage, current, power factor, and cumulative energy at a feeder or panel. Clamped non-invasively around the existing cable using split-core current transformers — no cable is ever cut. Installed at a transformer incomer, a diesel generator output, or a department's electrical sub-panel.

**Panel Overheating and Gas-Particle Sensor.** Detects the earliest signs of a cable or connection overheating inside an enclosed electrical panel — gas and micro-particle buildup — before there is any smoke or visible damage. Mounted inside the panel's internal airspace, never touching a live wire.

**Vibration and Mechanical Health Sensor, with co-located surface temperature.** Measures vibration velocity in three axes plus surface temperature from the same physical device, catching bearing wear, imbalance, and misalignment before a motor, pump, or compressor fails. Bolted or magnet-mounted to the outside of the machine housing, near the bearing.

**Standalone process or fluid temperature sensor.** A resistance-based temperature probe for fluid or gas temperature where there's no rotating machine nearby to piggyback a vibration sensor on — boiler water, chiller supply and return lines, hot-water calorifiers. Inserted into an existing thermowell port if one exists, or clamped onto the pipe's outer surface if not.

**Pressure sensor or transmitter, plant and utility range.** Measures line pressure in bar and its rate of change, catching leaks and supply drops in oxygen manifolds, medical air lines, compressed air, and water supply lines. Screwed into an existing gauge port — the same port a mechanical pressure gauge already uses.

**Room differential pressure sensor, pascal range.** Confirms an operation theatre is holding positive pressure relative to its corridor, or that an isolation ward is holding negative pressure. Wall-mounted with two thin sensing tubes, one on each side of the boundary being monitored.

**Ambient temperature and humidity sensor.** A room-level baseline reading, used in operation theatres, intensive care units, wards, pharmacy cold storage, server rooms, and blood banks. Simply mounted on a wall or ceiling.

**Air quality sensor.** Measures particulate matter, carbon dioxide, and volatile organic compounds — an air-cleanliness check most relevant in operation theatres and intensive care units, and useful as a general indoor air quality baseline elsewhere.

**Ultrasonic flow meter.** Measures liquid or gas flow rate through a pipe without cutting into it — the transducer clamps onto the outside of the pipe and reads flow through the pipe wall using ultrasound. Used on water supply lines and oxygen or medical-gas lines. This one carries a caveat: it's confirmed as core hardware by the vendor's own document and supported by real-world hospital water sub-metering practice, but it is not yet part of the field pack's tested vocabulary, so a surveyor is told to confirm the specific need on-site rather than assume it belongs in every survey.

**Communication gateway — shared infrastructure, not a per-department sensor.** Aggregates data from the sensors around it and pushes it to the cloud. One gateway typically serves about ten sensors on one electrical feeder. Mounted near the main electrical room it serves, needing only a power point and a cable or wireless connection back to the sensors.

---

## 5. Which Sensors Need Site-Specific Range Matching, and Which Don't

Most of the sensor catalog is universal — one model's measurement range comfortably covers almost any hospital installation, so a surveyor doesn't need to measure anything before ordering it. Vibration sensors, ambient temperature and humidity sensors, air quality sensors, and room differential pressure sensors all fall into this category.

Three sensor types are different, and picking the wrong size means the sensor simply will not work correctly:

The **current transformer** for the energy meter must be sized to the feeder's actual rated current, which the surveyor has to read off a nameplate or an existing panel meter before choosing a transformer ratio — common ratios include 30-to-5, 100-to-5, and 200-to-5 amps.

The **pressure sensor** must be sized to a range comfortably above whatever the existing mechanical gauge on that line currently reads — pressure sensors come in fixed bands like 0 to 10 bar, 0 to 16 bar, or 0 to 40 bar, and picking a band that's too low will saturate the sensor.

The **flow meter** must be sized to the actual outer diameter of the pipe it's clamping onto — small-pipe and large-pipe versions are physically different products.

For all three, the practical rule for a site visit is the same: note the existing number — current rating, gauge pressure, or pipe diameter — before deciding which size of sensor to specify.

---

## 6. How Many Gateways a Site Needs

The rule of thumb, taken directly from the hardware vendor's own specification, is that one gateway handles roughly ten sensors on one electrical feeder, and its cable connection back to those sensors only works reliably over roughly one hundred to three hundred metres. Practically, this means a surveyor should first count how many separate electrical rooms or main distribution panels the hospital has — that count is the minimum number of gateways needed — and then, for each one, check whether every sensor planned near it is actually within cable reach. A department on a different floor or served by a different electrical room needs its own gateway, even if the total sensor count elsewhere hasn't hit ten yet.

---

## 7. The Department Structure

Hospital departments are grouped into four categories in the survey template. Clinical departments — emergency, intensive care, operation theatres, outpatient consultation, general and private wards, radiology, pathology, pharmacy, blood bank, and physiotherapy — exist in the survey mainly for sizing and location context, since sensors don't attach to a ward's name, they attach to the electrical feeder or mechanical asset that actually serves that ward. Support departments — sterile services, laundry, kitchen, and housekeeping — round out the back-of-house. The facility and utility category is where most sensors are actually installed: the electrical room, the generator and changeover room, the boiler room, the chiller and air-handling plant, the medical gas plant, lifts, the server room, and the water pump house. A final administrative category covers reception, billing, and biomedical engineering.

Departments can have more than one physical instance — a hospital might have a general intensive care unit, a gynecology-specific intensive care unit, and a tuberculosis-specific isolation intensive care unit, each on a different floor with different sensor counts. The survey template handles this with a dedicated "sub-department or ward name" field, so each named unit gets tracked and costed separately, even while they all roll up under the single department category of "intensive care unit" for a higher-level total.

A fourth field, floor, exists purely for logistics — cabling and installation labor are typically planned per floor, not per department, so the cost summary rolls that up separately too.

---

## 8. What This System Deliberately Does Not Do

A hard constraint carried over from the existing field pack, and repeated throughout the new tracker's documentation: this is facility and utility sensing only. Nothing in this system monitors a patient directly — no pulse oximetry, no ECG, no ventilator waveforms, no bedside monitoring of any kind. Even when a department name sounds clinical, like an intensive care unit's ventilator bay, the only thing actually being measured is the electrical load on the panel feeding that bay — never the clinical device itself. This boundary exists because OmniView's product is about facility operations and energy — not clinical care — and crossing that line would require an entirely different regulatory and safety framework.

---

## 9. The Deliverable

All of this reasoning is embodied in one reusable Excel workbook, meant to be copied fresh for each hospital surveyed. It contains an instructions page explaining how to use it and what each field means in plain language; a sensor catalog page listing the nine generic sensor types with their descriptions, placements, and cost ranges; an editable department list that feeds a dropdown and can be extended per hospital; the main data-entry grid where a surveyor picks department, sub-department, floor, and sensor type and gets an automatic cost calculation; a field guide page describing exactly how and where to physically attach each sensor and which ones need site-specific range checking; and a cost summary page that automatically rolls totals up by department, by floor, by sensor category, and by individual named ward, alongside a separate line for gateway infrastructure and one final grand total.

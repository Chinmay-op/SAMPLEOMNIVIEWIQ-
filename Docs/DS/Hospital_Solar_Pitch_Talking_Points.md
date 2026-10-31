# Solar Pitch — 6 Talking Points, Explained in Detail

*A working breakdown of the 6 core arguments from [`Hospital_Solar_Client_Pitch_Brief.md`](Hospital_Solar_Client_Pitch_Brief.md) — each with a plain-language example, when it applies, and what's genuinely true both for and against it. Use this to prep for the conversation, not to hand to the client as-is (the brief itself is the client-facing version).*

---

## Point 1 — Solar substitutes *billing*, not *consumption*

**In detail:** Solar panels generate DC power that gets converted and fed into the hospital's electrical system during daylight hours, reducing the number of units the hospital has to *buy* from the grid utility (DISCOM) at that moment. The hospital's actual energy consumption — how many units its equipment draws — doesn't change at all. What changes is who supplied those units and what they cost.

**Layman example:** Think of it like a household that starts growing its own vegetables. The family isn't eating less food — they're still eating the same amount, maybe even the same vegetables. They're just buying fewer of them from the market. If they were already wasting half of what they bought (throwing away spoiled produce), growing their own doesn't fix that waste — it just means they're now wasting some of their own homegrown vegetables instead of store-bought ones.

**Conditions:** Applies at all times solar is generating (roughly sunrise to sunset, weather-dependent). Doesn't apply at all outside daylight hours — 100% grid/DG dependency then, solar or no solar.

**Pros:** Real, measurable reduction in the grid import line item on the bill. Straightforward ROI calculation. No behavior change required to get this saving — it's automatic once installed.

**Cons:** Gives a false sense that the "energy problem" is solved, because the bill visibly drops. The underlying consumption pattern — including all its inefficiencies — is completely untouched and invisible in a solar generation report.

---

## Point 2 — Maximum Demand (MD) penalty risk is about *timing*, not *totals* — and solar doesn't control timing

**In detail:** Utilities like MSEDCL don't just charge for total units consumed in a month — they also charge a penalty if the hospital's *peak* load in any single 15-minute window exceeds its contracted demand. This is measured in kVA, not kWh, and it only takes one bad 15-minute block in the entire month to trigger it. Solar reduces the hospital's *average* draw from the grid during sunlight hours, but it doesn't guarantee it reduces the load at the *exact* 15-minute block where the peak happens to land.

**Layman example:** It's like a toll booth that fines you if your car's speed crosses 80 km/h at any single moment on the highway, not your average speed for the trip. Driving slower for 90% of the trip doesn't help if you still hit 85 km/h for ten seconds going downhill. Similarly, having solar cover most of the day doesn't help if the actual demand spike happens during a cloudy ten minutes, or before/after sunlight hours.

**Conditions:** Applies specifically to HT/commercial connections with a contracted maximum demand clause (which most hospitals on an HT connection have). The risk is highest when the hospital's peak-load activities — OT AC pre-cool, imaging warm-up, laundry/kitchen peak, boiler heat-up — happen to cluster at the edges of the solar-generation window (early morning, evening) or on a low-sun day.

**Pros:** Solar can genuinely help reduce demand-penalty risk *if* the hospital's peak load reliably happens mid-day, in full sun, every time — some facilities do get lucky here.

**Cons:** It's not a guarantee, and hospitals typically can't control exactly when their peak load hits (an emergency surgery, a delayed OT schedule, a cloudy morning). One bad 15-minute block anywhere in the month still triggers the penalty, solar capacity notwithstanding.

---

## Point 3 — Weather makes solar's contribution inconsistent, exactly when it's needed most

**In detail:** Solar panel output isn't a fixed number — it swings with cloud cover, minute to minute on a partly-cloudy day, and drops for extended stretches during multi-day monsoon overcast periods. A hospital that budgets its energy plan assuming solar reliably covers, say, 30% of daytime load will find that number is sometimes far lower — right when the grid/DG has to pick up the difference unexpectedly.

**Layman example:** It's like planning your commute assuming the bus always arrives on time. Most days it does, and your plan works fine. But on the days it's late — which cluster together during bad weather — you're stuck, and if that's also the day you had an important meeting (a demand-sensitive load), the "usual" plan doesn't save you.

**Conditions:** Most relevant during Maharashtra's monsoon season (roughly July–October), where 3–5 consecutive heavily overcast days aren't unusual, and on any partly-cloudy day where output swings unpredictably minute to minute.

**Pros:** On a clear day, solar performs exactly as expected or better — this isn't a permanent problem, just a seasonal and daily variability the hospital needs to plan around rather than ignore.

**Cons:** The hospital cannot choose when clouds show up, and the periods of lowest solar output (monsoon) don't correlate with periods of lower hospital load — if anything, humidity-driven HVAC load can go up exactly when solar output goes down.

---

## Point 4 — Critical hospital loads never run on solar in the first place

**In detail:** By standard hospital electrical design (aligned with NABH accreditation practice), critical loads — ICU, OT, MRI and similar life-safety-adjacent equipment — are wired to stay on the UPS → DG → grid chain, specifically so they never depend on an inherently variable source like rooftop solar. Solar sits upstream, offsetting the *general* HT load, not these critical circuits.

**Layman example:** It's like a hospital having a backup generator for the ICU that kicks in during a power cut — nobody would want the ICU's power to depend on whether it's sunny outside. Solar was never meant to, and structurally can't, reach those circuits.

**Conditions:** Applies to any hospital following standard critical-load electrical architecture — essentially universal practice for accredited facilities.

**Pros:** This is a *safety* feature, not a flaw — it means patient-critical equipment has guaranteed, stable power regardless of weather. That's the correct design choice.

**Cons:** It also means a meaningful chunk of the hospital's total load (often energy-intensive: ICU AC, OT lighting/AC, imaging) is structurally excluded from ever benefiting from solar, so the theoretical maximum saving solar can ever deliver is capped well below 100% of the bill, no matter how large the solar installation gets.

---

## Point 5 — Solar is electricity-only; it has zero effect on fuel burned by the DG and boiler

**In detail:** Rooftop solar is a photovoltaic system — it makes electricity. The hospital's diesel generator (for outage backup and critical-load changeover) and its boiler (for CSSD sterilization, hot water, often kitchen/laundry) both run on *combustion* — diesel and LPG/furnace-oil/biomass respectively. These are entirely separate energy systems, on separate meters, governed by separate schedules. Nothing about installing solar panels changes how much diesel the DG burns per hour, or how long the boiler needs to reach operating temperature.

**Layman example:** Imagine a household that has both a car (petrol) and an electric scooter. Switching some errands from the car to the scooter reduces petrol consumption for those trips — but it does absolutely nothing to how much gas the kitchen stove burns to cook dinner. They're unrelated systems running on unrelated fuels; improving one doesn't touch the other.

**Conditions:** Applies to any hospital with a boiler and/or DG — which is essentially every hospital of meaningful size, since both are typically mandatory for safety/sterilization compliance.

**Pros:** None, from solar's side — this is a genuine, complete blind spot, not a partial limitation. Naming it clearly is what makes the pitch credible rather than vague.

**Cons:** A hospital that has "solved" its electrical energy story with solar can still be significantly overspending on diesel and boiler fuel with zero visibility into it, because nothing in the solar story ever looked at that side of the operation.

---

## Point 6 — Waste is invisible regardless of where the energy came from, and solar can make it *easier* to miss

**In detail:** Equipment that's inefficient — a standby chiller running with no cooling load, a ward AC with no night setback, a slow leak in a compressed-air or water line, a motor bearing wearing out and drawing more current for the same output — wastes energy regardless of whether that energy came from the grid or from the hospital's own roof. Solar has no monitoring capability of its own to detect any of this; it only reports how much it generated, not how well the hospital used what it received.

**Layman example:** It's like fixing a leaking bucket by pouring in more water from a second tap instead of patching the leak. You might feel like you're "managing" the water supply better because you added a source, but the leak — the actual waste — is still there, dripping exactly as much as before. Adding solar is adding a second tap; it was never a patch for the leak.

**Conditions:** Applies universally, at all times, regardless of solar penetration — waste is a property of *equipment behavior*, not of *energy source*.

**Pros:** None directly from solar — but this point has an important secondary effect worth flagging: once solar visibly lowers the bill, facility teams often (understandably) feel the energy problem is "handled" and stop actively looking for waste, right when there's more total energy (grid + solar) worth auditing, not less.

**Cons:** This is the single biggest missed-savings risk in the whole solar conversation — waste typically represents a larger, more consistently recoverable saving than anything solar itself delivers, and it's the one thing solar cannot find, measure, or fix on its own.

---

## How to use this in the room

Points 1 and 4 are the *credibility-builders* — they concede real, genuine value to solar, which makes the harder points (2, 3, 5, 6) land as informed analysis rather than a sales knock against a decision they've already made. Points 5 and 6 are the *close* — they're the two arguments that most directly justify bringing in a monitoring layer regardless of the solar investment, since neither is something solar can ever address, no matter how large or well-maintained the installation is.

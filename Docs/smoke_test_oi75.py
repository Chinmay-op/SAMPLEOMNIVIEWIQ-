"""
Smoke Test — OI-75 Safety / Access Sign-Off + Install Window
===============================================================

Usage::

    python Docs/smoke_test_oi75.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from omniview.edge.safety_signoff import SafetySignOff, generate_safety_report


def main() -> None:
    print("=" * 72)
    print(" OI-75 Safety / Access Sign-Off — Smoke Test")
    print("=" * 72)
    print()

    so = SafetySignOff()

    print(f"Hazards assessed:      {so.hazard_count}")
    print(f"PPE items:             {so.ppe_count}")
    print(f"Install windows:       {so.window_count}")
    print(f"Total install time:    {so.total_install_duration_minutes} min")
    print(f"All risks low:         {'✅' if so.all_risks_low else '❌'}")
    print(f"Zero downtime:         {'✅' if so.zero_production_stoppage else '❌'}")
    print(f"Constraints documented: {len(so.zero_downtime_constraints)}")
    print()

    # Hazards
    print("-" * 72)
    print("Hazard Assessments:")
    print()
    for h in so.hazards:
        risk_arrow = f"{h.risk_before_controls.value} → {h.risk_after_controls.value}"
        print(f"  {h.hazard_id}: {h.location_name}")
        print(f"    Category: {h.hazard_category.value} | Risk: {risk_arrow}")
        print(f"    Controls: {len(h.controls)} | PPE: {', '.join(h.ppe_required)}")
    print()

    # PPE
    print("-" * 72)
    print("PPE Requirements:")
    print()
    for p in so.ppe:
        print(f"  {p.ppe_id}: {p.item} (×{p.quantity})")
        print(f"    Spec: {p.specification}")
    print()

    # Windows
    print("-" * 72)
    print("Install Windows:")
    print()
    for w in so.windows:
        print(f"  {w.window_id}: {w.description}")
        print(f"    Day: {w.proposed_day}")
        print(f"    Shift: {w.proposed_shift}")
        print(f"    Duration: {w.duration_minutes} min | Production stop: NO")
    print()

    # Zero downtime constraints
    print("-" * 72)
    print(f"Zero Downtime Constraints ({len(so.zero_downtime_constraints)}):")
    print()
    for c in so.zero_downtime_constraints:
        print(f"  {c['id']}: {c['constraint'][:70]}...")
    print()

    # Simulate approval
    so.approve("Site Safety Officer", "All hazards reviewed and accepted")
    print("-" * 72)
    print(f"Sign-off status: {so.status.value.upper()}")
    print(f"Approved: {'✅' if so.is_approved else '❌'}")
    print()

    # Report
    report = generate_safety_report(so)
    print("Acceptance Criteria:")
    print(json.dumps(report["acceptance_criteria"], indent=2))
    print()

    ac = report["acceptance_criteria"]
    all_ok = all(ac.values())
    print("=" * 72)
    if all_ok:
        print(" ✅  OI-75 ACCEPTANCE CRITERIA MET")
        print("     Written sign-off captured: yes")
        print("     Install window scheduled: yes")
        print("     Zero production stoppage documented: yes")
    else:
        print(" ❌  OI-75 ACCEPTANCE CRITERIA NOT MET")
    print("=" * 72)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

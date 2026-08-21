"""
Smoke Test — OI-74 Site Walkthrough + Layer 0 Profile
=======================================================

Usage::

    python Docs/smoke_test_oi74.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from omniview.edge.site_profile import (
    Layer0Profile,
    SiteWalkthrough,
    generate_walkthrough_report,
)


def main() -> None:
    print("=" * 72)
    print(" OI-74 Site Walkthrough + Layer 0 Profile — Smoke Test")
    print("=" * 72)
    print()

    profile = Layer0Profile()

    # ── Site Info ────────────────────────────────────────────────────────
    print(f"Site:       {profile.site.name}")
    print(f"Site ID:    {profile.site.site_id}")
    print(f"Timezone:   {profile.site.timezone}")
    print(f"Utility:    {profile.tariff.utility} {profile.tariff.tariff_category}")
    print(f"Contracted: {profile.tariff.contracted_demand_kva} kVA")
    print(f"Machines:   {profile.machine_count}")
    print(f"Locations:  {profile.location_count}")
    print()

    # ── Machine Profiles ────────────────────────────────────────────────
    print("-" * 72)
    print("Machine Profiles:")
    print()
    for m in profile.machines:
        print(f"  {m.machine_id}: {m.display_name}")
        print(f"    Node:    {m.node_id}")
        print(f"    Class:   {m.equipment_class}")
        print(f"    Model:   {m.make_model}")
        kw = f"{m.nameplate_kw} kW" if m.nameplate_kw else "TBC"
        bar = f"{m.nameplate_bar} bar" if m.nameplate_bar else "N/A"
        print(f"    Rated:   {kw}, {bar}")
        print(f"    Zone:    {m.location_zone.value}")
        print(f"    Feed:    {m.connection_type}")
        print()

    # ── Location Map ────────────────────────────────────────────────────
    print("-" * 72)
    print("Location Map:")
    print()
    print(f"  {'ID':<10} {'Name':<45} {'Node':<16} {'Access':<12} {'Dist':>5}")
    print(f"  {'-'*10} {'-'*45} {'-'*16} {'-'*12} {'-'*5}")
    for loc in profile.locations:
        print(
            f"  {loc.point_id:<10} {loc.name[:45]:<45} {loc.node_id:<16} "
            f"{loc.access_level.value:<12} {loc.distance_from_panel_m:>4.0f}m"
        )
    print()

    # ── Walkthrough Checklist ───────────────────────────────────────────
    walkthrough = SiteWalkthrough(profile)
    print("-" * 72)
    print(f"Walkthrough Checklist ({walkthrough.item_count} items):")
    print()
    for item in walkthrough.items:
        print(f"  [ ] {item.item_id}: {item.check}")
    print()

    # ── Report ──────────────────────────────────────────────────────────
    report = generate_walkthrough_report(profile)
    print("-" * 72)
    print("Acceptance Criteria:")
    print(json.dumps(report["acceptance_criteria"], indent=2))
    print()
    print("Summary:")
    print(json.dumps(report["summary"], indent=2))
    print()

    # ── Final Verdict ───────────────────────────────────────────────────
    ac = report["acceptance_criteria"]
    all_ok = ac["location_map_for_both_nodes"] and ac["layer_0_profile_draft_complete"]
    print("=" * 72)
    if all_ok:
        print(" ✅  OI-74 ACCEPTANCE CRITERIA MET")
        print("     Location map for both nodes: complete")
        print("     Layer 0 profile draft: complete")
    else:
        print(" ❌  OI-74 ACCEPTANCE CRITERIA NOT MET")
    print("=" * 72)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

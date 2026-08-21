"""
Smoke Test — OI-73 BOM + Procurement Lead Times
==================================================

Quick validation that the BOM is complete, costs are in range, and
critical-path items are flagged.

Usage::

    python Docs/smoke_test_oi73.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

# Ensure src/ is on the path
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

# Ensure UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from omniview.edge.bom import BOMSheet, generate_bom_report


def main() -> None:
    print("=" * 72)
    print(" OI-73 BOM + Procurement Lead Times — Smoke Test")
    print("=" * 72)
    print()

    bom = BOMSheet()

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"Total line items:     {bom.item_count}")
    print(f"Total units:          {bom.total_quantity}")
    print(f"Estimated CapEx:      {bom.total_cost_display}")
    print(f"Max lead time:        {bom.max_lead_time_days} days")
    print(f"Critical-path lead:   {bom.critical_path_lead_time_days} days")
    print()

    # ── All Items ───────────────────────────────────────────────────────
    print("-" * 72)
    print(f"{'ID':<10} {'Item':<40} {'Qty':>4} {'Cost Range':<22} {'Lead':>10} {'CP':>4}")
    print("-" * 72)
    for item in bom.items:
        cp = "⚠" if item.is_critical_path else ""
        print(
            f"{item.item_id:<10} {item.name[:40]:<40} {item.quantity:>4} "
            f"{item.cost_display:<22} {item.lead_time_display:>10} {cp:>4}"
        )
    print("-" * 72)
    print()

    # ── Critical Path ───────────────────────────────────────────────────
    critical = bom.get_critical_path_items()
    print(f"⚠ Critical-Path Items ({len(critical)}):")
    print()
    for item in critical:
        print(f"  {item.item_id}: {item.name}")
        print(f"    Make/Model:  {item.make_model}")
        print(f"    Lead time:   {item.lead_time_display}")
        print(f"    Availability: {item.availability.value}")
        print(f"    Vendor:      {item.vendor_location}")
        print(f"    Note:        {item.notes[:100]}...")
        print()

    # ── Cost by Node ────────────────────────────────────────────────────
    print("-" * 72)
    print("Cost by Node:")
    print()
    for node, costs in bom.get_cost_by_node().items():
        print(f"  {node:<20} ₹{costs['low']:>8,.0f} – ₹{costs['high']:>8,.0f}")
    print()

    # ── Cost by Category ────────────────────────────────────────────────
    print("Cost by Category:")
    print()
    for cat, costs in bom.get_cost_by_category().items():
        print(f"  {cat:<20} ₹{costs['low']:>8,.0f} – ₹{costs['high']:>8,.0f}")
    print()

    # ── Report ──────────────────────────────────────────────────────────
    report = generate_bom_report(bom)
    print("-" * 72)
    print("Acceptance Criteria:")
    print(json.dumps(report["acceptance_criteria"], indent=2))
    print()
    print("Summary:")
    print(json.dumps(report["summary"], indent=2))
    print()

    # ── Final Verdict ───────────────────────────────────────────────────
    ac = report["acceptance_criteria"]
    all_ok = ac["bom_sheet_with_qty_cost_lead_time"] and ac["critical_path_items_flagged"]
    print("=" * 72)
    if all_ok:
        print(" ✅  OI-73 ACCEPTANCE CRITERIA MET")
        print("     BOM sheet with qty/cost/lead time: complete")
        print("     Critical-path items flagged: yes")
    else:
        print(" ❌  OI-73 ACCEPTANCE CRITERIA NOT MET")
    print("=" * 72)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

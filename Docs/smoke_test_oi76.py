"""
Smoke Test — OI-76 Non-Invasive Install Verification
======================================================

Quick validation script that runs the install procedure and verifier
to confirm both nodes (compressor-01 + isbm-01) are properly defined
and meet the acceptance criteria:

  1. Both nodes instrumented
  2. No production stoppage attributable to install

Usage::

    python Docs/smoke_test_oi76.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure src/ is on the path
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from omniview.edge.install_procedure import (
    InstallProcedure,
    InstallVerifier,
    generate_install_report,
)

# Ensure UTF-8 output on Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main() -> None:
    print("=" * 72)
    print(" OI-76 Non-Invasive Install — Smoke Test")
    print("=" * 72)
    print()

    # ── Create procedure ────────────────────────────────────────────────
    procedure = InstallProcedure(safety_approved=True, bom_confirmed=True)

    print(f"Total nodes:    {len(procedure.node_plans)}")
    print(f"Total steps:    {procedure.total_step_count}")
    print(f"Total devices:  {procedure.total_device_count}")
    print(f"Total duration: {procedure.total_duration_minutes} minutes")
    print(f"Zero downtime:  {procedure.zero_downtime}")
    print()

    # ── Print node summaries ────────────────────────────────────────────
    for plan in procedure.node_plans:
        print(f"  Node: {plan.node_id}")
        print(f"    Name:     {plan.display_name}")
        print(f"    Location: {plan.location}")
        print(f"    Steps:    {len(plan.steps)}")
        print(f"    Devices:  {plan.device_count}")
        print(f"    Duration: {plan.total_duration_minutes} min")
        print(f"    Safety:   {'✅ Approved' if plan.safety_approved else '⬜ Pending'}")
        print(f"    BOM:      {'✅ Confirmed' if plan.bom_confirmed else '⬜ Pending'}")
        print()
        for step in plan.steps:
            print(f"      [{step.step_id}] {step.description[:70]}...")
            print(f"        Method: {step.method.value} | PPE: {', '.join(step.ppe_required) or 'none'}")
        print()

    # ── Pre-install checklist ───────────────────────────────────────────
    print("-" * 72)
    print("Pre-Install Checklist:")
    print()
    for item in procedure.get_pre_install_checklist():
        print(f"  [ ] {item['id']}: {item['check']}")
    print()

    # ── Verify ──────────────────────────────────────────────────────────
    print("-" * 72)
    print("Running install verification...")
    print()

    verifier = InstallVerifier(procedure)
    result = verifier.verify_all()

    for nr in result.node_results:
        status = "✅ PASS" if nr.passed else "❌ FAIL"
        print(f"  {nr.node_id}: {status}")
        for check in nr.checks:
            chk_status = "✅" if check["passed"] else "❌"
            print(f"    {chk_status} {check['check']}")
    print()
    print(f"  Zero downtime confirmed: {'✅' if result.zero_downtime_confirmed else '❌'}")
    print(f"  All passed: {'✅' if result.all_passed else '❌'}")
    print()

    # ── Simulate full install ───────────────────────────────────────────
    print("-" * 72)
    print("Simulating complete install (marking all steps completed)...")
    print()
    for step in procedure.get_all_steps():
        procedure.mark_step_completed(step.step_id)

    print(f"  All nodes instrumented: {'✅' if procedure.all_nodes_instrumented else '❌'}")
    print(f"  Zero downtime: {'✅' if procedure.zero_downtime else '❌'}")
    print()

    # ── Generate report ─────────────────────────────────────────────────
    report = generate_install_report(procedure)
    print("-" * 72)
    print("Install Report Summary:")
    print(json.dumps(report["summary"], indent=2))
    print()
    print("Acceptance Criteria:")
    print(json.dumps(report["acceptance_criteria"], indent=2))
    print()

    # ── Final verdict ───────────────────────────────────────────────────
    ac = report["acceptance_criteria"]
    all_ok = ac["both_nodes_instrumented"] and ac["zero_production_stoppage"]
    print("=" * 72)
    if all_ok:
        print(" ✅  OI-76 ACCEPTANCE CRITERIA MET")
        print("     Both nodes instrumented. Zero production stoppage.")
    else:
        print(" ❌  OI-76 ACCEPTANCE CRITERIA NOT MET")
        if not ac["both_nodes_instrumented"]:
            print("     ⚠ Not all nodes instrumented")
        if not ac["zero_production_stoppage"]:
            print("     ⚠ Production stoppage detected")
    print("=" * 72)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

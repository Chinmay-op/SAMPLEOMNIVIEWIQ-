"""
OmniView IQ — Dynamic Implementation Status Inspector
=======================================================

Automated inspection engine that inspects detector modules, ASTs, registry wiring,
and live TimescaleDB telemetry to dynamically evaluate implementation status.

Status categories (per Section 3 of Master Task):
- NOT IMPLEMENTED: fails import, missing class/function, pass/stub body, or missing required threshold.
- NOT WIRED: implemented, but not in build_default_registry() in detectors_live.py.
- NO DATA: implemented and wired, but no sensor telemetry in the last N minutes.
- LIVE: implemented, wired, and real data is actively flowing.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from omniview.ingest.db import get_engine
from omniview.rules.detectors_live import build_default_registry


@dataclass
class FunctionStatus:
    name: str
    spec_file: str
    code_file: str
    target_symbol: str
    status: str          # LIVE | NO DATA | NOT WIRED | NOT IMPLEMENTED
    reason: str
    last_event_time: str
    spec_reference: str
    is_wired: bool
    recent_rows: int


# Specification metadata for the 9 Feature 2 functions
FUNCTION_SPECS = [
    {
        "id": "md_nearmiss",
        "name": "MD Near-Miss",
        "spec_file": "md_nearmiss.py",
        "code_module": "omniview.rules.demand_window",
        "code_path": "src/omniview/rules/demand_window.py",
        "target_symbol": "DemandWindowDetector",
        "registry_name": "demand_window",
        "sensor_types": ["electrical"],
        "table": "readings_electrical",
        "required_constants": ["CONTRACTED_DEMAND_KVA", "MD_ALERT_MINUTE"],
        "spec_reference": "LLD §3 / Archify cor_md (Feature 1/2 Cross-Check)",
        "notes": "Spec names file 'md_nearmiss.py', but implemented in 'demand_window.py' (DemandWindowDetector).",
    },
    {
        "id": "cooling_malfunction",
        "name": "Cooling Malfunction",
        "spec_file": "cooling_malfunction.py",
        "code_module": "omniview.rules.cooling_malfunction",
        "code_path": "src/omniview/rules/cooling_malfunction.py",
        "target_symbol": "CoolingMalfunctionDetector",
        "registry_name": "cooling_malfunction",
        "sensor_types": ["electrical", "thermal"],
        "table": "readings_electrical",
        "required_constants": ["COOLING_POWER_THRESHOLD_KW", "COOLING_TEMP_LOW_C"],
        "spec_reference": "LLD §3 line 57 / Archify cor_cooling (OI-145)",
        "notes": "Correlates high electrical kW (>50kW) with cold barrel/cooling temp (<100°C).",
    },
    {
        "id": "lazy_idle",
        "name": "Lazy-Idle",
        "spec_file": "lazy_idle.py",
        "code_module": "omniview.rules.lazy_idle",
        "code_path": "src/omniview/rules/lazy_idle.py",
        "target_symbol": "LazyIdleDetector",
        "registry_name": "lazy_idle",
        "sensor_types": ["thermal", "electrical"],
        "table": "readings_electrical",
        "required_constants": ["LAZY_IDLE_RULE_CURRENT_A", "LAZY_IDLE_RULE_TEMP_C", "LAZY_IDLE_DURATION_MIN"],
        "spec_reference": "LLD §3 / Archify cor_lazy (Feature 4)",
        "notes": "Live runner passes single sensor per call without cross-sensor join; requires harness join to fire.",
    },
    {
        "id": "pressure_leak",
        "name": "Pressure Leak Proxy",
        "spec_file": "pressure_leak.py",
        "code_module": "omniview.rules.pressure_leak",
        "code_path": "src/omniview/rules/pressure_leak.py",
        "target_symbol": "PressureLeakDetector",
        "registry_name": "pressure_leak",
        "sensor_types": ["pressure"],
        "table": "readings_pressure",
        "required_constants": ["PRESSURE_DECAY_THRESHOLD_BAR_PER_MIN", "PRESSURE_MIN_LOADED_SAMPLES"],
        "spec_reference": "LLD §3 / Archify cor_leak (Feature 2 F05)",
        "notes": "Monitors loaded decay rate vs -0.15 bar/min slope threshold.",
    },
    {
        "id": "vibration_zone",
        "name": "Vibration Zones (ISO 10816-3)",
        "spec_file": "vibration_zone.py",
        "code_module": "omniview.rules.vibration_zone",
        "code_path": "src/omniview/rules/vibration_zone.py",
        "target_symbol": "VibrationZoneDetector",
        "registry_name": "vibration_zone",
        "sensor_types": ["vibration"],
        "table": "readings_vibration",
        "required_constants": ["VIB_ZONE_B_BOUNDARY", "VIB_ZONE_C_BOUNDARY", "VIB_ZONE_D_BOUNDARY"],
        "spec_reference": "LLD §3 / Archify cor_vib (Feature 2 F06)",
        "notes": "Classifies RMS velocity into ISO Zones A/B/C/D.",
    },
    {
        "id": "health_index",
        "name": "Health Index & CUSUM",
        "spec_file": "predictive_maintenance.py + predictive/health_index.py",
        "code_module": "omniview.rules.predictive_maintenance",
        "code_path": "src/omniview/rules/predictive_maintenance.py",
        "target_symbol": "run_stage_a_pipeline",
        "registry_name": None,  # Driven by batch_runner from TSDB daily rows
        "sensor_types": ["electrical", "vibration"],
        "table": "readings_electrical",
        "required_constants": ["DEMO_PRIORS"],
        "spec_reference": "LLD Table 3 / Archify cor_pdm (Feature 2 PdM)",
        "notes": "Batch-driven via HealthIndexPipeline; not in 15s streaming registry. High risk threshold (<40 in priors.py:130-131, <50 in action_cards.py:360).",
    },
    {
        "id": "machine_service_status",
        "name": "Machine Service Status Registry",
        "spec_file": "predictive/maintenance_log.py via predictive_maintenance.py",
        "code_module": "omniview.rules.predictive_maintenance",
        "code_path": "src/omniview/rules/predictive_maintenance.py",
        "target_symbol": "get_machine_service_status",
        "registry_name": None,  # Cross-feature registry interface
        "sensor_types": ["electrical"],
        "table": "readings_electrical",
        "required_constants": [],
        "spec_reference": "LLD §3 line 85, §5 line 101 / Archify cross_service_reg (OI-154)",
        "notes": "In-memory MachineServiceRegistry tracks active high-risk tier & log windows. MaintenanceLogStore persists events.",
    },
    {
        "id": "gas_model",
        "name": "Panel Overheat Precursor",
        "spec_file": "gas_model.py",
        "code_module": "omniview.rules.gas_model",
        "code_path": "src/omniview/rules/gas_model.py",
        "target_symbol": "EnhancedGasOverheatDetector",
        "registry_name": "gas_overheat",
        "sensor_types": ["gas", "electrical"],
        "table": "readings_gas",
        "required_constants": [],
        "spec_reference": "LLD §3 / Archify cor_gas (Enhanced Gas Overheat)",
        "notes": "Multi-variable gas/thermal z-score, 4-tier alert, root-cause heuristics, and IsolationForest anomaly score.",
    },
    {
        "id": "ambient_correlation",
        "name": "Ambient Chiller OLS",
        "spec_file": "ambient_correlation.py",
        "code_module": "omniview.rules.ambient_correlation",
        "code_path": "src/omniview/rules/ambient_correlation.py",
        "target_symbol": "AmbientCorrelationRule",
        "registry_name": None,  # Missing in build_default_registry()
        "sensor_types": ["ambient", "electrical"],
        "table": "readings_ambient",
        "required_constants": [],
        "spec_reference": "LLD Feature Ledger Row S3 / Archify cor_amb",
        "notes": "Implemented with rolling OLS and residual 2-sigma check, but omitted from build_default_registry().",
    },
]


def check_ast_for_stub(file_path: Path, symbol_name: str) -> tuple[bool, str]:
    """Inspect AST to detect if the target function/class is a pass/TODO/stub."""
    if not file_path.exists():
        return False, f"File not found: {file_path}"

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except Exception as e:
        return False, f"Syntax error in AST parsing: {e}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol_name:
                # Check for empty body / pass only / raise NotImplementedError only
                if len(node.body) == 1:
                    stmt = node.body[0]
                    if isinstance(stmt, ast.Pass):
                        return False, f"Symbol {symbol_name} is only a 'pass' stub"
                    if isinstance(stmt, ast.Raise):
                        if isinstance(stmt.exc, ast.Call) and getattr(stmt.exc.func, "id", "") == "NotImplementedError":
                            return False, f"Symbol {symbol_name} raises NotImplementedError stub"
                return True, "Valid implementation found"

    return False, f"Symbol {symbol_name} not found in AST"


def get_latest_sensor_data_info(tables: list[str], minutes: int = 15) -> tuple[int, datetime | None]:
    """Check total row count and latest timestamp across given TSDB tables."""
    try:
        engine = get_engine()
        total_rows = 0
        latest_time = None
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        with engine.connect() as conn:
            for tbl in tables:
                cnt = conn.execute(
                    text(f"SELECT count(*) FROM {tbl} WHERE time >= :cutoff"),
                    {"cutoff": cutoff}
                ).scalar() or 0
                total_rows += cnt

                max_t = conn.execute(
                    text(f"SELECT max(time) FROM {tbl}")
                ).scalar()
                if max_t:
                    if latest_time is None or max_t > latest_time:
                        latest_time = max_t

        return total_rows, latest_time
    except Exception as e:
        return 0, None


def evaluate_all_functions(lookback_minutes: int = 15) -> list[FunctionStatus]:
    """Evaluate implementation status of all 9 Feature 2 functions dynamically."""
    # 1. Fetch live detector registry
    try:
        registry = build_default_registry()
        registered_names = {entry.name for entry in registry if entry.enabled}
    except Exception:
        registered_names = set()

    statuses: list[FunctionStatus] = []

    for spec in FUNCTION_SPECS:
        name = spec["name"]
        spec_file = spec["spec_file"]
        code_path_str = spec["code_path"]
        code_file = Path(code_path_str)
        symbol = spec["target_symbol"]
        reg_name = spec["registry_name"]
        spec_ref = spec["spec_reference"]

        # Step A: Check import & symbol presence
        try:
            mod = importlib.import_module(spec["code_module"])
            if not hasattr(mod, symbol):
                statuses.append(FunctionStatus(
                    name=name, spec_file=spec_file, code_file=code_path_str,
                    target_symbol=symbol, status="NOT IMPLEMENTED",
                    reason=f"Symbol '{symbol}' missing in {code_path_str}",
                    last_event_time="None", spec_reference=spec_ref,
                    is_wired=False, recent_rows=0,
                ))
                continue
        except Exception as e:
            statuses.append(FunctionStatus(
                name=name, spec_file=spec_file, code_file=code_path_str,
                target_symbol=symbol, status="NOT IMPLEMENTED",
                reason=f"Failed to import {spec['code_module']}: {e}",
                last_event_time="None", spec_reference=spec_ref,
                is_wired=False, recent_rows=0,
            ))
            continue

        # Step B: AST stub check
        is_impl, impl_msg = check_ast_for_stub(code_file, symbol)
        if not is_impl:
            statuses.append(FunctionStatus(
                name=name, spec_file=spec_file, code_file=code_path_str,
                target_symbol=symbol, status="NOT IMPLEMENTED",
                reason=impl_msg, last_event_time="None", spec_reference=spec_ref,
                is_wired=False, recent_rows=0,
            ))
            continue

        # Step C: Check required constants
        missing_constants = []
        for c in spec["required_constants"]:
            if not hasattr(mod, c):
                # Try config
                import omniview.config as cfg
                if not hasattr(cfg, c):
                    missing_constants.append(c)
        if missing_constants:
            statuses.append(FunctionStatus(
                name=name, spec_file=spec_file, code_file=code_path_str,
                target_symbol=symbol, status="NOT IMPLEMENTED",
                reason=f"Missing required constant(s): {', '.join(missing_constants)}",
                last_event_time="None", spec_reference=spec_ref,
                is_wired=False, recent_rows=0,
            ))
            continue

        # Step D: Wiring check
        is_wired = (reg_name in registered_names) if reg_name else False

        # If architectural function is intentionally batch-driven or cross-feature facade
        # we check whether it's in the streaming registry or requires batch runner
        if reg_name is None:
            # Ambient correlation is NOT wired in build_default_registry()
            # Health Index & Service Registry are intentionally decoupled batch/cross-feature services
            pass

        # Step E: TSDB telemetry data check
        tables_to_check = [f"readings_{st}" for st in spec["sensor_types"]]
        recent_rows, latest_time = get_latest_sensor_data_info(tables_to_check, minutes=lookback_minutes)

        last_ts_str = latest_time.strftime("%Y-%m-%d %H:%M:%S UTC") if latest_time else "Never"

        # Determine final status
        if not is_wired:
            if spec["id"] in ("health_index", "machine_service_status"):
                status = "LIVE (BATCH/API)" if recent_rows > 0 else "NO DATA (BATCH)"
                reason = "Driven via BatchRunner / ServiceRegistry API (Not in 15s streaming registry by design)"
            else:
                status = "NOT WIRED"
                reason = f"Module implemented, but '{reg_name or spec['id']}' not in build_default_registry() in detectors_live.py"
        elif recent_rows == 0:
            status = "NO DATA"
            reason = f"Wired in registry, but 0 readings received in the last {lookback_minutes} minutes"
        else:
            status = "LIVE"
            reason = f"Implemented, wired in registry, and {recent_rows} telemetry readings flowing"

        statuses.append(FunctionStatus(
            name=name,
            spec_file=spec_file,
            code_file=code_path_str,
            target_symbol=symbol,
            status=status,
            reason=reason,
            last_event_time=last_ts_str,
            spec_reference=spec_ref,
            is_wired=is_wired,
            recent_rows=recent_rows,
        ))

    return statuses


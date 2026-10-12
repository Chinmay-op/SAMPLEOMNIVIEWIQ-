import os
import sys
import json
import time
import io
from pathlib import Path

# Fix Windows terminal encoding — force UTF-8 output
if sys.platform == "win32":
    os.system("")  # enable ANSI escapes on Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic
from omniview.rules.gas_model import EnhancedGasOverheatDetector, GasOverheatEvent, GasSensorFaultEvent

class C:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"

detector = EnhancedGasOverheatDetector()

def on_message(topic, payload):
    try:
        # Extract raw bot values for display
        data = payload.get("data", {})
        gas = data.get("gas_concentration_ppm", 0)
        part = data.get("micro_particle_index", 0)
        temp = data.get("internal_panel_temp_c", 0)
        
        print(f"\n{C.DIM}--------------------------------------------------{C.END}", flush=True)
        print(f"{C.BOLD}INCOMING READING:{C.END} Gas={gas}ppm | Particles={part} | Temp={temp}°C", flush=True)
        
        # Run through the gas model pipeline!
        event = detector.evaluate(payload)
        
        if event is None:
            print(f"  {C.GREEN}MODEL OUTPUT: Normal (No Event){C.END}", flush=True)
            
        elif isinstance(event, GasSensorFaultEvent):
            print(f"  {C.YELLOW}MODEL OUTPUT: SENSOR FAULT - {event.fault_type}{C.END}", flush=True)
            print(f"    Details: {event.details}", flush=True)
            
        elif isinstance(event, GasOverheatEvent):
            color = C.RED if event.severity == "CRITICAL" else C.YELLOW
            print(f"  {color}MODEL OUTPUT: {event.tier} ({event.severity}){C.END}", flush=True)
            print(f"    Root Cause : {event.root_cause}", flush=True)
            print(f"    Confidence : {event.confidence_score:.1f} / 100", flush=True)
            print(f"    Health Idx : {event.equipment_health_index:.1f}", flush=True)
            print(f"    Cost Impact: INR {event.estimated_cost_impact_inr:,.0f}", flush=True)
            
    except Exception as e:
        print(f"Error processing message: {e}", flush=True)

if __name__ == "__main__":
    topic = build_topic("pune-isbm", "compressor-01", "gas")
    print(f"{C.CYAN}Connected to MQTT broker. Listening on '{topic}' for live gas bot data...{C.END}\n", flush=True)
    
    with OmniViewMQTTClient() as client:
        client.subscribe(topic, on_message)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nExiting...", flush=True)

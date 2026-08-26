import json
import time
import uuid
import paho.mqtt.client as mqtt

from omniview.edge.bots.electrical_bot import generate_reading as e_read
from omniview.edge.bots.vibration_bot import generate_reading as v_read
from omniview.edge.bots.thermal_bot import generate_reading as t_read
from omniview.edge.bots.pressure_bot import generate_reading as p_read
from omniview.edge.bots.gas_bot import generate_reading as g_read
from omniview.edge.bots.stroke_bot import generate_reading as s_read
from omniview.edge.bots.ambient_bot import generate_reading as a_read

from omniview.ingest.validation import validate_payload

BROKER = "broker.hivemq.com"
PORT = 1883
BASE_TOPIC = f"omniview/pune-isbm/test-{uuid.uuid4().hex[:8]}"

bots = {
    "electrical": e_read,
    "vibration": v_read,
    "thermal": t_read,
    "pressure": p_read,
    "gas": g_read,
    "stroke": s_read,
    "ambient": a_read
}

results = {"received": 0, "passed_validation": 0}

def on_message(client, userdata, msg):
    payload_str = msg.payload.decode()
    topic = msg.topic
    print(f"\n[SUBSCRIBER] Received message on topic: {topic}")
    
    sensor_type = topic.split("/")[-1]
    results["received"] += 1
    
    try:
        data = json.loads(payload_str)
        # Run the exact same validation as the ingest pipeline!
        validate_payload(sensor_type, "1.0", data)
        print(f"  ✅ Validation PASSED for {sensor_type}!")
        results["passed_validation"] += 1
    except Exception as e:
        print(f"  ❌ Validation FAILED for {sensor_type}: {e}")

if __name__ == "__main__":
    print(f"Starting E2E Pipeline Test against {BROKER}...")
    
    # Start Subscriber
    sub_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sub-{uuid.uuid4()}")
    sub_client.on_message = on_message
    sub_client.connect(BROKER, PORT, 60)
    sub_client.subscribe(f"{BASE_TOPIC}/#", qos=1)
    sub_client.loop_start()
    
    # Wait for subscription
    time.sleep(2)
    
    # Start Publisher
    pub_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pub-{uuid.uuid4()}")
    pub_client.connect(BROKER, PORT, 60)
    pub_client.loop_start()
    
    print("\nPublishing all 7 simulated payloads over the internet...")
    for sensor_type, bot_func in bots.items():
        payload = bot_func()
        topic = f"{BASE_TOPIC}/{sensor_type}"
        pub_client.publish(topic, json.dumps(payload), qos=1)
        print(f"[PUBLISHER] Published {sensor_type} -> {topic}")
        time.sleep(0.5)
        
    time.sleep(3)
    
    pub_client.loop_stop()
    sub_client.loop_stop()
    
    print("\n=== E2E Pipeline Test Summary ===")
    print(f"Messages published: 7")
    print(f"Messages received:  {results['received']}")
    print(f"Validation passes:  {results['passed_validation']}")
    if results['passed_validation'] == 7:
        print("🎉 PIPELINE IS 100% HEALTHY AND PRD-COMPLIANT!")
    else:
        print("⚠️ Pipeline failed validation.")

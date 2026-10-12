import paho.mqtt.client as mqtt
import json
import time

messages = []

def on_connect(client, userdata, flags, rc):
    client.subscribe("pune-isbm/compressor-01/gas")

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    data = payload.get("data", {})
    gas = data.get("gas_concentration_ppm", 0)
    part = data.get("micro_particle_index", 0)
    temp = data.get("internal_panel_temp_c", 0)
    messages.append((gas, part, temp))
    print(f"📥 INCOMING READING: Gas={gas}ppm | Particles={part} | Temp={temp}°C")

print("Starting subscriber...")
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("localhost", 1883, 60)
client.loop_start()

time.sleep(5)
client.loop_stop()
print("Finished.")

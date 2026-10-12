import time
import subprocess
import sys

print("Running live demo for 5 seconds...", flush=True)
p = subprocess.Popen([sys.executable, "tests/live_demo_mqtt.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

time.sleep(7)
p.terminate()

out, err = p.communicate()
print("OUTPUT:")
print(out)
if err:
    print("ERRORS:")
    print(err)

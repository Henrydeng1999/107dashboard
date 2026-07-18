import time

print("dashboard_test=cancelable-task", flush=True)
for step in range(1, 61):
    print(f"heartbeat={step}", flush=True)
    time.sleep(2)
print("result=completed-without-cancel", flush=True)

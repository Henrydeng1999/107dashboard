import time

print("dashboard_test=log-stream", flush=True)
for step in range(1, 6):
    print(f"progress={step}/5", flush=True)
    time.sleep(4)
print("result=ok", flush=True)

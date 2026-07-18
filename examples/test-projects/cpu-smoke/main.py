import os
import platform

print("dashboard_test=cpu-smoke", flush=True)
print(f"python={platform.python_version()}", flush=True)
print(f"host={platform.node()}", flush=True)
print(f"slurm_job_id={os.environ.get('SLURM_JOB_ID', 'missing')}", flush=True)
print("result=ok", flush=True)

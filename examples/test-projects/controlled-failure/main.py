import sys

print("dashboard_test=controlled-failure", flush=True)
print("expected_error=acceptance failure with exit code 17", file=sys.stderr, flush=True)
raise SystemExit(17)

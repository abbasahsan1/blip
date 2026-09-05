#!/usr/bin/env python3
"""
Infrastructure verification script for MinIO S3 and NATS JetStream.
Can be executed directly or via `make verify-infra`.
"""

import sys
import json
import urllib.request
import urllib.error
import subprocess

READY_URLS = [
    "http://127.0.0.1:8419/readyz",
    "http://100.122.207.32:8419/readyz",
]


def check_readyz():
    print("\n--- 1. Testing /readyz Health Probe Endpoint ---")
    data = None
    status_code = None
    for url in READY_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "infra-verifier"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                status_code = resp.status
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                print(f"  Connected via {url} -> HTTP {status_code}")
                break
        except Exception:
            continue

    if not data:
        # Fallback query via kubectl exec
        print("  Direct HTTP not responding, querying via kubectl exec...")
        cmd = [
            "kubectl", "exec", "-n", "blipp", "deployment/auth-service", "--",
            "python3", "-c",
            "import urllib.request, json; resp = urllib.request.urlopen('http://localhost:8000/readyz'); print(resp.read().decode())"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            try:
                data = json.loads(res.stdout.strip())
                status_code = 200
            except Exception as e:
                print(f"  Error parsing kubectl exec output: {e}")

    if data:
        print(f"  Readiness Payload: {json.dumps(data, indent=2)}")
        components = data.get("components", {})
        db_ok = components.get("database") == "healthy"
        storage_ok = components.get("storage") == "healthy"
        nats_ok = components.get("event_bus") == "healthy"

        print(f"  [DB] Database:           {'PASS' if db_ok else 'FAIL'}")
        print(f"  [S3] MinIO Storage:      {'PASS' if storage_ok else 'FAIL'}")
        print(f"  [BUS] NATS JetStream:    {'PASS' if nats_ok else 'FAIL'}")

        if db_ok and storage_ok and nats_ok:
            print("  All components are healthy and ready!")
            return True
        else:
            print("  Some components reported unhealthy status.")
            return False
    else:
        print("  FAILED to query /readyz probe.")
        return False


def run_pod_integration_tests():
    print("\n--- 2. Running MinIO & NATS JetStream Pytest Suite Inside Pod ---")
    cmd = [
        "kubectl", "exec", "-n", "blipp", "deployment/auth-service", "--",
        "python3", "-m", "pytest", "tests/test_infra.py", "-v", "-s"
    ]
    print(f"  Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    return res.returncode == 0


def main():
    print("==================================================================")
    print("🚀 Blipp Dev Infrastructure Verification (MinIO + NATS JetStream)")
    print("==================================================================")

    # 1. Check readyz probe
    ready_ok = check_readyz()

    # 2. Run integration tests in pod
    tests_ok = run_pod_integration_tests()

    print("\n==================================================================")
    if ready_ok and tests_ok:
        print("🎉 SUCCESS: MinIO & NATS JetStream infrastructure is fully verified!")
        print("==================================================================")
        sys.exit(0)
    else:
        print("❌ FAILURE: Infrastructure verification had issues.")
        print("==================================================================")
        sys.exit(1)


if __name__ == "__main__":
    main()

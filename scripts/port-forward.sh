#!/usr/bin/env bash
set -euo pipefail
NAMESPACE="${NAMESPACE:-blipp}"

pkill -f "kubectl port-forward.*(8000|8001|8002|8080|9000)" 2>/dev/null || true
sleep 1

kubectl port-forward --address 0.0.0.0 svc/auth-service 8000:8000 -n "${NAMESPACE}" >/dev/null 2>&1 &
kubectl port-forward --address 0.0.0.0 svc/content-ingest-service 8001:8001 -n "${NAMESPACE}" >/dev/null 2>&1 &
kubectl port-forward --address 0.0.0.0 svc/feed-service 8002:8002 -n "${NAMESPACE}" >/dev/null 2>&1 &
kubectl port-forward --address 0.0.0.0 svc/keycloak 8080:8080 -n "${NAMESPACE}" >/dev/null 2>&1 &
kubectl port-forward --address 0.0.0.0 svc/minio 9000:9000 -n "${NAMESPACE}" >/dev/null 2>&1 &

sleep 2
echo "Port forwards active for auth (8000), content-ingest (8001), feed (8002), keycloak (8080), and minio (9000)."

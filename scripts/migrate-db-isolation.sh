#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-blipp}"
SQL_FILE="$(dirname "$0")/../k8s/postgres/init-dbs.sql"

echo "==> Locating PostgreSQL pod in namespace '${NAMESPACE}'..."
POSTGRES_POD=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [ -z "${POSTGRES_POD}" ]; then
  echo "Error: No PostgreSQL pod found in namespace '${NAMESPACE}'." >&2
  exit 1
fi

echo "==> PostgreSQL pod identified: ${POSTGRES_POD}"
echo "==> Applying database creation and privilege grants..."

kubectl exec -i -n "${NAMESPACE}" "${POSTGRES_POD}" -- psql -U keycloak -d keycloak < "${SQL_FILE}"

echo "==> Database migration completed successfully."
echo "Created/verified databases:"
kubectl exec -i -n "${NAMESPACE}" "${POSTGRES_POD}" -- psql -U keycloak -d keycloak -c "\l" | grep -E "blipp_|keycloak" || true

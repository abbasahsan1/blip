#!/usr/bin/env bash
set -euo pipefail

# Determine repository and app directories
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${REPO_ROOT}/apps/blipp"
NAMESPACE="${NAMESPACE:-blipp}"

echo "============================================================"
echo "🚀 Blipp Mobile Development Environment (Tailscale / Expo Go)"
echo "============================================================"

# ------------------------------------------------------------------------------
# 1. IP Resolution Logic
# ------------------------------------------------------------------------------
DEV_HOST_IP=""
IP_SOURCE=""

# Check manual override
if [ -n "${DEV_HOST_IP:-}" ]; then
  IP_SOURCE="Manual Override"
elif [ -n "${LAN_IP:-}" ]; then
  DEV_HOST_IP="$LAN_IP"
  IP_SOURCE="LAN_IP Override"
fi

# 1a. Detect if Tailscale is running via tailscale ip -4
if [ -z "$DEV_HOST_IP" ] && command -v tailscale >/dev/null 2>&1; then
  TS_IP=$(tailscale ip -4 2>/dev/null || true)
  if [[ "$TS_IP" =~ ^100\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    DEV_HOST_IP="$TS_IP"
    IP_SOURCE="Tailscale"
  fi
fi

# 1b. Fall back to LAN IP if Tailscale is unavailable
if [ -z "$DEV_HOST_IP" ]; then
  if [[ "$OSTYPE" == "darwin"* ]]; then
    CANDIDATE_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
    if [ -n "$CANDIDATE_IP" ] && [[ ! "$CANDIDATE_IP" =~ ^127\. ]] && [[ ! "$CANDIDATE_IP" =~ ^172\.(17|18)\. ]]; then
      DEV_HOST_IP="$CANDIDATE_IP"
      IP_SOURCE="macOS LAN"
    fi
  else
    # Linux: default route IP via ip route get 1.1.1.1
    CANDIDATE_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || true)
    if [ -n "$CANDIDATE_IP" ] && [[ ! "$CANDIDATE_IP" =~ ^127\. ]] && [[ ! "$CANDIDATE_IP" =~ ^172\.(17|18)\. ]]; then
      DEV_HOST_IP="$CANDIDATE_IP"
      IP_SOURCE="LAN"
    fi
  fi
fi

# 1c. Secondary fallback: hostname -I (excluding loopback and Docker bridge networks 172.17.x / 172.18.x)
if [ -z "$DEV_HOST_IP" ]; then
  for ip in $(hostname -I 2>/dev/null || true); do
    if [[ ! "$ip" =~ ^127\. ]] && [[ ! "$ip" =~ ^172\.(17|18)\. ]]; then
      DEV_HOST_IP="$ip"
      IP_SOURCE="LAN interface"
      break
    fi
  done
fi

if [ -z "$DEV_HOST_IP" ]; then
  echo "❌ Error: Could not automatically detect a valid reachable IP address (excluding Docker bridges)."
  echo "   Please specify manually: DEV_HOST_IP=100.x.y.z $0"
  exit 1
fi

echo "Resolved reachable IP: ${DEV_HOST_IP} (${IP_SOURCE})"

# ------------------------------------------------------------------------------
# 2. Generate apps/blipp/.env
# ------------------------------------------------------------------------------
ENV_FILE="${APP_DIR}/.env"
echo "⚙️  Generating ${ENV_FILE}..."

cat <<EOF > "${ENV_FILE}"
EXPO_PUBLIC_API_URL=http://${DEV_HOST_IP}:8000
EXPO_PUBLIC_CONTENT_INGEST_URL=http://${DEV_HOST_IP}:8001
EXPO_PUBLIC_FEED_URL=http://${DEV_HOST_IP}:8002
EXPO_PUBLIC_SOCIAL_GRAPH_URL=http://${DEV_HOST_IP}:8003
EXPO_PUBLIC_MESSAGING_URL=http://${DEV_HOST_IP}:8004
EXPO_PUBLIC_MODERATION_URL=http://${DEV_HOST_IP}:8005
EXPO_PUBLIC_MINIO_URL=http://${DEV_HOST_IP}:9000
EXPO_PUBLIC_KEYCLOAK_URL=http://${DEV_HOST_IP}:8080
S3_PUBLIC_ENDPOINT_URL=http://${DEV_HOST_IP}:9000
EOF

echo "   Configuration written successfully."

# ------------------------------------------------------------------------------
# 3. Ensure Port-Forwarding (Optional / Automatic)
# ------------------------------------------------------------------------------
# If --ports-only flag is passed, run make port-forward and exit
if [ "${1:-}" = "--ports-only" ]; then
  make -C "${REPO_ROOT}" port-forward
  exit 0
fi

# Ensure port forwarding is active on 0.0.0.0 if cluster is reachable
if kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "🔗 Ensuring Kubernetes port-forwards are active on 0.0.0.0..."
  make -C "${REPO_ROOT}" port-forward
fi

# ------------------------------------------------------------------------------
# 4. Configure Metro Bundler Hostname & Launch
# ------------------------------------------------------------------------------
export REACT_NATIVE_PACKAGER_HOSTNAME="${DEV_HOST_IP}"

echo "📱 Launching Metro Bundler for ${DEV_HOST_IP}..."
echo "   Scan the QR code in the Expo Go app on your physical mobile device."
echo "   (Make sure your phone is connected to Tailscale)"
echo ""

# Free port 8081 if previously occupied by a detached metro instance
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8081/tcp 2>/dev/null || true
fi

cd "${APP_DIR}"
exec npx expo start --clear "$@"

#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# remote-deploy.sh - runs ON the EC2 host. Never run this by hand during a
# normal deploy; GitHub Actions calls it over SSH.
#
#   usage: remote-deploy.sh <full-image-uri> <git-sha>
#
# Strategy (this is the "zero-downtime + rollback" bullet on the resume):
#   1. pull the new image
#   2. start it on the *free* of two ports (8000 / 8001)
#   3. poll /health until it answers (or time out => rollback)
#   4. repoint the nginx upstream at the new port and reload nginx (no drop)
#   5. only then remove the old container
# ---------------------------------------------------------------------------
set -euo pipefail

IMAGE="${1:?usage: remote-deploy.sh <image-uri> <git-sha>}"
SHA="${2:-unknown}"

APP_DIR="/opt/expense-api"
ACTIVE_PORT_FILE="${APP_DIR}/active_port"
ENV_FILE="${APP_DIR}/app.env"
UPSTREAM_FILE="/etc/nginx/conf.d/upstream-expense-api.conf"
APP_NAME="expense-api"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-45}"
LOCK_FILE="/tmp/expense-api-deploy.lock"
AWS_REGION="${AWS_REGION:-ap-south-1}"

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }

# Never let two deploys overlap.
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  log "another deploy is already running - exiting"
  exit 1
fi

# ---------------------------------------------------------------- 1. login --
REGISTRY="${IMAGE%%/*}"
log "logging in to ${REGISTRY}"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}" >/dev/null

log "pulling ${IMAGE}"
docker pull "${IMAGE}"

# ------------------------------------------------------- 2. pick new port ----
CURRENT_PORT="$(cat "${ACTIVE_PORT_FILE}" 2>/dev/null || true)"
if [[ "${CURRENT_PORT}" == "8001" ]]; then
  NEW_PORT=8000
else
  NEW_PORT=8001
fi
NEW_CONTAINER="${APP_NAME}-${NEW_PORT}"
log "active port=[${CURRENT_PORT:-none}] new port=[${NEW_PORT}]"

# Clean up a leftover failed container on that port, if any.
docker rm -f "${NEW_CONTAINER}" >/dev/null 2>&1 || true

[[ -f "${ENV_FILE}" ]] || { log "missing ${ENV_FILE}"; exit 1; }

docker run -d \
  --name "${NEW_CONTAINER}" \
  --restart unless-stopped \
  --env-file "${ENV_FILE}" \
  -e GIT_SHA="${SHA}" \
  -p "127.0.0.1:${NEW_PORT}:8000" \
  -v expense-data:/data \
  --label "com.expense-api.sha=${SHA}" \
  "${IMAGE}" >/dev/null

# ------------------------------------------------------- 3. health gate ----
log "waiting up to ${HEALTH_TIMEOUT}s for /health on port ${NEW_PORT}"
HEALTHY=0
for _ in $(seq 1 "${HEALTH_TIMEOUT}"); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${NEW_PORT}/health" >/dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 1
done

if [[ "${HEALTHY}" -ne 1 ]]; then
  log "HEALTH CHECK FAILED - rolling back, old container stays live"
  docker logs --tail 60 "${NEW_CONTAINER}" 2>&1 || true
  docker rm -f "${NEW_CONTAINER}" >/dev/null 2>&1 || true
  exit 1
fi
log "new container is healthy"

# -------------------------------------------------------- 4. swap traffic --
printf 'upstream expense_api {\n    server 127.0.0.1:%s;\n    keepalive 16;\n}\n' \
  "${NEW_PORT}" > "${UPSTREAM_FILE}"

if ! nginx -t >/dev/null 2>&1; then
  log "nginx config invalid - reverting upstream and rolling back"
  printf 'upstream expense_api {\n    server 127.0.0.1:%s;\n    keepalive 16;\n}\n' \
    "${CURRENT_PORT}" > "${UPSTREAM_FILE}"
  docker rm -f "${NEW_CONTAINER}" >/dev/null 2>&1 || true
  exit 1
fi

nginx -s reload
echo "${NEW_PORT}" > "${ACTIVE_PORT_FILE}"
log "nginx now routes to port ${NEW_PORT}"

# ------------------------------------------------ 5. remove the old one ----
if [[ -n "${CURRENT_PORT}" && "${CURRENT_PORT}" != "${NEW_PORT}" ]]; then
  docker rm -f "${APP_NAME}-${CURRENT_PORT}" >/dev/null 2>&1 || true
  log "removed old container on port ${CURRENT_PORT}"
fi

# Reclaim disk - a full disk is the classic silent outage.
docker image prune -af --filter "until=168h" >/dev/null 2>&1 || true
df -h / | tail -1 | awk '{printf "[deploy] disk in use: %s\n", $5}'

log "deploy complete: ${SHA}"

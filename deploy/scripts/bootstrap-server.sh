#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# bootstrap-server.sh - run ONCE on a fresh Ubuntu 22.04 / 24.04 EC2 instance.
#
#   scp -i key.pem -r deploy ubuntu@EC2_IP:~/
#   ssh -i key.pem ubuntu@EC2_IP 'bash ~/deploy/scripts/bootstrap-server.sh'
#
# Installs Docker + nginx + AWS CLI, creates /opt/expense-api, installs the
# deploy script and the nginx site that proxies to 127.0.0.1:<active port>.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="/opt/expense-api"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '[bootstrap] %s\n' "$*"; }

log "installing packages"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y docker.io nginx curl unzip jq

sudo systemctl enable --now docker
sudo systemctl enable --now nginx
sudo usermod -aG docker "${USER}" || true

if ! command -v aws >/dev/null 2>&1; then
  log "installing AWS CLI v2 (needed for 'aws ecr get-login-password')"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  sudo /tmp/aws/install
fi

log "creating ${APP_DIR}"
sudo mkdir -p "${APP_DIR}/bin" "${APP_DIR}/logs"
sudo cp "${HERE}/remote-deploy.sh" "${APP_DIR}/bin/remote-deploy.sh"
sudo chmod +x "${APP_DIR}/bin/remote-deploy.sh"

if [[ ! -f "${APP_DIR}/app.env" ]]; then
  log "writing ${APP_DIR}/app.env (edit this for real secrets)"
  sudo tee "${APP_DIR}/app.env" >/dev/null <<'ENV'
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_URL=sqlite:////data/expenses.db
ENV
  sudo chmod 600 "${APP_DIR}/app.env"
fi

log "installing nginx site"
sudo cp "${HERE}/../nginx/expense-api.conf" /etc/nginx/sites-available/expense-api
sudo ln -sf /etc/nginx/sites-available/expense-api /etc/nginx/sites-enabled/expense-api
sudo rm -f /etc/nginx/sites-enabled/default

# Upstream include file, seeded with a port that is not in use yet.
if [[ ! -f /etc/nginx/conf.d/upstream-expense-api.conf ]]; then
  sudo tee /etc/nginx/conf.d/upstream-expense-api.conf >/dev/null <<'CONF'
upstream expense_api {
    server 127.0.0.1:8000;
    keepalive 16;
}
CONF
fi

sudo nginx -t
sudo systemctl reload nginx

# Docker named volume for the SQLite file.
sudo docker volume create expense-data >/dev/null

cat <<DONE

[bootstrap] done.
  - verify:      curl -s http://localhost/health
  - deploy:      from GitHub Actions (or: sudo ${APP_DIR}/bin/remote-deploy.sh <image> <sha>)
  - env/secrets: ${APP_DIR}/app.env (chmod 600)
  - NOTE: once the pipeline has run, open security group ports 80 (and 443 for TLS).
DONE

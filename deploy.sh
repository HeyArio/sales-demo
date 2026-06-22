#!/usr/bin/env bash
#
# deploy.sh — your one-word update command.
# Installed to /usr/local/bin/deploy by setup.sh, so you just type:  deploy
#
# It does the Python equivalent of "pull + npm install + pm2 restart":
#   1. git pull          (get latest code)
#   2. pip install       (update dependencies)
#   3. pm2 restart       (or start, the first time)
#
set -e

APP_DIR="/opt/sales-demo"
APP_NAME="sales-demo"
PORT=8000

cd "${APP_DIR}"

echo "==> Pulling latest code"
git pull

echo "==> Installing/updating Python dependencies"
./venv/bin/pip install -r requirements.txt

# Make sure the index exists; if not, remind the user (don't fail silently)
if [ ! -f "${APP_DIR}/index.json" ]; then
  echo ""
  echo "  !! index.json not found. Build it first:"
  echo "     cd ${APP_DIR} && set -a && source .env && set +a && \\"
  echo "       ./venv/bin/python build_index.py knowledge_base.json"
  echo ""
  exit 1
fi

echo "==> (Re)starting the app under pm2"
# pm2 needs the env var; we load .env and pass it through.
set -a
source "${APP_DIR}/.env"
set +a

if pm2 describe "${APP_NAME}" >/dev/null 2>&1; then
  pm2 restart "${APP_NAME}" --update-env
else
  # First launch: tell pm2 how to run uvicorn.
  # --interpreter points pm2 at the venv's python so it uses our installed deps.
  pm2 start "${APP_DIR}/venv/bin/uvicorn" \
    --name "${APP_NAME}" \
    --interpreter none \
    -- server:app --host 0.0.0.0 --port "${PORT}"
  pm2 save
fi

echo ""
echo "==> Done. App is running on port ${PORT}."
echo "    Logs:    pm2 logs ${APP_NAME}"
echo "    Status:  pm2 status"
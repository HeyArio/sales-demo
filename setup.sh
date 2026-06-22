#!/usr/bin/env bash
#
# setup.sh — RUN ONCE on the VPS to get everything installed and ready.
#
# Usage (as root or with sudo):
#   bash setup.sh
#
# After this finishes once, you'll use the `deploy` command for all future updates.
#
set -e

REPO_URL="https://github.com/HeyArio/sales-demo.git"
APP_DIR="/opt/sales-demo"
APP_NAME="sales-demo"
PORT=8000

echo "==> Updating system packages"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl

echo "==> Installing Node + pm2 (pm2 will manage the Python process)"
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
if ! command -v pm2 >/dev/null 2>&1; then
  npm install -g pm2
fi

echo "==> Cloning repo into ${APP_DIR}"
if [ -d "${APP_DIR}/.git" ]; then
  echo "    repo already exists, pulling latest"
  git -C "${APP_DIR}" pull
else
  git clone "${REPO_URL}" "${APP_DIR}"
fi

cd "${APP_DIR}"

echo "==> Creating Python virtual environment"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "==> Setting up the .env file for your API key"
if [ ! -f "${APP_DIR}/.env" ]; then
  cat > "${APP_DIR}/.env" <<'EOF'
# Put your real Mistral key on the next line, between the quotes.
MISTRAL_API_KEY="PASTE_YOUR_KEY_HERE"
EOF
  echo ""
  echo "  ****************************************************************"
  echo "  *  IMPORTANT: edit ${APP_DIR}/.env and paste your Mistral key  *"
  echo "  *  Run:  nano ${APP_DIR}/.env                                  *"
  echo "  ****************************************************************"
  echo ""
else
  echo "    .env already exists, leaving it alone"
fi

echo "==> Building the embeddings index (one-time, needs the key set)"
echo "    Skipping for now — run this AFTER you've put your key in .env:"
echo "      cd ${APP_DIR} && set -a && source .env && set +a && ./venv/bin/python build_index.py knowledge_base.json"

echo ""
echo "==> Installing the 'deploy' command"
cp "${APP_DIR}/deploy.sh" /usr/local/bin/deploy
chmod +x /usr/local/bin/deploy

echo ""
echo "============================================================"
echo " Setup complete. Next steps:"
echo "   1. nano ${APP_DIR}/.env      # paste your Mistral key"
echo "   2. cd ${APP_DIR} && set -a && source .env && set +a && \\"
echo "        ./venv/bin/python build_index.py knowledge_base.json"
echo "   3. deploy                     # starts everything"
echo "============================================================"
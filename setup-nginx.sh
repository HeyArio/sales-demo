#!/usr/bin/env bash
#
# setup-nginx.sh — OPTIONAL. Run once if you want the client to visit
#   http://185.110.188.92   (clean, no :8000 at the end)
#
# Without this, the app is reachable at http://185.110.188.92:8000
# With it, nginx listens on port 80 and forwards to uvicorn on 8000.
#
set -e

PORT=8000

echo "==> Installing nginx"
apt-get update -y
apt-get install -y nginx

echo "==> Writing nginx site config"
cat > /etc/nginx/sites-available/sales-demo <<EOF
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# enable it, disable the default welcome page
ln -sf /etc/nginx/sites-available/sales-demo /etc/nginx/sites-enabled/sales-demo
rm -f /etc/nginx/sites-enabled/default

echo "==> Testing and reloading nginx"
nginx -t
systemctl restart nginx
systemctl enable nginx

echo ""
echo "==> Done. The client can now visit:  http://185.110.188.92"
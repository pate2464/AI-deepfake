#!/usr/bin/env bash
#
# One-time setup for a fresh Vultr Cloud Compute VPS (Ubuntu 22.04+).
# Run as root: bash setup-vps.sh
#
set -euo pipefail

echo "==> Updating system packages"
apt-get update && apt-get upgrade -y

echo "==> Installing Docker"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    echo "    Docker already installed"
fi

echo "==> Installing Docker Compose plugin"
if ! docker compose version &>/dev/null; then
    apt-get install -y docker-compose-plugin
else
    echo "    Docker Compose already installed"
fi

echo "==> Configuring firewall (UFW)"
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Creating application directory"
APP_DIR="/opt/ai-deepfake"
mkdir -p "$APP_DIR/nginx/certs"

echo "==> Creating .env.production template"
if [ ! -f "$APP_DIR/.env.production" ]; then
    cat > "$APP_DIR/.env.production" <<'ENVEOF'
# App
DEBUG=false

# Database (Vultr Managed PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:password@host:port/dbname

# Gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash

# Object Storage (Vultr)
OBJECT_STORAGE_ENABLED=true
OBJECT_STORAGE_ENDPOINT_URL=https://ewr1.vultrobjects.com
OBJECT_STORAGE_REGION=us-east-1
OBJECT_STORAGE_BUCKET=
OBJECT_STORAGE_ACCESS_KEY_ID=
OBJECT_STORAGE_SECRET_ACCESS_KEY=
OBJECT_STORAGE_PREFIX=uploads

# ML
MODEL_CACHE_DIR=/app/models
ENVEOF
    echo "    Created $APP_DIR/.env.production — edit with real values"
else
    echo "    $APP_DIR/.env.production already exists, skipping"
fi

echo "==> Creating Docker volumes for persistent data"
docker volume create --name ai-deepfake_model_cache 2>/dev/null || true
docker volume create --name ai-deepfake_uploads 2>/dev/null || true

echo "==> Copying project files to $APP_DIR"
echo "    You need to copy the following files to the VPS:"
echo "      - docker-compose.prod.yml  -> $APP_DIR/docker-compose.prod.yml"
echo "      - nginx/nginx.conf         -> $APP_DIR/nginx/nginx.conf"
echo ""
echo "    Then log in to Vultr Container Registry:"
echo "      docker login <your-vultr-cr-url> -u <user> -p <pass>"
echo ""
echo "    And pull + start the stack:"
echo "      cd $APP_DIR"
echo "      export VULTR_CR_URL=<your-vultr-cr-url>"
echo "      docker compose -f docker-compose.prod.yml pull"
echo "      docker compose -f docker-compose.prod.yml up -d"

echo ""
echo "==> VPS setup complete!"

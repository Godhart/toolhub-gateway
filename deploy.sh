#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -f .env ]; then
    echo 'Copy .env.example to .env and configure your domain, email and router.' >&2
    exit 1
fi
# Trusted local config; POSIX NAME=value assignments.
set -a
. ./.env
set +a
: "${DOMAIN:?Set DOMAIN}"
: "${EMAIL:?Set EMAIL}"
: "${TOOLHUB_UPSTREAM:?Set TOOLHUB_UPSTREAM}"
case "$DOMAIN" in ''|*[!a-zA-Z0-9.-]*) echo 'Invalid DOMAIN' >&2; exit 1 ;; esac
case "$TOOLHUB_UPSTREAM" in ''|*[!a-zA-Z0-9.:-]*) echo 'Invalid TOOLHUB_UPSTREAM (hostname:port)' >&2; exit 1 ;; esac
if [ "$DOMAIN" = tools.example.com ] || [ "$EMAIL" = admin@example.com ]; then
    echo 'Replace the example DOMAIN and EMAIL.' >&2; exit 1
fi
if [ "${TOOLHUB_CONTAINER:-}" = YOUR_TOOLHUB_CONTAINER ]; then
    echo 'Set TOOLHUB_CONTAINER or leave it empty if the network is already configured.' >&2; exit 1
fi
docker compose version >/dev/null
# Compose >= 2.24 is needed for optional env_file support.
mkdir -p config data/keycloak-import data/letsencrypt data/webroot/.well-known/acme-challenge data/reload data/certbot-work data/certbot-logs
TOOLHUB_NETWORK=${TOOLHUB_NETWORK:-toolhub-edge}
export TOOLHUB_NETWORK
if ! docker network inspect "$TOOLHUB_NETWORK" >/dev/null 2>&1; then
    docker network create "$TOOLHUB_NETWORK"
fi
if [ -n "${TOOLHUB_CONTAINER:-}" ]; then
    upstream_alias=${TOOLHUB_UPSTREAM%:*}
    attached=$(docker inspect --format '{{range $name, $v := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$TOOLHUB_CONTAINER")
    if ! printf '%s\n' "$attached" | grep -Fx "$TOOLHUB_NETWORK" >/dev/null; then
        docker network connect --alias "$upstream_alias" "$TOOLHUB_NETWORK" "$TOOLHUB_CONTAINER"
    fi
fi
chmod 0700 config data
docker compose build --pull
docker compose run --rm --user "$(id -u):$(id -g)" setup
docker compose up -d postgres keycloak auth-gate
docker compose stop certbot
if [ -f "data/letsencrypt/live/$DOMAIN/fullchain.pem" ] && [ -f "data/letsencrypt/live/$DOMAIN/privkey.pem" ]; then
    NGINX_MODE=https docker compose up -d nginx
else
    NGINX_MODE=http docker compose up -d nginx
fi
printf 'ready\n' > data/webroot/.well-known/acme-challenge/ready
attempt=0
until docker compose exec -T nginx wget -q -O /dev/null http://127.0.0.1/.well-known/acme-challenge/ready; do
    if [ "$attempt" -ge 30 ]; then
        echo 'HTTP bootstrap not ready. Inspect docker compose logs nginx.' >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done
# Wait until the imported OAuth realm publishes discovery.
attempt=0
until docker compose exec -T auth-gate python -c "import urllib.request; urllib.request.urlopen('http://keycloak:8080/auth/realms/toolhub/.well-known/openid-configuration', timeout=5)"; do
    if [ "$attempt" -ge 90 ]; then
        echo 'Keycloak not ready. Inspect docker compose logs keycloak postgres.' >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done
docker compose run --rm certbot init
rm -f data/webroot/.well-known/acme-challenge/ready
NGINX_MODE=https docker compose up -d --force-recreate nginx
docker compose exec -T nginx nginx -t
docker compose up -d certbot
echo "Ready: https://$DOMAIN; OAuth enabled; renewal checks every 12 hours. Credentials: config/credentials.txt"

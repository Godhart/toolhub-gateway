#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
set -a
. ./.env
set +a
: "${OAUTH_REDIRECT_URI:?Set the exact ChatGPT callback in .env}"
case "$OAUTH_REDIRECT_URI" in
    https://chatgpt.com/*) ;;
    *) echo 'Only an HTTPS ChatGPT callback is allowed' >&2; exit 1 ;;
esac
case "$OAUTH_REDIRECT_URI" in *[!a-zA-Z0-9:/._-]*) echo 'Invalid callback' >&2; exit 1 ;; esac
docker compose exec -T -e "NEW_CALLBACK=$OAUTH_REDIRECT_URI" keycloak sh -c '
    set -eu
    cfg=$(mktemp /tmp/kcadm.XXXXXX)
    trap '\''rm -f "$cfg"'\'' EXIT
    /opt/keycloak/bin/kcadm.sh config credentials --config "$cfg" \
        --server http://localhost:8080/auth --realm master \
        --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"
    client=$(/opt/keycloak/bin/kcadm.sh get clients --config "$cfg" -r toolhub \
        -q clientId=chatgpt-toolhub --fields id --format csv --noquotes)
    [ -n "$client" ]
    /opt/keycloak/bin/kcadm.sh update "clients/$client" --config "$cfg" -r toolhub \
        -s "redirectUris=[\"$NEW_CALLBACK\"]"
'
echo 'OAuth callback updated. Reconnect the app in ChatGPT.'

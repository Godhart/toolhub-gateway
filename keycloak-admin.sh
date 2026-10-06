#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
docker compose exec -T keycloak sh -c '
    set -eu
    cfg=$(mktemp /tmp/kcadm.XXXXXX)
    trap '\''rm -f "$cfg"'\'' EXIT
    /opt/keycloak/bin/kcadm.sh config credentials --config "$cfg" \
        --server http://localhost:8080/auth --realm master \
        --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"
    /opt/keycloak/bin/kcadm.sh "$@" --config "$cfg"
' sh "$@"


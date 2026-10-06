#!/bin/sh
set -eu
case "${1:-renew-loop}" in
    init)
        exec certbot certonly --webroot -w /var/www/letsencrypt \
            --cert-name "$DOMAIN" -d "$DOMAIN" --email "$EMAIL" \
            --agree-tos --non-interactive --keep-until-expiring \
            --deploy-hook /usr/local/bin/notify-nginx
        ;;
    renew-loop)
        child=''
        trap 'if [ -n "$child" ]; then kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi; exit 0' TERM INT
        while :; do
            certbot renew --non-interactive --deploy-hook /usr/local/bin/notify-nginx &
            child=$!
            if wait "$child"; then
                echo '[certbot] renewal check succeeded'
            else
                echo '[certbot] renewal check failed; inspect logs; next check in 12h' >&2
            fi
            sleep 43200 &
            child=$!
            wait "$child"
        done
        ;;
    *) exec certbot "$@" ;;
esac

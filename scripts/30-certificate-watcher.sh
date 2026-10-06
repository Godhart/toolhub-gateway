#!/bin/sh
set -eu
(
    previous=''
    while :; do
        sleep 30
        current=$(cat /var/run/certbot-reload/generation 2>/dev/null || true)
        if [ -n "$current" ] && [ "$current" != "$previous" ]; then
            if nginx -t && nginx -s reload; then
                previous=$current
                echo "[certificate-watcher] nginx reloaded after certificate deployment"
            else
                echo "[certificate-watcher] reload failed; will retry" >&2
            fi
        fi
    done
) &

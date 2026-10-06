#!/bin/sh
set -eu
mkdir -p /var/run/certbot-reload
tmp=$(mktemp /var/run/certbot-reload/.generation.XXXXXX)
printf '%s\n' "$tmp-$(date +%s)" > "$tmp"
chmod 0644 "$tmp"
mv "$tmp" /var/run/certbot-reload/generation

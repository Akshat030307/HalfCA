#!/usr/bin/env bash
# Runs ON THE VPS (make deploy-domain pipes it over ssh).
# Routes a domain to Half CA through the shared Caddy in /root/mesh, which already
# terminates HTTPS for the other sites on this box.
#
#   route-domain.sh <domain> [--check]
#
# --check validates the would-be config and changes nothing.
set -euo pipefail

DOMAIN="$1"
MODE="${2:-apply}"
CADDYFILE=/root/mesh/Caddyfile
CONTAINER=mesh-caddy-1
UPSTREAM=172.18.0.1:8040

if grep -q "^${DOMAIN} {" "$CADDYFILE"; then
    echo "already routed: ${DOMAIN}"
    exit 0
fi

BLOCK=$(printf '\n# Half CA (added %s): static site + API on the docker bridge\n%s {\n\treverse_proxy %s\n}\n' \
    "$(date +%F)" "$DOMAIN" "$UPSTREAM")

# Validate the combined config inside the running Caddy (it has the env vars the
# existing blocks rely on) before touching the real file.
if ! { cat "$CADDYFILE"; printf '%s\n' "$BLOCK"; } \
    | docker exec -i "$CONTAINER" caddy validate --adapter caddyfile --config /dev/stdin >/dev/null 2>&1; then
    echo "the combined config does not validate; nothing changed" >&2
    exit 1
fi
echo "config with ${DOMAIN} validates"
[ "$MODE" = "--check" ] && exit 0

cp "$CADDYFILE" "$CADDYFILE.bak-halfca"
# Append in place: the file is a single-file bind mount, so it must keep its inode.
printf '%s\n' "$BLOCK" >> "$CADDYFILE"

if docker exec "$CONTAINER" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
    echo "routed ${DOMAIN} -> ${UPSTREAM} (backup: $CADDYFILE.bak-halfca)"
else
    cat "$CADDYFILE.bak-halfca" > "$CADDYFILE"
    echo "reload failed; Caddyfile restored" >&2
    exit 1
fi

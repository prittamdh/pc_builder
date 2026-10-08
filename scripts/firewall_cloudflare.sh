#!/usr/bin/env bash
# Only Cloudflare may reach the web ports (plan 03-02, OPS-02). Runbook: docs/DEPLOY.md.
#
# Docker's published ports (Caddy's 80/443) do not pass through the INPUT chain, so the
# rules go in DOCKER-USER, which Docker leaves alone and consults for every forwarded
# packet. Run by the pcbuilder-firewall systemd unit after Docker starts, and safe to run
# again: it rebuilds the PCB-CF chain from scratch each time.
#
# The OCI security list carries the same Cloudflare-only rule; this is the second layer.
set -euo pipefail

RANGES_URL="https://www.cloudflare.com/ips-v4"
CACHE=/etc/pcbuilder/cloudflare-ips-v4.txt
IFACE="$(ip route show default | awk '{print $5; exit}')"

mkdir -p "$(dirname "$CACHE")"
if FRESH="$(curl -fsS --max-time 15 "$RANGES_URL")" && grep -qE '^[0-9.]+/[0-9]+$' <<<"$FRESH"; then
  echo "$FRESH" > "$CACHE"
fi
[[ -s "$CACHE" ]] || { echo "no Cloudflare ranges (fetch failed, no cache)" >&2; exit 1; }

# PCB-CF: accept Cloudflare, drop everyone else, for traffic to the web ports.
iptables -N PCB-CF 2>/dev/null || iptables -F PCB-CF
while read -r cidr; do
  [[ -n "$cidr" ]] && iptables -A PCB-CF -s "$cidr" -j RETURN
done < "$CACHE"
iptables -A PCB-CF -j DROP

iptables -N DOCKER-USER 2>/dev/null || true
# Hook PCB-CF in for new connections arriving on the internet interface for ports
# 80/443 (Caddy's published ports map one-to-one, so after Docker's NAT the destination
# port is still 80 or 443). Remove any earlier copies of the hook first.
HOOK=(-i "$IFACE" -p tcp -m conntrack --ctstate NEW -m multiport --dports 80,443 -j PCB-CF)
OLD_HOOK=(-i "$IFACE" -p tcp -m conntrack --ctstate NEW -m conntrack --ctorigdstport 80:443 -m multiport --dports 80,443 -j PCB-CF)
while iptables -C DOCKER-USER "${OLD_HOOK[@]}" 2>/dev/null; do iptables -D DOCKER-USER "${OLD_HOOK[@]}"; done
while iptables -C DOCKER-USER "${HOOK[@]}" 2>/dev/null; do iptables -D DOCKER-USER "${HOOK[@]}"; done
iptables -I DOCKER-USER 1 "${HOOK[@]}"

echo "web ports on $IFACE: $(grep -c . "$CACHE") Cloudflare ranges allowed, everything else dropped"

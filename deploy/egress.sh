#!/usr/bin/env bash
# Keep SnipShare's containers to the public internet (D-102).
#
#   sudo deploy/egress.sh           apply, or re-apply after the network changed
#   sudo deploy/egress.sh --remove  take every rule this script made away again
#
# The app needs the internet (Google's keys, Turnstile, Resend, GIPHY, KLIPY, Chat)
# and nothing else. Docker's bridge lets a container reach the host it runs on, the
# other machines on the host's private network and the cloud's metadata service,
# which on most clouds hands out the machine's own credentials. Code that ever ran
# inside the app could otherwise walk from there to everything else on a shared host.
#
# Every rule matches only this project's own subnet, read from Docker, so nothing
# else on the host is touched. Rules live in one chain, SNIPSHARE-EGRESS, entered
# from DOCKER-USER (traffic leaving the host) and INPUT (traffic to the host itself).
# Run as root. Installed as a service by scripts/deploy.sh, so it holds after reboot.
set -euo pipefail

NETWORK=snipshare_snipshare
CHAIN=SNIPSHARE-EGRESS
TAG=snipshare-egress
PRIVATE=(0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16
         172.16.0.0/12 192.168.0.0/16 224.0.0.0/4 240.0.0.0/4)

# Every jump this script ever added, whatever subnet it was for.
unhook() {
  local chain rule words
  for chain in DOCKER-USER INPUT; do
    while read -r rule; do
      # `-S` prints `-A CHAIN ...`; the same words after `-D` delete that rule.
      read -ra words <<<"${rule#-A }"
      iptables -D "${words[@]}"
    done < <(iptables -S "$chain" 2>/dev/null | grep -- "--comment $TAG" || true)
  done
}

if [[ "${1:-}" == "--remove" ]]; then
  unhook
  iptables -F "$CHAIN" 2>/dev/null && iptables -X "$CHAIN" || true
  exit 0
fi

subnet="$(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}' "$NETWORK")"
subnet="${subnet%% *}"
[[ "$subnet" =~ ^[0-9.]+/[0-9]+$ ]] || { echo "no IPv4 subnet for $NETWORK" >&2; exit 1; }
# The resolvers Docker's own DNS forwards to may sit at a private or link-local
# address (a cloud's resolver often shares the metadata service's): DNS to those
# stays open, everything else to them is refused.
resolvers="$(sed -n 's/^nameserver[[:space:]]\+\([0-9.]\+\)$/\1/p' \
  /run/systemd/resolve/resolv.conf /etc/resolv.conf 2>/dev/null | grep -v '^127\.' | sort -u)"

iptables -N "$CHAIN" 2>/dev/null || iptables -F "$CHAIN"
iptables -A "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A "$CHAIN" -d "$subnet" -j RETURN
for ns in $resolvers; do
  iptables -A "$CHAIN" -d "$ns" -p udp --dport 53 -j RETURN
  iptables -A "$CHAIN" -d "$ns" -p tcp --dport 53 -j RETURN
done
for range in "${PRIVATE[@]}"; do
  iptables -A "$CHAIN" -d "$range" -j REJECT --reject-with icmp-admin-prohibited
done
iptables -A "$CHAIN" -j RETURN

unhook
iptables -I DOCKER-USER 1 -s "$subnet" -m comment --comment "$TAG" -j "$CHAIN"
# The host itself, at any of its addresses: nothing the app does needs it.
iptables -I INPUT 1 -s "$subnet" -m conntrack --ctstate NEW -m comment --comment "$TAG" \
  -j REJECT --reject-with icmp-admin-prohibited
echo "$CHAIN applied to $subnet"

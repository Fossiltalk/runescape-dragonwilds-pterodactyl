#!/bin/sh
# DNAT tailnet Dragonwilds traffic (udp game 7777, beacon 8888) to the Pterodactyl host ports
set -e
H=172.30.0.1
for P in 7777 8888; do
  iptables -t nat -A PREROUTING -i tailscale0 -p udp --dport $P -j DNAT --to-destination $H:$P
done
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
exec /usr/local/bin/containerboot

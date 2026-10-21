#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 kaantcp (https://github.com/kaantcp)
#
# Part of z380m-alpine: Alpine Linux on the ASUS ZenPad 8.0 (Z380M, MT8163).
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# for more details. You should have received a copy of the GNU General
# Public License along with this program (file LICENSE). If not, see
# <https://www.gnu.org/licenses/>.

Z380M_CREDIT="z380m-alpine by kaantcp - https://github.com/kaantcp"

# pc_usbnet.sh -- PC side of the Z380M tablet's USB network (RNDIS).          Run it with sudo.
#
#   sudo bash pc_usbnet.sh status   show what is set up (changes nothing)
#   sudo bash pc_usbnet.sh up       give the tablet's USB network interface 192.168.7.1/24 and share this PC's internet with it
#   sudo bash pc_usbnet.sh down     undo everything "up" did
#
# "up" changes exactly three things.  "down" undoes all of them, and a reboot of the PC clears them too:
#   1. the tablet's USB interface gets the address 192.168.7.1/24
#      (NetworkManager, if it runs, is told to leave that one interface alone, so it does not run DHCP on it)
#   2. net.ipv4.ip_forward is set to 1 (the old value is remembered and put back by "down")
#   3. one nftables table named z380m_usbnet with ONE NAT rule: traffic from 192.168.7.0/24 that leaves through any
#      interface other than the tablet's is masqueraded
# Nothing else is touched: no other nftables table, no other interface, no file except /run/z380m-usbnet.state.
#
# The tablet's interface is recognised by its USB ID 0e8d:2008 (what "z380m-usb rndis-acm" sets on the tablet).  If it is not
# found, the script lists the USB network interfaces it sees and stops; then name the interface yourself:
#       sudo bash pc_usbnet.sh up <name>
# It refuses to touch an interface that carries this PC's default route, that is not a USB interface, or that already has an
# IPv4 address of its own (only link-local 169.254.x.x and 192.168.7.1/24 are tolerated).

set -u
PATH=$PATH:/usr/sbin:/sbin:/usr/local/sbin
export PATH

ACTION=${1:-status}
PC_IP=192.168.7.1
PC_ADDR=$PC_IP/24
TAB_IP=192.168.7.2
SUBNET=192.168.7.0/24
TABLE=z380m_usbnet
WANT_ID=0e8d:2008
STATE=${Z380_STATE:-/run/z380m-usbnet.state}
SYSNET=${Z380_SYSNET:-/sys/class/net}
IF=${2:-${IF:-}}

die()  { echo "pc_usbnet: $*" >&2; exit 1; }
say()  { echo "$*"; }
run()  { echo "+ $*"; "$@"; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() { echo "usage: sudo bash $0 status | up [interface] | down      (the optional interface names the tablet's USB network interface)"; echo "$Z380M_CREDIT"; exit 2; }

case "$ACTION" in up|down|status) ;; *) usage ;; esac
[ "$(id -u)" = 0 ] || die "run it with sudo:  sudo bash $0 $ACTION"
have ip || die "'ip' not found (package iproute2)"

# ---------------------------------------------------------------------------------------------------------------------
usb_info() {   # $1 = interface; prints "vid:pid driver" when it is a USB interface, else returns 1
  local d="$SYSNET/$1/device" v p drv
  [ -e "$d" ] || return 1
  v=$(cat "$d/../idVendor" 2>/dev/null) && p=$(cat "$d/../idProduct" 2>/dev/null) || return 1
  drv=$(readlink "$d/driver" 2>/dev/null || true); drv=${drv##*/}
  echo "$v:$p ${drv:-no-driver}"
}

list_usb_ifs() {   # one line per USB-based network interface
  local p n i
  for p in "$SYSNET"/*; do
    n=${p##*/}
    i=$(usb_info "$n") && printf '  %-22s %s\n' "$n" "$i"
  done
}

pick_if() {   # sets IF to the tablet's interface, or stops
  local p n i hits=0 pick='' d other
  if [ -n "$IF" ]; then
    [ -e "$SYSNET/$IF" ] || die "no interface named '$IF' (see:  ip -br link)"
  else
    for p in "$SYSNET"/*; do
      n=${p##*/}
      i=$(usb_info "$n") || continue
      case "$i" in "$WANT_ID "*) hits=$((hits + 1)); pick=$n ;; esac
    done
    if [ "$hits" = 1 ]; then
      IF=$pick
    else
      echo "pc_usbnet: found $hits interface(s) with USB ID $WANT_ID (the tablet in 'rndis-acm' mode)." >&2
      echo "USB network interfaces seen (name, USB ID, driver):" >&2
      list_usb_ifs >&2
      echo "If one of them is the tablet:   sudo bash $0 $ACTION <name>" >&2
      exit 1
    fi
  fi
  # safety: never touch an interface that looks like part of this PC's real network
  for d in $(ip -4 route show default 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "dev") print $(i + 1)}'); do
    [ "$d" != "$IF" ] || die "$IF carries this PC's default route - refusing to touch it"
  done
  other=$(ip -4 -o addr show dev "$IF" 2>/dev/null | awk '{print $4}' | grep -vxF "$PC_ADDR" | grep -v '^169\.254\.')
  [ -z "$other" ] || die "$IF already has the IPv4 address(es) $(echo "$other" | tr '\n' ' ')- it does not look like the tablet's interface; refusing"
  if [ -z "${Z380_ANY_IF:-}" ]; then
    usb_info "$IF" >/dev/null || die "$IF is not a USB network interface - refusing (name the tablet's own interface)"
  fi
}

state_get() { [ -r "$STATE" ] && sed -n "s/^$1=//p" "$STATE" | head -n 1; }
state_put() {   # replace or add one KEY=VALUE line
  local tmp
  tmp=$(mktemp "$STATE.XXXXXX") || return 1
  { [ -r "$STATE" ] && grep -v "^$1=" "$STATE"; echo "$1=$2"; } > "$tmp"
  mv "$tmp" "$STATE"
}

nm_running() { have nmcli && [ "$(nmcli -t -f RUNNING general 2>/dev/null)" = running ]; }

warn_blockers() {
  have nft || return 0
  if nft list ruleset 2>/dev/null | grep -Eq 'hook forward .*policy drop'; then
    say
    say "WARNING: another rule set on this PC (ufw or Docker, probably) drops forwarded packets by default."
    say "         If the tablet can ping $PC_IP but not the internet, report the output of (https://github.com/kaantcp):"
    say "             sudo nft list ruleset | grep -B3 -A12 'hook forward'"
  fi
}

# ---------------------------------------------------------------------------------------------------------------------
do_up() {
  have nft || die "'nft' not found.  On Ubuntu:  sudo apt install nftables   (then run this again)"
  pick_if
  say "tablet interface: $IF   (USB ID / driver: $(usb_info "$IF" 2>/dev/null || echo 'not a USB interface'))"
  if nm_running; then
    if run nmcli device set "$IF" managed no; then state_put NM_UNMANAGED 1; else say "(nmcli could not unmanage $IF - continuing)"; fi
  fi
  run ip link set "$IF" up || die "could not bring $IF up"
  run ip addr replace "$PC_ADDR" dev "$IF" || die "could not set the address on $IF"
  state_put IF "$IF"
  [ -n "$(state_get OLD_FORWARD)" ] || state_put OLD_FORWARD "$(cat /proc/sys/net/ipv4/ip_forward)"
  say "+ echo 1 > /proc/sys/net/ipv4/ip_forward"
  echo 1 > /proc/sys/net/ipv4/ip_forward || die "could not enable forwarding"
  nft delete table ip "$TABLE" 2>/dev/null
  say "+ nft -f -    # table ip $TABLE: masquerade $SUBNET when it leaves through anything but $IF"
  nft -f - <<EOF || die "nft refused the rule set"
table ip $TABLE {
	chain postrouting {
		type nat hook postrouting priority 100; policy accept;
		ip saddr $SUBNET oifname != "$IF" masquerade
	}
}
EOF
  say
  say "PC side is ready:  $IF = $PC_ADDR, NAT for $SUBNET through this PC's other interfaces."
  warn_blockers
  if have ping && ping -c 2 -W 1 "$TAB_IP" >/dev/null 2>&1; then
    say "The tablet answers at $TAB_IP."
  else
    say "The tablet does not answer at $TAB_IP yet - normal until its side is up (after 'z380m-usb rndis-acm' it has $TAB_IP on its USB interface)."
  fi
  cat <<EOT

On the tablet (serial console):
    ip route add default via $PC_IP
    ping -c 3 $PC_IP; ping -c 3 1.1.1.1; ping -c 3 dl-cdn.alpinelinux.org
    apk update
Undo on the PC:   sudo bash $0 down
EOT
}

do_down() {
  local old
  [ -n "$IF" ] || IF=$(state_get IF)
  if have nft && nft delete table ip "$TABLE" 2>/dev/null; then say "removed nftables table $TABLE"; else say "(no nftables table $TABLE)"; fi
  if [ -n "$IF" ] && [ -e "$SYSNET/$IF" ]; then
    run ip addr del "$PC_ADDR" dev "$IF" 2>/dev/null || say "($PC_ADDR was not on $IF)"
  fi
  old=$(state_get OLD_FORWARD)
  if [ -n "$old" ]; then
    echo "$old" > /proc/sys/net/ipv4/ip_forward && say "ip_forward back to $old"
  else
    say "(ip_forward left as it is: nothing saved)"
  fi
  if [ "$(state_get NM_UNMANAGED)" = 1 ] && [ -n "$IF" ] && [ -e "$SYSNET/$IF" ] && nm_running; then
    run nmcli device set "$IF" managed yes || true
  fi
  rm -f "$STATE"
  say "done."
}

do_status() {
  say "ip_forward       : $(cat /proc/sys/net/ipv4/ip_forward)"
  if [ -r "$STATE" ]; then say "saved state      : $(tr '\n' ' ' < "$STATE")"; else say "saved state      : none"; fi
  if have nft && nft list table ip "$TABLE" >/dev/null 2>&1; then nft list table ip "$TABLE"; else say "nftables table  : $TABLE not present"; fi
  say "USB network interfaces (name, USB ID, driver):"
  list_usb_ifs
  [ -z "$IF" ] && IF=$(state_get IF)
  if [ -n "$IF" ] && [ -e "$SYSNET/$IF" ]; then
    say "interface $IF:"; ip -4 -br addr show dev "$IF"
  fi
  if have ping && ping -c 1 -W 1 "$TAB_IP" >/dev/null 2>&1; then say "tablet $TAB_IP  : answers"; else say "tablet $TAB_IP  : no answer"; fi
}

say "$Z380M_CREDIT"
case "$ACTION" in
  up)     do_up ;;
  down)   do_down ;;
  status) do_status ;;
esac
exit 0

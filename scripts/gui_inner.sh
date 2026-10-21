#!/bin/sh
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

# test rig only (inside the x86 Alpine rootfs): plays BusyBox init for the console entry.
# It respawns /etc/z380m/console.sh forever, like "::respawn:/etc/z380m/console.sh" does.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
# the sandbox kernel has virtual terminals; the tablet's may not. Point the VT check at a file that does not exist.
Z380M_TTY_DRIVERS=/tmp/no-such-file
export Z380M_TTY_DRIVERS
mkdir -p /run /var/log /tmp
: > /tmp/stub.log
i=0
while :; do
  i=$((i+1))
  echo "init: respawn #$i of console.sh" >> /tmp/stub.log
  sh /etc/z380m/console.sh
  sleep 0.2
done

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

# test rig only (inside the rootfs): runs the installer with the scenario's settings
. "$1"
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ -n "$TTY0" ] && { touch /dev/tty0; mount --bind /dev/null /dev/tty0; }
Z380M_TTY_DRIVERS=${DRIVERS:-/tmp/drivers-vt}
Z380M_INPUT_DEVICES=${INPUTS:-/tmp/inputs-touch}
export Z380M_TTY_DRIVERS Z380M_INPUT_DEVICES
cd /tmp/zgui
sh ./install.sh $MODE
echo "INSTALLER EXIT STATUS $?"

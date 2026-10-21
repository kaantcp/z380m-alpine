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

# usage: patch_console.sh <console.sh in> <console.sh out> <block A file> <block B file>
# Inserts block A before the line "t0=$(up)" and block B right after the line that logs "z380term exited with status".
# Exit 3 if one of the two anchor lines is not found (then nothing must be installed).
awk -v blka="$3" -v blkb="$4" '
/^t0=\$\(up\)$/ && !a { while ((getline l < blka) > 0) print l; close(blka); a=1 }
{ print }
/^echo "\[\$t1\] z380term exited with status/ && !b { while ((getline l < blkb) > 0) print l; close(blkb); b=1 }
END { if (!a || !b) exit 3 }
' "$1" > "$2"

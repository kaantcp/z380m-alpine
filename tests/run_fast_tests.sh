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

# Run the fast test suites on a COPY of this repository: no x86 rig is needed.
#   sudo sh tests/run_fast_tests.sh <work-dir>
# Needs root, gcc, dash, bash and python3. Some suites install stand-in programs under /etc/z380m, /usr/local and /run of the
# machine they run on and remove them again: use a throw-away VM or container, not your everyday PC.
# The logs are written to <work-dir>/logs. The exit status is 0 only if every check passed.
set -u
REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=${1:?usage: sudo sh tests/run_fast_tests.sh <work-dir>}
[ "$(id -u)" = 0 ] || { echo "run it as root, in a throw-away VM"; exit 2; }
mkdir -p "$WORK" && WORK=$(cd "$WORK" && pwd)
case "$WORK" in "$REPO"|"$REPO"/*) echo "work-dir must be outside the repository"; exit 2 ;; esac
R=$WORK/repo
LOGS=$WORK/logs
rm -rf "$R" "$LOGS" "$WORK/tb" "$WORK/tf" "$WORK/tfi" "$WORK/gpt"
mkdir -p "$R" "$LOGS"
(cd "$REPO" && tar cf - --exclude=.git --exclude=tests/logs .) | (cd "$R" && tar xf -)
echo "$Z380M_CREDIT"
FAILED=0
run() {   # run <log name> <command...>
  name=$1; shift
  echo "== $name"
  "$@" > "$LOGS/$name.txt" 2>&1
  rc=$?
  p=$(grep -c '^PASS' "$LOGS/$name.txt"); f=$(grep -c '^FAIL' "$LOGS/$name.txt")
  echo "   exit $rc, $p PASS, $f FAIL"
  if [ "$rc" != 0 ] || [ "$f" != 0 ] || [ "$p" = 0 ]; then FAILED=1; fi
}
gcc -O1 -DTESTBUILD -o "$WORK/tb" "$R/src/touchbridge/z380m-touchbridge.c" || exit 2
run touchbridge       python3 -I "$R/src/touchbridge/test_touchbridge.py" "$WORK/tb"
run gui_v2            bash "$R/scripts/test_gui_v2.sh" "$R"
run touchfix          bash "$R/scripts/test_touchfix.sh" "$R" "$WORK/tf"
run touchfix_int      bash "$R/scripts/test_touchfix_int.sh" "$R" "$WORK/tfi"
run check_gpt         python3 -I "$R/tests/test_check_gpt.py" "$R" "$WORK/gpt"
run verify_dist       python3 -I "$R/tests/verify_dist.py" "$R"
echo "logs: $LOGS"
[ "$FAILED" = 0 ] && echo "ALL FAST SUITES PASSED" || echo "SOME SUITE FAILED"
exit $FAILED

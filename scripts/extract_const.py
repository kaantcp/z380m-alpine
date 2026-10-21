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

"""Read a string constant (e.g. CONSOLE_SH) out of a Python source file WITHOUT running it.

usage: extract_const.py <source.py> <NAME> <out-file>
"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import ast
import sys

src, name, out = sys.argv[1:4]
with open(src, "r", encoding="utf-8") as f:
    tree = ast.parse(f.read(), filename=src)
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
        value = ast.literal_eval(node.value)
        with open(out, "w", encoding="utf-8", newline="\n") as o:
            o.write(value)
        print("wrote %s (%d bytes) from %s" % (out, len(value.encode("utf-8")), name))
        break
else:
    sys.exit("constant %s not found in %s" % (name, src))

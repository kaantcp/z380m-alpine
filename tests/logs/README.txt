Copyright (C) 2026 kaantcp (https://github.com/kaantcp) - GPL-3.0-only (see ../../LICENSE) - part of z380m-alpine

Results of the last full test run, 20 Oct 2026, on the files of this repository.
What the tests prove and what they do not: docs/TESTING.md. Read that first.

Environment: Ubuntu 24.04.5 LTS (Linux 6.18.44), Python 3.13.16, gcc 13.3.0, Ubuntu clang 18.1.3, bash 5.2.21,
dash 0.5.12, util-linux 2.39.3. The rig suites ran in chroots of the Alpine 3.24.2 x86_64 mini root filesystem
(sha256 c5ca053cfe1d85c5b96dff8b9bc57045f7f184a30ffb6b65776409ca90388677).

fast_*.txt     one log per fast suite, written by tests/run_fast_tests.sh (all six together took 111 s)
  fast_touchbridge.txt    21 checks
  fast_gui_v2.txt         31 checks
  fast_touchfix.txt       55 checks
  fast_touchfix_int.txt   16 checks
  fast_check_gpt.txt      16 checks
  fast_verify_dist.txt    26 checks
rig_*.txt      the rig suites (x86 Alpine chroots; installer/rig/README.txt)
  rig_test_gui.txt        99 checks (scripts/test_gui.py, about 4 minutes)
  rig_test_install.txt    48 checks (installer/test_install.py, a few seconds)
  rig_test_paste.txt      25 checks (installer/test_paste.py, about half a minute together with building the paste file)
  rig_fbfix.txt           the colour-shim host test (installer/shim/test_fbfix.c)

Notes
 - In fast_touchfix.txt the name of the work folder was replaced by <work>. Nothing else in the logs was changed.
 - Each log carries its own result (a count line, or "all checks passed" for the colour-shim test). The rig logs
   end with exit=N, the exit status of the test program, written by the command that ran it. The counts above were
   taken from the logs by counting their PASS lines.

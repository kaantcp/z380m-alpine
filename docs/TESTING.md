# Testing: what the tests check, and what they do not prove

Copyright (C) 2026 [kaantcp](https://github.com/kaantcp) · GPL-3.0-only · part of [z380m-alpine](../README.md)

Labels as elsewhere: **V** = verified on the tablet, **A** = assumed, **A(rig)** = passes in the x86 test rig, never seen on the tablet.

## The short version

The tests run the project's own scripts, and the logic of the touch bridge, on an ordinary x86 Linux machine against **stand-ins** for the tablet: fake `/proc` and `/sys` files, a fake `Xorg`, `jwm` and `z380term`, a fake package repository, a pseudo-terminal in place of the USB serial line. They find script bugs before anyone has to find them on the tablet.

They prove **script logic only**. They say nothing about Xorg and its drivers, the touch panel, the display driver, the 3.18 kernel or timing on the real tablet. Whenever this repository says **A(rig)**, it means exactly this: the logic passes here, and nobody has seen it on the tablet.

There are two groups:

| Group | Needs | Where to start |
|---|---|---|
| **Fast suites** (6) | root, gcc, dash, bash, python3. No rig. | `tests/run_fast_tests.sh` |
| **Rig suites** (4) | the same, plus the x86 rig (an Alpine x86_64 mini root filesystem, unpacked and prepared by `installer/rig/make_rig.sh`) | `installer/rig/README.txt` |

## 1. Fast suites

```
P:  sudo sh tests/run_fast_tests.sh ~/z380m-tests
```

The folder you name must be **outside** the repository. The runner works on a copy of the repository, writes one log per suite to `<folder>/logs`, prints one line per suite and ends with `ALL FAST SUITES PASSED` (exit status 0) or `SOME SUITE FAILED`. A suite counts as failed if it exits non-zero, prints any `FAIL` line, or prints no `PASS` line at all.

**Use a throw-away VM or container, not your everyday PC.** Some suites install stand-in programs under `/etc/z380m`, `/usr/local`, `/run`, `/var/log` and `/tmp` of the machine they run on, start and stop processes named `Xorg`, `jwm` and `z380m-touchbridge`, and remove everything again when they finish.

| Suite | Checks | What it does |
|---|---|---|
| `touchbridge` (`src/touchbridge/test_touchbridge.py`) | 21 | Builds the bridge's C source for x86_64 with `-DTESTBUILD` and feeds it made-up panel event streams: both multitouch protocol types, a drag, two fingers, the mirror options, coordinate clamping, a `SYN_DROPPED` event, the `probe` command. It checks the events the bridge writes to its virtual single-touch device. |
| `gui_v2` (`scripts/test_gui_v2.sh`) | 31 | Runs desktop starter version 2 with stand-ins for Xorg, jwm and the bridge, in eight groups: a kernel without virtual terminals (the `tty1` stand-in, `-sharevts`), the bridge started with the `touch.flags` options and stopped with X, the display-format flag; a bridge that exits at once or never shows its virtual device (the starter falls back to the panel and leaves no bridge running); the `no-bridge` file and a missing bridge program; `restart-x` and `keep`; a kernel with virtual terminals; an old `xorg.flags` that already has `-sharevts` (not doubled); `touchtest`, `report` and the usage message. |
| `touchfix` (`scripts/test_touchfix.sh`) | 55 | Builds test copies of the touch-fix installer (from `installer/touchfix/touchfix_template.sh` and stand-in programs) and runs them against a fake root folder in 19 scenarios: a normal install; both axes mirrored; only one axis; corner taps too close together; a second run changes nothing; a damaged file (nothing installed); the desktop running (refused); a stale pid file; a failing `uinput` check; a program that does not run at all; a panel that sends nothing; an unknown line in `console.sh`; `undo`; not the tablet (nothing done); the preconditions; starter already version 2; `console.sh` missing; the length of the output; and the same scenario under `bash --posix`. |
| `touchfix_int` (`scripts/test_touchfix_int.sh`) | 16 | The touch-fix installer against the **real** starter version 2 and the real console script, with stand-ins for Xorg, jwm and the bridge, in three steps: the install (the probe runs on the panel node, the flags are measured from the two corner taps, version 1 is kept, the supervisor starts the desktop, the bridge gets the saved flags, `z380m-touch` points at the virtual device); the return to the text console, where `z380term` gets `-n` only while the flag file exists; and `undo` through the real files. |
| `check_gpt` (`tests/test_check_gpt.py`) | 16 | Tests `src/check_gpt.py` (the partition-table gate of the guide) against the logged `printgpt` output of the tested tablet and against deliberately damaged copies: a moved offset, a changed total, a missing or extra partition, two partitions swapped, an empty file, a file with no table (accepted: Windows line ends and colour codes). Then backup folders: complete (with and without the preloader file), a truncated file, a missing file, a preloader file of the wrong size, not a folder. |
| `verify_dist` (`tests/verify_dist.py`) | 26 | Provenance check: every file inside `dist/z380m_gui_paste.txt` and `dist/z380m_touchfix.sh` equals the file of the same name in this repository byte for byte (the paste's starter is `scripts/obsolete/z380m-gui.v1`); the checksums in `dist/SHA256SUMS`; the two files are plain ASCII with no TAB and no CR; the credit line is in them. Reads files only. |

You can run any single suite by hand; the commands are in `tests/run_fast_tests.sh`.

## 2. Rig suites

The rig is a throw-away x86_64 Alpine 3.24.2 userland that runs in chroots inside `unshare` namespaces. It uses Alpine's own BusyBox and apk-tools, so the shell scripts meet the x86_64 build of the BusyBox `ash` that the tablet runs as an aarch64 build of the same Alpine release (**A** that the behaviour is identical on both CPUs). The setup is described in `installer/rig/README.txt`: it needs the official mini root filesystem tarball and takes about 180 MB.

```
P:  cd <copy of the repository>
P:  sudo python3 -I scripts/test_gui.py .
P:  sudo python3 -I installer/test_install.py .
P:  sudo python3 -I installer/mkpaste.py . ./out && sudo python3 -I installer/test_paste.py .
P:  gcc -O1 -o out/t_fbfix installer/shim/test_fbfix.c installer/shim/fbfix.c && out/t_fbfix
```

(Run these in a **copy** of the repository, after `make_rig.sh` has built the rig folders there. `test_gui.py` takes about 4 minutes, `test_install.py` a few seconds and `test_paste.py` about half a minute.)

| Suite | Checks | What it does |
|---|---|---|
| `test_gui.py` | 99 | Runs the **real** `z380m-gui`, `console.sh`, `session.sh` and Alpine's BusyBox in the chroot, with static stand-ins for `z380term` and `Xorg`, stub programs for `jwm`, `xterm`, `xset` and so on, and a pseudo-terminal as the serial line. It plays the user at the serial window. It copies the current sources into the rig at the start of every run, so it cannot test a stale copy. Sections: text console up; test run and watchdog; `keep` and `stop`; Xorg that cannot start; supervisor killed with `-9` (the console must be taken back); boot mode and the boot guard; a guard left behind; `boot-enable` and `boot-disable`; `/dev/tty0` present; `restart-x`; the colour-fix preload; virtual-terminal nodes; colour swap toggle; the first-run window. |
| `test_install.py` | 48 | Runs the **real** `install.sh` against a fake tablet (fake `/proc` files, a mock `fbset`, a fake package repository built with the real apk-tools, a fake `tcc`): `check` mode installs nothing; a full install; a repeat run; uninstall; every gate (no network, no space, no virtual terminals, no touch screen, wrong machine); `console.sh` without the expected anchors (exit 5); `apk add` failing (exit 2); the compiler failing; no `svkbd` (falls back to `matchbox-keyboard`). |
| `test_paste.py` | 25 | The paste path: a real interactive BusyBox `ash` on a pseudo-terminal receives the paste file the way the serial window sends it (every line end as a carriage return). Normal paste; blank lines and trailing spaces; one damaged character (refused, nothing unpacked); wrong window (nothing done); a truncated paste; the HTTP route; terminal size replies injected into the middle of the paste; the whole flow paste, check, install, status, uninstall. |
| `test_fbfix.c` | 1 program | A host test of the colour shim (`installer/shim/fbfix.c`) with a fake kernel behind it; prints `fbfix host test: all checks passed`. |

## 3. What a pass does not mean

- **Xorg, JWM, svkbd and the drivers are never run.** The stand-ins only record that they were started with the expected arguments. That the desktop looks right and that Xorg's fbdev and evdev drivers accept the configuration is known from my own check on the tablet (**V**, no log), not from any test.
- **No aarch64 program is executed by any test.** `z380term` and the touch bridge binary are built for the tablet's CPU. The bridge's *logic* is tested through an x86 build of the same C source (`-DTESTBUILD`); the binary in the touch fix is the aarch64 build of that source. That the binary runs and that touch works on the tablet is **V** by my own check only, and only for the first build (18 Oct); the binary in `dist/` was rebuilt on 20 Oct 2026 with the credit line and has not been run on the tablet (**A(rig)**).
- **Timing is not tested on the tablet.** The watchdog (240 s by default) and the boot guard are exercised in the rig with shortened times (for example `z380m-gui start 20`); the real values are **A(rig)**.
- **The kernel is not tested.** `uinput`, `mtkfb`, the input layer and virtual terminals of the 3.18.35 kernel are replaced by fake files and folders. Whether this kernel has virtual terminals is open (see [HARDWARE.md](HARDWARE.md)); the scripts handle both cases and both are tested in the rig.
- **`boot-enable` and a reboot with the desktop installed were never tried on the tablet** (**A(rig)**).
- **The `df` the installer sees in the rig is a mock, not the tablet's BusyBox `df`.** The installer's free-space check prints a clear message when it cannot read `df -k /`, but how it behaves with the tablet's real `df` output was only seen in my own runs (**A**: no log of that step is in this repository).
- **The two image builders were not run end to end after the credit lines were added** (20 Oct 2026): the sandbox has neither the stock kernel nor an aarch64 cross compiler. Their edited parts were checked separately (see [CHANGELOG.md](CHANGELOG.md), item 2).
- **A test run is not a safety proof.** Nothing here tests flashing. The flashing steps rely on the checks in the guide (partition table gate, backup size check, read-back and `cmp`), which you run yourself on your own tablet.

## 4. Results of the last full run (20 Oct 2026)

All suites were run on the final files of this repository, in a Linux sandbox (Ubuntu 24.04.5, Python 3.13.16, gcc 13.3.0, clang 18.1.3; Alpine 3.24.2 x86_64 rig, built from the official mini root filesystem, sha256 `c5ca053cfe1d85c5b96dff8b9bc57045f7f184a30ffb6b65776409ca90388677`). The logs are in [tests/logs/](../tests/logs); `tests/logs/README.txt` says which log belongs to which suite.

| Suite | Result |
|---|---|
| touchbridge | 21 of 21 pass |
| gui_v2 | 31 of 31 pass |
| touchfix | 55 of 55 pass |
| touchfix_int | 16 of 16 pass |
| check_gpt | 16 of 16 pass |
| verify_dist | 26 of 26 pass |
| test_gui.py | 99 of 99 pass (see the note below) |
| test_install.py | 48 of 48 pass |
| test_paste.py | 25 of 25 pass |
| test_fbfix | all checks passed |

**A note on `test_gui.py`.** It was written for desktop starter version 1 and was not run against version 2 until 19 Oct. Its first run against version 2 had 98 of 99 checks passing. The single failure was an out-of-date expectation: the check looked for the log line `touch screen: /dev/input/event7`, and version 2 words that line `touch panel: /dev/input/event7` (the check also tests that the symlink `z380m-touch` points at `event7`, which it did). The word in the test was changed and the whole suite was run again: 99 of 99. The program being tested was not changed. The run in the table above (20 Oct 2026) passed 99 of 99 on the final files.

## 5. What the tests found

- **A real bug in the installer, found by the rig before it reached the tablet:** the awk that looks for the touch screen in `/proc/bus/input/devices` matched the bare word `event11`, but the file prints `Handlers=event11`; on the real tablet the installer would have stopped at its touch-screen gate. Fixed.
- **A stale rig:** the desktop rig once kept an older copy of the scripts than the ones being shipped, so the colour-fix menu, the preload clean-up and the first-run window were not covered. `test_gui.py` now copies the current sources into the rig at the start of every run.
- **An out-of-date test expectation** (section 4): found by running the desktop rig against starter version 2 for the first time.
- **What the tests did not find:** the touch problem of 18 Oct. Xorg's evdev driver ignoring a panel that only speaks the multitouch protocol (**A**, the Xorg log was never received) is invisible to a rig with a fake Xorg. It showed up on the tablet, and the touch bridge was written in response.

## 6. If you change something

1. Run the fast suites. They are quick and need no rig.
2. If you change a file that is packed into `dist/` or listed in `installer/payload.list`, rebuild the files in `dist/` (`installer/mkpaste.py`, `installer/touchfix/build_touchfix.py`, and `src/touchbridge/build.sh` if the bridge source changed), write `dist/SHA256SUMS` again, run the rig suites, and `tests/verify_dist.py` must pass again.
3. A passing test does not change an **A(rig)** into a **V**. Only a log from the tablet does.

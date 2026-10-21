# History and provenance

Copyright (C) 2026 [kaantcp](https://github.com/kaantcp) · GPL-3.0-only · part of [z380m-alpine](../README.md)

This page answers two questions: **what happened when**, and **how do the files in this repository relate to the files that actually ran on the tablet**. Labels as elsewhere: **V** = verified (a log in [evidence/](../evidence) or my own check on the tablet), **A** = assumed, **A(rig)** = passes in the x86 test rig only. Dates are 2026; times are my local time (Eastern) unless marked UTC. `evidence/01` to `evidence/05` are the files in [evidence/](../evidence) by their number.

## Timeline

| Date | What happened | Where to look |
|---|---|---|
| 4 Oct | I read a backup of the tablet with mtkclient: the 23 partitions `proinfo` to `APD`, the partition table (`gpt.bin`, `gpt_backup.bin`) and the 4 MiB `boot1` area that holds the preloader (file dates 16:50 to 17:00 for most of it). Later that day a **console-only** boot image ("v2": the stock kernel plus a ramdisk with a text console on the screen and on USB serial, no Alpine) was built at 21:08. A file `boot_after.bin` dated 21:12 compares identical to it: the console-only image had been read back identical (first lines of evidence/01). **V** | evidence/05 (listing), evidence/01 (the `cmp` line), [reference/build_console_boot_v2.py](../reference/build_console_boot_v2.py) |
| 10 Oct | The Alpine images were built at 18:48 (22:48 UTC): `boot_alpine_full.bin` (sha256 `fbf826f8af73055953048788c18f9ed174abd0030590cfcaf84ebe5219ca2d16`) and `system_alpine.ext4` (sha256 `77613db5c283e655f45611e3834ecd96a733d35f94e2d1483cde047c993d9a46`). **Stage A:** `boot` written and read back identical. **Stage B:** the first 512 MiB of `system` written and read back identical. First boot: the ramdisk found `system` at 7.44 s, OpenRC finished at 19.9 s, the text console and the USB serial shell came up. **V** | evidence/01, 02, 03, 05 |
| after 10 Oct | USB network (RNDIS) through the PC with NAT; `apk update` against the real Alpine mirrors worked (28,554 packages). The log has no timestamps. **V** | evidence/04 |
| 18 Oct | **Desktop.** `z380m_gui_paste.txt` (desktop starter version 1) was pasted into the tablet's shell and installed. The desktop came up with the right colours, but **touch did nothing**. I also noticed that the text console's red/blue colour fix looked broken while the desktop's colours were fine. Then the **touch fix** was written (a small touch bridge program plus desktop starter version 2 plus a console change) and `z380m_touchfix.sh` was run. Touch worked (my own check; no log in this repository). **V** (my own check) | [dist/](../dist), [GUIDE.md](GUIDE.md) sections 9 and 10 |
| 18 to 20 Oct | This repository was prepared for publication: license notices, a credit line in the code, documentation, tests, and the rebuilt files in `dist/` (see below). | |

Nothing else was flashed after 10 Oct: only `boot` and the first 512 MiB of `system` were ever written with the Alpine images.

## The two files in `dist/`

Both files are generated from the sources in this repository. [tests/verify_dist.py](../tests/verify_dist.py) checks by script (26 checks) that everything inside them equals the repository files byte for byte.

**Two generations.** The *first generation* of both files ran on the tablet on 18 Oct (**V**, my own check). Those files are not in this repository; their checksums are in the table below. The files in `dist/` now are the *second generation*, rebuilt on 20 Oct 2026. The logic is the same. What changed: the wording of the messages that ask for a report (they name the project page), the license notices, the credit line that the scripts and programs print and carry, and the touch bridge program, which was rebuilt from its source with the credit line in it. The second generation passes all rig tests (**A(rig)**); it has **not** been run on the tablet yet.

### `dist/z380m_gui_paste.txt` (20,909 bytes)

- It carries 13 files (listed in [installer/payload.list](../installer/payload.list)) as a base64 tar.gz, with a checksum guard and a wrong-window guard. One of them is **desktop starter version 1**, [scripts/obsolete/z380m-gui.v1](../scripts/obsolete/z380m-gui.v1), the starter that the paste installs. The current [scripts/gui/z380m-gui](../scripts/gui/z380m-gui) is **version 2**; the touch fix installs it.
- `python3 -I installer/mkpaste.py . <output folder>` rebuilds the file; on 20 Oct 2026 (Python 3.13.16) the result was byte for byte the file in `dist/`. The compressed bytes may depend on the zlib version, so another machine can give a different checksum for the same content; the guard inside the paste file checks the content before it unpacks anything.

### `dist/z380m_touchfix.sh` (28,733 bytes)

- Its shell code equals [installer/touchfix/touchfix_template.sh](../installer/touchfix/touchfix_template.sh) with the version placeholder set to 1 and the two checksums filled in.
- It embeds the touch bridge program: an aarch64 binary of 9,248 bytes, which is [installer/touchfix/z380m-touchbridge.arm64](../installer/touchfix/z380m-touchbridge.arm64). The source is [src/touchbridge/z380m-touchbridge.c](../src/touchbridge/z380m-touchbridge.c) and [src/touchbridge/build.sh](../src/touchbridge/build.sh) rebuilds the binary byte for byte (checked twice with Ubuntu clang 18.1.3 on 20 Oct 2026). The first-generation program was 9,200 bytes; the source differs from it only by the credit line, which the `version` and usage output print. The program was not run on the tablet after that change (**A(rig)**: its logic is tested through the x86 build of the same source).
- It embeds **desktop starter version 2**, which equals [scripts/gui/z380m-gui](../scripts/gui/z380m-gui).
- It also changes the text console script: `z380term -n` (no red/blue swap) is used while `/run/z380m-fb-panned` exists, i.e. after the desktop's first screen update. **A** for the reason (the display's pixel format changes when X first updates the screen); the effect (right colours on the console after the desktop) is **V** by my own check, with the first generation.

### Checksums (sha256)

| File | sha256 |
|---|---|
| `dist/z380m_gui_paste.txt` | `174fb06c773f660cc1808130987e8e5c87f1d21f37ddfdf3f28aca6c1a5d7f5d` |
| `dist/z380m_touchfix.sh` | `c6c1436614609e2fa41d3300e9eb691ed60894a260231554739895d079ef35a6` |
| touch bridge program (`installer/touchfix/z380m-touchbridge.arm64`, 9,248 bytes) | `936d15cab2b5383de849113c193df03f9f797ab1015644aa5ef36c3a1f252028` |
| desktop starter version 2 (`scripts/gui/z380m-gui`) | `fd7caa39c6bae863a60e9c5ff3dbb2d5dd78540860fab23ef5b317ebdbba65f9` |
| first generation of the paste file (ran on the tablet; not in this repository) | `39e017434e90a00c09bc08ef039135c0366bcd208b12fd7c319f750e93259048` |
| first generation of the touch fix (ran on the tablet; not in this repository) | `9063d14339ff3e9d2205781e6728e88d63666b6506c6e9bc93aa8d97b7eb3d6b` |
| first generation of the touch bridge program (9,200 bytes) | `03ce0d4429d976805c13dbc1fd7ca395393a25e5b78ed9da41c311faf4047fc5` |

### Starter version 1 to version 2: what changed

Version 2 adds, to version 1: the touch bridge handling (`real_touch`, `make_input_node`, `find_touch`, `stop_bridge`, the options file `touch.flags`, the switch file `no-bridge`, and the `touchtest` command); the stand-in for kernels without virtual terminals (`-sharevts`, `/dev/tty1` linked to `/dev/null`); the flag file `/run/z380m-fb-panned`; the test hooks `TTYDIR`, `DEVIN`, `SYSIN` and `UINPUT`, which let the tests point the script at fake device folders; and more lines in `status` and `report`. Version 1 is kept because the paste file installs it, and the touch fix backs it up on the tablet (as `z380m-gui.v1`) and `undo` puts it back. See [scripts/obsolete/README.txt](../scripts/obsolete/README.txt).

## Changes made for publication (18 to 20 Oct)

1. **License notices.** Every source file written for the project got the same 15-line comment block at the top (after the `#!` line where there is one): the SPDX line `GPL-3.0-only`, "Copyright (C) 2026 kaantcp (https://github.com/kaantcp)" and the standard GPL warranty text. The notices are comments only. Files that cannot carry a notice without changing them are listed in [NOTICE](../NOTICE).
2. **Credit line.** On 20 Oct 2026 the line `z380m-alpine by kaantcp - https://github.com/kaantcp` was added to the code itself, not only to comments: every script and program carries it as data and the programs print it; the Python files define `__author__`, `__url__` and `CREDIT`; the builders write it into the images. What was run afterwards: all test suites (see [TESTING.md](TESTING.md)); a syntax check of every script, Python file and C file; a host compile of the C programs. What was **not** run: the two image builders end to end (the sandbox has neither the stock kernel nor an aarch64 cross compiler, **A**). For `build_boot_v3.py` the ramdisk scripts were written with `--dump-scripts` and checked with `sh -n`; for `build_alpine_rootfs.py` the message of the day and the marker file text were formatted in a Python session. The aarch64 build of `src/z380term_rbswap.c` (one added line in its banner) has not been made here.
3. **Messages.** Lines that asked the reader to send the output to someone now read "Report this output (https://github.com/kaantcp)". The heading of the touch fix's diagnostics now reads "Details for a bug report".
4. **Two one-line edits to test files:**
   - `installer/test_install.py`: the host name that one scenario uses as its "wrong machine" value was the name of my PC; it is now `some-other-pc`. The scenario behaves the same.
   - `scripts/test_gui.py`: one expected log text was updated from `touch screen:` to `touch panel:`, because starter version 2 words that line differently. The first run of the desktop rig against version 2 had 98 of 99 checks passing; the one failure was exactly this out-of-date expectation (the symlink the check also looks at was made correctly).
5. **Evidence logs** (`evidence/01` to `05`) are my terminal output with personal identifiers replaced: the tablet's serial numbers, the MediaTek ME_ID, the eMMC CID, the PC's user and host name, MAC addresses and the partition GUIDs. Nothing else was changed in them.
6. **New files, not part of what ran on the tablet:** [LICENSE](../LICENSE), [NOTICE](../NOTICE), [README.md](../README.md), `docs/` (this folder), [src/check_gpt.py](../src/check_gpt.py) (compares a live `printgpt` with the tested tablet's table and checks the size of backup files), [src/touchbridge/build.sh](../src/touchbridge/build.sh), `tests/`, `dist/SHA256SUMS`, `dist/README.txt`, `scripts/obsolete/README.txt`, and a rewritten `installer/rig/README.txt`.
7. **Not included on purpose:** every dump, backup and image of a tablet, ASUS files, and the built `boot_alpine_full.bin` and `system_alpine.ext4` (see [NOTICE](../NOTICE)).

## Texts that are out of date and were left alone

These strings are inside `src/build_alpine_rootfs.py`, and the image that was flashed on 10 Oct has them too:

- the `z380m-usb` help text calls `rndis-acm` "never tried" (it works, evidence/04);
- the message of the day says "Network: none yet";
- `/etc/network/interfaces` has a `usb0` stanza although the interface is `rndis0`.

The full list of known leftovers is in [HARDWARE.md](HARDWARE.md#known-leftovers-v-unless-marked).

## Versions at a glance

| Piece | Version |
|---|---|
| Alpine Linux | 3.24.2, aarch64 (apk-tools 3.0.8) |
| Kernel | 3.18.35, ASUS stock, unchanged |
| BusyBox in the ramdisk | 1.36.1, static aarch64, supplied by the builder's user |
| Boot image builder / ramdisk `/init` | `build_boot_v3.py` / v3 |
| Root filesystem builder | `build_alpine_rootfs.py` 1.0 |
| Desktop starter | version 1 (in `dist/z380m_gui_paste.txt`), version 2 (in `dist/z380m_touchfix.sh` and `scripts/gui/`) |
| Touch bridge | `z380m-touchbridge 1` |
| mtkclient (my run) | 2.1.3 with a local patch of `dalegacy_lib.py` (the need for it is unknown, **A**) |

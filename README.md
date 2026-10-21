# z380m-alpine

**Alpine Linux with a touch-screen desktop on the ASUS ZenPad 8.0 (Z380M, model P00A, MediaTek MT8163)** - installed on the tablet's own storage and running on the tablet's stock Android kernel.

Created by [kaantcp](https://github.com/kaantcp) · License: [GPL-3.0-only](LICENSE) · Copyright (C) 2026 kaantcp

> **Warning.** Following this project overwrites two partitions of the tablet's flash storage (`boot` and the first 512 MiB of `system`) and Android will no longer start. I did this on one tablet (mine) and it worked there. It is specific to this model: do not use it on any other device. Nothing here comes with a warranty. Read [docs/GUIDE.md](docs/GUIDE.md), section 0, before you touch anything, and make a backup first.

## What this is

The ZenPad 8.0 Z380M ships with an old Android kernel (Linux 3.18.35). I built this to run a real **Alpine Linux 3.24.2 (aarch64)** userland on the tablet, booted through a small custom `boot` image, with a working **touch desktop** (Xorg + JWM + an on-screen keyboard) on the tablet's screen.

It does **not** replace the kernel. The Linux kernel in the boot image is ASUS's own, copied byte for byte from the stock boot image that you supply (the builder checks this). Everything else (the boot ramdisk, the root filesystem builder, the text console, the touch bridge, the desktop scripts, the installers) was made for this project and is in this repository.

## What works, and what is verified

Labels: **V** = verified on the tablet (a log in [evidence/](evidence) or my own check on the tablet). **A** = assumed, not verified. **A(rig)** = passes only in the x86 test rig, never seen on the tablet.

| Feature | State |
|---|---|
| Flash a custom `boot` image and the first 512 MiB of `system` with mtkclient, read back and compare | **V** ([evidence/01](evidence/01_stageA_printgpt_and_boot_write.txt), [02](evidence/02_stageB_system_write_and_readback.txt)) |
| Boot: ramdisk finds `system`, mounts ext4, `switch_root`, Alpine OpenRC finishes in about 20 s | **V** ([evidence/03](evidence/03_tablet_first_boot_report.txt)) |
| Text console on the tablet screen with the right colours, mirrored to a USB serial port | **V** (evidence/03 and my own check) |
| USB network (RNDIS) through a PC with NAT, `apk update` against the real Alpine mirrors | **V** ([evidence/04](evidence/04_usbnet_nat_apk_update.txt)) |
| Desktop (Xorg fbdev + JWM) on the screen with correct colours | **V** (my own check; no log in this repo) |
| Touch input in the desktop, through the touch bridge | **V** (my own check; no log in this repo) |
| Start the desktop automatically at power-on (`z380m-gui boot-enable`) | **A(rig)** - implemented and tested in the rig; I have not tested a reboot on the tablet |
| On-screen keyboard (svkbd) | **A(rig)** |
| Wi-Fi | **Does not work.** The kernel shows no `wlan0` ([evidence/03](evidence/03_tablet_first_boot_report.txt)); the chip is not identified and would need vendor firmware and drivers that this project does not have (**A**) |
| Bluetooth, sound, camera, sensors, GPU acceleration, suspend, battery gauge | Not attempted |

The installers in `dist/` were rebuilt on 20 Oct 2026 and passed the rig tests (**A(rig)**) but have not been run on the tablet since; the **V** entries for the desktop and for touch refer to their first versions (see [docs/CHANGELOG.md](docs/CHANGELOG.md)).

The full list of known facts about the hardware is in [docs/HARDWARE.md](docs/HARDWARE.md).

## How it boots

```
BROM -> preloader -> LK -> boot partition
                             |- ASUS kernel 3.18.35 (unchanged)
                             '- my ramdisk: static BusyBox + z380term + /init
                                  |- USB serial gadget, 5 s rescue window
                                  |- finds `system` (mmcblk0p25), mounts it (ext4), checks the marker file
                                  '- mount --move + switch_root
                                       -> Alpine: BusyBox init + OpenRC
                                       -> z380term (text console on /dev/fb0 + USB serial)
                                       -> z380m-gui: Xorg (fbdev) + JWM + z380m-touchbridge (touch)
```

## Repository layout

| Path | What is in it |
|---|---|
| [docs/GUIDE.md](docs/GUIDE.md) | **Step-by-step guide to reproduce everything** |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Facts about the tablet (partition table, display, input, USB), verified or assumed |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Symptoms, checks and fixes |
| [docs/TESTING.md](docs/TESTING.md) | The test suites and what they prove |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | History, and how the published files relate to the ones that ran on the tablet |
| `src/` | PC-side builders and helpers: `build_boot_v3.py` (boot image), `build_alpine_rootfs.py` (root filesystem), `check_gpt.py` (partition-table gate and backup size check), `pc_usbnet.sh` (USB network helper), `z380term_rbswap.c` (screen terminal), `touchbridge/` (touch bridge source and build script) |
| `scripts/gui/` | The desktop: `z380m-gui` (start/stop/keep/boot), Xorg and JWM configuration, session script, keyboard and brightness helpers |
| `scripts/` | The test suites for the desktop and the touch fix, their stand-in programs (`stubs/`), and `obsolete/z380m-gui.v1`, the first desktop starter (see its README) |
| `installer/` | The desktop installer (`install.sh`, `mkpaste.py`), the touch-fix builder (`touchfix/`), the colour shim (`shim/`), and the test rigs (`rig/`) |
| `dist/` | The two installer files (generated from the sources), with checksums and a README |
| `tests/` | `run_fast_tests.sh` (all fast suites in one go), the tests for `check_gpt.py` and for `dist/`, and `logs/` with the results of the last run |
| `evidence/` | Terminal logs from the real tablet and PC (personal identifiers removed) |
| `reference/` | The earlier console-only boot builder this one grew from |

## Quick start

The guide has every command, the safety checks and the undo steps. In short:

1. Put the tablet in BROM mode, dump its partition table with `mtkclient printgpt`, and compare it with [Appendix A of the guide](docs/GUIDE.md#appendix-a-the-partition-table-of-the-tested-tablet). **Stop if it differs.**
2. Back up the tablet: the 23 partitions before `cache`, the partition table and the preloader, then check the file sizes with `src/check_gpt.py --sizes` (guide, section 3).
3. Build the two images on a PC (`src/build_alpine_rootfs.py`, `src/build_boot_v3.py`).
4. Flash with mtkclient: `w boot ...` then `w system ...`, and verify each with `ro` + `cmp`.
5. Boot, open the USB serial console, bring up the USB network, install the desktop (`dist/z380m_gui_paste.txt`), then the touch fix (`dist/z380m_touchfix.sh`).

## What is not in this repository

Device backups, ASUS firmware, the stock boot image, the preloader and `lk`, and the built images are **not** included and should never be added: they belong to other people (ASUS, MediaTek) or hold data unique to one device. You build the images yourself from your own tablet's files. See [NOTICE](NOTICE).

## Tests

Six fast suites (touch bridge, desktop starter, touch-fix installer, the touch-fix installer against the real starter, the partition-table checker, and the check that `dist/` is made of the sources in this repository: 165 checks) and four rig suites (desktop, installer, paste, colour shim: 99 + 48 + 25 checks and one host test) check the scripts' logic against stand-ins. All of them passed on 20 Oct 2026; the logs are in [tests/logs](tests/logs). They prove script logic only; they say nothing about Xorg, the touch driver, the display driver or timing on the real tablet. Details and how to run them: [docs/TESTING.md](docs/TESTING.md).

## Credits

- Project, hardware, flashing and testing on the tablet: [kaantcp](https://github.com/kaantcp).
- [mtkclient](https://github.com/bkerler/mtkclient) by Bjoern Kerler and contributors (GPL-3.0) is the flashing tool used. It is not included.
- [Alpine Linux](https://alpinelinux.org/), [BusyBox](https://busybox.net/), the Linux kernel, [X.Org](https://www.x.org/), [JWM](https://joewing.net/projects/jwm/) and [svkbd](https://tools.suckless.org/x/svkbd/) are used but not included; each has its own license.
- Prior art: a search in October 2026 found no other public Alpine Linux port for the Z380M. That describes the search, not a claim of priority. If you know of earlier work, please open an issue so it can be credited.

ASUS, ZenPad, MediaTek, Android and Alpine Linux are trademarks of their owners. This project is not affiliated with or endorsed by any of them.

## License

Copyright (C) 2026 kaantcp (<https://github.com/kaantcp>). Licensed under the **GNU General Public License, version 3 only** (`GPL-3.0-only`). See [LICENSE](LICENSE) and [NOTICE](NOTICE).

You may use, study, change and share this work. If you share it, in original or changed form, you must keep the copyright and license notices, state what you changed, and release your version under the same license with its source code. The software comes without any warranty.

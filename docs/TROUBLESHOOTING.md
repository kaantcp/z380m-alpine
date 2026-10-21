# Troubleshooting

Copyright (C) 2026 [kaantcp](https://github.com/kaantcp) · GPL-3.0-only · part of [z380m-alpine](../README.md)

Symptom, then a read-only check, then the likely cause and a fix. **V** = seen on the tablet or in a log, **A** = assumed, **A(rig)** = seen only in the x86 test rig. The message texts are quoted from the scripts in this repository. If you open an issue, attach the relevant output and remove serial numbers, `ME_ID`, eMMC `CID`, MAC addresses and your user and host names first.

## 1. On the PC: flashing

| Symptom | Meaning | Do |
|---|---|---|
| mtkclient keeps printing `Waiting for PreLoader VCOM, please reconnect mobile/iot device to brom mode` | The tablet is not in BROM mode, or the cable or port is wrong (V: this is the normal waiting message, evidence/01). | Switch the tablet off completely, hold the volume key(s), plug in the cable. My log does not say which key worked; try volume up, volume down, or both. Try another cable or a USB 2.0 port (**A**). |
| The partition list differs from the guide, or `check_gpt.py` says `DIFFERENT` | Not the tested tablet or firmware. | **Stop.** Nothing was written. The offsets in the guide belong to the tested table. |
| `cmp` after a write says the files differ | The write or the read-back was damaged. | Do not boot. Check the file with `sha256sum -c`, enter BROM again, run `printgpt` and the checker, write again, read back, compare (**A**: the procedure; the logged runs verified on the first try). |
| `w boot` is refused or the size is wrong | `boot` must be exactly 16,740,352 bytes. | Use `boot_alpine_full.bin` (the padded file), not `boot_alpine.img` (V: the builder writes both; the full file is the one that was flashed). |
| `sudo` Python cannot find mtkclient modules or `serial` | Wrong Python or missing package. | I ran `sudo /usr/bin/python3 mtk.py ...` from inside the mtkclient folder (V). Install mtkclient's requirements for that Python. |
| `printgpt` works but `w` / `ro` fail at the download agent stage | Version or local-patch differences in mtkclient (**A**). | My copy was 2.1.3 with a local patch of `dalegacy_lib.py` ("manual preloader"). Compare with your copy and ask in mtkclient's issue tracker. |
| The tablet shows nothing at all after Stage A | Boot image or LK problem. | Enter BROM and write your stock `boot` back (guide, section 6, "Rollback of `boot`"). The tablet starts at all only if the preloader, `lk` and `boot` are intact; this project's steps never write the preloader or `lk` (V as a statement about the steps). |
| After Stage A the tablet shows a rescue console | The ramdisk found no Alpine `system` (V, my own check; this is expected between Stage A and Stage B). | Do Stage B. In the rescue console `retry-boot` tries again (V: the script exists, evidence/05). |

## 2. On the PC: building

| Symptom | Do |
|---|---|
| `compiler aarch64-linux-gnu-gcc not found` or `static libc missing` | `sudo apt install gcc-aarch64-linux-gnu libc6-dev-arm64-cross` (V: the builders print these hints). |
| The root filesystem builder says qemu is not registered | `sudo apt install qemu-user-static binfmt-support` (V: printed by the builder). It needs the `qemu-user-static` package, not `qemu-user`. |
| `minirootfs ... does not match the reference hashes` | The tarball is not `alpine-minirootfs-3.24.2-aarch64.tar.gz`, or it is damaged. Download it again from Alpine's release directory (guide, section 4). Do not use a file with a different hash. |
| `this BusyBox ... lacks required applets` | Use a fuller static aarch64 BusyBox, for example Debian's or Ubuntu's `busybox-static` (V: the builder says so). |
| `source is not an Android boot image` / `unexpected header layout` / `kernel has no MTK header` | `Z380_SRC_BOOT` (default `~/official_ref/boot.bin`) is not the stock boot image of this tablet. |
| Out of disk space | The builder needs about 2 GiB free in the output folder (V). |

## 3. The first boot and the serial console

| Symptom | Likely cause | Do |
|---|---|---|
| The screen shows a text console but nothing happens when you touch it or press keys | The on-screen console is output only (V: `z380term` reads input from the USB serial line only). | Connect the cable and open the serial port (guide, section 7). |
| No `/dev/ttyACM0` on the PC | Cable without data lines, or the gadget did not start. | Check `dmesg` and `lsusb` on the PC for `0e8d:2007` (V: the ID of the serial gadget). Try another cable. |
| `Permission denied` on `/dev/ttyACM0` | The port belongs to root:dialout. | Use `sudo`, as I did, or add yourself to the `dialout` group (**A**). |
| miniterm stops with `SerialException` | The tablet's USB gadget restarted (reboot, or `z380m-usb`). | Expected (V). Start miniterm again. |
| The terminal looks empty, or the text sits "in the middle" | Cosmetic (V, evidence/03). | Press Enter a couple of times. |
| `ESC[6n` noise in the terminal | The tablet's shell asks the terminal for its size (V). | Ignore it. |
| The tablet boots into the rescue console although `system` was flashed | `system` was not written or not read back correctly, or its marker file is missing (`/etc/z380m-release`). | In the rescue console read the log it prints; from the PC compare the read-back (guide, section 6). `retry-boot` tries again. |
| `No space left on device` | The root filesystem is 487 MiB and `/tmp` is on it (V). | `df -k /; du -sk /tmp /var/cache/apk /var/log`; `apk cache clean`. |
| The network is gone after a reboot | The gadget starts serial-only at every boot (V by design). | Repeat the network steps (guide, section 8). |

## 4. The USB network

| Symptom | Likely cause | Do |
|---|---|---|
| `RTNETLINK answers: Operation not permitted` on `ip route add` | The command was typed in the PC window (V: this happened, evidence/04). | Run it in T, the window with the prompt `z380m:/# `. |
| `Command 'apk' not found` | Typed in the PC window (V, evidence/04). | Run it in T. |
| `pc_usbnet.sh up` cannot find the tablet's interface | The tablet is not in `rndis-acm` mode yet, or the USB ID differs. | Check `z380m-usb status` in T and `lsusb` for `0e8d:2008`. The script lists the USB network interfaces it sees and accepts a name: `sudo bash src/pc_usbnet.sh up <name>`. |
| The tablet pings 192.168.7.1 but not the internet | Another firewall on the PC drops forwarded packets (ufw, Docker). The script warns when it sees such a rule. | `sudo nft list ruleset \| grep -B3 -A12 'hook forward'`; allow forwarding from the tablet's interface (**A**). |
| `ping 1.1.1.1` works, names do not resolve | `/etc/resolv.conf` on the tablet. | It is static (1.1.1.1, 9.9.9.9); check the file (V: its contents, evidence/04). |
| The T window died and does not come back | `z380m-usb rndis-acm` restarts the gadget. | Wait a few seconds and start miniterm again. If nothing works, the timer you started switches back to serial-only after 10 minutes (V: the command, evidence/04). |

## 5. The desktop installer: pasting

| Symptom | Meaning | Do |
|---|---|---|
| `WRONG WINDOW: this shell is '...'` | The file was pasted into the PC window. | Paste it into T, the window whose prompt is `z380m:/# `. Nothing was done. |
| `PASTE DAMAGED: got N lines, expected M` and two checksums | The text changed in transit. | Paste again. If it keeps failing, serve the file from the PC (`python3 -m http.server 8000 --bind 192.168.7.1` in `dist/`) and run `wget -qO- http://192.168.7.1:8000/z380m_gui_paste.txt \| sh` in T (**A** on the real link, A(rig) on 127.0.0.1). |
| `UNPACK FAILED (disk full?)` | The root filesystem is full. | `df -k /`; free space; retry. |
| The prompt turns into `> ` | The paste stopped early. | Ctrl+C and paste again. |
| `syntax error: unexpected newline` | A raw script was pasted instead of the package (V: this happened with a long raw script; the package file exists because of it). | Paste `dist/z380m_gui_paste.txt`, not the scripts. |

## 6. The desktop installer: `sh /root/zgui/install.sh`

The log is `/root/gui-install.txt`; the exit code is in `/tmp/z380m-install.rc`. The checks (exit code 1) stop **before** anything is changed and print "(nothing was installed or changed)". Exits 2 to 5 happen after the install began; `/root/gui-uninstall.sh` exists from the moment the package install starts. `sh /root/zgui/install.sh check` runs only the checks.

| Message (start of it) | Meaning | Do |
|---|---|---|
| `This is not the tablet (hostname: ...)` / `Run this as root` | Wrong window. | Use T. |
| `cannot read the free space of /` | `df -k /` gave nothing usable. | Run `df -k /` by hand. |
| `/dev/fb0 is missing: there is no framebuffer` | No framebuffer node. | `ls -l /dev/fb0`; `mdev -s`. (This never happened on the tablet; the text console uses the node.) |
| `the kernel shows no virtual terminals (no vtmaster in /proc/tty/drivers, no /dev/tty0). Standard Xorg needs one.` | No VT console. | Xorg cannot run as installed. Open an issue with the lines the installer printed. |
| `no touch screen found in /proc/bus/input/devices` | No input device with "touch" in its name. | Look at `/proc/bus/input/devices`. The desktop finds the panel by that name. |
| `no internet through the USB link. Bring it up first: ...` | The USB network is not up. | Guide, section 8. |
| `apk update failed (exit N)` | The repositories are unreachable. | `ping dl-cdn.alpinelinux.org`; DNS; `sudo bash src/pc_usbnet.sh status`. |
| `required package 'NAME' is not in the package index.` | A required package name is missing from the index. | `apk search <part>`; the list is in `installer/install.sh`. Alpine renames packages now and then. |
| `the dry run failed (exit N)` | `apk add --simulate` failed (conflict, index problem). | Read the 8 lines it prints. |
| `it does not fit: need about N MiB, free M MiB.` | The size check (need = size × 1.3 + 25 MiB). | Free space (`apk cache clean`, remove packages you added). |
| exit 2: `apk add failed (exit N). Last lines:` | The packages did not install completely. | Read the last 15 lines; `sh /root/gui-uninstall.sh`; free space; retry. |
| exit 3: `something that should have been installed is not usable` | A program or driver is missing after the install. | The lines above name it (`fbdev_drv.so`, `evdev_drv.so`, `Xorg -version`, a program). |
| exit 4: `could not write some files` / `has a syntax error under this shell` | The disk is full, or a script broke under the tablet's `sh`. | `df -k /`; the message names the file. |
| exit 5: `console.sh ... does not exist` / `could not patch ... safely` | The console hook could not be applied. | The file is unchanged. Compare it with `scripts/gui/console.sh.orig`; the anchors are the line `t0=$(up)` and the log text "z380term exited with status". |

## 7. The desktop does not come up

`z380m-gui start` ends with "Xorg did not come up", or the screen stays on the console.

1. In T: `z380m-gui report` (also saved to `/root/gui-report.txt`) and read the Xorg part. Typical lines (wording from memory, **A**): `(EE) no screens found` or `Cannot open /dev/fb0`; `xf86OpenConsole: Cannot open /dev/tty0` or `Cannot find a VT` (the starter makes the VT nodes it can, and uses `vt1` when only `tty1` exists); `Server is already active for display 0` (the starter removes `/tmp/.X0-lock` and `/tmp/.X11-unix/X0` before every start, because `/tmp` survives reboots here; if you still see it, `pidof Xorg`); `Failed to load module "fbdev"` (driver package); `evdev: ... Cannot open` (touch link).
2. `ls -l /dev/input/z380m-touch /dev/fb0 /dev/tty0 /dev/tty1; cat /proc/tty/drivers; pidof Xorg z380term`.
3. A colour-fix library that breaks X is removed automatically (log: `removed /etc/z380m/gui/preload`).
4. Try the plain case: `z380m-gui swapcolors` (toggles the fix) and `z380m-gui start` again. The supervisor always returns the screen to the console after its time limit.
5. Still nothing: `sh /root/gui-uninstall.sh` restores the console. Open an issue with `/root/gui-report.txt`.

## 8. Other desktop symptoms

| Symptom | Likely cause | Do |
|---|---|---|
| Red and blue swapped | The fix is not active. | Menu > Display > Fix colours, or `z380m-gui swapcolors`. `z380m-gui status` shows `Xorg preload: ...` when it is on. If the library is missing, no compiler was found at install time: `apk add tcc` and run the installer again. |
| The desktop returns to the text console after 4 minutes (15 after the touch fix) | Nobody confirmed. | `z380m-gui keep`, or Menu > KEEP this desktop. |
| Touch does nothing | The touch bridge is not installed or not running (V: before the touch fix, touch did not work). | Install the touch fix (guide, section 10). `z380m-gui status` shows the bridge; `z380m-gui touchtest` shows what the panel sends. |
| Touch works but the pointer is mirrored or upside down | The panel counts the other way. | Run the touch fix again (it asks for the two corner taps) or edit `/etc/z380m/gui/touch.flags` (`-x` / `-y` mirror an axis). |
| The screen is frozen but T answers | X or a client hung. | `z380m-gui restart-x` or `z380m-gui stop`. |
| T prints nothing after `z380m-gui start` | The serial shell was replaced. | Press Enter once; if still dead, start miniterm again. |
| The touch fix says `the desktop is running` | It refuses to run while the desktop runs. | `z380m-gui stop`, wait for the text console, press Enter, run it again. |
| The next boot stays on the text console although `boot-enable` was done | The boot guard is set: an earlier automatic start did not reach 60 s of stable desktop. | `z380m-gui status`; read `/var/log/z380m-gui.log`; `z380m-gui boot-reset`. |
| The text console shows swapped colours after leaving the desktop | `console.sh` did not see the flag `/run/z380m-fb-panned` (**A**). | `z380m-gui status` shows whether the flag is set; the console script is `/etc/z380m/console.sh`. |

If a problem is not listed, `z380m-gui report` and `/var/log/z380m-*.log` are the places to look.

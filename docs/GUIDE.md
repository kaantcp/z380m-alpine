# Guide: Alpine Linux and a touch desktop on the ASUS ZenPad 8.0 (Z380M)

Copyright (C) 2026 [kaantcp](https://github.com/kaantcp) · GPL-3.0-only · part of [z380m-alpine](../README.md)

This guide repeats what I did on my tablet. Every command in it was either run on my tablet (the output is in [evidence/](../evidence)) or is marked as not verified. It is written for someone who is comfortable in a Linux terminal and accepts that a mistake can leave the tablet unusable.

## How to read this guide

| Label | Meaning |
|---|---|
| **V** | Verified on the real tablet: a log in `evidence/`, or my own check on the tablet. |
| **A** | Assumed. Not verified. Do not rely on it. |
| **A(rig)** | Works in the x86 test rig only; never seen on the tablet. |

Two terminals are used. **P** is a terminal on your PC. **T** is the terminal attached to the tablet over USB serial (section 7). Every command block says which one it is for. A tablet command typed in the PC window does nothing useful, and a PC command typed in the tablet window does nothing at all.

In the blocks below `REPO` is the folder where you cloned this repository and `MTK` is your mtkclient folder:

**P:**

```sh
REPO=~/z380m-alpine      # change to where you put this repository
MTK=~/mtkclient          # change to where mtkclient is
```

## 0. Stop and read this first

**Scope.** This is for the ASUS ZenPad 8.0 **Z380M (P00A)** with the MediaTek **MT8163** and for nothing else. The tested unit reported HW code `0x8163` (V, evidence/01), 1953 MB of RAM (V, evidence/03), an eMMC user area of `0x3ab400000` bytes = 14.7 GiB (V, evidence/01) and, once booted, `Linux 3.18.35 #1 SMP PREEMPT Thu Aug 9 12:33:25 CST 2018 aarch64` (V, evidence/03). Section 2 contains a check that compares your tablet's partition table with the tested one. If it says "DIFFERENT", **stop**: every offset in this guide belongs to that table.

**What gets overwritten (V).**

| Where | What | Size |
|---|---|---|
| partition `boot` (offset `0x3e40000`) | replaced by my boot image (ASUS kernel + my ramdisk) | 16,740,352 bytes |
| partition `system` (offset `0x20ba5000`), the first 512 MiB | replaced by the Alpine root filesystem; the rest of the partition is not written | 536,870,912 bytes |
| partition `expdb` (offset `0x76a5000`) | On every boot the boot ramdisk writes a text log into it, only if the partition's start and size equal the table in Appendix A (`savelog` in `src/build_boot_v3.py`; evidence/03 shows "expdb node ok (mmcblk0p14); log dumps enabled"). `expdb` is MediaTek's exception-log area. Back it up first. | up to 1,000,000 bytes at the start of the partition |

After this, Android does not start any more. **I did not back up `system`, `cache` or `userdata`** (V, listing in evidence/05), so my tablet cannot return to stock from its own backups. If you want that option, dump `system` as well (section 3). Without a dump you would have to get Android back from ASUS's own firmware for your exact model, which this project does not cover.

**What the steps of this guide never write.** The only flash commands in this guide are `w boot` and `w system`. No step writes the preloader, `lk`, `nvram`, `proinfo`, `persist`, `seccfg`, `userdata` or any other partition. (This is a statement about the commands you will type, which you can read. It is not a claim about everything I did to my tablet before this project began.)

**Risks.** A wrong or interrupted write can leave the tablet without a working `boot` or with a damaged `system`. The MediaTek boot ROM lives in the chip, not in flash, so BROM mode normally still works when flash content is damaged (**A**: general MediaTek design, not tested here by breaking anything on purpose). On the tested tablet `boot` was replaced at least twice, first by the earlier console-only image and then by the Alpine image, and the writes were read back identical (V: the first lines of evidence/01 and the `WRITE-VERIFIED` lines). Start with a charged battery and do not unplug the cable during a write. You do this at your own risk; the license (GPL-3.0) gives no warranty.

## 1. What you need

- The tablet and a USB cable that carries data.
- A PC with Linux on x86-64. Tested: Ubuntu 24.04 with Python 3.12 (my PC; evidence/04 shows Python 3.12). At least 2 GiB free for the build (the root filesystem builder checks this and stops if there is less), much more if you dump `system` or `userdata`.
- Time. Every mtkclient command needs the tablet to be power-cycled into BROM mode again (V), and reading from the tablet runs at only 0.49 MB/s (V).

Files you must supply yourself. None of them is, or will ever be, in this repository:

| File | Where it comes from |
|---|---|
| mtkclient | <https://github.com/bkerler/mtkclient> (GPL-3.0). I used version 2.1.3, run as `sudo /usr/bin/python3 mtk.py ...`, with a local patch of `dalegacy_lib.py` ("manual preloader"). The patch is not part of this repository and I cannot say whether stock 2.1.3, or a newer release, needs it (**A**). The logs show mtkclient finding the preloader by itself: "No preloader given, trying to dump preloader from ram" (V, evidence/01). |
| the stock `boot` image of your tablet | Your own dump from section 3 (`boot.bin`, 16,740,352 bytes). The builder takes only the Android header, the kernel and the ramdisk from it, so trailing padding is ignored (read from `src/build_boot_v3.py`; not tried with a raw dump, **A**). My file was a 10,006,784-byte `boot.bin`; where it came from is not recorded. The kernel is copied unchanged, and the builder stops if the layout is not the expected one (page size 2048, no second stage, MTK headers on kernel and ramdisk). |
| `alpine-minirootfs-3.24.2-aarch64.tar.gz` | Alpine's release directory (section 4). The builder refuses a file with a different hash. |
| a static aarch64 BusyBox with the 28 applets the init needs | Tested: 1,914,704 bytes (V, evidence/05: "all 28 required applets present; optional ones missing: blkid"). Ubuntu's arm64 package `busybox-static_1.36.1-6ubuntu3.1_arm64.deb` exists at <http://ports.ubuntu.com/pool/main/b/busybox/> (listing checked 18 Oct 2026). I cannot prove that it is byte-identical to the tested file (**A**). The builder checks CPU type, static linking and the applets and stops if one is wrong. |

## 2. Enter BROM mode and check that the tablet matches (read-only)

BROM mode: switch the tablet off completely, hold the volume key(s), plug in the USB cable. I did not record which key (up, down or both) I used; mtkclient prints "press and hold vol up, vol dwn, or all hw buttons and connect usb". Until it sees the tablet, mtkclient prints `Waiting for PreLoader VCOM, please reconnect mobile/iot device to brom mode` (V, evidence/01).

**P:**

```sh
cd "$MTK"
sudo /usr/bin/python3 -u mtk.py printgpt 2>&1 | tee ~/gpt_live.txt
```

Then plug the tablet in as described. (I ran plain `printgpt` without `tee`; saving the output with `tee` is **A**. If it misbehaves, run `printgpt` without it and paste the printed table into a text file.) Expected in the logged run (V, evidence/01): `CPU: MT8163()`, `HW code: 0x8163`, `SBC enabled: True`, `SLA enabled: False`, `DAA enabled: False`, `Exploitation - Kamakiri Run`, `Uploading legacy stage 1 from MTK_DA_V5.bin`, `m_emmc_ua_size = 0x3ab400000` and the partition list.

**The gate.** Compare the saved table with the tested one. The checker only reads the file:

**P:**

```sh
python3 -I "$REPO/src/check_gpt.py" ~/gpt_live.txt
```

Its first line must be `OK: 26 partitions and the total size 0x3ab400000 are identical to the tested tablet.` (the last line is the credit line `z380m-alpine by kaantcp - https://github.com/kaantcp`). Anything else (`DIFFERENT ...`, or "no partition table found") means: stop. (The checker passes on the logged `printgpt` of the tested tablet and fails on every deliberate change that was tried: a moved offset, a changed total, a missing, an extra and a re-ordered partition. Results: `tests/logs/fast_check_gpt.txt`.)

## 3. Back up

Do this before any write. Keep the backups outside the repository and **never publish them**. They contain data that is unique to your device (calibration in `nvram`, `proinfo`, `persist`, serial numbers, and `hwparam.json`, which mtkclient writes into the folder it is started in).

Speed (V): reading ran at 490.85 and 485.75 KB/s, writing at 7.02 and 8.16 MB/s (evidence/01 and 02). Extrapolated (**A**): the 23 partitions below take roughly 12 minutes to read, all of `system` about 2 hours, all of `userdata` about 6 hours.

**The minimum.** This is what I backed up on 4 Oct 2026 (V, listing in evidence/05): the 23 partitions from `proinfo` to `APD`, i.e. everything before `cache`; the partition table (`gpt.bin`, `gpt_backup.bin`); and the 4 MiB eMMC `boot1` area, which holds the preloader (`preloader_boot1.bin`). The command line of that dump was not recorded. mtkclient's own usage page (`README-USAGE.md`, checked 19 Oct 2026) documents reading several partitions in one run, and the preloader:

**P:**

```sh
mkdir -p ~/z380m_backup && cd ~/z380m_backup
P=proinfo,nvram,protect1,protect2,asus_nvm,persist,seccfg,lk,boot,recovery,secro,para,logo,expdb,frp,tee1,tee2,kb,dkb,metadata,flashinfo,ADF,APD
F=$(echo "$P" | sed 's/,/.bin,/g').bin
sudo /usr/bin/python3 "$MTK/mtk.py" r "$P" "$F"
sudo /usr/bin/python3 "$MTK/mtk.py" r preloader preloader_boot1.bin --parttype boot1
```

These two `mtk.py` lines are **A**: the syntax is the documented one, but they were not run in this form. If the multi-partition read fails, read one partition per run with the form that is V in the logs, using the offset and length from Appendix A, for example `nvram`:

**P:**

```sh
sudo /usr/bin/python3 "$MTK/mtk.py" ro 0x380000 0x500000 ~/z380m_backup/nvram.bin
```

Then check that nothing is truncated. Every file must have exactly the length of its partition (my files do), and `preloader_boot1.bin` must be 4,194,304 bytes (V: `m_emmc_boot1_size = 0x400000`):

**P:**

```sh
python3 -I "$REPO/src/check_gpt.py" --sizes ~/z380m_backup
sha256sum ~/z380m_backup/*.bin > ~/z380m_backup/SHA256SUMS      # keep this list with the backup
```

Make a second copy on another disk.

**Everything, if you may want Android back.** `rl` dumps every partition into a folder (documented by mtkclient as `python mtk.py rl out`), including `cache`, `system` (3,753,902,080 bytes) and `userdata` (11,455,000,064 bytes):

**P:**

```sh
sudo /usr/bin/python3 "$MTK/mtk.py" rl ~/z380m_full_backup
```

## 4. Prepare the PC

**P:**

```sh
sudo apt install qemu-user-static binfmt-support gcc-aarch64-linux-gnu libc6-dev-arm64-cross \
                 e2fsprogs python3-serial nftables
```

The first four package names are the ones the builders print in their own error messages, `nftables` is what `pc_usbnet.sh` asks for, and `python3-serial` provides `serial.tools.miniterm` (section 7). `e2fsprogs` provides `mke2fs` and `e2fsck`; the logged build used 1.47.0 (V, evidence/05). The root filesystem builder checks all of this and says what is missing: run it with `--preflight-only` (section 5) to see that report. That mode installs nothing and writes no image.

Get the Alpine mini root filesystem and check it. The hash below is the one the builder checks (V: evidence/05, "hashes match the reference sha256 and the sha512 published in Alpine's docker-alpine repository"):

**P:**

```sh
mkdir -p ~/alpine && cd ~/alpine
wget https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-minirootfs-3.24.2-aarch64.tar.gz
echo "9bf70a7f18ea44094cbb5f70c58f9af129c8214745743db0e68e5502cc2ce773  alpine-minirootfs-3.24.2-aarch64.tar.gz" | sha256sum -c
```

(The builder finds the only `alpine-minirootfs-*-aarch64.tar.gz` in `~/alpine` by itself.) Get BusyBox (table in section 1) and put it where the builder looks by default, `~/bbx/usr/bin/busybox` (or set `Z380_BUSYBOX`):

**P:**

```sh
mkdir -p ~/bbx && cd ~/bbx
# after downloading busybox-static_1.36.1-6ubuntu3.1_arm64.deb into this folder:
dpkg-deb -x busybox-static_1.36.1-6ubuntu3.1_arm64.deb .
ls -l usr/bin/busybox          # the tested file was 1,914,704 bytes
```

Put your stock boot image where the builder looks by default, `~/official_ref/boot.bin` (or set `Z380_SRC_BOOT`):

**P:**

```sh
mkdir -p ~/official_ref && cp ~/z380m_backup/boot.bin ~/official_ref/boot.bin
```

## 5. Build the two images

The builders read files on the PC and write the two images into an output folder (V, evidence/05).

**P:**

```sh
mkdir -p ~/z380m_v3 && cd ~/z380m_v3
cp "$REPO"/src/build_boot_v3.py "$REPO"/src/build_alpine_rootfs.py .
cp "$REPO"/src/z380term_rbswap.c z380term.c
sudo /usr/bin/python3 build_alpine_rootfs.py --preflight-only     # checks only: installs nothing, writes no image
sudo /usr/bin/python3 build_alpine_rootfs.py --size-mb 512        # about 25 s on the tested PC (V)
python3 build_boot_v3.py z380term.c ~/linux_alpine_v3
ls -l ~/linux_alpine_v3
```

Expected end of the output (V, evidence/05). The root filesystem builder: `DONE.` with `size : 536870912 bytes (limit 3745886208)` and `Nothing was flashed.` The boot builder: `busybox: 1914704 bytes, all 28 required applets present`, `kernel: 7472341 bytes, byte-identical to source`, `header: only the ramdisk size (offset 16) and the SHA1 (0x240) differ from the official boot image`, `image: 8753152 bytes, padded file: 16740352 bytes (partition 16740352)` and `BUILD OK`.

You get `~/linux_alpine_v3/system_alpine.ext4` (536,870,912 bytes) and `~/linux_alpine_v3/boot_alpine_full.bin` (16,740,352 bytes), each with a `.sha256` file. **Your hashes will differ from mine**: the root filesystem carries its build time, and a different compiler gives a different `z380term`. Compare the log lines, not the hashes. If you build again later, use a new output folder (`--out-dir` for the root filesystem builder, the second argument for the boot builder): the builders write into an existing folder without asking.

## 6. Flash (the only destructive step)

Every command needs a fresh BROM entry (section 2). Write by partition **name**. Before each write, run `printgpt` and the checker again (section 2). After each write, read the partition back and compare. The commands below are the ones that ran on the tablet (V, evidence/01 and 02).

**Stage A: `boot`.**

**P:**

```sh
cd ~/linux_alpine_v3
sha256sum -c boot_alpine_full.bin.sha256           # must say OK
cd "$MTK"
sudo /usr/bin/python3 mtk.py w boot ~/linux_alpine_v3/boot_alpine_full.bin
sudo /usr/bin/python3 mtk.py ro 0x3e40000 0xff7000 ~/linux_alpine_v3/boot_readback.bin
cmp ~/linux_alpine_v3/boot_readback.bin ~/linux_alpine_v3/boot_alpine_full.bin && echo WRITE-VERIFIED
```

Expected (V): `Write: (0xFF7000/0xFF7000), 7.02 MB/s`, `Wrote ... to sector 127488 with sector count 32696.`, then `WRITE-VERIFIED`. The file must be exactly 16,740,352 bytes; the builder pads it to that size.

Do Stage B right after Stage A. With the new `boot` and Android's old `system`, the ramdisk refuses a `system` that lacks my marker file and stays in its rescue console (`src/build_boot_v3.py`). This is what my tablet did after Stage A (V, my own check; there is no log of it in this repository).

**Stage B: `system`, first 512 MiB.** In the logged run the write took about a minute and the read-back about 18 minutes (V, evidence/02).

**P:**

```sh
cd ~/linux_alpine_v3
sha256sum -c system_alpine.ext4.sha256             # must say OK
cd "$MTK"
sudo /usr/bin/python3 mtk.py w system ~/linux_alpine_v3/system_alpine.ext4
sudo /usr/bin/python3 mtk.py ro 0x20ba5000 0x20000000 ~/linux_alpine_v3/system_readback.bin
cmp ~/linux_alpine_v3/system_readback.bin ~/linux_alpine_v3/system_alpine.ext4 && echo SYSTEM-WRITE-VERIFIED
```

Expected (V): `Write: (0x20000000/0x20000000), 8.16 MB/s`, then `SYSTEM-WRITE-VERIFIED`. mtkclient's message `Wrote ... to sector 1072424 with sector count 7331840.` names the sector count of the whole partition, although only 0x20000000 bytes were written (the progress line says so). That is how the logged run looked; do not worry about it.

**Rollback of `boot`.** Write your own stock dump back (`boot` must be exactly 16,740,352 bytes) and verify it:

**P:**

```sh
cd "$MTK"
sudo /usr/bin/python3 mtk.py w boot ~/z380m_backup/boot.bin
sudo /usr/bin/python3 mtk.py ro 0x3e40000 0xff7000 ~/z380m_backup/boot_after.bin
cmp ~/z380m_backup/boot_after.bin ~/z380m_backup/boot.bin && echo ROLLBACK-VERIFIED
```

This is the same `w boot` / `ro` / `cmp` sequence as above with a different file. Writing the stock image back was not logged for this project (**A**). Note that this brings back Android's `boot`, not Android: after Stage B the first 512 MiB of `system` hold Alpine. Android needs your own `system` dump written back.

## 7. First boot and the serial console

Unplug the cable, then start the tablet with the power button. Do not touch the screen or the volume keys during the first seconds: the boot ramdisk has a 5-second rescue window that they open (the log says "tap VOL+/VOL- or touch the screen within 5s for RESCUE", V; that the rescue console works was never tested, **A**).

What the logged boot looks like (V, evidence/03, from `/var/log/z380m-ramdisk.log`, `z380m-boot.log` and `z380m-openrc.log`): `init v3 start: kernel 3.18.35 aarch64` at 2.31 s; `system: mmcblk0p25 start=1072424 sectors=7331840` at 7.44 s; `marker ok: alpine 3.24.2 aarch64 built ...`; `userland smoke test ...: smoke-ok`; `handing over: switch_root`; `openrc: runlevels done` at 19.90 s. On the screen you get a text console (V, my own check).

The screen is output only: the console program reads input only from the USB serial line (`z380term`: "feeds bytes typed on the serial line to the command"). Connect the cable to the PC. The tablet shows up as a USB serial device (`0e8d:2007`, product `Z380M-Alpine`; V, evidence/03), normally `/dev/ttyACM0`:

**P:**

```sh
sudo /usr/bin/python3 -m serial.tools.miniterm --eol CR /dev/ttyACM0 115200
```

Leave miniterm with Ctrl+]. The tested PC used `sudo` for this. You get a root shell with the prompt `z380m:/# ` and no login (V). The root account itself has a locked password (the builder checks that, `src/build_alpine_rootfs.py`), but anyone with the cable and the powered-on tablet has a root shell on this port. This terminal is **T** from now on. It stops with a Python `SerialException` whenever the tablet's USB gadget restarts (a reboot, or `z380m-usb`); that is expected, just start miniterm again. Right after a boot the window may look empty or show the text "in the middle"; press Enter a couple of times (cosmetic; evidence/03 shows the blank prompts).

**T:**

```sh
cat /etc/alpine-release                              # 3.24.2
uname -a                                             # Linux z380m 3.18.35 ... aarch64
df -h /                                              # 487.6M size, 433.3M available on the fresh image
cat /var/log/z380m-ramdisk.log /var/log/z380m-boot.log /var/log/z380m-openrc.log
```

(V, evidence/03. BusyBox's `df` labels that line `tmpfs ... /tmp`. `/` and `/tmp` are on the same device (V, evidence/04: `stat` shows the same device number for both), so the numbers are those of the root filesystem.)

## 8. Bring up the USB network

The boot ramdisk starts the USB gadget with the serial function only, at every boot (`src/build_boot_v3.py`), so repeat this after every boot when you need the internet (whether anything survives a reboot was not tested, **A**). The helper on the tablet is `z380m-usb`; its own help text still says "never tried on this tablet", but evidence/04 shows that it was tried and worked. The first command below starts a timer that switches back to serial-only after 10 minutes unless you confirm, so a failed switch cannot lock you out. `z380m-usb` also announces its own fall-back to serial-only after 25 s without a network interface (V as printed in evidence/04; the fall-back itself did not trigger in the logs).

**T:**

```sh
rm -f /tmp/usb-ok; ( setsid sh -c 'sleep 600; [ -e /tmp/usb-ok ] || z380m-usb acm' </dev/null >/dev/null 2>&1 & )
z380m-usb rndis-acm
```

The T window dies with a `SerialException`: expected. On the PC:

**P:**

```sh
sudo bash "$REPO/src/pc_usbnet.sh" up        # finds the tablet by its USB ID 0e8d:2008
sudo /usr/bin/python3 -m serial.tools.miniterm --eol CR /dev/ttyACM0 115200     # T again
```

**T:**

```sh
touch /tmp/usb-ok
ip route add default via 192.168.7.1
ping -c 3 192.168.7.1; ping -c 3 1.1.1.1; ping -c 3 dl-cdn.alpinelinux.org
apk update
```

Expected (V, evidence/04): the pings answer, and `apk update` fetches `main` and `community` of v3.24 and ends with `OK: 28554 distinct packages available` (the number changes as Alpine publishes). The tablet is 192.168.7.2/24.

What `pc_usbnet.sh up` changes on the PC (the script's own description; V that it ran, evidence/04): the tablet's interface gets 192.168.7.1/24 (and NetworkManager, if it runs, is told to leave that one interface alone); `net.ipv4.ip_forward` is set to 1 (the old value is saved); one nftables table `z380m_usbnet` gets one masquerade rule for 192.168.7.0/24. It refuses an interface that carries your default route, is not USB, or already has an IPv4 address. If the tablet can ping 192.168.7.1 but not the internet, another firewall on the PC (ufw, Docker) may drop forwarded packets; the script warns when it sees such a rule. Check and undo:

**P:**

```sh
sudo bash "$REPO/src/pc_usbnet.sh" status
sudo bash "$REPO/src/pc_usbnet.sh" down
```

(Messages printed by the tablet-side installers mention `~/linux_alpine_v3/pc_usbnet.sh`, which is where I kept a copy. Use the path where your copy is.) Do not run `z380m-usb` while the desktop is running: it restarts the gadget and drops T.

## 9. Install the desktop

This installs Xorg (fbdev driver), the evdev driver, JWM, xterm, svkbd and a few more packages into Alpine's root filesystem. It writes nothing to flash. Before it changes anything, it checks that the host name is `z380m`, that you are root, that `/dev/fb0`, a virtual terminal and a touch screen exist, that the internet works, that every package is in the index (`apk add --simulate`) and that there is room (it needs size × 1.3 + 25 MiB). The installer is `dist/z380m_gui_paste.txt`. Its first version ran on the tablet (V); the file in this repository was rebuilt on 20 Oct 2026 (same logic, new message wording, credit line) and has passed the rig tests (**A(rig)**), not the tablet yet (see the note at the end of section 10 and `docs/CHANGELOG.md`).

Open the file on the PC in a text editor, copy all of it and paste it into the T window. It refuses to run in any other window (it checks the host name and root) and refuses to unpack if any character was damaged on the way (sha256 check). It unpacks into `/root/zgui` and runs a dry run that installs nothing (V: it ran so on the tablet).

**T:** paste the whole file, then:

```sh
sh /root/zgui/install.sh              # installs; the log is /root/gui-install.txt
z380m-gui start                       # look at the tablet screen
```

On the first start the screen shows a colour check with three bars (red, green, blue). The desktop returns to the text console by itself after 240 s unless you confirm it with **Menu > KEEP this desktop** on the tablet or `z380m-gui keep` in T. At this stage Xorg runs but the touch screen does not work yet (V, my own check), so just look and continue with section 10, which needs the desktop stopped (`z380m-gui stop`). If red and blue look swapped, the menu has **Display > Fix colours**; on the tested tablet the colours were right (V, my own check).

Undo at any time: `sh /root/gui-uninstall.sh` (it stops the desktop, removes the packages that were installed for it and its files, and puts the original text-console script back).

## 10. Touch

The panel (`elan-touchscreen`, `/dev/input/event11`) speaks only the multitouch protocol, type B. Its capability bits are `ABS_MT_SLOT`, `ABS_MT_TOUCH_MAJOR`, `ABS_MT_POSITION_X/Y`, `ABS_MT_TRACKING_ID` and `ABS_PRESSURE`, with no `BTN_TOUCH` and no `ABS_X`/`ABS_Y` (V, decoded from evidence/03). Xorg's evdev driver needs the single-touch events (**A**: that this is why touch failed; the failure itself is V, from my own check). `z380m-touchbridge` reads the panel and creates a virtual single-touch screen through `/dev/uinput`. `dist/z380m_touchfix.sh` installs it together with desktop starter version 2. Its first version ran on the tablet and touch worked (V, my own check); the file in this repository was rebuilt on 20 Oct 2026 (same logic, new message wording, credit line, a rebuilt bridge program) and has passed the rig tests (**A(rig)**), not the tablet yet. Its sha256 is in `dist/SHA256SUMS`:

```
c6c1436614609e2fa41d3300e9eb691ed60894a260231554739895d079ef35a6  z380m_touchfix.sh
```

The file will not run while the desktop is running, so stop it first. How the file reached the tablet is not in the logs; the route below is the one the rig tests use (**A(rig)**), and any other way is fine as long as the sha256 matches.

**T:**

```sh
z380m-gui stop                        # wait for the text console, press Enter
```

**P:**

```sh
cd "$REPO/dist" && python3 -m http.server 8000 --bind 192.168.7.1
```

**T:**

```sh
wget -O /root/z380m_touchfix.sh http://192.168.7.1:8000/z380m_touchfix.sh
echo "c6c1436614609e2fa41d3300e9eb691ed60894a260231554739895d079ef35a6  /root/z380m_touchfix.sh" | sha256sum -c
sh /root/z380m_touchfix.sh
```

Stop the web server on the PC with Ctrl+C when the file is on the tablet. What the script does (it writes only inside Alpine's root filesystem): it checks that it is the tablet, that the desktop pack is installed and that the desktop is not running; unpacks the two files stored inside it and checks their sha256; keeps your present `z380m-gui` and `console.sh` as `z380m-gui.v1` and `console.sh.v1`, then installs version 2 and the bridge; checks that the bridge runs on this kernel and that `/dev/uinput` works; asks for two corner taps (press Enter in T, then tap the top-left, and later the bottom-right, corner of the tablet screen a few times) to learn which way the panel counts, and saves that in `/etc/z380m/gui/touch.flags`; and starts the desktop, which returns to the text console after 15 minutes unless you tap **Menu > KEEP this desktop** (or type `z380m-gui keep`). It also makes the text console skip its red/blue swap after the desktop has run (**A**: X's first screen update changes the display's pixel format). The log is `/root/z380m_touchfix.log`.

Result on the tested tablet, with the first version of the file: touch works in the desktop (V, my own check; there is no log of it in this repository).

**A note on versions.** The files in `dist/` are generated from the sources in this repository (`installer/mkpaste.py`, `installer/touchfix/build_touchfix.py`, and `src/touchbridge/build.sh` for the bridge program), and `tests/verify_dist.py` checks that. The paste file installs desktop starter version 1 (`scripts/obsolete/z380m-gui.v1`); the touch fix then installs version 2 (`scripts/gui/z380m-gui`). The first versions of both files ran on the tablet (V); `docs/CHANGELOG.md` says how they differ from the files in `dist/`.

## 11. Start the desktop at power-on (optional)

**T:**

```sh
z380m-gui boot-enable             # start the desktop at every boot (OpenRC service "z380m-gui")
```

**A(rig)**: implemented and tested in the rig; I have not tested a reboot on the tablet. A boot guard protects you: if the previous automatic start did not reach one minute of stable desktop (a hang or a power cut), the next boot stays on the text console until you type `z380m-gui boot-reset`. Undo: `z380m-gui boot-disable`.

## 12. Undo summary

| What | How |
|---|---|
| start at power-on | `z380m-gui boot-disable` |
| touch fix | `z380m-gui stop`, then `sh /root/z380m_touchfix.sh undo` (puts `z380m-gui.v1` and `console.sh.v1` back, removes the bridge and `touch.flags`) |
| desktop and its packages | `sh /root/gui-uninstall.sh` |
| both | first the touch fix, then the desktop (**A**: the order follows from reading the scripts; not run) |
| PC network changes | `sudo bash "$REPO/src/pc_usbnet.sh" down` |
| the `boot` partition | section 6, "Rollback of `boot`" |
| the `system` partition | write your own `system` dump back (section 3, "Everything"), or rebuild and re-flash `system_alpine.ext4`; that erases everything installed on the tablet since the last flash |

## 13. Known limits

- **No Wi-Fi.** There is no `wlan0`: the boot summary lists only `lo`, `ifb0`, `ifb1`, `tunl0`, `sit0` and `ip6tnl0` (V, evidence/03). The chip is not identified; it would need vendor firmware and drivers that this project does not have (**A**).
- Not attempted: Bluetooth, sound, camera, sensors, GPU acceleration, suspend, battery information, screen rotation.
- The desktop turns screen blanking and power saving off (`xset s off s noblank -dpms` in `scripts/gui/session.sh`): watch the battery.
- The tablet clock is not reliable (the installers themselves print "the tablet clock may be wrong"). Set it by hand if you need it (`date -s`).
- `/tmp` is on the root filesystem (V, evidence/04), so it survives reboots.
- The serial port gives a root shell without a login (section 7). `sshd` is installed but not enabled. Do not enable password or empty-password logins; use a key. The root filesystem builder has `--ssh-pubkey FILE`, which installs the key and enables sshd; it was not tested on the tablet (**A**).
- Everything you install on the tablet lives in the 512 MiB root filesystem. Re-flashing `system_alpine.ext4` erases it. `userdata` (10.7 GiB) is unused.

## 14. When something goes wrong

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). If you try this on a Z380M, please open an issue on the repository with the output of `check_gpt.py`, which steps you ran, and what happened. Do not post dumps, or logs that contain serial numbers, the `ME_ID` or the eMMC `CID`.

## Appendix A: The partition table of the tested tablet

Live `printgpt` output from the tablet on 10 Oct 2026 (V, [evidence/01](../evidence/01_stageA_printgpt_and_boot_write.txt)); `src/check_gpt.py` compares against exactly this. The nodes of `expdb` (p14) and `system` (p25) are V (evidence/03: `mmcblk0p14`, `mmcblk0p25`); the other node numbers follow the table order (**A**).

```
name       offset        length        node
proinfo    0x00080000    0x00300000    p1
nvram      0x00380000    0x00500000    p2      (Wi-Fi/BT calibration and MAC probably live here, A. Never overwrite.)
protect1   0x00880000    0x00a00000    p3
protect2   0x01280000    0x00a00000    p4
asus_nvm   0x01c80000    0x00100000    p5
persist    0x01d80000    0x02000000    p6
seccfg     0x03d80000    0x00040000    p7
lk         0x03dc0000    0x00080000    p8
boot       0x03e40000    0x00ff7000    p9      (16,740,352 bytes)  <- written by this guide
recovery   0x04e37000    0x00ff7000    p10
secro      0x05e2e000    0x00ff7000    p11
para       0x06e25000    0x00080000    p12
logo       0x06ea5000    0x00800000    p13
expdb      0x076a5000    0x00a00000    p14     (the boot ramdisk writes a text log here)
frp        0x080a5000    0x00100000    p15
tee1       0x081a5000    0x00500000    p16
tee2       0x086a5000    0x00500000    p17
kb         0x08ba5000    0x00200000    p18
dkb        0x08da5000    0x00200000    p19
metadata   0x08fa5000    0x02000000    p20
flashinfo  0x0afa5000    0x01000000    p21
ADF        0x0bfa5000    0x02000000    p22
APD        0x0dfa5000    0x06400000    p23
cache      0x143a5000    0x0c800000    p24
system     0x20ba5000    0xdfc00000    p25     (3,753,902,080 bytes; first 512 MiB = Alpine)  <- written by this guide
userdata   0x1007a5000   0x2aac56e00   p26     (11,455,000,064 bytes, above 4 GiB)
total disk 0x3ab400000
```

The largest image that keeps every write of `system` below 4 GiB is 3,745,886,208 bytes (4 GiB minus the start of `system`). Whether the tablet's download agent accepts addresses above 4 GiB was not tested (**A**), which is why `userdata` was never used.

## Appendix B: What each log proves

| Log | Shows |
|---|---|
| [evidence/01](../evidence/01_stageA_printgpt_and_boot_write.txt) | BROM entry, mtkclient output for this tablet, the full partition table, `w boot` and the verified read-back. Its first lines show that the earlier console-only image had been read back identical. |
| [evidence/02](../evidence/02_stageB_system_write_and_readback.txt) | Boot read-back, `w system`, the verified read-back of the first 512 MiB. |
| [evidence/03](../evidence/03_tablet_first_boot_report.txt) | The first Alpine boot: kernel, mounts, the ramdisk, boot and OpenRC logs, framebuffer, input devices (including the touch panel's capabilities), USB gadget. |
| [evidence/04](../evidence/04_usbnet_nat_apk_update.txt) | USB network through the PC, the pings and `apk update` against the real mirrors. |
| [evidence/05](../evidence/05_final_build_and_backup_listing.txt) | The final build output (root filesystem and boot image) and the listing of my backup folders. |

Identifiers that are unique to my devices (serial numbers, `ME_ID`, eMMC `CID`, partition GUIDs, MAC addresses) and the PC's user and host names were replaced in these copies. Everything else is as printed.

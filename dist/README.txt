Copyright (C) 2026 kaantcp (https://github.com/kaantcp) - GPL-3.0-only (see ../LICENSE) - part of z380m-alpine

dist/ - the two installer files

  z380m_gui_paste.txt   desktop installer ("step 1 of 3"). Paste the whole file into the tablet's shell (the T window).
                        docs/GUIDE.md, section 9.
  z380m_touchfix.sh     touch fix: the touch bridge program and desktop starter version 2 in one file.
                        docs/GUIDE.md, section 10.
  SHA256SUMS            check with:  cd dist && sha256sum -c SHA256SUMS

How they relate to the sources in this repository
  Both files are generated from the sources. Everything inside them equals the repository files byte for byte:

  z380m_gui_paste.txt   holds the 13 files named in installer/payload.list. The starter inside is desktop starter
                        version 1 (scripts/obsolete/z380m-gui.v1); the repository's scripts/gui/z380m-gui is version 2.
                        Rebuild:  python3 -I installer/mkpaste.py . <output folder>
  z380m_touchfix.sh     its code equals installer/touchfix/touchfix_template.sh (placeholders filled), its program is
                        installer/touchfix/z380m-touchbridge.arm64 (built from src/touchbridge/), and its desktop starter is
                        scripts/gui/z380m-gui (version 2).
                        Rebuild:  python3 -I installer/touchfix/build_touchfix.py installer/touchfix/touchfix_template.sh \
                                  installer/touchfix/z380m-touchbridge.arm64 scripts/gui/z380m-gui <output file>

  Check all of this yourself:  python3 -I tests/verify_dist.py .      (run in the repository root; reads files only)

Status: the first versions of both files ran on the tablet. The files in this folder were rebuilt on 20 Oct 2026 (new message
wording and credit line, same logic). They pass the rig tests (A(rig)) and have not been run on the tablet yet.

See docs/CHANGELOG.md for the history and docs/TESTING.md for what the tests do and do not prove.

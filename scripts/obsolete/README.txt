Copyright (C) 2026 kaantcp (https://github.com/kaantcp) - GPL-3.0-only (see ../../LICENSE) - part of z380m-alpine

scripts/obsolete/ - kept on purpose

  z380m-gui.v1   The first desktop starter (version 1), the one inside dist/z380m_gui_paste.txt. It is not the current
                 starter (scripts/gui/z380m-gui, version 2). It is kept because
                 - the paste file installs it (installer/payload.list),
                 - the touch fix (dist/z380m_touchfix.sh) backs it up on the tablet as z380m-gui.v1 and "undo" puts it back,
                 - the tests use it (scripts/test_touchfix_int.sh) as the "before" state,
                 - tests/verify_dist.py compares it with the copy inside the paste file.

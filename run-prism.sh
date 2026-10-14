#!/usr/bin/env bash
# Start Prism from source, from any terminal — including VS Code's.
# Run it with:  ./run-prism.sh      (see "If Prism will not start" in README.md)
cd "$(dirname "$0")" || exit 1

# A snap-packaged VS Code (Ubuntu) exports its own GTK/GLib settings into every
# terminal it opens. Qt loads them and aborts at startup with
#   GLib-GIO-ERROR: Settings schema 'org.gnome.settings-daemon.plugins.xsettings'
#   does not contain a key named 'antialiasing'      (exit 133, "Trace/breakpoint trap")
# Clearing them is harmless anywhere else.
unset GTK_PATH GIO_MODULE_DIR GTK_EXE_PREFIX GTK_IM_MODULE_FILE GSETTINGS_SCHEMA_DIR GTK_MODULES LOCPATH
if [ -n "${XDG_DATA_DIRS_VSCODE_SNAP_ORIG+x}" ]; then
  export XDG_DATA_DIRS="$XDG_DATA_DIRS_VSCODE_SNAP_ORIG"
fi

PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" main.py "$@"

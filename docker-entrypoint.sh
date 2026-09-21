#!/bin/sh
set -eu

preview_font_dir=/usr/local/share/fonts/windows
if [ -d "$preview_font_dir" ] && command -v fc-cache >/dev/null 2>&1; then
  fc-cache -f "$preview_font_dir" >/dev/null 2>&1 || true
fi

exec "$@"

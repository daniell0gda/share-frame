#!/usr/bin/env bash
# Install share-frame for the current user (no sudo). Safe to run again.
# The Omarchy plugin runs this on load; run it by hand for a standalone install.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUIET=0
[[ ${1:-} == --quiet ]] && QUIET=1
say() { if ((QUIET)); then :; else echo "$@"; fi; }

BIN=~/.local/bin
PICKER="$BIN/share-frame-picker"
XDPH=~/.config/hypr/xdph.conf
portal_config_changed=0

report_missing_packages() {
  local missing=()
  for p in python-gobject gtk4 gtk4-layer-shell slurp socat; do
    pacman -Q "$p" &>/dev/null || missing+=("$p")
  done
  if ((${#missing[@]})); then
    echo "MISSING: ${missing[*]}"
    say "Install the missing packages with: omarchy-pkg-add ${missing[*]}"
  fi
}

write_picker_launcher() {
  rm -f "$PICKER"
  cat > "$PICKER" <<LAUNCHER
#!/usr/bin/env bash
[[ -x "$HERE/share-frame-picker" ]] && exec "$HERE/share-frame-picker" "\$@"
for p in hyprland-preview-share-picker hyprland-share-picker; do
  command -v "\$p" >/dev/null && exec "\$p" "\$@"
done
exit 1
LAUNCHER
  chmod +x "$PICKER"
}

register_picker_with_portal() {
  if [[ ! -f $XDPH ]]; then
    mkdir -p ~/.config/hypr
    printf 'screencopy {\n    allow_token_by_default = true\n    custom_picker_binary = %s\n}\n' "$PICKER" > "$XDPH"
    portal_config_changed=1
  elif ! grep -q custom_picker_binary "$XDPH"; then
    cp "$XDPH" "$XDPH.bak.$(date +%Y%m%d%H%M%S)"
    if grep -q 'screencopy *{' "$XDPH"; then
      sed -i "/screencopy *{/a\\    custom_picker_binary = $PICKER" "$XDPH"
    else
      printf '\nscreencopy {\n    custom_picker_binary = %s\n}\n' "$PICKER" >> "$XDPH"
    fi
    portal_config_changed=1
  elif ! grep -q share-frame-picker "$XDPH"; then
    say "NOTE: $XDPH already sets another custom_picker_binary; left unchanged."
    say "      To use share-frame, set: custom_picker_binary = $PICKER"
  fi
}

write_launcher_entry() {
  mkdir -p ~/.local/share/applications
  cat > ~/.local/share/applications/share-frame.desktop <<DESKTOP
[Desktop Entry]
Type=Application
Name=share frame
Comment=Toggle a border around the screen region you share
Exec=$BIN/share-frame toggle
Icon=video-display
Terminal=false
Categories=Utility;
DESKTOP
}

report_missing_packages
mkdir -p "$BIN"
ln -sf "$HERE/share-frame" "$BIN/share-frame"
write_picker_launcher
register_picker_with_portal
write_launcher_entry

if ((portal_config_changed)); then
  systemctl --user restart xdg-desktop-portal-hyprland 2>/dev/null || true
  say "Registered the share-frame picker and restarted the screencast portal."
fi
say "Installed. Run 'share-frame pick' to choose a region."

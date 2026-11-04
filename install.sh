#!/usr/bin/env bash
# Install share-frame for the current user (no sudo). Safe to run again.
#   --quiet            used by the Omarchy plugin on load; never edits your Hyprland config
#   --register-portal  also add the picker to ~/.config/hypr/xdph.conf (a backup is kept)
# Run by hand without options, it asks before touching xdph.conf.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUIET=0
REGISTER_PORTAL=0
case "${1:-}" in
  --quiet) QUIET=1 ;;
  --register-portal) REGISTER_PORTAL=1 ;;
esac
say() { if ((QUIET)); then :; else echo "$@"; fi; }

BIN=~/.local/bin
PICKER="$BIN/share-frame-picker"
XDPH=~/.config/hypr/xdph.conf

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

portal_registered() {
  [[ -f $XDPH ]] && grep -q 'custom_picker_binary.*share-frame-picker' "$XDPH"
}

another_picker_configured() {
  [[ -f $XDPH ]] && grep -q custom_picker_binary "$XDPH" && ! portal_registered
}

register_picker_with_portal() {
  if [[ ! -f $XDPH ]]; then
    mkdir -p ~/.config/hypr
    printf 'screencopy {\n    allow_token_by_default = true\n    custom_picker_binary = %s\n}\n' "$PICKER" > "$XDPH"
  else
    cp "$XDPH" "$XDPH.bak.$(date +%Y%m%d%H%M%S)"
    if grep -q 'screencopy *{' "$XDPH"; then
      sed -i "/screencopy *{/a\\    custom_picker_binary = $PICKER" "$XDPH"
    else
      printf '\nscreencopy {\n    custom_picker_binary = %s\n}\n' "$PICKER" >> "$XDPH"
    fi
  fi
  systemctl --user restart xdg-desktop-portal-hyprland 2>/dev/null || true
  say "Registered the share-frame picker in $XDPH (an existing file was backed up) and restarted the screencast portal."
}

consent_to_register_portal() {
  ((REGISTER_PORTAL)) && return 0
  ((QUIET)) && return 1
  [[ -t 0 ]] || return 1
  read -r -p "Add share-frame-picker to $XDPH? A backup is kept. [y/N] " answer
  [[ $answer == [yY]* ]]
}

handle_portal_registration() {
  portal_registered && return 0
  if another_picker_configured; then
    say "NOTE: $XDPH already sets another custom_picker_binary; left unchanged."
    say "      To use share-frame, set: custom_picker_binary = $PICKER"
    return 0
  fi
  if consent_to_register_portal; then
    register_picker_with_portal
  else
    echo "PORTAL: unregistered"
    say "To share the frame area, run: $HERE/install.sh --register-portal"
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
write_launcher_entry
handle_portal_registration
say "Installed. Run 'share-frame pick' to choose a region."
